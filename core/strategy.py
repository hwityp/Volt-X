"""
VOLTX_Strategy Module
Implements DipBuying and Breakout strategies.
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional, Literal
from datetime import datetime
import pandas as pd

from infra.logger import logger
from infra.upbit_client import UpbitClient
from utils.indicators import (
    calculate_rsi, calculate_bollinger_bands, calculate_ema, calculate_atr, calculate_sma
)

SignalType = Literal["BUY", "SELL", "HOLD", "TP", "SL"]

class Signal:
    def __init__(self, action: SignalType, symbol: str, price: float, reason: str, quantity: float = 0.0):
        self.action = action
        self.symbol = symbol
        self.price = price
        self.reason = reason
        self.quantity = quantity # Optional, often calculated later by RiskManager but strategy can suggest size.

class StrategyBase(ABC):
    def __init__(self, client: UpbitClient):
        self.client = client
        
    @abstractmethod
    def check_signal(
        self, 
        symbol: str, 
        df_3m: pd.DataFrame, 
        df_15m: pd.DataFrame, # Strategy might need multiple frames
        regime: str, 
        scanner_status: str
    ) -> Optional[Signal]:
        pass

class DipStrategy(StrategyBase):
    """
    VOLTX_DIP Strategy
    - Trend Active
    - EMA 12 > EMA 26
    - Drop > 1.5%
    - RSI < 50
    - BB Lower Touch
    - Reversal Confirmation
    """
    def check_signal(
        self, 
        symbol: str, 
        df_3m: pd.DataFrame, 
        df_15m: pd.DataFrame, 
        regime: str, 
        scanner_status: str
    ) -> Optional[Signal]:
        
        if scanner_status != "TREND_ACTIVE":
            if scanner_status == "EXHAUSTED":
                return None # Don't buy exhausted
                
        # Use 3m for precise entry
        if df_3m.empty or len(df_3m) < 30:
            return None
            
        last = df_3m.iloc[-1]
        close = last['close']
        
        # 0. Trend Filter (EMA 12 > 26)
        ema12 = calculate_ema(df_3m['close'], 12).iloc[-1]
        ema26 = calculate_ema(df_3m['close'], 26).iloc[-1]
        
        if ema12 <= ema26:
            return None
            
        # 1. Drop Calculation (From recent high)
        # Find Recent High in last 20 candles
        recent_high = df_3m['high'].iloc[-20:].max()
        drop_pct = (recent_high - close) / recent_high
        
        drop_threshold = 0.020 # Default
        if regime == "BULL": 
            drop_threshold = 0.020 # Middle ground (was 1.2 then 2.5)
            rsi_threshold = 45     # Middle ground (was 55 then 40)
        elif regime == "FLAT":
            drop_threshold = 0.025 
            rsi_threshold = 40     
        else: # BEAR
            drop_threshold = 0.030
            rsi_threshold = 35
        
        if drop_pct < drop_threshold:
            return None
            
        # 2. RSI Filter
        rsi = calculate_rsi(df_3m['close'], 14).iloc[-1]
        
        if rsi > rsi_threshold:
            return None
            
        # 3. BB Lower Touch
        _, _, lower = calculate_bollinger_bands(df_3m['close'], 20, 2.0)
        bb_lower = lower.iloc[-1]
        
        if last['low'] > bb_lower * 1.005: # Not close enough to lower band
            return None
            
        # 4. Reversal Confirmation (Hammer/Pinbar or Green Candle)
        # Check current or PREVIOUS candle?
        # If we act on closed candle, check last closed.
        # But 'last' here typically is current forming. 
        # Safer to check if price is bouncing now? 
        # Let's say we enter if close > open (Green) and we successfully touched low.
        is_reversal = False
        if last['close'] >= last['open']:
            # It's a green candle
            is_reversal = True
        else:
            # Maybe a pinbar? Lower wick > body * 2
            body = abs(last['close'] - last['open'])
            lower_wick = min(last['close'], last['open']) - last['low']
            if lower_wick > body * 2:
                is_reversal = True
                
        if not is_reversal:
            return None
            
        return Signal(
            action="BUY",
            symbol=symbol,
            price=close,
            reason=f"DIP: Drop {drop_pct:.1%}, RSI {rsi:.1f}, BB Touch"
        )
        
class VolatilityBreakoutStrategy(StrategyBase):
    """
    VOLTX_VBS Strategy
    - Larry Williams Volatility Breakout
    - Target = Open + (Prev Range * k)
    - k = 0.7 (Increased from 0.5 to reduce false breakouts)
    - Only for Hot Symbols (Volume Spike Active)
    - Trend Filter: Price > 3m SMA 120
    """
    def check_signal(
        self, 
        symbol: str, 
        df_3m: pd.DataFrame, 
        df_15m: pd.DataFrame, 
        regime: str, 
        scanner_status: str
    ) -> Optional[Signal]:
        
        # 1. Regime Filter (New in Proto 1.5)
        # VBS is a "Trend Following" strategy. It fails in Chop/Bear.
        # Strict Rule: Only trade VBS in BULL market.
        if regime != "BULL":
            return None

        # 2. Active Filter: Only trade if volume is active (Scanner)
        if scanner_status != "TREND_ACTIVE":
             if scanner_status == "EXHAUSTED": return None
             if scanner_status == "NORMAL": return None

        # 3. Multi-Timeframe Trend Filter (New in Proto 1.5)
        # Ensure 15m trend is UP (Price > 15m SMA 20)
        if df_15m.empty or len(df_15m) < 20:
            return None
            
        sma20_15m = calculate_sma(df_15m['close'], 20).iloc[-1]
        if df_15m['close'].iloc[-1] < sma20_15m:
            return None

        # 4. Need Daily Data for VBS
        try:
            # We fetch 2 days of daily candles to get Prev Close/Range and Current Open
            end = datetime.now()
            start = end - pd.Timedelta(days=3)
            df_daily = self.client.fetch_ohlcv(symbol, 'day', start, end)
            
            if df_daily.empty or len(df_daily) < 2:
                return None
            
            prev_day = df_daily.iloc[-2]
            current_day = df_daily.iloc[-1]
            
            prev_range = prev_day['high'] - prev_day['low']
            # k = 0.7 for stricter entry
            target_price = current_day['open'] + (prev_range * 0.7)
            
            if df_3m.empty or len(df_3m) < 120:
                return None

            current_price = df_3m.iloc[-1]['close']
            
            # Trend Filter: Price > SMA 120 (3m) => Price is above 6-hour average
            sma120 = calculate_sma(df_3m['close'], 120).iloc[-1]
            if current_price < sma120:
                return None
            
            # 3. Bollinger Band Breakout Confirmation (New in Proto 1.3)
            # Ensure price is essentially at or above the Upper Band (Expansion Phase)
            _, upper, _ = calculate_bollinger_bands(df_3m['close'], 20, 2.0)
            bb_upper = upper.iloc[-1]
            
            # Allow slight tolerance (0.5%) below upper band to catch breakout early
            if current_price < bb_upper * 0.995:
                 return None

            # 4. Breakout Check
            if current_price >= target_price:
                # 5. Filter: Don't chase if too high (> 3% above target)
                if current_price > target_price * 1.03:
                    return None
                    
                # 6. RSI Filter (Optional safety)
                rsi = calculate_rsi(df_3m['close'], 14).iloc[-1]
                if rsi > 75: 
                    return None
                    
                return Signal(
                    action="BUY",
                    symbol=symbol,
                    price=current_price,
                    reason=f"VBS: Price {current_price} > Target {target_price:.0f} (Range {prev_range:.0f}, k=0.7)"
                )
                
        except Exception as e:
            logger.error(f"VBS Analysis Failed for {symbol}: {e}")
            return None
            
        return None
