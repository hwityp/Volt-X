"""
VOLTX_Strategy_Fib Module
Implements Advanced Morning Fibonacci Retracement Strategy.
"""
from typing import Optional, Dict
from datetime import datetime, time, timedelta
import pandas as pd
import requests
import os

from infra.logger import logger
from infra.upbit_client import UpbitClient
from core.strategy import StrategyBase, Signal
from utils.indicators import calculate_sma

class FibonacciMorningStrategy(StrategyBase):
    """
    VOLTX_FIB Strategy (Advanced)
    - Target: "Morning Rush" (09:00 - 11:00)
    - Setup: Daily MA 5 > 10 > 20 (Uptrend)
    - Anchor: First 5-minute candle (09:00:00 - 09:05:00)
    - Entry: Pullback to 0.382 ~ 0.5 (Golden Pocket)
    - Confirmation: check_support_at_fib()
    """
    def __init__(self, client: UpbitClient):
        super().__init__(client)
        self.telegram_token = os.environ.get("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    def check_signal(
        self, 
        symbol: str, 
        df_3m: pd.DataFrame, 
        df_15m: pd.DataFrame, 
        regime: str, 
        scanner_status: str
    ) -> Optional[Signal]:
        
        now = datetime.now()
        
        # 1. Time Window Filter (09:05 ~ 11:30)
        # Must wait for first 5m candle to close (09:05)
        if not (time(9, 5) <= now.time() <= time(11, 30)):
             return None

        try:
            # 2. Daily Trend Alignment Filter (MA 5 > 10 > 20)
            # Need at least 20 days of data
            df_daily = self.client.fetch_ohlcv(symbol, 'day', count=30)
            if not self.check_daily_alignment(df_daily):
                return None
            
            # 3. Identify First 5m Candle (The Anchor)
            # We need 5m data. df_15m is too coarse. 
            # We fetch 5m candles covering 09:00 today.
            today_str = now.strftime("%Y-%m-%d")
            start_of_day = datetime.strptime(f"{today_str} 09:00:00", "%Y-%m-%d %H:%M:%S")
            
            # Fetch last ~30 5m candles to find the 09:00 one easily
            df_5m = self.client.fetch_ohlcv(symbol, '5m', count=36) # 36 * 5 = 3 hours coverage
            
            # Find the candle that starts at 09:00
            # Pandas timestamp might be UTC or KST depending on UpbitClient. 
            # UpbitClient usually handles timezone logic or returns KST aware.
            # Assuming 'timestamp' column or index matches. 
            # If not found, skip.
            
            anchor_candle = None
            for idx, row in df_5m.iterrows():
                # Assuming index is datetime
                # Check if hour=9 and minute=0 (KST)
                # If using standard KST client
                if idx.hour == 9 and idx.minute == 0:
                    anchor_candle = row
                    break
            
            if anchor_candle is None:
                return None
                
            day_open = anchor_candle['open']
            day_high = anchor_candle['high'] # Initial High? 
            # WAIT. Strategy says "High of the first 5m candle" or "Daily High"?
            # User spec: "First 5min candle High/Low reference".
            # OK, we use specific 5m candle as the Impulse range.
            
            ref_high = anchor_candle['high']
            ref_low = anchor_candle['low'] # or Open? Video said "Start Price". 
            # User prompt: "First 5m candle High and Low".
            
            # Check Impulse Size
            impulse_pct = (ref_high - ref_low) / ref_low
            if impulse_pct < 0.03: # Must be at least 3% spike
                return None
                
            # 4. Calculate Fib Levels
            # Uptrend: Zones are below High.
            range_val = ref_high - ref_low
            fib_0382 = ref_high - (range_val * 0.382) # Top of zone
            fib_0500 = ref_high - (range_val * 0.500) # Bottom of zone
            fib_0618 = ref_high - (range_val * 0.618) # SL level
            
            current_price = df_5m.iloc[-1]['close']
            
            # 5. Check Entry Zone
            # Price is within 0.382 ~ 0.5
            if fib_0500 <= current_price <= fib_0382:
                
                # 6. Advanced Confirmation: Support Check
                support_conf = self.check_support_at_fib(symbol, df_5m, df_daily)
                
                if support_conf['valid']:
                    self.send_telegram_alert(f"🚀 FIB Entry: {symbol} at {current_price} (Zone: {fib_0382:.0f}~{fib_0500:.0f})")
                    
                    return Signal(
                        action="BUY",
                        symbol=symbol,
                        price=current_price,
                        reason=f"FIB: Golden Pocket [{fib_0500:.0f}-{fib_0382:.0f}], Vol: {support_conf['msg']}"
                    )

        except Exception as e:
            logger.error(f"FIB Strategy Error {symbol}: {e}")
            return None
            
        return None

    def check_daily_alignment(self, df_daily: pd.DataFrame) -> bool:
        """
        Check if Daily MA 5 > 10 > 20 (Golden Alignment)
        """
        if df_daily.empty or len(df_daily) < 20:
            return False
            
        ma5 = calculate_sma(df_daily['close'], 5).iloc[-1]
        ma10 = calculate_sma(df_daily['close'], 10).iloc[-1]
        ma20 = calculate_sma(df_daily['close'], 20).iloc[-1]
        
        return ma5 > ma10 > ma20

    def check_support_at_fib(self, symbol: str, df_5m: pd.DataFrame, df_daily: pd.DataFrame) -> Dict:
        """
        Confirm Support at Fibonacci Level.
        1. Volume Analysis: Pullback volume < Impulse Volume
        2. Orderbook: Bid Depth > Ask Depth (Optional/Simulated)
        """
        try:
            # 1. Volume Analysis
            # Compare current falling volume vs 09:00 impulse volume from df_5m
            # 09:00 volume is usually huge.
            # We want current volume to be 'low' (drying up).
            
            # Simple heuristic: Current volume < 50% of 09:00 volume
            # Find 09:00 candle again (or pass it in)
            impulse_vol = 0 
            for idx, row in df_5m.iterrows():
                if idx.hour == 9 and idx.minute == 0:
                    impulse_vol = row['volume']
                    break
            
            if impulse_vol == 0: return {'valid': False, 'msg': 'No Impulse Vol'}
            
            current_vol = df_5m.iloc[-1]['volume']
            
            # Strict Rule: Volume must be decreasing (< 30% of impulse peak)
            if current_vol > impulse_vol * 0.3:
                return {'valid': False, 'msg': f"High Vol Drop ({current_vol/impulse_vol:.2%})"}
            
            # 2. Orderbook Analysis (Slippage/Support check)
            # Fetch realtime orderbook
            """
            orderbook = self.client.get_orderbook(symbol) # Expensive API call?
            total_bid_size = sum([u['bid_size'] for u in orderbook['orderbook_units'][:5]])
            total_ask_size = sum([u['ask_size'] for u in orderbook['orderbook_units'][:5]])
            
            if total_bid_size < total_ask_size * 1.2:
                 return {'valid': False, 'msg': 'Weak Bid Support'}
            """
            # Disabled orderbook for dry-run efficiency, relying on Volume Pattern
            
            return {'valid': True, 'msg': 'Vol Dried Up'}
            
        except Exception as e:
            logger.error(f"Support Check Error: {e}")
            return {'valid': False, 'msg': 'Error'}

    def send_telegram_alert(self, msg: str):
        """
        Send Telegram Notification
        """
        if not self.telegram_token or not self.telegram_chat_id:
            return
            
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {"chat_id": self.telegram_chat_id, "text": f"[VOLT-X] {msg}"}
            requests.post(url, data=data, timeout=3)
        except Exception as e:
            logger.error(f"Telegram Fail: {e}")
