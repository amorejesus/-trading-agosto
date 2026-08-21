from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_market


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = [
    "EURUSD-OTC",
]


# ============================================================
# TEMPORALIDADES
# ============================================================

TIMEFRAME = 60
MICRO_TIMEFRAME = 5

CANDLE_COUNT = 60
MICRO_CANDLE_COUNT = 12


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 78
EXPIRATION = 1


# ============================================================
# LOOP SNIPER
# ============================================================

POLL_INTERVAL = 0.03

# Ventana de ejecución de N+1.
# La orden se intenta desde el segundo 00 y se permite
# reintentar hasta el segundo indicado.
MAX_ENTRY_DELAY = 5.0


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 0.5


# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None

LAST_PROCESSED_MINUTE: Dict[str, int] = {}

PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}

LAST_TRADE_CANDLE: Dict[str, int] = {}

STREAMS_STARTED = False

ACTIVE_API_PAIR: Dict[str, str] = {}

# Seguimiento de la vela M1 que está transcurriendo.
# No modifica la decisión final de la estrategia.
LIVE_M1_STATE: Dict[str, Dict[str, Any]] = {}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message: str) -> bool:

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=TELEGRAM_HTTP_TIMEOUT,
        )

        return response.status_code == 200

    except Exception as exc:
        logger.warning("Telegram no disponible: %s", exc)
        return False


# ============================================================
# TELEGRAM WORKER
# ============================================================

def telegram_worker() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    logger.info("Telegram worker iniciado.")

    while True:

        try:

            url = (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/getUpdates"
            )

            params: Dict[str, Any] = {"timeout": 0}

            if LAST_UPDATE_ID is not None:
                params["offset"] = LAST_UPDATE_ID + 1

            response = requests.get(
                url,
                params=params,
                timeout=TELEGRAM_HTTP_TIMEOUT,
            )

            if response.status_code != 200:
                time.sleep(TELEGRAM_POLL_INTERVAL)
                continue

            data = response.json()

            if not data.get("ok"):
                time.sleep(TELEGRAM_POLL_INTERVAL)
                continue

            for update in data.get("result", []):

                LAST_UPDATE_ID = update.get("update_id")

                message = update.get("message", {})

                text = str(
                    message.get("text", "")
                ).strip().lower()

                chat_id = str(
                    message.get("chat", {}).get("id", "")
                )

                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text == "/start":

                    BOT_RUNNING = True

                    telegram_send(
                        "🟢 BOT ACTIVADO\n\n"
                        "ESTRATEGIA 1M + MONITOREO INTRAMINUTO\n"
                        "🎯 SNIPER N+1\n"
                        "La M1 se monitorea mientras está abierta.\n"
                        "La decisión definitiva se toma al cierre de N.\n"
                        "La entrada se intenta en 00-05s de N+1."
                    )

                    logger.info("BOT ACTIVADO")

                elif text == "/stop":

                    BOT_RUNNING = False

                    telegram_send(
                        "🔴 BOT DETENIDO\n\n"
                        "No se abrirán nuevas operaciones."
                    )

                    logger.info("BOT DETENIDO")

                elif text == "/status":

                    status = "🟢 ACTIVO" if BOT_RUNNING else "🔴 DETENIDO"

                    active = ", ".join(
                        f"{logical}->{api}"
                        for logical, api
                        in ACTIVE_API_PAIR.items()
                    )

                    telegram_send(
                        "📊 ESTADO\n\n"
                        f"Estado: {status}\n"
                        "Modo: SNIPER\n"
                        "Principal: 1M\n"
                        "Monitoreo: intraminuto\n"
                        "Entrada: N+1, segundos 00-05\n"
                        "Tipo: BINARIA\n"
                        f"Importe: ${AMOUNT}\n"
                        f"Pares: {', '.join(PAIRS)}\n"
                        f"Activos IQ: {active or 'sin resolver'}"
                    )

        except Exception as exc:

            logger.warning(
                "Telegram worker: %s",
                exc,
            )

        time.sleep(TELEGRAM_POLL_INTERVAL)


# ============================================================
# SERVIDOR IQ OPTION
# ============================================================

