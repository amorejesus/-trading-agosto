from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# STRATEGY.PY
#
# 1 M1 = EXACTAMENTE 12 VELAS DE 5 SEGUNDOS
#
# OBJETIVO:
# Analizar el movimiento de CADA vela de 5S y determinar
# el posible movimiento de N+1 según el comportamiento
# de N y de toda la secuencia anterior.
#
# La señal generada corresponde a:
#
#        N  -> análisis
#        N+1 -> CALL / PUT
#
# ============================================================


MICRO_CANDLES_REQUIRED = 12

FINAL_CONTROL_CANDLES = 3

PREVIOUS_M1_COUNT = 5


# ============================================================
# UMBRALES
# ============================================================

DOMINANCE_THRESHOLD = 0.25
EFFICIENCY_THRESHOLD = 0.45

MIN_RANGE_RATIO = 0.60

CLOSE_POSITION_CALL = 0.65
CLOSE_POSITION_PUT = 0.35


# ============================================================
# FILTROS N -> N+1
# ============================================================

# La última vela debe tener cuerpo suficiente respecto
# a su rango para considerarse una vela con movimiento real.

LAST_CANDLE_BODY_RATIO = 0.30


# La última vela debe mostrar desplazamiento suficiente
# respecto al movimiento de las anteriores.

LAST_CANDLE_MOMENTUM_RATIO = 0.20


# Evita señales cuando la última vela prácticamente
# no tiene cuerpo.

MIN_BODY_RATIO = 0.10


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:

    try:
        return float(value)

    except (TypeError, ValueError):

        return None


# ============================================================
# NORMALIZACIÓN
# ============================================================

def _normalize_5s(
    df: pd.DataFrame
) -> pd.DataFrame:

    if (
        df is None
        or not isinstance(df, pd.DataFrame)
        or df.empty
    ):
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    if (
        "max" in out.columns
        and "high" not in out.columns
    ):
        rename["max"] = "high"

    if (
        "min" in out.columns
        and "low" not in out.columns
    ):
        rename["min"] = "low"

    if (
        "Open" in out.columns
        and "open" not in out.columns
    ):
        rename["Open"] = "open"

    if (
        "High" in out.columns
        and "high" not in out.columns
    ):
        rename["High"] = "high"

    if (
        "Low" in out.columns
        and "low" not in out.columns
    ):
        rename["Low"] = "low"

    if (
        "Close" in out.columns
        and "close" not in out.columns
    ):
        rename["Close"] = "close"

    if rename:
        out.rename(
            columns=rename,
            inplace=True
        )

    if (
        "open" not in out.columns
        or "close" not in out.columns
    ):
        return pd.DataFrame()

    out["open"] = pd.to_numeric(
        out["open"],
        errors="coerce"
    )

    out["close"] = pd.to_numeric(
        out["close"],
        errors="coerce"
    )

    if "high" in out.columns:

        out["high"] = pd.to_numeric(
            out["high"],
            errors="coerce"
        )

    if "low" in out.columns:

        out["low"] = pd.to_numeric(
            out["low"],
            errors="coerce"
        )

    if "from" in out.columns:

        out["from"] = pd.to_numeric(
            out["from"],
            errors="coerce"
        )

        out.dropna(
            subset=["from"],
            inplace=True
        )

        out.sort_values(
            "from",
            inplace=True
        )

    out.dropna(
        subset=["open", "close"],
        inplace=True
    )

    out.reset_index(
        drop=True,
        inplace=True
    )

    return out


# ============================================================
# SECUENCIA 5S
# ============================================================

