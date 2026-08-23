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
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}
    if "max" in out.columns and "high" not in out.columns:
        rename["max"] = "high"
    if "min" in out.columns and "low" not in out.columns:
        rename["min"] = "low"

    if rename:
        out.rename(columns=rename, inplace=True)

    for col in ["open", "close", "high", "low", "from"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out.dropna(subset=["open", "close", "from"], inplace=True)
    out.sort_values("from", inplace=True)

    out.drop_duplicates(subset=["from"], keep="last", inplace=True)

    out.reset_index(drop=True, inplace=True)
    return out


def _validate_5s_sequence(micro: pd.DataFrame) -> bool:
    if len(micro) != MICRO_CANDLES_REQUIRED:
        return False

    if "from" not in micro.columns:
        return False

    timestamps = micro["from"].astype(int).tolist()

    for i in range(1, len(timestamps)):
        if timestamps[i] <= timestamps[i - 1]:
            return False
        if timestamps[i] - timestamps[i - 1] != 5:
            return False

    return True


def _get_minute_micro_candles(candle_1m, candles_5s) -> pd.DataFrame:
    micro = _normalize_5s(candles_5s)

    if micro.empty:
        return pd.DataFrame()

    try:
        minute_timestamp = int(float(candle_1m["from"]))
    except:
        return pd.DataFrame()

    start_time = minute_timestamp
    end_time = minute_timestamp + 60

    micro = micro[(micro["from"] >= start_time) & (micro["from"] < end_time)]

    micro = micro.sort_values("from")
    micro.drop_duplicates(subset=["from"], keep="last", inplace=True)
    micro.reset_index(drop=True, inplace=True)

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return pd.DataFrame()

    return micro


def _calculate_global_dominance(micro: pd.DataFrame) -> Dict[str, Any]:
    result = {
        "dominant": "neutral",
        "buy_score": 0.0,
        "sell_score": 0.0,
        "dominance_ratio": 0.0,
    }

    if len(micro) != MICRO_CANDLES_REQUIRED:
        return result

    buy = 0.0
    sell = 0.0

    for _, c in micro.iterrows():
        o = _to_float(c["open"])
        cl = _to_float(c["close"])

        if o is None or cl is None:
            return result

        body = cl - o

        if body > 0:
            buy += body
        else:
            sell += abs(body)

    total = buy + sell

    if total <= 0:
        return result

    ratio = abs(buy - sell) / total

    result["buy_score"] = buy
    result["sell_score"] = sell
    result["dominance_ratio"] = ratio

    if ratio >= DOMINANCE_THRESHOLD:
        result["dominant"] = "buyer" if buy > sell else "seller"

    return result


def analyze_market(candle_1m, candles_5s, previous_m1=None):

    result = {
        "signal": None,
        "valid": False,
        "reason": "sin señal",
    }

    micro = _get_minute_micro_candles(candle_1m, candles_5s)

    if micro.empty:
        result["reason"] = "micro inválido"
        return result

    if not _validate_5s_sequence(micro):
        result["reason"] = "secuencia 5s inválida"
        return result

    dominance = _calculate_global_dominance(micro)

    if dominance["dominant"] == "neutral":
        result["reason"] = "sin dominancia"
        return result

    m1_open = _to_float(candle_1m.get("open"))
    m1_close = _to_float(candle_1m.get("close"))

    if m1_open is None or m1_close is None:
        result["reason"] = "M1 inválido"
        return result

    if dominance["dominant"] == "buyer" and m1_close > m1_open:
        result["signal"] = "call"
        result["valid"] = True
        result["reason"] = "CALL confirmada"
        return result

    if dominance["dominant"] == "seller" and m1_close < m1_open:
        result["signal"] = "put"
        result["valid"] = True
        result["reason"] = "PUT confirmada"
        return result

    result["reason"] = "no confirma dirección"
    return result


# ============================================================
# 🔥 FIX IMPORTANTE: COMPATIBILIDAD CON BOT.PY
# ============================================================

def analyze_live_candle(*args, **kwargs):
    """
    🔧 FIX: compatibilidad con bot.py antiguo
    NO cambia lógica, solo alias.
    """
    return analyze_market(*args, **kwargs)


def check_pattern(candles_5s):
    candle_1m, micro = _build_strategy_inputs(candles_5s)

    if candle_1m is None or micro is None:
        return None

    return analyze_market(candle_1m, micro).get("signal")
