from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# STRATEGY.PY
#
# ESTRATEGIA:
#
#   VELAS 1-6 = ESTRUCTURA
#   VELA 7    = N+1 / ENTRADA
#
# REGLA:
#
#   SOPORTE    -> CALL
#   RESISTENCIA -> PUT
#
# LA ENTRADA SE DETERMINA ÚNICAMENTE CON LA UBICACIÓN
# DE LA APERTURA DE LA VELA 7 RESPECTO A LA ESTRUCTURA
# FORMADA POR LAS 6 VELAS ANTERIORES.
# ============================================================


STRUCTURE_CANDLES_REQUIRED = 6
ENTRY_CANDLE_REQUIRED = 7

# Tolerancia máxima para considerar que la apertura N+1
# está suficientemente cerca de soporte/resistencia.
#
# Se calcula dinámicamente utilizando el rango de las
# primeras 6 velas.
#
# Ejemplo:
#
#   rango estructura = 0.00020
#   tolerancia       = 0.00004
#
# La apertura N+1 debe estar dentro de esa zona.
#
SUPPORT_RESISTANCE_TOLERANCE = 0.20


# ============================================================
# UTILIDADES
# ============================================================

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
        out.rename(
            columns=rename,
            inplace=True
        )

    required = [
        "open",
        "close",
    ]

    for column in required:
        if column not in out.columns:
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
# VALIDAR SECUENCIA
# ============================================================

def _validate_5s_sequence(
    candles: pd.DataFrame
) -> bool:

    if candles is None:
        return False

    if candles.empty:
        return False

    if "from" not in candles.columns:
        return False

    timestamps = (
        candles["from"]
        .astype(int)
        .tolist()
    )

    if len(timestamps) < 2:
        return True

    for i in range(1, len(timestamps)):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:
            return False

    return True


# ============================================================
# OBTENER RANGO DE UNA VELA
# ============================================================

def _candle_high(
    candle: pd.Series
) -> Optional[float]:

    if candle is None:
        return None

    high = _to_float(
        candle.get("high")
    )

    if high is not None:
        return high

    opening = _to_float(
        candle.get("open")
    )

    closing = _to_float(
        candle.get("close")
    )

    if opening is None or closing is None:
        return None

    return max(
        opening,
        closing
    )


def _candle_low(
    candle: pd.Series
) -> Optional[float]:

    if candle is None:
        return None

    low = _to_float(
        candle.get("low")
    )

    if low is not None:
        return low

    opening = _to_float(
        candle.get("open")
    )

    closing = _to_float(
        candle.get("close")
    )

    if opening is None or closing is None:
        return None

    return min(
        opening,
        closing
    )


# ============================================================
# ESTRUCTURA DE LAS PRIMERAS 6 VELAS
# ============================================================

def _calculate_structure(
    structure: pd.DataFrame
) -> Dict[str, Any]:

    result = {
        "support": None,
        "resistance": None,
        "structure_range": None,
        "tolerance": None,
        "structure_valid": False,
    }

    if structure is None:
        return result

    if len(structure) != STRUCTURE_CANDLES_REQUIRED:
        return result

    highs = []
    lows = []

    for _, candle in structure.iterrows():

        high = _candle_high(candle)
        low = _candle_low(candle)

        if high is None or low is None:
            return result

        highs.append(high)
        lows.append(low)

    if not highs or not lows:
        return result

    resistance = max(highs)
    support = min(lows)

    if resistance <= support:
        return result

    structure_range = (
        resistance
        - support
    )

    tolerance = (
        structure_range
        * SUPPORT_RESISTANCE_TOLERANCE
    )

    result["support"] = support
    result["resistance"] = resistance
    result["structure_range"] = structure_range
    result["tolerance"] = tolerance
    result["structure_valid"] = True

    return result


# ============================================================
# ANALIZAR UBICACIÓN DE LA APERTURA N+1
# ============================================================

