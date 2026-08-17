# ============================================================
# STRATEGY.PY
# ANÁLISIS EXCLUSIVO DE VELA M1
#
# La estrategia analiza UNA vela M1 cerrada.
#
# Estados analizados:
#   - FUERZA
#   - CONTINUIDAD
#   - REVERSIÓN
#   - INDECISIÓN
#   - DEBILIDAD
#   - DOJI
#
# La señal se determina únicamente cuando la vela N termina.
# El bot debe ejecutar esa señal en la apertura de N+1.
# ============================================================


# ============================================================
# CONFIGURACIÓN
# ============================================================

DOJI_BODY_RATIO = 0.10

STRONG_BODY_RATIO = 0.60
WEAK_BODY_RATIO = 0.30

STRONG_CLOSE_POSITION = 0.75
WEAK_CLOSE_POSITION = 0.55

LONG_WICK_RATIO = 0.35
REVERSAL_WICK_RATIO = 0.45

MIN_RANGE = 0.0


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_ohlc(candle):
    if not isinstance(candle, dict):
        return None

    opening = _to_float(candle.get("open"))
    high = _to_float(candle.get("max"))
    low = _to_float(candle.get("min"))
    closing = _to_float(candle.get("close"))

    # Compatibilidad con algunas respuestas de API
    if high is None:
        high = _to_float(candle.get("high"))

    if low is None:
        low = _to_float(candle.get("low"))

    if None in (opening, high, low, closing):
        return None

    if high < low:
        return None

    if opening < low or opening > high:
        return None

    if closing < low or closing > high:
        return None

    return opening, high, low, closing


# ============================================================
# COLOR
# ============================================================

def get_candle_color(candle):
    data = _get_ohlc(candle)

    if data is None:
        return None

    opening, _, _, closing = data

    if closing > opening:
        return "verde"

    if closing < opening:
        return "rojo"

    return "doji"


# ============================================================
# DIRECCIÓN M1
# ============================================================

def get_m1_direction(candle):
    """
    Devuelve la dirección de la vela M1 cerrada.

    verde -> call
    rojo  -> put
    doji  -> None
    """

    color = get_candle_color(candle)

    if color == "verde":
        return "call"

    if color == "rojo":
        return "put"

    return None


# ============================================================
# POSICIÓN DEL CIERRE
# ============================================================

def _close_position(opening, high, low, closing):
    candle_range = high - low

    if candle_range <= MIN_RANGE:
        return 0.50

    return (closing - low) / candle_range


# ============================================================
# ANÁLISIS DE UNA VELA M1
# ============================================================

