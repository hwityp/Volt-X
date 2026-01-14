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

---

# 🇰🇷 VOLT-X: 업비트 급등주 자동매매 봇

VOLT-X는 업비트 원화 마켓의 변동성 높은 "급등주(Hot Symbols)"를 타겟으로 하는 자동매매 시스템입니다. **변동성 돌파(추세 추종)** 전략과 **눌림목(평균 회귀)** 전략을 결합하여 운영됩니다.

## 🚀 전략 아키텍처 (Strategy Architecture)

매 시간 갱신되는 거래량 상위 10개 종목(Hot Symbols)을 감시하며, 두 가지 전략을 병렬로 수행합니다.

### 1. VBS 최적화 (Volatility Breakout Strategy) v3
*가짜 반등을 걸러내고, 강력한 추세가 터질 때만 올라타는 추세 추종 전략입니다.*

*   **타겟**: 1시간마다 선정되는 거래량/상승률 상위 10개 종목.
*   **진입 조건 (Entry Logic)**:
    *   **돌파**: 현재가 > `당일 시가 + (전일 고가 - 전일 저가) * k`
    *   **변동성 계수(k)**: **0.7** (높은 진입 장벽으로 노이즈 필터링).
    *   **추세 필터**: 3분봉 기준 주가가 **120이평선(SMA)** 위에 있어야 함 (정배열 조건).
*   **청산 조건 (Exit Logic)**:
    *   **트들링 스탑 (Trailing Stop)**: 최고점 대비 **-2.0%** 하락 시 전량 매도. (상승 시 계속 따라가며 수익 극대화, +5% 제한 없음)
    *   **손절 (Stop Loss)**: 진입가 대비 **-1.5%** 하락 시 칼손절.
*   **추가 조건**:
    *   돌파 가격보다 3% 이상 이미 오른 경우 추격 매수 금지 (뇌동매매 방지).
    *   RSI 75 이상(과매수)일 경우 진입 보류.

### 2. DIP 전략 (눌림목 매매)
*상승 추세 중 일시적인 하락(조정)을 노리는 역추세 전략입니다.*

*   **진입 조건 (Entry Logic)**:
    *   **하락폭**: 고점 대비 **1.5% ~ 2.5%** 급락 발생 시 (시장 상황에 따라 유동적).
    *   **과매도**: RSI가 40~50 이하로 떨어짐.
    *   **지지선**: 볼린저 밴드 하단 터치.
    *   **확인**: 양봉(반등 캔들) 출현 시 진입.
*   **청산 조건 (Exit Logic)**:
    *   **익절 (Take Profit)**: **+5.0%** 고정.
    *   **손절 (Stop Loss)**: **-1.5%** 고정.

## ⚙️ 시스템 주요 기능

1.  **동적 유니버스 (Dynamic Universe)**:
    *   **1시간 주기**로 급등주 리스트 10개를 새로 선정합니다.
    *   시장의 자금 흐름이 바뀌면 봇의 타겟도 즉시 변경됩니다.
2.  **리스크 관리 (Risk Management)**:
    *   **상승장(BULL)**: 공격적 비중, 여유로운 필터.
    *   **하락/횡보장(BEAR/FLAT)**: 수비적 비중, 엄격한 진입 요건 적용.
    *   **서킷 브레이커**: 연속 5회 손실 또는 일일 손실 한도(-3%) 도달 시 당일 거래 자동 중단.
3.  **실시간 모니터링**:
    *   순간 체결량 급증(Volume Spike) 감지.
    *   거래량 과열(Climax) 및 소진(Exhaustion) 패턴 분석.