def _analyze_entry_location(
    entry_open: float,
    support: float,
    resistance: float,
    tolerance: float,
) -> Dict[str, Any]:

    result = {
        "location": "neutral",
        "distance_support": None,
        "distance_resistance": None,
        "support_distance_ratio": None,
        "resistance_distance_ratio": None,
        "support_ok": False,
        "resistance_ok": False,
    }

    distance_support = abs(
        entry_open
        - support
    )

    distance_resistance = abs(
        resistance
        - entry_open
    )

    result["distance_support"] = (
        distance_support
    )

    result["distance_resistance"] = (
        distance_resistance
    )

    if tolerance <= 0:
        return result

    support_ratio = (
        distance_support
        / tolerance
    )

    resistance_ratio = (
        distance_resistance
        / tolerance
    )

    result["support_distance_ratio"] = (
        support_ratio
    )

    result["resistance_distance_ratio"] = (
        resistance_ratio
    )

    support_ok = (
        distance_support
        <= tolerance
    )

    resistance_ok = (
        distance_resistance
        <= tolerance
    )

    result["support_ok"] = support_ok
    result["resistance_ok"] = resistance_ok

    # ========================================================
    # PRIORIDAD
    #
    # Si por una estructura extremadamente pequeña el precio
    # queda simultáneamente cerca de ambos extremos,
    # no se fuerza una operación.
    # ========================================================

    if support_ok and resistance_ok:

        result["location"] = "neutral"

        return result

    if support_ok:

        result["location"] = "support"

        return result

    if resistance_ok:

        result["location"] = "resistance"

        return result

    result["location"] = "neutral"

    return result


# ============================================================
# ANALIZAR LAS 6 VELAS DE ESTRUCTURA
# ============================================================

def _analyze_structure_behavior(
    structure: pd.DataFrame
) -> Dict[str, Any]:

    result = {
        "green_count": 0,
        "red_count": 0,
        "doji_count": 0,
        "net_movement": 0.0,
        "total_body": 0.0,
        "structure_direction": "neutral",
    }

    if structure is None:
        return result

    if len(structure) != STRUCTURE_CANDLES_REQUIRED:
        return result

    first_open = _to_float(
        structure.iloc[0]["open"]
    )

    last_close = _to_float(
        structure.iloc[-1]["close"]
    )

    if first_open is None or last_close is None:
        return result

    total_body = 0.0

    green_count = 0
    red_count = 0
    doji_count = 0

    for _, candle in structure.iterrows():

        opening = _to_float(
            candle["open"]
        )

        closing = _to_float(
            candle["close"]
        )

        if opening is None or closing is None:
            return result

        movement = (
            closing
            - opening
        )

        total_body += abs(
            movement
        )

        if movement > 0:
            green_count += 1

        elif movement < 0:
            red_count += 1

        else:
            doji_count += 1

    net_movement = (
        last_close
        - first_open
    )

    result["green_count"] = green_count
    result["red_count"] = red_count
    result["doji_count"] = doji_count
    result["net_movement"] = net_movement
    result["total_body"] = total_body

    if net_movement > 0:
        result["structure_direction"] = "call"

    elif net_movement < 0:
        result["structure_direction"] = "put"

    return result


# ============================================================
# ANALISIS PRINCIPAL
# ============================================================

