from __future__ import annotations
from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# STRATEGY.PY
# ESTRATEGIA: 1 M1 + EXACTAMENTE 12 MICROVELAS DE 5 SEGUNDOS
# ============================================================
#
# PRINCIPIO:
#
# La primera vela de 5s NO determina la dirección.
#
# Las 12 velas de 5s de la M1 se analizan completas.
#
# DIRECCIÓN:
#     dominante matemático por SUMA DE CUERPOS.
#
# CALIDAD:
#     1) dominancia mínima
#     2) eficiencia del movimiento
#     3) control de las últimas 3 velas
#     4) posición del cierre dentro del rango
#     5) rango mínimo respecto a M1 anteriores, si se proporciona
#
# IMPORTANTE:
# Los filtros de calidad SOLO pueden bloquear una operación.
# Nunca convierten CALL en PUT ni PUT en CALL.
#
# ============================================================
# REGLAS MATEMÁTICAS
# ============================================================
#
# BUY_SCORE  = suma(max(close-open, 0))
# SELL_SCORE = suma(max(open-close, 0))
#
# DOMINANCE =
#     abs(BUY_SCORE - SELL_SCORE)
#     --------------------------
#       BUY_SCORE + SELL_SCORE
#
# Se exige:
#     DOMINANCE >= 25%
#
# EFICIENCIA =
#     abs(close_12 - open_1)
#     --------------------
#     suma(abs(close-open)) de las 12 velas
#
# Se exige:
#     EFICIENCIA >= 45%
#
# CONTROL FINAL:
#     últimas 3 velas de 5s
#
#     final_net = suma(close-open)
#
#     > 0  comprador
#     < 0  vendedor
#     = 0  neutral
#
# POSICIÓN DEL CIERRE:
#
#     position =
#       (close_12 - low_M1) / (high_M1 - low_M1)
#
# CALL:
#     position >= 0.65
#
# PUT:
#     position <= 0.35
#
# RANGO CONTEXTUAL:
#
# Si se proporcionan M1 anteriores:
#
#     current_range / promedio_range_anteriores
#
# Se exige:
#     ratio >= 0.60
#
# Si NO se proporciona historial M1, este filtro queda
# desactivado para mantener compatibilidad con el bot actual.
#
# ============================================================
# CONDICIÓN FINAL CALL
# ============================================================
#
# 1. 12 microvelas exactas
# 2. comprador dominante
# 3. dominancia >= 25%
# 4. eficiencia >= 45%
# 5. control final comprador
# 6. último cierre 5s > apertura M1
# 7. M1 verde
# 8. posición de cierre >= 65%
# 9. rango suficiente si existe historial
#
# ============================================================
# CONDICIÓN FINAL PUT
# ============================================================
#
# 1. 12 microvelas exactas
# 2. vendedor dominante
# 3. dominancia >= 25%
# 4. eficiencia >= 45%
# 5. control final vendedor
# 6. último cierre 5s < apertura M1
# 7. M1 roja
# 8. posición de cierre <= 35%
# 9. rango suficiente si existe historial
#
# ============================================================


# ============================================================
# CONFIGURACIÓN
# ============================================================

MICRO_CANDLES_REQUIRED = 12

FINAL_CONTROL_CANDLES = 3

DOMINANCE_THRESHOLD = 0.25

EFFICIENCY_THRESHOLD = 0.45

MIN_RANGE_RATIO = 0.60

CLOSE_POSITION_CALL = 0.65

CLOSE_POSITION_PUT = 0.35

PREVIOUS_M1_COUNT = 5


# ============================================================
# UTILIDAD
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ============================================================
# NORMALIZAR 5S
# ============================================================

