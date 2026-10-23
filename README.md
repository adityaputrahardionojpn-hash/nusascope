# NusaScope — Real-time educational market dashboard

NusaScope is a small FastAPI + HTML/JavaScript project that retrieves **public Binance Spot market data** and calculates common technical indicators. It does not place orders, connect to accounts, or require API credentials.

## Features

- Live market data on refresh/polling from Binance public REST endpoints
- BTC, ETH, SOL, BNB, XRP, ADA, DOGE pairs against USDT
- Timeframes: 5m, 15m, 1h, 4h, 1d
- Candlestick chart (rendered in browser)
- EMA 20/50/200, RSI(14), MACD, Stochastic RSI, Bollinger Bands, VWAP, ATR
- Rolling support/resistance estimates and Fibonacci retracement
- Educational scenario levels derived from recent swings and ATR
- Mobile-friendly dark dashboard

## Run locally

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

The dashboard polls the backend every 30 seconds. Public API availability, geographic restrictions, and network conditions can affect access. The server proxies the data request, which also avoids browser CORS issues.

## Important notes

- Public market data is retrieved from `https://data-api.binance.vision`, which Binance documents for public market-data-only requests.
- This is a prototype, not a production trading system. It never places orders and does not ask for exchange API keys.
- Support/resistance is estimated from recent rolling highs/lows. Fibonacci uses the highest high and lowest low from recent candles. Those choices are subjective and may not match another analyst's chart.
- Entry/target/invalidation fields are **educational scenario levels** derived from current price, ATR, and recent swing data. They are not personalized financial advice, not a prediction, and not a promise of performance. Verify independently; do not make decisions solely from indicators.
- Current candle can still be forming. Indicator values can change until candle close.
- For production deployment, add caching, rate-limit handling, monitoring, tests, and stricter input validation.


## Deploy to Render

This folder is arranged with `app.py` and `requirements.txt` at the repository root. Connect a Git repository containing these files to Render as a Python Web Service. Build command: `pip install -r requirements.txt`. Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`. A `render.yaml` Blueprint file is also included.