def get_server_timestamp() -> Optional[int]:

    if IQ is None:
        return None

    try:

        timestamp = IQ.get_server_timestamp()

        if timestamp is None:
            return None

        return int(float(timestamp))

    except Exception as exc:

        logger.warning(
            "Error timestamp servidor: %s",
            exc,
        )

        return None


# ============================================================
# DISPONIBILIDAD DEL ACTIVO
# ============================================================

def _binary_asset_is_usable(
    active: Dict[str, Any],
) -> bool:

    try:

        if not isinstance(active, dict):
            return False

        if not bool(active.get("enabled", False)):
            return False

        if bool(active.get("is_suspended", False)):
            return False

        return True

    except Exception:
        return False


def resolve_binary_asset(
    logical_pair: str,
) -> Optional[str]:

    if IQ is None:
        return None

    candidates = [
        logical_pair,
    ]

    if not logical_pair.upper().endswith("-OTC"):
        candidates.append(
            f"{logical_pair}-OTC"
        )

    try:

        init_data = IQ.get_all_init_v2()

        if not isinstance(init_data, dict):
            logger.warning(
                "%s | get_all_init_v2() devolvió datos inválidos.",
                logical_pair,
            )
            return None

        for option_type in ("binary", "turbo"):

            option_data = init_data.get(
                option_type,
                {},
            )

            if not isinstance(option_data, dict):
                continue

            actives = option_data.get(
                "actives",
                {},
            )

            if not isinstance(actives, dict):
                continue

            for active in actives.values():

                if not isinstance(active, dict):
                    continue

                raw_name = str(
                    active.get("name", "")
                )

                if "." in raw_name:
                    symbol = raw_name.split(".", 1)[1]
                else:
                    symbol = raw_name

                if symbol not in candidates:
                    continue

                if _binary_asset_is_usable(active):

                    logger.info(
                        "%s | activo %s disponible para %s",
                        logical_pair,
                        symbol,
                        option_type.upper(),
                    )

                    return symbol

        logger.warning(
            "%s | no hay BINARIA/TURBO disponible ahora.",
            logical_pair,
        )

        return None

    except Exception as exc:

        logger.warning(
            "%s | error consultando activos binarios: %s",
            logical_pair,
            exc,
        )

        return None


def resolve_all_binary_assets() -> None:

    global ACTIVE_API_PAIR

    if IQ is None:
        return

    for logical_pair in PAIRS:

        actual = resolve_binary_asset(
            logical_pair
        )

        if actual:

            previous = ACTIVE_API_PAIR.get(
                logical_pair
            )

            if previous != actual:

                ACTIVE_API_PAIR[
                    logical_pair
                ] = actual

                logger.info(
                    "%s | activo IQ seleccionado: %s",
                    logical_pair,
                    actual,
                )

        else:

            logger.warning(
                "%s | no hay activo binario disponible.",
                logical_pair,
            )


def get_api_pair(
    logical_pair: str,
) -> Optional[str]:

    actual = ACTIVE_API_PAIR.get(
        logical_pair
    )

    if actual:
        return actual

    actual = resolve_binary_asset(
        logical_pair
    )

    if actual:
        ACTIVE_API_PAIR[
            logical_pair
        ] = actual

    return actual


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq() -> bool:

    global IQ
    global STREAMS_STARTED

    if not IQ_EMAIL:
        raise ValueError("Falta IQ_EMAIL")

    if not IQ_PASSWORD:
        raise ValueError("Falta IQ_PASSWORD")

    logger.info("Conectando a IQ Option...")

    IQ = IQ_Option(
        IQ_EMAIL,
        IQ_PASSWORD,
    )

    connected, reason = IQ.connect()

    if not connected:
        raise ConnectionError(
            f"No se pudo conectar: {reason}"
        )

    logger.info("IQ Option conectado.")

    STREAMS_STARTED = False

    resolve_all_binary_assets()

    start_realtime_streams()

    server_ts = get_server_timestamp()

    logger.info(
        "Servidor IQ timestamp=%s",
        server_ts,
    )

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "Modo SNIPER\n"
        "Binarias\n"
        "Entrada en 00-05s de N+1."
    )

    return True


