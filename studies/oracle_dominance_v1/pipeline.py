"""Oracle dominance v1 research scaffold.

This module is intentionally repo-grounded:
- Monarch indexer defines the market universe we care about.
- Morpho API provides live market state plus historical market time series.
- Oracles scanner output defines the market's oracle/feed/provider composition.

The implementation stays stdlib-only so it can run without extra setup.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import csv
import json
import os
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MORPHO_API_URL = "https://blue-api.morpho.org/graphql"
MONARCH_MARKETS_PAGE_SIZE = 1_000
MORPHO_MARKETS_PAGE_SIZE = 500
SUPPORTED_CHAINS = [1, 10, 8453, 42161, 137, 130, 999, 143, 42793]
REPO_ROOT = Path(__file__).resolve().parents[2]
MONARCH_REPO_ROOT = Path("/Users/anton/projects/monarch")


def _load_local_env() -> None:
    candidates = (
        REPO_ROOT / ".env",
        REPO_ROOT / ".env.local",
        MONARCH_REPO_ROOT / ".env",
        MONARCH_REPO_ROOT / ".env.local",
        Path.cwd() / ".env",
        Path.cwd() / ".env.local",
    )
    for candidate in candidates:
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_local_env()


MONARCH_MARKETS_QUERY = """
query EnvioMarketsPage($limit: Int!, $offset: Int!, $zeroAddress: String!) {
  Market(
    where: {
      collateralToken: { _neq: $zeroAddress }
      irm: { _neq: $zeroAddress }
    }
    limit: $limit
    offset: $offset
    order_by: [{ chainId: asc }, { marketId: asc }]
  ) {
    chainId
    marketId
    collateralToken
    oracle
  }
}
"""

MORPHO_MARKETS_QUERY = """
query getMarkets($first: Int, $skip: Int, $where: MarketFilters) {
  markets(first: $first, skip: $skip, where: $where) {
    items {
      lltv
      uniqueKey
      irmAddress
      oracle {
        address
      }
      morphoBlue {
        address
        chain {
          id
        }
      }
      loanAsset {
        address
        symbol
        decimals
      }
      collateralAsset {
        address
        symbol
        decimals
      }
      state {
        borrowAssets
        supplyAssets
        borrowAssetsUsd
        supplyAssetsUsd
      }
    }
    pageInfo {
      countTotal
    }
  }
}
"""

MARKET_HISTORICAL_DATA_QUERY = """
query getMarketHistoricalData($uniqueKey: String!, $options: TimeseriesOptions!, $chainId: Int) {
  marketByUniqueKey(uniqueKey: $uniqueKey, chainId: $chainId) {
    historicalState {
      supplyAssetsUsd(options: $options) {
        x
        y
      }
      borrowAssetsUsd(options: $options) {
        x
        y
      }
      supplyAssets(options: $options) {
        x
        y
      }
      borrowAssets(options: $options) {
        x
        y
      }
    }
  }
}
"""


@dataclass(slots=True)
class MarketRef:
    unique_key: str
    chain_id: int
    oracle_address: str
    loan_asset_address: str
    loan_asset_symbol: str
    loan_asset_decimals: int
    collateral_asset_address: str
    collateral_asset_symbol: str
    supply_assets: str | None = None
    borrow_assets: str | None = None
    supply_assets_usd: float | None = None
    borrow_assets_usd: float | None = None


@dataclass(slots=True)
class VendorLeg:
    vendor: str
    leg_key: str
    is_hardcoded_assumption: bool = False
    source_field: str | None = None


@dataclass(slots=True)
class MarketVendorAllocation:
    unique_key: str
    chain_id: int
    vendors: list[str] = field(default_factory=list)
    recognized_vendor_count: int = 0
    hardcoded_leg_count: int = 0
    unknown_leg_count: int = 0


@dataclass(slots=True)
class VendorExposurePoint:
    as_of: date
    vendor: str
    exposure_usd: float
    metric: str  # e.g. supply_usd, borrow_usd, repriced_supply_usd


def _env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value else None


def _monarch_api_url() -> str:
    for key in (
        "MONARCH_INDEXER_ENDPOINT",
        "MONARCH_API_ENDPOINT",
        "NEXT_PUBLIC_MONARCH_API_NEW",
        "MONARCH_API_URL",
        "MONARCH_GRAPHQL_API_URL",
    ):
        value = _env(key)
        if value:
            return value
    raise RuntimeError("Monarch endpoint not configured. Set MONARCH_INDEXER_ENDPOINT or MONARCH_API_ENDPOINT locally.")


def _monarch_api_key() -> str | None:
    for key in (
        "MONARCH_API_KEY",
        "NEXT_PUBLIC_MONARCH_API_KEY",
        "MONARCH_GRAPHQL_API_KEY",
    ):
        value = _env(key)
        if value:
            return value
    return None


def _oracle_gist_base_url() -> str:
    for key in (
        "ORACLE_GIST_BASE_URL",
        "NEXT_PUBLIC_ORACLE_GIST_BASE_URL",
    ):
        value = _env(key)
        if value:
            return value.rstrip("/")
    raise RuntimeError("Oracle gist base URL not configured in environment")


def _json_post(url: str, payload: dict, headers: dict[str, str] | None = None) -> dict:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def _json_get(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body[:400]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Data-source adapters
# ---------------------------------------------------------------------------

def fetch_monarch_market_universe() -> dict[tuple[int, str], str]:
    """Return {(chain_id, unique_key): oracle_address} from the Monarch indexer."""
    api_url = _monarch_api_url()
    api_key = _monarch_api_key()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    zero_address = "0x0000000000000000000000000000000000000000"

    markets: dict[tuple[int, str], str] = {}
    offset = 0
    while True:
        result = _json_post(
            api_url,
            {
                "query": MONARCH_MARKETS_QUERY,
                "variables": {
                    "limit": MONARCH_MARKETS_PAGE_SIZE,
                    "offset": offset,
                    "zeroAddress": zero_address,
                },
            },
            headers=headers,
        )
        rows = result.get("data", {}).get("Market", [])
        if not rows:
            break

        for row in rows:
            chain_id = int(row["chainId"])
            unique_key = row["marketId"].lower()
            oracle_address = (row.get("oracle") or "").lower()
            if oracle_address:
                markets[(chain_id, unique_key)] = oracle_address

        if len(rows) < MONARCH_MARKETS_PAGE_SIZE:
            break
        offset += len(rows)

    return markets



def fetch_morpho_markets_for_chain(chain_id: int) -> list[MarketRef]:
    markets: list[MarketRef] = []
    skip = 0
    total = None

    while True:
        result = _json_post(
            MORPHO_API_URL,
            {
                "query": MORPHO_MARKETS_QUERY,
                "variables": {
                    "first": MORPHO_MARKETS_PAGE_SIZE,
                    "skip": skip,
                    "where": {"chainId_in": [chain_id]},
                },
            },
        )
        page = result.get("data", {}).get("markets", {})
        items = page.get("items", [])
        total = page.get("pageInfo", {}).get("countTotal", total)
        if not items:
            break

        for item in items:
            loan_asset = item.get("loanAsset") or {}
            collateral_asset = item.get("collateralAsset") or {}
            state = item.get("state") or {}
            oracle = item.get("oracle") or {}
            if not loan_asset.get("address") or not collateral_asset.get("address"):
                continue
            markets.append(
                MarketRef(
                    unique_key=item["uniqueKey"].lower(),
                    chain_id=int(item["morphoBlue"]["chain"]["id"]),
                    oracle_address=(oracle.get("address") or "").lower(),
                    loan_asset_address=loan_asset["address"].lower(),
                    loan_asset_symbol=loan_asset.get("symbol") or "UNKNOWN",
                    loan_asset_decimals=int(loan_asset.get("decimals") or 18),
                    collateral_asset_address=collateral_asset["address"].lower(),
                    collateral_asset_symbol=collateral_asset.get("symbol") or "UNKNOWN",
                    supply_assets=state.get("supplyAssets"),
                    borrow_assets=state.get("borrowAssets"),
                    supply_assets_usd=float(state.get("supplyAssetsUsd") or 0),
                    borrow_assets_usd=float(state.get("borrowAssetsUsd") or 0),
                )
            )

        skip += len(items)
        if total is not None and skip >= total:
            break

    return markets



def fetch_live_markets() -> list[MarketRef]:
    """Fetch live market list filtered to Monarch's market universe when available."""
    monarch_universe: dict[tuple[int, str], str] = {}
    try:
        monarch_universe = fetch_monarch_market_universe()
    except Exception as exc:
        print(f"[oracle-dominance-v1] Monarch market universe fetch failed; falling back to Morpho-only market discovery: {exc}")

    chain_ids = sorted({chain_id for chain_id, _ in monarch_universe.keys()}) or SUPPORTED_CHAINS

    merged: list[MarketRef] = []
    for chain_id in chain_ids:
        for market in fetch_morpho_markets_for_chain(chain_id):
            if monarch_universe:
                key = (market.chain_id, market.unique_key)
                monarch_oracle = monarch_universe.get(key)
                if not monarch_oracle:
                    continue
                if not market.oracle_address:
                    market.oracle_address = monarch_oracle
            merged.append(market)

    return merged



