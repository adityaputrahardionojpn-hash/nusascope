from __future__ import annotations
import math
from typing import Any
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP_TITLE = "NusaScope"
BINANCE_BASE = "https://data-api.binance.vision"
ALLOWED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"}
ALLOWED_INTERVALS = {"5m", "15m", "1h", "4h", "1d"}

app = FastAPI(title=APP_TITLE, version="1.0.0", description="Educational crypto market dashboard using public Binance Spot market data.")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


async def fetch_json(path: str, params: dict[str, Any]) -> Any:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BINANCE_BASE}{path}", params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream market-data API returned HTTP {exc.response.status_code}. Try again shortly.")
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Unable to reach public market-data API. Check your connection and try again.")


def ema(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    sma = sum(values[:period]) / period
    out[period - 1] = sma
    alpha = 2 / (period + 1)
    current = sma
    for i in range(period, len(values)):
        current = values[i] * alpha + current * (1 - alpha)
        out[i] = current
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(values[i] - values[i-1], 0) for i in range(1, len(values))]
    losses = [max(values[i-1] - values[i], 0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    def value(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return 100 - (100 / (1 + g / l))
    out[period] = value(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
        out[i] = value(avg_gain, avg_loss)
    return out


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i-period+1:i+1]) / period
    return out


def macd(values: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    e12, e26 = ema(values, 12), ema(values, 26)
    line = [None if a is None or b is None else a-b for a,b in zip(e12,e26)]
    valid = [v for v in line if v is not None]
    signal_valid = ema(valid, 9)
    signal: list[float | None] = [None] * len(values)
    hist: list[float | None] = [None] * len(values)
    j = 0
    for i, v in enumerate(line):
        if v is not None:
            s = signal_valid[j]
            signal[i] = s
            if s is not None:
                hist[i] = v-s
            j += 1
    return line, signal, hist


def stochastic_rsi(rsi_values: list[float | None], period: int = 14) -> tuple[list[float | None], list[float | None]]:
    raw: list[float | None] = [None] * len(rsi_values)
    for i in range(len(rsi_values)):
        window = [v for v in rsi_values[max(0, i-period+1):i+1] if v is not None]
        if len(window) == period and rsi_values[i] is not None:
            lo, hi = min(window), max(window)
            raw[i] = 0.0 if hi == lo else 100 * (rsi_values[i]-lo)/(hi-lo)
    k = [None] * len(raw)
    for i in range(2, len(raw)):
        win = raw[i-2:i+1]
        if all(v is not None for v in win):
            k[i] = sum(win)/3
    d: list[float | None] = [None] * len(raw)
    for i in range(2, len(raw)):
        win = k[i-2:i+1]
        if all(v is not None for v in win):
            d[i] = sum(win)/3
    return k, d


def round_price(v: float, price: float) -> float:
    if price >= 1000: return round(v, 2)
    if price >= 1: return round(v, 4)
    return round(v, 6)


def calculate_analysis(candles: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]
    current = closes[-1]
    e20, e50, e200 = ema(closes,20), ema(closes,50), ema(closes,200)
    rsi_values = rsi(closes)
    m_line, m_signal, m_hist = macd(closes)
    st_k, st_d = stochastic_rsi(rsi_values)
    bb_mid = sma(closes,20)
    bb_upper: list[float | None] = [None] * len(closes)
    bb_lower: list[float | None] = [None] * len(closes)
    for i in range(19, len(closes)):
        win = closes[i-19:i+1]
        mean = sum(win)/20
        sd = math.sqrt(sum((v-mean)**2 for v in win)/20)
        bb_upper[i], bb_lower[i] = mean+2*sd, mean-2*sd

    # Rolling pivot zones: local swing highs/lows in the recent 80 candles.
    recent_highs, recent_lows = highs[-80:], lows[-80:]
    resistance = max(recent_highs)
    support = min(recent_lows)
    # Use robust recent swing levels; zones are informational, not trade instructions.
    recent_low, recent_high = min(lows[-120:]), max(highs[-120:])
    span = max(recent_high - recent_low, 0)
    fib = {f"{level:.3f}": round_price(recent_high - span*level, current) for level in (0.236,0.382,0.5,0.618,0.786)}
    atr_values = []
    for i in range(1, len(candles)):
        atr_values.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
    atr = sum(atr_values[-14:])/min(14,len(atr_values)) if atr_values else current*0.01

    last = lambda seq: seq[-1] if seq else None
    vwap_window = candles[-20:]
    vol_sum = sum(c["volume"] for c in vwap_window)
    vwap = (sum(((c["high"]+c["low"]+c["close"])/3)*c["volume"] for c in vwap_window)/vol_sum) if vol_sum else current
    trend = "Bullish" if e20[-1] and e50[-1] and current > e20[-1] > e50[-1] else ("Bearish" if e20[-1] and e50[-1] and current < e20[-1] < e50[-1] else "Mixed / sideways")
    rsi_now, macd_now, signal_now, hist_now = last(rsi_values), last(m_line), last(m_signal), last(m_hist)
    stoch_now, stoch_d_now = last(st_k), last(st_d)
    # Educational example levels around current price; not a recommendation.
    # These are scenario levels derived from ATR and nearby rolling swing zones.
    entry_low = min(current, support + 0.15*atr)
    entry_high = max(current, support + 0.65*atr)
    if entry_low > entry_high: entry_low, entry_high = entry_high, entry_low
    invalidation = min(support - 0.25*atr, entry_low - 0.8*atr)
    targets = [current + atr*mult for mult in (1.0,1.8,2.6)]
    # Never imply a guaranteed direction: label as illustrative scenario only.
    return {
        "price": current, "change24h": (current/candles[-25]["close"]-1)*100 if len(candles)>25 and candles[-25]["close"] else 0,
        "trend": trend, "ema": {"20": last(e20), "50": last(e50), "200": last(e200)},
        "rsi14": rsi_now, "macd": {"line": macd_now, "signal": signal_now, "histogram": hist_now},
        "stochRsi": {"k": stoch_now, "d": stoch_d_now},
        "bollinger": {"mid": last(bb_mid), "upper": last(bb_upper), "lower": last(bb_lower)},
        "vwap20": vwap, "atr14": atr,
        "support": support, "resistance": resistance, "fibonacci": fib,
        "educationalScenario": {"entryZone": [round_price(entry_low,current), round_price(entry_high,current)],
          "invalidationReference": round_price(invalidation,current),
          "targets": [round_price(v,current) for v in targets],
          "note": "Ilustrasi edukatif berbasis volatilitas dan swing. Bukan rekomendasi trading; jangan gunakan sebagai instruksi transaksi."},
        "candles": candles
    }


@app.get("/api/market")
async def market(symbol: str = Query("BTCUSDT"), interval: str = Query("1h")):
    symbol = symbol.upper()
    if symbol not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol not supported. Choose: {', '.join(sorted(ALLOWED_SYMBOLS))}")
    if interval not in ALLOWED_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Interval not supported. Choose: {', '.join(sorted(ALLOWED_INTERVALS))}")
    raw = await fetch_json("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": 300})
    ticker = await fetch_json("/api/v3/ticker/24hr", {"symbol": symbol})
    candles = [{
        "time": int(row[0] / 1000), "open": float(row[1]), "high": float(row[2]),
        "low": float(row[3]), "close": float(row[4]), "volume": float(row[5]),
        "closeTime": int(row[6] / 1000)
    } for row in raw]
    analysis = calculate_analysis(candles)
    analysis["symbol"] = symbol
    analysis["interval"] = interval
    analysis["ticker24h"] = {
        "priceChangePercent": float(ticker.get("priceChangePercent", 0)),
        "quoteVolume": float(ticker.get("quoteVolume", 0)),
        "highPrice": float(ticker.get("highPrice", 0)),
        "lowPrice": float(ticker.get("lowPrice", 0))
    }
    analysis["dataSource"] = "Binance public Spot market-data API"
    return analysis


@app.get("/api/health")
async def health():
    return {"ok": True, "app": APP_TITLE, "marketData": "public Binance Spot; no API key required"}