def analyze_m1_candle(candle):
    """
    Analiza exclusivamente la estructura OHLC de una vela M1.

    No utiliza:
        - 5S
        - 12 velas
        - M5
        - mayoría de velas
        - contexto de velas anteriores

    Retorna un diccionario completo de análisis.
    """

    data = _get_ohlc(candle)

    if data is None:
        return {
            "valid": False,
            "state": None,
            "signal": None,
            "reason": "VELA M1 INVALIDA",
        }

    opening, high, low, closing = data

    candle_range = high - low

    if candle_range <= MIN_RANGE:
        return {
            "valid": True,
            "state": "DOJI",
            "signal": None,
            "direction": "neutral",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": 0.0,
            "body_ratio": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "close_position": 0.50,
            "reason": "RANGO CERO",
        }

    body = abs(closing - opening)

    body_ratio = body / candle_range

    upper_wick = high - max(opening, closing)
    lower_wick = min(opening, closing) - low

    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    close_position = _close_position(
        opening,
        high,
        low,
        closing,
    )

    if closing > opening:
        direction = "bullish"

    elif closing < opening:
        direction = "bearish"

    else:
        direction = "neutral"

    # ========================================================
    # DOJI
    # ========================================================

    if body_ratio <= DOJI_BODY_RATIO:
        return {
            "valid": True,
            "state": "DOJI",
            "signal": None,
            "direction": direction,
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "CUERPO MUY PEQUEÑO",
        }

    # ========================================================
    # REVERSIÓN
    #
    # Rechazo fuerte de una zona:
    #   - mecha superior grande -> presión vendedora
    #   - mecha inferior grande -> presión compradora
    # ========================================================

    if (
        upper_wick_ratio >= REVERSAL_WICK_RATIO
        and close_position <= 0.40
    ):
        return {
            "valid": True,
            "state": "REVERSIÓN",
            "signal": "put",
            "direction": "bearish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "RECHAZO SUPERIOR",
        }

    if (
        lower_wick_ratio >= REVERSAL_WICK_RATIO
        and close_position >= 0.60
    ):
        return {
            "valid": True,
            "state": "REVERSIÓN",
            "signal": "call",
            "direction": "bullish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "RECHAZO INFERIOR",
        }

    # ========================================================
    # FUERZA
    # ========================================================

    if (
        body_ratio >= STRONG_BODY_RATIO
        and close_position >= STRONG_CLOSE_POSITION
        and direction == "bullish"
        and upper_wick_ratio <= 0.20
    ):
        return {
            "valid": True,
            "state": "FUERZA",
            "signal": "call",
            "direction": "bullish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "CUERPO ALCISTA FUERTE",
        }

    if (
        body_ratio >= STRONG_BODY_RATIO
        and close_position <= (1.0 - STRONG_CLOSE_POSITION)
        and direction == "bearish"
        and lower_wick_ratio <= 0.20
    ):
        return {
            "valid": True,
            "state": "FUERZA",
            "signal": "put",
            "direction": "bearish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "CUERPO BAJISTA FUERTE",
        }

    # ========================================================
    # CONTINUIDAD
    #
    # Cuerpo relativamente amplio y cierre próximo al extremo.
    # ========================================================

    if (
        direction == "bullish"
        and body_ratio >= 0.45
        and close_position >= STRONG_CLOSE_POSITION
        and upper_wick_ratio < LONG_WICK_RATIO
    ):
        return {
            "valid": True,
            "state": "CONTINUIDAD",
            "signal": "call",
            "direction": "bullish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "CIERRE ALCISTA CERCANO AL MAXIMO",
        }

    if (
        direction == "bearish"
        and body_ratio >= 0.45
        and close_position <= (1.0 - STRONG_CLOSE_POSITION)
        and lower_wick_ratio < LONG_WICK_RATIO
    ):
        return {
            "valid": True,
            "state": "CONTINUIDAD",
            "signal": "put",
            "direction": "bearish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "CIERRE BAJISTA CERCANO AL MINIMO",
        }

    # ========================================================
    # DEBILIDAD
    # ========================================================

    if (
        direction == "bullish"
        and (
            body_ratio <= WEAK_BODY_RATIO
            or upper_wick_ratio >= LONG_WICK_RATIO
        )
    ):
        return {
            "valid": True,
            "state": "DEBILIDAD",
            "signal": None,
            "direction": "bullish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "IMPULSO ALCISTA CON DEBILIDAD",
        }

    if (
        direction == "bearish"
        and (
            body_ratio <= WEAK_BODY_RATIO
            or lower_wick_ratio >= LONG_WICK_RATIO
        )
    ):
        return {
            "valid": True,
            "state": "DEBILIDAD",
            "signal": None,
            "direction": "bearish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "IMPULSO BAJISTA CON DEBILIDAD",
        }

    # ========================================================
    # INDECISIÓN
    # ========================================================

    if (
        body_ratio < 0.35
        and upper_wick_ratio >= 0.20
        and lower_wick_ratio >= 0.20
    ):
        return {
            "valid": True,
            "state": "INDECISIÓN",
            "signal": None,
            "direction": direction,
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "MECHAS EN AMBOS EXTREMOS",
        }

    # ========================================================
    # CONTINUIDAD SECUNDARIA
    # ========================================================

    if direction == "bullish":
        return {
            "valid": True,
            "state": "CONTINUIDAD",
            "signal": "call",
            "direction": "bullish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "ESTRUCTURA ALCISTA",
        }

    if direction == "bearish":
        return {
            "valid": True,
            "state": "CONTINUIDAD",
            "signal": "put",
            "direction": "bearish",
            "open": opening,
            "high": high,
            "low": low,
            "close": closing,
            "range": candle_range,
            "body": body,
            "body_ratio": body_ratio,
            "upper_wick": upper_wick,
            "lower_wick": lower_wick,
            "upper_wick_ratio": upper_wick_ratio,
            "lower_wick_ratio": lower_wick_ratio,
            "close_position": close_position,
            "reason": "ESTRUCTURA BAJISTA",
        }

    # ========================================================
    # CASO FINAL
    # ========================================================

    return {
        "valid": True,
        "state": "INDECISIÓN",
        "signal": None,
        "direction": "neutral",
        "open": opening,
        "high": high,
        "low": low,
        "close": closing,
        "range": candle_range,
        "body": body,
        "body_ratio": body_ratio,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio,
        "close_position": close_position,
        "reason": "SIN DIRECCIÓN DEFINIDA",
    }


