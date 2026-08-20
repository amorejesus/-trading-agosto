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

# SOLO ESTE PAR
PAIRS = [
    "EURUSD",
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

AMOUNT = 70
EXPIRATION = 1


# ============================================================
# EJECUCIÓN N+1
# ============================================================

POLL_INTERVAL = 0.03

# Ventana máxima de reintentos después de comenzar N+1.
# Se mantiene suficientemente amplia para rechazos temporales.
MAX_ENTRY_DELAY = 15.0

# Tiempo mínimo entre dos llamadas consecutivas a IQ.buy().
BUY_RETRY_INTERVAL = 0.08


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 0.8


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

    if not TELEGRAM_TOKEN:
        return False

    if not TELEGRAM_CHAT_ID:
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

        if response.status_code != 200:

            logger.warning(
                "Telegram HTTP %s",
                response.status_code,
            )

            return False

        return True

    except Exception as exc:

        logger.warning(
            "Telegram no disponible: %s",
            exc,
        )

        return False


# ============================================================
# TELEGRAM WORKER
# ============================================================

def telegram_worker() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    logger.info(
        "Telegram worker iniciado."
    )

    while True:

        try:

            url = (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/getUpdates"
            )

            params: Dict[str, Any] = {
                "timeout": 0,
            }

            if LAST_UPDATE_ID is not None:

                params["offset"] = (
                    LAST_UPDATE_ID + 1
                )

            response = requests.get(
                url,
                params=params,
                timeout=TELEGRAM_HTTP_TIMEOUT,
            )

            if response.status_code != 200:

                time.sleep(
                    TELEGRAM_POLL_INTERVAL
                )

                continue

            data = response.json()

            if not data.get("ok"):

                time.sleep(
                    TELEGRAM_POLL_INTERVAL
                )

                continue

            for update in data.get(
                "result",
                [],
            ):

                LAST_UPDATE_ID = update.get(
                    "update_id"
                )

                message = update.get(
                    "message",
                    {},
                )

                text = str(
                    message.get(
                        "text",
                        "",
                    )
                ).strip().lower()

                chat_id = str(
                    message.get(
                        "chat",
                        {},
                    ).get(
                        "id",
                        "",
                    )
                )

                if chat_id != str(
                    TELEGRAM_CHAT_ID
                ):
                    continue

                if text == "/start":

                    BOT_RUNNING = True

                    telegram_send(
                        "🟢 BOT ACTIVADO\n\n"
                        "ESTRATEGIA 1M + 5S\n\n"
                        "CALL:\n"
                        "🟢 Primera 5S > apertura 1M\n"
                        "🔴 Retroceso 5S < apertura 1M\n"
                        "🟢 Cierre 1M verde\n\n"
                        "PUT:\n"
                        "🔴 Primera 5S < apertura 1M\n"
                        "🟢 Retroceso 5S > apertura 1M\n"
                        "🔴 Cierre 1M rojo\n\n"
                        "🎯 ENTRADA N+1\n"
                        "⚡ Reintento automático si IQ rechaza temporalmente."
                    )

                    logger.info(
                        "BOT ACTIVADO"
                    )

                elif text == "/stop":

                    BOT_RUNNING = False

                    telegram_send(
                        "🔴 BOT DETENIDO\n\n"
                        "No se abrirán nuevas operaciones."
                    )

                    logger.info(
                        "BOT DETENIDO"
                    )

                elif text == "/status":

                    status = (
                        "🟢 ACTIVO"
                        if BOT_RUNNING
                        else
                        "🔴 DETENIDO"
                    )

                    telegram_send(
                        "📊 ESTADO\n\n"
                        f"Estado: {status}\n"
                        "Modo: SNIPER N+1\n"
                        "Principal: 1M\n"
                        "Micro: 5S\n"
                        "Entrada: N+1\n"
                        "Tipo: BINARIA\n"
                        f"Importe: ${AMOUNT}\n"
                        f"Pares: {', '.join(PAIRS)}"
                    )

        except Exception as exc:

            logger.warning(
                "Telegram worker: %s",
                exc,
            )

        time.sleep(
            TELEGRAM_POLL_INTERVAL
        )


# ============================================================
# TIMESTAMP SERVIDOR IQ
# ============================================================

def get_server_timestamp() -> Optional[int]:

    if IQ is None:
        return None

    try:

        timestamp = IQ.get_server_timestamp()

        if timestamp is None:
            return None

        return int(
            float(timestamp)
        )

    except Exception as exc:

        logger.warning(
            "Error timestamp servidor: %s",
            exc,
        )

        return None


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq() -> bool:

    global IQ
    global STREAMS_STARTED

    if not IQ_EMAIL:
        raise ValueError(
            "Falta IQ_EMAIL"
        )

    if not IQ_PASSWORD:
        raise ValueError(
            "Falta IQ_PASSWORD"
        )

    logger.info(
        "Conectando a IQ Option..."
    )

    IQ = IQ_Option(
        IQ_EMAIL,
        IQ_PASSWORD,
    )

    connected, reason = IQ.connect()

    if not connected:

        raise ConnectionError(
            f"No se pudo conectar: {reason}"
        )

    logger.info(
        "IQ Option conectado."
    )

    STREAMS_STARTED = False

    start_realtime_streams()

    server_ts = get_server_timestamp()

    logger.info(
        "Servidor IQ timestamp=%s",
        server_ts,
    )

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "Modo SNIPER N+1\n"
        "Binarias OTC\n"
        "Entrada al comenzar N+1."
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
# STREAMS
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

    for pair in PAIRS:

        try:

            IQ.start_candles_stream(
                pair,
                TIMEFRAME,
                5,
            )

            IQ.start_candles_stream(
                pair,
                MICRO_TIMEFRAME,
                20,
            )

            logger.info(
                "%s | streams 60s + 5s iniciados",
                pair,
            )

        except Exception as exc:

            logger.error(
                "%s | error iniciando streams: %s",
                pair,
                exc,
            )

    STREAMS_STARTED = True


# ============================================================
# DATAFRAME REALTIME
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
                        "from": int(
                            float(timestamp)
                        ),

                        "open": float(
                            candle["open"]
                        ),

                        "close": float(
                            candle["close"]
                        ),

                        "high": float(
                            candle.get(
                                "max",
                                candle.get(
                                    "high"
                                ),
                            )
                        ),

                        "low": float(
                            candle.get(
                                "min",
                                candle.get(
                                    "low"
                                ),
                            )
                        ),

                        "volume": float(
                            candle.get(
                                "volume",
                                0,
                            )
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
    pair: str,
) -> Optional[pd.DataFrame]:

    return realtime_dataframe(
        pair,
        TIMEFRAME,
    )


# ============================================================
# MICROVELAS 5S
# ============================================================

def get_5s_realtime(
    pair: str,
    minute_timestamp: int,
) -> Optional[pd.DataFrame]:

    df = realtime_dataframe(
        pair,
        MICRO_TIMEFRAME,
    )

    if df is None:
        return None

    start = int(
        minute_timestamp
    )

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
# VELA CERRADA
# ============================================================

def get_closed_1m(
    df: pd.DataFrame,
) -> Optional[pd.Series]:

    if df is None:
        return None

    if len(df) < 2:
        return None

    return df.iloc[-2]


# ============================================================
# CREAR SEÑAL PENDIENTE
# ============================================================

def create_pending_signal(
    pair: str,
    result: Dict[str, Any],
) -> None:

    signal = result.get(
        "signal"
    )

    if signal not in (
        "call",
        "put",
    ):
        return

    minute_ts = result.get(
        "minute_timestamp"
    )

    if minute_ts is None:
        return

    minute_ts = int(
        minute_ts
    )

    next_timestamp = (
        minute_ts + TIMEFRAME
    )

    existing = PENDING_ENTRY.get(
        pair
    )

    # Evitar duplicar la misma señal N.
    if existing is not None:

        if int(
            existing["minute_timestamp"]
        ) == minute_ts:

            return

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

    PENDING_ENTRY[pair] = {

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

        "created_at": time.time(),

        # Estado de ejecución
        "entry_notified": False,
        "attempts": 0,
        "last_attempt": 0.0,
        "last_rejection": None,
    }

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "🎯 SEÑAL CONFIRMADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N CERRADA\n"
        f"Timestamp: {minute_ts}\n"
        f"Apertura: {opening}\n"
        f"Cierre: {closing}\n\n"
        "PRIMERA 5S\n"
        f"Cierre: {first_5s_close}\n\n"
        "RETROCESOS 5S\n"
        f"Cantidad: {pullback_count}\n\n"
        "✅ PATRÓN CONFIRMADO\n"
        "🚫 N NO SE OPERA\n"
        "➡️ ENTRADA EXCLUSIVA EN N+1\n"
        f"N+1: {next_timestamp}"
    )

    logger.info(
        "%s | SEÑAL %s | N=%s | N+1=%s",
        pair,
        signal.upper(),
        minute_ts,
        next_timestamp,
    )


