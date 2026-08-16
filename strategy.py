from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA 1M + 12 MICROVELAS DE 5 SEGUNDOS
# ============================================================
#
# OBJETIVO:
#
# Analizar cada vela de 1 minuto utilizando exactamente
# sus 12 velas de 5 segundos.
#
# La primera vela de 5s NO determina la dirección.
#
# La dirección se determina mediante:
#
#   1. DOMINANTE GLOBAL
#   2. CONTROL FINAL
#   3. COLOR FINAL DE LA M1
#
#
# ============================================================
# DOMINANTE GLOBAL
# ============================================================
#
# BUY_SCORE:
#
#   suma de todos los cuerpos alcistas de las 12 velas.
#
#   max(close - open, 0)
#
#
# SELL_SCORE:
#
#   suma de todos los cuerpos bajistas de las 12 velas.
#
#   max(open - close, 0)
#
#
# DOMINANCE:
#
#   abs(BUY_SCORE - SELL_SCORE)
#   ---------------------------
#       BUY_SCORE + SELL_SCORE
#
#
# Se requiere una dominancia mínima de 20%.
#
#
# ============================================================
# CONTROL FINAL
# ============================================================
#
# Se utilizan exclusivamente las últimas 3 microvelas:
#
#   #10
#   #11
#   #12
#
# BUY_FINAL:
#
#   suma(close - open) de #10,#11,#12 > 0
#
#
# SELL_FINAL:
#
#   suma(close - open) de #10,#11,#12 < 0
#
#
# Además:
#
# CALL:
#   cierre #12 > apertura M1
#
# PUT:
#   cierre #12 < apertura M1
#
#
# ============================================================
# CALL
# ============================================================
#
# 1. BUY_SCORE > SELL_SCORE
# 2. Dominance >= 20%
# 3. Movimiento neto de las últimas 3 velas > 0
# 4. Último cierre 5s > apertura M1
# 5. Cierre M1 > apertura M1
#
#
# ============================================================
# PUT
# ============================================================
#
# 1. SELL_SCORE > BUY_SCORE
# 2. Dominance >= 20%
# 3. Movimiento neto de las últimas 3 velas < 0
# 4. Último cierre 5s < apertura M1
# 5. Cierre M1 < apertura M1
#
#
# ============================================================
# SIN SEÑAL
# ============================================================
#
# Si el dominante global y el control final se contradicen,
# no se genera señal.
#
# ============================================================


# ============================================================
# CONFIGURACIÓN
# ============================================================

MICRO_CANDLES_REQUIRED = 12

FINAL_CONTROL_CANDLES = 3

DOMINANCE_THRESHOLD = 0.20


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    """
    Convierte un valor a float de forma segura.
    """

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# NORMALIZAR MICROVELAS
# ============================================================

