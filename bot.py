from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# STRATEGY.PY
#
# ESTRATEGIA:
#
# M5 = ESTRUCTURA
# M1 = CONFIRMACIÓN / CONTEO
#
# SOPORTE M5:
#   toque/rompimiento en M1
#   ↓
#   la vela del toque NO cuenta
#   ↓
#   esperar 6 velas M1 COMPLETAS
#   ↓
#   cierre de la sexta
#   ↓
#   CALL en apertura de N+1
#
# RESISTENCIA M5:
#   toque/rompimiento en M1
#   ↓
#   la vela del toque NO cuenta
#   ↓
#   esperar 6 velas M1 COMPLETAS
#   ↓
#   cierre de la sexta
#   ↓
#   PUT en apertura de N+1
#
# IMPORTANTE:
# - No usa 12 velas de 5 segundos.
# - No importa el color de las 6 velas.
# - No importa si hacen doji.
# - No importa si hay agotamiento.
# - No importa si hay continuidad.
# - No importa si rechazan o rompen.
# - La dirección viene de la estructura M5.
# ============================================================


# ============================================================
# CONFIGURACIÓN
# ============================================================

WAITING_CANDLES = 6

SIGNAL_CALL = "call"
SIGNAL_PUT = "put"

TYPE_SUPPORT = "support"
TYPE_RESISTANCE = "resistance"

STATE_WAITING = "waiting"
STATE_READY = "ready"
STATE_EXECUTED = "executed"


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

        value = float(value)

        if pd.isna(value):
            return None

        return value

    except (TypeError, ValueError):
        return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    column_map = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "MAX": "high",
        "MIN": "low",
        "Max": "high",
        "Min": "low",
    }

    for old_name, new_name in column_map.items():
        if old_name in out.columns and new_name not in out.columns:
            rename[old_name] = new_name

    if rename:
        out.rename(columns=rename, inplace=True)

    for column in (
        "open",
        "high",
        "low",
        "close",
        "from",
    ):
        if column in out.columns:
            out[column] = pd.to_numeric(
                out[column],
                errors="coerce",
            )

    if "from" in out.columns:
        out.dropna(
            subset=["from"],
            inplace=True,
        )

        out.sort_values(
            "from",
            inplace=True,
        )

        out.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

    required = (
        "open",
        "high",
        "low",
        "close",
    )

    for column in required:
        if column not in out.columns:
            return pd.DataFrame()

    out.dropna(
        subset=list(required),
        inplace=True,
    )

    out.reset_index(
        drop=True,
        inplace=True,
    )

    return out


def _normalize_m1(candles: Any) -> pd.DataFrame:
    if candles is None:
        return pd.DataFrame()

    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        try:
            df = pd.DataFrame(list(candles))
        except Exception:
            return pd.DataFrame()

    return _normalize_columns(df)


def _normalize_m5(candles: Any) -> pd.DataFrame:
    if candles is None:
        return pd.DataFrame()

    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        try:
            df = pd.DataFrame(list(candles))
        except Exception:
            return pd.DataFrame()

    return _normalize_columns(df)


# ============================================================
# DIRECCIÓN DE VELA
# ============================================================

def candle_direction(candle: Any) -> str:
    if candle is None:
        return "doji"

    try:
        opening = _to_float(candle["open"])
        closing = _to_float(candle["close"])
    except Exception:
        return "doji"

    if opening is None or closing is None:
        return "doji"

    if closing > opening:
        return "bullish"

    if closing < opening:
        return "bearish"

    return "doji"


# ============================================================
# SOPORTE / RESISTENCIA M5
#
# Se utilizan las zonas de la última vela M5 COMPLETADA.
#
# Soporte    = mínimo M5
# Resistencia = máximo M5
# ============================================================

