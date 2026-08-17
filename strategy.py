from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# STRATEGY.PY
#
# ESTRATEGIA:
#
# SOPORTE M5 / RESISTENCIA M5
# + 6 VELAS DE 5 SEGUNDOS
# + ENTRADA N+1
#
# REGLAS:
#
# 1. La primera vela del bloque toca o rompe SOPORTE M5
#    -> CALL
#
# 2. La primera vela del bloque toca o rompe RESISTENCIA M5
#    -> PUT
#
# 3. Se esperan exactamente 6 velas cerradas.
#
# 4. NO importa cómo termine la sexta vela.
#
# 5. La sexta vela solamente confirma que terminó el periodo
#    de espera.
#
# 6. La entrada corresponde a N+1.
#
# NO SE UTILIZA:
# - 12 velas 5S
# - M1
# - dominancia
# - eficiencia
# - pesos
# - mayoría
# - color obligatorio
# - patrón obligatorio de la sexta vela
# ============================================================


MICRO_CANDLES_REQUIRED = 6


# ============================================================
# CONVERSIÓN NUMÉRICA
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

        result = float(value)

        if pd.isna(result):
            return None

        return result

    except (TypeError, ValueError):
        return None


# ============================================================
# NORMALIZAR VELAS 5S
# ============================================================

