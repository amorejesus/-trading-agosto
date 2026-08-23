from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result.dropna(subset=list(required), inplace=True)
    result.reset_index(drop=True, inplace=True)

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(df: pd.DataFrame) -> float:

    df = safe_dataframe(df)

    if len(df) < 2:
        return 0.0

    prev_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(14).mean().iloc[-1]

    if pd.isna(atr):
        return 0.0

    return float(atr)


# ============================================================
# DATOS DE VELA
# ============================================================

def get_candle_data(candle: pd.Series):

    try:
        o = float(candle["open"])
        c = float(candle["close"])
        h = float(candle["high"])
        l = float(candle["low"])
    except:
        return None

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
    }


# ============================================================
# ESTRUCTURA (SIN CAMBIOS)
# ============================================================

def analyze_structure(df: pd.DataFrame) -> Dict[str, Any]:

    df = safe_dataframe(df)

    if len(df) < 10:
        return {
            "direction": "NEUTRAL",
            "score": 0,
        }

    closes = df["close"].tolist()

    bullish = sum(closes[i] > closes[i-1] for i in range(1, len(closes)))
    bearish = sum(closes[i] < closes[i-1] for i in range(1, len(closes)))

    if bullish > bearish:
        return {"direction": "BULLISH", "score": bullish}

    if bearish > bullish:
        return {"direction": "BEARISH", "score": bearish}

    return {"direction": "NEUTRAL", "score": 0}


# ============================================================
# CONTINUIDAD (SIN CAMBIOS)
# ============================================================

def check_continuity(df: pd.DataFrame, direction: str):

    df = safe_dataframe(df)

    closes = df["close"].tolist()

    score = 0

    if direction == "BULLISH":
        score = sum(closes[i] >= closes[i-1] for i in range(1, len(closes)))

    if direction == "BEARISH":
        score = sum(closes[i] <= closes[i-1] for i in range(1, len(closes)))

    return {
        "score": score,
        "valid": score >= 3,
    }


# ============================================================
# CONFIRMACIÓN (SIN CAMBIOS)
# ============================================================

def confirmation_score(df: pd.DataFrame, direction: str):

    df = safe_dataframe(df)

    last = df.iloc[-1]

    body = abs(last["close"] - last["open"])

    valid = body > 0

    return {
        "score": 10 if valid else 0,
        "valid": valid,
    }


# ============================================================
# 🧠 NUEVO: IMPULSO TEMPRANO SNIPER
# ============================================================

def detect_early_impulse(df: pd.DataFrame) -> Dict[str, Any]:

    df = safe_dataframe(df)

    result = {
        "early": False,
        "blocked": False,
        "reason": ""
    }

    if len(df) < 6:
        result["reason"] = "sin datos"
        return result

    # VELAS 1–2–3
    first = df.tail(3)

    opens = first["open"].tolist()
    closes = first["close"].tolist()

    bodies = [abs(c - o) for o, c in zip(opens, closes)]

    strong_start = bodies[0] > bodies[1] and bodies[0] > 0
    continuation = bodies[1] >= bodies[0] * 0.7

    if not (strong_start and continuation):
        result["reason"] = "sin impulso temprano"
        return result

    # 🚨 BLOQUEO: IMPULSO TARDÍO (VELA 4+)
    if len(df) >= 6:

        early = abs(df.iloc[-4]["close"] - df.iloc[-4]["open"])
        late = abs(df.iloc[-1]["close"] - df.iloc[-1]["open"])

        if late > early * 1.5:
            result["blocked"] = True
            result["reason"] = "impulso tardío (vela 4+)"
            return result

    result["early"] = True
    result["reason"] = "impulso temprano válido"

    return result


# ============================================================
# ANÁLISIS LIVE
# ============================================================

def analyze_live_candle(candle):

    o = float(candle["open"])
    c = float(candle["close"])

    return {
        "direction": "BULLISH" if c > o else "BEARISH",
        "score": 10,
        "state": "LIVE_CONTINUITY"
    }


# ============================================================
# ANÁLISIS PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m,
    candles_5s=None,
    previous_m1=None
):

    df = safe_dataframe(previous_m1)

    structure = analyze_structure(df)
    continuity = check_continuity(df, structure["direction"])
    confirmation = confirmation_score(df, structure["direction"])
    early = detect_early_impulse(df)   # 🔥 NUEVO

    score = (
        structure["score"] +
        continuity["score"] +
        confirmation["score"]
    )

    valid = (
        continuity["valid"]
        and confirmation["valid"]
        and not early["blocked"]   # 🚨 BLOQUEO SNIPER
    )

    return {
        "signal": "call" if structure["direction"] == "BULLISH" else "put",
        "valid": valid,
        "score": score,
        "direction": structure["direction"],
        "structure": structure,
        "continuity": continuity,
        "confirmation": confirmation,
        "early_impulse": early   # 🔥 NUEVO
    }


# ============================================================
# COMPATIBILIDAD
# ============================================================

def get_signal(*args, **kwargs):
    return analyze_market(*args, **kwargs).get("signal")