def _validate_5s_sequence(
    micro: pd.DataFrame
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

    for i in range(
        1,
        len(timestamps)
    ):

        if (
            timestamps[i]
            - timestamps[i - 1]
            != 5
        ):
            return False

    return True


# ============================================================
# EXTRAER LAS 12 VELAS DE LA M1
# ============================================================

def _get_minute_micro_candles(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> pd.DataFrame:

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:
        return pd.DataFrame()

    minute_timestamp = None

    if candle_1m is not None:

        try:

            if "from" in candle_1m.index:

                minute_timestamp = int(
                    float(
                        candle_1m["from"]
                    )
                )

        except (
            TypeError,
            ValueError
        ):

            minute_timestamp = None

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = minute_timestamp

        end_time = (
            minute_timestamp
            + 60
        )

        micro = micro[
            (
                micro["from"]
                >= start_time
            )
            &
            (
                micro["from"]
                < end_time
            )
        ].copy()

        micro.sort_values(
            "from",
            inplace=True
        )

        micro.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True
        )

        micro.reset_index(
            drop=True,
            inplace=True
        )

    return micro


# ============================================================
# INFORMACIÓN INDIVIDUAL DE CADA VELA
# ============================================================

def _candle_metrics(
    candle: pd.Series
) -> Optional[Dict[str, float]]:

    opening = _to_float(
        candle.get("open")
    )

    closing = _to_float(
        candle.get("close")
    )

    if opening is None or closing is None:
        return None

    high = _to_float(
        candle.get("high")
    )

    low = _to_float(
        candle.get("low")
    )

    if high is None:
        high = max(
            opening,
            closing
        )

    if low is None:
        low = min(
            opening,
            closing
        )

    if high < low:
        return None

    total_range = high - low

    body = closing - opening

    body_abs = abs(body)

    if total_range > 0:

        body_ratio = (
            body_abs
            / total_range
        )

    else:

        body_ratio = 0.0

    upper_wick = (
        high
        - max(
            opening,
            closing
        )
    )

    lower_wick = (
        min(
            opening,
            closing
        )
        - low
    )

    if total_range > 0:

        upper_wick_ratio = (
            upper_wick
            / total_range
        )

        lower_wick_ratio = (
            lower_wick
            / total_range
        )

    else:

        upper_wick_ratio = 0.0
        lower_wick_ratio = 0.0

    close_position = 0.5

    if total_range > 0:

        close_position = (
            closing - low
        ) / total_range

    return {

        "open": opening,

        "close": closing,

        "high": high,

        "low": low,

        "range": total_range,

        "body": body,

        "body_abs": body_abs,

        "body_ratio": body_ratio,

        "upper_wick": upper_wick,

        "lower_wick": lower_wick,

        "upper_wick_ratio":
            upper_wick_ratio,

        "lower_wick_ratio":
            lower_wick_ratio,

        "close_position":
            close_position,
    }


# ============================================================
# ANALIZAR LAS 12 VELAS
# ============================================================

def _analyze_each_candle(
    micro: pd.DataFrame
) -> Optional[list]:

    if (
        micro is None
        or len(micro)
        != MICRO_CANDLES_REQUIRED
    ):
        return None

    result = []

    for index, candle in micro.iterrows():

        metrics = _candle_metrics(
            candle
        )

        if metrics is None:
            return None

        metrics["index"] = (
            len(result) + 1
        )

        if metrics["body"] > 0:

            metrics["direction"] = (
                "buyer"
            )

        elif metrics["body"] < 0:

            metrics["direction"] = (
                "seller"
            )

        else:

            metrics["direction"] = (
                "neutral"
            )

        result.append(metrics)

    return result


# ============================================================
# DOMINANCIA REAL
# ============================================================

def _calculate_global_dominance(
    micro: pd.DataFrame
) -> Dict[str, Any]:

    result = {

        "dominant": "neutral",

        "buy_score": 0.0,

        "sell_score": 0.0,

        "dominance_ratio": 0.0,

        "total_body": 0.0,
    }

    if (
        len(micro)
        != MICRO_CANDLES_REQUIRED
    ):
        return result

    buy_score = 0.0
    sell_score = 0.0

    for _, candle in micro.iterrows():

        metrics = _candle_metrics(
            candle
        )

        if metrics is None:
            return result

        body = metrics["body"]

        # Se utiliza el cuerpo real.
        if body > 0:

            buy_score += (
                metrics["body_abs"]
                * (
                    0.5
                    + metrics["body_ratio"]
                    / 2
                )
            )

        elif body < 0:

            sell_score += (
                metrics["body_abs"]
                * (
                    0.5
                    + metrics["body_ratio"]
                    / 2
                )
            )

    total_body = (
        buy_score
        + sell_score
    )

    result["buy_score"] = buy_score
    result["sell_score"] = sell_score
    result["total_body"] = total_body

    if total_body <= 0:
        return result

    ratio = (
        abs(
            buy_score
            - sell_score
        )
        / total_body
    )

    result["dominance_ratio"] = ratio

    if (
        buy_score > sell_score
        and ratio >= DOMINANCE_THRESHOLD
    ):

        result["dominant"] = (
            "buyer"
        )

    elif (
        sell_score > buy_score
        and ratio >= DOMINANCE_THRESHOLD
    ):

        result["dominant"] = (
            "seller"
        )

    return result


# ============================================================
# EFICIENCIA
# ============================================================

def _calculate_efficiency(
    micro: pd.DataFrame
) -> Dict[str, Any]:

    result = {

        "efficiency": 0.0,

        "net_movement": 0.0,

        "total_abs_body": 0.0,
    }

    if (
        len(micro)
        != MICRO_CANDLES_REQUIRED
    ):
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

        opening = _to_float(
            candle["open"]
        )

        closing = _to_float(
            candle["close"]
        )

        if (
            opening is None
            or closing is None
        ):
            return result

        total_abs_body += abs(
            closing - opening
        )

    net_movement = (
        last_close
        - first_open
    )

    result["net_movement"] = (
        net_movement
    )

    result["total_abs_body"] = (
        total_abs_body
    )

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
    micro: pd.DataFrame
) -> Dict[str, Any]:

    result = {

        "final_control":
            "neutral",

        "final_net":
            0.0,

        "final_buy_movement":
            0.0,

        "final_sell_movement":
            0.0,
    }

    if (
        len(micro)
        < FINAL_CONTROL_CANDLES
    ):
        return result

    final_micro = micro.iloc[
        -FINAL_CONTROL_CANDLES:
    ]

    final_net = 0.0

    final_buy = 0.0
    final_sell = 0.0

    for _, candle in final_micro.iterrows():

        opening = _to_float(
            candle["open"]
        )

        closing = _to_float(
            candle["close"]
        )

        if (
            opening is None
            or closing is None
        ):
            return result

        movement = (
            closing - opening
        )

        final_net += movement

        if movement > 0:

            final_buy += movement

        elif movement < 0:

            final_sell += abs(
                movement
            )

    result["final_net"] = final_net

    result["final_buy_movement"] = (
        final_buy
    )

    result["final_sell_movement"] = (
        final_sell
    )

    if final_net > 0:

        result["final_control"] = (
            "buyer"
        )

    elif final_net < 0:

        result["final_control"] = (
            "seller"
        )

    return result


