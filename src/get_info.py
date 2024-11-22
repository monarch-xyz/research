from web3 import Web3
import os
from dotenv import load_dotenv
from config import VAULTS
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

def get_quick_info():
    """Get current and 24h historical share prices for all vaults"""
    
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(os.getenv('RPC_URL')))
    if not w3.is_connected():
        raise Exception("Failed to connect to RPC endpoint")
    
    # Get current and historical block numbers
    current_block = w3.eth.block_number
    blocks_per_day = 86400 // 2  # Assuming 2s block time on Base
    historical_block = current_block - blocks_per_day
    
    print(f"Connected to network.")
    print(f"Current block: {current_block}")
    print(f"24h ago block: {historical_block}\n")
    
    # ERC4626 ABI - minimal version for share price
    abi = [
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
    
    for vault_name, vault_data in VAULTS.items():
        print(f"\nFetching {vault_name}...")
        
        try:
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(vault_data['address']),
                abi=abi
            )
            
            # Get decimals
            decimals = contract.functions.decimals().call()
            one_share = 10 ** decimals
            
            # Get current price
            current_assets = contract.functions.convertToAssets(one_share).call()
            current_price = current_assets / 1e6  # Convert to USDC
            
            # Get historical price
            historical_assets = contract.functions.convertToAssets(one_share).call(
                block_identifier=historical_block
            )
            historical_price = historical_assets / 1e6  # Convert to USDC
            
            # Calculate APY
            time_diff = (
                w3.eth.get_block(current_block)['timestamp'] - 
                w3.eth.get_block(historical_block)['timestamp']
            )
            time_diff_years = time_diff / (365 * 24 * 3600)
            apy = ((current_price / historical_price) ** (1 / time_diff_years)) - 1
            
            print(f"✓ {vault_name}:")
            print(f"  24h ago: {historical_price:.6f} USDC/share")
            print(f"  Current: {current_price:.6f} USDC/share")
            print(f"  24h APY: {apy * 100:.2f}%")
            
        except Exception as e:
            print(f"✗ Error: {str(e)}")

if __name__ == "__main__":
    try:
        get_quick_info()
    except Exception as e:
        print(f"Error: {str(e)}")
