from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import math
import numpy as np
import pandas as pd

MIN_BARS = 35
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
STRUCTURE_LOOKBACK = 6
SR_LOOKBACK = 20
SR_ATR_MULTIPLIER = 0.35
MIN_BODY_ATR = 0.18
MAX_BODY_ATR = 1.80
CALL_RSI_MIN = 48.0
CALL_RSI_MAX = 72.0
PUT_RSI_MIN = 28.0
PUT_RSI_MAX = 52.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    out = df.copy()
    out.rename(columns={
        "max": "high", "min": "low",
        "Open": "open", "High": "high",
        "Low": "low", "Close": "close",
    }, inplace=True)
    required = ["open", "high", "low", "close"]
    if any(c not in out.columns for c in required):
        return pd.DataFrame()
    for c in required:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "from" in out.columns:
        out["from"] = pd.to_numeric(out["from"], errors="coerce")
        out.dropna(subset=["from"], inplace=True)
        out.sort_values("from", inplace=True)
    out.dropna(subset=required, inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = _normalize(df)
    if out.empty:
        return out
    close, high, low = out["close"], out["high"], out["low"]
    out["ema9"] = close.ewm(span=EMA_FAST, adjust=False).mean()
    out["ema21"] = close.ewm(span=EMA_MID, adjust=False).mean()
    out["ema50"] = close.ewm(span=EMA_SLOW, adjust=False).mean()

    prev = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low - prev).abs()
    ], axis=1).max(axis=1)
    out["atr"] = tr.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, adjust=False,
                        min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, adjust=False,
                        min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))
    out.loc[(avg_loss == 0) & (avg_gain > 0), "rsi"] = 100.0
    out.loc[(avg_gain == 0) & (avg_loss > 0), "rsi"] = 0.0
    return out


def candle_direction(candle: pd.Series) -> str:
    o, c = _safe_float(candle.get("open")), _safe_float(candle.get("close"))
    return "bull" if c > o else "bear" if c < o else "neutral"


def candle_metrics(candle: pd.Series) -> Dict[str, float]:
    o = _safe_float(candle.get("open"))
    h = _safe_float(candle.get("high"))
    l = _safe_float(candle.get("low"))
    c = _safe_float(candle.get("close"))
    rng = max(h - l, 0.0)
    body = abs(c - o)
    return {
        "range": rng,
        "body": body,
        "upper_wick": max(h - max(o, c), 0.0),
        "lower_wick": max(min(o, c) - l, 0.0),
        "body_ratio": body / rng if rng > 0 else 0.0,
    }


def detect_structure(df: pd.DataFrame, lookback: int = STRUCTURE_LOOKBACK) -> str:
    if df is None or len(df) < lookback:
        return "range"
    x = df.tail(lookback)
    highs = x["high"].to_numpy(float)
    lows = x["low"].to_numpy(float)
    hh = hl = lh = ll = 0
    for i in range(1, len(x)):
        if highs[i] > highs[i - 1]: hh += 1
        elif highs[i] < highs[i - 1]: lh += 1
        if lows[i] > lows[i - 1]: hl += 1
        elif lows[i] < lows[i - 1]: ll += 1
    if hh >= 3 and hl >= 3:
        return "bullish"
    if lh >= 3 and ll >= 3:
        return "bearish"
    return "range"


def structure_score(df: pd.DataFrame) -> int:
    if df is None or len(df) < STRUCTURE_LOOKBACK:
        return 0
    x = df.tail(STRUCTURE_LOOKBACK)
    highs, lows = x["high"].to_numpy(float), x["low"].to_numpy(float)
    bull = bear = 0
    for i in range(1, len(x)):
        if highs[i] > highs[i - 1] and lows[i] > lows[i - 1]:
            bull += 1
        if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
            bear += 1
    return min(5, max(bull, bear))


