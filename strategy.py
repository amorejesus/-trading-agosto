from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

TREND_LOOKBACK = 15
STRUCTURE_LOOKBACK = 20
CONTINUITY_LOOKBACK = 6
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14

MAX_SCORE = 100
MIN_STRUCTURE_SCORE = 8
MIN_CONTINUITY_SCORE = 5
MIN_FINAL_SCORE = 82

# ============================================================
# UTILS
# ============================================================

def safe_dataframe(df):
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return pd.DataFrame()

    required = {"open", "close", "high", "low"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df.copy()
    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def get_candle_data(c):
    try:
        o = float(c["open"])
        cl = float(c["close"])
        h = float(c["high"])
        l = float(c["low"])
    except:
        return None

    r = h - l
    body = abs(cl - o)

    if r == 0:
        return None

    return {
        "open": o,
        "close": cl,
        "high": h,
        "low": l,
        "range": r,
        "body": body,
        "body_ratio": body / r,
        "upper_wick": h - max(o, cl),
        "lower_wick": min(o, cl) - l,
    }


# ============================================================
# ATR
# ============================================================

def calculate_atr(df):
    df = safe_dataframe(df)
    if len(df) < 2:
        return 0

    prev_close = df["close"].shift(1)

    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)

    return float(tr.rolling(14).mean().iloc[-1])


# ============================================================
# STRUCTURE
# ============================================================

def analyze_structure(df):
    df = safe_dataframe(df)

    if len(df) < 6:
        return {"direction": "NEUTRAL", "score": 0}

    highs = df["high"]
    lows = df["low"]
    closes = df["close"]

    bullish = sum(highs.diff() > 0) + sum(lows.diff() > 0)
    bearish = sum(highs.diff() < 0) + sum(lows.diff() < 0)

    if bullish > bearish and bullish >= MIN_STRUCTURE_SCORE:
        return {"direction": "BULLISH", "score": bullish}

    if bearish > bullish and bearish >= MIN_STRUCTURE_SCORE:
        return {"direction": "BEARISH", "score": bearish}

    return {"direction": "NEUTRAL", "score": 0}


# ============================================================
# CONTINUITY
# ============================================================

def check_continuity(df, direction):
    df = safe_dataframe(df).tail(CONTINUITY_LOOKBACK)

    if len(df) < CONTINUITY_LOOKBACK:
        return {"valid": False, "score": 0}

    closes = df["close"]

    if direction == "BULLISH":
        score = sum(closes.diff() > 0)
    else:
        score = sum(closes.diff() < 0)

    return {
        "valid": score >= MIN_CONTINUITY_SCORE,
        "score": score
    }


# ============================================================
# 🔥 NUEVO: MOMENTUM BREAK
# ============================================================

def detect_momentum_break(df, direction):
    df = safe_dataframe(df)

    result = {
        "broken": False,
        "penalty": 0,
        "reason": ""
    }

    if len(df) < 3:
        return result

    last = get_candle_data(df.iloc[-1])
    prev = get_candle_data(df.iloc[-2])

    if not last or not prev:
        return result

    # 🔴 ruptura bajista fuerte
    if direction == "BULLISH":
        if (
            last["close"] < last["open"] and
            last["body_ratio"] >= 0.55 and
            last["close"] < prev["low"]
        ):
            result["broken"] = True
            result["penalty"] = 15
            result["reason"] = "ruptura bajista fuerte"

    # 🟢 ruptura alcista fuerte
    elif direction == "BEARISH":
        if (
            last["close"] > last["open"] and
            last["body_ratio"] >= 0.55 and
            last["close"] > prev["high"]
        ):
            result["broken"] = True
            result["penalty"] = 15
            result["reason"] = "ruptura alcista fuerte"

    return result


# ============================================================
# MAIN
# ============================================================

def analyze_market(candle_1m=None, candles_5s=None, previous_m1=None):

    result = {
        "signal": None,
        "valid": False,
        "score": 0,
        "direction": "NEUTRAL",
        "state": "NO_SIGNAL",
        "reason": ""
    }

    df = safe_dataframe(previous_m1)

    if len(df) < 10:
        result["reason"] = "pocos datos"
        return result

    structure = analyze_structure(df)
    direction = structure["direction"]

    if direction == "NEUTRAL":
        result["reason"] = "sin estructura"
        return result

    continuity = check_continuity(df, direction)

    # 🔥 NUEVO
    momentum_break = detect_momentum_break(df, direction)

    score = 0
    score += structure["score"] * 3
    score += continuity["score"] * 3

    # penalización
    score -= momentum_break["penalty"]

    result["score"] = score
    result["direction"] = direction

    # 🔥 BLOQUEO CRÍTICO
    if momentum_break["broken"]:
        result["state"] = "MOMENTUM_BREAK"
        result["reason"] = momentum_break["reason"]
        return result

    if not continuity["valid"]:
        result["state"] = "NO_CONTINUITY"
        return result

    if score < MIN_FINAL_SCORE:
        result["state"] = "LOW_SCORE"
        return result

    if direction == "BULLISH":
        result["signal"] = "call"
    else:
        result["signal"] = "put"

    result["valid"] = True
    result["state"] = "OK"
    result["reason"] = f"{direction} score={score}"

    return result


# ============================================================
# COMPAT
# ============================================================

def analyze_minute(*args, **kwargs):
    return analyze_market(*args, **kwargs)

def build_n1_signal(*args, **kwargs):
    return analyze_market(*args, **kwargs)

def get_signal(*args, **kwargs):
    return analyze_market(*args, **kwargs).get("signal")

def signal(*args, **kwargs):
    return get_signal(*args, **kwargs)

def check_pattern(*args, **kwargs):
    return None
