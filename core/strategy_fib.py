"""
VOLTX_Strategy_Fib Module
Implements Morning Fibonacci Retracement Strategy.
"""
from typing import Optional
from datetime import datetime, time
import pandas as pd

from infra.logger import logger
from infra.upbit_client import UpbitClient
from core.strategy import StrategyBase, Signal

class FibonacciMorningStrategy(StrategyBase):
    """
    VOLTX_FIB Strategy
    - Target: "Morning Rush" (09:00 - 12:00)
    - Impulse: Rise > 3.0% from Open
    - Entry: Retracement to 0.382 ~ 0.5 (Golden Pocket)
    - Filter: Healthy Correction (No massive dumping volume - simplified for now)
    """
    def check_signal(
        self, 
        symbol: str, 
        df_3m: pd.DataFrame, 
        df_15m: pd.DataFrame, 
        regime: str, 
        scanner_status: str
    ) -> Optional[Signal]:
        
        now = datetime.now()
        
        # 1. Time Window Filter (09:00 ~ 12:05)
        # We allow slightly past 12:00 to catch late morning dips
        if not (time(9, 0) <= now.time() <= time(12, 5)):
             return None

        try:
            # 2. Daily Data for Impulse Check
            # Need Today's Open and High
            # Upbit Daily Candle '09:00' is the current day's candle in KST
            df_daily = self.client.fetch_ohlcv(symbol, 'day', count=1)
            
            if df_daily.empty:
                return None
            
            today = df_daily.iloc[-1]
            day_open = today['open']
            day_high = today['high']
            day_low = today['low']
            current_price = df_3m.iloc[-1]['close'] # More timely than daily close
            
            # 3. Impulse Validation
            # Must have risen at least 3% from Open
            impulse_pct = (day_high - day_open) / day_open
            
            if impulse_pct < 0.03:
                return None # Not a strong enough impulse
                
            # 4. Fibonacci Calculation
            # Uptrend Retracement: High - ((High - Low) * level)
            # Impulse Range = Day High - Day Open (Assuming Open is the Low of the impulse start)
            # Actually, Low should be the low *since* 09:00. 
            # Usually Day Low is good enough if it hasn't crashed below Open.
            # But strictly for "Morning Rush", Open is usually the launchpad.
            # Let's use Range = High - Open for strict "Gap/Rush" logic, 
            # or High - Low if we want to include pre-pump dips.
            # User specified: "Start from 09:00 Start Price".
            
            impulse_range = day_high - day_open
            
            # Levels
            fib_0382 = day_high - (impulse_range * 0.382)
            fib_0500 = day_high - (impulse_range * 0.500)
            fib_0618 = day_high - (impulse_range * 0.618)
            
            # 5. Entry Condition (Golden Pocket)
            # Price is between 0.382 (Higher price) and 0.5 (Lower price)
            # Or usually defined as 0.618 to 0.5? 
            # User said: "0.382 ~ 0.5 line". 
            # Note: Retracement of 0.382 means price dropped 38.2% from top. 
            # Price level = High - 0.382 range. This is HIGHER than 0.5 level.
            # So Zone is [fib_0500, fib_0382].
            
            if fib_0500 <= current_price <= fib_0382:
                
                # Filter: Don't buy if we already broke below 0.618 earlier?
                # Hard to track without state. 
                # Current simple verification: Current price is in zone.
                
                # Check 3m Candle Color (Optional)
                # Strategy description says "Wait for stop falling".
                # Simple check: Current 3m is not a "Big Black Candle"?
                # Or just Limit Order logic.
                
                return Signal(
                    action="BUY",
                    symbol=symbol,
                    price=current_price,
                    reason=f"FIB: Golden Pocket {current_price} in [{fib_0500:.0f}, {fib_0382:.0f}] (Impulse {impulse_pct:.1%})"
                )
                
        except Exception as e:
            logger.error(f"Fib Strategy Error {symbol}: {e}")
            return None
            
        return None
