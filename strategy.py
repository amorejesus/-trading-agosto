from __future__ import annotations

from typing import Any, Dict

import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

TIMEFRAME = 60
MICRO_TIMEFRAME = 5

MICRO_CANDLE_COUNT = 12


# ============================================================
# FILTRO DE MOVIMIENTO FUERTE
# ============================================================

# Porcentaje mínimo del cuerpo respecto al rango total
# para considerar que la vela de 1 minuto tiene
# movimiento suficientemente fuerte.
MIN_STRONG_BODY_RATIO = 0.50


# ============================================================
# UTILIDADES
# ============================================================

def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# PREPARAR MICROVELAS
# ============================================================

def prepare_micro_candles(
    micro: pd.DataFrame,
) -> pd.DataFrame:

    if micro is None:
        return pd.DataFrame()

    if not isinstance(micro, pd.DataFrame):
        return pd.DataFrame()

    if micro.empty:
        return pd.DataFrame()

    df = micro.copy()

    required = [
        "open",
        "close",
    ]

    for column in required:

        if column not in df.columns:
            return pd.DataFrame()

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df.dropna(
        subset=required,
        inplace=True,
    )

    if "from" in df.columns:

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce",
        )

        df.dropna(
            subset=["from"],
            inplace=True,
        )

        df.sort_values(
            "from",
            inplace=True,
        )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# MOVIMIENTO DE LA VELA PRINCIPAL
# ============================================================

def get_main_candle_data(
    candle: pd.Series,
) -> Dict[str, float]:

    opening = safe_float(
        candle.get("open")
    )

    closing = safe_float(
        candle.get("close")
    )

    high = safe_float(
        candle.get("high")
    )

    low = safe_float(
        candle.get("low")
    )

    candle_range = high - low

    body = abs(
        closing - opening
    )

    if candle_range > 0:

        body_ratio = (
            body / candle_range
        )

    else:

        body_ratio = 0.0

    if closing > opening:

        direction = "call"

    elif closing < opening:

        direction = "put"

    else:

        direction = "none"

    return {

        "open": opening,

        "close": closing,

        "high": high,

        "low": low,

        "range": candle_range,

        "body": body,

        "body_ratio": body_ratio,

        "direction": direction,
    }


# ============================================================
# MOVIMIENTO FUERTE
# ============================================================

def detect_strong_movement(
    candle: pd.Series,
) -> Dict[str, Any]:

    data = get_main_candle_data(
        candle
    )

    direction = data[
        "direction"
    ]

    body_ratio = data[
        "body_ratio"
    ]

    candle_range = data[
        "range"
    ]

    body = data[
        "body"
    ]

    # --------------------------------------------------------
    # Sin movimiento
    # --------------------------------------------------------

    if direction == "none":

        return {

            "strong": False,

            "direction": "none",

            "body_ratio": body_ratio,

            "reason":
                "vela sin dirección",
        }

    # --------------------------------------------------------
    # Sin rango
    # --------------------------------------------------------

    if candle_range <= 0:

        return {

            "strong": False,

            "direction": direction,

            "body_ratio": body_ratio,

            "reason":
                "vela sin rango",
        }

    # --------------------------------------------------------
    # Movimiento fuerte
    # --------------------------------------------------------

    if body_ratio >= MIN_STRONG_BODY_RATIO:

        return {

            "strong": True,

            "direction": direction,

            "body_ratio": body_ratio,

            "reason":
                "movimiento fuerte "
                f"{direction.upper()}",
        }

    return {

        "strong": False,

        "direction": direction,

        "body_ratio": body_ratio,

        "reason":
            "movimiento débil",
    }


# ============================================================
# PRIMERA MICROVELA
# ============================================================

