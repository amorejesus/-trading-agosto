from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# ESTRATEGIA 1M + MICROVELAS DE 5 SEGUNDOS
# ============================================================
#
# LOGICA ORIGINAL — NO SE CAMBIA
#
# CALL:
#
# 1. Primera 5s cierra POR ENCIMA de apertura 1M.
# 2. Después existe al menos una 5s que cierra
#    POR DEBAJO de apertura 1M.
# 3. La vela 1M termina VERDE.
# 4. Se prepara CALL para N+1.
#
#
# PUT:
#
# 1. Primera 5s cierra POR DEBAJO de apertura 1M.
# 2. Después existe al menos una 5s que cierra
#    POR ENCIMA de apertura 1M.
# 3. La vela 1M termina ROJA.
# 4. Se prepara PUT para N+1.
#
#
# FILTRO AÑADIDO:
#
# Después de cumplirse la lógica original:
#
# CALL:
#     El dominio comprador debe confirmar continuidad.
#
# PUT:
#     El dominio vendedor debe confirmar continuidad.
#
# Este filtro NO sustituye la estrategia.
# Solamente permite la señal si existe continuidad
# posterior al último retroceso.
#
# ============================================================


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    """
    Conversión segura a float.
    """

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# NORMALIZAR MICROVELAS 5S
# ============================================================

def _normalize_5s(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza las microvelas de 5 segundos.

    Columnas obligatorias:
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

    rename = {}

    # --------------------------------------------------------
    # Compatibilidad IQ Option
    # --------------------------------------------------------

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
            inplace=True,
        )

    # --------------------------------------------------------
    # Validación
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
        subset=["open", "close"],
        inplace=True,
    )

    out.reset_index(
        drop=True,
        inplace=True,
    )

    return out


# ============================================================
# VALIDAR SECUENCIA DE MICROVELAS
# ============================================================

def _validate_5s_sequence(
    micro: pd.DataFrame,
) -> bool:
    """
    Comprueba que las microvelas sean consecutivas
    cada 5 segundos.

    Esto NO cambia la estrategia.

    Solo evita analizar:
        - duplicados
        - huecos
        - timestamps incorrectos
        - datos desordenados
    """

    if micro.empty:
        return False

    if "from" not in micro.columns:
        # Si IQ Option no entrega timestamp,
        # no podemos comprobar la secuencia.
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

        # 5 segundos exactos.
        if difference != 5:
            return False

    return True


# ============================================================
# FILTRAR MICROVELAS DEL MINUTO
# ============================================================