def get_m5_levels(
    m5_candles: Any,
) -> Dict[str, Any]:

    result = {
        "available": False,
        "support": None,
        "resistance": None,
        "timestamp": None,
        "reason": "sin datos M5",
    }

    m5 = _normalize_m5(m5_candles)

    if m5.empty:
        return result

    if len(m5) < 1:
        return result

    # La última M5 recibida se considera la estructura más reciente.
    last = m5.iloc[-1]

    support = _to_float(last["low"])
    resistance = _to_float(last["high"])

    if support is None:
        result["reason"] = "soporte M5 inválido"
        return result

    if resistance is None:
        result["reason"] = "resistencia M5 inválida"
        return result

    if resistance < support:
        result["reason"] = "estructura M5 inválida"
        return result

    result["available"] = True
    result["support"] = support
    result["resistance"] = resistance

    if "from" in last.index:
        timestamp = _to_float(last["from"])

        if timestamp is not None:
            result["timestamp"] = int(timestamp)

    result["reason"] = "estructura M5 disponible"

    return result


# ============================================================
# DETECTAR TOQUE / ROMPIMIENTO M1
#
# SOPORTE:
#   low <= soporte
#
# RESISTENCIA:
#   high >= resistencia
#
# No importa cómo termine la vela.
# ============================================================

def detect_zone_touch(
    candle_m1: Any,
    support: Optional[float],
    resistance: Optional[float],
) -> Optional[str]:

    if candle_m1 is None:
        return None

    if support is None or resistance is None:
        return None

    try:
        low = _to_float(candle_m1["low"])
        high = _to_float(candle_m1["high"])
    except Exception:
        return None

    if low is None or high is None:
        return None

    # --------------------------------------------------------
    # SOPORTE
    # --------------------------------------------------------

    if low <= support:
        return TYPE_SUPPORT

    # --------------------------------------------------------
    # RESISTENCIA
    # --------------------------------------------------------

    if high >= resistance:
        return TYPE_RESISTANCE

    return None


# ============================================================
# CREAR ESTADO DEL TOQUE
# ============================================================

def create_touch_state(
    zone_type: str,
    candle: Any,
) -> Dict[str, Any]:

    timestamp = None

    try:
        timestamp_value = _to_float(
            candle.get("from")
        )

        if timestamp_value is not None:
            timestamp = int(timestamp_value)

    except Exception:
        pass

    if zone_type == TYPE_SUPPORT:
        signal = SIGNAL_CALL
    elif zone_type == TYPE_RESISTANCE:
        signal = SIGNAL_PUT
    else:
        signal = None

    return {
        "active": True,
        "state": STATE_WAITING,

        "zone": zone_type,
        "signal": signal,

        "touch_timestamp": timestamp,

        # ----------------------------------------------------
        # MUY IMPORTANTE:
        #
        # La vela del toque empieza en 0.
        #
        # La siguiente vela será 1.
        # Después:
        # 2
        # 3
        # 4
        # 5
        # 6
        #
        # Al cerrar la 6 -> READY.
        # ----------------------------------------------------

        "completed_after_touch": 0,

        "signal_timestamp": None,

        "entry_timestamp": None,

        "reason": "toque detectado",
    }


# ============================================================
# ACTUALIZAR CON UNA NUEVA VELA M1
# ============================================================

def update_touch_state(
    state: Optional[Dict[str, Any]],
    candle_m1: Any,
) -> Dict[str, Any]:

    if state is None:
        return {
            "active": False,
            "state": STATE_WAITING,
            "zone": None,
            "signal": None,
            "completed_after_touch": 0,
            "signal_timestamp": None,
            "entry_timestamp": None,
            "reason": "sin estado",
        }

    if not state.get("active"):
        return state

    if candle_m1 is None:
        return state

    # --------------------------------------------------------
    # SI YA ESTÁ LISTO
    # --------------------------------------------------------

    if state.get("state") == STATE_READY:
        return state

    if state.get("state") == STATE_EXECUTED:
        return state

    timestamp = None

    try:
        timestamp_value = _to_float(
            candle_m1.get("from")
        )

        if timestamp_value is not None:
            timestamp = int(timestamp_value)

    except Exception:
        pass

    # --------------------------------------------------------
    # CONTAR UNA VELA M1 COMPLETA DESPUÉS DEL TOQUE
    # --------------------------------------------------------

    completed = int(
        state.get(
            "completed_after_touch",
            0,
        )
    )

    completed += 1

    state["completed_after_touch"] = completed

    # --------------------------------------------------------
    # NO ANALIZAMOS EL COLOR.
    #
    # Solo esperamos que termine la sexta vela.
    # --------------------------------------------------------

    if completed < WAITING_CANDLES:

        state["state"] = STATE_WAITING

        state["reason"] = (
            f"esperando vela "
            f"{completed}/{WAITING_CANDLES} "
            f"después del toque"
        )

        return state

    # --------------------------------------------------------
    # SEXTA VELA COMPLETADA
    # --------------------------------------------------------

    state["state"] = STATE_READY

    state["signal_timestamp"] = timestamp

    state["reason"] = (
        "6 velas M1 completadas después del toque"
    )

    return state