# ============================================================
# COMPRA BINARIA
# ============================================================

def buy_binary(
    pair: str,
    signal: str,
) -> tuple[bool, Optional[Any], Any]:

    if IQ is None:

        return (
            False,
            None,
            "IQ=None",
        )

    try:

        logger.info(
            "%s | ENVIANDO IQ.buy() | signal=%s | amount=%s",
            pair,
            signal.upper(),
            AMOUNT,
        )

        result = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION,
        )

        logger.info(
            "%s | RESPUESTA IQ.buy(): %r",
            pair,
            result,
        )

        # IQ Option normalmente devuelve:
        # (True, order_id)
        if isinstance(result, tuple):

            if len(result) >= 2:

                accepted = result[0]
                order_id = result[1]

                # NO convertir cualquier objeto extraño
                # a True. Solo aceptación explícita.
                ok = (
                    accepted is True
                    or accepted == 1
                    or str(accepted).lower() == "true"
                )

                return (
                    ok,
                    order_id,
                    result,
                )

            if len(result) == 1:

                accepted = result[0]

                ok = (
                    accepted is True
                    or accepted == 1
                    or str(accepted).lower() == "true"
                )

                return (
                    ok,
                    None,
                    result,
                )

        if result is True:

            return (
                True,
                None,
                result,
            )

        if result == 1:

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
            "%s | excepción IQ.buy()",
            pair,
        )

        return (
            False,
            None,
            str(exc),
        )


