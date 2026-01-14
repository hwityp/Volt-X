"""
Upbit API Client for VOLT-X
Refactored from Quant-coin-bot to consolidate Data Feeder and Order Execution.
"""
import os
import uuid
import hashlib
import jwt
import requests
import time
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode
from pathlib import Path
from infra.logger import logger

class UpbitClient:
    """
    Unified Upbit Client
    - Market Data (OHLCV, Ticker) with Caching
    - Account & Ordering (Private API)
    """
    
    def __init__(self, access_key: Optional[str] = None, secret_key: Optional[str] = None):
        self.access_key = access_key or os.getenv("UPBIT_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("UPBIT_SECRET_KEY")
        self.base_url = "https://api.upbit.com/v1"
        self.cache_dir = Path("./data/ohlcv")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Auth & Private API
    # ============================================================
    def _get_auth_token(self, query: Optional[dict] = None) -> str:
        if not self.access_key or not self.secret_key:
            raise ValueError("Upbit API Keys are missing.")
            
        payload = {
            'access_key': self.access_key,
            'nonce': str(uuid.uuid4()),
        }
        
        if query:
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload['query_hash'] = m.hexdigest()
            payload['query_hash_alg'] = 'SHA512'
        
        token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return f"Bearer {token}"

    def get_balance(self, currency: str = "KRW") -> float:
        """Get balance for a specific currency."""
        try:
            headers = {"Authorization": self._get_auth_token()}
            resp = requests.get(f"{self.base_url}/accounts", headers=headers, timeout=5)
            resp.raise_for_status()
            for acc in resp.json():
                if acc['currency'] == currency:
                    return float(acc['balance'])
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get balance for {currency}: {e}")
            return 0.0

    def place_order(self, market: str, side: str, volume: Optional[float] = None, price: Optional[float] = None, ord_type: str = "limit") -> dict:
        """
        Execute Order (REAL TRADING)
        side: 'bid' (buy) or 'ask' (sell)
        """
        query = {
            'market': market,
            'side': side,
            'ord_type': ord_type,
        }
        if volume:
            query['volume'] = str(volume)
        if price:
            query['price'] = str(price)
            
        headers = {
            "Authorization": self._get_auth_token(query),
            "Content-Type": "application/json"
        }
        
        resp = requests.post(f"{self.base_url}/orders", json=query, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def cancel_order(self, uuid: str) -> dict:
        """Cancel an order by UUID."""
        query = {'uuid': uuid}
        headers = {"Authorization": self._get_auth_token(query)}
        resp = requests.delete(f"{self.base_url}/order", params=query, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_order(self, uuid: str) -> dict:
        """Get order status."""
        query = {'uuid': uuid}
        headers = {"Authorization": self._get_auth_token(query)}
        resp = requests.get(f"{self.base_url}/order", params=query, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ============================================================
    # Public Market Data API
    # ============================================================
    def get_current_price(self, market: str) -> float:
        """Get current price for a market."""
        try:
            resp = requests.get(
                f"{self.base_url}/ticker", 
                params={"markets": market}, 
                headers={"Accept": "application/json"},
                timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data[0]['trade_price']) if data else 0.0
        except Exception as e:
            logger.error(f"Failed to get price for {market}: {e}")
            return 0.0

    def get_krw_markets(self) -> List[str]:
        """Get all KRW markets."""
        try:
            resp = requests.get(f"{self.base_url}/market/all?isDetails=false", timeout=5)
            resp.raise_for_status()
            return [m['market'] for m in resp.json() if m['market'].startswith('KRW-')]
        except Exception as e:
            logger.error(f"Failed to fetch market list: {e}")
            return []

    # ============================================================
    # OHLCV Data & Caching
    # ============================================================
    def fetch_ohlcv(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        """
        Fetch OHLCV Data with Caching.
        timeframe: '1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d'
        """
        cache_path = self.cache_dir / f"{symbol.replace('-', '_')}_{timeframe}.csv"
        
        # 1. Try Cache
        cached_df = self._load_cache(cache_path, start, end)
        if cached_df is not None:
             # Check if cache covers the requested range seamlessly
             # For simplicity in this plan, if cache exists and covers part, we might still fetch missing.
             # However, let's implement the 'fetch needed' logic simply by checking last time.
             if cached_df.index.max() >= end - timedelta(minutes=1): # Roughly met
                 return cached_df

        # 2. Fetch from API (simplified logic: fetch backward from end until start)
        new_df = self._fetch_from_api(symbol, timeframe, start, end)
        
        # 3. Merge and Save
        if not new_df.empty:
            full_df = self._merge_and_save_cache(cached_df, new_df, cache_path)
            # Filter return range
            return full_df.loc[(full_df.index >= start) & (full_df.index <= end)]
            
        return cached_df if cached_df is not None else pd.DataFrame()

    def _fetch_from_api(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Recursive fetch from Upbit API"""
        unit_conf = self._get_timeframe_unit(timeframe)
        url = unit_conf['url']
        
        all_candles = []
        current_to = end
        
        while current_to > start:
            params = {
                "market": symbol,
                "count": 200,
                "to": current_to.strftime("%Y-%m-%dT%H:%M:%S")
            }
            try:
                resp = requests.get(url, params=params, timeout=5)
                # Retry once
                if resp.status_code == 429:
                    time.sleep(0.5)
                    resp = requests.get(url, params=params, timeout=5)
                
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                    
                all_candles.extend(data)
                
                # Next Fetch Time
                last_candle_time = data[-1]['candle_date_time_kst']
                current_to = datetime.fromisoformat(last_candle_time) - timedelta(seconds=1)
                
                time.sleep(0.1) # Rate limit
                if len(data) < 200:
                    break
                    
            except Exception as e:
                logger.error(f"API Fetch Error ({symbol}): {e}")
                break
                
        if not all_candles:
            return pd.DataFrame()
            
        df = pd.DataFrame(all_candles)
        df['timestamp'] = pd.to_datetime(df['candle_date_time_kst'])
        df = df.set_index('timestamp').sort_index()
        df = df[['opening_price', 'high_price', 'low_price', 'trade_price', 'candle_acc_trade_volume']]
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        return df

    def _get_timeframe_unit(self, timeframe: str) -> dict:
        tf_map = {
            '1m': ('minutes/1', ''), '3m': ('minutes/3', ''), '5m': ('minutes/5', ''),
            '10m': ('minutes/10', ''), '15m': ('minutes/15', ''), '30m': ('minutes/30', ''),
            '1h': ('minutes/60', ''), '4h': ('minutes/240', ''), '1d': ('days', '')
        }
        path, _ = tf_map.get(timeframe, ('minutes/60', ''))
        return {'url': f"{self.base_url}/candles/{path}"}

    def _load_cache(self, path: Path, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path, parse_dates=['timestamp'], index_col='timestamp')
            # Check coverage could be added here
            return df
        except Exception:
            return None

    def _merge_and_save_cache(self, old_df: Optional[pd.DataFrame], new_df: pd.DataFrame, path: Path) -> pd.DataFrame:
        if old_df is not None:
            combined = pd.concat([old_df, new_df])
            combined = combined[~combined.index.duplicated(keep='last')] # Prefer new
            combined = combined.sort_index()
        else:
            combined = new_df
            
        combined.to_csv(path)
        return combined