def ensure_connection() -> bool:

    global IQ
    global STREAMS_STARTED

    try:

        if IQ is None:
            return connect_iq()

        if IQ.check_connect():

            if not STREAMS_STARTED:
                resolve_all_binary_assets()
                start_realtime_streams()

            return True

        logger.warning(
            "Conexión IQ perdida. Reconectando..."
        )

        connected, reason = IQ.connect()

        if not connected:

            logger.error(
                "Reconexión fallida: %s",
                reason,
            )

            return False

        STREAMS_STARTED = False

        resolve_all_binary_assets()
        start_realtime_streams()

        telegram_send(
            "🟢 IQ OPTION RECONECTADO"
        )

        return True

    except Exception as exc:

        logger.error(
            "Error conexión IQ: %s",
            exc,
        )

        return False


# ============================================================
# STREAMS DE VELAS
# ============================================================

def start_realtime_streams() -> None:

    global STREAMS_STARTED

    if IQ is None:
        return

    if STREAMS_STARTED:
        return

    logger.info(
        "Iniciando streams en tiempo real..."
    )

    any_started = False

    for logical_pair in PAIRS:

        api_pair = get_api_pair(
            logical_pair
        )

        if not api_pair:

            logger.warning(
                "%s | no disponible para iniciar stream.",
                logical_pair,
            )

            continue

        try:

            IQ.start_candles_stream(
                api_pair,
                TIMEFRAME,
                5,
            )

            IQ.start_candles_stream(
                api_pair,
                MICRO_TIMEFRAME,
                20,
            )

            logger.info(
                "%s -> %s | streams 60s + 5s iniciados",
                logical_pair,
                api_pair,
            )

            any_started = True

        except Exception as exc:

            logger.error(
                "%s | error iniciando streams: %s",
                api_pair,
                exc,
            )

    STREAMS_STARTED = any_started


# ============================================================
# REALTIME DATAFRAME
# ============================================================

