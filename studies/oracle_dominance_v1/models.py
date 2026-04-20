from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


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
    assumption_label: str | None = None
    assumption_kind: str | None = None


@dataclass(slots=True)
class MarketVendorAllocation:
    unique_key: str
    chain_id: int
    vendors: list[str] = field(default_factory=list)
    recognized_vendor_count: int = 0
    hardcoded_leg_count: int = 0
    unknown_leg_count: int = 0
    assumption_labels: list[str] = field(default_factory=list)
    peg_assumption_count: int = 0
    vault_assumption_count: int = 0


@dataclass(slots=True)
class VendorExposurePoint:
    as_of: date
    vendor: str
    exposure_usd: float
    metric: str