# ============================================================
# PREPARAR N+1
# ============================================================

def prepare_n_plus_1(
    state: Optional[Dict[str, Any]],
    next_timestamp: Optional[int] = None,
) -> Optional[str]:

    if state is None:
        return None

    if not state.get("active"):
        return None

    if state.get("state") != STATE_READY:
        return None

    signal = state.get("signal")

    if signal not in (
        SIGNAL_CALL,
        SIGNAL_PUT,
    ):
        return None

    state["entry_timestamp"] = next_timestamp

    return signal


# ============================================================
# MARCAR EJECUTADA
# ============================================================

def mark_executed(
    state: Optional[Dict[str, Any]],
) -> None:

    if state is None:
        return

    state["state"] = STATE_EXECUTED
    state["active"] = False
    state["reason"] = "operación ejecutada en N+1"


# ============================================================
# ANALIZAR UNA SECUENCIA COMPLETA
#
# Esta función recibe las velas M1 y la estructura M5.
#
# IMPORTANTE:
# La última vela M1 se interpreta como la vela que acaba
# de cerrar.
# ============================================================

def analyze_sequence(
    candles_m1: Any,
    candles_m5: Any,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "valid": False,
        "signal": None,
        "zone": None,

        "support": None,
        "resistance": None,

        "touch_detected": False,
        "touch_timestamp": None,

        "completed_after_touch": 0,

        "waiting": False,
        "ready": False,

        "entry": False,
        "entry_timestamp": None,

        "reason": "sin señal",
    }

    m1 = _normalize_m1(candles_m1)

    if m1.empty:
        result["reason"] = "sin velas M1"
        return result

    m5_levels = get_m5_levels(candles_m5)

    if not m5_levels["available"]:
        result["reason"] = m5_levels["reason"]
        return result

    support = m5_levels["support"]
    resistance = m5_levels["resistance"]

    result["support"] = support
    result["resistance"] = resistance

    # --------------------------------------------------------
    # BUSCAR EL ÚLTIMO TOQUE M1
    # --------------------------------------------------------

    touch_index = None
    touch_zone = None

    for index in range(len(m1) - 1, -1, -1):

        candle = m1.iloc[index]

        zone = detect_zone_touch(
            candle,
            support,
            resistance,
        )

        if zone is not None:
            touch_index = index
            touch_zone = zone
            break

    if touch_index is None:
        result["reason"] = (
            "ninguna vela M1 tocó soporte/resistencia M5"
        )
        return result

    result["touch_detected"] = True
    result["zone"] = touch_zone

    touch_candle = m1.iloc[touch_index]

    touch_timestamp = None

    if "from" in touch_candle.index:
        value = _to_float(
            touch_candle["from"]
        )

        if value is not None:
            touch_timestamp = int(value)

    result["touch_timestamp"] = touch_timestamp

    # --------------------------------------------------------
    # TODAS LAS VELAS DESPUÉS DEL TOQUE
    #
    # LA VELA DEL TOQUE NO SE CUENTA.
    # --------------------------------------------------------

    candles_after_touch = m1.iloc[
        touch_index + 1:
    ].copy()

    completed = len(candles_after_touch)

    result["completed_after_touch"] = completed

    # --------------------------------------------------------
    # TODAVÍA NO LLEGÓ A 6
    # --------------------------------------------------------

    if completed < WAITING_CANDLES:

        result["waiting"] = True

        result["reason"] = (
            f"esperando {WAITING_CANDLES - completed} "
            f"vela(s) M1 después del toque"
        )

        return result

    # --------------------------------------------------------
    # EXACTAMENTE / AL MENOS 6 VELAS
    # --------------------------------------------------------

    sixth_candle = candles_after_touch.iloc[
        WAITING_CANDLES - 1
    ]

    sixth_timestamp = None

    if "from" in sixth_candle.index:
        value = _to_float(
            sixth_candle["from"]
        )

        if value is not None:
            sixth_timestamp = int(value)

    # --------------------------------------------------------
    # DIRECCIÓN:
    #
    # SOPORTE  -> CALL
    # RESISTENCIA -> PUT
    #
    # NO SE USA:
    # - color de la sexta
    # - cuerpo
    # - doji
    # - mecha
    # - agotamiento
    # - continuidad
    # --------------------------------------------------------

    if touch_zone == TYPE_SUPPORT:
        signal = SIGNAL_CALL

    elif touch_zone == TYPE_RESISTANCE:
        signal = SIGNAL_PUT

    else:
        result["reason"] = "zona desconocida"
        return result

    result["signal"] = signal
    result["valid"] = True
    result["ready"] = True
    result["entry_timestamp"] = (
        sixth_timestamp + 60
        if sixth_timestamp is not None
        else None
    )

    result["reason"] = (
        f"{touch_zone.upper()} M5 detectado + "
        f"{WAITING_CANDLES} velas M1 completadas"
    )

    return result


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(
    candles_m1: Any,
    candles_m5: Any,
) -> Dict[str, Any]:

    return analyze_sequence(
        candles_m1,
        candles_m5,
    )