# ============================================================
# FUNCIÓN PRINCIPAL DE ESTRATEGIA
# ============================================================

def check_pattern(candles):
    """
    Compatible con bot.py.

    IMPORTANTE:
    Se utiliza únicamente la última vela recibida,
    que debe ser la vela M1 YA CERRADA.

    La señal se ejecuta posteriormente en N+1.
    """

    if candles is None:
        return None

    if not isinstance(candles, (list, tuple)):
        return None

    if len(candles) == 0:
        return None

    candle_n = candles[-1]

    analysis = analyze_m1_candle(candle_n)

    if not analysis.get("valid"):
        return None

    return analysis.get("signal")


# ============================================================
# ANÁLISIS COMPLETO
# ============================================================

def get_strategy_analysis(candles):
    """
    Devuelve el análisis completo de la vela M1 cerrada.
    Compatible con bot.py.
    """

    if candles is None:
        return {
            "valid": False,
            "state": None,
            "signal": None,
            "reason": "SIN DATOS",
        }

    if not isinstance(candles, (list, tuple)):
        return {
            "valid": False,
            "state": None,
            "signal": None,
            "reason": "FORMATO INVALIDO",
        }

    if len(candles) == 0:
        return {
            "valid": False,
            "state": None,
            "signal": None,
            "reason": "LISTA VACIA",
        }

    candle_n = candles[-1]

    analysis = analyze_m1_candle(candle_n)

    if not analysis.get("valid"):
        return analysis

    return {
        "valid": True,

        "state": analysis.get("state"),

        "signal": analysis.get("signal"),

        "direction": analysis.get("direction"),

        "dominant": analysis.get("state"),

        "dominance_ratio": analysis.get(
            "body_ratio",
            0.0,
        ),

        "efficiency": analysis.get(
            "close_position",
            0.0,
        ),

        "final_control": analysis.get(
            "direction",
        ),

        "last_5s_close": None,

        "close_position": analysis.get(
            "close_position",
        ),

        "range_ok": (
            analysis.get("range", 0.0)
            > MIN_RANGE
        ),

        "open": analysis.get("open"),

        "high": analysis.get("high"),

        "low": analysis.get("low"),

        "close": analysis.get("close"),

        "range": analysis.get("range"),

        "body": analysis.get("body"),

        "body_ratio": analysis.get(
            "body_ratio",
        ),

        "upper_wick": analysis.get(
            "upper_wick",
        ),

        "lower_wick": analysis.get(
            "lower_wick",
        ),

        "upper_wick_ratio": analysis.get(
            "upper_wick_ratio",
        ),

        "lower_wick_ratio": analysis.get(
            "lower_wick_ratio",
        ),

        "reason": analysis.get(
            "reason",
            "SIN MOTIVO",
        ),
    }


# ============================================================
# FUNCIÓN AUXILIAR
# ============================================================

def get_signal(candle):
    """
    Analiza directamente una vela M1 cerrada.

    Retorna:
        call
        put
        None
    """

    analysis = analyze_m1_candle(candle)

    if not analysis.get("valid"):
        return None

    return analysis.get("signal")


# ============================================================
# FIN
# ============================================================
