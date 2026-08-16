from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# ESTRATEGIA 1M + MICROVELAS DE 5 SEGUNDOS
# ============================================================
#
# CALL:
#
# 1. Comienza una vela de 1 minuto.
# 2. La primera vela de 5 segundos cierra POR ENCIMA
#    de la apertura de la vela de 1 minuto.
# 3. Durante el resto de ese minuto, al menos una vela
#    de 5 segundos cierra POR DEBAJO de la apertura de
#    la vela de 1 minuto.
# 4. La vela de 1 minuto termina VERDE:
#       cierre_1m > apertura_1m
# 5. Se genera CALL para la APERTURA de la siguiente
#    vela de 1 minuto.
#
#
# PUT:
#
# 1. Comienza una vela de 1 minuto.
# 2. La primera vela de 5 segundos cierra POR DEBAJO
#    de la apertura de la vela de 1 minuto.
# 3. Durante el resto de ese minuto, al menos una vela
#    de 5 segundos cierra POR ENCIMA de la apertura de
#    la vela de 1 minuto.
# 4. La vela de 1 minuto termina ROJA:
#       cierre_1m < apertura_1m
# 5. Se genera PUT para la APERTURA de la siguiente
#    vela de 1 minuto.
#
#
# IMPORTANTE:
#
# NO se utilizan:
# - EMA
# - RSI
# - ATR
# - Soporte/resistencia
# - Tendencia
# - Score
# - Volumen
# - Filtros adicionales
# - Martingala
#
# SOLO se utiliza la lÃ³gica solicitada.
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
# NORMALIZACIÃ“N DE MICROVELAS 5S
# ============================================================