def analyze_n_plus_1(
    candles_5s: Any
) -> Dict[str, Any]:

    result: Dict[str, Any] = {

        "signal": None,

        "valid": False,

        "reason": "sin señal",

        "candles_received": 0,

        "structure_candles": STRUCTURE_CANDLES_REQUIRED,

        "entry_candle": ENTRY_CANDLE_REQUIRED,

        "support": None,

        "resistance": None,

        "structure_range": None,

        "tolerance": None,

        "entry_open": None,

        "location": "neutral",

        "distance_support": None,

        "distance_resistance": None,

        "support_distance_ratio": None,

        "resistance_distance_ratio": None,

        "support_ok": False,

        "resistance_ok": False,

        "green_count": 0,

        "red_count": 0,

        "doji_count": 0,

        "net_movement": 0.0,

        "total_body": 0.0,

        "structure_direction": "neutral",

        "quality_checks": {

            "seven_candles": False,

            "sequence_ok": False,

            "structure_ok": False,

            "support_ok": False,

            "resistance_ok": False,

        },
    }

    # ========================================================
    # CONVERTIR DATOS
    # ========================================================

    if candles_5s is None:

        result["reason"] = (
            "no se recibieron velas 5S"
        )

        return result

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

            result["reason"] = (
                "datos 5S inválidos"
            )

            return result

    df = _normalize_5s(df)

    if df.empty:

        result["reason"] = (
            "DataFrame 5S vacío"
        )

        return result

    df.sort_values(
        "from",
        inplace=True
    )

    df.drop_duplicates(
        subset=["from"],
        keep="last",
        inplace=True
    )

    df.reset_index(
        drop=True,
        inplace=True
    )

    result["candles_received"] = len(df)

    # ========================================================
    # NECESITAMOS EXACTAMENTE 7 VELAS
    #
    # 1-6 = estructura
    # 7   = entrada
    # ========================================================

    if len(df) != ENTRY_CANDLE_REQUIRED:

        result["reason"] = (
            "se requieren exactamente "
            "7 velas de 5S: "
            "6 de estructura + 1 de entrada"
        )

        return result

    result["quality_checks"][
        "seven_candles"
    ] = True

    # ========================================================
    # VALIDAR SECUENCIA
    # ========================================================

    if not _validate_5s_sequence(df):

        result["reason"] = (
            "secuencia 5S inválida"
        )

        return result

    result["quality_checks"][
        "sequence_ok"
    ] = True

    # ========================================================
    # SEPARAR ESTRUCTURA Y ENTRADA
    # ========================================================

    structure = df.iloc[
        :STRUCTURE_CANDLES_REQUIRED
    ].copy()

    entry_candle = df.iloc[
        ENTRY_CANDLE_REQUIRED - 1
    ]

    # ========================================================
    # CALCULAR SOPORTE / RESISTENCIA
    # ========================================================

    structure_data = _calculate_structure(
        structure
    )

    if not structure_data[
        "structure_valid"
    ]:

        result["reason"] = (
            "estructura de 6 velas inválida"
        )

        return result

    result["quality_checks"][
        "structure_ok"
    ] = True

    support = structure_data[
        "support"
    ]

    resistance = structure_data[
        "resistance"
    ]

    structure_range = structure_data[
        "structure_range"
    ]

    tolerance = structure_data[
        "tolerance"
    ]

    result["support"] = support
    result["resistance"] = resistance
    result["structure_range"] = (
        structure_range
    )
    result["tolerance"] = tolerance

    # ========================================================
    # APERTURA DE LA VELA 7
    # ========================================================

    entry_open = _to_float(
        entry_candle["open"]
    )

    if entry_open is None:

        result["reason"] = (
            "apertura de vela 7 inválida"
        )

        return result

    result["entry_open"] = entry_open

    # ========================================================
    # ANALIZAR ESTRUCTURA
    # ========================================================

    behavior = (
        _analyze_structure_behavior(
            structure
        )
    )

    result["green_count"] = (
        behavior["green_count"]
    )

    result["red_count"] = (
        behavior["red_count"]
    )

    result["doji_count"] = (
        behavior["doji_count"]
    )

    result["net_movement"] = (
        behavior["net_movement"]
    )

    result["total_body"] = (
        behavior["total_body"]
    )

    result["structure_direction"] = (
        behavior["structure_direction"]
    )

    # ========================================================
    # UBICACIÓN N+1
    # ========================================================

    location = _analyze_entry_location(
        entry_open,
        support,
        resistance,
        tolerance,
    )

    result["location"] = (
        location["location"]
    )

    result["distance_support"] = (
        location["distance_support"]
    )

    result["distance_resistance"] = (
        location["distance_resistance"]
    )

    result["support_distance_ratio"] = (
        location["support_distance_ratio"]
    )

    result["resistance_distance_ratio"] = (
        location["resistance_distance_ratio"]
    )

    result["support_ok"] = (
        location["support_ok"]
    )

    result["resistance_ok"] = (
        location["resistance_ok"]
    )

    result["quality_checks"][
        "support_ok"
    ] = location["support_ok"]

    result["quality_checks"][
        "resistance_ok"
    ] = location["resistance_ok"]

    # ========================================================
    # REGLA PRINCIPAL
    #
    # SOPORTE     -> CALL
    # RESISTENCIA -> PUT
    # ========================================================

    if location["location"] == "support":

        result["signal"] = "call"

        result["valid"] = True

        result["reason"] = (
            "CALL N+1: apertura de vela 7 "
            "en zona de SOPORTE de la estructura "
            "formada por las primeras 6 velas"
        )

        return result

    if location["location"] == "resistance":

        result["signal"] = "put"

        result["valid"] = True

        result["reason"] = (
            "PUT N+1: apertura de vela 7 "
            "en zona de RESISTENCIA de la estructura "
            "formada por las primeras 6 velas"
        )

        return result

    result["reason"] = (
        "SIN OPERACIÓN: apertura de vela 7 "
        "no está suficientemente cerca "
        "de soporte ni resistencia"
    )

    return result


