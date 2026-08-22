from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1 - SOLO REVERSIÓN
# ============================================================
#
# La última vela del historial es la VELA DE CONFIRMACIÓN.
#
# CALL:
#   Tendencia bajista previa
#   + llegada a zona baja / soporte
#   + agotamiento o rechazo inferior
#   + confirmación alcista
#   = posible REVERSIÓN ALCISTA
#
# PUT:
#   Tendencia alcista previa
#   + llegada a zona alta / resistencia
#   + agotamiento o rechazo superior
#   + confirmación bajista
#   = posible REVERSIÓN BAJISTA
#
# IMPORTANTE:
# Esta estrategia NO genera señales de continuidad.
# La señal obtenida en la vela cerrada debe ejecutarse
# exclusivamente en la siguiente vela N+1.
# ============================================================


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

TREND_LOOKBACK = 15
REVERSAL_CONTEXT_LOOKBACK = 20
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14


# ============================================================
# CONFIGURACIÓN DE VELAS
# ============================================================

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
WEAKNESS_BODY_RATIO = 0.35

MIN_REVERSAL_BODY_RATIO = 0.35
STRONG_BODY_RATIO = 0.55

MAX_CONFIRMATION_RANGE_ATR = 1.80
MAX_CONFIRMATION_BODY_ATR = 1.40

MAX_COUNTER_WICK_RATIO = 0.45

# Mecha mínima para considerar rechazo
MIN_REJECTION_WICK_RATIO = 0.25

# Tolerancia de cercanía a soporte/resistencia
SR_TOLERANCE_ATR = 0.50

# Para considerar que el precio está cerca de un extremo
EXTREME_TOLERANCE_ATR = 0.75


# ============================================================
# SCORES
# ============================================================

MAX_SCORE = 100

MIN_STRUCTURE_SCORE = 6
MIN_REVERSAL_SCORE = 70


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        result = float(value)

        if pd.isna(result):
            return None

        return result

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

    result = df.copy()

    # Compatibilidad con APIs que usan max/min
    if "high" not in result.columns and "max" in result.columns:
        result["high"] = result["max"]

    if "low" not in result.columns and "min" in result.columns:
        result["low"] = result["min"]

    required = {"open", "close", "high", "low"}

    if not required.issubset(result.columns):
        return pd.DataFrame()

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

        result["from"] = pd.to_numeric(
            result["from"],
            errors="coerce",
        )

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
# ANALIZAR TENDENCIA PREVIA
# ============================================================
#
# IMPORTANTE:
# Esta función solamente identifica el contexto anterior.
# NO genera una operación de continuidad.
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

    highs = work["high"].tolist()
    lows = work["low"].tolist()
    closes = work["close"].tolist()

    bullish_score = 0
    bearish_score = 0

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

    bullish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] > closes[i - 1]
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

    bearish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] < closes[i - 1]
    )

    # --------------------------------------------------------
    # ESTRUCTURA ALCISTA
    # --------------------------------------------------------

    if higher_highs >= 7:
        bullish_score += 3

    if higher_lows >= 7:
        bullish_score += 3

    if bullish_closes >= 7:
        bullish_score += 2

    if closes[-1] > closes[0]:
        bullish_score += 2

    # --------------------------------------------------------
    # ESTRUCTURA BAJISTA
    # --------------------------------------------------------

    if lower_highs >= 7:
        bearish_score += 3

    if lower_lows >= 7:
        bearish_score += 3

    if bearish_closes >= 7:
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
        result["reason"] = "tendencia previa alcista"

    elif (
        bearish_score >= MIN_STRUCTURE_SCORE
        and bearish_score > bullish_score
    ):

        result["direction"] = "BEARISH"
        result["score"] = bearish_score
        result["reason"] = "tendencia previa bajista"

    else:

        result["direction"] = "NEUTRAL"
        result["score"] = max(
            bullish_score,
            bearish_score,
        )
        result["reason"] = "sin tendencia previa clara"

    return result


# ============================================================
# SOPORTE / RESISTENCIA PARA REVERSIÓN
# ============================================================
#
# A diferencia de la estrategia anterior:
#
# Resistencia + tendencia alcista = posible zona para PUT
# Soporte + tendencia bajista = posible zona para CALL
#
# S/R ya NO es un bloqueo automático.
# ============================================================

