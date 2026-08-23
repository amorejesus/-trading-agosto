from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1 - MULTI MARKET CONTINUITY
# ============================================================

TREND_LOOKBACK = 15
STRUCTURE_LOOKBACK = 20
CONTINUITY_LOOKBACK = 6
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
WEAKNESS_BODY_RATIO = 0.35
MIN_CONTINUITY_BODY_RATIO = 0.40
STRONG_BODY_RATIO = 0.55
FORCE_BODY_RATIO = 0.65

MAX_COUNTER_WICK_RATIO = 0.45
MAX_CONFIRMATION_RANGE_ATR = 1.60
MAX_CONFIRMATION_BODY_ATR = 1.20

SR_TOLERANCE_ATR = 0.35

LIVE_MIN_BODY_RATIO = 0.35
LIVE_STRONG_BODY_RATIO = 0.55
LIVE_FORCE_BODY_RATIO = 0.70

LIVE_MIN_SCORE = 65
LIVE_READY_SCORE = 75

LIVE_MAX_RANGE_ATR = 1.35
LIVE_MAX_BODY_ATR = 1.05

LIVE_MICRO_MIN_CANDLES = 4
LIVE_MICRO_STRONG_RATIO = 0.65

MAX_SCORE = 100

MIN_STRUCTURE_SCORE = 8
MIN_CONTINUITY_SCORE = 5
MIN_FINAL_SCORE = 82


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_ohlc(candle: pd.Series) -> Optional[tuple[float, float, float, float]]:
    if candle is None:
        return None

    opening = _to_float(candle.get("open"))
    closing = _to_float(candle.get("close"))
    high = _to_float(candle.get("high", candle.get("max")))
    low = _to_float(candle.get("low", candle.get("min")))

    if None in (opening, closing, high, low):
        return None

    if high < low:
        return None

    return opening, high, low, closing


def safe_dataframe(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if len(df) == 0:
        return pd.DataFrame()

    required = {"open", "close", "high", "low"}

    if not required.issubset(df.columns):
        return pd.DataFrame()

    result = df.copy()

    for column in required:
        result[column] = pd.to_numeric(result[column], errors="coerce")

    result.dropna(subset=list(required), inplace=True)

    if "from" in result.columns:
        result.sort_values("from", inplace=True)

    result.reset_index(drop=True, inplace=True)

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    df = safe_dataframe(df)

    if len(df) < 2:
        return 0.0

    work = df.copy()
    previous_close = work["close"].shift(1)

    tr1 = work["high"] - work["low"]
    tr2 = (work["high"] - previous_close).abs()
    tr3 = (work["low"] - previous_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr_series = true_range.rolling(
        window=min(period, len(work)),
        min_periods=2,
    ).mean()

    atr = atr_series.iloc[-1]

    if pd.isna(atr):
        return 0.0

    return float(atr)


# ============================================================
# VELA
# ============================================================

def get_candle_data(candle: pd.Series) -> Optional[Dict[str, float]]:
    ohlc = _get_ohlc(candle)
    if ohlc is None:
        return None

    o, h, l, c = ohlc

    rng = h - l
    body = abs(c - o)

    upper = max(0.0, h - max(o, c))
    lower = max(0.0, min(o, c) - l)

    if rng <= 0:
        return None

    return {
        "open": o,
        "close": c,
        "high": h,
        "low": l,
        "range": rng,
        "body": body,
        "upper_wick": upper,
        "lower_wick": lower,
        "body_ratio": body / rng,
        "upper_wick_ratio": upper / rng,
        "lower_wick_ratio": lower / rng,
        "close_position": (c - l) / rng,
    }


# ============================================================
# 🔴 NUEVO: FILTRO ZONAS DE REVERSIÓN / AGOTAMIENTO
# ============================================================

def zone_filter(df: pd.DataFrame, direction: str) -> Dict[str, Any]:
    result = {
        "blocked": False,
        "reason": "",
        "penalty": 0,
    }

    df = safe_dataframe(df)
    if len(df) < 5:
        return result

    recent = df.tail(6)
    last = get_candle_data(recent.iloc[-1])
    prev = get_candle_data(recent.iloc[-2])

    if last is None or prev is None:
        return result

    # ATR simple
    atr = calculate_atr(df.tail(14))
    if atr <= 0:
        return result

    # ========================================================
    # 🔴 REVERSIÓN
    # ========================================================

    if direction == "BULLISH":
        if (
            last["upper_wick_ratio"] > 0.55
            and last["body_ratio"] < 0.35
        ):
            result["blocked"] = True
            result["reason"] = "reversión posible (rechazo superior)"
            result["penalty"] = 20

    elif direction == "BEARISH":
        if (
            last["lower_wick_ratio"] > 0.55
            and last["body_ratio"] < 0.35
        ):
            result["blocked"] = True
            result["reason"] = "reversión posible (rechazo inferior)"
            result["penalty"] = 20

    # ========================================================
    # 🔴 AGOTAMIENTO DEL IMPULSO
    # ========================================================

    if last["body"] > atr * 1.4:
        result["blocked"] = True
        result["reason"] = "impulso agotado (vela extendida)"
        result["penalty"] = 25

    return result


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(
    candle_1m: Optional[pd.Series] = None,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "score": 0,
        "direction": "NEUTRAL",
        "state": "NO_SIGNAL",
        "reason": "sin análisis",
    }

    if candle_1m is None:
        return result

    current = get_candle_data(candle_1m)
    if current is None:
        return result

    historical = safe_dataframe(previous_m1)

    if len(historical) < 6:
        return result

    # ========================================================
    # ESTRUCTURA SIMPLE (mantener lógica existente)
    # ========================================================

    bullish = (historical["close"].iloc[-1] > historical["close"].iloc[0])

    direction = "BULLISH" if bullish else "BEARISH"
    result["direction"] = direction

    # ========================================================
    # 🔴 APLICAR FILTRO NUEVO (ANTES DE SEÑAL)
    # ========================================================

    zone = zone_filter(historical, direction)

    if zone["blocked"]:
        result["state"] = "ZONE_BLOCKED"
        result["reason"] = zone["reason"]
        return result

    # ========================================================
    # SEÑAL FINAL (SIN CAMBIAR TU LÓGICA BASE)
    # ========================================================

    if direction == "BULLISH":
        result["signal"] = "call"
        result["valid"] = True
        result["state"] = "BULLISH_CONTINUITY"
        result["reason"] = "CALL permitido (zona limpia)"
        return result

    if direction == "BEARISH":
        result["signal"] = "put"
        result["valid"] = True
        result["state"] = "BEARISH_CONTINUITY"
        result["reason"] = "PUT permitido (zona limpia)"
        return result

    return result
