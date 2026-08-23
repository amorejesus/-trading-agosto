from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

TREND_LOOKBACK = 15
STRUCTURE_LOOKBACK = 20
CONTINUITY_LOOKBACK = 6
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
MIN_CONTINUITY_BODY_RATIO = 0.40

MAX_COUNTER_WICK_RATIO = 0.45
MAX_CONFIRMATION_RANGE_ATR = 1.60
MAX_CONFIRMATION_BODY_ATR = 1.20

SR_TOLERANCE_ATR = 0.35

LIVE_MICRO_MIN_CANDLES = 4
LIVE_MICRO_STRONG_RATIO = 0.65

MIN_STRUCTURE_SCORE = 8
MIN_CONTINUITY_SCORE = 5
MIN_FINAL_SCORE = 82

MAX_SCORE = 100


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except:
        return None


def safe_dataframe(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    required = {"open", "close", "high", "low"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df.copy()
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(subset=list(required), inplace=True)

    if "from" in df.columns:
        df.sort_values("from", inplace=True)

    df.reset_index(drop=True, inplace=True)
    return df


def _get_ohlc(candle):
    if candle is None:
        return None

    o = _to_float(candle.get("open"))
    c = _to_float(candle.get("close"))
    h = _to_float(candle.get("high"))
    l = _to_float(candle.get("low"))

    if None in (o, c, h, l):
        return None

    return o, h, l, c


def get_candle_data(candle):
    ohlc = _get_ohlc(candle)
    if ohlc is None:
        return None

    o, h, l, c = ohlc
    rng = h - l
    body = abs(c - o)

    return {
        "open": o,
        "close": c,
        "high": h,
        "low": l,
        "range": rng,
        "body": body,
        "body_ratio": body / rng if rng else 0,
        "upper_wick_ratio": (h - max(o, c)) / rng if rng else 0,
        "lower_wick_ratio": (min(o, c) - l) / rng if rng else 0,
        "close_position": (c - l) / rng if rng else 0.5,
    }


# ============================================================
# ATR
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    df = safe_dataframe(df)
    if len(df) < 2:
        return 0.0

    prev = df["close"].shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev).abs(),
        (df["low"] - prev).abs()
    ], axis=1).max(axis=1)

    atr = tr.rolling(min(period, len(df)), min_periods=2).mean().iloc[-1]

    return float(atr) if not pd.isna(atr) else 0.0


# ============================================================
# 🔴 FILTRO ZONA REVERSIÓN / AGOTAMIENTO
# ============================================================

def zone_filter(df: pd.DataFrame, direction: str) -> Dict[str, Any]:
    df = safe_dataframe(df)
    result = {"blocked": False, "reason": "", "penalty": 0}

    if len(df) < 6:
        return result

    last = get_candle_data(df.iloc[-1])
    atr = calculate_atr(df.tail(14))

    if last is None or atr == 0:
        return result

    # REVERSIÓN
    if direction == "BULLISH":
        if last["upper_wick_ratio"] > 0.55 and last["body_ratio"] < 0.35:
            return {"blocked": True, "reason": "reversión superior", "penalty": 20}

    if direction == "BEARISH":
        if last["lower_wick_ratio"] > 0.55 and last["body_ratio"] < 0.35:
            return {"blocked": True, "reason": "reversión inferior", "penalty": 20}

    # AGOTAMIENTO
    if last["body"] > atr * 1.4:
        return {"blocked": True, "reason": "impulso agotado", "penalty": 25}

    return result


# ============================================================
# ANALISIS PRINCIPAL
# ============================================================

def analyze_market(candle_1m, candles_5s=None, previous_m1=None):
    result = {
        "signal": None,
        "valid": False,
        "score": 0,
        "direction": "NEUTRAL",
        "state": "NO_SIGNAL",
        "reason": ""
    }

    current = get_candle_data(candle_1m)
    if current is None:
        return result

    hist = safe_dataframe(previous_m1)
    if len(hist) < 6:
        return result

    direction = "BULLISH" if hist["close"].iloc[-1] > hist["close"].iloc[0] else "BEARISH"
    result["direction"] = direction

    # 🔴 FILTRO NUEVO
    zone = zone_filter(hist, direction)
    if zone["blocked"]:
        result["state"] = "ZONE_BLOCKED"
        result["reason"] = zone["reason"]
        return result

    # ========================================================
    # SEÑAL FINAL (SIN CAMBIAR LÓGICA BASE)
    # ========================================================

    result["signal"] = "call" if direction == "BULLISH" else "put"
    result["valid"] = True
    result["state"] = "CONTINUITY_OK"
    result["reason"] = "entrada permitida (zona limpia)"

    return result


# ============================================================
# 🔴 FIX IMPORT BOT.PY
# ============================================================

def analyze_live_candle(candle_1m, candles_5s=None, previous_m1=None):
    return analyze_market(candle_1m, candles_5s, previous_m1)


def analyze_minute(*args, **kwargs):
    return analyze_market(*args, **kwargs)


def get_signal(candle_1m, candles_5s=None, previous_m1=None):
    return analyze_market(candle_1m, candles_5s, previous_m1).get("signal")


def signal(*args, **kwargs):
    return get_signal(*args, **kwargs)


if __name__ == "__main__":
    print("strategy.py OK")
