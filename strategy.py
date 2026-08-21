from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1 - MULTI MARKET CONTINUITY
# ============================================================
#
# OBJETIVO
# ------------------------------------------------------------
# Analizar la estructura de un mercado y devolver:
#
# - Dirección probable: CALL / PUT
# - Tendencia
# - Continuidad
# - Calidad de la estructura
# - Calidad de la vela M1
# - Riesgos: agotamiento, rechazo, S/R, rango
# - Score total para comparar este mercado con otros
#
# IMPORTANTE
# ------------------------------------------------------------
# La vela M1 actual puede analizarse EN VIVO para observar:
#
# - apertura
# - máximo
# - mínimo
# - precio actual
# - cuerpo
# - mechas
# - fuerza
# - continuidad
#
# La señal definitiva se genera utilizando la M1 cerrada.
# La entrada corresponde a N+1.
# ============================================================


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

TREND_LOOKBACK = 15
STRUCTURE_LOOKBACK = 20
CONTINUITY_LOOKBACK = 6
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14


# ============================================================
# RATIOS DE VELA
# ============================================================

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


# ============================================================
# SCORES
# ============================================================

MAX_SCORE = 100

MIN_STRUCTURE_SCORE = 8
MIN_CONTINUITY_SCORE = 5
MIN_FINAL_SCORE = 70


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_ohlc(
    candle: pd.Series,
) -> Optional[tuple[float, float, float, float]]:

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


def safe_dataframe(
    df: Optional[pd.DataFrame],
) -> pd.DataFrame:

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

    result.dropna(
        subset=list(required),
        inplace=True,
    )

    if "from" in result.columns:
        result.sort_values(
            "from",
            inplace=True,
        )

    result.reset_index(
        drop=True,
        inplace=True,
    )

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df: pd.DataFrame,
    period: int = ATR_PERIOD,
) -> float:

    df = safe_dataframe(df)

    if len(df) < 2:
        return 0.0

    work = df.copy()

    previous_close = work["close"].shift(1)

    tr1 = work["high"] - work["low"]
    tr2 = (work["high"] - previous_close).abs()
    tr3 = (work["low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    atr_series = true_range.rolling(
        window=min(period, len(work)),
        min_periods=2,
    ).mean()

    atr = atr_series.iloc[-1]

    if pd.isna(atr):
        return 0.0

    return float(atr)


# ============================================================
# DATOS DE VELA
# ============================================================

def get_candle_data(
    candle: pd.Series,
) -> Optional[Dict[str, float]]:

    ohlc = _get_ohlc(candle)

    if ohlc is None:
        return None

    opening, high, low, closing = ohlc

    candle_range = high - low
    body = abs(closing - opening)

    upper_wick = max(
        0.0,
        high - max(opening, closing),
    )

    lower_wick = max(
        0.0,
        min(opening, closing) - low,
    )

    if candle_range <= 0:

        return {
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "range": 0.0,
            "body": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "body_ratio": 0.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0,
            "close_position": 0.5,
        }

    return {
        "open": opening,
        "close": closing,
        "high": high,
        "low": low,
        "range": candle_range,
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body / candle_range,
        "upper_wick_ratio": upper_wick / candle_range,
        "lower_wick_ratio": lower_wick / candle_range,
        "close_position": (
            closing - low
        ) / candle_range,
    }


# ============================================================
# ANALIZAR ESTRUCTURA
# ============================================================

def analyze_structure(
    df: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "direction": "NEUTRAL",
        "score": 0,
        "bullish_score": 0,
        "bearish_score": 0,
        "reason": "estructura insuficiente",
    }

    df = safe_dataframe(df)

    if len(df) < 6:
        return result

    work = df.tail(
        TREND_LOOKBACK
    ).reset_index(drop=True)

    bullish_score = 0
    bearish_score = 0

    highs = work["high"].tolist()
    lows = work["low"].tolist()
    closes = work["close"].tolist()

    higher_highs = sum(
        1
        for i in range(1, len(highs))
        if highs[i] > highs[i - 1]
    )

    higher_lows = sum(
        1
        for i in range(1, len(lows))
        if lows[i] > lows[i - 1]
    )

    lower_highs = sum(
        1
        for i in range(1, len(highs))
        if highs[i] < highs[i - 1]
    )

    lower_lows = sum(
        1
        for i in range(1, len(lows))
        if lows[i] < lows[i - 1]
    )

    bullish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] > closes[i - 1]
    )

    bearish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] < closes[i - 1]
    )

    if higher_highs >= 8:
        bullish_score += 3

    if higher_lows >= 8:
        bullish_score += 3

    if bullish_closes >= 8:
        bullish_score += 2

    if closes[-1] > closes[0]:
        bullish_score += 2

    if lower_highs >= 8:
        bearish_score += 3

    if lower_lows >= 8:
        bearish_score += 3

    if bearish_closes >= 8:
        bearish_score += 2

    if closes[-1] < closes[0]:
        bearish_score += 2

    result["bullish_score"] = bullish_score
    result["bearish_score"] = bearish_score

    if (
        bullish_score >= MIN_STRUCTURE_SCORE
        and bullish_score > bearish_score
    ):

        result["direction"] = "BULLISH"
        result["score"] = bullish_score
        result["reason"] = (
            "estructura alcista"
        )

    elif (
        bearish_score >= MIN_STRUCTURE_SCORE
        and bearish_score > bullish_score
    ):

        result["direction"] = "BEARISH"
        result["score"] = bearish_score
        result["reason"] = (
            "estructura bajista"
        )

    else:

        result["direction"] = "NEUTRAL"
        result["score"] = max(
            bullish_score,
            bearish_score,
        )
        result["reason"] = (
            "estructura lateral o mezclada"
        )

    return result


