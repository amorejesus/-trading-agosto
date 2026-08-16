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
    "GBPUSD-OTC",
    "EURJPY-OTC",
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
# LOOP SNIPER
# ============================================================

# Poll muy rápido para detectar el cambio de vela.
POLL_INTERVAL = 0.03

# No se permite ejecutar una señal atrasada.
MAX_ENTRY_DELAY = 5.0


# ============================================================
# TELEGRAM
# ============================================================

# Telegram NO debe bloquear el loop de trading.
TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 0.5


# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None

LAST_TELEGRAM_CHECK = 0.0


# Última vela N cerrada analizada.
LAST_PROCESSED_MINUTE: Dict[str, int] = {}


# Señal pendiente para N+1.
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}


# Última vela donde realmente se abrió operación.
LAST_TRADE_CANDLE: Dict[str, int] = {}


# Control de streams.
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
# TELEGRAM EN HILO SEPARADO
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

                # ============================================
                # START
                # ============================================

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
                        "🎯 SNIPER N+1\n"
                        "Entrada inmediatamente al comenzar N+1."
                    )

                    logger.info(
                        "BOT ACTIVADO"
                    )

                # ============================================
                # STOP
                # ============================================

                elif text == "/stop":

                    BOT_RUNNING = False

                    telegram_send(
                        "🔴 BOT DETENIDO\n\n"
                        "No se abrirán nuevas operaciones."
                    )

                    logger.info(
                        "BOT DETENIDO"
                    )

                # ============================================
                # STATUS
                # ============================================

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
                        "Modo: SNIPER\n"
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
# SERVIDOR IQ OPTION
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
        "Modo SNIPER\n"
        "Binarias OTC\n"
        "Entrada inmediata en N+1."
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
            "🟢 IQ OPTION RECONectado"
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

    for pair in PAIRS:

        try:

            # ------------------------------------------------
            # VELA 1 MINUTO
            # ------------------------------------------------

            IQ.start_candles_stream(
                pair,
                TIMEFRAME,
                5,
            )

            # ------------------------------------------------
            # MICROVELAS 5 SEGUNDOS
            # ------------------------------------------------

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

        df = pd.DataFrame(
            rows
        )

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
# OBTENER VELA VIVA
# ============================================================

def get_live_1m(
    df: pd.DataFrame,
) -> Optional[pd.Series]:

    if df is None:
        return None

    if df.empty:
        return None

    return df.iloc[-1]


