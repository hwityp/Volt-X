"""
VOLTX Performance Analyzer
Parses trade logs and generates detailed performance reports.

Usage:
    python analyze_voltx.py --run-id <RUN_ID>
    python analyze_voltx.py --trades-file reports/trades_<RUN_ID>.csv
"""
import argparse
import pandas as pd
import numpy as np
import os
from datetime import datetime

# Targets
PF_TARGET = 1.5
WINRATE_TARGET_MIN = 0.45
WINRATE_TARGET_MAX = 0.60
WL_TARGET = 1.8

def load_trades(file_path):
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        return pd.DataFrame() # Empty
        
    try:
        df = pd.read_csv(file_path)
        # Ensure correct types
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return pd.DataFrame()

def calculate_metrics(df):
    if df.empty:
        return {}
        
    total_trades = len(df)
    
    # Win/Loss
    wins = df[df['net_pnl_pct'] > 0]
    losses = df[df['net_pnl_pct'] <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_trades if total_trades > 0 else 0
    
    # Financials (Using KRW values if available, else PCT)
    # df has 'gross_pnl_pct', 'net_pnl_pct'. 
    # Also 'size', 'entry_price', 'exit_price', 'fees_slippage'.
    
    # Re-calculate PnL in Value if needed, but PnL % is standard.
    # Let's use Sum of PnL % as a proxy for simpler "Unit" return, 
    # OR calculate actual KRW PnL if size is consistent.
    # User asked for "Gross PnL / Net PnL / Friction".
    # Assuming 'size' is KRW entry size.
    
    # Net PnL Value = size * net_pnl_pct (approx)
    # More precise: (exit_val - entry_val - fees)
    # We have 'net_pnl_pct' already calculated in trader.
    # Let's assume size was roughly constant or use provided columns if possible.
    # Trader logs: cost_basis (size), gross_pnl_pct, net_pnl_pct, fees_slippage (value)
    
    # Recover Net PnL Value
    df['net_pnl_val'] = df['size'] * df['net_pnl_pct']
    df['gross_pnl_val'] = df['size'] * df['gross_pnl_pct']
    
    net_pnl_sum = df['net_pnl_val'].sum()
    gross_pnl_sum = df['gross_pnl_val'].sum()
    friction_sum = df['fees_slippage'].sum()
    
    # PF
    gross_profit = df[df['net_pnl_val'] > 0]['net_pnl_val'].sum()
    gross_loss = abs(df[df['net_pnl_val'] <= 0]['net_pnl_val'].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Averages
    avg_win = wins['net_pnl_pct'].mean() if not wins.empty else 0
    avg_loss = losses['net_pnl_pct'].mean() if not losses.empty else 0
    wl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
    
    # MDD
    # Sort by time
    df = df.sort_values('timestamp')
    df['cum_pnl'] = df['net_pnl_val'].cumsum()
    df['peak'] = df['cum_pnl'].cummax()
    df['drawdown'] = df['cum_pnl'] - df['peak']
    max_drawdown = df['drawdown'].min()
    mdd_pct = (max_drawdown / 10_000_000) * 100 # Assuming 10M start
    
    return {
        "Trades": total_trades,
        "Net_PnL": net_pnl_sum,
        "Friction": friction_sum,
        "Win_Rate": win_rate,
        "PF": pf,
        "Avg_Win": avg_win,
        "Avg_Loss": avg_loss,
        "WL_Ratio": wl_ratio,
        "MDD_Val": max_drawdown,
        "MDD_Pct": mdd_pct
    }

def format_metrics(m, label="Overall"):
    if not m: return f"[{label}] No Trades."
    
    s = f"[{label}]\n"
    s += f"  Trades: {m['Trades']} | Win Rate: {m['Win_Rate']:.1%}\n"
    s += f"  Net PnL: {m['Net_PnL']:,.0f} KRW | PF: {m['PF']:.2f}\n"
    s += f"  Avg Win: {m['Avg_Win']:.2%} | Avg Loss: {m['Avg_Loss']:.2%} | W/L: {m['WL_Ratio']:.2f}\n"
    return s

def tuning_advice(m, hours_run):
    if not m: return "No Trades."
    
    suggestions = []
    
    # Signal Frequency
    trades_per_hour = m['Trades'] / hours_run if hours_run > 0 else 0
    if trades_per_hour < 3:
        suggestions.append(f"Low Signal Frequency ({trades_per_hour:.1f}/h < 3). Relax conditions or Universe filter.")
    elif trades_per_hour > 10:
        suggestions.append(f"High Signal Frequency ({trades_per_hour:.1f}/h > 10). Tighten Scanner/Strategy logic.")
    else:
        suggestions.append("Signal Frequency OK.")
        
    # Performance Targets
    if m['PF'] < PF_TARGET:
        suggestions.append(f"PF Low ({m['PF']:.2f} < {PF_TARGET}). Strategy is losing money or inefficient.")
        if m['WL_Ratio'] < WL_TARGET:
             suggestions.append(" -> W/L Ratio is poor. Consider tighter Stop Loss or wider Take Profit.")
        if m['Win_Rate'] < WINRATE_TARGET_MIN:
             suggestions.append(" -> Win Rate is poor. Filter entries more strictly (RSI < 30? Drop > 2%?).")
             
    elif m['Win_Rate'] > WINRATE_TARGET_MAX and m['WL_Ratio'] < 1.0:
        suggestions.append("High Win Rate but Low Payoff. You are scalping too small. Let profits run.")
        
    if not suggestions:
        suggestions.append("Performance meets baseline targets.")
        
    return suggestions

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=str)
    parser.add_argument("--trades-file", type=str)
    args = parser.parse_args()
    
    path = ""
    run_id = args.run_id or "unknown"
    if args.trades_file:
        path = args.trades_file
    elif args.run_id:
        path = f"reports/trades_{args.run_id}.csv"
        
    print(f"Analyzing: {path}")
    df = load_trades(path)
    if df.empty:
        print("No data found.")
        return

    # Calculate run duration roughly
    start_time = df['timestamp'].min()
    end_time = df['timestamp'].max()
    duration = (end_time - start_time).total_seconds() / 3600
    if duration < 0.1: duration = 0.1 # avoid div/0
    
    # metrics
    overall = calculate_metrics(df)
    
    # Grouped
    by_strategy = {g: calculate_metrics(d) for g, d in df.groupby('strategy')}
    by_tier = {g: calculate_metrics(d) for g, d in df.groupby('tier')}
    by_regime = {g: calculate_metrics(d) for g, d in df.groupby('regime')}
    
    # Generate Output
    report_lines = []
    report_lines.append(f"=== VOLT-X Performance Report ({run_id}) ===")
    report_lines.append(f"Duration: {duration:.1f} hours | Start: {start_time}")
    report_lines.append("-" * 40)
    
    report_lines.append(format_metrics(overall, "OVERALL"))
    report_lines.append("-" * 40)
    
    report_lines.append(">>> BY STRATEGY")
    for k, v in by_strategy.items():
        report_lines.append(format_metrics(v, k))
        
    report_lines.append(">>> BY REGIME")
    for k, v in by_regime.items():
        report_lines.append(format_metrics(v, k))

    report_lines.append("-" * 40)
    report_lines.append("=== KEY SUMMARY & TUNING ADVICE ===")
    
    advice = tuning_advice(overall, duration)
    for line in advice:
        report_lines.append(f"- {line}")
        
    # Print to Console
    full_text = "\n".join(report_lines)
    print(full_text)
    
    # Save to File
    out_path = f"reports/voltx_summary_{run_id}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"\nReport saved to {out_path}")

if __name__ == "__main__":
    main()
