from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Iterable

from studies.oracle_dominance_v1.config import STABLE_REFERENCE_SYMBOLS
from studies.oracle_dominance_v1.models import MarketRef, MarketVendorAllocation, VendorExposurePoint, VendorLeg


def _normalize_symbol(value: str | None) -> str:
    return (value or "").strip().upper()


def _is_stable_reference_symbol(value: str | None) -> bool:
    symbol = _normalize_symbol(value)
    return symbol in STABLE_REFERENCE_SYMBOLS or symbol.endswith("USD")


def _extract_feed_assumption(feed: dict | None) -> str | None:
    if not feed:
        return None
    pair = feed.get("pair") or []
    if len(pair) != 2:
        return None
    left = _normalize_symbol(pair[0])
    right = _normalize_symbol(pair[1])
    if not left or not right:
        return None
    if right == "USD" and _is_stable_reference_symbol(left) and left != "USD":
        return f"{left}/USD peg"
    if left == "USD" and _is_stable_reference_symbol(right) and right != "USD":
        return f"{right}/USD peg"
    return None


def _extract_vault_assumption(vault: dict | None) -> str | None:
    if not vault:
        return None
    pair = vault.get("pair") or []
    if len(pair) == 2:
        left = _normalize_symbol(pair[0])
        right = _normalize_symbol(pair[1])
        if left and right:
            return f"{left}/{right} conversion"
    symbol = _normalize_symbol(vault.get("symbol"))
    asset_symbol = _normalize_symbol(vault.get("assetSymbol"))
    if symbol and asset_symbol:
        return f"{symbol}/{asset_symbol} conversion"
    return None


def _feed_from_output_section(section: dict | None, source_field: str) -> list[VendorLeg]:
    if not section:
        return []

    legs: list[VendorLeg] = []
    for feed_key in ("baseFeedOne", "baseFeedTwo", "quoteFeedOne", "quoteFeedTwo"):
        feed = section.get(feed_key)
        if not feed:
            continue
        provider = feed.get("provider")
        assumption_label = _extract_feed_assumption(feed)
        if provider:
            legs.append(
                VendorLeg(
                    vendor=str(provider),
                    leg_key=f"{source_field}:{feed_key}",
                    source_field=feed_key,
                    assumption_label=assumption_label,
                    assumption_kind="peg" if assumption_label else None,
                )
            )
        else:
            legs.append(
                VendorLeg(
                    vendor="Unknown",
                    leg_key=f"{source_field}:{feed_key}",
                    source_field=feed_key,
                    assumption_label=assumption_label,
                    assumption_kind="peg" if assumption_label else None,
                )
            )

    for vault_key in ("baseVault", "quoteVault"):
        vault = section.get(vault_key)
        if vault:
            legs.append(
                VendorLeg(
                    vendor="HardcodedAssumption",
                    leg_key=f"{source_field}:{vault_key}",
                    is_hardcoded_assumption=True,
                    source_field=vault_key,
                    assumption_label=_extract_vault_assumption(vault),
                    assumption_kind="vault",
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
    assumption_labels = sorted({leg.assumption_label for leg in legs if leg.assumption_label})
    peg_assumption_count = sum(1 for leg in legs if leg.assumption_kind == "peg" and leg.assumption_label)
    vault_assumption_count = sum(1 for leg in legs if leg.assumption_kind == "vault" and leg.assumption_label)
    return MarketVendorAllocation(
        unique_key=market.unique_key,
        chain_id=market.chain_id,
        vendors=vendors,
        recognized_vendor_count=len(vendors),
        hardcoded_leg_count=hardcoded_leg_count,
        unknown_leg_count=unknown_leg_count,
        assumption_labels=assumption_labels,
        peg_assumption_count=peg_assumption_count,
        vault_assumption_count=vault_assumption_count,
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

    return {key: sum(samples) / len(samples) for key, samples in prices.items() if samples}


def build_current_exposure_table(markets: list[MarketRef], oracle_metadata: dict) -> list[dict]:
    rows: list[dict] = []
    for market in markets:
        oracle_output = oracle_metadata.get((market.chain_id, market.oracle_address))
        allocation = build_market_vendor_allocation(market, oracle_output)
        supply_split = allocate_evenly(float(market.supply_assets_usd or 0), allocation.vendors)
        borrow_split = allocate_evenly(float(market.borrow_assets_usd or 0), allocation.vendors)
        assumption_supply_split = allocate_evenly(float(market.supply_assets_usd or 0), allocation.assumption_labels)
        assumption_borrow_split = allocate_evenly(float(market.borrow_assets_usd or 0), allocation.assumption_labels)
        rows.append(
            {
                "chain_id": market.chain_id,
                "unique_key": market.unique_key,
                "oracle_address": market.oracle_address,
                "loan_asset_symbol": market.loan_asset_symbol,
                "collateral_asset_symbol": market.collateral_asset_symbol,
                "vendors": "|".join(allocation.vendors),
                "recognized_vendor_count": allocation.recognized_vendor_count,
                "hardcoded_leg_count": allocation.hardcoded_leg_count,
                "unknown_leg_count": allocation.unknown_leg_count,
                "assumption_labels": "|".join(allocation.assumption_labels),
                "assumption_count": len(allocation.assumption_labels),
                "peg_assumption_count": allocation.peg_assumption_count,
                "vault_assumption_count": allocation.vault_assumption_count,
                "supply_assets_usd": float(market.supply_assets_usd or 0),
                "borrow_assets_usd": float(market.borrow_assets_usd or 0),
                "supply_split_json": json.dumps(supply_split, sort_keys=True),
                "borrow_split_json": json.dumps(borrow_split, sort_keys=True),
                "assumption_supply_split_json": json.dumps(assumption_supply_split, sort_keys=True),
                "assumption_borrow_split_json": json.dumps(assumption_borrow_split, sort_keys=True),
            }
        )
    return rows


def build_historical_exposure_series(
    markets: list[MarketRef],
    oracle_metadata: dict,
    current_prices: dict[tuple[int, str], float],
    fetch_market_history,
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

            for vendor, value in allocate_evenly(supply_usd, allocation.vendors).items():
                exposure_map[(point_date, vendor, "supply_usd")] += value
            for vendor, value in allocate_evenly(borrow_usd, allocation.vendors).items():
                exposure_map[(point_date, vendor, "borrow_usd")] += value

            if current_price is not None:
                repriced_supply = 0.0
                repriced_borrow = 0.0
                raw_supply = point.get("supplyAssets")
                raw_borrow = point.get("borrowAssets")
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


def build_hardcoded_summary(current_rows: list[dict]) -> list[dict]:
    summary: dict[str, float] = defaultdict(float)
    for row in current_rows:
        if row["hardcoded_leg_count"] > 0:
            summary["markets_with_hardcoded_legs"] += 1
            summary["supply_assets_usd"] += float(row["supply_assets_usd"])
            summary["borrow_assets_usd"] += float(row["borrow_assets_usd"])
    return [{"metric": key, "value": value} for key, value in summary.items()]