def fetch_oracle_metadata() -> dict[tuple[int, str], dict]:
    base_url = _oracle_gist_base_url()
    live_markets = fetch_live_markets()
    chain_ids = sorted({market.chain_id for market in live_markets})

    metadata: dict[tuple[int, str], dict] = {}
    for chain_id in chain_ids:
        payload = _json_get(f"{base_url}/oracles.{chain_id}.json")
        for oracle in payload.get("oracles", []):
            metadata[(int(chain_id), oracle["address"].lower())] = oracle
    return metadata



def fetch_market_history(unique_key: str, chain_id: int, days: int = 180) -> list[dict]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    result = _json_post(
        MORPHO_API_URL,
        {
            "query": MARKET_HISTORICAL_DATA_QUERY,
            "variables": {
                "uniqueKey": unique_key,
                "chainId": chain_id,
                "options": {
                    "startTimestamp": int(start.timestamp()),
                    "endTimestamp": int(end.timestamp()),
                    "interval": "DAY",
                },
            },
        },
    )
    historical = result.get("data", {}).get("marketByUniqueKey", {}).get("historicalState", {})
    by_ts: dict[int, dict] = {}
    for field in ("supplyAssets", "borrowAssets", "supplyAssetsUsd", "borrowAssetsUsd"):
        for point in historical.get(field, []) or []:
            ts = int(point["x"])
            row = by_ts.setdefault(ts, {"timestamp": ts})
            row[field] = point.get("y")
    return [by_ts[key] for key in sorted(by_ts)]


