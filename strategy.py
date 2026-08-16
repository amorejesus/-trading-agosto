from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


MICRO_CANDLES_REQUIRED = 12
FINAL_CONTROL_CANDLES = 3

DOMINANCE_THRESHOLD = 0.25
EFFICIENCY_THRESHOLD = 0.45
MIN_RANGE_RATIO = 0.60

CLOSE_POSITION_CALL = 0.65
CLOSE_POSITION_PUT = 0.35

PREVIOUS_M1_COUNT = 5


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:
            return False

    return True


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

    ratio = (
        abs(buy_score - sell_score)
        / total_body
    )

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


def _calculate_micro_range(
    micro: pd.DataFrame,
) -> Optional[float]:

    if micro.empty:
        return None

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

            return (
                float(highs.max())
                - float(lows.min())
            )

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

    if (
        previous_m1 is None
        or not isinstance(
            previous_m1,
            pd.DataFrame,
        )
        or previous_m1.empty
    ):
        return result

    previous = previous_m1.copy()

    rename = {}

    if (
        "High" in previous.columns
        and "high" not in previous.columns
    ):
        rename["High"] = "high"

    if (
        "Low" in previous.columns
        and "low" not in previous.columns
    ):
        rename["Low"] = "low"

    if rename:
        previous.rename(
            columns=rename,
            inplace=True,
        )

    if (
        "high" not in previous.columns
        or "low" not in previous.columns
    ):
        return result

    previous = previous.tail(
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

    if len(micro) != MICRO_CANDLES_REQUIRED:

        result["reason"] = (
            "M1 inválida: se requieren "
            f"{MICRO_CANDLES_REQUIRED} velas "
            "de 5s"
        )

        return result

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if last_close is None:

        result["reason"] = (
            "cierre 5s #12 inválido"
        )

        return result

    result["last_5s_close"] = last_close

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
        result["dominant"]
        in ("buyer", "seller")
        and result["dominance_ratio"]
        >= DOMINANCE_THRESHOLD
    )

    result[
        "quality_checks"
    ]["dominance_ok"] = dominance_ok

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

    close_position = _calculate_close_position(
        micro
    )

    result["close_position"] = close_position

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
    ]["range_ok"] = result["range_ok"]

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
                "posición de cierre inválida"
            )
            return result

        if not result["range_ok"]:
            result["reason"] = (
                "CALL bloqueada: "
                "rango M1 insuficiente"
            )
            return result

        result["signal"] = "call"
        result["valid"] = True

        result["reason"] = (
            "CALL confirmada"
        )

        return result

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
                "posición de cierre inválida"
            )
            return result

        if not result["range_ok"]:
            result["reason"] = (
                "PUT bloqueada: "
                "rango M1 insuficiente"
            )
            return result

        result["signal"] = "put"
        result["valid"] = True

        result["reason"] = (
            "PUT confirmada"
        )

        return result

    result["reason"] = (
        "sin señal: "
        "no existe dominante suficiente"
    )

    return result


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


def _prepare_5s_for_compatibility(
    candles_5s: Any,
) -> pd.DataFrame:

    if candles_5s is None:
        return pd.DataFrame()

    if isinstance(candles_5s, pd.DataFrame):
        return _normalize_5s(candles_5s)

    if isinstance(
        candles_5s,
        (list, tuple),
    ):

        if len(candles_5s) == 0:
            return pd.DataFrame()

        try:
            df = pd.DataFrame(
                list(candles_5s)
            )
        except Exception:
            return pd.DataFrame()

        return _normalize_5s(df)

    return pd.DataFrame()


def check_pattern(
    candles_5s: Any,
) -> Optional[str]:

    micro = _prepare_5s_for_compatibility(
        candles_5s
    )

    if micro.empty:
        return None

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return None

    if not _validate_5s_sequence(micro):
        return None

    dominance = _calculate_global_dominance(
        micro
    )

    dominant = dominance["dominant"]

    if dominant not in (
        "buyer",
        "seller",
    ):
        return None

    if (
        dominance["dominance_ratio"]
        < DOMINANCE_THRESHOLD
    ):
        return None

    efficiency = _calculate_efficiency(
        micro
    )

    if (
        efficiency["efficiency"]
        < EFFICIENCY_THRESHOLD
    ):
        return None

    final_control = _calculate_final_control(
        micro
    )

    if dominant == "buyer":

        if (
            final_control["final_control"]
            != "buyer"
        ):
            return None

        return "call"

    if dominant == "seller":

        if (
            final_control["final_control"]
            != "seller"
        ):
            return None

        return "put"

    return None


def get_m1_direction(
    candles_5s: Any,
) -> Optional[str]:

    micro = _prepare_5s_for_compatibility(
        candles_5s
    )

    if micro.empty:
        return None

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return None

    if not _validate_5s_sequence(micro):
        return None

    first_open = _to_float(
        micro.iloc[0]["open"]
    )

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if first_open is None:
        return None

    if last_close is None:
        return None

    if last_close > first_open:
        return "verde"

    if last_close < first_open:
        return "rojo"

    return None


if __name__ == "__main__":

    print("strategy.py cargado correctamente.")
    print("1 M1 = exactamente 12 velas de 5S")
    print("check_pattern() disponible.")
    print("get_m1_direction() disponible.")
