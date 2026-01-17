"""
VOLTX_Universe Module
Selects target symbols based on Volume and Volatility.
"""
import pandas as pd
from datetime import datetime, timedelta
from typing import List
from infra.upbit_client import UpbitClient
from infra.logger import logger

class UniverseSelector:
    """
    Selects 'hot_symbols' for VOLT-X strategies.
    Criteria:
    1. 24h Volume >= 10B KRW
    2. High Volatility (std of returns) & High Returns
    3. Score = Volume * Volatility
    """
    
    def __init__(self, client: UpbitClient):
        self.client = client
        self.blacklist = ['KRW-BTT', 'KRW-XEC'] # Tick value too small or erratic
        self.min_volume_krw = 10_000_000_000 # 10 Billion KRW

    def get_top_movers(self, limit: int = 10) -> List[str]:
        """
        Get Top N symbols by Score (Volume * Volatility)
        """
        logger.info("Scanning for Top Movers...")
        markets = self.client.get_krw_markets()
        candidates = []
        
        # We need recent 24h data. 
        # Getting 'ticker' for all markets is efficient for Volume and Change.
        # But 'volatility' needs history. 
        # Optimization: Filter by Volume first using Ticker, then calc Volatility for candidates.
        
        # 1. Fetch Ticker for all markets
        # Upbit allows comma separated markets in ticker API
        # but max length is limited. Split into chunks.
        chunk_size = 50
        all_tickers = []
        for i in range(0, len(markets), chunk_size):
            chunk = markets[i:i+chunk_size]
            mkts_str = ",".join(chunk)
            # We use a direct requests call here or add a bulk method to client.
            # For now, let's use client.get_current_price style but extended?
            # Actually client.get_current_price only returns price.
            # Let's assume we can fetch detailed ticker info. 
            # I'll restart the loop and do it properly or add a method to client.
            # Or just use the `get_current_price` logic but raw request.
            pass
        
        # Let's just implement a quick helper here or use slow loop if list is small (~100 items).
        # Better: Add `get_tickers` to UpbitClient. 
        # But for now I'll do it purely here to avoid touching client file again immediately.
        
        import requests
        tickers_data = []
        for i in range(0, len(markets), chunk_size):
            chunk = markets[i:i+chunk_size]
            url = f"https://api.upbit.com/v1/ticker?markets={','.join(chunk)}"
            try:
                resp = requests.get(url, timeout=5)
                tickers_data.extend(resp.json())
            except Exception as e:
                logger.error(f"Ticker fetch failed: {e}")
                
        # 2. Filter by Volume
        volume_filtered = []
        for t in tickers_data:
            m = t['market']
            if m in self.blacklist:
                continue
            
            acc_trade_price_24h = t['acc_trade_price_24h']
            if acc_trade_price_24h >= self.min_volume_krw:
                volume_filtered.append({
                    'market': m,
                    'volume_24h': acc_trade_price_24h,
                    'change_rate': t['signed_change_rate'], # 24h return info
                    'high_rate': (t['high_price'] - t['opening_price'])/t['opening_price'] # rough intraday vol
                })
        
        logger.info(f"Volume filtered candidates: {len(volume_filtered)}")
        
        # 3. Calculate Score
        # Score = Volume * Volatility
        # Instead of expensive candle fetch for volatility, we use 'signed_change_rate' abs + volume weight?
        # The user requested: "vol_24h = recent 24h return standard deviation".
        # This implies we DO need candles. But iterating 30-40 coins is fine.
        
        scored_candidates = []
        end = datetime.now()
        start = end - timedelta(days=2) # Fetch enough for 24h calculation
        
        for item in volume_filtered:
            m = item['market']
            # Fetch 1h candles for volatility calculation (24 data points is enough for rough std)
            df = self.client.fetch_ohlcv(m, '1h', start, end)
            if df.empty or len(df) < 24:
                continue
            
            # Use last 24h
            recent = df.iloc[-24:]
            pct_change = recent['close'].pct_change()
            volatility = pct_change.std()
            
            if pd.isna(volatility):
                volatility = 0.0
                
            # Trend Filter (New in Proto 1.6)
            # Filter out coins trading BELOW 24h SMA (Downtrend / Panic Sell)
            sma24 = recent['close'].mean()
            current_price = recent['close'].iloc[-1]
            
            if current_price < sma24:
                # logger.info(f"Skipping {m}: Downtrend (Price {current_price} < SMA24 {sma24:.1f})")
                continue

            # Score = Volume(KRW) * Volatility
            # Normalize volume to avoid it dominating too much? 
            # User said: score = 24h volume * vol_24h
            score = item['volume_24h'] * volatility
            
            scored_candidates.append({
                'market': m,
                'score': score,
                'volume': item['volume_24h'],
                'volatility': volatility
            })
            
        # 4. Sort and Pick Top N
        scored_candidates.sort(key=lambda x: x['score'], reverse=True)
        top_n = scored_candidates[:limit]
        
        logger.info(f"Selected Top {limit} Movers:")
        for rank, c in enumerate(top_n, 1):
            logger.info(f"{rank}. {c['market']} (Score: {c['score']:.2e}, Vol: {c['volatility']:.4f})")
            
        return [c['market'] for c in top_n]

    def get_weekly_gainers(self, limit: int = 10) -> List[str]:
        """
        Get Top N symbols by Weekly Rise (7-day change)
        """
        logger.info("Scanning for Weekly Top Gainers...")
        markets = self.client.get_krw_markets()
        candidates = []
        end = datetime.now()
        # Start enough back to get at least one weekly candle
        start = end - timedelta(days=14) 
        
        # Optimize: Fetch ticker first to filter low volume? 
        # User wants "Trends" -> Top Gainers. Low vol might be risky but is technically a gainer.
        # Let's adhere to "Trends" page which usually sorts by change rate.
        # We can still apply minimum volume blacklist.
        
        for m in markets:
            if m in self.blacklist: continue
            
            # Fetch 1w candle
            # Note: Upbit 'weeks' candle returns current week. 
            # We want current weekly performance.
            try:
                df = self.client.fetch_ohlcv(m, '1w', start, end)
                if df.empty: continue
                
                # Latest candle
                last = df.iloc[-1]
                
                # If the week just started, it might be small data. 
                # Upbit Trend is usually 1W change.
                # Change = (Close - Open) / Open
                change = (last['close'] - last['open']) / last['open']
                
                # Filter inactive?
                if last['volume'] * last['close'] < 100_000_000: # Min 100M KRW weekly vol
                    continue
                    
                candidates.append({
                    'market': m,
                    'change': change,
                    'close': last['close']
                })
            except Exception as e:
                logger.error(f"Weekly fetch failed for {m}: {e}")
                
        # Sort by Change Descending
        candidates.sort(key=lambda x: x['change'], reverse=True)
        top_n = candidates[:limit]
        
        logger.info(f"Selected Weekly Top {limit}:")
        for rank, c in enumerate(top_n, 1):
            logger.info(f"{rank}. {c['market']} (Change: {c['change']:.2%})")
            
        return [c['market'] for c in top_n]

if __name__ == "__main__":
    # Test
    client = UpbitClient()
    selector = UniverseSelector(client)
    print(selector.get_top_movers(5))
