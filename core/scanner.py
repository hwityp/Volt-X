"""
VOLTX_Scanner Module
Detects Volume Spikes and Climaxes in real-time (3m timeframe).
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List
from infra.upbit_client import UpbitClient
from infra.logger import logger
from utils.indicators import calculate_rsi

class ScannerState:
    """State of a tracked symbol"""
    def __init__(self, symbol):
        self.symbol = symbol
        self.volume_spike = False
        self.volume_climax = False
        self.is_exhausted = False
        self.last_update = None
        self.exhausted_until = None

class VolumeScanner:
    """
    Scans hot_symbols for Volume Spikes/Climaxes.
    """
    
    def __init__(self, client: UpbitClient):
        self.client = client
        self.states: Dict[str, ScannerState] = {}
        self.spike_threshold = 3.0
        self.climax_threshold = 5.0
        
    def scan(self, symbols: List[str]) -> Dict[str, str]:
        """
        Scan updated candles for the given symbols.
        Returns a dict of {symbol: status} ('TREND_ACTIVE', 'EXHAUSTED', 'NORMAL')
        """
        results = {}
        end = datetime.now()
        start = end - timedelta(minutes=100) # Need ~20-30 candles for avg volume
        
        # Optimization: Use ThreadPoolExecutor if too slow, but sequential is safer for now.
        for symbol in symbols:
            # Init state if new
            if symbol not in self.states:
                self.states[symbol] = ScannerState(symbol)
            state = self.states[symbol]
            
            # Check Exhaustion Timeout
            if state.is_exhausted:
                if state.exhausted_until and datetime.now() > state.exhausted_until:
                    state.is_exhausted = False
                    logger.info(f"{symbol}: Exhaustion Cooldown Over. Resetting.")
                else:
                    results[symbol] = "EXHAUSTED"
                    continue
            
            # Fetch 3m candles
            df = self.client.fetch_ohlcv(symbol, '3m', start, end)
            if df.empty or len(df) < 20:
                results[symbol] = "NORMAL"
                continue
            
            # Analysis
            last = df.iloc[-1]
            prev_vol_avg = df['volume'].iloc[-21:-1].mean() # Avg of previous 20 (excluding current if incomplete?) 
            # Actually, using last closed candles is better. The last row in fetch_ohlcv depends on API. 
            # Upbit API returns partial current candle. 
            # We treat the current (latest) candle as the one to check for spike.
            
            if prev_vol_avg == 0: 
                prev_vol_avg = 1
                
            rel_vol = last['volume'] / prev_vol_avg
            
            # Spike Detection
            if rel_vol >= self.spike_threshold:
                if not state.volume_spike:
                    logger.info(f"{symbol}: Volume Spike Detected (Rel: {rel_vol:.1f}x)")
                    state.volume_spike = True
            
            # Climax Detection
            # Condition: Huge Volume + (Reversal Candle OR Huge Wick)
            is_climax = False
            if rel_vol >= self.climax_threshold:
                upper_shadow = last['high'] - max(last['close'], last['open'])
                body = abs(last['close'] - last['open'])
                total_range = last['high'] - last['low']
                
                # Big upper wick? (> 50% of range)
                upper_shadow_ratio = upper_shadow / total_range if total_range > 0 else 0
                
                # Bearish Reversal? (Close < High * 0.97)
                drop_from_high = (last['high'] - last['close']) / last['high']
                
                if upper_shadow_ratio >= 0.5 or drop_from_high >= 0.03:
                    is_climax = True
                    logger.info(f"{symbol}: Volume Climax Detected! (Rel: {rel_vol:.1f}x, Shadow: {upper_shadow_ratio:.2f})")
                    state.volume_climax = True
            
            # Exhaustion Logic
            # If Climax + RSI Overbought -> Exhausted
            if is_climax:
                # Calc RSI
                rsi = calculate_rsi(df['close'], 14).iloc[-1]
                if rsi >= 70:
                    state.is_exhausted = True
                    # Cool off for 60 mins
                    state.exhausted_until = datetime.now() + timedelta(minutes=60)
                    logger.warning(f"{symbol} marked EXHAUSTED (Climax + RSI {rsi:.1f}). Cooldown 60m.")
                    results[symbol] = "EXHAUSTED"
                    continue
            
            # Result
            if state.volume_spike:
                results[symbol] = "TREND_ACTIVE"
            else:
                results[symbol] = "NORMAL"
                
        return results
