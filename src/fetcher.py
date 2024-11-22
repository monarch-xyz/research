from web3 import Web3
import os
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

class Fetcher:
    # ERC4626 ABI for share price calculation
    ERC4626_ABI = [
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "uint256", "name": "shares", "type": "uint256"}],
            "name": "convertToAssets",
            "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]

    def __init__(self, vault_config):
        """Initialize fetcher with vault configuration"""
        self.vault_config = vault_config
        self.w3 = Web3(Web3.HTTPProvider(os.getenv('RPC_URL')))
        if not self.w3.is_connected():
            raise Exception("Failed to connect to RPC endpoint")
        
        # Initialize contract
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(vault_config['address']),
            abi=self.ERC4626_ABI
        )
        
        # Get decimals
        self.decimals = self.contract.functions.decimals().call()
        self.one_share = 10 ** self.decimals

    def _get_block_for_timestamp(self, timestamp):
        """Get the closest block number for a given timestamp"""
        current_block = self.w3.eth.block_number
        current_timestamp = self.w3.eth.get_block(current_block)['timestamp']
        
        # Estimate block number based on timestamp difference and 2s block time
        time_diff = current_timestamp - timestamp
        block_diff = time_diff // 2  # Assuming 2s block time
        
        return current_block - block_diff

    def get_price_at_block(self, block_number):
        """Get share price at a specific block number"""
        assets = self.contract.functions.convertToAssets(self.one_share).call(
            block_identifier=block_number
        )
        return assets / 1e6  # Convert to USDC

    def fetch_prices(self, start_date, end_date, interval_hours=24):
        """
        Fetch prices between start_date and end_date at specified intervals
        Returns DataFrame with timestamps and prices
        """
        # Convert dates to timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        # Calculate number of intervals
        interval_seconds = interval_hours * 3600
        timestamps = range(start_timestamp, end_timestamp + interval_seconds, interval_seconds)
        
        data = []
        for ts in timestamps:
            block = self._get_block_for_timestamp(ts)
            price = self.get_price_at_block(block)
            data.append({
                'timestamp': datetime.fromtimestamp(ts),
                'price': price
            })
        
        return pd.DataFrame(data)

    def plot(self, start_date, end_date, interval_hours=24, ax=None):
        """
        Plot prices between start_date and end_date
        If ax is provided, plot on that axis (allows multiple plots on same figure)
        Returns the axis object
        """
        df = self.fetch_prices(start_date, end_date, interval_hours)
        
        if ax is None:
            _, ax = plt.subplots(figsize=(12, 6))
        
        ax.plot(df['timestamp'], df['price'], label=self.vault_config.get('name', 'Vault'))
        ax.set_xlabel('Date')
        ax.set_ylabel('Share Price (USDC)')
        ax.grid(True)
        ax.legend()
        
        return ax
