import sys
import os
sys.path.append(os.getcwd())

from infra.upbit_client import UpbitClient

def check_pnl():
    try:
        client = UpbitClient()
        positions = {
            'KRW-BREV': 499.0,  # DIP
            'KRW-IP': 5740.0,   # DIP
            'KRW-AXS': 1733.0   # VBS
        }
        
        print("-" * 50)
        print(f"{'Symbol':<10} {'Entry':<10} {'Current':<10} {'PnL':<8} {'Status'}")
        print("-" * 50)
        
        for sym, entry in positions.items():
            current = client.get_current_price(sym)
            if not current:
                print(f"{sym}: Failed to fetch price")
                continue
                
            pnl_pct = (current - entry) / entry * 100
            
            status = "🔴 LOSS"
            if pnl_pct > 0: status = "🟢 PROFIT"
            
            print(f"{sym:<10} {entry:<10.1f} {current:<10.1f} {pnl_pct:+.2f}%   {status}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_pnl()
