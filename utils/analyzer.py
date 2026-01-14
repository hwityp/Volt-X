"""
VOLTX_Analyzer Module
Calculates performance metrics and generates tuning reports.
"""
import pandas as pd
from typing import List, Dict
from infra.logger import logger

class PerformanceAnalyzer:
    """
    Analyzes trade history and generates reports.
    """
    
    def __init__(self):
        self.trades = []
        
    def add_trade(self, trade: Dict):
        """
        Add a completed trade record.
        Trade format: {'symbol': str, 'strategy': str, 'entry_price': float, 'exit_price': float, 'pnl_pct': float, 'regime': str}
        """
        self.trades.append(trade)
        
    def generate_report(self) -> Dict:
        """
        Generate performance report.
        """
        if not self.trades:
            return {"message": "No trades recorded."}
            
        df = pd.DataFrame(self.trades)
        
        # Overall Metrics
        total_trades = len(df)
        wins = df[df['pnl_pct'] > 0]
        losses = df[df['pnl_pct'] <= 0]
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        
        gross_profit = wins['pnl_pct'].sum()
        gross_loss = abs(losses['pnl_pct'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = wins['pnl_pct'].mean() if not wins.empty else 0
        avg_loss = losses['pnl_pct'].mean() if not losses.empty else 0
        wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        report = {
            "Total Trades": total_trades,
            "Win Rate": f"{win_rate:.1%}",
            "Profit Factor": f"{profit_factor:.2f}",
            "Avg Win": f"{avg_win:.2%}",
            "Avg Loss": f"{avg_loss:.2%}",
            "W/L Ratio": f"{wl_ratio:.2f}",
        }
        
        # Strategy Breakdown
        strategy_stats = df.groupby('strategy')['pnl_pct'].agg(['count', 'mean', 'sum'])
        report['By Strategy'] = strategy_stats.to_dict()
        
        # Tuning Suggestions
        suggestions = []
        if win_rate < 0.45:
            suggestions.append("Win Rate Low (< 45%). Tighten Entry Filters (RSI, Drop).")
        if wl_ratio < 1.5:
            suggestions.append("W/L Ratio Low (< 1.5). Increase TP or Tighten SL.")
        if total_trades < 5: # Assuming adequate timeframe
            suggestions.append("Low Trade Count. Relax Entry Conditions?")
            
        report['Suggestions'] = suggestions
        
        return report

    def log_report(self):
        report = self.generate_report()
        logger.info("=== Performance Report ===")
        for k, v in report.items():
            if k == "By Strategy":
                 logger.info(f"[By Strategy]:\n{pd.DataFrame(v)}")
            elif k == "Suggestions":
                logger.info("[Suggestions]:")
                for s in v:
                    logger.info(f" - {s}")
            else:
                logger.info(f"{k}: {v}")
        logger.info("==========================")