# ============================================================
# CONTINUIDAD
# ============================================================

def check_continuity(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "sin continuidad",
    }

    df = safe_dataframe(df)

    if len(df) < CONTINUITY_LOOKBACK:
        result["reason"] = (
            "pocas velas para continuidad"
        )
        return result

    work = df.tail(
        CONTINUITY_LOOKBACK
    ).reset_index(drop=True)

    highs = work["high"].tolist()
    lows = work["low"].tolist()
    closes = work["close"].tolist()

    if direction == "BULLISH":

        higher_highs = sum(
            1
            for i in range(1, len(highs))
            if highs[i] >= highs[i - 1]
        )

        higher_lows = sum(
            1
            for i in range(1, len(lows))
            if lows[i] >= lows[i - 1]
        )

        price_continues = (
            closes[-1] >= closes[-2]
        )

        score = 0

        if higher_highs >= 3:
            score += 3

        if higher_lows >= 3:
            score += 3

        if price_continues:
            score += 2

        result["score"] = score
        result["valid"] = score >= MIN_CONTINUITY_SCORE
        result["reason"] = (
            f"continuidad alcista score={score}"
        )

        return result

    if direction == "BEARISH":

        lower_highs = sum(
            1
            for i in range(1, len(highs))
            if highs[i] <= highs[i - 1]
        )

        lower_lows = sum(
            1
            for i in range(1, len(lows))
            if lows[i] <= lows[i - 1]
        )

        price_continues = (
            closes[-1] <= closes[-2]
        )

        score = 0

        if lower_highs >= 3:
            score += 3

        if lower_lows >= 3:
            score += 3

        if price_continues:
            score += 2

        result["score"] = score
        result["valid"] = score >= MIN_CONTINUITY_SCORE
        result["reason"] = (
            f"continuidad bajista score={score}"
        )

        return result

    return result


# ============================================================
# AGOTAMIENTO
# ============================================================