def realtime_dataframe(
    pair: str,
    timeframe: int,
) -> Optional[pd.DataFrame]:

    if IQ is None:
        return None

    try:

        candles = IQ.get_realtime_candles(
            pair,
            timeframe,
        )

        if not candles:
            return None

        rows = []

        for timestamp, candle in candles.items():

            try:

                rows.append(
                    {
                        "from": int(float(timestamp)),
                        "open": float(candle["open"]),
                        "close": float(candle["close"]),
                        "high": float(
                            candle.get(
                                "max",
                                candle.get("high"),
                            )
                        ),
                        "low": float(
                            candle.get(
                                "min",
                                candle.get("low"),
                            )
                        ),
                        "volume": float(
                            candle.get("volume", 0)
                        ),
                    }
                )

            except Exception:
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)

        df.sort_values(
            "from",
            inplace=True,
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        df.reset_index(
            drop=True,
            inplace=True,
        )

        return df

    except Exception as exc:

        logger.warning(
            "%s | realtime %ss error: %s",
            pair,
            timeframe,
            exc,
        )

        return None


# ============================================================
# VELAS 1M
# ============================================================

def get_1m_realtime(
    logical_pair: str,
) -> Optional[pd.DataFrame]:

    api_pair = get_api_pair(
        logical_pair
    )

    if not api_pair:
        return None

    return realtime_dataframe(
        api_pair,
        TIMEFRAME,
    )


# ============================================================
# MICROVELAS 5S
# ============================================================

def get_5s_realtime(
    logical_pair: str,
    minute_timestamp: int,
) -> Optional[pd.DataFrame]:

    api_pair = get_api_pair(
        logical_pair
    )

    if not api_pair:
        return None

    df = realtime_dataframe(
        api_pair,
        MICRO_TIMEFRAME,
    )

    if df is None:
        return None

    start = int(minute_timestamp)
    end = start + TIMEFRAME

    df = df[
        (df["from"] >= start)
        &
        (df["from"] < end)
    ].copy()

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# MONITOREO INTRAMINUTO
# ============================================================

def monitor_live_minute(
    logical_pair: str,
    df_1m: pd.DataFrame,
    server_ts: int,
) -> None:
    """
    Monitorea la M1 que está abierta durante todo el minuto.

    IMPORTANTE:
    Este monitoreo NO cambia la lógica final de la estrategia.
    Sirve para que el bot observe la evolución de N mientras
    está abierta y llegue al cierre con el seguimiento completo.
    La decisión definitiva sigue utilizando N cerrada.
    """

    if df_1m is None or len(df_1m) == 0:
        return

    try:
        live = df_1m.iloc[-1]

        live_ts = int(live["from"])

        current_minute = (
            int(server_ts) // TIMEFRAME
        ) * TIMEFRAME

        if live_ts != current_minute:
            return

        opening = float(live["open"])
        high = float(live["high"])
        low = float(live["low"])
        closing = float(live["close"])

        candle_range = max(
            0.0,
            high - low,
        )

        body = abs(
            closing - opening
        )

        body_ratio = (
            body / candle_range
            if candle_range > 0
            else 0.0
        )

        elapsed = max(
            0,
            min(
                TIMEFRAME,
                int(server_ts - live_ts),
            ),
        )

        previous = LIVE_M1_STATE.get(
            logical_pair
        )

        # Se crea una nueva observación al comenzar cada M1.
        if (
            previous is None
            or int(previous.get("timestamp", -1)) != live_ts
        ):

            LIVE_M1_STATE[
                logical_pair
            ] = {
                "timestamp": live_ts,
                "observations": 1,
                "last_second": elapsed,
                "open": opening,
                "high": high,
                "low": low,
                "close": closing,
                "body_ratio": body_ratio,
            }

            logger.info(
                "%s | 🔎 N ABIERTA | "
                "inicio=%s | observando durante 60s",
                logical_pair,
                live_ts,
            )

            return

        # Solo aumenta el contador cuando aparece una nueva marca
        # temporal del servidor, evitando inflar observaciones.
        if int(
            previous.get("last_second", -1)
        ) != elapsed:

            previous["observations"] = int(
                previous.get("observations", 0)
            ) + 1

            previous["last_second"] = elapsed

        previous["open"] = opening
        previous["high"] = high
        previous["low"] = low
        previous["close"] = closing
        previous["body_ratio"] = body_ratio

    except Exception:
        logger.exception(
            "%s | error monitoreando M1",
            logical_pair,
        )


# ============================================================
# VELAS
# ============================================================

def get_closed_1m(
    df: pd.DataFrame,
) -> Optional[pd.Series]:

    if df is None or len(df) < 2:
        return None

    return df.iloc[-2]


# ============================================================
# CREAR SEÑAL PENDIENTE
# ============================================================

def create_pending_signal(
    logical_pair: str,
    result: Dict[str, Any],
) -> None:

    signal = result.get("signal")

    if signal not in ("call", "put"):
        return

    minute_ts = result.get(
        "minute_timestamp"
    )

    if minute_ts is None:
        return

    minute_ts = int(minute_ts)

    next_timestamp = (
        minute_ts + TIMEFRAME
    )

    existing = PENDING_ENTRY.get(
        logical_pair
    )

    if existing is not None:

        if int(
            existing["minute_timestamp"]
        ) == minute_ts:

            return

    api_pair = get_api_pair(
        logical_pair
    )

    opening = result.get(
        "minute_open"
    )

    closing = result.get(
        "minute_close"
    )

    first_5s_close = result.get(
        "first_5s_close"
    )

    pullback_count = result.get(
        "pullback_count",
        0,
    )

    live_state = LIVE_M1_STATE.get(
        logical_pair,
        {},
    )

    observations = int(
        live_state.get(
            "observations",
            0,
        )
    )

    PENDING_ENTRY[
        logical_pair
    ] = {

        "signal": signal,

        "minute_timestamp": minute_ts,

        "next_timestamp": next_timestamp,

        "minute_open": opening,

        "minute_close": closing,

        "first_5s_close": first_5s_close,

        "pullback_count": pullback_count,

        "reason": result.get(
            "reason",
            "",
        ),

        "api_pair": api_pair,

        "created_at": time.time(),

        "entry_notified": False,

        "last_rejection": None,

        "attempts": 0,

        "last_attempt": 0.0,

        "live_observations": observations,
    }

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "🎯 SEÑAL CONFIRMADA\n\n"
        f"Par: {logical_pair}\n"
        f"Activo IQ: {api_pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N CERRADA\n"
        f"Timestamp: {minute_ts}\n"
        f"Apertura: {opening}\n"
        f"Cierre: {closing}\n\n"
        "🔎 MONITOREO INTRAMINUTO\n"
        f"Observaciones: {observations}\n\n"
        "PRIMERA 5S\n"
        f"Cierre: {first_5s_close}\n\n"
        "RETROCESOS 5S\n"
        f"Cantidad: {pullback_count}\n\n"
        "✅ PATRÓN CONFIRMADO\n"
        "🚫 N NO SE OPERA\n"
        "➡️ ENTRADA EXCLUSIVA EN N+1\n"
        f"N+1: {next_timestamp}\n"
        "⚡ Ventana de ejecución: 00-05s"
    )

    logger.info(
        "%s | SEÑAL %s | API=%s | N=%s | N+1=%s | observaciones=%s",
        logical_pair,
        signal.upper(),
        api_pair,
        minute_ts,
        next_timestamp,
        observations,
    )


