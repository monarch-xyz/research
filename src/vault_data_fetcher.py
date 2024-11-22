from web3 import Web3
import pandas as pd
from src.config import BASE_RPC_URL, VAULTS

# ERC4626 ABI for the functions we need
ERC4626_ABI = [
    {
        "inputs": [],
        "name": "totalAssets",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class VaultDataFetcher:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
        self.vault_contracts = {
            name: self.w3.eth.contract(
                address=Web3.to_checksum_address(info['address']), 
                abi=ERC4626_ABI
            )
            for name, info in VAULTS.items()
        }

    def fetch_vault_rates(self, vault_name, block_numbers):
        """
        Fetch historical vault rates for given blocks
        
        Args:
            vault_name (str): Name of the vault (e.g., 'Moonwell', 'Gauntlet', 'Re7')
            block_numbers (list): List of block numbers to fetch data for
        
        Returns:
            pd.DataFrame: Historical vault rates data
        """
        contract = self.vault_contracts[vault_name]
        rates_data = []

        for block in block_numbers:
            try:
                total_assets = contract.functions.totalAssets().call(block_identifier=block)
                total_supply = contract.functions.totalSupply().call(block_identifier=block)
                
                # Calculate share price (yield indicator)
                share_price = total_assets / total_supply if total_supply > 0 else 1
                
                rates_data.append({
                    'block_number': block,
                    'total_assets': total_assets,
                    'total_supply': total_supply,
                    'share_price': share_price
                })
            except Exception as e:
                print(f"Error fetching data for {vault_name} at block {block}: {str(e)}")
                continue

        return pd.DataFrame(rates_data)

    def fetch_all_vault_rates(self, block_numbers):
        """
        Fetch historical rates for all configured vaults
        
        Args:
            block_numbers (list): List of block numbers to fetch data for
        
        Returns:
            dict: Dictionary of DataFrames with vault rates data
        """
        return {
            vault_name: self.fetch_vault_rates(vault_name, block_numbers)
            for vault_name in VAULTS.keys()
        }

    def calculate_apy(self, initial_share_price, final_share_price, time_period_days):
        """
        Calculate annualized APY from share price change
        
        Args:
            initial_share_price (float): Initial share price
            final_share_price (float): Final share price
            time_period_days (int): Number of days between measurements
        
        Returns:
            float: Annualized APY
        """
        if initial_share_price <= 0 or time_period_days <= 0:
            return 0
        
        return ((final_share_price / initial_share_price) ** (365 / time_period_days)) - 1