def detect_end_of_trend(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "exhausted": False,
        "penalty": 0,
        "reason": "",
    }

    df = safe_dataframe(df)

    if len(df) < 3:
        return result

    work = df.tail(
        EXHAUSTION_LOOKBACK
    ).reset_index(drop=True)

    last = get_candle_data(
        work.iloc[-1]
    )

    previous = get_candle_data(
        work.iloc[-2]
    )

    if last is None or previous is None:
        return result

    penalty = 0
    reasons = []

    if direction == "BULLISH":

        if last["upper_wick_ratio"] >= 0.50:
            penalty += 8
            reasons.append(
                "rechazo superior"
            )

        if last["body_ratio"] < 0.20:
            penalty += 6
            reasons.append(
                "cuerpo muy débil"
            )

        if (
            last["close"]
            < previous["low"]
        ):
            penalty += 10
            reasons.append(
                "pérdida de estructura"
            )

    elif direction == "BEARISH":

        if last["lower_wick_ratio"] >= 0.50:
            penalty += 8
            reasons.append(
                "rechazo inferior"
            )

        if last["body_ratio"] < 0.20:
            penalty += 6
            reasons.append(
                "cuerpo muy débil"
            )

        if (
            last["close"]
            > previous["high"]
        ):
            penalty += 10
            reasons.append(
                "pérdida de estructura"
            )

    result["penalty"] = penalty
    result["exhausted"] = penalty >= 10
    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else "sin agotamiento evidente"
    )

    return result


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def check_support_resistance(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "blocked": False,
        "penalty": 0,
        "reason": "",
        "support": None,
        "resistance": None,
    }

    df = safe_dataframe(df)

    if len(df) < 5:
        return result

    historical = df.iloc[:-1].tail(
        SR_LOOKBACK
    )

    if len(historical) == 0:
        return result

    last = df.iloc[-1]

    price = float(last["close"])

    atr = calculate_atr(
        historical
    )

    if atr <= 0:
        return result

    support = float(
        historical["low"].min()
    )

    resistance = float(
        historical["high"].max()
    )

    tolerance = (
        atr * SR_TOLERANCE_ATR
    )

    result["support"] = support
    result["resistance"] = resistance

    if direction == "BULLISH":

        if (
            resistance - price
            <= tolerance
        ):

            result["blocked"] = True
            result["penalty"] = 12
            result["reason"] = (
                "CALL cerca de resistencia"
            )

    elif direction == "BEARISH":

        if (
            price - support
            <= tolerance
        ):

            result["blocked"] = True
            result["penalty"] = 12
            result["reason"] = (
                "PUT cerca de soporte"
            )

    if not result["reason"]:
        result["reason"] = (
            "sin bloqueo S/R"
        )

    return result


# ============================================================
# CONFIRMACIÓN DE LA VELA
# ============================================================

def confirmation_score(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "score": 0,
        "valid": False,
        "reason": "",
        "range_atr": 0.0,
        "body_atr": 0.0,
    }

    df = safe_dataframe(df)

    if len(df) < 2:
        result["reason"] = (
            "pocas velas para confirmación"
        )
        return result

    candle = get_candle_data(
        df.iloc[-1]
    )

    if candle is None:
        result["reason"] = (
            "vela inválida"
        )
        return result

    atr = calculate_atr(
        df.iloc[:-1]
    )

    if atr <= 0:
        atr = candle["range"]

    if atr <= 0:
        result["reason"] = (
            "ATR inválido"
        )
        return result

    range_atr = (
        candle["range"] / atr
    )

    body_atr = (
        candle["body"] / atr
    )

    result["range_atr"] = range_atr
    result["body_atr"] = body_atr

    score = 0
    reasons = []

    if direction == "BULLISH":

        if candle["close"] > candle["open"]:
            score += 5

        if (
            candle["body_ratio"]
            >= MIN_CONTINUITY_BODY_RATIO
        ):
            score += 5

        if candle["close_position"] >= 0.65:
            score += 4

        if (
            candle["upper_wick_ratio"]
            <= MAX_COUNTER_WICK_RATIO
        ):
            score += 3

    elif direction == "BEARISH":

        if candle["close"] < candle["open"]:
            score += 5

        if (
            candle["body_ratio"]
            >= MIN_CONTINUITY_BODY_RATIO
        ):
            score += 5

        if candle["close_position"] <= 0.35:
            score += 4

        if (
            candle["lower_wick_ratio"]
            <= MAX_COUNTER_WICK_RATIO
        ):
            score += 3

    if range_atr > MAX_CONFIRMATION_RANGE_ATR:
        reasons.append(
            "movimiento demasiado extendido"
        )
        score -= 8

    if body_atr > MAX_CONFIRMATION_BODY_ATR:
        reasons.append(
            "cuerpo demasiado extendido"
        )
        score -= 6

    if candle["body_ratio"] <= INDECISION_BODY_RATIO:
        reasons.append(
            "vela indecisa"
        )
        score -= 8

    result["score"] = max(
        0,
        score,
    )

    result["valid"] = (
        result["score"] >= 12
        and not reasons
    )

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else f"confirmación score={result['score']}"
    )

    return result


