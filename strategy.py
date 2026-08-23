from __future__ import annotations
from typing import Dict, Any
import pandas as pd


# ============================================================
# ANALIZAR VELA EN VIVO (CLAVE PARA EVITAR ENTRADAS MALAS)
# ============================================================

def analyze_live_candle(candle: pd.Series) -> Dict[str, Any]:
    o = float(candle["open"])
    c = float(candle["close"])
    h = float(candle["high"])
    l = float(candle["low"])

    body = abs(c - o)
    wick_up = h - max(o, c)
    wick_down = min(o, c) - l

    direction = "call" if c > o else "put"

    strength = 0
    rejection = False

    # Fuerza del cuerpo
    if body > (wick_up + wick_down):
        strength += 50
    else:
        strength += 20

    # Rechazo (mechas grandes)
    if wick_up > body * 1.5 or wick_down > body * 1.5:
        rejection = True
        strength -= 30

    # Resultado final
    return {
        "direction": direction,
        "strength": max(0, min(100, strength)),
        "rejection": rejection,
        "body": body,
        "wick_up": wick_up,
        "wick_down": wick_down,
    }


# ============================================================
# ANALIZAR MERCADO (SIN CAMBIAR TU LÓGICA BASE)
# ============================================================

def analyze_market(
    candle: pd.Series,
    previous_m1: pd.DataFrame,
) -> Dict[str, Any]:

    o = float(candle["open"])
    c = float(candle["close"])

    direction = "call" if c > o else "put"

    body = abs(c - o)

    # --------------------------------------------------------
    # SCORE BASE
    # --------------------------------------------------------

    score = 50

    # Vela fuerte
    if body > 0:
        score += 20

    # Continuidad simple
    if len(previous_m1) >= 3:
        last3 = previous_m1.tail(3)

        same_dir = 0
        for _, row in last3.iterrows():
            if (row["close"] > row["open"]) == (c > o):
                same_dir += 1

        score += same_dir * 10

    # --------------------------------------------------------
    # BLOQUEOS
    # --------------------------------------------------------

    valid = True
    reason = "Continuidad detectada"

    # Evitar rango
    if body < 0.00001:
        valid = False
        reason = "Rango"

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "valid": valid,
        "signal": direction,
        "score": score,
        "direction": direction,
        "reason": reason,
        "structure": {
            "score": score,
            "reason": "Continuidad simple",
        },
        "continuity": {
            "score": score,
            "reason": "Velas alineadas",
        },
        "confirmation": {
            "score": score,
            "reason": "Cierre direccional",
        },
        "minute_open": o,
        "minute_close": c,
    }
