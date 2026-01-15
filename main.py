"""
VOLTX Main Entry Point
"""
import sys
import time
import argparse
from datetime import datetime, timedelta
from typing import List

from infra.logger import logger
from infra.upbit_client import UpbitClient

# Load .env manually to avoid dependency
def load_env():
    import os
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"): continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip()

from core.universe import UniverseSelector
from core.regime import RegimeAnalyzer
from core.scanner import VolumeScanner
from core.risk import RiskManager
from core.strategy import DipStrategy, VolatilityBreakoutStrategy
from core.trader import VoltxTrader

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["dry-run", "live"], default="dry-run")
    parser.add_argument("--run-id", type=str, help="Custom Run ID for logs and reports", default=None)
    args = parser.parse_args()
    
    # Setup Logger with Run ID
    import logging
    # Reset handlers to apply run_id filename
    root_val = logging.getLogger("voltx")
    if root_val.handlers:
        for h in root_val.handlers:
            root_val.removeHandler(h)
            
    from infra.logger import setup_logger
    logger = setup_logger(run_id=args.run_id)
    
    logger.info(f"Starting VOLT-X in [{args.mode.upper()}] mode | Run ID: {args.run_id}")
    load_env()
    
    # 1. Initialize Modules
    client = UpbitClient()
    
    universe = UniverseSelector(client)
    regime_analyzer = RegimeAnalyzer(client)
    scanner = VolumeScanner(client)
    risk_manager = RiskManager()
    
    trader = VoltxTrader(client, risk_manager, mode="paper" if args.mode == "dry-run" else "live", run_id=args.run_id)
    
    strategies = [
        DipStrategy(client),
        VolatilityBreakoutStrategy(client)
    ]
    
    # State Variables
    hot_symbols: List[str] = []
    current_regime = "FLAT"
    last_universe_update = datetime.min
    last_universe_update = datetime.min
    last_regime_update = datetime.min
    last_sell_times = {} # Track last sell time for cooldown
    
    # Loop
    try:
        while True:
            now = datetime.now()
            
            # 2. Update Universe (Hourly)
            if not hot_symbols or (now - last_universe_update).total_seconds() > 3600:
                logger.info("Updating Universe...")
                hot_symbols = universe.get_top_movers(limit=10)
                last_universe_update = now
                logger.info(f"Hot Symbols: {hot_symbols}")
                
            # 3. Update Regime (Every 1 hour)
            if (now - last_regime_update).total_seconds() > 3600:
                logger.info("Updating Regime...")
                regime_info = regime_analyzer.analyze()
                current_regime = regime_info['type']
                last_regime_update = now
                logger.info(f"Current Regime: {current_regime}")
                
            # 4. Scanner Loop
            # Scan symbols for spikes/climaxes
            scanner_results = scanner.scan(hot_symbols)
            # Log significant Scanner Events
            for sym, status in scanner_results.items():
                if status != "NORMAL":
                     # This might be too noisy if 'TREND_ACTIVE' persists. 
                     # Only log changes? For now, debug log is fine.
                     pass 
            
            # 5. Strategy Loop
            current_prices = {} 
            
            for symbol in hot_symbols:
                scanner_status = scanner_results.get(symbol, "NORMAL")
                
                start_win = now - timedelta(minutes=100)
                df_3m = client.fetch_ohlcv(symbol, '3m', start_win, now)
                df_15m = client.fetch_ohlcv(symbol, '15m', start_win, now)
                
                # Pass to Strategies
                for strategy in strategies:
                    signal = strategy.check_signal(symbol, df_3m, df_15m, current_regime, scanner_status)
                    if signal:
                        logger.info(f"Signal Generated: {signal.action} {symbol} ({signal.reason})")
                        
                        # Execute
                        if signal.action == "BUY":
                            # Cooldown Check: 1 Hour
                            if symbol in last_sell_times:
                                last_sell = last_sell_times[symbol]
                                if (now - last_sell).total_seconds() < 3600:
                                    logger.info(f"Signal Blocked: Cooldown for {symbol} (Last Sell: {last_sell.strftime('%H:%M')})")
                                    continue

                            st_type = "VBS" if isinstance(strategy, VolatilityBreakoutStrategy) else "DIP"
                            strategy_name = f"VOLTX_{st_type}" # e.g. VOLTX_DIP
                            
                            if risk_manager.check_entry_allowed(current_regime, st_type):
                                trader.execute_signal(signal, signal.price, current_regime, "L1", strategy_name)
                            else:
                                if risk_manager.is_trading_halted:
                                    logger.info(f"Signal blocked: Trading HALTED (Daily Limit/Consec Loss)")
                                else:
                                    logger.info(f"Signal blocked by Risk Manager ({current_regime} vs {st_type})")

            # 6. Manage Open Positions
            held_symbols = list(trader.positions.keys())
            if held_symbols:
                 # Fetch current prices
                 current_price_map = {}
                 for s in held_symbols:
                     p = client.get_current_price(s)
                     current_price_map[s] = p
                     
                     pos = trader.positions[s]
                     pnl_pct = (p - pos.entry_price) / pos.entry_price
                     # 4. Exit Logic
                     # Hard SL (Global) - Safety Net
                     if pnl_pct < -0.015:
                         logger.info(f"Hard SL Triggered for {s} (PnL: {pnl_pct:.2%})")
                         sl_sig = type("Signal", (), {"action": "SL", "symbol": s, "price": p, "reason": "Hard SL"})
                         if trader.execute_signal(sl_sig, p, current_regime, "L1", pos.strategy_name):
                             last_sell_times[s] = datetime.now()
                     
                     else:
                         # Strategy Specific Exit
                         if pos.strategy_name == "VOLTX_VBS":
                             # VBS: Trailing Stop (Highest - 3%) - Loosened from 2%
                             # Note: pos.highest_price is updated below in trader.update_positions
                             ts_price = pos.highest_price * 0.97
                             if p < ts_price:
                                 logger.info(f"Trailing Stop Triggered for {s} (High: {pos.highest_price}, Now: {p})")
                                 ts_sig = type("Signal", (), {"action": "TP", "symbol": s, "price": p, "reason": f"Trailing Stop (High {pos.highest_price})"})
                                 if trader.execute_signal(ts_sig, p, current_regime, "L1", pos.strategy_name):
                                     last_sell_times[s] = datetime.now()
                         
                         else:
                             # DIP / Others: Fixed TP (+5%)
                             if pnl_pct > 0.05:
                                 logger.info(f"TP Triggered for {s} (PnL: {pnl_pct:.2%})")
                                 tp_sig = type("Signal", (), {"action": "TP", "symbol": s, "price": p, "reason": "Fixed TP"})
                                 if trader.execute_signal(tp_sig, p, current_regime, "L1", pos.strategy_name):
                                     last_sell_times[s] = datetime.now()

                 trader.update_positions(current_price_map)

            # Sleep
            # Console Heartbeat (every minute)
            pos_count = len(trader.positions)
            print(f"[VOLT-X] {now.strftime('%Y-%m-%d %H:%M:%S')} | Regime: {current_regime} | Positions: {pos_count} | Hot: {len(hot_symbols)}", flush=True)
            
            time.sleep(60) # 1 minute loop
            
    except KeyboardInterrupt:
        print("\nStopping VOLT-X...")
        logger.info("Stopping VOLT-X...")
    except Exception as e:
        logger.error(f"Critical Error: {e}", exc_info=True)
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()