# ============================================================
# ANALISIS ESPECÍFICO DE N
#
# ESTA ES LA PARTE PRINCIPAL DEL NUEVO SISTEMA
# ============================================================

def _analyze_last_candle(
    candles_analysis: list
) -> Dict[str, Any]:

    result = {

        "n_direction":
            "neutral",

        "n_strength":
            0.0,

        "n_body_ratio":
            0.0,

        "n_close_position":
            0.5,

        "n_upper_rejection":
            False,

        "n_lower_rejection":
            False,

        "n_bullish_pressure":
            0.0,

        "n_bearish_pressure":
            0.0,

        "n_continuation":
            False,

        "n_reversal":
            False,

        "n_signal":
            None,
    }

    if not candles_analysis:
        return result

    n = candles_analysis[-1]

    previous = None

    if len(candles_analysis) >= 2:
        previous = candles_analysis[-2]

    result["n_direction"] = (
        n["direction"]
    )

    result["n_body_ratio"] = (
        n["body_ratio"]
    )

    result["n_close_position"] = (
        n["close_position"]
    )

    result["n_strength"] = (
        n["body_abs"]
        * (
            0.5
            + n["body_ratio"]
            / 2
        )
    )

    # --------------------------------------------------------
    # PRESIÓN ALCISTA
    # --------------------------------------------------------

    bullish_pressure = (
        n["body_abs"]
        * n["body_ratio"]
    )

    # Cierre cerca del máximo.
    if n["close_position"] >= 0.70:

        bullish_pressure *= 1.35

    # Mecha inferior importante =
    # rechazo de precios inferiores.
    if (
        n["lower_wick_ratio"]
        >= 0.25
    ):

        result[
            "n_lower_rejection"
        ] = True

        bullish_pressure *= 1.15

    # --------------------------------------------------------
    # PRESIÓN BAJISTA
    # --------------------------------------------------------

    bearish_pressure = (
        n["body_abs"]
        * n["body_ratio"]
    )

    # Cierre cerca del mínimo.
    if n["close_position"] <= 0.30:

        bearish_pressure *= 1.35

    # Mecha superior importante =
    # rechazo de precios superiores.
    if (
        n["upper_wick_ratio"]
        >= 0.25
    ):

        result[
            "n_upper_rejection"
        ] = True

        bearish_pressure *= 1.15

    result[
        "n_bullish_pressure"
    ] = bullish_pressure

    result[
        "n_bearish_pressure"
    ] = bearish_pressure

    # --------------------------------------------------------
    # CONTINUACIÓN
    # --------------------------------------------------------

    if previous is not None:

        if (
            previous["direction"]
            == "buyer"
            and n["direction"]
            == "buyer"
        ):

            if (
                n["close_position"]
                >= 0.60
            ):

                result[
                    "n_continuation"
                ] = True

        elif (
            previous["direction"]
            == "seller"
            and n["direction"]
            == "seller"
        ):

            if (
                n["close_position"]
                <= 0.40
            ):

                result[
                    "n_continuation"
                ] = True

    # --------------------------------------------------------
    # POSIBLE REVERSIÓN
    # --------------------------------------------------------

    if previous is not None:

        if (
            previous["direction"]
            == "seller"
            and n["direction"]
            == "buyer"
            and n["lower_wick_ratio"]
            >= 0.20
        ):

            result[
                "n_reversal"
            ] = True

        elif (
            previous["direction"]
            == "buyer"
            and n["direction"]
            == "seller"
            and n["upper_wick_ratio"]
            >= 0.20
        ):

            result[
                "n_reversal"
            ] = True

    # --------------------------------------------------------
    # SEÑAL PRELIMINAR N+1
    # --------------------------------------------------------

    if (
        bullish_pressure
        > bearish_pressure
        and n["body_ratio"]
        >= MIN_BODY_RATIO
    ):

        result["n_signal"] = "call"

    elif (
        bearish_pressure
        > bullish_pressure
        and n["body_ratio"]
        >= MIN_BODY_RATIO
    ):

        result["n_signal"] = "put"

    return result


