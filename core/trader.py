"""
VOLTX_Trader Module
Handles Order Execution and Position Management.
Supports Dry-Run (Paper) and Live modes.
"""
from typing import Dict, List, Optional
from datetime import datetime
import uuid

from infra.logger import logger
from infra.upbit_client import UpbitClient
from core.risk import RiskManager
from core.strategy import Signal

class Position:
    def __init__(self, symbol, entry_price, quantity, strategy_name, regime):
        self.symbol = symbol
        self.entry_price = entry_price
        self.quantity = quantity
        self.strategy_name = strategy_name
        self.entry_regime = regime
        self.entry_time = datetime.now()
        self.highest_price = entry_price
        self.sl_price = 0.0
        self.tp_price = 0.0

class VoltxTrader:
    def __init__(self, client: UpbitClient, risk_manager: RiskManager, mode: str = "paper", run_id: Optional[str] = None):
        self.client = client
        self.risk = risk_manager
        self.mode = mode # 'paper' or 'live'
        self.run_id = run_id
        
        self.positions: Dict[str, Position] = {}
        self.paper_balance = 10_000_000.0 # 10M KRW start
        
        # Initialize CSV Logger for trades
        # We pass report_dir="./reports" to match user request
        from infra.logger import get_csv_logger
        self.trade_csv = get_csv_logger(run_id=run_id, report_dir="./reports")

    def get_balance(self) -> float:
        if self.mode == "paper":
            return self.paper_balance
        else:
            return self.client.get_balance("KRW")

    def execute_signal(self, signal: Signal, current_price: float, regime: str, tier: str = "L1", strategy_name: str = "Unknown") -> bool:
        """
        Execute a valid signal.
        """
        if signal.action == "BUY":
            return self._entry(signal, current_price, regime, tier, strategy_name)
        elif signal.action == "SELL" or signal.action == "SL" or signal.action == "TP":
            return self._exit(signal, current_price, signal)
        return False

    def _entry(self, signal: Signal, price: float, regime: str, tier: str, strategy_name: str) -> bool:
        if signal.symbol in self.positions:
            return False
            
        # 1. Calculate Size
        balance = self.get_balance()
        size_krw = self.risk.calculate_position_size(balance, regime, tier)
        
        if size_krw <= 0:
            logger.warning(f"[SKIP] {signal.symbol}: Risk Manager returned 0 size (Halted or too small).")
            return False
            
        quantity = size_krw / price
        
        # 2. Execute
        if self.mode == "live":
            # Safety Check
            if size_krw > 20000: 
                 logger.warning("Live Order capped at 20k KRW for safety.")
                 # size_krw = 20000 
                 
            try:
                # Market Buy by Amount (price)
                resp = self.client.place_order(signal.symbol, 'bid', price=int(size_krw), ord_type='price') 
                exec_price = price 
            except Exception as e:
                logger.error(f"Live Buy Failed: {e}")
                return False
        else:
            self.paper_balance -= size_krw
            exec_price = price
            logger.info(f"[PAPER BUY] {signal.symbol} Qty:{quantity:.4f} Price:{exec_price} Cost:{size_krw:.0f} | {signal.reason}")

        # 3. Record Position
        pos = Position(signal.symbol, exec_price, quantity, strategy_name, regime)
        pos.sl_price = exec_price * 0.985 
        
        self.positions[signal.symbol] = pos
        return True

    def _exit(self, signal: Signal, price: float, orig_signal: Signal) -> bool:
        if signal.symbol not in self.positions:
            return False
            
        pos = self.positions[signal.symbol]
        qty = pos.quantity
        exit_qty = qty
        
        if self.mode == "live":
            try:
                # Market Sell
                self.client.place_order(signal.symbol, 'ask', volume=exit_qty, ord_type='market')
            except Exception as e:
                logger.error(f"Live Sell Failed: {e}")
                return False
        else:
            proceeds = exit_qty * price
            fee = proceeds * 0.0005 # 0.05% Check user request, usually 0.05% per side. 
            # Slippage simulated? User said "Friction(fees+slippage)". 
            # Let's add simulated slippage 0.1% (+ 0.05% fee) -> 0.15% total friction per side?
            # User request: "gross_pnl, net_pnl, fees/slippage"
            
            slippage_rate = 0.001 # 0.1%
            real_exit_price = price * (1 - slippage_rate) # Sell Lower
            proceeds_real = exit_qty * real_exit_price
            
            fee_amt = proceeds_real * 0.0005
            net_proceeds = proceeds_real - fee_amt
            
            self.paper_balance += net_proceeds
            
            # PnL Calc
            cost_basis = pos.entry_price * pos.quantity
            gross_pnl = (exit_qty * price) - cost_basis # Pure price diff
            net_pnl = net_proceeds - cost_basis
            
            gross_pnl_pct = gross_pnl / cost_basis
            net_pnl_pct = net_pnl / cost_basis
            
            friction = (exit_qty * price) - net_proceeds # Total diff between theoretical mid-price exit and net cash
            
            logger.info(f"[PAPER SELL] {signal.symbol} Price:{price} NetPnL:{net_pnl:.0f} ({net_pnl_pct:.2%}) | {orig_signal.reason}")
            
            # CSV Log
            # timestamp,symbol,strategy,tier,regime,side,size,entry_price,exit_price,gross_pnl_pct,net_pnl_pct,fees_slippage,reason
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"{now_str},{signal.symbol},{pos.strategy_name},L1,{pos.entry_regime},long,{cost_basis:.0f},{pos.entry_price},{price},{gross_pnl_pct:.4f},{net_pnl_pct:.4f},{friction:.4f},{orig_signal.reason}"
            self.trade_csv.info(log_line)
            
            # Update Risk Manager
            self.risk.update_pnl(net_pnl_pct)
            
        del self.positions[signal.symbol]
        return True

    def update_positions(self, current_prices: Dict[str, float]):
        """
        Update position stats (highest price, etc) for trailing stops.
        """
        for sym, pos in self.positions.items():
            if sym in current_prices:
                price = current_prices[sym]
                if price > pos.highest_price:
                    pos.highest_price = price
