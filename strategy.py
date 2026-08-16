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
# FILTROS
# ============================================================

# Antes estaba en 0.50.
# Era demasiado restrictivo y eliminaba demasiadas oportunidades.
MIN_BODY_RATIO = 0.30

# Si más del 40% de las microvelas cierran en contra
# de la dirección de N, consideramos que hay demasiada
# inestabilidad.
MAX_OPPOSITE_MICRO_RATIO = 0.40

# Primera microvela:
# debe comenzar mostrando continuidad.
FIRST_MICRO_MIN_MOVE_RATIO = 0.0

# ============================================================
# UTILIDADES
# ============================================================


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def empty_result(reason: str = "") -> Dict[str, Any]:
    return {
        "signal": None,
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "minute_high": None,
        "minute_low": None,
        "first_5s_close": None,
        "micro_count": 0,
        "opposite_micro_count": 0,
        "body_ratio": 0.0,
        "movement_direction": None,
        "movement_strong": False,
        "continuity": False,
        "score": 0,
        "reason": reason,
    }


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
        "high",
        "low",
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

        df["from"] = df["from"].astype("int64")

        df.sort_values(
            "from",
            inplace=True,
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# DATOS DE VELA 1M
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

    candle_range = max(
        high - low,
        0.0,
    )

    body = abs(
        closing - opening
    )

    if candle_range > 0:
        body_ratio = body / candle_range
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
# MOVIMIENTO DE N
# ============================================================


def detect_movement(
    candle: pd.Series,
) -> Dict[str, Any]:

    data = get_main_candle_data(
        candle
    )

    direction = data["direction"]
    body_ratio = data["body_ratio"]

    if direction == "none":

        return {
            "valid": False,
            "strong": False,
            "direction": "none",
            "body_ratio": body_ratio,
            "reason": "N cerró sin dirección",
        }

    if data["range"] <= 0:

        return {
            "valid": False,
            "strong": False,
            "direction": direction,
            "body_ratio": body_ratio,
            "reason": "N no tiene rango",
        }

    # Movimiento válido.
    #
    # Ya no exigimos 50%.
    # Con 30% puede haber una vela suficientemente direccional
    # sin bloquear casi todas las señales.
    if body_ratio >= MIN_BODY_RATIO:

        return {
            "valid": True,
            "strong": True,
            "direction": direction,
            "body_ratio": body_ratio,
            "reason": "movimiento direccional válido",
        }

    return {
        "valid": False,
        "strong": False,
        "direction": direction,
        "body_ratio": body_ratio,
        "reason": (
            f"cuerpo insuficiente "
            f"({body_ratio:.3f} < {MIN_BODY_RATIO:.3f})"
        ),
    }


# ============================================================
# MICROESTRUCTURA
# ============================================================


def analyze_micro_continuity(
    minute_open: float,
    minute_close: float,
    direction: str,
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "first_close": None,
        "opposite_count": 0,
        "opposite_ratio": 1.0,
        "reason": "",
    }

    if micro is None or micro.empty:

        result["reason"] = (
            "no hay microvelas"
        )

        return result

    if len(micro) != MICRO_CANDLE_COUNT:

        result["reason"] = (
            f"microvelas incompletas "
            f"({len(micro)}/{MICRO_CANDLE_COUNT})"
        )

        return result

    first = micro.iloc[0]

    first_close = safe_float(
        first["close"]
    )

    result["first_close"] = first_close

    # --------------------------------------------------------
    # DIRECCIÓN FINAL DE N
    # --------------------------------------------------------

    if direction == "call":

        if minute_close <= minute_open:

            result["reason"] = (
                "N no cerró verde"
            )

            return result

        # Primera microvela debe acompañar.
        if first_close <= minute_open:

            result["reason"] = (
                "primera 5S no confirma CALL"
            )

            return result

        opposite_count = 0

        # El resto de microvelas.
        for index in range(1, len(micro)):

            row = micro.iloc[index]

            close = safe_float(
                row["close"]
            )

            # Cerrar por debajo de la apertura de N
            # es una señal clara de pérdida de continuidad.
            if close < minute_open:
                opposite_count += 1

    elif direction == "put":

        if minute_close >= minute_open:

            result["reason"] = (
                "N no cerró roja"
            )

            return result

        if first_close >= minute_open:

            result["reason"] = (
                "primera 5S no confirma PUT"
            )

            return result

        opposite_count = 0

        for index in range(1, len(micro)):

            row = micro.iloc[index]

            close = safe_float(
                row["close"]
            )

            if close > minute_open:
                opposite_count += 1

    else:

        result["reason"] = (
            "N sin dirección"
        )

        return result

    total_after_first = max(
        len(micro) - 1,
        1,
    )

    opposite_ratio = (
        opposite_count /
        total_after_first
    )

    result["opposite_count"] = (
        opposite_count
    )

    result["opposite_ratio"] = (
        opposite_ratio
    )

    # --------------------------------------------------------
    # DEMASIADA OPOSICIÓN
    # --------------------------------------------------------

    if opposite_ratio > MAX_OPPOSITE_MICRO_RATIO:

        result["reason"] = (
            "demasiada pérdida de continuidad "
            f"({opposite_count}/{total_after_first} "
            f"microvelas en contra)"
        )

        return result

    result["valid"] = True

    result["reason"] = (
        "continuidad micro confirmada"
    )

    return result


# ============================================================
# SCORE
# ============================================================


def calculate_score(
    movement: Dict[str, Any],
    micro_result: Dict[str, Any],
) -> int:

    score = 0

    # Movimiento válido.
    if movement.get("valid"):
        score += 3

    # Primera microvela confirma.
    if micro_result.get("first_close") is not None:
        score += 2

    # Continuidad.
    if micro_result.get("valid"):
        score += 3

    # Poco movimiento contrario.
    opposite_ratio = float(
        micro_result.get(
            "opposite_ratio",
            1.0,
        )
    )

    if opposite_ratio <= 0.20:
        score += 2

    elif opposite_ratio <= 0.40:
        score += 1

    return min(
        score,
        10,
    )


# ============================================================
# ANALIZAR MERCADO
# ============================================================


def analyze_market(
    candle: pd.Series,
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = empty_result()

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if candle is None:

        result["reason"] = (
            "vela N inexistente"
        )

        return result

    if not isinstance(
        candle,
        pd.Series,
    ):

        result["reason"] = (
            "vela N inválida"
        )

        return result

    # --------------------------------------------------------
    # DATOS DE N
    # --------------------------------------------------------

    data = get_main_candle_data(
        candle
    )

    minute_open = data["open"]
    minute_close = data["close"]

    result["minute_open"] = (
        minute_open
    )

    result["minute_close"] = (
        minute_close
    )

    result["minute_high"] = (
        data["high"]
    )

    result["minute_low"] = (
        data["low"]
    )

    result["body_ratio"] = (
        data["body_ratio"]
    )

    result["movement_direction"] = (
        data["direction"]
    )

    # Timestamp.
    if "from" in candle.index:

        try:
            result["minute_timestamp"] = int(
                float(candle["from"])
            )
        except (
            TypeError,
            ValueError,
        ):
            pass

    # --------------------------------------------------------
    # N VÁLIDA
    # --------------------------------------------------------

    if minute_open <= 0:

        result["reason"] = (
            "apertura N inválida"
        )

        return result

    # --------------------------------------------------------
    # MOVIMIENTO
    # --------------------------------------------------------

    movement = detect_movement(
        candle
    )

    result["movement_strong"] = (
        movement["strong"]
    )

    # --------------------------------------------------------
    # MICROVELAS
    # --------------------------------------------------------

    micro = prepare_micro_candles(
        micro
    )

    result["micro_count"] = len(
        micro
    )

    if len(micro) != MICRO_CANDLE_COUNT:

        result["reason"] = (
            f"microvelas incompletas: "
            f"{len(micro)}/{MICRO_CANDLE_COUNT}"
        )

        return result

    # --------------------------------------------------------
    # MICROCONTINUIDAD
    # --------------------------------------------------------

    micro_result = analyze_micro_continuity(
        minute_open,
        minute_close,
        movement["direction"],
        micro,
    )

    result["first_5s_close"] = (
        micro_result["first_close"]
    )

    result["opposite_micro_count"] = (
        micro_result["opposite_count"]
    )

    result["continuity"] = (
        micro_result["valid"]
    )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    score = calculate_score(
        movement,
        micro_result,
    )

    result["score"] = score

    # --------------------------------------------------------
    # FILTRO DE MOVIMIENTO
    # --------------------------------------------------------

    if not movement["valid"]:

        result["reason"] = (
            "SIN ENTRADA | "
            + movement["reason"]
        )

        return result

    # --------------------------------------------------------
    # FILTRO DE CONTINUIDAD
    # --------------------------------------------------------

    if not micro_result["valid"]:

        result["reason"] = (
            "SIN ENTRADA | "
            + micro_result["reason"]
        )

        return result

    # --------------------------------------------------------
    # SCORE MÍNIMO
    # --------------------------------------------------------

    if score < 6:

        result["reason"] = (
            f"SIN ENTRADA | score bajo "
            f"{score}/10"
        )

        return result

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    if movement["direction"] == "call":

        result["signal"] = "call"

        result["reason"] = (
            "CALL | continuidad confirmada | "
            f"body_ratio={data['body_ratio']:.3f} | "
            f"micro={len(micro)} | "
            f"opuestas={micro_result['opposite_count']} | "
            f"score={score}/10"
        )

        return result

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    if movement["direction"] == "put":

        result["signal"] = "put"

        result["reason"] = (
            "PUT | continuidad confirmada | "
            f"body_ratio={data['body_ratio']:.3f} | "
            f"micro={len(micro)} | "
            f"opuestas={micro_result['opposite_count']} | "
            f"score={score}/10"
        )

        return result

    result["reason"] = (
        "SIN ENTRADA | dirección desconocida"
    )

    return result
