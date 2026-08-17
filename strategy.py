from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1
# ============================================================
#
# N inicia      -> recopilar datos de la M1
# N continúa    -> NO se genera señal
# N cierra      -> calcular toda la estructura de N
# decidir       -> CALL / PUT
# N+1           -> ejecutar la señal calculada
#
# La decisión usa exclusivamente OHLC de la M1 N ya cerrada.
# N+1 nunca participa en la decisión de N+1.
# No se utilizan 5S ni se exige ninguna cantidad de microvelas.
# ============================================================

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
WEAKNESS_BODY_RATIO = 0.35
CONTINUITY_BODY_RATIO = 0.45
FORCE_BODY_RATIO = 0.60


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


# ============================================================
# ANALISIS DE LA M1 CERRADA
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Analiza únicamente la vela M1 N después de su cierre."""

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "reason": "sin señal",
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "high": None,
        "low": None,
        "range": 0.0,
        "body": 0.0,
        "body_ratio": 0.0,
        "upper_wick": 0.0,
        "lower_wick": 0.0,
        "close_position": None,
        "direction": "NEUTRAL",
        "state": "INDECISION",
        "fuerza": False,
        "continuidad": False,
        "reversion": False,
        "indecision": False,
        "debilidad": False,
        "doji": False,
        "quality_checks": {},
    }

    ohlc = _get_ohlc(candle_1m)
    if ohlc is None:
        result["reason"] = "OHLC de M1 inválido"
        return result

    opening, high, low, closing = ohlc

    result["minute_open"] = opening
    result["minute_close"] = closing
    result["high"] = high
    result["low"] = low

    if "from" in candle_1m.index:
        try:
            result["minute_timestamp"] = int(float(candle_1m["from"]))
        except (TypeError, ValueError):
            pass

    candle_range = high - low
    body = abs(closing - opening)
    upper_wick = max(0.0, high - max(opening, closing))
    lower_wick = max(0.0, min(opening, closing) - low)

    result["range"] = candle_range
    result["body"] = body
    result["upper_wick"] = upper_wick
    result["lower_wick"] = lower_wick

    if candle_range <= 0:
        result["direction"] = "NEUTRAL"
        result["state"] = "DOJI"
        result["doji"] = True
        result["indecision"] = True
        result["reason"] = "sin señal: M1 sin rango"
        return result

    body_ratio = body / candle_range
    close_position = (closing - low) / candle_range

    result["body_ratio"] = body_ratio
    result["close_position"] = close_position

    if closing > opening:
        direction = "BULLISH"
    elif closing < opening:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    result["direction"] = direction

    # --------------------------------------------------------
    # ESTADOS DE LA M1 YA CERRADA
    # --------------------------------------------------------

    doji = body_ratio <= DOJI_BODY_RATIO
    indecision = body_ratio <= INDECISION_BODY_RATIO

    fuerza = (
        body_ratio >= FORCE_BODY_RATIO
        and (
            close_position >= 0.75
            or close_position <= 0.25
        )
    )

    continuidad = (
        body_ratio >= CONTINUITY_BODY_RATIO
        and (
            (direction == "BULLISH" and close_position >= 0.65)
            or (direction == "BEARISH" and close_position <= 0.35)
        )
    )

    reversion = (
        (direction == "BULLISH" and lower_wick > body * 1.5 and close_position >= 0.50)
        or (direction == "BEARISH" and upper_wick > body * 1.5 and close_position <= 0.50)
    )

    debilidad = (
        not doji
        and body_ratio < WEAKNESS_BODY_RATIO
        and max(upper_wick, lower_wick) > body
    )

    result["fuerza"] = fuerza
    result["continuidad"] = continuidad
    result["reversion"] = reversion
    result["indecision"] = indecision
    result["debilidad"] = debilidad
    result["doji"] = doji

    if doji:
        state = "DOJI"
    elif fuerza:
        state = "FUERZA"
    elif reversion:
        state = "REVERSIÓN"
    elif continuidad:
        state = "CONTINUIDAD"
    elif debilidad:
        state = "DEBILIDAD"
    elif indecision:
        state = "INDECISIÓN"
    else:
        state = "MOVIMIENTO"

    result["state"] = state

    # --------------------------------------------------------
    # DECISION FINAL: SOLO CON N CERRADA
    # --------------------------------------------------------

    if doji or direction == "NEUTRAL":
        result["reason"] = "sin señal: M1 neutral/doji"
        return result

    if direction == "BULLISH":
        result["signal"] = "call"
        result["valid"] = True
        result["reason"] = f"CALL confirmada al cierre de N: {state}"
        return result

    result["signal"] = "put"
    result["valid"] = True
    result["reason"] = f"PUT confirmada al cierre de N: {state}"
    return result


def check_pattern(candles_5s=None):
    """Compatibilidad con verificadores antiguos.

    La estrategia actual NO utiliza velas de 5 segundos para decidir.
    Las decisiones se realizan exclusivamente con la M1 ya cerrada
    mediante analyze_market().
    """
    return None


def build_n1_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Compatibilidad con versiones anteriores del bot.

    No crea una lógica nueva: utiliza exactamente el mismo análisis
    de la M1 cerrada que analyze_market().
    """
    return analyze_market(candle_1m, candles_5s, previous_m1)


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    return analyze_minute(candle_1m, candles_5s, previous_m1)


def get_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    return analyze_market(candle_1m, candles_5s, previous_m1).get("signal")


def signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    return get_signal(candle_1m, candles_5s, previous_m1)


if __name__ == "__main__":
    print("strategy.py cargado correctamente.")
    print("Estrategia: M1 completa -> cierre -> decisión -> N+1")