def is_near_sr(df: pd.DataFrame, confirmation_index: int = -1,
               tolerance: Optional[float] = None) -> bool:
    if df is None or len(df) < 6:
        return True
    pos = confirmation_index if confirmation_index >= 0 else len(df) + confirmation_index
    if pos < 1 or pos >= len(df):
        return True
    historical = df.iloc[:pos].tail(SR_LOOKBACK)
    candle = df.iloc[pos]
    if historical.empty:
        return True
    close = _safe_float(candle.get("close"))
    atr = _safe_float(candle.get("atr"))
    support = _safe_float(historical["low"].min())
    resistance = _safe_float(historical["high"].max())
    if tolerance is None:
        tolerance = atr * SR_ATR_MULTIPLIER
    if tolerance <= 0:
        tolerance = max(abs(close) * 0.00015, 1e-8)
    return (abs(close - support) <= tolerance or
            abs(resistance - close) <= tolerance)


def breakout_context(df: pd.DataFrame, confirmation_index: int = -1) -> Dict[str, bool]:
    result = {
        "bull_breakout": False, "bear_breakout": False,
        "false_bull_breakout": False, "false_bear_breakout": False,
    }
    if df is None or len(df) < 5:
        return result
    pos = confirmation_index if confirmation_index >= 0 else len(df) + confirmation_index
    if pos < 4 or pos >= len(df):
        return result
    x = df.iloc[pos - 4:pos + 1]
    current, previous = x.iloc[-1], x.iloc[:-1]
    ph = _safe_float(previous["high"].max())
    pl = _safe_float(previous["low"].min())
    h, l, c = map(_safe_float, [current["high"], current["low"], current["close"]])
    result["bull_breakout"] = c > ph
    result["bear_breakout"] = c < pl
    result["false_bull_breakout"] = h > ph and c <= ph
    result["false_bear_breakout"] = l < pl and c >= pl
    return result


def _checks(df: pd.DataFrame, pos: int, direction: str) -> Tuple[bool, int, list[str]]:
    last = df.iloc[pos]
    history = df.iloc[:pos + 1]
    structure = detect_structure(history)
    s_score = structure_score(history)
    ema9, ema21, ema50 = (_safe_float(last.get(k)) for k in ("ema9", "ema21", "ema50"))
    close = _safe_float(last.get("close"))
    rsi = _safe_float(last.get("rsi"), 50.0)
    atr = _safe_float(last.get("atr"))
    metrics = candle_metrics(last)
    candle = candle_direction(last)
    points = 0
    reasons: list[str] = []

    if direction == "call":
        if structure == "bullish":
            points += 2; reasons.append("estructura alcista")
        else: reasons.append("estructura no alcista")
        if ema9 > ema21 > ema50 and close > ema9:
            points += 2; reasons.append("EMA 9>21>50")
        else: reasons.append("EMA no alineada")
        if candle == "bull":
            points += 1; reasons.append("vela alcista")
        else: reasons.append("vela no alcista")
        if CALL_RSI_MIN <= rsi <= CALL_RSI_MAX:
            points += 1; reasons.append(f"RSI {rsi:.1f}")
        else: reasons.append(f"RSI fuera {rsi:.1f}")
        rsi_ok = CALL_RSI_MIN <= rsi <= CALL_RSI_MAX
        trend_ok = structure == "bullish" and ema9 > ema21 > ema50 and close > ema9
        candle_ok = candle == "bull"
        false_break = breakout_context(df, pos)["false_bull_breakout"]
    else:
        if structure == "bearish":
            points += 2; reasons.append("estructura bajista")
        else: reasons.append("estructura no bajista")
        if ema9 < ema21 < ema50 and close < ema9:
            points += 2; reasons.append("EMA 9<21<50")
        else: reasons.append("EMA no alineada")
        if candle == "bear":
            points += 1; reasons.append("vela bajista")
        else: reasons.append("vela no bajista")
        if PUT_RSI_MIN <= rsi <= PUT_RSI_MAX:
            points += 1; reasons.append(f"RSI {rsi:.1f}")
        else: reasons.append(f"RSI fuera {rsi:.1f}")
        rsi_ok = PUT_RSI_MIN <= rsi <= PUT_RSI_MAX
        trend_ok = structure == "bearish" and ema9 < ema21 < ema50 and close < ema9
        candle_ok = candle == "bear"
        false_break = breakout_context(df, pos)["false_bear_breakout"]

    if atr > 0:
        body_atr = metrics["body"] / atr
        if MIN_BODY_ATR <= body_atr <= MAX_BODY_ATR:
            points += 1; reasons.append("cuerpo válido")
        else: reasons.append("cuerpo extremo")
    else:
        body_atr = 0.0
        reasons.append("ATR inválido")

    if s_score >= 4:
        points += 1
    reasons.append(f"estructura {s_score}/5")

    near_sr = is_near_sr(df, pos)
    if not near_sr:
        points += 1; reasons.append("ubicación libre")
    else: reasons.append("cerca de S/R")

    br = breakout_context(df, pos)
    if false_break:
        points = 0
        reasons.append("falsa ruptura " + ("alcista" if direction == "call" else "bajista"))
    elif br["bull_breakout" if direction == "call" else "bear_breakout"]:
        reasons.append("ruptura " + ("alcista" if direction == "call" else "bajista"))

    valid = (
        points >= 8 and trend_ok and candle_ok and rsi_ok and
        not near_sr and not false_break and atr > 0 and
        MIN_BODY_ATR <= body_atr <= MAX_BODY_ATR
    )
    return valid, min(points, 10), reasons