# ============================================================
# OBTENER VELA CERRADA
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

    # --------------------------------------------------------
    # N+1 OBLIGATORIA
    # --------------------------------------------------------

    next_timestamp = (
        minute_ts + TIMEFRAME
    )

    # --------------------------------------------------------
    # EVITAR DUPLICADO
    # --------------------------------------------------------

    existing = PENDING_ENTRY.get(
        pair
    )

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
        return False, None, "IQ=None"

    try:

        # ====================================================
        # IMPORTANTE:
        #
        # Para BINARIAS:
        #
        # IQ.buy()
        #
        # NO buy_digital_spot()
        # ====================================================

        result = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION,
        )

        # La API normalmente devuelve:
        #
        # (True, order_id)
        #
        # o
        #
        # (False, reason)

        if isinstance(
            result,
            tuple,
        ):

            if len(result) >= 2:

                ok = bool(
                    result[0]
                )

                order_id = result[1]

                return (
                    ok,
                    order_id,
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
            pair,
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
    pair: str,
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    # --------------------------------------------------------
    # SERVIDOR IQ OPTION
    # --------------------------------------------------------

    server_ts = get_server_timestamp()

    if server_ts is None:
        return False

    current_minute = (
        int(server_ts)
        // TIMEFRAME
    ) * TIMEFRAME

    n_timestamp = int(
        pending[
            "minute_timestamp"
        ]
    )

    n1_timestamp = int(
        pending[
            "next_timestamp"
        ]
    )

    # ========================================================
    # N TODAVÍA VIVA
    # ========================================================

    if current_minute < n1_timestamp:

        return False

    # ========================================================
    # N+1 EXACTAMENTE
    # ========================================================

    if current_minute == n1_timestamp:

        pass

    # ========================================================
    # N+2 O MÁS
    #
    # SE CANCELA.
    #
    # NUNCA EJECUTAR TARDE.
    # ========================================================

    elif current_minute > n1_timestamp:

        logger.warning(
            "%s | señal perdida | "
            "N=%s | N+1=%s | actual=%s",
            pair,
            n_timestamp,
            n1_timestamp,
            current_minute,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N: {n_timestamp}\n"
            f"N+1: {n1_timestamp}\n"
            f"Minuto actual: {current_minute}\n\n"
            "La ventana N+1 terminó.\n"
            "🚫 No se ejecuta en N+2."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # OBTENER VELA 1M EN TIEMPO REAL
    # ========================================================

    df = get_1m_realtime(
        pair
    )

    if df is None:
        return False

    if df.empty:
        return False

    live_candle = get_live_1m(
        df
    )

    if live_candle is None:
        return False

    try:

        live_timestamp = int(
            live_candle["from"]
        )

        execution_open = float(
            live_candle["open"]
        )

    except Exception:

        return False

    # ========================================================
    # SEGURIDAD ABSOLUTA
    #
    # La vela realtime tiene que ser N+1.
    # ========================================================

    if live_timestamp != n1_timestamp:

        logger.debug(
            "%s | servidor está en N+1 "
            "pero stream aún no muestra N+1 | "
            "server=%s | stream=%s | esperado=%s",
            pair,
            server_ts,
            live_timestamp,
            n1_timestamp,
        )

        return False

    # ========================================================
    # EVITAR DUPLICADO
    # ========================================================

    if (
        LAST_TRADE_CANDLE.get(pair)
        == n1_timestamp
    ):

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    signal = pending[
        "signal"
    ]

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    # ========================================================
    # SNIPER
    # ========================================================

    server_second = (
        int(server_ts)
        % TIMEFRAME
    )

    logger.info(
        "%s | ⚡ SNIPER N+1 | "
        "server=%s | segundo=%s | "
        "N=%s | N+1=%s | OPEN=%s",
        pair,
        server_ts,
        server_second,
        n_timestamp,
        n1_timestamp,
        execution_open,
    )

    telegram_send(
        "⚡ N+1 DETECTADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        f"Servidor IQ: {server_ts}\n"
        f"Segundo: {server_second}\n\n"
        f"Timestamp N: {n_timestamp}\n"
        f"Timestamp N+1: {n1_timestamp}\n\n"
        f"Apertura REAL N+1: {execution_open}\n\n"
        "🎯 EJECUTANDO BINARIA"
    )

    # ========================================================
    # EJECUTAR
    # ========================================================

    ok, order_id, raw_result = buy_binary(
        pair,
        signal,
    )

    if not ok:

        logger.error(
            "%s | ❌ BINARIA RECHAZADA | "
            "signal=%s | N=%s | N+1=%s | "
            "server=%s | result=%s",
            pair,
            signal.upper(),
            n_timestamp,
            n1_timestamp,
            server_ts,
            raw_result,
        )

        telegram_send(
            "❌ BINARIA RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"N: {n_timestamp}\n"
            f"N+1: {n1_timestamp}\n"
            f"Servidor: {server_ts}\n"
            f"Apertura N+1: {execution_open}\n\n"
            f"Respuesta IQ:\n{raw_result}"
        )

        # ----------------------------------------------------
        # NO VOLVER A INTENTAR EN N+2
        # ----------------------------------------------------

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # OPERACIÓN ACEPTADA
    # ========================================================

    LAST_TRADE_CANDLE[
        pair
    ] = n1_timestamp

    PENDING_ENTRY.pop(
        pair,
        None,
    )

    telegram_send(
        "✅ OPERACIÓN ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "VELA N\n"
        f"Timestamp: {n_timestamp}\n"
        f"Apertura: "
        f"{pending['minute_open']}\n"
        f"Cierre: "
        f"{pending['minute_close']}\n\n"
        "VELA N+1\n"
        f"Timestamp: {n1_timestamp}\n"
        f"Apertura REAL: {execution_open}\n\n"
        f"💵 Importe: ${AMOUNT}\n"
        "⏱ Expiración: 1 minuto\n"
        f"🆔 ID: {order_id}"
    )

    logger.info(
        "%s | ✅ BINARIA ABIERTA | "
        "%s | N=%s | N+1=%s | "
        "OPEN=%s | ID=%s",
        pair,
        signal.upper(),
        n_timestamp,
        n1_timestamp,
        execution_open,
        order_id,
    )

    return True


# ============================================================
# PROCESAR UN PAR
# ============================================================

def process_pair(
    pair: str,
) -> None:

    # ========================================================
    # 1. PRIMERO:
    #    intentar ejecutar una señal pendiente.
    #
    # Esto va ANTES del análisis nuevo.
    # ========================================================

    if pair in PENDING_ENTRY:

        execute_pending(
            pair
        )

    # ========================================================
    # 2. OBTENER 1M REALTIME
    # ========================================================

    df_1m = get_1m_realtime(
        pair
    )

    if df_1m is None:
        return

    if len(df_1m) < 2:
        return

    # ========================================================
    # 3. SERVIDOR IQ
    # ========================================================

    server_ts = get_server_timestamp()

    if server_ts is None:
        return

    current_minute = (
        int(server_ts)
        // TIMEFRAME
    ) * TIMEFRAME

    # ========================================================
    # 4. VELA CERRADA
    # ========================================================

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

    # ========================================================
    # SEGURIDAD:
    #
    # La vela cerrada debe ser anterior al
    # minuto que el servidor considera actual.
    # ========================================================

    if closed_ts >= current_minute:

        return

    # ========================================================
    # 5. EVITAR REPETICIÓN
    # ========================================================

    if (
        LAST_PROCESSED_MINUTE.get(pair)
        == closed_ts
    ):

        return

    # ========================================================
    # 6. OBTENER 5S DEL MINUTO CERRADO
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

    # ========================================================
    # 12 MICROVELAS
    # ========================================================

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

    # ========================================================
    # MARCAR COMO PROCESADA
    # ========================================================

    LAST_PROCESSED_MINUTE[
        pair
    ] = closed_ts

    # ========================================================
    # 7. ANALIZAR ESTRATEGIA
    # ========================================================

    result = analyze_market(
        closed_candle,
        candles_5s,
    )

    # Asegurar timestamp correcto.
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
    # 8. GUARDAR SEÑAL PARA N+1
    # ========================================================

    if signal in (
        "call",
        "put",
    ):

        create_pending_signal(
            pair,
            result,
        )

    else:

        logger.info(
            "%s | N=%s | SIN SEÑAL | %s",
            pair,
            closed_ts,
            reason,
        )


# ============================================================
# PROCESAR TODOS LOS PARES
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
        "=========================================="
    )

    # ========================================================
    # VARIABLES
    # ========================================================

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

    # ========================================================
    # CONEXIÓN
    # ========================================================

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

    # ========================================================
    # TELEGRAM WORKER
    # ========================================================

    telegram_thread = threading.Thread(
        target=telegram_worker,
        daemon=True,
    )

    telegram_thread.start()

    # ========================================================
    # BOT LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "BINARIAS OTC\n"
        "MODO SNIPER\n\n"
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
        "⚡ Sin espera artificial\n"
        "🕐 Reloj sincronizado con IQ Option\n"
        "💵 $10\n"
        "⏱ 1 minuto"
    )

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    while True:

        try:

            if not BOT_RUNNING:

                time.sleep(
                    0.20
                )

                continue

            # =================================================
            # IQ
            # =================================================

            if not ensure_connection():

                time.sleep(
                    1
                )

                continue

            # =================================================
            # TRADING PRIMERO
            #
            # NO Telegram aquí.
            #
            # El hilo de Telegram trabaja separado.
            # =================================================

            analyze_all_pairs()

            # =================================================
            # LOOP SNIPER
            # =================================================

            time.sleep(
                POLL_INTERVAL
            )

        # ====================================================
        # CTRL+C
        # ====================================================

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            logger.info(
                "Bot detenido."
            )

            break

        # ====================================================
        # ERROR GENERAL
        # ====================================================

        except Exception as exc:

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
