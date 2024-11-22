from web3 import Web3
import os
from dotenv import load_dotenv
from config import VAULTS
from datetime import datetime, timedelta
from fetcher import Fetcher

# Load environment variables
load_dotenv()

def print_vault_info(vault_name, data):
    """Print information for a single vault"""
    print(f"✓ {vault_name}:")
    print(f"  Start Block {data['start']['block']} ({data['start']['timestamp']}):")
    print(f"    Price: {data['start']['price']:.6f} USDC/share")
    print(f"  End Block {data['end']['block']} ({data['end']['timestamp']}):")
    print(f"    Price: {data['end']['price']:.6f} USDC/share")
    print(f"  APY: {data['apy']:.2f}%\n")

def get_vault_info():
    """Get current and historical share prices for all vaults"""
    
    # Calculate time period
    end_time = datetime.now()
    start_time = end_time - timedelta(days=14)  # 2 weeks ago
    
    print(f"Analyzing vault performance:")
    print(f"Period: {start_time.strftime('%Y-%m-%d %H:%M:%S')} to {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Analyze each vault
    for vault_name, vault_data in VAULTS.items():
        try:
            # Create fetcher and get data
            fetcher = Fetcher(vault_data)
            data = fetcher.get_price_data(start_time, end_time)
            
            # Print results
            print_vault_info(vault_name, data)
            
        except Exception as e:
            print(f"✗ Error analyzing {vault_name}: {str(e)}\n")

if __name__ == "__main__":
    try:
        get_vault_info()
    except Exception as e:
        print(f"Error: {str(e)}")
