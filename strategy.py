from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA 1M + MICROVELAS 5S
# ============================================================
#
# LÓGICA ORIGINAL:
#
# CALL:
# 1. Primera 5S cierra por encima de apertura 1M.
# 2. Alguna 5S posterior cierra por debajo de apertura 1M.
# 3. 1M termina verde.
#
# PUT:
# 1. Primera 5S cierra por debajo de apertura 1M.
# 2. Alguna 5S posterior cierra por encima de apertura 1M.
# 3. 1M termina roja.
#
# NUEVO ÚNICO FILTRO:
#
# Después de cumplirse la lógica original:
#
# CALL:
#     Los compradores deben confirmar continuidad.
#
# PUT:
#     Los vendedores deben confirmar continuidad.
#
# Si la dominancia NO confirma:
#
#     signal = None
#
# IMPORTANTE:
#
# NO se utilizan:
# - EMA
# - RSI
# - ATR
# - Volumen
# - Score
# - Martingala
# - Soporte/resistencia
# - Indicadores externos
#
# Tampoco se cambia la dirección determinada por la
# estrategia original.
# ============================================================


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
# NORMALIZACIÓN DE MICROVELAS 5S
# ============================================================

def _normalize_5s(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza las microvelas de 5 segundos.

    Obligatorio:
        open
        close

    Opcional:
        from
        high
        low
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(
        df,
        pd.DataFrame,
    ):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    # --------------------------------------------------------
    # Compatibilidad IQ Option
    # --------------------------------------------------------

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
# FILTRO DE DOMINANCIA
# ============================================================

def _confirm_buyer_continuity(
    micro: pd.DataFrame,
    opening: float,
    pullback_indexes: list[int],
) -> bool:
    """
    Confirma continuidad compradora después del retroceso.

    NO utiliza mayoría de velas.

    Busca la estructura:

        retroceso
             ↓
        recuperación
             ↓
        continuación
             ↓
        cierre manteniendo dominio comprador

    Condiciones:

    1. Debe existir una vela posterior al retroceso.

    2. El precio debe recuperar la apertura 1M o mantenerse
       por encima de ella al final.

    3. Debe existir una continuación alcista real:
       un cierre posterior superior al cierre anterior.

    4. Las últimas velas no pueden terminar mostrando una
       pérdida clara del dominio comprador.

    Esta función solamente confirma continuidad.
    No genera la señal.
    """

    if micro.empty:
        return False

    if not pullback_indexes:
        return False

    # --------------------------------------------------------
    # Último retroceso comprador
    # --------------------------------------------------------

    last_pullback = max(
        pullback_indexes
    )

    recovery = micro.iloc[
        last_pullback + 1:
    ].copy()

    if recovery.empty:
        return False

    # --------------------------------------------------------
    # Debe existir recuperación posterior
    # --------------------------------------------------------

    if len(recovery) < 2:
        return False

    closes = [
        _to_float(value)
        for value in recovery["close"]
    ]

    closes = [
        value
        for value in closes
        if value is not None
    ]

    if len(closes) < 2:
        return False

    # --------------------------------------------------------
    # El cierre final debe estar por encima de la apertura
    # 1M.
    #
    # Esto evita aceptar una simple reacción que no consiguió
    # recuperar el nivel.
    # --------------------------------------------------------

    final_close = closes[-1]

    if final_close <= opening:
        return False

    # --------------------------------------------------------
    # CONTINUIDAD COMPRADORA
    #
    # No contamos mayoría.
    #
    # Buscamos una secuencia donde después del retroceso
    # exista por lo menos una continuación de precio:
    #
    # cierre actual > cierre anterior
    # --------------------------------------------------------

    continuation = False

    for index in range(
        1,
        len(closes),
    ):

        previous_close = closes[
            index - 1
        ]

        current_close = closes[
            index
        ]

        if current_close > previous_close:

            continuation = True

            break

    if not continuation:
        return False

    # --------------------------------------------------------
    # Las dos últimas velas no pueden estar ambas perdiendo
    # el nivel de apertura.
    # --------------------------------------------------------

    last_closes = closes[-2:]

    if all(
        close < opening
        for close in last_closes
    ):
        return False

    return True


def _confirm_seller_continuity(
    micro: pd.DataFrame,
    opening: float,
    pullback_indexes: list[int],
) -> bool:
    """
    Confirma continuidad vendedora después del retroceso.

    Es la versión simétrica del filtro comprador.

    NO utiliza mayoría de velas.

    Busca:

        retroceso
             ↓
        recuperación bajista
             ↓
        continuación
             ↓
        cierre manteniendo dominio vendedor
    """

    if micro.empty:
        return False

    if not pullback_indexes:
        return False

    # --------------------------------------------------------
    # Último retroceso vendedor
    # --------------------------------------------------------

    last_pullback = max(
        pullback_indexes
    )

    recovery = micro.iloc[
        last_pullback + 1:
    ].copy()

    if recovery.empty:
        return False

    # --------------------------------------------------------
    # Debe existir recuperación posterior
    # --------------------------------------------------------

    if len(recovery) < 2:
        return False

    closes = [
        _to_float(value)
        for value in recovery["close"]
    ]

    closes = [
        value
        for value in closes
        if value is not None
    ]

    if len(closes) < 2:
        return False

    # --------------------------------------------------------
    # El cierre final debe estar por debajo de la apertura
    # 1M.
    # --------------------------------------------------------

    final_close = closes[-1]

    if final_close >= opening:
        return False

    # --------------------------------------------------------
    # CONTINUIDAD VENDEDORA
    #
    # No contamos mayoría.
    #
    # Buscamos al menos una continuación:
    #
    # cierre actual < cierre anterior
    # --------------------------------------------------------

    continuation = False

    for index in range(
        1,
        len(closes),
    ):

        previous_close = closes[
            index - 1
        ]

        current_close = closes[
            index
        ]

        if current_close < previous_close:

            continuation = True

            break

    if not continuation:
        return False

    # --------------------------------------------------------
    # Las dos últimas velas no pueden estar ambas por encima
    # de la apertura.
    # --------------------------------------------------------

    last_closes = closes[-2:]

    if all(
        close > opening
        for close in last_closes
    ):
        return False

    return True


# ============================================================
# ANALIZAR UNA VELA DE 1 MINUTO
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Analiza una vela 1M cerrada utilizando sus microvelas 5S.

    La lógica original se mantiene.

    Se añade únicamente la confirmación final de dominancia.
    """

    result: Dict[str, Any] = {

        "signal": None,

        "valid": False,

        "reason": "sin señal",

        "minute_timestamp": None,

        "minute_open": None,

        "minute_close": None,

        "first_5s_open": None,

        "first_5s_close": None,

        "pullback_count": 0,

        # ----------------------------------------------------
        # Información adicional del filtro
        # ----------------------------------------------------

        "dominance_confirmed": False,

        "dominance": None,

    }

    # ========================================================
    # VALIDAR VELA 1M
    # ========================================================

    if candle_1m is None:

        result["reason"] = (
            "vela de 1 minuto no disponible"
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
            "apertura de vela 1M inválida"
        )

        return result

    if closing is None:

        result["reason"] = (
            "cierre de vela 1M inválido"
        )

        return result

    result["minute_open"] = opening

    result["minute_close"] = closing

    # ========================================================
    # TIMESTAMP
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
    # NORMALIZAR 5S
    # ========================================================

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:

        result["reason"] = (
            "no hay microvelas de 5 segundos"
        )

        return result

    # ========================================================
    # FILTRAR MICROVELAS DEL MISMO MINUTO
    # ========================================================

    minute_timestamp = result[
        "minute_timestamp"
    ]

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = (
            minute_timestamp
        )

        end_time = (
            minute_timestamp + 60
        )

        micro = micro[
            (micro["from"] >= start_time)
            &
            (micro["from"] < end_time)
        ].copy()

        micro.reset_index(
            drop=True,
            inplace=True,
        )

    # ========================================================
    # MÍNIMO DE MICROVELAS
    # ========================================================

    if len(micro) < 2:

        result["reason"] = (
            "faltan microvelas 5S del minuto"
        )

        return result

    # ========================================================
    # PRIMERA 5S
    # ========================================================

    first_5s = micro.iloc[0]

    first_5s_open = _to_float(
        first_5s["open"]
    )

    first_5s_close = _to_float(
        first_5s["close"]
    )

    if first_5s_open is None:

        result["reason"] = (
            "apertura de primera 5S inválida"
        )

        return result

    if first_5s_close is None:

        result["reason"] = (
            "cierre de primera 5S inválido"
        )

        return result

    result[
        "first_5s_open"
    ] = first_5s_open

    result[
        "first_5s_close"
    ] = first_5s_close

    # ========================================================
    # CALL
    # ========================================================

    if first_5s_close > opening:

        rest = micro.iloc[1:]

        # ----------------------------------------------------
        # RETROCESOS
        # ----------------------------------------------------

        pullback_mask = (
            rest["close"] < opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result[
            "pullback_count"
        ] = pullback_count

        # Guardamos las posiciones absolutas dentro de
        # micro para el filtro de dominancia.
        pullback_indexes = [
            int(index)
            for index in rest.index[
                pullback_mask
            ].tolist()
        ]

        # ----------------------------------------------------
        # CIERRE 1M VERDE
        # ----------------------------------------------------

        minute_is_green = (
            closing > opening
        )

        if (
            pullback_count > 0
            and minute_is_green
        ):

            # =================================================
            # NUEVO FILTRO
            # =================================================

            dominance_ok = (
                _confirm_buyer_continuity(
                    micro,
                    opening,
                    pullback_indexes,
                )
            )

            if not dominance_ok:

                result[
                    "reason"
                ] = (
                    "CALL original confirmada, "
                    "pero sin continuidad compradora"
                )

                result[
                    "dominance"
                ] = "buyers"

                result[
                    "dominance_confirmed"
                ] = False

                return result

            # ------------------------------------------------
            # CALL FINAL
            # ------------------------------------------------

            result[
                "signal"
            ] = "call"

            result[
                "valid"
            ] = True

            result[
                "dominance"
            ] = "buyers"

            result[
                "dominance_confirmed"
            ] = True

            result[
                "reason"
            ] = (
                "CALL confirmada: "
                "primera 5S por encima de apertura; "
                "retroceso por debajo de apertura; "
                "vela 1M verde; "
                "continuidad compradora confirmada"
            )

            return result

        # ----------------------------------------------------
        # SIN RETROCESO
        # ----------------------------------------------------

        if pullback_count == 0:

            result[
                "reason"
            ] = (
                "CALL no válida: "
                "no hubo retroceso con cierre 5S "
                "por debajo de apertura 1M"
            )

            return result

        # ----------------------------------------------------
        # 1M NO VERDE
        # ----------------------------------------------------

        result[
            "reason"
        ] = (
            "CALL no válida: "
            "vela 1M no cerró verde"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    if first_5s_close < opening:

        rest = micro.iloc[1:]

        # ----------------------------------------------------
        # RETROCESOS
        # ----------------------------------------------------

        pullback_mask = (
            rest["close"] > opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result[
            "pullback_count"
        ] = pullback_count

        # ----------------------------------------------------
        # Índices de retroceso
        # ----------------------------------------------------

        pullback_indexes = [
            int(index)
            for index in rest.index[
                pullback_mask
            ].tolist()
        ]

        # ----------------------------------------------------
        # CIERRE 1M ROJO
        # ----------------------------------------------------

        minute_is_red = (
            closing < opening
        )

        if (
            pullback_count > 0
            and minute_is_red
        ):

            # =================================================
            # NUEVO FILTRO
            # =================================================

            dominance_ok = (
                _confirm_seller_continuity(
                    micro,
                    opening,
                    pullback_indexes,
                )
            )

            if not dominance_ok:

                result[
                    "reason"
                ] = (
                    "PUT original confirmada, "
                    "pero sin continuidad vendedora"
                )

                result[
                    "dominance"
                ] = "sellers"

                result[
                    "dominance_confirmed"
                ] = False

                return result

            # ------------------------------------------------
            # PUT FINAL
            # ------------------------------------------------

            result[
                "signal"
            ] = "put"

            result[
                "valid"
            ] = True

            result[
                "dominance"
            ] = "sellers"

            result[
                "dominance_confirmed"
            ] = True

            result[
                "reason"
            ] = (
                "PUT confirmada: "
                "primera 5S por debajo de apertura; "
                "retroceso por encima de apertura; "
                "vela 1M roja; "
                "continuidad vendedora confirmada"
            )

            return result

        # ----------------------------------------------------
        # SIN RETROCESO
        # ----------------------------------------------------

        if pullback_count == 0:

            result[
                "reason"
            ] = (
                "PUT no válida: "
                "no hubo retroceso con cierre 5S "
                "por encima de apertura 1M"
            )

            return result

        # ----------------------------------------------------
        # 1M NO ROJA
        # ----------------------------------------------------

        result[
            "reason"
        ] = (
            "PUT no válida: "
            "vela 1M no cerró roja"
        )

        return result

    # ========================================================
    # NEUTRAL
    # ========================================================

    result[
        "reason"
    ] = (
        "primera vela 5S cerró exactamente "
        "en la apertura de la vela 1M"
    )

    return result


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Función principal utilizada por bot.py.
    """

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
    """
    Devuelve:

        "call"
        "put"
        None
    """

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
    """
    Alias de compatibilidad.
    """

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
        "Estrategia:"
    )

    print(
        "1 minuto + microvelas de 5 segundos"
    )

    print(
        "Lógica original + confirmación de "
        "dominancia y continuidad."
        )
