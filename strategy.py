from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd

# ============================================
# CONFIG
# ============================================

MIN_CONFIRMATION_SCORE = 30


# ============================================
# UTILIDADES
# ============================================

def _to_float(value: Any):
    try:
        return float(value)
    except:
        return None


def safe_dataframe(df):
    if df is None or not isinstance(df, pd.DataFrame) or len(df) == 0:
        return pd.DataFrame()

    df = df.copy()

    if "max" in df.columns:
        df["high"] = df["max"]
    if "min" in df.columns:
        df["low"] = df["min"]

    required = ["open", "close", "high", "low"]

    for c in required:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df


# ============================================
# DATOS DE VELA
# ============================================

def get_candle(c):
    o = _to_float(c.get("open"))
    cl = _to_float(c.get("close"))
    h = _to_float(c.get("high"))
    l = _to_float(c.get("low"))

    if None in (o, cl, h, l):
        return None

    r = h - l
    body = abs(cl - o)

    return {
        "open": o,
        "close": cl,
        "high": h,
        "low": l,
        "range": r,
        "body": body,
        "body_ratio": body / r if r > 0 else 0,
        "bull": cl > o,
        "bear": cl < o
    }


# ============================================
# CONFIRMACIÓN DE REVERSIÓN
# ============================================

def confirmation(df):
    df = safe_dataframe(df)

    if len(df) < 3:
        return {"valid": False}

    last = get_candle(df.iloc[-1])
    prev = get_candle(df.iloc[-2])

    if not last or not prev:
        return {"valid": False}

    score = 0

    # CALL
    if last["bull"]:
        score += 15
        if last["body_ratio"] > 0.4:
            score += 10
        if last["close"] > prev["close"]:
            score += 5

        if score >= MIN_CONFIRMATION_SCORE:
            return {"valid": True, "dir": "CALL", "score": score}

    # PUT
    if last["bear"]:
        score += 15
        if last["body_ratio"] > 0.4:
            score += 10
        if last["close"] < prev["close"]:
            score += 5

        if score >= MIN_CONFIRMATION_SCORE:
            return {"valid": True, "dir": "PUT", "score": score}

    return {"valid": False}


# ============================================
# 🔥 FILTRO DE CALIDAD DEL PAR
# ============================================

def evaluate_pair_quality(df):
    df = safe_dataframe(df)

    if len(df) < 10:
        return 0

    last = get_candle(df.iloc[-1])
    prev = get_candle(df.iloc[-2])

    if not last or not prev:
        return 0

    score = 0

    # Volatilidad
    avg_range = (df["high"] - df["low"]).mean()
    last_range = last["range"]

    if last_range > avg_range:
        score += 10

    # Cuerpo fuerte
    if last["body_ratio"] > 0.5:
        score += 10

    # Cambio de intención
    if last["bull"] and prev["bear"]:
        score += 15

    if last["bear"] and prev["bull"]:
        score += 15

    # Evitar mercado muerto
    if last_range < avg_range * 0.5:
        score -= 15

    return score


# ============================================
# MAIN SNIPER
# ============================================

def analyze_market(
    candle_1m=None,
    candles_5s=None,
    previous_m1=None
):

    result = {
        "signal": None,
        "valid": False,
        "reason": "no signal",
        "execution": "N+1"
    }

    if candle_1m is None:
        return result

    df = safe_dataframe(previous_m1)
    df = pd.concat([df, pd.DataFrame([candle_1m])], ignore_index=True)

    conf = confirmation(df)

    if not conf["valid"]:
        result["reason"] = "sin confirmación"
        return result

    if conf["dir"] == "CALL":
        result.update({
            "signal": "call",
            "valid": True,
            "reason": "CALL SNIPER REVERSAL",
        })

    elif conf["dir"] == "PUT":
        result.update({
            "signal": "put",
            "valid": True,
            "reason": "PUT SNIPER REVERSAL",
        })

    return result


# ============================================
# ANALISIS LIVE (NECESARIO PARA TU BOT)
# ============================================

def analyze_live_candle(candle_1m):

    data = get_candle(candle_1m)

    if not data:
        return {"state": "INVALID"}

    direction = "NEUTRAL"

    if data["bull"]:
        direction = "BULLISH"
    elif data["bear"]:
        direction = "BEARISH"

    return {
        "direction": direction,
        "body_ratio": data["body_ratio"],
        "state": "LIVE"
    }


# ============================================
# COMPATIBILIDAD BOT
# ============================================

def analyze_minute(candle_1m, candles_5s=None, previous_m1=None):
    return analyze_market(candle_1m, candles_5s, previous_m1)


def get_signal(candle_1m, candles_5s=None, previous_m1=None):
    r = analyze_market(candle_1m, candles_5s, previous_m1)
    return r.get("signal")


def signal(candle_1m, candles_5s=None, previous_m1=None):
    return get_signal(candle_1m, candles_5s, previous_m1)


def check_pattern(candles_5s=None):
    return None


# ============================================
# TEST
# ============================================

if __name__ == "__main__":
    print("✅ STRATEGY SNIPER + FILTRO DE PAR ACTIVA")
