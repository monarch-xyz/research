"""Reusable oracle dominance v1 pipeline orchestration."""

from __future__ import annotations

import csv
from pathlib import Path

from studies.oracle_dominance_v1.analysis import (
    allocate_evenly,
    build_current_exposure_table,
    build_hardcoded_summary,
    build_historical_exposure_series,
    build_market_vendor_allocation,
    flatten_vendor_legs,
    infer_current_loan_asset_prices,
)
from studies.oracle_dominance_v1.clients.monarch import fetch_monarch_market_universe
from studies.oracle_dominance_v1.clients.morpho import fetch_market_history, fetch_morpho_markets_for_chain
from studies.oracle_dominance_v1.clients.oracle_gist import fetch_oracle_metadata as fetch_oracle_metadata_for_chains
from studies.oracle_dominance_v1.config import (
    BLACKLISTED_MARKET_IDS,
    BLACKLISTED_TOKEN_ADDRESSES,
    SUPPORTED_CHAINS,
)
from studies.oracle_dominance_v1.models import MarketRef, MarketVendorAllocation, VendorExposurePoint, VendorLeg
from studies.oracle_dominance_v1.utils.env import load_local_env


load_local_env()


def _is_known_symbol(symbol: str) -> bool:
    value = (symbol or "").strip().upper()
    return value not in {"", "UNKNOWN", "N/A", "NULL"}


# Fetch markets with methodology filters (borrow cutoff, listed-only, recognized tokens only).
def fetch_live_markets(
    min_borrow_usd: float = 0.0,
    require_listed: bool = False,
    recognized_tokens_only: bool = False,
) -> list[MarketRef]:
    merged: list[MarketRef] = []
    for chain_id in SUPPORTED_CHAINS:
        merged.extend(fetch_morpho_markets_for_chain(chain_id))

    monarch_universe: dict[tuple[int, str], str] = {}
    try:
        monarch_universe = fetch_monarch_market_universe()
    except Exception:
        monarch_universe = {}

    listed_keys: set[tuple[int, str]] | None = set(monarch_universe.keys()) if require_listed else None

    filtered: list[MarketRef] = []
    for market in merged:
        monarch_oracle = monarch_universe.get((market.chain_id, market.unique_key))
        if monarch_oracle and not market.oracle_address:
            market.oracle_address = monarch_oracle
        if market.unique_key in BLACKLISTED_MARKET_IDS:
            continue
        if market.loan_asset_address in BLACKLISTED_TOKEN_ADDRESSES:
            continue
        if market.collateral_asset_address in BLACKLISTED_TOKEN_ADDRESSES:
            continue
        if float(market.borrow_assets_usd or 0) < float(min_borrow_usd):
            continue
        if listed_keys is not None and (market.chain_id, market.unique_key) not in listed_keys:
            continue
        if recognized_tokens_only and (
            not _is_known_symbol(market.loan_asset_symbol)
            or not _is_known_symbol(market.collateral_asset_symbol)
        ):
            continue
        filtered.append(market)

    return filtered


def fetch_oracle_metadata(markets: list[MarketRef] | None = None) -> dict[tuple[int, str], dict]:
    market_list = markets if markets is not None else fetch_live_markets()
    return fetch_oracle_metadata_for_chains([m.chain_id for m in market_list])


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


def export_csvs(output_dir: str | Path, current_rows: list[dict], historical_points: list[VendorExposurePoint], days: int) -> tuple[Path, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    current_csv = output_path / "vendor_dominance_current.csv"
    historical_csv = output_path / f"vendor_dominance_{days}d.csv"
    export_csv(current_csv, current_rows)
    export_csv(
        historical_csv,
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
    return current_csv, historical_csv


# Build vendor and assumption attribution outputs plus historical time series.
def run_v1(
    output_dir: str | Path,
    days: int = 180,
    min_borrow_usd: float = 500_000,
    require_listed: bool = False,
    recognized_tokens_only: bool = False,
) -> dict[str, object]:
    markets = fetch_live_markets(
        min_borrow_usd=min_borrow_usd,
        require_listed=require_listed,
        recognized_tokens_only=recognized_tokens_only,
    )
    metadata = fetch_oracle_metadata(markets)
    current_prices = infer_current_loan_asset_prices(markets)
    current_rows = build_current_exposure_table(markets, metadata)
    historical_points = build_historical_exposure_series(
        markets,
        metadata,
        current_prices,
        fetch_market_history=fetch_market_history,
        days=days,
    )

    current_csv, historical_csv = export_csvs(output_dir, current_rows, historical_points, days=days)
    export_csv(Path(output_dir) / "hardcoded_exposure_summary.csv", build_hardcoded_summary(current_rows))
    return {
        "market_count": len(markets),
        "metadata_count": len(metadata),
        "price_count": len(current_prices),
        "current_output": str(current_csv),
        "historical_output": str(historical_csv),
        "filters": {
            "min_borrow_usd": min_borrow_usd,
            "require_listed": require_listed,
            "recognized_tokens_only": recognized_tokens_only,
        },
    }


__all__ = [
    "MarketRef",
    "MarketVendorAllocation",
    "VendorLeg",
    "VendorExposurePoint",
    "allocate_evenly",
    "build_current_exposure_table",
    "build_hardcoded_summary",
    "build_historical_exposure_series",
    "build_market_vendor_allocation",
    "export_csv",
    "export_csvs",
    "fetch_live_markets",
    "fetch_market_history",
    "fetch_monarch_market_universe",
    "fetch_oracle_metadata",
    "flatten_vendor_legs",
    "infer_current_loan_asset_prices",
    "run_v1",
]