# ============================================================
# ANÁLISIS DE VELA EN VIVO
# ============================================================

def analyze_live_candle(
    candle_1m: pd.Series,
) -> Dict[str, Any]:

    result = {
        "direction": "NEUTRAL",
        "state": "INDEFINITION",
        "score": 0,
        "open": None,
        "close": None,
        "high": None,
        "low": None,
        "range": 0.0,
        "body": 0.0,
        "body_ratio": 0.0,
        "upper_wick": 0.0,
        "lower_wick": 0.0,
        "close_position": 0.5,
    }

    data = get_candle_data(
        candle_1m
    )

    if data is None:
        return result

    result.update(data)

    if data["close"] > data["open"]:
        direction = "BULLISH"
    elif data["close"] < data["open"]:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    result["direction"] = direction

    score = 0

    if direction == "BULLISH":

        if data["body_ratio"] >= 0.40:
            score += 5

        if data["close_position"] >= 0.65:
            score += 5

        if data["upper_wick_ratio"] <= 0.30:
            score += 3

    elif direction == "BEARISH":

        if data["body_ratio"] >= 0.40:
            score += 5

        if data["close_position"] <= 0.35:
            score += 5

        if data["lower_wick_ratio"] <= 0.30:
            score += 3

    if data["body_ratio"] <= DOJI_BODY_RATIO:
        result["state"] = "DOJI"

    elif data["body_ratio"] <= INDECISION_BODY_RATIO:
        result["state"] = "INDECISION"

    elif score >= 10:
        result["state"] = "LIVE_CONTINUITY"

    else:
        result["state"] = "MOVEMENT"

    result["score"] = score

    return result