def check_first_5s(
    minute_open: float,
    first_micro: pd.Series,
) -> Dict[str, Any]:

    first_open = safe_float(
        first_micro.get("open")
    )

    first_close = safe_float(
        first_micro.get("close")
    )

    # ========================================================
    # CALL
    # Primera 5S debe cerrar por encima
    # de la apertura de la vela de 1 minuto.
    # ========================================================

    first_bullish = (
        first_close > minute_open
    )

    # ========================================================
    # PUT
    # Primera 5S debe cerrar por debajo
    # de la apertura de la vela de 1 minuto.
    # ========================================================

    first_bearish = (
        first_close < minute_open
    )

    return {

        "first_open": first_open,

        "first_close": first_close,

        "call": first_bullish,

        "put": first_bearish,
    }


# ============================================================
# RETROCESO CALL
# ============================================================

def count_call_pullbacks(
    minute_open: float,
    micro: pd.DataFrame,
) -> int:

    if micro.empty:
        return 0

    count = 0

    # --------------------------------------------------------
    # La primera microvela no cuenta como retroceso.
    # --------------------------------------------------------

    for index in range(
        1,
        len(micro),
    ):

        row = micro.iloc[index]

        close = safe_float(
            row["close"]
        )

        # Para CALL:
        #
        # durante el resto del minuto,
        # las microvelas deben cerrar
        # por debajo de la apertura de N.

        if close < minute_open:

            count += 1

    return count


# ============================================================
# RETROCESO PUT
# ============================================================

def count_put_pullbacks(
    minute_open: float,
    micro: pd.DataFrame,
) -> int:

    if micro.empty:
        return 0

    count = 0

    # --------------------------------------------------------
    # La primera microvela no cuenta como retroceso.
    # --------------------------------------------------------

    for index in range(
        1,
        len(micro),
    ):

        row = micro.iloc[index]

        close = safe_float(
            row["close"]
        )

        # Para PUT:
        #
        # durante el resto del minuto,
        # las microvelas deben cerrar
        # por encima de la apertura de N.

        if close > minute_open:

            count += 1

    return count


# ============================================================
# VALIDAR RETROCESO CALL
# ============================================================

def validate_call_pattern(
    minute_open: float,
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    if len(micro) != MICRO_CANDLE_COUNT:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "microvelas insuficientes",
        }

    first = micro.iloc[0]

    first_data = check_first_5s(
        minute_open,
        first,
    )

    # Primera 5S obligatoriamente alcista.
    if not first_data["call"]:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "primera 5S no supera "
                "la apertura de N",
        }

    pullbacks = count_call_pullbacks(
        minute_open,
        micro,
    )

    # Debe existir al menos un retroceso.
    if pullbacks < 1:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "no existe retroceso CALL",
        }

    return {

        "valid": True,

        "pullback_count": pullbacks,

        "first_5s_close":
            first_data["first_close"],

        "reason":
            "patrón CALL confirmado",
    }


# ============================================================
# VALIDAR RETROCESO PUT
# ============================================================