def _normalize_5s(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza los datos de las velas de 5 segundos.

    Columnas obligatorias:

        open
        close

    Opcional:

        from
        high
        low

    Compatible con nombres utilizados por IQ Option.
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    # --------------------------------------------------------
    # IQ Option
    # --------------------------------------------------------

    if "max" in out.columns and "high" not in out.columns:
        rename["max"] = "high"

    if "min" in out.columns and "low" not in out.columns:
        rename["min"] = "low"

    # --------------------------------------------------------
    # Open
    # --------------------------------------------------------

    if "Open" in out.columns and "open" not in out.columns:
        rename["Open"] = "open"

    # --------------------------------------------------------
    # High
    # --------------------------------------------------------

    if "High" in out.columns and "high" not in out.columns:
        rename["High"] = "high"

    # --------------------------------------------------------
    # Low
    # --------------------------------------------------------

    if "Low" in out.columns and "low" not in out.columns:
        rename["Low"] = "low"

    # --------------------------------------------------------
    # Close
    # --------------------------------------------------------

    if "Close" in out.columns and "close" not in out.columns:
        rename["Close"] = "close"

    if rename:
        out.rename(
            columns=rename,
            inplace=True,
        )

    # --------------------------------------------------------
    # Columnas obligatorias
    # --------------------------------------------------------

    if "open" not in out.columns:
        return pd.DataFrame()

    if "close" not in out.columns:
        return pd.DataFrame()

    # --------------------------------------------------------
    # Conversión numérica
    # --------------------------------------------------------

    out["open"] = pd.to_numeric(
        out["open"],
        errors="coerce",
    )

    out["close"] = pd.to_numeric(
        out["close"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # High / Low
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # Eliminar datos inválidos
    # --------------------------------------------------------

    out.dropna(
        subset=[
            "open",
            "close",
        ],
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
    """
    Verifica que las velas sean consecutivas cada 5 segundos.

    Si existe timestamp:

        diferencia = 5

    para todas las velas consecutivas.
    """

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


# ============================================================
# OBTENER LAS 12 MICROVELAS DE LA M1
# ============================================================

def _get_minute_micro_candles(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> pd.DataFrame:
    """
    Obtiene exclusivamente las microvelas pertenecientes
    al minuto de candle_1m.
    """

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:
        return pd.DataFrame()

    minute_timestamp = None

    # --------------------------------------------------------
    # Obtener timestamp de la M1
    # --------------------------------------------------------

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
            ValueError,
        ):

            minute_timestamp = None

    # --------------------------------------------------------
    # Filtrar exactamente el minuto
    # --------------------------------------------------------

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = minute_timestamp

        end_time = (
            minute_timestamp + 60
        )

        micro = micro[
            (micro["from"] >= start_time)
            &
            (micro["from"] < end_time)
        ].copy()

        micro.sort_values(
            "from",
            inplace=True,
        )

        # Eliminar duplicados de timestamp.

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
# CALCULAR DOMINANTE GLOBAL
# ============================================================

def _calculate_global_dominance(
    micro: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Calcula el dominio global de las 12 microvelas.

    BUY_SCORE:
        suma de los cuerpos alcistas.

    SELL_SCORE:
        suma de los cuerpos bajistas.

    No utiliza mayoría de velas.
    """

    result: Dict[str, Any] = {

        "dominant": "neutral",

        "buy_score": 0.0,

        "sell_score": 0.0,

        "dominance_ratio": 0.0,

        "total_movement": 0.0,
    }

    if micro.empty:
        return result

    buy_score = 0.0
    sell_score = 0.0

    # --------------------------------------------------------
    # Las 12 velas
    # --------------------------------------------------------

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
            continue

        movement = (
            closing - opening
        )

        # ----------------------------------------------------
        # Compradores
        # ----------------------------------------------------

        if movement > 0:

            buy_score += movement

        # ----------------------------------------------------
        # Vendedores
        # ----------------------------------------------------

        elif movement < 0:

            sell_score += abs(
                movement
            )

    total_movement = (
        buy_score + sell_score
    )

    result["buy_score"] = buy_score

    result["sell_score"] = sell_score

    result["total_movement"] = (
        total_movement
    )

    # --------------------------------------------------------
    # Sin movimiento
    # --------------------------------------------------------

    if total_movement <= 0:

        return result

    # --------------------------------------------------------
    # Ratio de dominancia
    # --------------------------------------------------------

    dominance_ratio = (
        abs(
            buy_score - sell_score
        )
        / total_movement
    )

    result["dominance_ratio"] = (
        dominance_ratio
    )

    # --------------------------------------------------------
    # Comprador dominante
    # --------------------------------------------------------

    if (
        buy_score > sell_score
        and dominance_ratio
        >= DOMINANCE_THRESHOLD
    ):

        result["dominant"] = (
            "buyer"
        )

        return result

    # --------------------------------------------------------
    # Vendedor dominante
    # --------------------------------------------------------

    if (
        sell_score > buy_score
        and dominance_ratio
        >= DOMINANCE_THRESHOLD
    ):

        result["dominant"] = (
            "seller"
        )

        return result

    return result


# ============================================================
# CALCULAR CONTROL FINAL
# ============================================================

def _calculate_final_control(
    micro: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Determina quién controla el final de la M1.

    Se utilizan exactamente las últimas 3 velas:

        #10
        #11
        #12

    Se calcula:

        final_net =
            suma(close - open)

    Resultado:

        > 0  comprador
        < 0  vendedor
        = 0  neutral
    """

    result: Dict[str, Any] = {

        "final_control": "neutral",

        "final_net": 0.0,

        "final_buy_movement": 0.0,

        "final_sell_movement": 0.0,
    }

    if len(micro) < FINAL_CONTROL_CANDLES:
        return result

    final_micro = micro.iloc[
        -FINAL_CONTROL_CANDLES:
    ].copy()

    final_net = 0.0

    final_buy = 0.0

    final_sell = 0.0

    # --------------------------------------------------------
    # Últimas 3 velas
    # --------------------------------------------------------

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

    result[
        "final_buy_movement"
    ] = final_buy

    result[
        "final_sell_movement"
    ] = final_sell

    # --------------------------------------------------------
    # Comprador controla el final
    # --------------------------------------------------------

    if final_net > 0:

        result[
            "final_control"
        ] = "buyer"

        return result

    # --------------------------------------------------------
    # Vendedor controla el final
    # --------------------------------------------------------

    if final_net < 0:

        result[
            "final_control"
        ] = "seller"

        return result

    return result


# ============================================================
# ANALIZAR UNA M1
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Analiza una vela completa de 1 minuto.

    Requiere exactamente 12 velas de 5 segundos.
    """

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

        "final_control": None,

        "final_net": 0.0,

        "final_buy_movement": 0.0,

        "final_sell_movement": 0.0,

        "last_5s_close": None,
    }

    # ========================================================
    # VALIDAR M1
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

    # ========================================================
    # TIMESTAMP M1
    # ========================================================

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
            ValueError,
        ):

            result[
                "minute_timestamp"
            ] = None

    # ========================================================
    # OBTENER MICROVELAS
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

    # ========================================================
    # VALIDAR SECUENCIA
    # ========================================================

    if not _validate_5s_sequence(
        micro
    ):

        result["micro_candles_count"] = (
            len(micro)
        )

        result["reason"] = (
            "secuencia 5s inválida"
        )

        return result

    # ========================================================
    # EXACTAMENTE 12
    # ========================================================

    if len(micro) != MICRO_CANDLES_REQUIRED:

        result["micro_candles_count"] = (
            len(micro)
        )

        result["reason"] = (
            "M1 inválida: "
            f"se requieren "
            f"{MICRO_CANDLES_REQUIRED} "
            f"velas de 5s y se recibieron "
            f"{len(micro)}"
        )

        return result

    result["micro_candles_count"] = (
        len(micro)
    )

    # ========================================================
    # ÚLTIMO CIERRE 5S
    # ========================================================

    last_close = _to_float(
        micro.iloc[-1]["close"]
    )

    if last_close is None:

        result["reason"] = (
            "cierre de la vela 5s #12 inválido"
        )

        return result

    result["last_5s_close"] = last_close

    # ========================================================
    # DOMINANTE GLOBAL
    # ========================================================

    global_dominance = (
        _calculate_global_dominance(
            micro
        )
    )

    result["buy_score"] = (
        global_dominance[
            "buy_score"
        ]
    )

    result["sell_score"] = (
        global_dominance[
            "sell_score"
        ]
    )

    result["dominance_ratio"] = (
        global_dominance[
            "dominance_ratio"
        ]
    )

    result["dominant"] = (
        global_dominance[
            "dominant"
        ]
    )

    # ========================================================
    # CONTROL FINAL
    # ========================================================

    final_control = (
        _calculate_final_control(
            micro
        )
    )

    result["final_control"] = (
        final_control[
            "final_control"
        ]
    )

    result["final_net"] = (
        final_control[
            "final_net"
        ]
    )

    result[
        "final_buy_movement"
    ] = (
        final_control[
            "final_buy_movement"
        ]
    )

    result[
        "final_sell_movement"
    ] = (
        final_control[
            "final_sell_movement"
        ]
    )

    # ========================================================
    # COMPRADOR
    # ========================================================

    if global_dominance[
        "dominant"
    ] == "buyer":

        # ----------------------------------------------------
        # El control final también debe ser comprador
        # ----------------------------------------------------

        if final_control[
            "final_control"
        ] != "buyer":

            result["reason"] = (
                "CALL bloqueada: "
                "dominante global comprador "
                "pero control final vendedor "
                "o neutral"
            )

            return result

        # ----------------------------------------------------
        # Último cierre 5s sobre apertura M1
        # ----------------------------------------------------

        if last_close <= opening:

            result["reason"] = (
                "CALL bloqueada: "
                "cierre 5s #12 no está "
                "por encima de apertura M1"
            )

            return result

        # ----------------------------------------------------
        # M1 verde
        # ----------------------------------------------------

        if closing <= opening:

            result["reason"] = (
                "CALL bloqueada: "
                "M1 no terminó verde"
            )

            return result

        # ----------------------------------------------------
        # CALL CONFIRMADA
        # ----------------------------------------------------

        result["signal"] = "call"

        result["valid"] = True

        result["reason"] = (
            "CALL confirmada: "
            "dominante comprador + "
            "control final comprador + "
            "M1 verde"
        )

        return result

    # ========================================================
    # VENDEDOR
    # ========================================================

    if global_dominance[
        "dominant"
    ] == "seller":

        # ----------------------------------------------------
        # Control final vendedor
        # ----------------------------------------------------

        if final_control[
            "final_control"
        ] != "seller":

            result["reason"] = (
                "PUT bloqueada: "
                "dominante global vendedor "
                "pero control final comprador "
                "o neutral"
            )

            return result

        # ----------------------------------------------------
        # Último cierre 5s debajo apertura M1
        # ----------------------------------------------------

        if last_close >= opening:

            result["reason"] = (
                "PUT bloqueada: "
                "cierre 5s #12 no está "
                "por debajo de apertura M1"
            )

            return result

        # ----------------------------------------------------
        # M1 roja
        # ----------------------------------------------------

        if closing >= opening:

            result["reason"] = (
                "PUT bloqueada: "
                "M1 no terminó roja"
            )

            return result

        # ----------------------------------------------------
        # PUT CONFIRMADA
        # ----------------------------------------------------

        result["signal"] = "put"

        result["valid"] = True

        result["reason"] = (
            "PUT confirmada: "
            "dominante vendedor + "
            "control final vendedor + "
            "M1 roja"
        )

        return result

    # ========================================================
    # DOMINANTE NEUTRAL
    # ========================================================

    result["reason"] = (
        "sin señal: "
        "no existe dominante suficiente"
    )

    return result


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:

    return analyze_minute(
        candle_1m,
        candles_5s,
    )


# ============================================================
# API SIMPLE
# ============================================================

def get_signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Optional[str]:

    result = analyze_market(
        candle_1m,
        candles_5s,
    )

    return result.get(
        "signal"
    )


# ============================================================
# COMPATIBILIDAD
# ============================================================

def signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
    )


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    print(
        "strategy.py cargado correctamente."
    )

    print(
        "Estrategia: 1M + 12 microvelas de 5S"
    )

    print(
        "Dirección: dominante matemático."
    )

    print(
        "Control final: últimas 3 velas."
    )

    print(
        "Dominancia mínima: "
        f"{DOMINANCE_THRESHOLD:.0%}"
    )

    print(
        "CALL = comprador global + "
        "comprador final + M1 verde"
    )

    print(
        "PUT = vendedor global + "
        "vendedor final + M1 roja"
    )

    print(
        "Si existe contradicción: SIN SEÑAL."
    )
