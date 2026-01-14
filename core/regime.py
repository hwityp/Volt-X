"""
VOLTX_Regime Module
Analyzes Market Regime (BULL, BEAR, FLAT) using BTC/Index data.
"""
from typing import Literal
from datetime import datetime, timedelta
import pandas as pd
from infra.upbit_client import UpbitClient
from infra.logger import logger
from utils.indicators import calculate_volatility

RegimeType = Literal["BULL", "BEAR", "FLAT"]

class RegimeAnalyzer:
    """
    Analyzes market regime based on BTC price action.
    """
    
    def __init__(self, client: UpbitClient):
        self.client = client
        self.market_index = "KRW-BTC" # Using BTC as proxy for market
        
    def analyze(self) -> dict:
        """
        Determine current regime.
        Returns:
            {
                'type': BULL|BEAR|FLAT,
                'factor': float (position sizing factor),
                'details': dict
            }
        """
        end = datetime.now()
        start = end - timedelta(days=5)
        
        # Fetch 4h candles
        df = self.client.fetch_ohlcv(self.market_index, '4h', start, end)
        
        if df.empty or len(df) < 6:
            logger.warning("Insufficient data for Regime Analysis. Defaulting to FLAT.")
            return {'type': "FLAT", 'factor': 1.0, 'details': {}}
            
        # Analysis Logic
        # 1. 24h Return (Last 6 candles of 4h)
        # 2. 72h Return (Last 18 candles)
        # 3. Volatility
        
        current_price = df.iloc[-1]['close']
        price_24h_ago = df.iloc[-7]['close'] if len(df) >= 7 else df.iloc[0]['close']
        price_72h_ago = df.iloc[-19]['close'] if len(df) >= 19 else df.iloc[0]['close']
        
        ret_24h = (current_price - price_24h_ago) / price_24h_ago
        ret_72h = (current_price - price_72h_ago) / price_72h_ago
        
        # Volatility (std of last 20 4h candles)
        vol = calculate_volatility(df['close'], period=20).iloc[-1]
        if pd.isna(vol):
            vol = 0.005 # Default low vol
            
        # Classification
        # BULL: Strong positive return (+3% over 24h or +5% over 72h)
        # BEAR: Strong negative return (-3% over 24h or -5% over 72h)
        # FLAT: Between
        
        regime_type = "FLAT"
        factor = 1.0
        
        if ret_24h > 0.03 or ret_72h > 0.05:
            regime_type = "BULL"
            factor = 1.2
            # Check for Overheated? Maybe
            
        elif ret_24h < -0.03 or ret_72h < -0.05:
            regime_type = "BEAR"
            factor = 0.5
        
        logger.info(f"Regime: {regime_type} (24h: {ret_24h:.2%}, 72h: {ret_72h:.2%}, Vol: {vol:.4f})")
        
        return {
            'type': regime_type,
            'factor': factor,
            'details': {
                'ret_24h': ret_24h,
                'ret_72h': ret_72h,
                'volatility': vol
            }
        }