# ============================================================
# MOVIMIENTO DE LAS ÚLTIMAS VELAS
# ============================================================

def _calculate_sequence_pressure(
    candles_analysis: list
) -> Dict[str, Any]:

    result = {

        "sequence_direction":
            "neutral",

        "sequence_score":
            0.0,

        "last_move_agrees":
            False,

        "pressure_change":
            0.0,
    }

    if not candles_analysis:
        return result

    buyer = 0.0
    seller = 0.0

    for candle in candles_analysis:

        strength = (
            candle["body_abs"]
            * (
                0.5
                + candle["body_ratio"]
                / 2
            )
        )

        if candle["direction"] == "buyer":

            buyer += strength

        elif (
            candle["direction"]
            == "seller"
        ):

            seller += strength

    total = buyer + seller

    if total <= 0:
        return result

    difference = (
        buyer - seller
    )

    result["sequence_score"] = (
        abs(difference)
        / total
    )

    if difference > 0:

        result[
            "sequence_direction"
        ] = "buyer"

    elif difference < 0:

        result[
            "sequence_direction"
        ] = "seller"

    last = candles_analysis[-1]

    if (
        result["sequence_direction"]
        == last["direction"]
    ):

        result[
            "last_move_agrees"
        ] = True

    # --------------------------------------------------------
    # CAMBIO DE PRESIÓN
    # --------------------------------------------------------

    if len(candles_analysis) >= 6:

        first_half = (
            candles_analysis[:6]
        )

        second_half = (
            candles_analysis[6:]
        )

        first_buyer = sum(
            c["body_abs"]
            for c in first_half
            if c["direction"]
            == "buyer"
        )

        first_seller = sum(
            c["body_abs"]
            for c in first_half
            if c["direction"]
            == "seller"
        )

        second_buyer = sum(
            c["body_abs"]
            for c in second_half
            if c["direction"]
            == "buyer"
        )

        second_seller = sum(
            c["body_abs"]
            for c in second_half
            if c["direction"]
            == "seller"
        )

        first_pressure = (
            first_buyer
            - first_seller
        )

        second_pressure = (
            second_buyer
            - second_seller
        )

        result[
            "pressure_change"
        ] = (
            second_pressure
            - first_pressure
        )

    return result


# ============================================================
# RANGO
# ============================================================

def _calculate_micro_range(
    micro: pd.DataFrame
) -> Optional[float]:

    if micro.empty:
        return None

    if (
        "high" in micro.columns
        and "low" in micro.columns
    ):

        highs = pd.to_numeric(
            micro["high"],
            errors="coerce"
        )

        lows = pd.to_numeric(
            micro["low"],
            errors="coerce"
        )

        if (
            highs.notna().all()
            and lows.notna().all()
        ):

            return (
                float(highs.max())
                - float(lows.min())
            )

    closes = pd.to_numeric(
        micro["close"],
        errors="coerce"
    )

    opens = pd.to_numeric(
        micro["open"],
        errors="coerce"
    )

    if (
        closes.isna().any()
        or opens.isna().any()
    ):
        return None

    high_value = max(
        float(closes.max()),
        float(opens.max())
    )

    low_value = min(
        float(closes.min()),
        float(opens.min())
    )

    return (
        high_value
        - low_value
    )


# ============================================================
# CONTEXTO DE RANGO
# ============================================================

