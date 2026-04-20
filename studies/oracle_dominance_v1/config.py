from __future__ import annotations

from pathlib import Path


MORPHO_API_URL = "https://blue-api.morpho.org/graphql"
DEFAULT_ORACLE_GIST_BASE_URL = "https://gist.githubusercontent.com/starksama/087ce4682243a059d77b1361fcccf221/raw"
MONARCH_MARKETS_PAGE_SIZE = 1_000
MORPHO_MARKETS_PAGE_SIZE = 500
SUPPORTED_CHAINS = [1, 10, 8453, 42161, 137, 130, 999, 143, 42793]

BLACKLISTED_TOKEN_ADDRESSES = {
    "0xda1c2c3c8fad503662e41e324fc644dc2c5e0ccd",
    "0x8413d2a624a9fa8b6d3ec7b22cf7f62e55d6bc83",
    "0x4bcaf180df5b13c0441fe41a66e9638a2a410c6d",
}

BLACKLISTED_MARKET_IDS = {
    "0xfdb8221edcae73f73485d55c30e706906114bc2ff4634870c5c57e8fb83eae6a",
}

STABLE_REFERENCE_SYMBOLS = {
    "USD",
    "USDC",
    "USDT",
    "USDS",
    "USDE",
    "USDB",
    "USD0",
    "USDF",
    "USDTB",
    "USDL",
    "USDG",
    "RLUSD",
    "PYUSD",
    "FDUSD",
    "CRVUSD",
    "BOLD",
    "SUSDE",
    "SUSDF",
    "SFRXUSD",
    "RUSD",
}

REPO_ROOT = Path(__file__).resolve().parents[2]
