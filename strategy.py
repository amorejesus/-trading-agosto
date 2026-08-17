import time


# ============================================================
# CONFIGURACIÓN
# ============================================================

# La estrategia trabaja ÚNICAMENTE con velas M1.
TIMEFRAME_SECONDS = 60

# Tolerancias de clasificación de la vela.
DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
FORCE_BODY_RATIO = 0.60

CLOSE_EXTREME = 0.75
LONG_WICK_RATIO = 0.30


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_timestamp(candle):
    if not isinstance(candle, dict):
        return None

    for key in ("from", "timestamp", "time"):
        value = candle.get(key)

        try:
            return int(float(value))
        except (TypeError, ValueError):
            continue

    return None


def _normalize_candle(candle):
    if not isinstance(candle, dict):
        return None

    opening = _to_float(candle.get("open"))
    high = _to_float(candle.get("max", candle.get("high")))
    low = _to_float(candle.get("min", candle.get("low")))
    closing = _to_float(candle.get("close"))

    if None in (opening, high, low, closing):
        return None

    if high < low:
        return None

    if high < max(opening, closing):
        return None

    if low > min(opening, closing):
        return None

    return {
        "from": _to_timestamp(candle),
        "open": opening,
        "high": high,
        "low": low,
        "close": closing,
    }


def _is_closed(candle, now=None):
    """
    Una vela M1 está cerrada únicamente cuando ha terminado
    completamente su intervalo de 60 segundos.
    """

    timestamp = _to_timestamp(candle)

    if timestamp is None:
        return False

    if now is None:
        now = time.time()

    return now >= timestamp + TIMEFRAME_SECONDS


def _direction_from_values(opening, closing):
    if closing > opening:
        return "bullish"

    if closing < opening:
        return "bearish"

    return "neutral"


def _signal_from_direction(direction):
    if direction == "bullish":
        return "call"

    if direction == "bearish":
        return "put"

    return None


# ============================================================
# DIRECCIÓN M1
# ============================================================

def get_m1_direction(candle):
    """
    Devuelve la dirección de una vela M1.

    bullish  = cierre > apertura
    bearish  = cierre < apertura
    neutral  = apertura == cierre
    """

    normalized = _normalize_candle(candle)

    if normalized is None:
        return None

    return _direction_from_values(
        normalized["open"],
        normalized["close"],
    )


# ============================================================
# ANÁLISIS DE LA VELA
# ============================================================

def _analyze_candle(candle, previous_candle=None):
    current = _normalize_candle(candle)

    if current is None:
        return None

    opening = current["open"]
    high = current["high"]
    low = current["low"]
    closing = current["close"]

    candle_range = high - low
    body = abs(closing - opening)

    if candle_range <= 0:
        return {
            "direction": "neutral",
            "body": 0.0,
            "range": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "close_position": 0.5,
            "state": "DOJI",
            "signal": None,
            "reason": "RANGO CERO",
        }

    body_ratio = body / candle_range

    upper_wick = high - max(opening, closing)
    lower_wick = min(opening, closing) - low

    close_position = (closing - low) / candle_range

    direction = _direction_from_values(
        opening,
        closing,
    )

    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    # ========================================================
    # DOJI
    # ========================================================

    if body_ratio <= DOJI_BODY_RATIO:
        return {
            "direction": direction,
            "body": body,
            "range": candle_range,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "close_position": close_position,
            "state": "DOJI",
            "signal": None,
            "reason": "DOJI / INDECISION EXTREMA",
        }

    # ========================================================
    # INDECISIÓN
    # ========================================================

    if body_ratio <= INDECISION_BODY_RATIO:
        return {
            "direction": direction,
            "body": body,
            "range": candle_range,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "close_position": close_position,
            "state": "INDECISION",
            "signal": None,
            "reason": "CUERPO PEQUEÑO / INDECISIÓN",
        }

    # ========================================================
    # REVERSIÓN
    # ========================================================

    previous = _normalize_candle(previous_candle)

    if previous is not None:
        previous_direction = _direction_from_values(
            previous["open"],
            previous["close"],
        )

        if (
            previous_direction == "bearish"
            and direction == "bullish"
            and close_position >= CLOSE_EXTREME
            and body_ratio >= 0.35
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "REVERSAL",
                "signal": "call",
                "reason": "REVERSIÓN ALCISTA",
            }

        if (
            previous_direction == "bullish"
            and direction == "bearish"
            and close_position <= (1.0 - CLOSE_EXTREME)
            and body_ratio >= 0.35
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "REVERSAL",
                "signal": "put",
                "reason": "REVERSIÓN BAJISTA",
            }

    # ========================================================
    # FUERZA
    # ========================================================

    if body_ratio >= FORCE_BODY_RATIO:

        if direction == "bullish" and close_position >= CLOSE_EXTREME:
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "FUERZA",
                "signal": "call",
                "reason": "CUERPO ALCISTA FUERTE",
            }

        if direction == "bearish" and close_position <= (1.0 - CLOSE_EXTREME):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "FUERZA",
                "signal": "put",
                "reason": "CUERPO BAJISTA FUERTE",
            }

    # ========================================================
    # CONTINUIDAD
    # ========================================================

    if previous is not None:
        previous_direction = _direction_from_values(
            previous["open"],
            previous["close"],
        )

        if (
            direction == "bullish"
            and previous_direction == "bullish"
            and body_ratio >= 0.35
            and close_position >= 0.60
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "CONTINUITY",
                "signal": "call",
                "reason": "CONTINUIDAD ALCISTA",
            }

        if (
            direction == "bearish"
            and previous_direction == "bearish"
            and body_ratio >= 0.35
            and close_position <= 0.40
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "CONTINUITY",
                "signal": "put",
                "reason": "CONTINUIDAD BAJISTA",
            }

    # ========================================================
    # DEBILIDAD
    # ========================================================

    if direction == "bullish":

        if (
            upper_wick_ratio >= LONG_WICK_RATIO
            and upper_wick > lower_wick
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "WEAKNESS",
                "signal": "call",
                "reason": "IMPULSO ALCISTA CON DEBILIDAD",
            }

    if direction == "bearish":

        if (
            lower_wick_ratio >= LONG_WICK_RATIO
            and lower_wick > upper_wick
        ):
            return {
                "direction": direction,
                "body": body,
                "range": candle_range,
                "body_ratio": body_ratio,
                "upper_wick": upper_wick,
                "lower_wick": lower_wick,
                "close_position": close_position,
                "state": "WEAKNESS",
                "signal": "put",
                "reason": "IMPULSO BAJISTA CON DEBILIDAD",
            }

    # ========================================================
    # DEBILIDAD / ESTADO NORMAL
    # ========================================================

    if direction == "bullish":
        signal = "call"
        reason = "CIERRE ALCISTA"

    elif direction == "bearish":
        signal = "put"
        reason = "CIERRE BAJISTA"

    else:
        signal = None
        reason = "SIN DIRECCIÓN"

    return {
        "direction": direction,
        "body": body,
        "range": candle_range,
        "body_ratio": body_ratio,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "close_position": close_position,
        "state": "WEAKNESS",
        "signal": signal,
        "reason": reason,
    }