def _calculate_range_context(
    candle_1m: pd.Series,
    previous_m1: Optional[pd.DataFrame],
    current_micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {

        "range_context_available":
            False,

        "current_range":
            None,

        "average_previous_range":
            None,

        "range_ratio":
            None,

        "range_ok":
            True,
    }

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

            current_range = (
                high - low
            )

    if current_range is None:

        current_range = (
            _calculate_micro_range(
                current_micro
            )
        )

    result[
        "current_range"
    ] = current_range

    if (
        previous_m1 is None
        or not isinstance(
            previous_m1,
            pd.DataFrame
        )
        or previous_m1.empty
    ):

        return result

    if (
        "high" not in previous_m1.columns
        and "High"
        in previous_m1.columns
    ):

        previous_m1 = (
            previous_m1.rename(
                columns={
                    "High": "high"
                }
            )
        )

    if (
        "low" not in previous_m1.columns
        and "Low"
        in previous_m1.columns
    ):

        previous_m1 = (
            previous_m1.rename(
                columns={
                    "Low": "low"
                }
            )
        )

    if (
        "high" not in previous_m1.columns
        or "low"
        not in previous_m1.columns
    ):

        return result

    previous = previous_m1.tail(
        PREVIOUS_M1_COUNT
    ).copy()

    previous["high"] = pd.to_numeric(
        previous["high"],
        errors="coerce"
    )

    previous["low"] = pd.to_numeric(
        previous["low"],
        errors="coerce"
    )

    previous.dropna(
        subset=[
            "high",
            "low"
        ],
        inplace=True
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

    result[
        "range_context_available"
    ] = True

    result[
        "range_ratio"
    ] = ratio

    result[
        "range_ok"
    ] = (
        ratio
        >= MIN_RANGE_RATIO
    )

    return result


# ============================================================
# POSICIÓN DEL CIERRE
# ============================================================

def _calculate_close_position(
    micro: pd.DataFrame
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
            errors="coerce"
        )

        lows = pd.to_numeric(
            micro["low"],
            errors="coerce"
        )

        if (
            highs.notna().all()
            and lows.notna().all()
        ):

            high = float(
                highs.max()
            )

            low = float(
                lows.min()
            )

    if (
        high is None
        or low is None
    ):

        opens = pd.to_numeric(
            micro["open"],
            errors="coerce"
        )

        closes = pd.to_numeric(
            micro["close"],
            errors="coerce"
        )

        if (
            opens.isna().any()
            or closes.isna().any()
        ):

            return None

        high = max(
            float(opens.max()),
            float(closes.max())
        )

        low = min(
            float(opens.min()),
            float(closes.min())
        )

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if (
        last_close is None
        or high <= low
    ):

        return None

    return (
        last_close - low
    ) / (
        high - low
    )


# ============================================================
# ANÁLISIS PRINCIPAL
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

        "range_context_available":
            False,

        "range_ok": True,

        "n_signal": None,

        "n_direction": None,

        "n_strength": 0.0,

        "n_body_ratio": 0.0,

        "n_close_position": 0.5,

        "n_upper_rejection": False,

        "n_lower_rejection": False,

        "n_continuation": False,

        "n_reversal": False,

        "sequence_direction": None,

        "sequence_score": 0.0,

        "last_move_agrees": False,

        "pressure_change": 0.0,

        "candles_analysis": [],

        "quality_checks": {

            "dominance_ok": False,

            "efficiency_ok": False,

            "final_control_ok": False,

            "last_close_ok": False,

            "m1_color_ok": False,

            "close_position_ok": False,

            "range_ok": True,

            "n_strength_ok": False,

            "n_sequence_ok": False,

            "n_close_ok": False,

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

    result[
        "minute_open"
    ] = opening

    result[
        "minute_close"
    ] = closing

    if "from" in candle_1m.index:

        try:

            result[
                "minute_timestamp"
            ] = int(
                float(
                    candle_1m["from"]
                )
            )

        except (
            TypeError,
            ValueError
        ):

            pass

    # ========================================================
    # 12 VELAS
    # ========================================================

    micro = _get_minute_micro_candles(
        candle_1m,
        candles_5s
    )

    if micro.empty:

        result["reason"] = (
            "no hay microvelas 5s"
        )

        return result

    result[
        "micro_candles_count"
    ] = len(micro)

    if not _validate_5s_sequence(
        micro
    ):

        result["reason"] = (
            "secuencia 5s inválida"
        )

        return result

    if (
        len(micro)
        != MICRO_CANDLES_REQUIRED
    ):

        result["reason"] = (
            "M1 inválida: se requieren "
            f"{MICRO_CANDLES_REQUIRED} "
            "velas de 5s y se recibieron "
            f"{len(micro)}"
        )

        return result

    # ========================================================
    # ANALIZAR CADA 5S
    # ========================================================

    candles_analysis = (
        _analyze_each_candle(
            micro
        )
    )

    if candles_analysis is None:

        result["reason"] = (
            "error analizando velas 5S"
        )

        return result

    result[
        "candles_analysis"
    ] = candles_analysis

    # ========================================================
    # ÚLTIMA VELA N
    # ========================================================

    last = candles_analysis[-1]

    result[
        "last_5s_close"
    ] = last["close"]

    n_analysis = (
        _analyze_last_candle(
            candles_analysis
        )
    )

    result[
        "n_signal"
    ] = n_analysis[
        "n_signal"
    ]

    result[
        "n_direction"
    ] = n_analysis[
        "n_direction"
    ]

    result[
        "n_strength"
    ] = n_analysis[
        "n_strength"
    ]

    result[
        "n_body_ratio"
    ] = n_analysis[
        "n_body_ratio"
    ]

    result[
        "n_close_position"
    ] = n_analysis[
        "n_close_position"
    ]

    result[
        "n_upper_rejection"
    ] = n_analysis[
        "n_upper_rejection"
    ]

    result[
        "n_lower_rejection"
    ] = n_analysis[
        "n_lower_rejection"
    ]

    result[
        "n_continuation"
    ] = n_analysis[
        "n_continuation"
    ]

    result[
        "n_reversal"
    ] = n_analysis[
        "n_reversal"
    ]

    # ========================================================
    # SECUENCIA
    # ========================================================

    sequence = (
        _calculate_sequence_pressure(
            candles_analysis
        )
    )

    result[
        "sequence_direction"
    ] = sequence[
        "sequence_direction"
    ]

    result[
        "sequence_score"
    ] = sequence[
        "sequence_score"
    ]

    result[
        "last_move_agrees"
    ] = sequence[
        "last_move_agrees"
    ]

    result[
        "pressure_change"
    ] = sequence[
        "pressure_change"
    ]

    # ========================================================
    # DOMINANCIA
    # ========================================================

    dominance = (
        _calculate_global_dominance(
            micro
        )
    )

    result[
        "buy_score"
    ] = dominance[
        "buy_score"
    ]

    result[
        "sell_score"
    ] = dominance[
        "sell_score"
    ]

    result[
        "dominance_ratio"
    ] = dominance[
        "dominance_ratio"
    ]

    result[
        "dominant"
    ] = dominance[
        "dominant"
    ]

    dominance_ok = (

        result["dominant"]
        in (
            "buyer",
            "seller"
        )

        and

        result[
            "dominance_ratio"
        ]
        >= DOMINANCE_THRESHOLD
    )

    result[
        "quality_checks"
    ][
        "dominance_ok"
    ] = dominance_ok

    # ========================================================
    # EFICIENCIA
    # ========================================================

    efficiency = (
        _calculate_efficiency(
            micro
        )
    )

    result[
        "efficiency"
    ] = efficiency[
        "efficiency"
    ]

    result[
        "net_movement"
    ] = efficiency[
        "net_movement"
    ]

    efficiency_ok = (
        result["efficiency"]
        >= EFFICIENCY_THRESHOLD
    )

    result[
        "quality_checks"
    ][
        "efficiency_ok"
    ] = efficiency_ok

    # ========================================================
    # CONTROL FINAL
    # ========================================================

    final_control = (
        _calculate_final_control(
            micro
        )
    )

    result[
        "final_control"
    ] = final_control[
        "final_control"
    ]

    result[
        "final_net"
    ] = final_control[
        "final_net"
    ]

    result[
        "final_buy_movement"
    ] = final_control[
        "final_buy_movement"
    ]

    result[
        "final_sell_movement"
    ] = final_control[
        "final_sell_movement"
    ]

    # ========================================================
    # POSICIÓN CIERRE
    # ========================================================

    close_position = (
        _calculate_close_position(
            micro
        )
    )

    result[
        "close_position"
    ] = close_position

    # ========================================================
    # RANGO
    # ========================================================

    range_context = (
        _calculate_range_context(
            candle_1m,
            previous_m1,
            micro
        )
    )

    result[
        "current_range"
    ] = range_context[
        "current_range"
    ]

    result[
        "average_previous_range"
    ] = range_context[
        "average_previous_range"
    ]

    result[
        "range_ratio"
    ] = range_context[
        "range_ratio"
    ]

    result[
        "range_context_available"
    ] = range_context[
        "range_context_available"
    ]

    result[
        "range_ok"
    ] = range_context[
        "range_ok"
    ]

    result[
        "quality_checks"
    ][
        "range_ok"
    ] = result[
        "range_ok"
    ]

    # ========================================================
    # FILTROS N
    # ========================================================

    n_strength_ok = (
        n_analysis[
            "n_body_ratio"
        ]
        >= LAST_CANDLE_BODY_RATIO
    )

    result[
        "quality_checks"
    ][
        "n_strength_ok"
    ] = n_strength_ok

    n_close_ok = False

    if (
        n_analysis[
            "n_signal"
        ]
        == "call"
    ):

        n_close_ok = (
            n_analysis[
                "n_close_position"
            ]
            >= CLOSE_POSITION_CALL
        )

    elif (
        n_analysis[
            "n_signal"
        ]
        == "put"
    ):

        n_close_ok = (
            n_analysis[
                "n_close_position"
            ]
            <= CLOSE_POSITION_PUT
        )

    result[
        "quality_checks"
    ][
        "n_close_ok"
    ] = n_close_ok

    # ========================================================
    # DIRECCIÓN N+1
    #
    # NO se ejecuta una dirección contraria
    # solamente por mayoría.
    #
    # La última vela N debe confirmar.
    # ========================================================

    candidate = (
        n_analysis[
            "n_signal"
        ]
    )

    if candidate is None:

        result["reason"] = (
            "N+1 bloqueada: "
            "vela N sin dirección clara"
        )

        return result

    # ========================================================
    # CALL N+1
    # ========================================================

    if candidate == "call":

        final_control_ok = (
            result[
                "final_control"
            ]
            == "buyer"
        )

        last_close_ok = (
            last["close"]
            > opening
        )

        m1_color_ok = (
            closing
            > opening
        )

        close_position_ok = (
            close_position is not None
            and close_position
            >= CLOSE_POSITION_CALL
        )

        sequence_ok = (
            result[
                "sequence_direction"
            ]
            == "buyer"
            or
            result[
                "pressure_change"
            ] > 0
        )

        result[
            "quality_checks"
        ][
            "final_control_ok"
        ] = final_control_ok

        result[
            "quality_checks"
        ][
            "last_close_ok"
        ] = last_close_ok

        result[
            "quality_checks"
        ][
            "m1_color_ok"
        ] = m1_color_ok

        result[
            "quality_checks"
        ][
            "close_position_ok"
        ] = close_position_ok

        result[
            "quality_checks"
        ][
            "n_sequence_ok"
        ] = sequence_ok

        if not n_strength_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "vela N débil"
            )

            return result

        if not n_close_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "vela N no terminó cerca "
                "del extremo superior"
            )

            return result

        if not dominance_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "dominancia insuficiente"
            )

            return result

        if not efficiency_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "eficiencia insuficiente"
            )

            return result

        if not final_control_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "últimas 3 velas no confirman "
                "control comprador"
            )

            return result

        if not last_close_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "cierre N no supera apertura M1"
            )

            return result

        if not m1_color_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "M1 no terminó verde"
            )

            return result

        if not close_position_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "cierre fuera de zona superior"
            )

            return result

        if not sequence_ok:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "secuencia no confirma presión "
                "compradora"
            )

            return result

        if not result["range_ok"]:

            result["reason"] = (
                "N+1 CALL bloqueada: "
                "rango M1 insuficiente"
            )

            return result

        # ====================================================
        # CONFIRMACIÓN
        # ====================================================

        result["signal"] = "call"

        result["valid"] = True

        result["reason"] = (
            "N+1 CALL CONFIRMADA: "
            "movimiento 5S + vela N fuerte + "
            "cierre superior + dominancia + "
            "eficiencia + control final + "
            "secuencia compradora"
        )

        return result

    # ========================================================
    # PUT N+1
    # ========================================================

    if candidate == "put":

        final_control_ok = (
            result[
                "final_control"
            ]
            == "seller"
        )

        last_close_ok = (
            last["close"]
            < opening
        )

        m1_color_ok = (
            closing
            < opening
        )

        close_position_ok = (
            close_position is not None
            and close_position
            <= CLOSE_POSITION_PUT
        )

        sequence_ok = (
            result[
                "sequence_direction"
            ]
            == "seller"
            or
            result[
                "pressure_change"
            ] < 0
        )

        result[
            "quality_checks"
        ][
            "final_control_ok"
        ] = final_control_ok

        result[
            "quality_checks"
        ][
            "last_close_ok"
        ] = last_close_ok

        result[
            "quality_checks"
        ][
            "m1_color_ok"
        ] = m1_color_ok

        result[
            "quality_checks"
        ][
            "close_position_ok"
        ] = close_position_ok

        result[
            "quality_checks"
        ][
            "n_sequence_ok"
        ] = sequence_ok

        if not n_strength_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "vela N débil"
            )

            return result

        if not n_close_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "vela N no terminó cerca "
                "del extremo inferior"
            )

            return result

        if not dominance_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "dominancia insuficiente"
            )

            return result

        if not efficiency_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "eficiencia insuficiente"
            )

            return result

        if not final_control_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "últimas 3 velas no confirman "
                "control vendedor"
            )

            return result

        if not last_close_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "cierre N no está debajo "
                "de apertura M1"
            )

            return result

        if not m1_color_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "M1 no terminó roja"
            )

            return result

        if not close_position_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "cierre fuera de zona inferior"
            )

            return result

        if not sequence_ok:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "secuencia no confirma presión "
                "vendedora"
            )

            return result

        if not result["range_ok"]:

            result["reason"] = (
                "N+1 PUT bloqueada: "
                "rango M1 insuficiente"
            )

            return result

        # ====================================================
        # CONFIRMACIÓN
        # ====================================================

        result["signal"] = "put"

        result["valid"] = True

        result["reason"] = (
            "N+1 PUT CONFIRMADA: "
            "movimiento 5S + vela N fuerte + "
            "cierre inferior + dominancia + "
            "eficiencia + control final + "
            "secuencia vendedora"
        )

        return result

    result["reason"] = (
        "N+1 sin señal"
    )

    return result