def _normalize_5s(df: pd.DataFrame) -> pd.DataFrame:

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    if "max" in out.columns and "high" not in out.columns:
        rename["max"] = "high"

    if "min" in out.columns and "low" not in out.columns:
        rename["min"] = "low"

    if "Open" in out.columns and "open" not in out.columns:
        rename["Open"] = "open"

    if "High" in out.columns and "high" not in out.columns:
        rename["High"] = "high"

    if "Low" in out.columns and "low" not in out.columns:
        rename["Low"] = "low"

    if "Close" in out.columns and "close" not in out.columns:
        rename["Close"] = "close"

    if rename:
        out.rename(columns=rename, inplace=True)

    if "open" not in out.columns:
        return pd.DataFrame()

    if "close" not in out.columns:
        return pd.DataFrame()

    out["open"] = pd.to_numeric(
        out["open"],
        errors="coerce",
    )

    out["close"] = pd.to_numeric(
        out["close"],
        errors="coerce",
    )

    if "high" in out.columns:
        out["high"] = pd.to_numeric(
            out["high"],
            errors="coerce",
        )

    if "low" in out.columns:
        out["low"] = pd.to_numeric(
            out["low"],
            errors="coerce",
        )

    if "from" in out.columns:

        out["from"] = pd.to_numeric(
            out["from"],
            errors="coerce",
        )

        out.dropna(
            subset=["from"],
            inplace=True,
        )

        out.sort_values(
            "from",
            inplace=True,
        )

    out.dropna(
        subset=["open", "close"],
        inplace=True,
    )

    out.reset_index(
        drop=True,
        inplace=True,
    )

    return out


# ============================================================
# VALIDAR SECUENCIA 5S
# ============================================================

def _validate_5s_sequence(
    micro: pd.DataFrame,
) -> bool:

    if micro.empty:
        return False

    if "from" not in micro.columns:
        return True

    if len(micro) < 2:
        return False

    timestamps = (
        micro["from"]
        .astype(float)
        .tolist()
    )

    for i in range(1, len(timestamps)):

        if (
            timestamps[i]
            - timestamps[i - 1]
            != 5
        ):
            return False

    return True


# ============================================================
# OBTENER MICROVELAS DE LA M1
# ============================================================