# ============================================================
# OBTENER ÚLTIMA VELA M1 CERRADA
# ============================================================

def _get_last_closed_candle(candles):
    if not isinstance(candles, (list, tuple)):
        return None, None

    normalized = []

    for candle in candles:
        item = _normalize_candle(candle)

        if item is None:
            continue

        normalized.append(item)

    if not normalized:
        return None, None

    normalized.sort(
        key=lambda x: (
            x["from"]
            if x["from"] is not None
            else 0
        )
    )

    now = time.time()

    closed = [
        candle
        for candle in normalized
        if _is_closed(candle, now)
    ]

    if not closed:
        return None, None

    current = closed[-1]

    previous = None

    if len(closed) >= 2:
        previous = closed[-2]

    return current, previous


# ============================================================
# ANÁLISIS COMPLETO
# ============================================================

def get_strategy_analysis(candles):
    """
    Analiza exclusivamente la última vela M1 COMPLETAMENTE CERRADA.

    La vela M1 actualmente abierta nunca se utiliza para
    generar una señal definitiva.
    """

    current, previous = _get_last_closed_candle(candles)

    if current is None:
        return {
            "valid": False,
            "closed": False,
            "signal": None,
            "state": None,
            "direction": None,
            "reason": "NO EXISTE VELA M1 CERRADA",
            "body": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "close_position": 0.0,
            "last_5s_close": None,
            "range_ok": False,
        }

    analysis = _analyze_candle(
        current,
        previous,
    )

    if analysis is None:
        return {
            "valid": False,
            "closed": True,
            "signal": None,
            "state": None,
            "direction": None,
            "reason": "VELA M1 INVALIDA",
            "body": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "close_position": 0.0,
            "last_5s_close": None,
            "range_ok": False,
        }

    return {
        "valid": True,
        "closed": True,

        "signal": analysis["signal"],

        "state": analysis["state"],
        "direction": analysis["direction"],

        "body": analysis["body"],
        "range": analysis["range"],
        "body_ratio": analysis["body_ratio"],

        "upper_wick": analysis["upper_wick"],
        "lower_wick": analysis["lower_wick"],

        "close_position": analysis["close_position"],

        "last_5s_close": current["close"],

        "range_ok": analysis["range"] > 0,

        "reason": analysis["reason"],

        "open": current["open"],
        "high": current["high"],
        "low": current["low"],
        "close": current["close"],

        "timestamp": current["from"],
    }


# ============================================================
# SEÑAL PRINCIPAL
# ============================================================

def check_pattern(candles):
    """
    Devuelve únicamente:

        call
        put
        None

    La decisión se toma SOLO después del cierre de la M1.
    """

    analysis = get_strategy_analysis(candles)

    if not analysis.get("valid"):
        return None

    if not analysis.get("closed"):
        return None

    signal = analysis.get("signal")

    if signal == "call":
        return "call"

    if signal == "put":
        return "put"

    return None


# ============================================================
# FUNCIÓN DE COMPATIBILIDAD
# ============================================================

def analyze_m1(candles):
    """
    Alias para poder consultar directamente el análisis M1.
    """

    return get_strategy_analysis(candles)


# ============================================================
# VALIDACIÓN
# ============================================================

def validate_strategy():
    required = (
        "check_pattern",
        "get_m1_direction",
        "get_strategy_analysis",
    )

    for name in required:
        if not callable(globals().get(name)):
            raise RuntimeError(
                f"Falta la función requerida: {name}"
            )

    return True


validate_strategy()
