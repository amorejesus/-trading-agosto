from __future__ import annotations
from typing import Dict, Any
import pandas as pd


# ============================================================
# UTILIDADES
# ============================================================

def get_color(candle) -> str:
    return "verde" if candle["close"] > candle["open"] else "rojo"


def body_size(candle) -> float:
    return abs(candle["close"] - candle["open"])


def candle_range(candle) -> float:
    return candle["high"] - candle["low"]


# ============================================================
# ANALISIS DE VELA EN VIVO (SNIPER)
# ============================================================

def analyze_live_candle(candle: pd.Series) -> Dict[str, Any]:

    try:
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

        if body > (wick_up + wick_down):
            strength = 70
        elif body > (wick_up + wick_down) * 0.5:
            strength = 50
        else:
            strength = 30

        if wick_up > body * 1.5 or wick_down > body * 1.5:
            rejection = True
            strength -= 30

        return {
            "direction": direction,
            "strength": max(0, min(100, strength)),
            "rejection": rejection,
            "body": body,
            "wick_up": wick_up,
            "wick_down": wick_down,
        }

    except Exception:
        return {
            "direction": None,
            "strength": 0,
            "rejection": True,
            "body": 0,
            "wick_up": 0,
            "wick_down": 0,
        }


# ============================================================
# ANALISIS PRINCIPAL
# ============================================================

def analyze_market(
    candle: pd.Series,
    previous_m1: pd.DataFrame,
) -> Dict[str, Any]:

    try:

        o = float(candle["open"])
        c = float(candle["close"])
        h = float(candle["high"])
        l = float(candle["low"])

        direction = "call" if c > o else "put"

        body = body_size(candle)
        rng = candle_range(candle)

        # ====================================================
        # CONTINUIDAD
        # ====================================================

        continuity_score = 0
        continuity_reason = ""

        if len(previous_m1) >= 3:

            last3 = previous_m1.tail(3)

            same_dir = 0
            for _, row in last3.iterrows():
                if (row["close"] > row["open"]) == (c > o):
                    same_dir += 1

            if same_dir >= 2:
                continuity_score = 40
                continuity_reason = "Continuidad clara"
            else:
                continuity_reason = "Continuidad débil"

        # ====================================================
        # FUERZA
        # ====================================================

        strength_score = 0
        strength_reason = ""

        if rng > 0:
            ratio = body / rng

            if ratio > 0.6:
                strength_score = 40
                strength_reason = "Vela fuerte"
            elif ratio > 0.4:
                strength_score = 25
                strength_reason = "Fuerza media"
            else:
                strength_reason = "Vela débil"

        # ====================================================
        # REVERSIÓN SNIPER 🔥
        # ====================================================

        reversal_signal = None
        reversal_score = 0
        reversal_reason = ""

        if len(previous_m1) >= 1:

            prev = previous_m1.iloc[-1]

            prev_high = float(prev["high"])
            prev_low = float(prev["low"])

            wick_up = h - max(o, c)
            wick_down = min(o, c) - l

            # 🔻 techo → PUT
            if (
                wick_up > body * 1.5
                and c < o
                and l < prev_low
            ):
                reversal_signal = "put"
                reversal_score = 85
                reversal_reason = "Reversión en techo"

            # 🔺 suelo → CALL
            elif (
                wick_down > body * 1.5
                and c > o
                and h > prev_high
            ):
                reversal_signal = "call"
                reversal_score = 85
                reversal_reason = "Reversión en suelo"

        # ====================================================
        # FILTRO ANTI-RESISTENCIA INVISIBLE
        # ====================================================

        overextended = False
        overextended_reason = ""

        if len(previous_m1) >= 6:

            last6 = previous_m1.tail(6)

            same_dir = 0
            for _, row in last6.iterrows():
                if (row["close"] > row["open"]) == (c > o):
                    same_dir += 1

            if same_dir >= 5:
                overextended = True
                overextended_reason = "Tendencia extendida"

            avg_price = last6["close"].mean()
            distance = abs(c - avg_price)
            avg_range = (last6["high"] - last6["low"]).mean()

            if avg_range > 0 and distance > avg_range * 2:
                overextended = True
                overextended_reason = "Precio extendido"

            bodies = [
                abs(row["close"] - row["open"])
                for _, row in last6.iterrows()
            ]

            if len(bodies) >= 3:
                if bodies[-1] < bodies[-2] < bodies[-3]:
                    overextended = True
                    overextended_reason = "Agotamiento"

        # ====================================================
        # PRIORIDAD: REVERSIÓN > CONTINUIDAD
        # ====================================================

        if reversal_signal:

            signal = reversal_signal
            score = reversal_score
            valid = True
            reason = reversal_reason

        else:

            score = continuity_score + strength_score
            signal = direction
            valid = True
            reason = "Continuidad + fuerza"

        # ====================================================
        # BLOQUEOS
        # ====================================================

        if overextended:
            valid = False
            reason = overextended_reason

        elif score < 50:
            valid = False
            reason = "Score bajo"

        # ====================================================
        # RESULTADO
        # ====================================================

        return {
            "valid": valid,
            "signal": signal,
            "score": score,
            "direction": direction,
            "reason": reason,

            "structure": {
                "score": strength_score,
                "reason": strength_reason,
            },

            "continuity": {
                "score": continuity_score,
                "reason": continuity_reason,
            },

            "confirmation": {
                "score": 0,
                "reason": "No usado",
            },

            "minute_open": o,
            "minute_close": c,
        }

    except Exception:

        return {
            "valid": False,
            "signal": None,
            "score": 0,
            "direction": None,
            "reason": "Error",

            "structure": {"score": 0, "reason": ""},
            "continuity": {"score": 0, "reason": ""},
            "confirmation": {"score": 0, "reason": ""},

            "minute_open": 0,
            "minute_close": 0,
        }