def analyze_market(df: pd.DataFrame, confirmation_index: int = -1) -> Dict[str, Any]:
    neutral = {
        "signal": None, "score": 0, "reason": "sin señal",
        "structure": "range", "structure_score": 0,
        "candle": "neutral", "rsi": 0.0, "atr": 0.0,
        "confirmation_index": confirmation_index,
    }
    clean = _normalize(df)
    if clean.empty:
        neutral["reason"] = "dataframe vacío"
        return neutral
    pos = confirmation_index if confirmation_index >= 0 else len(clean) + confirmation_index
    if pos < 0 or pos >= len(clean):
        neutral["reason"] = "índice de confirmación inválido"
        return neutral
    if pos + 1 < MIN_BARS:
        neutral["reason"] = f"faltan velas: {pos + 1}/{MIN_BARS}"
        return neutral

    # SOLO datos hasta N. Nunca se usa N+1 para construir indicadores.
    data = add_indicators(clean.iloc[:pos + 1])
    if len(data) < MIN_BARS:
        neutral["reason"] = "indicadores insuficientes"
        return neutral

    p = len(data) - 1
    last = data.iloc[p]
    atr = _safe_float(last.get("atr"))
    rsi = _safe_float(last.get("rsi"), 50.0)
    if atr <= 0 or not math.isfinite(atr):
        neutral["reason"] = "ATR no disponible"
        return neutral
    if not math.isfinite(rsi):
        neutral["reason"] = "RSI no disponible"
        return neutral

    structure = detect_structure(data)
    ss = structure_score(data)
    candle = candle_direction(last)
    call_ok, call_score, call_reasons = _checks(data, p, "call")
    put_ok, put_score, put_reasons = _checks(data, p, "put")

    if call_ok and put_ok:
        return {**neutral, "reason": "señales contradictorias",
                "structure": structure, "structure_score": ss,
                "candle": candle, "rsi": rsi, "atr": atr}
    if call_ok:
        return {"signal": "call", "score": call_score,
                "reason": "CALL continuidad | " + ", ".join(call_reasons),
                "structure": structure, "structure_score": ss,
                "candle": candle, "rsi": rsi, "atr": atr,
                "confirmation_index": confirmation_index}
    if put_ok:
        return {"signal": "put", "score": put_score,
                "reason": "PUT continuidad | " + ", ".join(put_reasons),
                "structure": structure, "structure_score": ss,
                "candle": candle, "rsi": rsi, "atr": atr,
                "confirmation_index": confirmation_index}

    best_score = max(call_score, put_score)
    side = "CALL" if call_score >= put_score else "PUT"
    reasons = call_reasons if call_score >= put_score else put_reasons
    return {**neutral, "score": best_score,
            "reason": f"sin confirmación {side} | " + ", ".join(reasons),
            "structure": structure, "structure_score": ss,
            "candle": candle, "rsi": rsi, "atr": atr}


def get_signal(df: pd.DataFrame) -> Optional[str]:
    return analyze_market(df, confirmation_index=-1).get("signal")


def signal(df: pd.DataFrame) -> Optional[str]:
    return get_signal(df)


if __name__ == "__main__":
    print("strategy.py cargado correctamente.")
    print("Bot: analyze_market(df, confirmation_index=-2)")
