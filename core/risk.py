"""
VOLTX_Risk Module
Manages Position Sizing, Daily Limits, and Risk Controls.
"""
from typing import Dict
from datetime import date
from infra.logger import logger

class RiskManager:
    """
    Control Tower for Risk.
    - Determines Position Size based on Regime & Tier.
    - Enforces Daily Loss Limit.
    - Monitors Consecutive Losses.
    """
    
    def __init__(self):
        self.max_daily_loss_pct = -0.05 # -5%
        self.daily_pnl_pct = 0.0
        self.consecutive_losses = 0
        self.last_reset_date = date.today()
        self.is_trading_halted = False
        
    def _reset_daily_if_needed(self):
        if date.today() > self.last_reset_date:
            self.daily_pnl_pct = 0.0
            self.consecutive_losses = 0 # Optional: reset consec loss or keep? Usually daily reset.
            self.last_reset_date = date.today()
            self.is_trading_halted = False
            logger.info("Daily Risk Counter Reset.")
            
    def update_pnl(self, trade_pnl_pct: float):
        """Call this after a trade is closed"""
        self._reset_daily_if_needed()
        self.daily_pnl_pct += trade_pnl_pct
        
        if trade_pnl_pct < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
            
        # Circuit Breaker Check
        if self.daily_pnl_pct <= self.max_daily_loss_pct:
            self.is_trading_halted = True
            logger.error(f"🚨 Daily Loss Limit Hit ({self.daily_pnl_pct:.2%}). Trading HALTED.")
            
        if self.consecutive_losses >= 4:
            self.is_trading_halted = True
            logger.error(f"🚨 Consecutive Loss Limit ({self.consecutive_losses}). Trading HALTED.")

    def calculate_position_size(
        self, 
        account_balance: float, 
        regime: str, 
        symbol_tier: str = "L1"
    ) -> float:
        """
        Calculate Position Size in KRW.
        """
        self._reset_daily_if_needed()
        
        if self.is_trading_halted:
            return 0.0
            
        # Base Size
        # L1: 3% of account
        # L2: 1.5% of account
        base_pct = 0.03 if symbol_tier == "L1" else 0.015
        
        # Regime Factor
        # BULL: 1.0 (or 1.2 aggressive)
        # BEAR: 0.5
        # FLAT: 1.0
        regime_factor = {
            "BULL": 1.2,
            "FLAT": 1.0,
            "BEAR": 0.5
        }.get(regime, 1.0)
        
        # Consec Loss Factor (Reduce size if losing)
        # 1 loss -> 100%, 2 -> 80%, 3 -> 50%
        loss_factor = 1.0
        if self.consecutive_losses == 1: loss_factor = 1.0
        elif self.consecutive_losses == 2: loss_factor = 0.8
        elif self.consecutive_losses == 3: loss_factor = 0.5
        
        final_pct = base_pct * regime_factor * loss_factor
        
        # Clip max size (never > 5% per trade)
        final_pct = min(final_pct, 0.05)
        
        size_krw = account_balance * final_pct
        
        # Minimum order size check (5000 KRW)
        if size_krw < 6000:
            return 0.0
            
        return size_krw

    def check_entry_allowed(self, regime: str, strategy_type: str) -> bool:
        """
        Final Gatekeeper for Entry.
        """
        if self.is_trading_halted:
            return False
            
        # if regime == "BEAR" and strategy_type == "BREAKOUT":
        #    return False # No breakout in Bear market
            
        return True