# ============================================================
# EJECUCIÓN N+1
# ============================================================

def execute_pending(
    pair: str,
) -> bool:
    """
    EJECUCIÓN CORREGIDA.

    La señal se crea cuando N termina.

    La orden se envía directamente al comenzar N+1.

    Si IQ Option rechaza temporalmente la orden:
        - NO se elimina la señal.
        - NO se marca como ejecutada.
        - NO se cambia CALL/PUT.
        - Se vuelve a llamar IQ.buy().
    
    La señal solo desaparece cuando IQ.buy() confirma
    explícitamente que la operación fue aceptada.
    """

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    if IQ is None:
        return False

    server_ts = get_server_timestamp()

    if server_ts is None:
        return False

    server_ts = int(
        server_ts
    )

    n_timestamp = int(
        pending["minute_timestamp"]
    )

    n1_timestamp = int(
        pending["next_timestamp"]
    )

    # ========================================================
    # TODAVÍA ESTAMOS EN N
    # ========================================================

    if server_ts < n1_timestamp:

        return False

    # ========================================================
    # YA SE EJECUTÓ ESTA N+1
    # ========================================================

    if LAST_TRADE_CANDLE.get(pair) == n1_timestamp:

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return True

    # ========================================================
    # VERIFICAR QUE NO HAYA EXPIRADO LA VENTANA
    # ========================================================

    elapsed = (
        server_ts - n1_timestamp
    )

    if elapsed > MAX_ENTRY_DELAY:

        logger.error(
            "%s | ❌ VENTANA N+1 AGOTADA | "
            "N+1=%s | servidor=%s | intentos=%s | "
            "último rechazo=%r",
            pair,
            n1_timestamp,
            server_ts,
            pending.get("attempts", 0),
            pending.get("last_rejection"),
        )

        telegram_send(
            "❌ ENTRADA NO EJECUTADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {pending['signal'].upper()}\n"
            f"N+1: {n1_timestamp}\n\n"
            "Se agotó la ventana de ejecución.\n\n"
            f"Última respuesta IQ:\n"
            f"{pending.get('last_rejection')}"
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    signal = pending["signal"]

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    second_n1 = (
        server_ts % TIMEFRAME
    )

    # ========================================================
    # AVISO N+1
    # ========================================================

    if not pending.get(
        "entry_notified",
        False,
    ):

        pending["entry_notified"] = True

        logger.info(
            "%s | ⚡ N+1 DETECTADA | "
            "server=%s | segundo=%s | "
            "N=%s | N+1=%s",
            pair,
            server_ts,
            second_n1,
            n_timestamp,
            n1_timestamp,
        )

        telegram_send(
            "⚡ N+1 DETECTADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {direction}\n\n"
            f"Servidor IQ: {server_ts}\n"
            f"Segundo N+1: {second_n1}\n\n"
            f"Timestamp N: {n_timestamp}\n"
            f"Timestamp N+1: {n1_timestamp}\n\n"
            "🎯 ENVIANDO ORDEN A IQ OPTION"
        )

    # ========================================================
    # CONTROL DE VELOCIDAD DE REINTENTO
    # ========================================================

    now = time.monotonic()

    last_attempt = float(
        pending.get(
            "last_attempt_monotonic",
            0.0,
        )
    )

    if (
        last_attempt > 0
        and (
            now - last_attempt
        ) < BUY_RETRY_INTERVAL
    ):

        return False

    pending[
        "last_attempt_monotonic"
    ] = now

    pending["last_attempt"] = time.time()

    pending["attempts"] = int(
        pending.get(
            "attempts",
            0,
        )
    ) + 1

    attempt = pending[
        "attempts"
    ]

    logger.info(
        "%s | ⚡ IQ.buy() INTENTO #%s | "
        "%s | N+1=%s | segundo=%s",
        pair,
        attempt,
        signal.upper(),
        n1_timestamp,
        second_n1,
    )

    # ========================================================
    # ENVIAR ORDEN
    # ========================================================

    ok, order_id, raw_result = buy_binary(
        pair,
        signal,
    )

    # ========================================================
    # IQ RECHAZÓ
    # ========================================================

    if not ok:

        pending[
            "last_rejection"
        ] = raw_result

        logger.warning(
            "%s | ❌ IQ.buy() RECHAZADA | "
            "intento=%s | signal=%s | "
            "N+1=%s | servidor=%s | respuesta=%r",
            pair,
            attempt,
            signal.upper(),
            n1_timestamp,
            server_ts,
            raw_result,
        )

        # IMPORTANTE:
        # NO eliminar PENDING_ENTRY.
        # NO cambiar LAST_TRADE_CANDLE.
        # NO considerar ejecutada.
        #
        # El siguiente ciclo volverá a intentar.

        if attempt == 1:

            telegram_send(
                "⚠️ IQ OPTION RECHAZÓ EL PRIMER INTENTO\n\n"
                f"Par: {pair}\n"
                f"Dirección: {signal.upper()}\n"
                f"N+1: {n1_timestamp}\n\n"
                "🔄 SE REINTENTARÁ AUTOMÁTICAMENTE\n\n"
                f"Respuesta IQ:\n{raw_result}"
            )

        return False

    # ========================================================
    # IQ ACEPTÓ LA ORDEN
    # ========================================================

    LAST_TRADE_CANDLE[
        pair
    ] = n1_timestamp

    telegram_send(
        "✅ OPERACIÓN ACEPTADA POR IQ OPTION\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "VELA N\n"
        f"Timestamp: {n_timestamp}\n"
        f"Apertura: {pending['minute_open']}\n"
        f"Cierre: {pending['minute_close']}\n\n"
        "➡️ ENTRADA N+1\n"
        f"Timestamp: {n1_timestamp}\n\n"
        f"💵 Importe: ${AMOUNT}\n"
        "⏱ Expiración: 1 minuto\n"
        f"🆔 ID: {order_id}\n"
        f"🔁 Intentos: {attempt}"
    )

    logger.info(
        "%s | ✅ OPERACIÓN ACEPTADA | "
        "%s | N=%s | N+1=%s | "
        "ID=%s | intentos=%s",
        pair,
        signal.upper(),
        n_timestamp,
        n1_timestamp,
        order_id,
        attempt,
    )

    # SOLO AHORA eliminamos la señal pendiente.
    PENDING_ENTRY.pop(
        pair,
        None,
    )

    return True


# ============================================================
# PROCESAR UN PAR
# ============================================================

def process_pair(
    pair: str,
) -> None:

    # ========================================================
    # PRIMERO: ejecutar cualquier señal pendiente
    # ========================================================

    if pair in PENDING_ENTRY:

        execute_pending(
            pair
        )

    # ========================================================
    # OBTENER 1M
    # ========================================================

    df_1m = get_1m_realtime(
        pair
    )

    if df_1m is None:
        return

    if len(df_1m) < 2:
        return

    server_ts = get_server_timestamp()

    if server_ts is None:
        return

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

    # ========================================================
    # NO ANALIZAR LA MISMA N DOS VECES
    # ========================================================

    if (
        LAST_PROCESSED_MINUTE.get(pair)
        == closed_ts
    ):

        return

    # ========================================================
    # OBTENER 5S DE N
    # ========================================================

    candles_5s = get_5s_realtime(
        pair,
        closed_ts,
    )

    if candles_5s is None:

        logger.warning(
            "%s | no hay 5S para N=%s",
            pair,
            closed_ts,
        )

        return

    if len(candles_5s) < MICRO_CANDLE_COUNT:

        logger.warning(
            "%s | 5S insuficientes | "
            "N=%s | %s/%s",
            pair,
            closed_ts,
            len(candles_5s),
            MICRO_CANDLE_COUNT,
        )

        return

    # Marcar N como analizada.
    LAST_PROCESSED_MINUTE[
        pair
    ] = closed_ts

    # ========================================================
    # ANALIZAR N
    # ========================================================

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
        "%s | N=%s | "
        "signal=%s | reason=%s",
        pair,
        closed_ts,
        signal,
        reason,
    )

    # ========================================================
    # SEÑAL CONFIRMADA
    # ========================================================

    if signal in (
        "call",
        "put",
    ):

        create_pending_signal(
            pair,
            result,
        )

        # ====================================================
        # INTENTO INMEDIATO
        #
        # Si N ya cerró y el servidor está en N+1,
        # aquí se envía directamente IQ.buy().
        # ====================================================

        execute_pending(
            pair
        )

    else:

        logger.info(
            "%s | N=%s | SIN SEÑAL | %s",
            pair,
            closed_ts,
            reason,
        )