def check_reversal_zone(
    df: pd.DataFrame,
    trend_direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "sin zona de reversión",
        "support": None,
        "resistance": None,
        "zone": None,
        "distance_to_support": None,
        "distance_to_resistance": None,
    }

    df = safe_dataframe(df)

    if len(df) < 6:
        result["reason"] = "historial insuficiente para zonas"
        return result

    # Se excluye la última vela de confirmación
    historical = df.iloc[:-1].tail(
        SR_LOOKBACK
    )

    if len(historical) < 3:
        result["reason"] = "poco historial para zonas"
        return result

    confirmation = get_candle_data(
        df.iloc[-1]
    )

    if confirmation is None:
        result["reason"] = "vela de confirmación inválida"
        return result

    atr = calculate_atr(
        historical
    )

    if atr <= 0:
        atr = confirmation["range"]

    if atr <= 0:
        result["reason"] = "ATR inválido"
        return result

    support = float(
        historical["low"].min()
    )

    resistance = float(
        historical["high"].max()
    )

    price = confirmation["close"]

    distance_to_support = abs(
        price - support
    )

    distance_to_resistance = abs(
        resistance - price
    )

    result["support"] = support
    result["resistance"] = resistance
    result["distance_to_support"] = distance_to_support
    result["distance_to_resistance"] = distance_to_resistance

    tolerance = max(
        atr * SR_TOLERANCE_ATR,
        confirmation["range"] * 0.50,
    )

    # --------------------------------------------------------
    # REVERSIÓN BAJISTA
    # Tendencia previa alcista cerca de resistencia
    # --------------------------------------------------------

    if trend_direction == "BULLISH":

        touched_resistance = (
            confirmation["high"]
            >= resistance - tolerance
        )

        close_near_resistance = (
            price
            >= resistance - tolerance
        )

        if touched_resistance or close_near_resistance:

            score = 0

            if touched_resistance:
                score += 10

            if close_near_resistance:
                score += 5

            result["valid"] = True
            result["score"] = score
            result["zone"] = "RESISTANCE"
            result["reason"] = (
                "zona alta/resistencia apta "
                "para reversión bajista"
            )

            return result

    # --------------------------------------------------------
    # REVERSIÓN ALCISTA
    # Tendencia previa bajista cerca de soporte
    # --------------------------------------------------------

    elif trend_direction == "BEARISH":

        touched_support = (
            confirmation["low"]
            <= support + tolerance
        )

        close_near_support = (
            price
            <= support + tolerance
        )

        if touched_support or close_near_support:

            score = 0

            if touched_support:
                score += 10

            if close_near_support:
                score += 5

            result["valid"] = True
            result["score"] = score
            result["zone"] = "SUPPORT"
            result["reason"] = (
                "zona baja/soporte apta "
                "para reversión alcista"
            )

            return result

    return result


# ============================================================
# DETECCIÓN DE AGOTAMIENTO / RECHAZO
# ============================================================
#
# Tendencia alcista:
#   buscamos agotamiento arriba y rechazo superior
#
# Tendencia bajista:
#   buscamos agotamiento abajo y rechazo inferior
# ============================================================

