from web3 import Web3
from web3.exceptions import BlockNotFound
import os
from dotenv import load_dotenv
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import time
import json

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
        
        # Cache for block numbers
        self._block_cache = {}
        
    def _get_block_with_retry(self, block_number, max_retries=3):
        """Get block with retry logic"""
        for attempt in range(max_retries):
            try:
                return self.w3.eth.get_block(block_number)
            except BlockNotFound:
                if attempt == max_retries - 1:
                    return None
                time.sleep(0.5)  # Wait before retry
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5)

    def _get_block_for_timestamp(self, target_timestamp):
        """Get an approximate block number for a given timestamp using 2s block time"""
        current_block = self.w3.eth.block_number
        current_timestamp = self.w3.eth.get_block(current_block)['timestamp']
        
        # Calculate blocks difference based on 2s block time
        time_diff = current_timestamp - target_timestamp
        block_diff = time_diff // 2  # 2s block time
        
        estimated_block = max(1, current_block - block_diff)
        return estimated_block

    def get_price_at_block(self, block_number, max_retries=3):
        """Get share price at a specific block number with retry logic"""
        for attempt in range(max_retries):
            try:
                assets = self.contract.functions.convertToAssets(self.one_share).call(
                    block_identifier=block_number
                )
                return assets / 1e6  # Convert to USDC
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                time.sleep(0.5)

    def fetch_prices(self, start_date, end_date, interval_hours=24):
        """
        Fetch prices between start_date and end_date at specified intervals
        Returns DataFrame with timestamps and prices
        """
        # Ensure we're querying at 00:00 for each day
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Convert dates to timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        # Calculate daily timestamps (one point per day at 00:00)
        daily_timestamps = range(start_timestamp, end_timestamp + 86400, 86400)
        
        data = []
        for ts in daily_timestamps:
            try:
                block = self._get_block_for_timestamp(ts)
                if block is None:
                    print(f"Warning: Could not find block for timestamp {datetime.fromtimestamp(ts)}")
                    continue
                    
                price = self.get_price_at_block(block)
                actual_timestamp = self.w3.eth.get_block(block)['timestamp']
                
                data.append({
                    'timestamp': pd.Timestamp.fromtimestamp(actual_timestamp),
                    'price': price,
                    'block': block
                })
            except Exception as e:
                print(f"Warning: Error fetching data for {datetime.fromtimestamp(ts)}: {str(e)}")
                continue
        
        return pd.DataFrame(data)

    def fetch_and_save_prices(self, start_date, end_date, filename, interval_hours=24):
        """
        Fetch prices and save them to a file for later use
        Returns the fetched DataFrame
        """
        df = self.fetch_prices(start_date, end_date, interval_hours)
        
        # Convert timestamps to string for JSON serialization
        data_to_save = {
            'data': [{
                'timestamp': row['timestamp'].isoformat(),
                'price': row['price'],
                'block': row['block']
            } for _, row in df.iterrows()],
            'metadata': {
                'vault_address': self.vault_config['address'],
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'interval_hours': interval_hours
            }
        }
        
        with open(filename, 'w') as f:
            json.dump(data_to_save, f)
            
        return df
    
    def load_prices(self, filename):
        """
        Load previously saved price data from a file
        Returns DataFrame with the loaded data
        """
        with open(filename, 'r') as f:
            saved_data = json.load(f)
            
        # Convert the loaded data back to DataFrame
        df = pd.DataFrame(saved_data['data'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def plot_from_df(self, df, ax=None, label=None):
        """
        Plot prices from a pre-loaded DataFrame
        If ax is provided, plot on that axis (allows multiple plots on same figure)
        Returns the axis object
        """
        if ax is None:
            _, ax = plt.subplots(figsize=(12, 6))
        
        plot_label = label or self.vault_config.get('name', 'Vault')
        ax.plot(df['timestamp'], df['price'], label=plot_label)
        ax.set_xlabel('Date')
        ax.set_ylabel('Share Price (USDC)')
        ax.grid(True)
        ax.legend()
        
        return ax

    def plot(self, start_date, end_date, interval_hours=24, ax=None):
        """
        Plot prices between start_date and end_date
        If ax is provided, plot on that axis (allows multiple plots on same figure)
        Returns the axis object
        """
        df = self.fetch_prices(start_date, end_date, interval_hours)
        return self.plot_from_df(df, ax=ax)

    def get_block_at_timestamp(self, target_timestamp):
        """Binary search to find the closest block to a timestamp"""
        left = 1
        right = self.w3.eth.block_number
        
        while left <= right:
            mid = (left + right) // 2
            try:
                block = self.w3.eth.get_block(mid)
                if block['timestamp'] == target_timestamp:
                    return mid, block
                if block['timestamp'] < target_timestamp:
                    left = mid + 1
                else:
                    right = mid - 1
            except Exception:
                right = mid - 1
        
        # Get the closest block
        block = self.w3.eth.get_block(right)
        return right, block

    def get_price_data(self, start_time, end_time=None):
        """Get price data between start_time and end_time"""
        if end_time is None:
            end_time = datetime.now()

        # Get blocks for timestamps
        start_block_num, start_block = self.get_block_at_timestamp(int(start_time.timestamp()))
        if end_time:
            end_block_num = self.w3.eth.block_number
            end_block = self.w3.eth.get_block(end_block_num)
        
        # Get prices
        start_price = self.get_price_at_block(start_block_num)
        end_price = self.get_price_at_block(end_block_num)
        
        # Calculate APY
        time_diff = end_block['timestamp'] - start_block['timestamp']
        time_diff_years = time_diff / (365 * 24 * 3600)
        apy = ((end_price / start_price) ** (1 / time_diff_years)) - 1
        
        return {
            'start': {
                'block': start_block_num,
                'timestamp': datetime.fromtimestamp(start_block['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'price': start_price
            },
            'end': {
                'block': end_block_num,
                'timestamp': datetime.fromtimestamp(end_block['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                'price': end_price
            },
            'apy': apy * 100
        }
