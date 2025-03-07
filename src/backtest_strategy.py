import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from src.data_fetcher import MorphoDataFetcher
from src.vault_data_fetcher import VaultDataFetcher
from src.config import BACKTEST_CONFIG, VAULTS

class LendingStrategyBacktester:
    def __init__(self, initial_capital=BACKTEST_CONFIG['initial_capital']):
        self.initial_capital = initial_capital
        self.data_fetcher = MorphoDataFetcher()
        self.vault_fetcher = VaultDataFetcher()
        
    def basic_supply_strategy(self, asset_symbol, start_date, end_date):
        """
        Implement a basic supply lending strategy using Morpho supply rates
        """
        rates_df = self.data_fetcher.fetch_historical_rates(asset_symbol, start_date, end_date)
        return self._calculate_strategy_performance(rates_df['supply_rate'])
    
    def vault_strategy(self, vault_name, block_numbers):
        """
        Calculate performance for an ERC4626 vault
        
        Args:
            vault_name (str): Name of the vault
            block_numbers (list): List of block numbers for historical data
        """
        rates_df = self.vault_fetcher.fetch_vault_rates(vault_name, block_numbers)
        
        # Calculate returns from share price changes
        share_prices = rates_df['share_price'].values
        returns = np.diff(share_prices) / share_prices[:-1]
        
        # Convert returns to portfolio values
        portfolio_value = [self.initial_capital]
        current_value = self.initial_capital
        
        for ret in returns:
            current_value *= (1 + ret)
            portfolio_value.append(current_value)
            
        return {
            'total_return': (current_value - self.initial_capital) / self.initial_capital,
            'sharpe_ratio': self._calculate_sharpe_ratio(returns),
            'max_drawdown': self._calculate_max_drawdown(portfolio_value),
            'portfolio_values': portfolio_value,
            'returns': returns
        }
    
    def _calculate_strategy_performance(self, rates):
        """Calculate strategy performance metrics from rates"""
        capital = self.initial_capital
        portfolio_value = [capital]
        
        for rate in rates:
            capital *= (1 + rate)
            portfolio_value.append(capital)
        
        returns = np.diff(portfolio_value) / portfolio_value[:-1]
        
        return {
            'total_return': (capital - self.initial_capital) / self.initial_capital,
            'sharpe_ratio': self._calculate_sharpe_ratio(returns),
            'max_drawdown': self._calculate_max_drawdown(portfolio_value),
            'portfolio_values': portfolio_value,
            'returns': returns
        }
    
    def _calculate_sharpe_ratio(self, returns, risk_free_rate=BACKTEST_CONFIG['risk_free_rate']):
        """Calculate annualized Sharpe ratio using numpy"""
        if len(returns) < 2:
            return 0
        excess_returns = returns - risk_free_rate/365  # Daily risk-free rate
        if np.std(excess_returns) == 0:
            return 0
        return np.sqrt(365) * np.mean(excess_returns) / np.std(excess_returns)
    
    def _calculate_max_drawdown(self, portfolio_values):
        """Calculate maximum drawdown percentage"""
        peak = portfolio_values[0]
        max_drawdown = 0
        
        for value in portfolio_values[1:]:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_drawdown = max(max_drawdown, drawdown)
        
        return max_drawdown
    
    def compare_all_strategies(self, asset_symbol, block_numbers, start_date, end_date):
        """
        Compare Morpho supply strategy against vault strategies
        
        Args:
            asset_symbol (str): Asset symbol for Morpho strategy
            block_numbers (list): Block numbers for vault data
            start_date (str): Start date for Morpho data
            end_date (str): End date for Morpho data
        """
        results = {
            'Morpho Supply': self.basic_supply_strategy(asset_symbol, start_date, end_date)
        }
        
        # Add vault strategies
        for vault_name in VAULTS.keys():
            results[vault_name] = self.vault_strategy(vault_name, block_numbers)
            
        return results
    
    def plot_performance_comparison(self, results):
        """Plot performance comparison of all strategies"""
        plt.figure(figsize=(12, 8))
        
        # Calculate 7-day moving averages and overall averages
        moving_averages = {}
        overall_averages = {}
        
        for strategy_name, metrics in results.items():
            values = metrics['portfolio_values']
            
            # Normalize to starting value
            normalized_values = [v / values[0] for v in values]
            
            # Calculate daily returns
            daily_returns = np.diff(normalized_values) / normalized_values[:-1]
            
            # Convert to APY (annualized percentage yield)
            daily_apy = (1 + daily_returns) ** 365 - 1
            
            # Calculate 7-day moving average of APY
            moving_avg = pd.Series(daily_apy).rolling(window=7).mean()
            moving_averages[strategy_name] = moving_avg
            
            # Calculate overall average APY
            overall_averages[strategy_name] = np.mean(daily_apy) * 100
            
            # Plot normalized values
            plt.plot(normalized_values, label=f"{strategy_name}")
        
        plt.title('Strategy Performance Comparison (Normalized)')
        plt.xlabel('Time Period')
        plt.ylabel('Normalized Value')
        plt.legend()
        plt.grid(True)
        
        # Create a second figure for APY moving averages
        plt.figure(figsize=(12, 8))
        for strategy_name, moving_avg in moving_averages.items():
            plt.plot(moving_avg, label=f"{strategy_name} 7-day Avg APY")
            
        plt.title('7-Day Moving Average APY')
        plt.xlabel('Time Period')
        plt.ylabel('APY (%)')
        plt.legend()
        plt.grid(True)
        
        # Add summary table with new metrics
        summary_data = {
            'Total Return': [f"{metrics['total_return']*100:.2f}%" for metrics in results.values()],
            'Sharpe Ratio': [f"{metrics['sharpe_ratio']:.2f}" for metrics in results.values()],
            'Max Drawdown': [f"{metrics['max_drawdown']*100:.2f}%" for metrics in results.values()],
            'Avg 2M APY': [f"{overall_averages[name]:.2f}%" for name in results.keys()]
        }
        
        summary_df = pd.DataFrame(summary_data, index=results.keys())
        plt.figure(figsize=(12, 4))
        plt.axis('off')
        plt.table(cellText=summary_df.values,
                 rowLabels=summary_df.index,
                 colLabels=summary_df.columns,
                 cellLoc='center',
                 loc='center',
                 bbox=[0.1, 0.1, 0.8, 0.8])
        
        plt.tight_layout()
        return [plt.figure(n) for n in plt.get_fignums()]
    
def main():
    backtester = LendingStrategyBacktester()
    
    results = backtester.compare_all_strategies(
        'USDC', 
        [123456, 123457, 123458], 
        BACKTEST_CONFIG['start_date'], 
        BACKTEST_CONFIG['end_date']
    )
    
    # Print results with APY
    for strategy, performance in results.items():
        returns = np.diff(performance['portfolio_values']) / performance['portfolio_values'][:-1]
        apy = np.mean((1 + returns) ** 365 - 1) * 100
        
        print(f"{strategy} Strategy Performance:")
        print(f"Total Return: {performance['total_return']*100:.2f}%")
        print(f"Average APY: {apy:.2f}%")
        print(f"Sharpe Ratio: {performance['sharpe_ratio']:.2f}")
        print(f"Max Drawdown: {performance['max_drawdown']*100:.2f}%\n")
    
    # Plot performance
    figs = backtester.plot_performance_comparison(results)
    for i, fig in enumerate(figs):
        fig.savefig(f'strategy_performance_{i+1}.png')
    plt.close('all')

if __name__ == '__main__':
    main()