def detect_reversal_exhaustion(
    df: pd.DataFrame,
    trend_direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "sin agotamiento de reversión",
        "rejection": False,
        "weakness": False,
        "failed_continuation": False,
    }

    df = safe_dataframe(df)

    if len(df) < 3:
        result["reason"] = "pocas velas para agotamiento"
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
        result["reason"] = "velas inválidas"
        return result

    score = 0
    reasons = []

    # ========================================================
    # POSIBLE REVERSIÓN BAJISTA
    # ========================================================

    if trend_direction == "BULLISH":

        rejection = (
            last["upper_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        )

        weakness = (
            last["body_ratio"]
            <= WEAKNESS_BODY_RATIO
        )

        failed_continuation = (
            last["close"]
            <= previous["close"]
        )

        if rejection:
            score += 12
            reasons.append("rechazo superior")

        if weakness:
            score += 8
            reasons.append("debilidad alcista")

        if failed_continuation:
            score += 8
            reasons.append("pérdida de impulso alcista")

        # Si hizo máximo superior pero cerró claramente por debajo
        if (
            last["high"] > previous["high"]
            and last["close"] < previous["close"]
        ):
            score += 12
            reasons.append("barrida superior y cierre débil")

        result["rejection"] = rejection
        result["weakness"] = weakness
        result["failed_continuation"] = failed_continuation

    # ========================================================
    # POSIBLE REVERSIÓN ALCISTA
    # ========================================================

    elif trend_direction == "BEARISH":

        rejection = (
            last["lower_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        )

        weakness = (
            last["body_ratio"]
            <= WEAKNESS_BODY_RATIO
        )

        failed_continuation = (
            last["close"]
            >= previous["close"]
        )

        if rejection:
            score += 12
            reasons.append("rechazo inferior")

        if weakness:
            score += 8
            reasons.append("debilidad bajista")

        if failed_continuation:
            score += 8
            reasons.append("pérdida de impulso bajista")

        # Si hizo mínimo inferior pero cerró claramente por encima
        if (
            last["low"] < previous["low"]
            and last["close"] > previous["close"]
        ):
            score += 12
            reasons.append("barrida inferior y cierre fuerte")

        result["rejection"] = rejection
        result["weakness"] = weakness
        result["failed_continuation"] = failed_continuation

    result["score"] = min(35, score)

    result["valid"] = score >= 12

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else "sin agotamiento claro"
    )

    return result


# ============================================================
# CONFIRMACIÓN DE REVERSIÓN
# ============================================================
#
# La confirmación debe ir CONTRA la tendencia previa.
#
# Tendencia alcista -> buscamos vela BAJISTA -> PUT
# Tendencia bajista -> buscamos vela ALCISTA -> CALL
# ============================================================

def reversal_confirmation_score(
    df: pd.DataFrame,
    trend_direction: str,
) -> Dict[str, Any]:

    result = {
        "score": 0,
        "valid": False,
        "reason": "",
        "reversal_direction": "NEUTRAL",
        "range_atr": 0.0,
        "body_atr": 0.0,
    }

    df = safe_dataframe(df)

    if len(df) < 3:
        result["reason"] = "pocas velas para confirmación"
        return result

    candle = get_candle_data(
        df.iloc[-1]
    )

    previous = get_candle_data(
        df.iloc[-2]
    )

    if candle is None or previous is None:
        result["reason"] = "vela inválida"
        return result

    atr = calculate_atr(
        df.iloc[:-1]
    )

    if atr <= 0:
        atr = candle["range"]

    if atr <= 0:
        result["reason"] = "ATR inválido"
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

    # ========================================================
    # TENDENCIA PREVIA ALCISTA -> CONFIRMACIÓN BAJISTA -> PUT
    # ========================================================

    if trend_direction == "BULLISH":

        result["reversal_direction"] = "BEARISH"

        if candle["close"] < candle["open"]:
            score += 15
        else:
            reasons.append("confirmación no es bajista")

        if (
            candle["body_ratio"]
            >= MIN_REVERSAL_BODY_RATIO
        ):
            score += 10
        else:
            reasons.append("cuerpo bajista débil")

        if candle["close_position"] <= 0.45:
            score += 8

        if (
            candle["lower_wick_ratio"]
            <= MAX_COUNTER_WICK_RATIO
        ):
            score += 5

        # Cierra por debajo del cierre anterior
        if candle["close"] < previous["close"]:
            score += 7

        # Patrón engulfing bajista simple
        if (
            candle["open"] >= previous["close"]
            and candle["close"] <= previous["open"]
        ):
            score += 8

    # ========================================================
    # TENDENCIA PREVIA BAJISTA -> CONFIRMACIÓN ALCISTA -> CALL
    # ========================================================

    elif trend_direction == "BEARISH":

        result["reversal_direction"] = "BULLISH"

        if candle["close"] > candle["open"]:
            score += 15
        else:
            reasons.append("confirmación no es alcista")

        if (
            candle["body_ratio"]
            >= MIN_REVERSAL_BODY_RATIO
        ):
            score += 10
        else:
            reasons.append("cuerpo alcista débil")

        if candle["close_position"] >= 0.55:
            score += 8

        if (
            candle["upper_wick_ratio"]
            <= MAX_COUNTER_WICK_RATIO
        ):
            score += 5

        # Cierra por encima del cierre anterior
        if candle["close"] > previous["close"]:
            score += 7

        # Patrón engulfing alcista simple
        if (
            candle["open"] <= previous["close"]
            and candle["close"] >= previous["open"]
        ):
            score += 8

    else:

        result["reason"] = "sin tendencia previa"

        return result

    # Evitar velas exageradamente extendidas
    if range_atr > MAX_CONFIRMATION_RANGE_ATR:

        score -= 8
        reasons.append("rango demasiado extendido")

    if body_atr > MAX_CONFIRMATION_BODY_ATR:

        score -= 6
        reasons.append("cuerpo demasiado extendido")

    if candle["body_ratio"] <= INDECISION_BODY_RATIO:

        score -= 10

        if "vela indecisa" not in reasons:
            reasons.append("vela indecisa")

    result["score"] = max(
        0,
        min(55, score),
    )

    # Una vela debe estar realmente en dirección contraria
    opposite_direction = False

    if trend_direction == "BULLISH":
        opposite_direction = (
            candle["close"] < candle["open"]
        )

    elif trend_direction == "BEARISH":
        opposite_direction = (
            candle["close"] > candle["open"]
        )

    result["valid"] = (
        opposite_direction
        and result["score"] >= 25
        and "vela indecisa" not in reasons
    )

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else (
            f"confirmación de reversión "
            f"score={result['score']}"
        )
    )

    return result


# ============================================================
# CONFIRMACIÓN DE QUIEBRE DE LA MICROESTRUCTURA
# ============================================================

def check_micro_reversal(
    df: pd.DataFrame,
    trend_direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "sin quiebre de microestructura",
    }

    df = safe_dataframe(df)

    if len(df) < 4:
        result["reason"] = "pocas velas para microestructura"
        return result

    last = get_candle_data(
        df.iloc[-1]
    )

    previous = get_candle_data(
        df.iloc[-2]
    )

    before_previous = get_candle_data(
        df.iloc[-3]
    )

    if (
        last is None
        or previous is None
        or before_previous is None
    ):
        result["reason"] = "datos inválidos"
        return result

    score = 0
    reasons = []

    # --------------------------------------------------------
    # Tendencia alcista -> buscamos giro bajista
    # --------------------------------------------------------

    if trend_direction == "BULLISH":

        if last["close"] < previous["low"]:
            score += 15
            reasons.append("cierre bajo mínimo previo")

        elif last["close"] < previous["close"]:
            score += 8
            reasons.append("cierre bajista contra impulso")

        if (
            previous["high"]
            >= before_previous["high"]
            and last["high"] <= previous["high"]
        ):
            score += 5
            reasons.append("fallo en nuevos máximos")

    # --------------------------------------------------------
    # Tendencia bajista -> buscamos giro alcista
    # --------------------------------------------------------

    elif trend_direction == "BEARISH":

        if last["close"] > previous["high"]:
            score += 15
            reasons.append("cierre sobre máximo previo")

        elif last["close"] > previous["close"]:
            score += 8
            reasons.append("cierre alcista contra impulso")

        if (
            previous["low"]
            <= before_previous["low"]
            and last["low"] >= previous["low"]
        ):
            score += 5
            reasons.append("fallo en nuevos mínimos")

    result["score"] = min(20, score)
    result["valid"] = score >= 8

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else "microestructura sin reversión"
    )

    return result


# ============================================================
# COMPATIBILIDAD:
# DETECCIÓN DE AGOTAMIENTO
# ============================================================

def detect_end_of_trend(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    reversal = detect_reversal_exhaustion(
        df,
        direction,
    )

    return {
        "exhausted": reversal["valid"],
        "penalty": 0,
        "reason": reversal["reason"],
        "score": reversal["score"],
    }


# ============================================================
# COMPATIBILIDAD:
# SOPORTE / RESISTENCIA
# ============================================================

def check_support_resistance(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    zone = check_reversal_zone(
        df,
        direction,
    )

    return {
        "blocked": False,
        "penalty": 0,
        "reason": zone["reason"],
        "support": zone["support"],
        "resistance": zone["resistance"],
        "valid_reversal_zone": zone["valid"],
        "score": zone["score"],
        "zone": zone["zone"],
    }


# ============================================================
# COMPATIBILIDAD:
# CONFIRMACIÓN
# ============================================================

def confirmation_score(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    return reversal_confirmation_score(
        df,
        direction,
    )


# ============================================================
# ANÁLISIS DE VELA EN VIVO
# ============================================================
#
# Esto es solamente informativo.
# NO debe ejecutar una operación.
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

    if data["body_ratio"] >= MIN_REVERSAL_BODY_RATIO:
        score += 5

    if direction == "BULLISH":

        if data["close_position"] >= 0.60:
            score += 5

        if (
            data["lower_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 3

    elif direction == "BEARISH":

        if data["close_position"] <= 0.40:
            score += 5

        if (
            data["upper_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 3

    if data["body_ratio"] <= DOJI_BODY_RATIO:

        result["state"] = "DOJI"

    elif data["body_ratio"] <= INDECISION_BODY_RATIO:

        result["state"] = "INDECISION"

    elif score >= 8:

        result["state"] = "POSSIBLE_REVERSAL"

    else:

        result["state"] = "MOVEMENT"

    result["score"] = score

    return result


# ============================================================
# ANÁLISIS PRINCIPAL - SOLO REVERSIÓN
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
        "trend_direction": "NEUTRAL",
        "reversal_direction": "NEUTRAL",
        "state": "NO_SIGNAL",
        "reason": "sin análisis",
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "structure": {},
        "reversal_zone": {},
        "exhaustion": {},
        "confirmation": {},
        "micro_reversal": {},
        "support_resistance": {},
        "execution": "NEXT_CANDLE_N1",
    }

    if candle_1m is None:

        result["reason"] = "vela M1 no disponible"

        return result

    current = get_candle_data(
        candle_1m
    )

    if current is None:

        result["reason"] = "OHLC inválido"

        return result

    # --------------------------------------------------------
    # DATOS DE LA VELA DE CONFIRMACIÓN
    # --------------------------------------------------------

    if "from" in candle_1m.index:

        try:
            result["minute_timestamp"] = int(
                float(candle_1m["from"])
            )

        except Exception:
            pass

    result["minute_open"] = current["open"]
    result["minute_close"] = current["close"]

    # --------------------------------------------------------
    # CONSTRUIR HISTORIAL
    # --------------------------------------------------------

    historical = safe_dataframe(
        previous_m1
    )

    if len(historical) == 0:

        historical = pd.DataFrame(
            [dict(candle_1m)]
        )

    else:

        should_append = True

        if (
            "from" in historical.columns
            and result["minute_timestamp"] is not None
        ):

            timestamps = pd.to_numeric(
                historical["from"],
                errors="coerce",
            )

            if (
                timestamps
                == result["minute_timestamp"]
            ).any():

                should_append = False

        if should_append:

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

    if len(historical) < 8:

        result["reason"] = "historial insuficiente"

        return result

    # ========================================================
    # MUY IMPORTANTE:
    #
    # La última vela es la confirmación.
    # La tendencia se analiza SIN usar esa última vela.
    #
    # Esto evita que una vela de reversión sea interpretada
    # como parte de la tendencia previa.
    # ========================================================

    trend_history = historical.iloc[:-1].copy()

    if len(trend_history) < 6:

        result["reason"] = (
            "historial insuficiente antes de confirmación"
        )

        return result

    # --------------------------------------------------------
    # 1. TENDENCIA PREVIA
    # --------------------------------------------------------

    structure = analyze_structure(
        trend_history
    )

    trend_direction = structure["direction"]

    result["structure"] = structure
    result["trend_direction"] = trend_direction
    result["direction"] = trend_direction

    if trend_direction == "NEUTRAL":

        result["reason"] = (
            "sin tendencia previa clara para revertir"
        )

        result["state"] = "NO_TREND"

        return result

    # --------------------------------------------------------
    # 2. ZONA DE REVERSIÓN
    # --------------------------------------------------------

    reversal_zone = check_reversal_zone(
        historical,
        trend_direction,
    )

    result["reversal_zone"] = reversal_zone

    # Compatibilidad
    result["support_resistance"] = {
        "blocked": False,
        "penalty": 0,
        "reason": reversal_zone["reason"],
        "support": reversal_zone["support"],
        "resistance": reversal_zone["resistance"],
        "valid_reversal_zone": reversal_zone["valid"],
        "score": reversal_zone["score"],
        "zone": reversal_zone["zone"],
    }

    if not reversal_zone["valid"]:

        result["reason"] = (
            "no está en zona válida de reversión: "
            f"{reversal_zone['reason']}"
        )

        result["state"] = "NO_REVERSAL_ZONE"

        return result

    # --------------------------------------------------------
    # 3. AGOTAMIENTO / RECHAZO
    # --------------------------------------------------------

    exhaustion = detect_reversal_exhaustion(
        historical,
        trend_direction,
    )

    result["exhaustion"] = exhaustion

    if not exhaustion["valid"]:

        result["reason"] = (
            "sin agotamiento o rechazo suficiente: "
            f"{exhaustion['reason']}"
        )

        result["state"] = "NO_EXHAUSTION"

        return result

    # --------------------------------------------------------
    # 4. CONFIRMACIÓN CONTRARIA A LA TENDENCIA
    # --------------------------------------------------------

    confirmation = reversal_confirmation_score(
        historical,
        trend_direction,
    )

    result["confirmation"] = confirmation
    result["reversal_direction"] = (
        confirmation["reversal_direction"]
    )

    if not confirmation["valid"]:

        result["reason"] = (
            "confirmación de reversión inválida: "
            f"{confirmation['reason']}"
        )

        result["state"] = "WEAK_REVERSAL_CONFIRMATION"

        return result

    # --------------------------------------------------------
    # 5. QUIEBRE DE MICROESTRUCTURA
    # --------------------------------------------------------

    micro_reversal = check_micro_reversal(
        historical,
        trend_direction,
    )

    result["micro_reversal"] = micro_reversal

    # No bloqueamos automáticamente una reversión si todavía
    # no hay quiebre fuerte, pero su score influye en calidad.

    # --------------------------------------------------------
    # SCORE TOTAL DE REVERSIÓN
    # --------------------------------------------------------

    score = 0

    # Fuerza de tendencia previa: máximo 25
    score += min(
        25,
        structure["score"] * 2.5,
    )

    # Zona extrema: máximo 15
    score += min(
        15,
        reversal_zone["score"],
    )

    # Agotamiento/rechazo: máximo 30
    score += min(
        30,
        exhaustion["score"],
    )

    # Confirmación contraria: máximo 25
    score += min(
        25,
        confirmation["score"] / 2,
    )

    # Microestructura: máximo 10
    score += min(
        10,
        micro_reversal["score"] / 2,
    )

    score = max(
        0,
        min(MAX_SCORE, int(score)),
    )

    result["score"] = score

    if score < MIN_REVERSAL_SCORE:

        result["reason"] = (
            f"reversión detectada pero calidad insuficiente "
            f"score={score}"
        )

        result["state"] = "LOW_REVERSAL_SCORE"

        return result

    # ========================================================
    # SEÑAL FINAL
    # ========================================================
    #
    # Tendencia alcista previa
    # -> reversión bajista
    # -> PUT
    #
    # Tendencia bajista previa
    # -> reversión alcista
    # -> CALL
    # ========================================================

    if trend_direction == "BULLISH":

        result["signal"] = "put"
        result["valid"] = True
        result["direction"] = "BEARISH"
        result["reversal_direction"] = "BEARISH"
        result["state"] = "BEARISH_REVERSAL"

        result["reason"] = (
            f"PUT REVERSIÓN: tendencia alcista previa + "
            f"resistencia + agotamiento/rechazo + "
            f"confirmación bajista | score={score} | "
            f"ejecutar en N+1"
        )

        return result

    if trend_direction == "BEARISH":

        result["signal"] = "call"
        result["valid"] = True
        result["direction"] = "BULLISH"
        result["reversal_direction"] = "BULLISH"
        result["state"] = "BULLISH_REVERSAL"

        result["reason"] = (
            f"CALL REVERSIÓN: tendencia bajista previa + "
            f"soporte + agotamiento/rechazo + "
            f"confirmación alcista | score={score} | "
            f"ejecutar en N+1"
        )

        return result

    return result


# ============================================================
# COMPATIBILIDAD CON BOT.PY
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m=candle_1m,
        candles_5s=candles_5s,
        previous_m1=previous_m1,
    )


def build_n1_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    result = analyze_market(
        candle_1m=candle_1m,
        candles_5s=candles_5s,
        previous_m1=previous_m1,
    )

    result["execution"] = "NEXT_CANDLE_N1"

    return result


def get_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    result = analyze_market(
        candle_1m=candle_1m,
        candles_5s=candles_5s,
        previous_m1=previous_m1,
    )

    return result.get("signal")


def signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return get_signal(
        candle_1m=candle_1m,
        candles_5s=candles_5s,
        previous_m1=previous_m1,
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

    # La estrategia principal usa velas M1 cerradas.
    # Esta función se mantiene para compatibilidad.
    return None


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    print("strategy.py cargado correctamente.")
    print("Estrategia: SOLO REVERSIÓN M1")
    print("CALL = reversión alcista desde soporte")
    print("PUT  = reversión bajista desde resistencia")
    print("Ejecución: exclusivamente en N+1")