# ---------------------------------------------------------------------------
# Attribution helpers
# ---------------------------------------------------------------------------

def _feed_from_output_section(section: dict | None, source_field: str) -> list[VendorLeg]:
    if not section:
        return []

    legs: list[VendorLeg] = []
    for feed_key in ("baseFeedOne", "baseFeedTwo", "quoteFeedOne", "quoteFeedTwo"):
        feed = section.get(feed_key)
        if not feed:
            continue
        provider = feed.get("provider")
        if provider:
            legs.append(VendorLeg(vendor=str(provider), leg_key=f"{source_field}:{feed_key}", source_field=feed_key))
        else:
            legs.append(
                VendorLeg(
                    vendor="Unknown",
                    leg_key=f"{source_field}:{feed_key}",
                    source_field=feed_key,
                )
            )

    for vault_key in ("baseVault", "quoteVault"):
        if section.get(vault_key):
            legs.append(
                VendorLeg(
                    vendor="HardcodedAssumption",
                    leg_key=f"{source_field}:{vault_key}",
                    is_hardcoded_assumption=True,
                    source_field=vault_key,
                )
            )

    return legs



def flatten_vendor_legs(oracle_output: dict) -> list[VendorLeg]:
    if not oracle_output:
        return []

    oracle_type = oracle_output.get("type")
    data = oracle_output.get("data") or {}

    if oracle_type == "standard":
        return _feed_from_output_section(data, "standard")

    if oracle_type == "meta":
        sources = data.get("oracleSources") or {}
        legs: list[VendorLeg] = []
        legs.extend(_feed_from_output_section(sources.get("primary"), "meta.primary"))
        legs.extend(_feed_from_output_section(sources.get("backup"), "meta.backup"))
        return legs

    if oracle_type == "custom":
        feeds = data.get("feeds") or {}
        return _feed_from_output_section(feeds, "custom")

    return []