# ============================================================
# ALIAS PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_minute(
        candle_1m,
        candles_5s,
        previous_m1
    )


# ============================================================
# GET SIGNAL
# ============================================================

def get_signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    result = analyze_market(
        candle_1m,
        candles_5s,
        previous_m1
    )

    return result.get(
        "signal"
    )


def signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
        previous_m1
    )


# ============================================================
# COMPATIBILIDAD CON bot.py
# ============================================================

def _build_strategy_inputs(
    candles_5s: Any
):

    if candles_5s is None:
        return None, None

    if isinstance(
        candles_5s,
        pd.DataFrame
    ):

        df = candles_5s.copy()

    else:

        try:

            df = pd.DataFrame(
                list(candles_5s)
            )

        except Exception:

            return None, None

    df = _normalize_5s(
        df
    )

    if df.empty:
        return None, None

    if (
        len(df)
        != MICRO_CANDLES_REQUIRED
    ):

        return None, None

    if "from" not in df.columns:
        return None, None

    try:

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce"
        )

        df.dropna(
            subset=["from"],
            inplace=True
        )

        df.sort_values(
            "from",
            inplace=True
        )

        df.reset_index(
            drop=True,
            inplace=True
        )

    except Exception:

        return None, None

    if (
        len(df)
        != MICRO_CANDLES_REQUIRED
    ):

        return None, None

    if df[
        "from"
    ].duplicated().any():

        return None, None

    timestamps = (
        df["from"]
        .astype(int)
        .tolist()
    )

    for i in range(
        1,
        len(timestamps)
    ):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:

            return None, None

    first_timestamp = (
        timestamps[0]
    )

    minute_start = (
        first_timestamp // 60
    ) * 60

    for timestamp in timestamps:

        if not (
            minute_start
            <= timestamp
            < minute_start + 60
        ):

            return None, None

    first = df.iloc[0]

    last = df.iloc[-1]

    first_open = _to_float(
        first["open"]
    )

    last_close = _to_float(
        last["close"]
    )

    if first_open is None:
        return None, None

    if last_close is None:
        return None, None

    high = None
    low = None

    if (
        "high" in df.columns
        and "low" in df.columns
    ):

        highs = pd.to_numeric(
            df["high"],
            errors="coerce"
        )

        lows = pd.to_numeric(
            df["low"],
            errors="coerce"
        )

        if (
            highs.notna().all()
            and lows.notna().all()
        ):

            high = float(
                highs.max()
            )

            low = float(
                lows.min()
            )

    if (
        high is None
        or low is None
    ):

        opens = pd.to_numeric(
            df["open"],
            errors="coerce"
        )

        closes = pd.to_numeric(
            df["close"],
            errors="coerce"
        )

        if (
            opens.isna().any()
            or closes.isna().any()
        ):

            return None, None

        high = max(
            float(opens.max()),
            float(closes.max())
        )

        low = min(
            float(opens.min()),
            float(closes.min())
        )

    candle_1m = pd.Series({

        "from":
            int(minute_start),

        "open":
            float(first_open),

        "close":
            float(last_close),

        "high":
            float(high),

        "low":
            float(low),
    })

    return candle_1m, df