def validate_put_pattern(
    minute_open: float,
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    if len(micro) != MICRO_CANDLE_COUNT:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "microvelas insuficientes",
        }

    first = micro.iloc[0]

    first_data = check_first_5s(
        minute_open,
        first,
    )

    # Primera 5S obligatoriamente bajista.
    if not first_data["put"]:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "primera 5S no queda "
                "debajo de la apertura de N",
        }

    pullbacks = count_put_pullbacks(
        minute_open,
        micro,
    )

    # Debe existir al menos un retroceso.
    if pullbacks < 1:

        return {

            "valid": False,

            "pullback_count": 0,

            "reason":
                "no existe retroceso PUT",
        }

    return {

        "valid": True,

        "pullback_count": pullbacks,

        "first_5s_close":
            first_data["first_close"],

        "reason":
            "patrón PUT confirmado",
    }


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(
    candle: pd.Series,
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {

        "signal": None,

        "minute_timestamp": None,

        "minute_open": None,

        "minute_close": None,

        "first_5s_close": None,

        "pullback_count": 0,

        "movement_direction": None,

        "movement_strong": False,

        "body_ratio": 0.0,

        "reason": "",
    }

    # ========================================================
    # VALIDAR VELA PRINCIPAL
    # ========================================================

    if candle is None:

        result["reason"] = (
            "vela 1M inexistente"
        )

        return result

    minute_open = safe_float(
        candle.get("open")
    )

    minute_close = safe_float(
        candle.get("close")
    )

    if minute_open <= 0:

        result["reason"] = (
            "apertura 1M inválida"
        )

        return result

    # ========================================================
    # TIMESTAMP
    # ========================================================

    if "from" in candle.index:

        try:

            result[
                "minute_timestamp"
            ] = int(
                float(
                    candle["from"]
                )
            )

        except (
            TypeError,
            ValueError,
        ):

            result[
                "minute_timestamp"
            ] = None

    result[
        "minute_open"
    ] = minute_open

    result[
        "minute_close"
    ] = minute_close

    # ========================================================
    # PREPARAR MICROVELAS
    # ========================================================

    micro = prepare_micro_candles(
        micro
    )

    if len(micro) != MICRO_CANDLE_COUNT:

        result["reason"] = (
            "se requieren exactamente "
            f"{MICRO_CANDLE_COUNT} microvelas 5S"
        )

        return result

    # ========================================================
    # MOVIMIENTO FUERTE
    # ========================================================

    movement = detect_strong_movement(
        candle
    )

    result[
        "movement_direction"
    ] = movement["direction"]

    result[
        "movement_strong"
    ] = movement["strong"]

    result[
        "body_ratio"
    ] = movement["body_ratio"]

    # ========================================================
    # SI NO HAY MOVIMIENTO FUERTE,
    # NO SE OPERA.
    # ========================================================

    if not movement["strong"]:

        result["reason"] = (
            "sin movimiento fuerte"
        )

        return result

    # ========================================================
    # PRIMERA 5S
    # ========================================================

    first = micro.iloc[0]

    first_close = safe_float(
        first["close"]
    )

    result[
        "first_5s_close"
    ] = first_close

    # ========================================================
    # MOVIMIENTO FUERTE ALCISTA
    # ========================================================

    if movement[
        "direction"
    ] == "call":

        pattern = validate_call_pattern(
            minute_open,
            micro,
        )

        if not pattern["valid"]:

            result["reason"] = (
                pattern["reason"]
            )

            return result

        # ----------------------------------------------------
        # CONFIRMACIÓN FINAL
        #
        # La vela N debe cerrar verde.
        # ----------------------------------------------------

        if minute_close <= minute_open:

            result["reason"] = (
                "movimiento alcista pero "
                "vela N no cerró verde"
            )

            return result

        # ----------------------------------------------------
        # CALL
        # ----------------------------------------------------

        result["signal"] = "call"

        result[
            "pullback_count"
        ] = pattern[
            "pullback_count"
        ]

        result["reason"] = (
            "CALL | movimiento fuerte "
            "alcista | primera 5S alcista "
            "| retroceso confirmado "
            "| cierre N verde"
        )

        return result

    # ========================================================
    # MOVIMIENTO FUERTE BAJISTA
    # ========================================================

    if movement[
        "direction"
    ] == "put":

        pattern = validate_put_pattern(
            minute_open,
            micro,
        )

        if not pattern["valid"]:

            result["reason"] = (
                pattern["reason"]
            )

            return result

        # ----------------------------------------------------
        # CONFIRMACIÓN FINAL
        #
        # La vela N debe cerrar roja.
        # ----------------------------------------------------

        if minute_close >= minute_open:

            result["reason"] = (
                "movimiento bajista pero "
                "vela N no cerró roja"
            )

            return result

        # ----------------------------------------------------
        # PUT
        # ----------------------------------------------------

        result["signal"] = "put"

        result[
            "pullback_count"
        ] = pattern[
            "pullback_count"
        ]

        result["reason"] = (
            "PUT | movimiento fuerte "
            "bajista | primera 5S bajista "
            "| retroceso confirmado "
            "| cierre N rojo"
        )

        return result

    # ========================================================
    # SIN DIRECCIÓN
    # ========================================================

    result["reason"] = (
        "movimiento sin dirección"
    )

    return result