# ============================================================
# COMPRA BINARIA
# ============================================================

def buy_binary(
    api_pair: str,
    signal: str,
) -> tuple[bool, Optional[Any], Any]:

    if IQ is None:
        return False, None, "IQ=None"

    try:

        result = IQ.buy(
            AMOUNT,
            api_pair,
            signal,
            EXPIRATION,
        )

        if isinstance(result, tuple):

            if len(result) >= 2:
                return (
                    bool(result[0]),
                    result[1],
                    result,
                )

            if len(result) == 1:
                return (
                    bool(result[0]),
                    None,
                    result,
                )

        if result is True:
            return (
                True,
                None,
                result,
            )

        return (
            False,
            None,
            result,
        )

    except Exception as exc:

        logger.exception(
            "%s | error buy binary",
            api_pair,
        )

        return (
            False,
            None,
            str(exc),
        )


# ============================================================
# EJECUCIÓN SNIPER N+1
# ============================================================

def execute_pending(
    logical_pair: str,
) -> bool:

    pending = PENDING_ENTRY.get(
        logical_pair
    )

    if pending is None:
        return False

    server_ts = get_server_timestamp()

    if server_ts is None:
        return False

    server_ts = int(server_ts)

    n_timestamp = int(
        pending["minute_timestamp"]
    )

    n1_timestamp = int(
        pending["next_timestamp"]
    )

    if server_ts < n1_timestamp:
        return False

    if LAST_TRADE_CANDLE.get(
        logical_pair
    ) == n1_timestamp:

        PENDING_ENTRY.pop(
            logical_pair,
            None,
        )

        return True

    signal = pending["signal"]

    api_pair = pending.get(
        "api_pair"
    )

    if not api_pair:
        api_pair = get_api_pair(
            logical_pair
        )
        pending["api_pair"] = api_pair

    if not api_pair:

        logger.error(
            "%s | N+1 llegó pero no hay símbolo binario disponible.",
            logical_pair,
        )

        return False

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    server_second = (
        server_ts % TIMEFRAME
    )

    if server_second > int(MAX_ENTRY_DELAY):
        elapsed = server_ts - n1_timestamp

        if elapsed > MAX_ENTRY_DELAY:
            telegram_send(
                "❌ ENTRADA NO EJECUTADA\n\n"
                f"Par: {logical_pair}\n"
                f"Activo IQ: {api_pair}\n"
                f"Dirección: {signal.upper()}\n"
                f"N+1: {n1_timestamp}\n\n"
                "Se agotó la ventana de ejecución 00-05s.\n\n"
                f"Última respuesta IQ:\n"
                f"{pending.get('last_rejection')}"
            )

            logger.error(
                "%s | ❌ ventana N+1 agotada | "
                "última respuesta=%s",
                logical_pair,
                pending.get("last_rejection"),
            )

            PENDING_ENTRY.pop(
                logical_pair,
                None,
            )

            return False

    if not pending.get(
        "entry_notified",
        False,
    ):

        pending["entry_notified"] = True

        telegram_send(
            "⚡ N+1 DETECTADA\n\n"
            f"Par: {logical_pair}\n"
            f"Activo IQ: {api_pair}\n"
            f"Dirección: {direction}\n\n"
            f"Servidor IQ: {server_ts}\n"
            f"Segundo N+1: {server_second:02d}\n\n"
            f"Timestamp N: {n_timestamp}\n"
            f"Timestamp N+1: {n1_timestamp}\n\n"
            "🎯 EJECUTANDO BINARIA"
        )

        logger.info(
            "%s | ⚡ N+1 DETECTADA | "
            "API=%s | server=%s | segundo=%s",
            logical_pair,
            api_pair,
            server_ts,
            server_second,
        )

    elapsed = (
        server_ts - n1_timestamp
    )

    if elapsed < 0:
        return False

    if elapsed > MAX_ENTRY_DELAY:

        PENDING_ENTRY.pop(
            logical_pair,
            None,
        )

        return False

    last_attempt = float(
        pending.get(
            "last_attempt",
            0.0,
        )
    )

    if (
        last_attempt > 0
        and time.time() - last_attempt < POLL_INTERVAL
    ):
        return False

    pending["last_attempt"] = time.time()

    pending["attempts"] = int(
        pending.get(
            "attempts",
            0,
        )
    ) + 1

    logger.info(
        "%s | ⚡ IQ.buy #%s | "
        "API=%s | %s | N+1=%s | segundo=%02d",
        logical_pair,
        pending["attempts"],
        api_pair,
        signal.upper(),
        n1_timestamp,
        server_second,
    )

    ok, order_id, raw_result = buy_binary(
        api_pair,
        signal,
    )

    if not ok:

        pending["last_rejection"] = raw_result

        logger.warning(
            "%s | ❌ IQ RECHAZÓ | "
            "API=%s | intento=%s | resultado=%s",
            logical_pair,
            api_pair,
            pending["attempts"],
            raw_result,
        )

        return False

    LAST_TRADE_CANDLE[
        logical_pair
    ] = n1_timestamp

    PENDING_ENTRY.pop(
        logical_pair,
        None,
    )

    telegram_send(
        "✅ OPERACIÓN ABIERTA\n\n"
        f"Par: {logical_pair}\n"
        f"Activo IQ: {api_pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "VELA N\n"
        f"Timestamp: {n_timestamp}\n"
        f"Apertura: {pending['minute_open']}\n"
        f"Cierre: {pending['minute_close']}\n\n"
        "ENTRADA N+1\n"
        f"Timestamp: {n1_timestamp}\n"
        f"Segundo: {server_second:02d}\n\n"
        f"💵 Importe: ${AMOUNT}\n"
        "⏱ Expiración: 1 minuto\n"
        f"🆔 ID: {order_id}\n"
        f"🔁 Intentos: {pending['attempts']}"
    )

    logger.info(
        "%s | ✅ BINARIA ABIERTA | "
        "API=%s | %s | N=%s | N+1=%s | segundo=%02d",
        logical_pair,
        api_pair,
        signal.upper(),
        n_timestamp,
        n1_timestamp,
        server_second,
    )

    return True


