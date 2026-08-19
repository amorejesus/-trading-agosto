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
    "AUDUSD-OTC",
    "CADJPY-OTC",
]


# ============================================================
# TEMPORALIDADES
# ============================================================

TIMEFRAME = 60
CANDLE_COUNT = 60


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 30
EXPIRATION = 1


# ============================================================
# LOOP SNIPER
# ============================================================

POLL_INTERVAL = 0.05
MAX_ENTRY_DELAY = 0.0


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

LAST_TELEGRAM_CHECK = 0.0

LAST_PROCESSED_MINUTE: Dict[str, int] = {}

LAST_LIVE_M1: Dict[str, Dict[str, Any]] = {}

LAST_CLOSED_M1: Dict[str, Dict[str, Any]] = {}

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

                if text == "/start":

                    BOT_RUNNING = True

                    telegram_send(
                        "🟢 BOT ACTIVADO\n\n"
                        "ESTRATEGIA 2 MINUTOS\n\n"
                        "N inicia → recopilar datos → N cierra\n"
                        "analizar N → decidir CALL/PUT → N+1\n\n"
                        "🎯 SNIPER N+1 POR RETROCESO\n"
                        "CALL: precio < apertura N+1\n"
                        "PUT: precio > apertura N+1\n"
                        "Entrada dentro de N+1 cuando se cumple el disparador."
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
                        "Modo: SNIPER\n"
                        "Principal: M1 completa\n"
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
        "Entrada en N+1 únicamente cuando el precio está contra la operación."
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

            IQ.start_candles_stream(
                pair,
                TIMEFRAME,
                10,
            )

            IQ.start_candles_stream(
                pair,
                60,
                20,
            )

            logger.info(
                "%s | stream 60s + 60s iniciado",
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


def get_intrabar_1m(
    pair: str,
) -> Optional[pd.DataFrame]:

    # Estas velas de 1 minuto se usan solo para describir
    # los movimientos internos de la vela N de 2 minutos.
    return realtime_dataframe(
        pair,
        60,
    )


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
    expected_timestamp: Optional[int] = None,
) -> Optional[pd.Series]:

    if df is None or df.empty:
        return None

    if "from" not in df.columns:
        return None

    if expected_timestamp is not None:
        try:
            expected_timestamp = int(expected_timestamp)
            matches = df[
                df["from"].astype(int) == expected_timestamp
            ]
            if matches.empty:
                return None
            return matches.iloc[-1]
        except (TypeError, ValueError):
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

    PENDING_ENTRY[pair] = {

        "signal": signal,

        "minute_timestamp": minute_ts,

        "next_timestamp": next_timestamp,

        "minute_open": opening,

        "minute_close": closing,

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
        "ANÁLISIS DE N CERRADA\n"
        f"Estado: {result.get('state')}\n"
        f"Dirección: {result.get('direction')}\n"
        f"Cuerpo: {result.get('body')}\n"
        f"Mecha superior: {result.get('upper_wick')}\n"
        f"Mecha inferior: {result.get('lower_wick')}\n"
        f"Posición cierre: {result.get('close_position')}\n"
        f"Movimiento interno N: {result.get('intrabar', {}).get('path')}\n"
        f"EMA9: {result.get('indicators', {}).get('ema_fast')}\n"
        f"EMA21: {result.get('indicators', {}).get('ema_slow')}\n"
        f"RSI14: {result.get('indicators', {}).get('rsi')}\n\n"
        "✅ SEÑAL CONFIRMADA\n"
        "🚫 N NO SE OPERA\n"
        "➡️ ENTRADA EXCLUSIVA EN N+1\n"
        "🎯 Sniper: CALL si precio < apertura N+1; PUT si precio > apertura N+1\n"
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

        result = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION,
        )

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
# EJECUCIÓN SNIPER N+1 POR RETROCESO DE PRECIO
# ============================================================

def execute_pending(
    pair: str,
) -> bool:
    """
    Ejecuta la señal calculada al cierre de N exclusivamente en N+1.

    La dirección ya fue determinada con N cerrada:
    - N completa se analiza.
    - CALL/PUT queda fijado.
    - N+1 solo es la vela de ejecución.
    - Ningún dato de N+1 cambia la dirección.
    """

    pending = PENDING_ENTRY.get(pair)

    if pending is None:
        return False

    server_ts = get_server_timestamp()
    if server_ts is None:
        return False

    server_ts = int(server_ts)

    n_timestamp = int(pending["minute_timestamp"])
    n1_timestamp = int(pending["next_timestamp"])

    current_candle = (
        server_ts // TIMEFRAME
    ) * TIMEFRAME

    # Esperar hasta el comienzo exacto de N+1.
    if current_candle < n1_timestamp:
        return False

    # Si N+1 ya terminó, la señal se cancela y no pasa a N+2.
    if current_candle > n1_timestamp:
        logger.info(
            "%s | SEÑAL CANCELADA | N+1 terminó sin ejecución | "
            "N=%s | N+1=%s",
            pair,
            n_timestamp,
            n1_timestamp,
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    if LAST_TRADE_CANDLE.get(pair) == n1_timestamp:
        PENDING_ENTRY.pop(pair, None)
        return False

    signal = pending["signal"]

    if signal not in ("call", "put"):
        PENDING_ENTRY.pop(pair, None)
        return False

    # La entrada se hace en N+1. No se usa el precio de N+1
    # para cambiar la dirección calculada.
    logger.info(
        "%s | 🚀 EJECUTANDO N+1 | signal=%s | N=%s | N+1=%s",
        pair,
        signal.upper(),
        n_timestamp,
        n1_timestamp,
    )

    telegram_send(
        "🚀 EJECUTANDO SEÑAL N+1\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"N cerrada: {n_timestamp}\n"
        f"N+1 apertura: {n1_timestamp}\n\n"
        "La dirección fue calculada exclusivamente con N cerrada.\n"
        "N+1 no participa en la decisión.\n\n"
        "🎯 EJECUTANDO BINARIA"
    )

    ok, order_id, raw_result = buy_binary(
        pair,
        signal,
    )

    if not ok:
        # Mantener la señal pendiente si IQ Option rechaza el primer intento.
        # Esto permite reintentar dentro de la misma N+1 si el activo tarda
        # unos instantes en quedar disponible. La dirección sigue siendo la
        # calculada exclusivamente con N cerrada.
        logger.warning(
            "%s | BINARIA NO EJECUTADA TODAVÍA | "
            "signal=%s | N=%s | N+1=%s | result=%s",
            pair,
            signal.upper(),
            n_timestamp,
            n1_timestamp,
            raw_result,
        )

        # NO eliminar PENDING_ENTRY aquí.
        # El siguiente ciclo vuelve a intentar mientras N+1 siga abierta.
        return False

    LAST_TRADE_CANDLE[pair] = n1_timestamp
    PENDING_ENTRY.pop(pair, None)

    telegram_send(
        "✅ OPERACIÓN ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "ANÁLISIS DE N CERRADA\n"
        f"Timestamp N: {n_timestamp}\n"
        f"Apertura N: {pending['minute_open']}\n"
        f"Cierre N: {pending['minute_close']}\n\n"
        "ENTRADA N+1\n"
        f"Timestamp N+1: {n1_timestamp}\n\n"
        f"💵 Importe: ${AMOUNT}\n"
        "⏱ Expiración: 1 minuto\n"
        f"🆔 ID: {order_id}"
    )

    logger.info(
        "%s | ✅ BINARIA ABIERTA | %s | N=%s | N+1=%s | ID=%s",
        pair,
        signal.upper(),
        n_timestamp,
        n1_timestamp,
        order_id,
    )

    return True


# ============================================================
# PROCESAR UN PAR
# ============================================================
# PROCESAR UN PAR
# ============================================================

def process_pair(
    pair: str,
) -> None:
    """Flujo estricto N -> cierre -> decisión -> N+1.

    La vela de 1 minuto se va observando durante toda su duración y se guarda
    localmente en LAST_LIVE_M1. Al cambiar el minuto, la vela que
    estaba viva pasa a ser N cerrada y se analiza una sola vez.
    No se consultan microvelas ni se exige ninguna cantidad de datos 5S.
    """

    # Primero se atiende cualquier señal ya confirmada para ejecutar
    # exclusivamente en N+1.
    if pair in PENDING_ENTRY:
        execute_pending(pair)

    server_ts = get_server_timestamp()
    if server_ts is None:
        return

    server_ts = int(server_ts)
    current_minute = (server_ts // TIMEFRAME) * TIMEFRAME

    # Leer únicamente el stream stream de 2 minutos ya abierto. No hacemos una
    # petición histórica al llegar al cierre.
    df_1m = get_1m_realtime(pair)
    if df_1m is not None and not df_1m.empty:
        live_candle = get_live_1m(df_1m)
        if live_candle is not None:
            try:
                live_ts = int(float(live_candle["from"]))
            except (TypeError, ValueError, KeyError):
                live_ts = None

            if live_ts == current_minute:
                previous_live = LAST_LIVE_M1.get(pair)
                if previous_live is not None:
                    try:
                        previous_ts = int(float(previous_live.get("from")))
                    except (TypeError, ValueError):
                        previous_ts = None
                    if previous_ts is not None and previous_ts < live_ts:
                        LAST_CLOSED_M1[pair] = previous_live

                LAST_LIVE_M1[pair] = live_candle.to_dict()

    # Antes del cambio de minuto solo se recopila N.
    closed_timestamp = current_minute - TIMEFRAME

    if LAST_PROCESSED_MINUTE.get(pair) == closed_timestamp:
        return

    cached = LAST_CLOSED_M1.get(pair)

    # Si el stream todavía no publicó N+1, el último snapshot de
    # N ya quedó cerrado por el reloj y se usa como N final.
    if cached is None:
        live = LAST_LIVE_M1.get(pair)
        if live is not None:
            try:
                live_ts = int(float(live.get("from")))
            except (TypeError, ValueError):
                live_ts = None
            if live_ts == closed_timestamp:
                cached = live

    if not cached:
        return

    try:
        cached_ts = int(float(cached.get("from")))
    except (TypeError, ValueError):
        return

    if cached_ts != closed_timestamp:
        return

    closed_candle = pd.Series(cached)

    # Guardia crítica: nunca analizar una vela anterior ni N+1.
    if int(float(closed_candle["from"])) != closed_timestamp:
        return

    LAST_PROCESSED_MINUTE[pair] = closed_timestamp

    # Datos internos de N: solo las velas 1M que pertenecen al
    # intervalo de N. Nunca se entrega N+1 a la estrategia.
    intrabar_1m = get_intrabar_1m(pair)

    if intrabar_1m is not None and not intrabar_1m.empty:
        intrabar_1m = intrabar_1m[
            (intrabar_1m["from"].astype(int) >= closed_timestamp)
            & (
                intrabar_1m["from"].astype(int)
                < closed_timestamp + TIMEFRAME
            )
        ].copy()

    # El historial para indicadores/estructura usa velas 1M
    # anteriores a N; N+1 nunca entra en este análisis.
    previous_m1 = get_intrabar_1m(pair)
    if previous_m1 is not None and not previous_m1.empty:
        previous_m1 = previous_m1[
            previous_m1["from"].astype(int) < closed_timestamp
        ].copy()

    result = analyze_market(
        closed_candle,
        None,
        previous_m1,
        intrabar_1m,
    )

    result["minute_timestamp"] = closed_timestamp
    result["minute_open"] = float(closed_candle["open"])
    result["minute_close"] = float(closed_candle["close"])

    signal = result.get("signal")
    reason = result.get("reason", "")

    logger.info(
        "%s | N CERRADA=%s | signal=%s | reason=%s",
        pair,
        closed_timestamp,
        signal,
        reason,
    )

    if signal in ("call", "put"):
        create_pending_signal(pair, result)
    else:
        logger.info(
            "%s | N=%s | SIN SEÑAL | %s",
            pair,
            closed_timestamp,
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
        "MODO N+1 SEGÚN ANÁLISIS COMPLETO DE N"
    )

    logger.info(
        "ESTRATEGIA 2 MINUTOS"
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
        "MODO SNIPER\n\n"
        "ESTRATEGIA:\n"
        "M1 COMPLETA\n\n"
        "N inicia → recopilar datos → N cierra\n"
        "analizar N → decidir CALL/PUT → N+1\n\n"
        "🎯 Entrada SOLO en N+1\n"
        "🎯 CALL: precio < apertura N+1\n"
        "🎯 PUT: precio > apertura N+1\n"
        "🕐 Reloj sincronizado con IQ Option\n"
        "💵 $30\n"
        "⏱ 1 minuto"
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