# ============================================================
# ANÁLISIS PRINCIPAL DE MERCADO
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
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "structure": {},
        "continuity": {},
        "confirmation": {},
        "exhaustion": {},
        "support_resistance": {},
    }

    if candle_1m is None:
        result["reason"] = (
            "vela M1 no disponible"
        )
        return result

    current = get_candle_data(
        candle_1m
    )

    if current is None:
        result["reason"] = (
            "OHLC inválido"
        )
        return result

    if "from" in candle_1m.index:
        try:
            result["minute_timestamp"] = int(
                float(candle_1m["from"])
            )
        except Exception:
            pass

    result["minute_open"] = current["open"]
    result["minute_close"] = current["close"]

    historical = safe_dataframe(
        previous_m1
    )

    if len(historical) == 0:
        historical = pd.DataFrame(
            [dict(candle_1m)]
        )

    if len(historical) > 0:

        if (
            "from" not in historical.columns
            or result["minute_timestamp"] is None
            or result["minute_timestamp"]
            not in historical.get(
                "from",
                pd.Series(dtype=float),
            ).values
        ):

            historical = pd.concat(
                [
                    historical,
                    pd.DataFrame(
                        [dict(candle_1m)]
                    ),
                ],
                ignore_index=True,
            )

    historical = safe_dataframe(
        historical
    )

    if len(historical) < 6:

        result["reason"] = (
            "historial insuficiente"
        )

        return result

    structure = analyze_structure(
        historical.iloc[:-1]
    )

    direction = structure["direction"]

    result["structure"] = structure
    result["direction"] = direction

    if direction == "NEUTRAL":

        result["reason"] = (
            "mercado sin estructura clara"
        )

        result["state"] = "RANGE"

        return result

    continuity = check_continuity(
        historical.iloc[:-1],
        direction,
    )

    confirmation = confirmation_score(
        historical,
        direction,
    )

    exhaustion = detect_end_of_trend(
        historical,
        direction,
    )

    support_resistance = check_support_resistance(
        historical,
        direction,
    )

    result["continuity"] = continuity
    result["confirmation"] = confirmation
    result["exhaustion"] = exhaustion
    result[
        "support_resistance"
    ] = support_resistance

    # --------------------------------------------------------
    # SCORE BASE
    # --------------------------------------------------------

    score = 0

    # Estructura
    score += min(
        30,
        structure["score"] * 3,
    )

    # Continuidad
    score += min(
        25,
        continuity["score"] * 3,
    )

    # Confirmación
    score += min(
        30,
        confirmation["score"] * 2,
    )

    # Penalización agotamiento
    score -= exhaustion["penalty"]

    # Penalización S/R
    score -= support_resistance["penalty"]

    score = max(
        0,
        min(MAX_SCORE, score),
    )

    result["score"] = score

    # --------------------------------------------------------
    # BLOQUEOS
    # --------------------------------------------------------

    if not continuity["valid"]:

        result["reason"] = (
            "sin continuidad suficiente"
        )

        result["state"] = "NO_CONTINUITY"

        return result

    if exhaustion["exhausted"]:

        result["reason"] = (
            f"tendencia agotada: "
            f"{exhaustion['reason']}"
        )

        result["state"] = "EXHAUSTION"

        return result

    if support_resistance["blocked"]:

        result["reason"] = (
            support_resistance["reason"]
        )

        result["state"] = "SUPPORT_RESISTANCE"

        return result

    if not confirmation["valid"]:

        result["reason"] = (
            f"confirmación débil: "
            f"{confirmation['reason']}"
        )

        result["state"] = "WEAK_CONFIRMATION"

        return result

    if score < MIN_FINAL_SCORE:

        result["reason"] = (
            f"calidad insuficiente score={score}"
        )

        result["state"] = "LOW_SCORE"

        return result

    # --------------------------------------------------------
    # SEÑAL FINAL
    # --------------------------------------------------------

    if direction == "BULLISH":

        result["signal"] = "call"
        result["valid"] = True
        result["state"] = "BULLISH_CONTINUITY"

        result["reason"] = (
            f"CALL continuidad alcista "
            f"score={score}"
        )

        return result

    if direction == "BEARISH":

        result["signal"] = "put"
        result["valid"] = True
        result["state"] = "BEARISH_CONTINUITY"

        result["reason"] = (
            f"PUT continuidad bajista "
            f"score={score}"
        )

        return result

    return result


# ============================================================
# COMPATIBILIDAD
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )


def build_n1_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )


def get_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    ).get("signal")


def signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
        previous_m1,
    )


def get_m1_direction(
    candle_1m=None,
):

    if candle_1m is None:
        return None

    try:

        if (
            hasattr(candle_1m, "iloc")
            and hasattr(candle_1m, "columns")
        ):

            if len(candle_1m) == 0:
                return None

            candle_1m = candle_1m.iloc[-1]

        opening = float(
            candle_1m.get("open")
        )

        closing = float(
            candle_1m.get("close")
        )

    except Exception:

        return None

    if closing > opening:
        return "BULLISH"

    if closing < opening:
        return "BEARISH"

    return "NEUTRAL"


def check_pattern(
    candles_5s=None,
):

    return None


if __name__ == "__main__":

    print("strategy.py cargado correctamente.")
    print(
        "Estrategia: MULTI MARKET CONTINUITY"
    )