def _get_minute_micro_candles(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> pd.DataFrame:
    """
    Obtiene únicamente las microvelas pertenecientes
    al mismo minuto de la vela 1M.
    """

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

        except (TypeError, ValueError):
            minute_timestamp = None

    # --------------------------------------------------------
    # Si tenemos timestamp, filtrar exactamente el minuto
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
# FILTRO DE CONTINUIDAD COMPRADORA
# ============================================================

def _buyer_continuity_confirmed(
    micro: pd.DataFrame,
    opening: float,
) -> bool:
    """
    Confirma continuidad compradora.

    Se ejecuta DESPUÉS de encontrar el último
    retroceso comprador.

    Condiciones:

    1. Debe existir retroceso.
    2. Se toma el último cierre por debajo
       de la apertura 1M.
    3. Después de ese retroceso debe existir
       recuperación compradora.
    4. El último cierre debe estar por encima
       de la apertura 1M.
    5. Debe existir avance posterior:
       un cierre posterior superior al cierre
       inmediatamente anterior.

    No utiliza mayoría.
    No utiliza indicadores.
    """

    if micro.empty:
        return False

    # --------------------------------------------------------
    # Encontrar todos los retrocesos vendedores
    # --------------------------------------------------------

    pullback_indexes = []

    for i in range(1, len(micro)):

        close_value = _to_float(
            micro.iloc[i]["close"]
        )

        if close_value is None:
            continue

        if close_value < opening:
            pullback_indexes.append(i)

    if not pullback_indexes:
        return False

    # Último retroceso.
    last_pullback = (
        pullback_indexes[-1]
    )

    # No puede ser la última vela.
    if last_pullback >= len(micro) - 1:
        return False

    continuation = micro.iloc[
        last_pullback + 1:
    ].copy()

    if continuation.empty:
        return False

    # --------------------------------------------------------
    # Recuperación compradora
    # --------------------------------------------------------

    recovered = False

    for _, candle in continuation.iterrows():

        close_value = _to_float(
            candle["close"]
        )

        if close_value is None:
            continue

        if close_value > opening:
            recovered = True
            break

    if not recovered:
        return False

    # --------------------------------------------------------
    # Último cierre debe mantenerse encima
    # --------------------------------------------------------

    last_close = _to_float(
        continuation.iloc[-1]["close"]
    )

    if last_close is None:
        return False

    if last_close <= opening:
        return False

    # --------------------------------------------------------
    # Confirmación de avance
    # --------------------------------------------------------

    if len(continuation) >= 2:

        previous_close = _to_float(
            continuation.iloc[-2]["close"]
        )

        current_close = _to_float(
            continuation.iloc[-1]["close"]
        )

        if (
            previous_close is None
            or current_close is None
        ):
            return False

        if current_close <= previous_close:
            return False

    return True


# ============================================================
# FILTRO DE CONTINUIDAD VENDEDORA
# ============================================================

def _seller_continuity_confirmed(
    micro: pd.DataFrame,
    opening: float,
) -> bool:
    """
    Confirma continuidad vendedora.

    Es el espejo exacto del filtro comprador.

    Condiciones:

    1. Debe existir retroceso.
    2. Se toma el último cierre por encima
       de la apertura 1M.
    3. Después debe existir recuperación vendedora.
    4. El último cierre debe estar por debajo
       de la apertura 1M.
    5. Debe existir avance posterior:
       un cierre posterior inferior al cierre
       inmediatamente anterior.
    """

    if micro.empty:
        return False

    # --------------------------------------------------------
    # Encontrar todos los retrocesos compradores
    # --------------------------------------------------------

    pullback_indexes = []

    for i in range(1, len(micro)):

        close_value = _to_float(
            micro.iloc[i]["close"]
        )

        if close_value is None:
            continue

        if close_value > opening:
            pullback_indexes.append(i)

    if not pullback_indexes:
        return False

    # Último retroceso.
    last_pullback = (
        pullback_indexes[-1]
    )

    # No puede ser la última vela.
    if last_pullback >= len(micro) - 1:
        return False

    continuation = micro.iloc[
        last_pullback + 1:
    ].copy()

    if continuation.empty:
        return False

    # --------------------------------------------------------
    # Recuperación vendedora
    # --------------------------------------------------------

    recovered = False

    for _, candle in continuation.iterrows():

        close_value = _to_float(
            candle["close"]
        )

        if close_value is None:
            continue

        if close_value < opening:
            recovered = True
            break

    if not recovered:
        return False

    # --------------------------------------------------------
    # Último cierre debe mantenerse debajo
    # --------------------------------------------------------

    last_close = _to_float(
        continuation.iloc[-1]["close"]
    )

    if last_close is None:
        return False

    if last_close >= opening:
        return False

    # --------------------------------------------------------
    # Confirmación de avance
    # --------------------------------------------------------

    if len(continuation) >= 2:

        previous_close = _to_float(
            continuation.iloc[-2]["close"]
        )

        current_close = _to_float(
            continuation.iloc[-1]["close"]
        )

        if (
            previous_close is None
            or current_close is None
        ):
            return False

        if current_close >= previous_close:
            return False

    return True


# ============================================================
# ANALIZAR UNA VELA DE 1 MINUTO
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:

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

        "continuity_confirmed": False,
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
    # TIMESTAMP 1M
    # ========================================================

    if "from" in candle_1m.index:

        try:

            result["minute_timestamp"] = int(
                float(
                    candle_1m["from"]
                )
            )

        except (TypeError, ValueError):

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
    # VALIDACIÓN DE SECUENCIA
    # ========================================================

    if not _validate_5s_sequence(micro):

        result["reason"] = (
            "secuencia 5s inválida: "
            "hay huecos o timestamps incorrectos"
        )

        return result

    # ========================================================
    # NECESITAMOS AL MENOS 2 MICROVELAS
    # ========================================================

    if len(micro) < 2:

        result["reason"] = (
            "faltan microvelas 5s"
        )

        return result

    # ========================================================
    # PRIMERA 5S
    # ========================================================

    first_5s = micro.iloc[0]

    first_open = _to_float(
        first_5s["open"]
    )

    first_close = _to_float(
        first_5s["close"]
    )

    if first_open is None:

        result["reason"] = (
            "apertura primera 5s inválida"
        )

        return result

    if first_close is None:

        result["reason"] = (
            "cierre primera 5s inválido"
        )

        return result

    result["first_5s_open"] = first_open
    result["first_5s_close"] = first_close

    # ========================================================
    # CALL
    # ========================================================

    if first_close > opening:

        rest = micro.iloc[1:]

        pullback_mask = (
            rest["close"] < opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # ----------------------------------------------------
        # LOGICA ORIGINAL
        # ----------------------------------------------------

        if pullback_count <= 0:

            result["reason"] = (
                "CALL no válida: "
                "no hubo retroceso"
            )

            return result

        if closing <= opening:

            result["reason"] = (
                "CALL no válida: "
                "vela 1M no cerró verde"
            )

            return result

        # ----------------------------------------------------
        # FILTRO DOMINANTE COMPRADOR
        # ----------------------------------------------------

        continuity = (
            _buyer_continuity_confirmed(
                micro,
                opening,
            )
        )

        if not continuity:

            result["reason"] = (
                "CALL bloqueada: "
                "no hubo continuidad compradora"
            )

            return result

        # ----------------------------------------------------
        # CALL CONFIRMADA
        # ----------------------------------------------------

        result["signal"] = "call"

        result["valid"] = True

        result[
            "continuity_confirmed"
        ] = True

        result["reason"] = (
            "CALL confirmada: "
            "patrón original completo + "
            "continuidad compradora"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    if first_close < opening:

        rest = micro.iloc[1:]

        pullback_mask = (
            rest["close"] > opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # ----------------------------------------------------
        # LOGICA ORIGINAL
        # ----------------------------------------------------

        if pullback_count <= 0:

            result["reason"] = (
                "PUT no válida: "
                "no hubo retroceso"
            )

            return result

        if closing >= opening:

            result["reason"] = (
                "PUT no válida: "
                "vela 1M no cerró roja"
            )

            return result

        # ----------------------------------------------------
        # FILTRO DOMINANTE VENDEDOR
        # ----------------------------------------------------

        continuity = (
            _seller_continuity_confirmed(
                micro,
                opening,
            )
        )

        if not continuity:

            result["reason"] = (
                "PUT bloqueada: "
                "no hubo continuidad vendedora"
            )

            return result

        # ----------------------------------------------------
        # PUT CONFIRMADA
        # ----------------------------------------------------

        result["signal"] = "put"

        result["valid"] = True

        result[
            "continuity_confirmed"
        ] = True

        result["reason"] = (
            "PUT confirmada: "
            "patrón original completo + "
            "continuidad vendedora"
        )

        return result

    # ========================================================
    # NEUTRAL
    # ========================================================

    result["reason"] = (
        "primera 5s cerró exactamente "
        "en la apertura 1M"
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
        "Estrategia: 1M + microvelas 5S"
    )

    print(
        "Lógica original conservada."
    )

    print(
        "Filtro de continuidad dominante activo."
        )