# ============================================================
# PROCESAR UN PAR
# ============================================================

def process_pair(
    logical_pair: str,
) -> None:

    # PRIMERO: ejecutar cualquier señal pendiente.
    if logical_pair in PENDING_ENTRY:
        execute_pending(logical_pair)

    df_1m = get_1m_realtime(
        logical_pair
    )

    if df_1m is None:
        return

    if len(df_1m) < 2:
        return

    server_ts = get_server_timestamp()

    if server_ts is None:
        return

    # --------------------------------------------------------
    # MONITOREO CONTINUO DE LA M1 ABIERTA.
    # NO CAMBIA LA DECISIÓN FINAL.
    # --------------------------------------------------------
    monitor_live_minute(
        logical_pair,
        df_1m,
        server_ts,
    )

    current_minute = (
        int(server_ts)
        // TIMEFRAME
    ) * TIMEFRAME

    closed_candle = get_closed_1m(
        df_1m
    )

    if closed_candle is None:
        return

    try:
        closed_ts = int(
            closed_candle["from"]
        )
    except Exception:
        return

    if closed_ts >= current_minute:
        return

    if (
        LAST_PROCESSED_MINUTE.get(
            logical_pair
        )
        == closed_ts
    ):
        return

    # --------------------------------------------------------
    # Los datos 5S se recopilan, pero la decisión sigue siendo
    # exclusivamente la M1 N cerrada.
    # No se bloquea el cierre por exigir exactamente 12 velas.
    # --------------------------------------------------------

    candles_5s = get_5s_realtime(
        logical_pair,
        closed_ts,
    )

    if candles_5s is None:
        candles_5s = pd.DataFrame()

    LAST_PROCESSED_MINUTE[
        logical_pair
    ] = closed_ts

    result = analyze_market(
        closed_candle,
        candles_5s,
    )

    result[
        "minute_timestamp"
    ] = closed_ts

    result[
        "minute_open"
    ] = float(
        closed_candle["open"]
    )

    result[
        "minute_close"
    ] = float(
        closed_candle["close"]
    )

    signal = result.get(
        "signal"
    )

    reason = result.get(
        "reason",
        "",
    )

    logger.info(
        "%s | N=%s | signal=%s | reason=%s",
        logical_pair,
        closed_ts,
        signal,
        reason,
    )

    if signal in (
        "call",
        "put",
    ):

        create_pending_signal(
            logical_pair,
            result,
        )

        # Si el cierre coincide con el cambio de minuto,
        # intenta inmediatamente. Si todavía no es N+1,
        # queda pendiente y se ejecutará en el loop siguiente.
        execute_pending(
            logical_pair
        )

    else:

        logger.info(
            "%s | N=%s | SIN SEÑAL | %s",
            logical_pair,
            closed_ts,
            reason,
        )

    # La observación de N ya terminó.
    LIVE_M1_STATE.pop(
        logical_pair,
        None,
    )


