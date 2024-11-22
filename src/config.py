import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base Network Configuration
BASE_RPC_URL = os.getenv('BASE_RPC_URL', 'https://mainnet.base.org')
BASE_CHAIN_ID = 8453

# Morpho Blue Addresses
MORPHO_BLUE_ADDRESS = '0x...'  # Replace with actual Morpho Blue contract address

# Supported Assets (focusing on USDC only)
SUPPORTED_ASSETS = {
    'USDC': {
        'address': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913',  # USDC contract address on Base
        'decimals': 6
    }
}

# ERC4626 Vaults
VAULTS = {
    'Moonwell': {
        'address': '0xc1256Ae5FF1cf2719D4937adb3bbCCab2E00A2Ca',
        'name': 'Moonwell USDC Vault'
    },
    'Gauntlet': {
        'address': '0xc0c5689e6f4D256E861F65465b691aeEcC0dEb12',
        'name': 'Gauntlet USDC Vault'
    },
    'Re7': {
        'address': '0x12AFDeFb2237a5963e7BAb3e2D46ad0eee70406e',
        'name': 'Re7 USDC Vault'
    }
}

# Backtest Configuration
BACKTEST_CONFIG = {
    'start_date': '2023-11-01',  # 2 months ago
    'end_date': '2024-01-01',    # current
    'initial_capital': 10000,  # USD
    'risk_free_rate': 0.02  # 2% risk-free rate
}