# ============================================================
# COMPATIBILIDAD CON BOT.PY
# ============================================================

def check_pattern(
    candles_5s: Any
) -> Optional[str]:

    result = analyze_n_plus_1(
        candles_5s
    )

    return result.get(
        "signal"
    )


def get_signal(
    candles_5s: Any
) -> Optional[str]:

    return check_pattern(
        candles_5s
    )


def signal(
    candles_5s: Any
) -> Optional[str]:

    return check_pattern(
        candles_5s
    )


# ============================================================
# DIRECCIÓN M1
#
# Se mantiene para compatibilidad.
#
# IMPORTANTE:
# Esta función NO decide la entrada N+1.
# La entrada real utiliza soporte/resistencia.
# ============================================================

def get_m1_direction(
    candles_5s: Any
) -> Optional[str]:

    if candles_5s is None:
        return None

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

            return None

    df = _normalize_5s(df)

    if df.empty:
        return None

    if len(df) < 2:
        return None

    opening = _to_float(
        df.iloc[0]["open"]
    )

    closing = _to_float(
        df.iloc[-1]["close"]
    )

    if opening is None or closing is None:
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

    if candles_5s is None:
        return None

    return analyze_n_plus_1(
        candles_5s
    )


def analyze_market(
    candle_1m: Any,
    candles_5s: Any,
    previous_m1: Optional[
        pd.DataFrame
    ] = None,
) -> Dict[str, Any]:

    # --------------------------------------------------------
    # Compatibilidad con versiones anteriores de bot.py.
    #
    # La nueva estrategia NO utiliza previous_m1.
    # La decisión se basa únicamente en:
    #
    #   6 velas de estructura
    #   +
    #   apertura de vela 7
    # --------------------------------------------------------

    return analyze_n_plus_1(
        candles_5s
    )


def analyze_minute(
    candle_1m: Any,
    candles_5s: Any,
    previous_m1: Optional[
        pd.DataFrame
    ] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )


# ============================================================
# INFORMACIÓN DE LA ESTRATEGIA
# ============================================================

def strategy_info() -> Dict[str, Any]:

    return {

        "structure_candles":
            STRUCTURE_CANDLES_REQUIRED,

        "entry_candle":
            ENTRY_CANDLE_REQUIRED,

        "entry_mode":
            "N+1",

        "support_signal":
            "call",

        "resistance_signal":
            "put",

        "tolerance":
            SUPPORT_RESISTANCE_TOLERANCE,

        "description":
            (
                "Las primeras 6 velas construyen "
                "la estructura. La apertura de la "
                "vela 7 determina si el precio está "
                "en soporte o resistencia. "
                "Soporte = CALL. "
                "Resistencia = PUT."
            ),
    }


# ============================================================
# PRUEBA DIRECTA
# ============================================================

if __name__ == "__main__":

    print(
        "=========================================="
    )

    print(
        "STRATEGY.PY CARGADO CORRECTAMENTE"
    )

    print(
        "=========================================="
    )

    print(
        "Estructura : "
        f"{STRUCTURE_CANDLES_REQUIRED} velas de 5S"
    )

    print(
        "Entrada     : "
        f"vela {ENTRY_CANDLE_REQUIRED} / N+1"
    )

    print(
        "Soporte     : CALL"
    )

    print(
        "Resistencia : PUT"
    )

    print(
        "Tolerancia  : "
        f"{SUPPORT_RESISTANCE_TOLERANCE:.0%}"
    )

    print(
        "=========================================="
    )