def build_market_vendor_allocation(market: MarketRef, oracle_output: dict | None) -> MarketVendorAllocation:
    legs = flatten_vendor_legs(oracle_output or {})
    vendors = sorted({leg.vendor for leg in legs if leg.vendor not in {"Unknown", "HardcodedAssumption"}})
    hardcoded_leg_count = sum(1 for leg in legs if leg.is_hardcoded_assumption)
    unknown_leg_count = sum(1 for leg in legs if leg.vendor == "Unknown")
    return MarketVendorAllocation(
        unique_key=market.unique_key,
        chain_id=market.chain_id,
        vendors=vendors,
        recognized_vendor_count=len(vendors),
        hardcoded_leg_count=hardcoded_leg_count,
        unknown_leg_count=unknown_leg_count,
    )



def allocate_evenly(total_usd: float, vendors: Iterable[str]) -> dict[str, float]:
    vendor_list = sorted(set(vendors))
    if not vendor_list:
        return {}
    weight = total_usd / len(vendor_list)
    return {vendor: weight for vendor in vendor_list}



def infer_current_loan_asset_prices(markets: list[MarketRef]) -> dict[tuple[int, str], float]:
    prices: dict[tuple[int, str], list[float]] = defaultdict(list)
    for market in markets:
        supply_assets = market.supply_assets
        supply_usd = market.supply_assets_usd
        if not supply_assets or supply_usd is None:
            continue
        raw = int(supply_assets)
        if raw <= 0 or market.loan_asset_decimals < 0:
            continue
        units = raw / (10 ** market.loan_asset_decimals)
        if units <= 0:
            continue
        prices[(market.chain_id, market.loan_asset_address)].append(supply_usd / units)

    return {
        key: sum(samples) / len(samples)
        for key, samples in prices.items()
        if samples
    }


# ---------------------------------------------------------------------------
# Time-series assembly
# ---------------------------------------------------------------------------

def build_current_exposure_table(markets: list[MarketRef], oracle_metadata: dict) -> list[dict]:
    rows: list[dict] = []
    for market in markets:
        oracle_output = oracle_metadata.get((market.chain_id, market.oracle_address))
        allocation = build_market_vendor_allocation(market, oracle_output)
        supply_split = allocate_evenly(float(market.supply_assets_usd or 0), allocation.vendors)
        borrow_split = allocate_evenly(float(market.borrow_assets_usd or 0), allocation.vendors)
        rows.append(
            {
                "chain_id": market.chain_id,
                "unique_key": market.unique_key,
                "oracle_address": market.oracle_address,
                "vendors": "|".join(allocation.vendors),
                "recognized_vendor_count": allocation.recognized_vendor_count,
                "hardcoded_leg_count": allocation.hardcoded_leg_count,
                "unknown_leg_count": allocation.unknown_leg_count,
                "supply_assets_usd": float(market.supply_assets_usd or 0),
                "borrow_assets_usd": float(market.borrow_assets_usd or 0),
                "supply_split_json": json.dumps(supply_split, sort_keys=True),
                "borrow_split_json": json.dumps(borrow_split, sort_keys=True),
            }
        )
    return rows