def _get_minute_micro_candles(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> pd.DataFrame:

    micro = _normalize_5s(candles_5s)

    if micro.empty:
        return pd.DataFrame()

    minute_timestamp = None

    if candle_1m is not None:

        try:

            if "from" in candle_1m.index:

                minute_timestamp = int(
                    float(candle_1m["from"])
                )

        except (TypeError, ValueError):
            minute_timestamp = None

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = minute_timestamp
        end_time = minute_timestamp + 60

        micro = micro[
            (micro["from"] >= start_time)
            & (micro["from"] < end_time)
        ].copy()

        micro.sort_values(
            "from",
            inplace=True,
        )

        micro.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        micro.reset_index(
            drop=True,
            inplace=True,
        )

    return micro


# ============================================================
# DOMINANTE GLOBAL
# ============================================================

def _calculate_global_dominance(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "dominant": "neutral",
        "buy_score": 0.0,
        "sell_score": 0.0,
        "dominance_ratio": 0.0,
        "total_body": 0.0,
    }

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return result

    buy_score = 0.0
    sell_score = 0.0

    for _, candle in micro.iterrows():

        opening = _to_float(candle["open"])
        closing = _to_float(candle["close"])

        if opening is None or closing is None:
            return result

        body = closing - opening

        if body > 0:
            buy_score += body

        elif body < 0:
            sell_score += abs(body)

    total_body = buy_score + sell_score

    result["buy_score"] = buy_score
    result["sell_score"] = sell_score
    result["total_body"] = total_body

    if total_body <= 0:
        return result

    ratio = abs(
        buy_score - sell_score
    ) / total_body

    result["dominance_ratio"] = ratio

    if (
        buy_score > sell_score
        and ratio >= DOMINANCE_THRESHOLD
    ):
        result["dominant"] = "buyer"

    elif (
        sell_score > buy_score
        and ratio >= DOMINANCE_THRESHOLD
    ):
        result["dominant"] = "seller"

    return result


# ============================================================
# EFICIENCIA
# ============================================================

def _calculate_efficiency(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "efficiency": 0.0,
        "net_movement": 0.0,
        "total_abs_body": 0.0,
    }

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return result

    first_open = _to_float(
        micro.iloc[0]["open"]
    )

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if (
        first_open is None
        or last_close is None
    ):
        return result

    total_abs_body = 0.0

    for _, candle in micro.iterrows():

        opening = _to_float(candle["open"])
        closing = _to_float(candle["close"])

        if opening is None or closing is None:
            return result

        total_abs_body += abs(
            closing - opening
        )

    net_movement = (
        last_close - first_open
    )

    result["net_movement"] = net_movement
    result["total_abs_body"] = total_abs_body

    if total_abs_body <= 0:
        return result

    result["efficiency"] = (
        abs(net_movement)
        / total_abs_body
    )

    return result


# ============================================================
# CONTROL FINAL
# ============================================================

def _calculate_final_control(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "final_control": "neutral",
        "final_net": 0.0,
        "final_buy_movement": 0.0,
        "final_sell_movement": 0.0,
    }

    if len(micro) < FINAL_CONTROL_CANDLES:
        return result

    final_micro = micro.iloc[
        -FINAL_CONTROL_CANDLES:
    ]

    final_net = 0.0
    final_buy = 0.0
    final_sell = 0.0

    for _, candle in final_micro.iterrows():

        opening = _to_float(candle["open"])
        closing = _to_float(candle["close"])

        if opening is None or closing is None:
            return result

        movement = closing - opening

        final_net += movement

        if movement > 0:
            final_buy += movement

        elif movement < 0:
            final_sell += abs(movement)

    result["final_net"] = final_net
    result["final_buy_movement"] = final_buy
    result["final_sell_movement"] = final_sell

    if final_net > 0:
        result["final_control"] = "buyer"

    elif final_net < 0:
        result["final_control"] = "seller"

    return result


# ============================================================
# RANGO DE LAS 12 MICROVELAS
# ============================================================

def _calculate_micro_range(
    micro: pd.DataFrame,
) -> Optional[float]:

    if micro.empty:
        return None

    if "high" in micro.columns and "low" in micro.columns:

        highs = pd.to_numeric(
            micro["high"],
            errors="coerce",
        )

        lows = pd.to_numeric(
            micro["low"],
            errors="coerce",
        )

        if (
            highs.notna().all()
            and lows.notna().all()
        ):

            high_value = float(highs.max())
            low_value = float(lows.min())

            return high_value - low_value

    closes = pd.to_numeric(
        micro["close"],
        errors="coerce",
    )

    opens = pd.to_numeric(
        micro["open"],
        errors="coerce",
    )

    if closes.isna().any() or opens.isna().any():
        return None

    high_value = max(
        float(closes.max()),
        float(opens.max()),
    )

    low_value = min(
        float(closes.min()),
        float(opens.min()),
    )

    return high_value - low_value


# ============================================================
# RANGO CONTEXTUAL DE M1
# ============================================================

def _calculate_range_context(
    candle_1m: pd.Series,
    previous_m1: Optional[pd.DataFrame],
    current_micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "range_context_available": False,
        "current_range": None,
        "average_previous_range": None,
        "range_ratio": None,
        "range_ok": True,
    }

    # --------------------------------------------------------
    # Rango actual
    # --------------------------------------------------------

    current_range = None

    if candle_1m is not None:

        high = _to_float(
            candle_1m.get("high")
        )

        low = _to_float(
            candle_1m.get("low")
        )

        if (
            high is not None
            and low is not None
            and high >= low
        ):
            current_range = high - low

    if current_range is None:
        current_range = _calculate_micro_range(
            current_micro
        )

    result["current_range"] = current_range

    # --------------------------------------------------------
    # Sin historial: compatibilidad
    # --------------------------------------------------------

    if (
        previous_m1 is None
        or not isinstance(previous_m1, pd.DataFrame)
        or previous_m1.empty
    ):
        return result

    if "high" not in previous_m1.columns:
        if "High" in previous_m1.columns:
            previous_m1 = previous_m1.rename(
                columns={"High": "high"}
            )

    if "low" not in previous_m1.columns:
        if "Low" in previous_m1.columns:
            previous_m1 = previous_m1.rename(
                columns={"Low": "low"}
            )

    if (
        "high" not in previous_m1.columns
        or "low" not in previous_m1.columns
    ):
        return result

    previous = previous_m1.tail(
        PREVIOUS_M1_COUNT
    ).copy()

    previous["high"] = pd.to_numeric(
        previous["high"],
        errors="coerce",
    )

    previous["low"] = pd.to_numeric(
        previous["low"],
        errors="coerce",
    )

    previous.dropna(
        subset=["high", "low"],
        inplace=True,
    )

    if previous.empty:
        return result

    ranges = (
        previous["high"]
        - previous["low"]
    )

    ranges = ranges[
        ranges > 0
    ]

    if ranges.empty:
        return result

    average_range = float(
        ranges.mean()
    )

    result[
        "average_previous_range"
    ] = average_range

    if (
        current_range is None
        or average_range <= 0
    ):
        return result

    ratio = (
        current_range
        / average_range
    )

    result["range_context_available"] = True
    result["range_ratio"] = ratio

    result["range_ok"] = (
        ratio >= MIN_RANGE_RATIO
    )

    return result


# ============================================================
# POSICIÓN DEL CIERRE
# ============================================================

def _calculate_close_position(
    micro: pd.DataFrame,
) -> Optional[float]:

    if micro.empty:
        return None

    high = None
    low = None

    if (
        "high" in micro.columns
        and "low" in micro.columns
    ):

        highs = pd.to_numeric(
            micro["high"],
            errors="coerce",
        )

        lows = pd.to_numeric(
            micro["low"],
            errors="coerce",
        )

        if (
            highs.notna().all()
            and lows.notna().all()
        ):

            high = float(highs.max())
            low = float(lows.min())

    if high is None or low is None:

        opens = pd.to_numeric(
            micro["open"],
            errors="coerce",
        )

        closes = pd.to_numeric(
            micro["close"],
            errors="coerce",
        )

        if (
            opens.isna().any()
            or closes.isna().any()
        ):
            return None

        high = max(
            float(opens.max()),
            float(closes.max()),
        )

        low = min(
            float(opens.min()),
            float(closes.min()),
        )

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if last_close is None:
        return None

    if high <= low:
        return None

    return (
        last_close - low
    ) / (
        high - low
    )


# ============================================================
# ANALIZAR UNA M1
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {

        "signal": None,
        "valid": False,

        "reason": "sin señal",

        "minute_timestamp": None,

        "minute_open": None,
        "minute_close": None,

        "micro_candles_count": 0,

        "buy_score": 0.0,
        "sell_score": 0.0,

        "dominance_ratio": 0.0,
        "dominant": None,

        "efficiency": 0.0,
        "net_movement": 0.0,

        "final_control": None,
        "final_net": 0.0,

        "final_buy_movement": 0.0,
        "final_sell_movement": 0.0,

        "last_5s_close": None,

        "close_position": None,

        "current_range": None,
        "average_previous_range": None,
        "range_ratio": None,
        "range_context_available": False,
        "range_ok": True,

        "quality_checks": {
            "dominance_ok": False,
            "efficiency_ok": False,
            "final_control_ok": False,
            "last_close_ok": False,
            "m1_color_ok": False,
            "close_position_ok": False,
            "range_ok": True,
        },
    }

    # ========================================================
    # M1
    # ========================================================

    if candle_1m is None:

        result["reason"] = (
            "vela 1M no disponible"
        )

        return result

    opening = _to_float(
        candle_1m.get("open")
    )

    closing = _to_float(
        candle_1m.get("close")
    )

    if opening is None:

        result["reason"] = (
            "apertura 1M inválida"
        )

        return result

    if closing is None:

        result["reason"] = (
            "cierre 1M inválido"
        )

        return result

    result["minute_open"] = opening
    result["minute_close"] = closing

    if "from" in candle_1m.index:

        try:
            result["minute_timestamp"] = int(
                float(candle_1m["from"])
            )
        except (TypeError, ValueError):
            pass

    # ========================================================
    # MICROVELAS
    # ========================================================

    micro = _get_minute_micro_candles(
        candle_1m,
        candles_5s,
    )

    if micro.empty:

        result["reason"] = (
            "no hay microvelas 5s"
        )

        return result

    result["micro_candles_count"] = len(
        micro
    )

    if not _validate_5s_sequence(micro):

        result["reason"] = (
            "secuencia 5s inválida"
        )

        return result

    # ========================================================
    # EXACTAMENTE 12
    # ========================================================

    if len(micro) != MICRO_CANDLES_REQUIRED:

        result["reason"] = (
            "M1 inválida: se requieren "
            f"{MICRO_CANDLES_REQUIRED} velas "
            f"de 5s y se recibieron "
            f"{len(micro)}"
        )

        return result

    # ========================================================
    # ÚLTIMO CIERRE
    # ========================================================

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if last_close is None:

        result["reason"] = (
            "cierre 5s #12 inválido"
        )

        return result

    result["last_5s_close"] = last_close

    # ========================================================
    # DOMINANTE
    # ========================================================

    dominance = _calculate_global_dominance(
        micro
    )

    result["buy_score"] = dominance[
        "buy_score"
    ]

    result["sell_score"] = dominance[
        "sell_score"
    ]

    result["dominance_ratio"] = dominance[
        "dominance_ratio"
    ]

    result["dominant"] = dominance[
        "dominant"
    ]

    dominance_ok = (
        result["dominant"] in (
            "buyer",
            "seller",
        )
        and result["dominance_ratio"]
        >= DOMINANCE_THRESHOLD
    )

    result[
        "quality_checks"
    ]["dominance_ok"] = dominance_ok

    # ========================================================
    # EFICIENCIA
    # ========================================================

    efficiency = _calculate_efficiency(
        micro
    )

    result["efficiency"] = efficiency[
        "efficiency"
    ]

    result["net_movement"] = efficiency[
        "net_movement"
    ]

    efficiency_ok = (
        result["efficiency"]
        >= EFFICIENCY_THRESHOLD
    )

    result[
        "quality_checks"
    ]["efficiency_ok"] = efficiency_ok

    # ========================================================
    # CONTROL FINAL
    # ========================================================

    final_control = _calculate_final_control(
        micro
    )

    result["final_control"] = (
        final_control["final_control"]
    )

    result["final_net"] = (
        final_control["final_net"]
    )

    result["final_buy_movement"] = (
        final_control[
            "final_buy_movement"
        ]
    )

    result["final_sell_movement"] = (
        final_control[
            "final_sell_movement"
        ]
    )

    # ========================================================
    # POSICIÓN DEL CIERRE
    # ========================================================

    close_position = _calculate_close_position(
        micro
    )

    result["close_position"] = close_position

    # ========================================================
    # RANGO CONTEXTUAL
    # ========================================================

    range_context = _calculate_range_context(
        candle_1m,
        previous_m1,
        micro,
    )

    result["current_range"] = (
        range_context["current_range"]
    )

    result["average_previous_range"] = (
        range_context[
            "average_previous_range"
        ]
    )

    result["range_ratio"] = (
        range_context["range_ratio"]
    )

    result["range_context_available"] = (
        range_context[
            "range_context_available"
        ]
    )

    result["range_ok"] = (
        range_context["range_ok"]
    )

    result[
        "quality_checks"
    ]["range_ok"] = (
        result["range_ok"]
    )

    # ========================================================
    # CALL
    # ========================================================

    if result["dominant"] == "buyer":

        final_control_ok = (
            result["final_control"]
            == "buyer"
        )

        last_close_ok = (
            last_close > opening
        )

        m1_color_ok = (
            closing > opening
        )

        close_position_ok = (
            close_position is not None
            and close_position
            >= CLOSE_POSITION_CALL
        )

        result[
            "quality_checks"
        ]["final_control_ok"] = (
            final_control_ok
        )

        result[
            "quality_checks"
        ]["last_close_ok"] = (
            last_close_ok
        )

        result[
            "quality_checks"
        ]["m1_color_ok"] = (
            m1_color_ok
        )

        result[
            "quality_checks"
        ]["close_position_ok"] = (
            close_position_ok
        )

        if not dominance_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "dominancia insuficiente"
            )

            return result

        if not efficiency_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "eficiencia insuficiente"
            )

            return result

        if not final_control_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "control final no comprador"
            )

            return result

        if not last_close_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "último cierre 5s no supera "
                "la apertura M1"
            )

            return result

        if not m1_color_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "M1 no terminó verde"
            )

            return result

        if not close_position_ok:

            result["reason"] = (
                "CALL bloqueada: "
                "cierre demasiado alejado "
                "del extremo superior"
            )

            return result

        if not result["range_ok"]:

            result["reason"] = (
                "CALL bloqueada: "
                "rango M1 insuficiente "
                "respecto al contexto"
            )

            return result

        result["signal"] = "call"
        result["valid"] = True

        result["reason"] = (
            "CALL confirmada: "
            "dominante comprador + "
            "eficiencia + "
            "control final + "
            "M1 verde + "
            "posición de cierre válida"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    if result["dominant"] == "seller":

        final_control_ok = (
            result["final_control"]
            == "seller"
        )

        last_close_ok = (
            last_close < opening
        )

        m1_color_ok = (
            closing < opening
        )

        close_position_ok = (
            close_position is not None
            and close_position
            <= CLOSE_POSITION_PUT
        )

        result[
            "quality_checks"
        ]["final_control_ok"] = (
            final_control_ok
        )

        result[
            "quality_checks"
        ]["last_close_ok"] = (
            last_close_ok
        )

        result[
            "quality_checks"
        ]["m1_color_ok"] = (
            m1_color_ok
        )

        result[
            "quality_checks"
        ]["close_position_ok"] = (
            close_position_ok
        )

        if not dominance_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "dominancia insuficiente"
            )

            return result

        if not efficiency_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "eficiencia insuficiente"
            )

            return result

        if not final_control_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "control final no vendedor"
            )

            return result

        if not last_close_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "último cierre 5s no está "
                "debajo de la apertura M1"
            )

            return result

        if not m1_color_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "M1 no terminó roja"
            )

            return result

        if not close_position_ok:

            result["reason"] = (
                "PUT bloqueada: "
                "cierre demasiado alejado "
                "del extremo inferior"
            )

            return result

        if not result["range_ok"]:

            result["reason"] = (
                "PUT bloqueada: "
                "rango M1 insuficiente "
                "respecto al contexto"
            )

            return result

        result["signal"] = "put"
        result["valid"] = True

        result["reason"] = (
            "PUT confirmada: "
            "dominante vendedor + "
            "eficiencia + "
            "control final + "
            "M1 roja + "
            "posición de cierre válida"
        )

        return result

    # ========================================================
    # SIN DOMINANTE
    # ========================================================

    result["reason"] = (
        "sin señal: "
        "no existe dominante matemático "
        "suficiente"
    )

    return result


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_minute(
        candle_1m,
        candles_5s,
        previous_m1,
    )


# ============================================================
# API SIMPLE
# ============================================================

def get_signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    result = analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )

    return result.get("signal")


# ============================================================
# COMPATIBILIDAD
# ============================================================

def signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
        previous_m1,
    )


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    print(
        "strategy.py cargado correctamente."
    )

    print(
        "1 M1 = exactamente 12 velas de 5S"
    )

    print(
        "La primera 5S NO determina la dirección."
    )

    print(
        "Dirección = dominante matemático."
    )

    print(
        f"Dominancia mínima = "
        f"{DOMINANCE_THRESHOLD:.0%}"
    )

    print(
        f"Eficiencia mínima = "
        f"{EFFICIENCY_THRESHOLD:.0%}"
    )

    print(
        f"Control final = "
        f"últimas {FINAL_CONTROL_CANDLES} velas"
    )

    print(
        f"Rango mínimo contextual = "
        f"{MIN_RANGE_RATIO:.0%}"
    )

    print(
        "CALL y PUT solamente se bloquean; "
        "los filtros no cambian la dirección."
    )
