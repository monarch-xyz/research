# Morpho Lending Strategy Backtester

## Project Overview
This project provides tools to analyze and compare ERC4626 vaults on the Base network, focusing on:
- Fetching current and historical share prices
- Calculating APY
- Visualizing price trends
- Comparing multiple vaults

## Project Structure
```
backtest/
├── src/
│   ├── config.py          # Vault configurations and addresses
│   ├── fetcher.py         # Main Fetcher class for vault analysis
│   ├── get_info.py        # Quick info script for vault prices
│   └── backtest_strategy.py # Strategy backtesting code
├── notebooks/
│   └── plot_vault_prices.ipynb  # Example notebook for plotting vault prices
└── examples/
    └── ...                # Additional example code
```

## Setup

### Prerequisites
- Python 3.9+
- Web3.py
- Jupyter (for notebooks)

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip3 install -r requirements.txt
```

### Configuration
Create a `.env` file with your RPC URL:
```
RPC_URL=your_base_rpc_url
```

## Usage

### Quick Price Check
Get current prices and 24h APY for all vaults:
```bash
python3 src/get_info.py
```

### Interactive Analysis
1. Start Jupyter:
```bash
jupyter notebook
```

2. Open `notebooks/plot_vault_prices.ipynb`
3. Follow the notebook to:
   - Plot vault prices over time
   - Compare multiple vaults
   - Calculate APY

### Using the Fetcher Class
```python
from src.fetcher import Fetcher
from src.config import VAULTS
from datetime import datetime, timedelta

# Create a fetcher for a vault
fetcher = Fetcher(VAULTS['moonwell'])

# Get prices for last 7 days
end_date = datetime.now()
start_date = end_date - timedelta(days=7)
fetcher.plot(start_date, end_date, interval_hours=12)
```

## Supported Vaults
- Moonwell USDC Vault
- Gauntlet USDC Vault
- Re7 USDC Vault