# ============================================================
# GET SIGNAL
# ============================================================

def get_signal(
    candles_m1: Any,
    candles_m5: Any,
) -> Optional[str]:

    result = analyze_market(
        candles_m1,
        candles_m5,
    )

    if not result.get("valid"):
        return None

    return result.get("signal")


# ============================================================
# COMPATIBILIDAD
#
# Estas funciones se mantienen para que strategy.py siga
# teniendo los nombres esperados por versiones anteriores
# del bot.
#
# SIN DATOS M5 NO SE GENERA SEÑAL.
# ============================================================

def check_pattern(
    candles_m1: Any,
    candles_m5: Any = None,
) -> Optional[str]:

    if candles_m5 is None:
        return None

    return get_signal(
        candles_m1,
        candles_m5,
    )


def signal(
    candles_m1: Any,
    candles_m5: Any = None,
) -> Optional[str]:

    return check_pattern(
        candles_m1,
        candles_m5,
    )


def get_m1_direction(
    candles_m1: Any,
) -> Optional[str]:

    m1 = _normalize_m1(candles_m1)

    if m1.empty:
        return None

    candle = m1.iloc[-1]

    direction = candle_direction(candle)

    if direction == "bullish":
        return SIGNAL_CALL

    if direction == "bearish":
        return SIGNAL_PUT

    return None


def get_strategy_analysis(
    candles_m1: Any,
    candles_m5: Any = None,
) -> Optional[Dict[str, Any]]:

    if candles_m5 is None:
        return None

    return analyze_market(
        candles_m1,
        candles_m5,
    )


# ============================================================
# ESTADO INDEPENDIENTE POR PAR
#
# Esto permite que cada activo tenga su propio conteo.
# ============================================================

_PAIR_STATES: Dict[str, Dict[str, Any]] = {}


def reset_pair_state(
    pair: str,
) -> None:

    if not isinstance(pair, str):
        return

    _PAIR_STATES.pop(
        pair,
        None,
    )


def get_pair_state(
    pair: str,
) -> Optional[Dict[str, Any]]:

    return _PAIR_STATES.get(pair)