def build_historical_exposure_series(
    markets: list[MarketRef],
    oracle_metadata: dict,
    current_prices: dict[tuple[int, str], float],
    days: int = 180,
) -> list[VendorExposurePoint]:
    exposure_map: dict[tuple[date, str, str], float] = defaultdict(float)

    for market in markets:
        oracle_output = oracle_metadata.get((market.chain_id, market.oracle_address))
        allocation = build_market_vendor_allocation(market, oracle_output)
        if not allocation.vendors:
            continue

        current_price = current_prices.get((market.chain_id, market.loan_asset_address))
        history = fetch_market_history(market.unique_key, market.chain_id, days=days)
        for point in history:
            point_date = datetime.fromtimestamp(int(point["timestamp"]), tz=timezone.utc).date()
            supply_usd = float(point.get("supplyAssetsUsd") or 0)
            borrow_usd = float(point.get("borrowAssetsUsd") or 0)

            supply_split = allocate_evenly(supply_usd, allocation.vendors)
            borrow_split = allocate_evenly(borrow_usd, allocation.vendors)
            for vendor, value in supply_split.items():
                exposure_map[(point_date, vendor, "supply_usd")] += value
            for vendor, value in borrow_split.items():
                exposure_map[(point_date, vendor, "borrow_usd")] += value

            if current_price is not None:
                raw_supply = point.get("supplyAssets")
                raw_borrow = point.get("borrowAssets")
                repriced_supply = 0.0
                repriced_borrow = 0.0
                if raw_supply is not None:
                    repriced_supply = (int(raw_supply) / (10 ** market.loan_asset_decimals)) * current_price
                if raw_borrow is not None:
                    repriced_borrow = (int(raw_borrow) / (10 ** market.loan_asset_decimals)) * current_price
                for vendor, value in allocate_evenly(repriced_supply, allocation.vendors).items():
                    exposure_map[(point_date, vendor, "repriced_supply_usd")] += value
                for vendor, value in allocate_evenly(repriced_borrow, allocation.vendors).items():
                    exposure_map[(point_date, vendor, "repriced_borrow_usd")] += value

    return [
        VendorExposurePoint(as_of=as_of, vendor=vendor, metric=metric, exposure_usd=value)
        for (as_of, vendor, metric), value in sorted(exposure_map.items())
    ]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def export_csv(path: str | Path, rows: list[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)



def export_csvs(output_dir: str | Path, current_rows: list[dict], historical_points: list[VendorExposurePoint]) -> None:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    export_csv(output_path / "vendor_dominance_current.csv", current_rows)
    export_csv(
        output_path / "vendor_dominance_6m.csv",
        [
            {
                "as_of": point.as_of.isoformat(),
                "vendor": point.vendor,
                "metric": point.metric,
                "exposure_usd": round(point.exposure_usd, 2),
            }
            for point in historical_points
        ],
    )



def build_hardcoded_summary(current_rows: list[dict]) -> list[dict]:
    summary: dict[str, float] = defaultdict(float)
    for row in current_rows:
        if row["hardcoded_leg_count"] > 0:
            summary["markets_with_hardcoded_legs"] += 1
            summary["supply_assets_usd"] += float(row["supply_assets_usd"])
            summary["borrow_assets_usd"] += float(row["borrow_assets_usd"])
    return [{"metric": key, "value": value} for key, value in summary.items()]



def run_v1(output_dir: str | Path, days: int = 180) -> dict[str, object]:
    markets = fetch_live_markets()
    metadata = fetch_oracle_metadata()
    current_prices = infer_current_loan_asset_prices(markets)
    current_rows = build_current_exposure_table(markets, metadata)
    historical_points = build_historical_exposure_series(markets, metadata, current_prices, days=days)
    export_csvs(output_dir, current_rows, historical_points)
    export_csv(Path(output_dir) / "hardcoded_exposure_summary.csv", build_hardcoded_summary(current_rows))
    return {
        "market_count": len(markets),
        "metadata_count": len(metadata),
        "price_count": len(current_prices),
        "current_output": str(Path(output_dir) / "vendor_dominance_current.csv"),
        "historical_output": str(Path(output_dir) / "vendor_dominance_6m.csv"),
    }