def _normalize_5s(
    candles_5s: Any,
) -> pd.DataFrame:

    if candles_5s is None:
        return pd.DataFrame()

    try:
        if isinstance(
            candles_5s,
            pd.DataFrame,
        ):
            df = candles_5s.copy()

        else:
            df = pd.DataFrame(
                list(candles_5s)
            )

    except Exception:
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    rename = {}

    if "max" in df.columns:
        if "high" not in df.columns:
            rename["max"] = "high"

    if "min" in df.columns:
        if "low" not in df.columns:
            rename["min"] = "low"

    if "Open" in df.columns:
        if "open" not in df.columns:
            rename["Open"] = "open"

    if "High" in df.columns:
        if "high" not in df.columns:
            rename["High"] = "high"

    if "Low" in df.columns:
        if "low" not in df.columns:
            rename["Low"] = "low"

    if "Close" in df.columns:
        if "close" not in df.columns:
            rename["Close"] = "close"

    if rename:
        df.rename(
            columns=rename,
            inplace=True,
        )

    required = (
        "open",
        "close",
    )

    for column in required:
        if column not in df.columns:
            return pd.DataFrame()

    df["open"] = pd.to_numeric(
        df["open"],
        errors="coerce",
    )

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce",
    )

    if "high" in df.columns:
        df["high"] = pd.to_numeric(
            df["high"],
            errors="coerce",
        )

    if "low" in df.columns:
        df["low"] = pd.to_numeric(
            df["low"],
            errors="coerce",
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

        df["from"] = df["from"].astype(int)

        df.sort_values(
            "from",
            inplace=True,
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

    df.dropna(
        subset=[
            "open",
            "close",
        ],
        inplace=True,
    )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# VALIDAR SECUENCIA DE 5 SEGUNDOS
# ============================================================

def _validate_sequence(
    candles: pd.DataFrame,
) -> bool:

    if candles.empty:
        return False

    if "from" not in candles.columns:
        return True

    if len(candles) < 2:
        return False

    timestamps = (
        candles["from"]
        .astype(int)
        .tolist()
    )

    for i in range(
        1,
        len(timestamps),
    ):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:
            return False

    return True


# ============================================================
# OBTENER OHLC DE UNA VELA
# ============================================================

def _get_ohlc(
    candle: pd.Series,
) -> Optional[Dict[str, float]]:

    if candle is None:
        return None

    opening = _to_float(
        candle.get("open")
    )

    closing = _to_float(
        candle.get("close")
    )

    high = _to_float(
        candle.get("high")
    )

    low = _to_float(
        candle.get("low")
    )

    if opening is None:
        return None

    if closing is None:
        return None

    # Si API no proporciona high/low,
    # se construyen con open/close.
    if high is None:
        high = max(
            opening,
            closing,
        )

    if low is None:
        low = min(
            opening,
            closing,
        )

    return {
        "open": opening,
        "close": closing,
        "high": high,
        "low": low,
    }


# ============================================================
# DETECTAR TOQUE / RUPTURA SOPORTE
# ============================================================

def _touches_support(
    candle: pd.Series,
    support: float,
) -> bool:

    data = _get_ohlc(
        candle
    )

    if data is None:
        return False

    low = data["low"]
    high = data["high"]

    # La vela toca o atraviesa el soporte.
    #
    # Si el mínimo llega al nivel:
    #    low <= support
    #
    # Si atraviesa el soporte:
    #    low < support
    #
    # Ambas situaciones quedan cubiertas.
    if low <= support:
        return True

    # Protección adicional por si la vela
    # contiene completamente el nivel.
    if low <= support <= high:
        return True

    return False


# ============================================================
# DETECTAR TOQUE / RUPTURA RESISTENCIA
# ============================================================

def _touches_resistance(
    candle: pd.Series,
    resistance: float,
) -> bool:

    data = _get_ohlc(
        candle
    )

    if data is None:
        return False

    high = data["high"]
    low = data["low"]

    # La vela toca o atraviesa la resistencia.
    #
    # Si el máximo llega al nivel:
    #    high >= resistance
    #
    # Si atraviesa la resistencia:
    #    high > resistance
    #
    # Ambas situaciones quedan cubiertas.
    if high >= resistance:
        return True

    # Protección adicional por si la vela
    # contiene completamente el nivel.
    if low <= resistance <= high:
        return True

    return False


# ============================================================
# COLOR DE VELA
# ============================================================

def get_candle_color(
    candle: Any,
) -> str:

    if isinstance(
        candle,
        pd.Series,
    ):

        opening = _to_float(
            candle.get("open")
        )

        closing = _to_float(
            candle.get("close")
        )

    elif isinstance(
        candle,
        dict,
    ):

        opening = _to_float(
            candle.get("open")
        )

        closing = _to_float(
            candle.get("close")
        )

    else:
        return "doji"

    if opening is None or closing is None:
        return "doji"

    if closing > opening:
        return "verde"

    if closing < opening:
        return "rojo"

    return "doji"


# ============================================================
# ANALIZAR SEXTA VELA
#
# IMPORTANTE:
#
# NO SE UTILIZA SU COLOR PARA DECIDIR.
#
# Esta función solamente describe cómo terminó.
# ============================================================

def _analyze_final_candle(
    candle: pd.Series,
) -> Dict[str, Any]:

    data = _get_ohlc(
        candle
    )

    result = {
        "color": "doji",
        "open": None,
        "close": None,
        "high": None,
        "low": None,
        "body": 0.0,
        "range": 0.0,
        "body_ratio": 0.0,
        "classification": "indecision",
    }

    if data is None:
        return result

    opening = data["open"]
    closing = data["close"]
    high = data["high"]
    low = data["low"]

    body = abs(
        closing - opening
    )

    candle_range = (
        high - low
    )

    if candle_range > 0:
        body_ratio = (
            body / candle_range
        )

    else:
        body_ratio = 0.0

    result["color"] = (
        get_candle_color(
            candle
        )
    )

    result["open"] = opening
    result["close"] = closing
    result["high"] = high
    result["low"] = low
    result["body"] = body
    result["range"] = candle_range
    result["body_ratio"] = body_ratio

    # Esta clasificación NO bloquea la operación.
    if candle_range <= 0:
        classification = "doji"

    elif body_ratio <= 0.20:
        classification = "indecision"

    elif body_ratio >= 0.70:
        classification = "fuerza"

    elif body_ratio >= 0.45:
        classification = "continuidad"

    else:
        classification = "agotamiento"

    result["classification"] = (
        classification
    )

    return result


# ============================================================
# ANALIZAR SNIPER
# ============================================================

def analyze_sniper(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "reason": "sin señal",

        "support": None,
        "resistance": None,

        "candles_count": 0,

        "trigger": None,
        "trigger_type": None,

        "final_candle": None,
        "final_candle_color": None,
        "final_candle_classification": None,

        "ready_for_n1": False,
    }

    # --------------------------------------------------------
    # NORMALIZAR NIVELES
    # --------------------------------------------------------

    support_value = _to_float(
        support
    )

    resistance_value = _to_float(
        resistance
    )

    result["support"] = (
        support_value
    )

    result["resistance"] = (
        resistance_value
    )

    if (
        support_value is None
        and resistance_value is None
    ):
        result["reason"] = (
            "faltan soporte y resistencia M5"
        )
        return result

    # --------------------------------------------------------
    # NORMALIZAR VELAS
    # --------------------------------------------------------

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:
        result["reason"] = (
            "no hay velas 5S"
        )
        return result

    result["candles_count"] = len(
        micro
    )

    # --------------------------------------------------------
    # EXACTAMENTE 6 VELAS
    # --------------------------------------------------------

    if len(micro) != MICRO_CANDLES_REQUIRED:
        result["reason"] = (
            "se requieren exactamente "
            f"{MICRO_CANDLES_REQUIRED} "
            "velas 5S cerradas"
        )
        return result

    # --------------------------------------------------------
    # VALIDAR SECUENCIA
    # --------------------------------------------------------

    if not _validate_sequence(
        micro
    ):
        result["reason"] = (
            "secuencia 5S inválida"
        )
        return result

    # --------------------------------------------------------
    # PRIMERA VELA DEL BLOQUE
    #
    # Esta es la vela que toca/rompe
    # soporte o resistencia.
    # --------------------------------------------------------

    trigger_candle = micro.iloc[0]

    support_touch = False
    resistance_touch = False

    if support_value is not None:
        support_touch = (
            _touches_support(
                trigger_candle,
                support_value,
            )
        )

    if resistance_value is not None:
        resistance_touch = (
            _touches_resistance(
                trigger_candle,
                resistance_value,
            )
        )

    # --------------------------------------------------------
    # EVITAR AMBIGÜEDAD
    # --------------------------------------------------------

    if (
        support_touch
        and resistance_touch
    ):
        result["reason"] = (
            "la misma vela toca soporte "
            "y resistencia M5"
        )
        return result

    # --------------------------------------------------------
    # NO HUBO TOQUE
    # --------------------------------------------------------

    if not support_touch and not resistance_touch:
        result["reason"] = (
            "la primera vela no tocó "
            "soporte ni resistencia M5"
        )
        return result

    # --------------------------------------------------------
    # SEXTA VELA
    #
    # SU FORMA NO BLOQUEA.
    # --------------------------------------------------------

    final_candle = micro.iloc[-1]

    final_analysis = (
        _analyze_final_candle(
            final_candle
        )
    )

    result["final_candle"] = (
        final_analysis
    )

    result["final_candle_color"] = (
        final_analysis["color"]
    )

    result[
        "final_candle_classification"
    ] = final_analysis[
        "classification"
    ]

    # --------------------------------------------------------
    # SOPORTE -> CALL
    # --------------------------------------------------------

    if support_touch:

        result["trigger"] = "support"
        result["trigger_type"] = (
            "touch_or_break"
        )

        result["signal"] = "call"
        result["valid"] = True
        result["ready_for_n1"] = True

        result["reason"] = (
            "soporte M5 tocado o roto + "
            "6 velas cerradas + "
            "sexta vela confirmada; "
            "su forma no bloquea CALL"
        )

        return result

    # --------------------------------------------------------
    # RESISTENCIA -> PUT
    # --------------------------------------------------------

    if resistance_touch:

        result["trigger"] = "resistance"
        result["trigger_type"] = (
            "touch_or_break"
        )

        result["signal"] = "put"
        result["valid"] = True
        result["ready_for_n1"] = True

        result["reason"] = (
            "resistencia M5 tocada o rota + "
            "6 velas cerradas + "
            "sexta vela confirmada; "
            "su forma no bloquea PUT"
        )

        return result

    result["reason"] = (
        "sin señal"
    )

    return result


# ============================================================
# FUNCIÓN PRINCIPAL DE SEÑAL
# ============================================================

def get_signal(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Optional[str]:

    analysis = analyze_sniper(
        candles_5s,
        support,
        resistance,
    )

    if not analysis.get(
        "valid",
        False,
    ):
        return None

    signal_value = analysis.get(
        "signal"
    )

    if signal_value in (
        "call",
        "put",
    ):
        return signal_value

    return None


# ============================================================
# COMPATIBILIDAD check_pattern
# ============================================================

def check_pattern(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Optional[str]:

    return get_signal(
        candles_5s,
        support,
        resistance,
    )


# ============================================================
# COMPATIBILIDAD signal()
# ============================================================

def signal(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Optional[str]:

    return get_signal(
        candles_5s,
        support,
        resistance,
    )


# ============================================================
# COMPATIBILIDAD get_m1_direction
#
# Se mantiene para que bot.py no falle al importar.
#
# Ya NO se utiliza M1 para determinar la señal.
# ============================================================

def get_m1_direction(
    candles_5s: Any,
) -> Optional[str]:

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:
        return None

    if len(micro) < 1:
        return None

    first = _get_ohlc(
        micro.iloc[0]
    )

    last = _get_ohlc(
        micro.iloc[-1]
    )

    if first is None or last is None:
        return None

    if last["close"] > first["open"]:
        return "call"

    if last["close"] < first["open"]:
        return "put"

    return None


# ============================================================
# ANÁLISIS COMPLETO
# ============================================================

def get_strategy_analysis(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Optional[Dict[str, Any]]:

    return analyze_sniper(
        candles_5s,
        support,
        resistance,
    )


# ============================================================
# analyze_market
# ============================================================

def analyze_market(
    candles_5s: Any,
    support: Any = None,
    resistance: Any = None,
) -> Dict[str, Any]:

    return analyze_sniper(
        candles_5s,
        support,
        resistance,
    )


# ============================================================
# UTILIDAD:
# OBTENER SOPORTE M5
#
# Recibe una vela M5 y devuelve su mínimo.
# ============================================================

def get_m5_support(
    candle_m5: Any,
) -> Optional[float]:

    if candle_m5 is None:
        return None

    if isinstance(
        candle_m5,
        pd.Series,
    ):

        return _to_float(
            candle_m5.get("low")
        )

    if isinstance(
        candle_m5,
        dict,
    ):

        value = candle_m5.get(
            "low"
        )

        if value is None:
            value = candle_m5.get(
                "min"
            )

        return _to_float(
            value
        )

    return None


# ============================================================
# UTILIDAD:
# OBTENER RESISTENCIA M5
#
# Recibe una vela M5 y devuelve su máximo.
# ============================================================

def get_m5_resistance(
    candle_m5: Any,
) -> Optional[float]:

    if candle_m5 is None:
        return None

    if isinstance(
        candle_m5,
        pd.Series,
    ):

        return _to_float(
            candle_m5.get("high")
        )

    if isinstance(
        candle_m5,
        dict,
    ):

        value = candle_m5.get(
            "high"
        )

        if value is None:
            value = candle_m5.get(
                "max"
            )

        return _to_float(
            value
        )

    return None


# ============================================================
# INFORMACIÓN DE LA ESTRATEGIA
# ============================================================

def strategy_info() -> Dict[str, Any]:

    return {
        "micro_candles_required": (
            MICRO_CANDLES_REQUIRED
        ),

        "uses_m1": False,

        "uses_12_candles": False,

        "uses_weights": False,

        "uses_dominance": False,

        "uses_efficiency": False,

        "support_action": "call",

        "resistance_action": "put",

        "final_candle_color_required": False,

        "final_candle_pattern_required": False,

        "entry": "N+1",
    }


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    print(
        "======================================"
    )

    print(
        "STRATEGY.PY CARGADO"
    )

    print(
        "======================================"
    )

    print(
        "Modo: SNIPER M5"
    )

    print(
        "Velas requeridas: "
        f"{MICRO_CANDLES_REQUIRED} x 5S"
    )

    print(
        "Soporte M5 -> CALL"
    )

    print(
        "Resistencia M5 -> PUT"
    )

    print(
        "Sexta vela: cualquier cierre"
    )

    print(
        "Entrada: N+1"
    )

    print(
        "M1: NO UTILIZADO"
    )

    print(
        "12 velas 5S: NO UTILIZADAS"
    )

    print(
        "======================================"
    )