def process_pair_candle(
    pair: str,
    candle_m1: Any,
    m5_candles: Any,
) -> Dict[str, Any]:

    result = {
        "pair": pair,
        "signal": None,
        "ready": False,
        "entry": False,
        "state": None,
        "reason": "sin señal",
    }

    if not isinstance(pair, str) or not pair:
        result["reason"] = "par inválido"
        return result

    if candle_m1 is None:
        result["reason"] = "vela M1 inválida"
        return result

    levels = get_m5_levels(
        m5_candles
    )

    if not levels["available"]:
        result["reason"] = levels["reason"]
        return result

    support = levels["support"]
    resistance = levels["resistance"]

    # --------------------------------------------------------
    # COMPROBAR SI EXISTE UN ESTADO ACTIVO
    # --------------------------------------------------------

    state = _PAIR_STATES.get(pair)

    # --------------------------------------------------------
    # SI NO EXISTE TOQUE ACTIVO, BUSCAR UNO
    # --------------------------------------------------------

    if state is None:

        zone = detect_zone_touch(
            candle_m1,
            support,
            resistance,
        )

        if zone is None:

            result["reason"] = (
                "M1 sin toque en zona M5"
            )

            return result

        state = create_touch_state(
            zone,
            candle_m1,
        )

        _PAIR_STATES[pair] = state

        result["state"] = state.copy()

        result["reason"] = (
            f"TOQUE {zone.upper()} M5 detectado; "
            f"comienza conteo 0/{WAITING_CANDLES}"
        )

        return result

    # --------------------------------------------------------
    # ESTADO READY
    #
    # Si el bot consulta después del cierre de la sexta,
    # la señal queda disponible para N+1.
    # --------------------------------------------------------

    if state.get("state") == STATE_READY:

        result["signal"] = state.get("signal")
        result["ready"] = True
        result["entry"] = True
        result["state"] = state.copy()

        result["reason"] = (
            "señal preparada para ejecución N+1"
        )

        return result

    # --------------------------------------------------------
    # ESTADO EJECUTADO
    # --------------------------------------------------------

    if state.get("state") == STATE_EXECUTED:

        result["state"] = state.copy()
        result["reason"] = "estado ya ejecutado"

        return result

    # --------------------------------------------------------
    # CONTAR LA NUEVA VELA
    # --------------------------------------------------------

    state = update_touch_state(
        state,
        candle_m1,
    )

    _PAIR_STATES[pair] = state

    result["state"] = state.copy()

    if state.get("state") == STATE_READY:

        result["signal"] = state.get("signal")
        result["ready"] = True
        result["entry"] = True

        result["reason"] = (
            "sexta vela cerrada; "
            "entrada preparada para N+1"
        )

        return result

    result["reason"] = state.get(
        "reason",
        "esperando",
    )

    return result


# ============================================================
# MARCAR OPERACIÓN EJECUTADA
# ============================================================

def mark_pair_executed(
    pair: str,
) -> None:

    state = _PAIR_STATES.get(pair)

    if state is None:
        return

    mark_executed(
        state
    )


# ============================================================
# INFORMACIÓN DEL ESTADO
# ============================================================

def get_pair_analysis(
    pair: str,
) -> Optional[Dict[str, Any]]:

    state = _PAIR_STATES.get(pair)

    if state is None:
        return None

    return state.copy()


# ============================================================
# PRUEBA LOCAL
# ============================================================

if __name__ == "__main__":

    print("==========================================")
    print("STRATEGY.PY CARGADO CORRECTAMENTE")
    print("==========================================")
    print("ESTRUCTURA       : M5")
    print("ANÁLISIS         : M1")
    print("VELAS 5S         : NO UTILIZADAS")
    print("VELAS ESPERA     : 6 M1")
    print("VELA DEL TOQUE   : NO CUENTA")
    print("------------------------------------------")
    print("SOPORTE M5       -> CALL")
    print("RESISTENCIA M5   -> PUT")
    print("------------------------------------------")
    print("TOQUE")
    print("  ↓")
    print("N-6")
    print("  ↓")
    print("N-5")
    print("  ↓")
    print("N-4")
    print("  ↓")
    print("N-3")
    print("  ↓")
    print("N-2")
    print("  ↓")
    print("N-1")
    print("  ↓")
    print("N = 6.ª vela después del toque")
    print("  ↓")
    print("N+1 = EJECUCIÓN")
    print("==========================================")
