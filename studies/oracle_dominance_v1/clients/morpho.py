from __future__ import annotations

from datetime import datetime, timedelta, timezone

from studies.oracle_dominance_v1.config import MORPHO_API_URL, MORPHO_MARKETS_PAGE_SIZE
from studies.oracle_dominance_v1.models import MarketRef
from studies.oracle_dominance_v1.utils.http import json_post


MORPHO_MARKETS_QUERY = """
query getMarkets($first: Int, $skip: Int, $where: MarketFilters) {
  markets(first: $first, skip: $skip, where: $where) {
    items {
      uniqueKey
      oracle {
        address
      }
      morphoBlue {
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


def fetch_morpho_markets_for_chain(chain_id: int) -> list[MarketRef]:
    markets: list[MarketRef] = []
    skip = 0
    total = None

    while True:
        result = json_post(
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


def fetch_market_history(unique_key: str, chain_id: int, days: int = 180) -> list[dict]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    result = json_post(
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