# ============================================================
# CHECK PATTERN
# ============================================================

def check_pattern(
    candles_5s: Any
) -> Optional[str]:

    candle_1m, micro = (
        _build_strategy_inputs(
            candles_5s
        )
    )

    if (
        candle_1m is None
        or micro is None
    ):

        return None

    result = analyze_market(
        candle_1m,
        micro
    )

    return result.get(
        "signal"
    )


# ============================================================
# DIRECCIÓN M1
# ============================================================

def get_m1_direction(
    candles_5s: Any
) -> Optional[str]:

    candle_1m, micro = (
        _build_strategy_inputs(
            candles_5s
        )
    )

    if (
        candle_1m is None
        or micro is None
    ):

        return None

    opening = _to_float(
        candle_1m.get("open")
    )

    closing = _to_float(
        candle_1m.get("close")
    )

    if (
        opening is None
        or closing is None
    ):

        return None

    if closing > opening:

        return "call"

    if closing < opening:

        return "put"

    return None


# ============================================================
# ANÁLISIS COMPLETO
# ============================================================

def get_strategy_analysis(
    candles_5s: Any
) -> Optional[Dict[str, Any]]:

    candle_1m, micro = (
        _build_strategy_inputs(
            candles_5s
        )
    )

    if (
        candle_1m is None
        or micro is None
    ):

        return None

    return analyze_market(
        candle_1m,
        micro
    )


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    print(
        "strategy.py cargado correctamente."
    )

    print(
        "1 M1 = exactamente "
        "12 velas de 5S."
    )

    print(
        "Cada vela 5S es analizada "
        "individualmente."
    )

    print(
        "La última vela N determina "
        "el posible movimiento N+1."
    )

    print(
        "La señal final requiere "
        "confirmación matemática."
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
        f"Cuerpo mínimo N = "
        f"{LAST_CANDLE_BODY_RATIO:.0%}"
    )

    print(
        f"Control final = "
        f"últimas {FINAL_CONTROL_CANDLES} "
        f"velas"
    )

    print(
        "Señal = movimiento esperado "
        "de N+1."
    )