# ============================================================
# TODOS LOS PARES
# ============================================================

def analyze_all_pairs() -> None:

    if not BOT_RUNNING:
        return

    for pair in PAIRS:

        if not BOT_RUNNING:
            return

        try:

            process_pair(
                pair
            )

        except Exception:

            logger.exception(
                "%s | error procesando par",
                pair,
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
        "BOT IQ OPTION BINARIAS OTC"
    )

    logger.info(
        "MODO SNIPER N+1"
    )

    logger.info(
        "ESTRATEGIA 1M + MICROVELAS 5S"
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
        "REINTENTO IQ.buy(): %.2fs",
        BUY_RETRY_INTERVAL,
    )

    logger.info(
        "VENTANA N+1: %.2fs",
        MAX_ENTRY_DELAY,
    )

    logger.info(
        "=========================================="
    )

    required = {

        "IQ_EMAIL":
            IQ_EMAIL,

        "IQ_PASSWORD":
            IQ_PASSWORD,

        "TELEGRAM_TOKEN":
            TELEGRAM_TOKEN,

        "TELEGRAM_CHAT_ID":
            TELEGRAM_CHAT_ID,
    }

    missing = [
        key
        for key, value
        in required.items()
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
        "BINARIAS OTC\n"
        "MODO SNIPER N+1\n\n"
        "ESTRATEGIA:\n"
        "1M + 5S\n\n"
        "CALL:\n"
        "🟢 Primera 5S > apertura 1M\n"
        "🔴 Retroceso 5S < apertura 1M\n"
        "🟢 Cierre 1M verde\n\n"
        "PUT:\n"
        "🔴 Primera 5S < apertura 1M\n"
        "🟢 Retroceso 5S > apertura 1M\n"
        "🔴 Cierre 1M rojo\n\n"
        "🎯 Entrada SOLO en N+1\n"
        "⚡ IQ.buy() directo\n"
        "🔄 Reintento automático ante rechazo temporal\n"
        "🕐 Reloj IQ Option\n"
        f"💵 ${AMOUNT}\n"
        "⏱ 1 minuto\n"
        f"📌 Par: {', '.join(PAIRS)}"
    )

    while True:

        try:

            if not BOT_RUNNING:

                time.sleep(
                    0.20
                )

                continue

            if not ensure_connection():

                time.sleep(
                    1
                )

                continue

            # =================================================
            # PROCESAMIENTO CONTINUO
            # =================================================

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

            time.sleep(
                0.5
            )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