# ============================================================
# PROCESAR TODOS LOS PARES
# ============================================================

def analyze_all_pairs() -> None:

    if not BOT_RUNNING:
        return

    for logical_pair in PAIRS:

        if not BOT_RUNNING:
            return

        try:

            process_pair(
                logical_pair
            )

        except Exception:

            logger.exception(
                "%s | error procesando par",
                logical_pair,
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    global BOT_RUNNING

    logger.info(
        "=========================================="
    )

    logger.info(
        "BOT IQ OPTION BINARIAS"
    )

    logger.info(
        "MODO SNIPER N+1"
    )

    logger.info(
        "ESTRATEGIA 1M + MONITOREO INTRAMINUTO"
    )

    logger.info(
        "PARES: %s",
        ", ".join(PAIRS),
    )

    logger.info(
        "AMOUNT: $%s",
        AMOUNT,
    )

    logger.info(
        "EXPIRATION: %s minuto",
        EXPIRATION,
    )

    logger.info(
        "VENTANA N+1: 00-05s"
    )

    logger.info(
        "=========================================="
    )

    required = {
        "IQ_EMAIL": IQ_EMAIL,
        "IQ_PASSWORD": IQ_PASSWORD,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }

    missing = [
        key
        for key, value in required.items()
        if not value
    ]

    if missing:

        logger.error(
            "Faltan variables: %s",
            ", ".join(missing),
        )

        return

    try:

        connect_iq()

    except Exception as exc:

        logger.exception(
            "No se pudo conectar a IQ Option."
        )

        telegram_send(
            "❌ ERROR IQ OPTION\n\n"
            f"{exc}"
        )

        return

    telegram_thread = threading.Thread(
        target=telegram_worker,
        daemon=True,
    )

    telegram_thread.start()

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "BINARIAS\n"
        "MODO SNIPER\n\n"
        "ESTRATEGIA:\n"
        "M1 + monitoreo intraminuto\n\n"
        "🔎 N se observa durante todo el minuto\n"
        "✅ Decisión definitiva al cierre de N\n"
        "🎯 Entrada SOLO en N+1\n"
        "⚡ Ejecución en segundos 00-05\n"
        "🔄 Reintento rápido dentro de la ventana\n"
        "🔎 Activo binario resuelto automáticamente\n"
        f"💵 ${AMOUNT}\n"
        "⏱ 1 minuto"
    )

    while True:

        try:

            if not BOT_RUNNING:

                time.sleep(0.20)

                continue

            if not ensure_connection():

                time.sleep(1)

                continue

            resolve_all_binary_assets()

            analyze_all_pairs()

            time.sleep(
                POLL_INTERVAL
            )

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            logger.info(
                "Bot detenido."
            )

            break

        except Exception:

            logger.exception(
                "Error principal"
            )

            time.sleep(0.5)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
