# VOLT-X: High-Frequency Crypto Trading Bot (Upbit)

VOLT-X is an automated trading system designed for the Upbit exchange, focusing on high-volatility "Hot Symbols". It employs a hybrid approach combining **Volatility Breakout (Trend Following)** and **Mean Reversion (Dip Buying)** strategies.

## 🚀 Strategy Architecture

The bot monitors the Top 10 most active coins (updated hourly) and applies two distinct strategies in parallel.

### 1. VBS Optimized (Volatility Breakout Strategy) v3
*A trend-following strategy designed to capture massive pumps while filtering out false breakouts.*

*   **Target Asset**: Top 10 Volume/Price Surge Coins (Hourly Selection).
*   **Entry Logic**:
    *   **Breakout**: Current Price > `Open + (Previous Day Range * k)`
    *   **Factor (k)**: **0.7** (Strict entry to reduce noise).
    *   **Trend Filter**: Price must be above the **120-period SMA** on the 3-minute chart (Uptrend Confirmation).
*   **Exit Logic**:
    *   **Trailing Stop**: Sell if price drops **-2.0%** from the highest price reached during the trade. (No fixed Take Profit limit, allowing for unlimited upside).
    *   **Hard Stop Loss**: **-1.5%** (Safety net).
*   **Conditions**:
    *   Do not chase if price is already > 3% above target (Anti-FOMO).
    *   RSI < 75 (Avoid extreme overbought).

### 2. Dip Strategy (Mean Reversion)
*A counter-trend strategy purchasing high-quality assets during short-term pullbacks.*

*   **Entry Logic**:
    *   **Drop**: Price dropped > **1.5% ~ 2.5%** from 20-candle high (Regime dependent).
    *   **RSI**: Deep oversold condition (RSI < 40 ~ 50).
    *   **Support**: Price touches or breaks **Bollinger Band Lower Band**.
    *   **Confirmation**: Reversal candle (Hammer/Green) detected.
*   **Exit Logic**:
    *   **Take Profit**: Fixed **+5.0%**.
    *   **Stop Loss**: Fixed **-1.5%**.

## ⚙️ System Features

1.  **Dynamic Universe (Hourly)**:
    *   Refreshes the target list (Hot Symbols) every **60 minutes**.
    *   Continuously adapts to shifting market money flow.
2.  **Risk Management (Regime Adaptive)**:
    *   **BULL Market**: Aggressive sizing, looser filters.
    *   **BEAR/FLAT Market**: Defensive sizing, stricter entry filters.
    *   **Circuit Breaker**: Trading halted after 5 consecutive losses or Daily Loss Limit (-3%).
3.  **Real-Time Monitoring**:
    *   Volume Spike Detection (Relative Volume > 3.0x).
    *   Volume Climax / Exhaustion logic.

---
*Developed for KRW-Market on Upbit. Use at your own risk.*