def _normalize_5s(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el DataFrame de microvelas de 5 segundos.

    Se esperan como mÃ­nimo:
        open
        close

    Opcional:
        from
        high
        low
    """

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    # Compatibilidad con IQ Option.
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

    # Las Ãºnicas columnas obligatorias para esta estrategia.
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
# ANALIZAR UNA VELA DE 1 MINUTO
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Analiza una vela de 1 minuto YA CERRADA utilizando
    sus microvelas de 5 segundos.

    ========================================================
    CALL
    ========================================================

    Primera 5s:
        cierre > apertura 1M

    Retroceso:
        alguna 5s posterior cierra < apertura 1M

    Cierre 1M:
        cierre > apertura 1M

    Resultado:
        CALL para N+1


    ========================================================
    PUT
    ========================================================

    Primera 5s:
        cierre < apertura 1M

    Retroceso:
        alguna 5s posterior cierra > apertura 1M

    Cierre 1M:
        cierre < apertura 1M

    Resultado:
        PUT para N+1
    ========================================================
    """

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "reason": "sin seÃ±al",

        "minute_timestamp": None,

        "minute_open": None,
        "minute_close": None,

        "first_5s_open": None,
        "first_5s_close": None,

        "pullback_count": 0,
    }

    # --------------------------------------------------------
    # VALIDAR VELA DE 1 MINUTO
    # --------------------------------------------------------

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
            "apertura de vela 1M invÃ¡lida"
        )
        return result

    if closing is None:
        result["reason"] = (
            "cierre de vela 1M invÃ¡lido"
        )
        return result

    result["minute_open"] = opening
    result["minute_close"] = closing

    # Timestamp de la vela de 1 minuto.
    if "from" in candle_1m.index:

        try:
            result["minute_timestamp"] = int(
                float(candle_1m["from"])
            )

        except (TypeError, ValueError):
            result["minute_timestamp"] = None

    # --------------------------------------------------------
    # NORMALIZAR MICROVELAS
    # --------------------------------------------------------

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:

        result["reason"] = (
            "no hay microvelas de 5 segundos"
        )

        return result

    # --------------------------------------------------------
    # FILTRAR MICROVELAS DEL MISMO MINUTO
    # --------------------------------------------------------

    minute_timestamp = result[
        "minute_timestamp"
    ]

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = minute_timestamp
        end_time = minute_timestamp + 60

        micro = micro[
            (micro["from"] >= start_time)
            &
            (micro["from"] < end_time)
        ].copy()

        micro.reset_index(
            drop=True,
            inplace=True,
        )

    # Para esta lÃ³gica necesitamos al menos:
    #
    # primera 5s
    # otra 5s para comprobar retroceso
    #

    if len(micro) < 2:

        result["reason"] = (
            "faltan microvelas 5s del minuto"
        )

        return result

    # --------------------------------------------------------
    # PRIMERA VELA DE 5 SEGUNDOS
    # --------------------------------------------------------

    first_5s = micro.iloc[0]

    first_5s_open = _to_float(
        first_5s["open"]
    )

    first_5s_close = _to_float(
        first_5s["close"]
    )

    if first_5s_open is None:

        result["reason"] = (
            "apertura de primera 5s invÃ¡lida"
        )

        return result

    if first_5s_close is None:

        result["reason"] = (
            "cierre de primera 5s invÃ¡lido"
        )

        return result

    result["first_5s_open"] = (
        first_5s_open
    )

    result["first_5s_close"] = (
        first_5s_close
    )

    # ========================================================
    # CALL
    # ========================================================

    # Primera microvela verde respecto a la apertura 1M.
    if first_5s_close > opening:

        # Las demÃ¡s microvelas son el retroceso.
        rest = micro.iloc[1:]

        # Debe existir al menos una vela 5s que cierre
        # POR DEBAJO de la apertura de la vela de 1 minuto.
        pullback_mask = (
            rest["close"] < opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # Finalmente la vela de 1 minuto debe cerrar verde.
        minute_is_green = (
            closing > opening
        )

        if pullback_count > 0 and minute_is_green:

            result["signal"] = "call"

            result["valid"] = True

            result["reason"] = (
                "CALL confirmada: "
                "primera 5s por encima de apertura; "
                "retroceso con cierre 5s por debajo "
                "de apertura; "
                "vela 1M cerrÃ³ verde"
            )

            return result

        if pullback_count == 0:

            result["reason"] = (
                "CALL no vÃ¡lida: "
                "no hubo retroceso con cierre 5s "
                "por debajo de apertura 1M"
            )

            return result

        result["reason"] = (
            "CALL no vÃ¡lida: "
            "vela 1M no cerrÃ³ verde"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    # Primera microvela roja respecto a la apertura 1M.
    if first_5s_close < opening:

        # Las demÃ¡s microvelas son el retroceso.
        rest = micro.iloc[1:]

        # Debe existir al menos una vela 5s que cierre
        # POR ENCIMA de la apertura de la vela de 1 minuto.
        pullback_mask = (
            rest["close"] > opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # Finalmente la vela de 1 minuto debe cerrar roja.
        minute_is_red = (
            closing < opening
        )

        if pullback_count > 0 and minute_is_red:

            result["signal"] = "put"

            result["valid"] = True

            result["reason"] = (
                "PUT confirmada: "
                "primera 5s por debajo de apertura; "
                "retroceso con cierre 5s por encima "
                "de apertura; "
                "vela 1M cerrÃ³ roja"
            )

            return result

        if pullback_count == 0:

            result["reason"] = (
                "PUT no vÃ¡lida: "
                "no hubo retroceso con cierre 5s "
                "por encima de apertura 1M"
            )

            return result

        result["reason"] = (
            "PUT no vÃ¡lida: "
            "vela 1M no cerrÃ³ roja"
        )

        return result

    # ========================================================
    # NEUTRAL
    # ========================================================

    result["reason"] = (
        "primera vela 5s cerrÃ³ exactamente "
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
    FunciÃ³n principal que debe utilizar bot.py.
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
    Devuelve Ãºnicamente:

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
        "CALL/PUT segÃºn la lÃ³gica solicitada."
                     )
