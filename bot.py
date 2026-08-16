from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import pandas as pd
import requests
from iqoptionapi.stable_api import IQ_Option

from strategy import analyze_market


# ============================================================
# CONFIG
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
# TRADING
# ============================================================

TIMEFRAME = 60

EXPIRATION = 1

AMOUNT = 10

CANDLE_COUNT = 60


# ============================================================
# LOOP
# ============================================================

# Poll rápido para detectar cambio de vela.
POLL_INTERVAL = 0.08


# Tiempo máximo para esperar a que IQ Option
# entregue la nueva vela.
OPEN_RETRY_WINDOW = 4.0


# Ventana exacta de ejecución.
ENTRY_MIN_SECOND = 1.0
ENTRY_MAX_SECOND = 3.0


# Evita operaciones demasiado próximas
# en el mismo par.
TRADE_COOLDOWN = 60.0


# ============================================================
# ESTADO GLOBAL
# ============================================================

BOT_RUNNING = False

LAST_UPDATE_ID: Optional[int] = None

IQ: Optional[IQ_Option] = None


# Estado de la vela actualmente viva.
LIVE_STATE: Dict[
    str,
    Dict[str, Any],
] = {}


# Señales confirmadas en N que esperan N+1.
PENDING_ENTRY: Dict[
    str,
    Dict[str, Any],
] = {}


# Último momento en que se abrió una operación.
LAST_TRADE_TIME: Dict[
    str,
    float,
] = {}


# Timestamp de la última vela operada.
LAST_TRADE_CANDLE: Dict[
    str,
    int,
] = {}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(
    message: str,
) -> bool:

    if (
        not TELEGRAM_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
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
            timeout=(1, 2),
        )

        if response.status_code != 200:

            logger.error(
                "Telegram %s: %s",
                response.status_code,
                response.text,
            )

            return False

        return True

    except Exception as exc:

        # Telegram nunca debe tumbar el bot.
        logger.warning(
            "Telegram no disponible: %s",
            exc,
        )

        return False


def check_commands() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/getUpdates"
    )

    params = {
        "timeout": 0,
    }

    if LAST_UPDATE_ID is not None:

        params["offset"] = (
            LAST_UPDATE_ID + 1
        )

    try:

        response = requests.get(
            url,
            params=params,
            timeout=(1, 2),
        )

        data = response.json()

        if not data.get("ok"):
            return

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

            # ------------------------------------------------
            # START
            # ------------------------------------------------

            if text == "/start":

                BOT_RUNNING = True

                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "DIGITAL OTC\n"
                    "EURUSD-OTC\n"
                    "GBPUSD-OTC\n"
                    "EURJPY-OTC\n\n"
                    "⏱ Temporalidad: 1 minuto\n"
                    "💵 Importe: $10\n"
                    "⏱ Expiración: 1 minuto\n\n"
                    "La vela N se analiza completa.\n"
                    "🚫 N nunca se opera.\n"
                    "➡️ La señal pertenece a N+1.\n"
                    "🎯 Entrada: segundos 01–03."
                )

            # ------------------------------------------------
            # STOP
            # ------------------------------------------------

            elif text == "/stop":

                BOT_RUNNING = False

                telegram_send(
                    "🔴 BOT DETENIDO\n\n"
                    "No se abrirán nuevas operaciones."
                )

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            elif text == "/status":

                status = (
                    "🟢 ACTIVO"
                    if BOT_RUNNING
                    else "🔴 DETENIDO"
                )

                telegram_send(
                    "📊 ESTADO DEL BOT\n\n"
                    f"Estado: {status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $10\n"
                    "Entrada: N+1\n"
                    "Ventana: 01–03 s\n"
                    f"Pares: {', '.join(PAIRS)}"
                )

    except Exception as exc:

        logger.warning(
            "Error Telegram commands: %s",
            exc,
        )


# ============================================================
# IQ OPTION
# ============================================================

def connect_iq() -> bool:

    global IQ

    if not IQ_EMAIL or not IQ_PASSWORD:

        raise ValueError(
            "Faltan IQ_EMAIL/IQ_PASSWORD"
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
        "IQ Option conectado"
    )

    telegram_send(
        "🟢 CONECTADO A IQ OPTION\n\n"
        "Mercado: DIGITAL OTC\n"
        "Entrada: N+1\n"
        "Ventana: segundos 01–03\n"
        "Expiración: 1 minuto"
    )

    return True


def ensure_connection() -> bool:

    global IQ

    try:

        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        logger.warning(
            "Conexión perdida; reconectando..."
        )

        connected, reason = IQ.connect()

        if not connected:

            logger.error(
                "No se pudo reconectar: %s",
                reason,
            )

            return False

        telegram_send(
            "🟢 IQ Option reconectado."
        )

        return True

    except Exception as exc:

        logger.error(
            "Error conexión: %s",
            exc,
        )

        return False


# ============================================================
# CANDLES
# ============================================================

def get_candles(
    pair: str,
) -> Optional[pd.DataFrame]:

    if IQ is None:
        return None

    try:

        candles = IQ.get_candles(
            pair,
            TIMEFRAME,
            CANDLE_COUNT,
            time.time(),
        )

        if not candles:
            return None

        df = pd.DataFrame(
            candles
        )

        if df.empty:
            return None

        df.rename(
            columns={
                "max": "high",
                "min": "low",
            },
            inplace=True,
        )

        required = [
            "open",
            "close",
            "high",
            "low",
        ]

        for column in required:

            if column not in df.columns:
                return None

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df.dropna(
            subset=required,
            inplace=True,
        )

        if "from" in df.columns:

            df["from"] = pd.to_numeric(
                df["from"],
                errors="coerce",
            )

            df.dropna(
                subset=["from"],
                inplace=True,
            )

            df.sort_values(
                "from",
                inplace=True,
            )

        df.reset_index(
            drop=True,
            inplace=True,
        )

        if len(df) > CANDLE_COUNT:

            df = (
                df.tail(
                    CANDLE_COUNT
                )
                .reset_index(drop=True)
            )

        return df

    except Exception as exc:

        logger.error(
            "Velas %s: %s",
            pair,
            exc,
        )

        return None


def candle_timestamp(
    df: pd.DataFrame,
    index: int = -1,
) -> Optional[int]:

    if (
        df is None
        or df.empty
        or "from" not in df.columns
    ):
        return None

    try:

        return int(
            df.iloc[index]["from"]
        )

    except Exception:

        return None


def candle_values(
    df: pd.DataFrame,
    index: int,
) -> Dict[str, float]:

    row = df.iloc[index]

    return {
        "open": float(
            row["open"]
        ),
        "high": float(
            row["high"]
        ),
        "low": float(
            row["low"]
        ),
        "close": float(
            row["close"]
        ),
    }


# ============================================================
# ESTADO DE VELA
# ============================================================

def reset_live_state(
    pair: str,
    ts: int,
    open_price: Optional[float] = None,
    close_price: Optional[float] = None,
) -> None:

    LIVE_STATE[pair] = {

        "timestamp": ts,

        "signal": None,

        "candidate_seen": False,

        "invalidated": False,

        "open": open_price,

        "last_close": close_price,

        "signal_score": 0,
    }


def update_live_state(
    pair: str,
    df: pd.DataFrame,
    result: Dict[str, Any],
) -> None:

    ts = candle_timestamp(
        df,
        -1,
    )

    if ts is None:
        return

    values = candle_values(
        df,
        -1,
    )

    state = LIVE_STATE.get(
        pair
    )

    # --------------------------------------------------------
    # Crear estado si no existe.
    # --------------------------------------------------------

    if (
        state is None
        or int(state["timestamp"]) != ts
    ):

        reset_live_state(
            pair,
            ts,
            open_price=values["open"],
            close_price=values["close"],
        )

        state = LIVE_STATE[pair]

    # --------------------------------------------------------
    # Protección contra None.
    # --------------------------------------------------------

    if state.get("open") is None:

        state["open"] = values[
            "open"
        ]

    if state.get("last_close") is None:

        state["last_close"] = values[
            "close"
        ]

    # --------------------------------------------------------
    # Si la señal ya fue invalidada.
    # --------------------------------------------------------

    if state["invalidated"]:

        state["last_close"] = values[
            "close"
        ]

        return

    signal = result.get(
        "signal"
    )

    # --------------------------------------------------------
    # SEÑAL CALL / PUT
    # --------------------------------------------------------

    if signal in (
        "call",
        "put",
    ):

        # Primera confirmación.
        if not state["candidate_seen"]:

            state["signal"] = signal

            state["candidate_seen"] = True

            state["signal_score"] = int(
                result.get("score") or 0
            )

            direction = (
                "CALL 🟢"
                if signal == "call"
                else "PUT 🔴"
            )

            telegram_send(
                "📌 SEÑAL CONFIRMADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {direction}\n\n"
                "VELA N — CONFIRMACIÓN\n"
                f"Apertura: {state['open']}\n"
                f"Cierre actual: "
                f"{values['close']}\n"
                f"Score: "
                f"{state['signal_score']}/10\n\n"
                "✅ Señal guardada.\n"
                "🚫 NO se ejecuta en N.\n"
                "➡️ Pertenece EXCLUSIVAMENTE a N+1.\n"
                "🎯 Entrada objetivo: apertura.\n"
                "⏱ Ventana N+1: 01–03 s."
            )

        # Si cambia la dirección durante N,
        # invalidamos la señal.
        elif state["signal"] != signal:

            state["invalidated"] = True

            state["signal"] = None

            telegram_send(
                "⚠️ SEÑAL INVALIDADA\n\n"
                f"Par: {pair}\n"
                f"Vela: {ts}\n"
                "La dirección cambió durante N.\n"
                "No habrá entrada en N+1."
            )

    # --------------------------------------------------------
    # Actualizar cierre vivo.
    # --------------------------------------------------------

    state["last_close"] = values[
        "close"
    ]


# ============================================================
# PENDING ENTRY
# ============================================================

def save_pending_entry(
    pair: str,
    state: Dict[str, Any],
) -> None:

    signal = state.get(
        "signal"
    )

    if signal not in (
        "call",
        "put",
    ):
        return

    if pair in PENDING_ENTRY:
        return

    # --------------------------------------------------------
    # Protección contra el error original:
    #
    # float(None)
    # --------------------------------------------------------

    continuity_open = state.get(
        "open"
    )

    continuity_close = state.get(
        "last_close"
    )

    continuity_ts = state.get(
        "timestamp"
    )

    if continuity_open is None:

        logger.error(
            "%s | No se puede guardar pendiente: "
            "continuity_open=None",
            pair,
        )

        telegram_send(
            "⚠️ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "No se pudo obtener la apertura "
            "válida de la vela N."
        )

        return

    if continuity_close is None:

        logger.error(
            "%s | No se puede guardar pendiente: "
            "continuity_close=None",
            pair,
        )

        return

    if continuity_ts is None:

        logger.error(
            "%s | No se puede guardar pendiente: "
            "timestamp=None",
            pair,
        )

        return

    try:

        continuity_open = float(
            continuity_open
        )

        continuity_close = float(
            continuity_close
        )

        continuity_ts = int(
            continuity_ts
        )

    except Exception as exc:

        logger.error(
            "%s | Error convirtiendo datos "
            "de continuidad: %s",
            pair,
            exc,
        )

        return

    now = time.time()

    PENDING_ENTRY[pair] = {

        "signal": signal,

        "continuity_ts": continuity_ts,

        "continuity_open": continuity_open,

        "continuity_close": continuity_close,

        "created_at": now,

        "deadline": (
            now
            + OPEN_RETRY_WINDOW
        ),
    }

    logger.info(
        "%s | PENDIENTE %s | N=%s | "
        "open=%s | close=%s",
        pair,
        signal.upper(),
        continuity_ts,
        continuity_open,
        continuity_close,
    )


def cooldown_active(
    pair: str,
) -> bool:

    last = LAST_TRADE_TIME.get(
        pair,
        0.0,
    )

    return (
        time.time() - last
    ) < TRADE_COOLDOWN


# ============================================================
# DIGITAL ENTRY
# ============================================================

def buy_digital(
    pair: str,
    signal: str,
) -> tuple[bool, Optional[Any]]:

    if IQ is None:
        return False, None

    try:

        result = IQ.buy_digital_spot(
            pair,
            AMOUNT,
            signal,
            EXPIRATION,
        )

        if isinstance(
            result,
            tuple,
        ):

            if len(result) >= 2:

                return (
                    bool(result[0]),
                    result[1],
                )

            return (
                bool(result[0]),
                None,
            )

        if result not in (
            None,
            False,
            "error",
            -1,
        ):

            return (
                True,
                result,
            )

        return (
            False,
            result,
        )

    except Exception as exc:

        logger.error(
            "buy_digital %s %s: %s",
            pair,
            signal,
            exc,
        )

        return False, None


# ============================================================
# TRY EXECUTE PENDING
# ============================================================

def try_execute_pending(
    pair: str,
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    # --------------------------------------------------------
    # Cooldown.
    # --------------------------------------------------------

    if cooldown_active(pair):
        return False

    # --------------------------------------------------------
    # Obtener vela actual.
    # --------------------------------------------------------

    df = get_candles(
        pair
    )

    if (
        df is None
        or len(df) < 2
    ):
        return False

    execution_ts = candle_timestamp(
        df,
        -1,
    )

    if execution_ts is None:
        return False

    continuity_ts = int(
        pending["continuity_ts"]
    )

    # --------------------------------------------------------
    # TODAVÍA ESTAMOS EN N.
    # --------------------------------------------------------

    if execution_ts <= continuity_ts:

        # Si todavía estamos en N,
        # no hacemos absolutamente nada.
        return False

    # --------------------------------------------------------
    # AQUÍ YA ESTAMOS EN N+1.
    # --------------------------------------------------------

    elapsed = (
        time.time()
        - execution_ts
    )

    # --------------------------------------------------------
    # MUY TEMPRANO.
    #
    # Esperamos al segundo 01.
    # --------------------------------------------------------

    if elapsed < ENTRY_MIN_SECOND:

        return False

    # --------------------------------------------------------
    # MUY TARDE.
    #
    # Después de 03 segundos no ejecutar.
    # --------------------------------------------------------

    if elapsed > ENTRY_MAX_SECOND:

        logger.warning(
            "%s | N+1 detectada fuera "
            "de ventana | segundo=%.3f",
            pair,
            elapsed,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: "
            f"{pending['signal'].upper()}\n"
            f"N+1 detectada en segundo: "
            f"{elapsed:.2f}\n\n"
            "Ventana permitida: 01–03 s."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # EVITAR DOBLE OPERACIÓN.
    # --------------------------------------------------------

    if (
        LAST_TRADE_CANDLE.get(
            pair
        )
        == execution_ts
    ):

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # DATOS DE N+1.
    # --------------------------------------------------------

    execution_values = candle_values(
        df,
        -1,
    )

    open_price = execution_values[
        "open"
    ]

    if open_price is None:

        logger.error(
            "%s | N+1 sin OPEN válido",
            pair,
        )

        return False

    try:

        open_price = float(
            open_price
        )

    except Exception:

        logger.error(
            "%s | OPEN N+1 inválido: %s",
            pair,
            open_price,
        )

        return False

    signal = pending[
        "signal"
    ]

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    # --------------------------------------------------------
    # AVISO ANTES DE OPERAR.
    # --------------------------------------------------------

    telegram_send(
        "⚡ ENTRADA 01–03s\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"
        "VELA N — CONFIRMACIÓN:\n"
        f"Apertura: "
        f"{pending['continuity_open']}\n"
        f"Cierre: "
        f"{pending['continuity_close']}\n"
        f"Timestamp: "
        f"{pending['continuity_ts']}\n\n"
        "VELA N+1 — EJECUCIÓN:\n"
        f"Timestamp: {execution_ts}\n"
        f"Segundo: {elapsed:.2f}\n"
        f"Apertura: {open_price}\n\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto\n"
        "🎯 DIGITAL OTC"
    )

    # --------------------------------------------------------
    # EJECUTAR.
    # --------------------------------------------------------

    ok, order_id = buy_digital(
        pair,
        signal,
    )

    # --------------------------------------------------------
    # RECHAZADA.
    # --------------------------------------------------------

    if not ok:

        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: "
            f"{signal.upper()}\n"
            f"Apertura N+1: {open_price}\n"
            f"Segundo: {elapsed:.2f}\n\n"
            "La señal pertenecía a N+1,\n"
            "pero IQ Option no aceptó la orden.\n\n"
            f"Resultado API: {order_id}"
        )

        logger.error(
            "%s | DIGITAL RECHAZADA | "
            "signal=%s | N+1=%s | "
            "segundo=%.3f | result=%s",
            pair,
            signal,
            execution_ts,
            elapsed,
            order_id,
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # OPERACIÓN ABIERTA.
    # --------------------------------------------------------

    LAST_TRADE_TIME[pair] = (
        time.time()
    )

    LAST_TRADE_CANDLE[pair] = (
        execution_ts
    )

    PENDING_ENTRY.pop(
        pair,
        None,
    )

    telegram_send(
        "✅ OPERACIÓN DIGITAL ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: "
        f"{signal.upper()}\n"
        f"Entrada: {open_price}\n"
        f"Segundo: {elapsed:.2f}\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto\n"
        f"Timestamp N+1: {execution_ts}\n"
        f"ID: {order_id}"
    )

    logger.info(
        "%s | DIGITAL %s | "
        "entrada=%s | N+1=%s | "
        "segundo=%.3f | ID=%s",
        pair,
        signal.upper(),
        open_price,
        execution_ts,
        elapsed,
        order_id,
    )

    return True


# ============================================================
# PROCESS PAIR
# ============================================================

def process_pair(
    pair: str,
) -> None:

    df = get_candles(
        pair
    )

    if (
        df is None
        or len(df) < 30
    ):
        return

    ts = candle_timestamp(
        df,
        -1,
    )

    if ts is None:
        return

    state = LIVE_STATE.get(
        pair
    )

    # ========================================================
    # PRIMERA VELA OBSERVADA
    # ========================================================

    if state is None:

        values = candle_values(
            df,
            -1,
        )

        reset_live_state(
            pair,
            ts,
            open_price=values[
                "open"
            ],
            close_price=values[
                "close"
            ],
        )

        state = LIVE_STATE[
            pair
        ]

    # ========================================================
    # CAMBIO DE VELA
    # ========================================================

    elif int(
        state["timestamp"]
    ) != ts:

        previous_ts = int(
            state["timestamp"]
        )

        previous_signal = state.get(
            "signal"
        )

        invalidated = bool(
            state.get(
                "invalidated",
                False,
            )
        )

        # ----------------------------------------------------
        # Guardar señal N.
        # ----------------------------------------------------

        if (
            previous_signal
            in (
                "call",
                "put",
            )
            and not invalidated
            and previous_ts < ts
        ):

            save_pending_entry(
                pair,
                state,
            )

        # ----------------------------------------------------
        # Crear estado de nueva vela.
        # ----------------------------------------------------

        values = candle_values(
            df,
            -1,
        )

        reset_live_state(
            pair,
            ts,
            open_price=values[
                "open"
            ],
            close_price=values[
                "close"
            ],
        )

        state = LIVE_STATE[
            pair
        ]

    # ========================================================
    # PENDING TIENE PRIORIDAD.
    #
    # Primero intentamos ejecutar la señal de N
    # en N+1.
    # ========================================================

    if pair in PENDING_ENTRY:

        try_execute_pending(
            pair
        )

    # ========================================================
    # ANALIZAR VELA ACTUAL
    # ========================================================

    result = analyze_market(
        df
    )

    logger.info(
        "%s | ts=%s | signal=%s | "
        "score=%s | %s",
        pair,
        ts,
        result.get("signal"),
        result.get("score"),
        result.get("reason"),
    )

    # ========================================================
    # ACTUALIZAR ESTADO VIVO
    # ========================================================

    update_live_state(
        pair,
        df,
        result,
    )


# ============================================================
# ANALYZE ALL PAIRS
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
                "Error procesando %s",
                pair,
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    global BOT_RUNNING

    logger.info(
        "===================================="
    )

    logger.info(
        "BOT DIGITAL OTC - CONTINUIDAD"
    )

    logger.info(
        "PARES: %s",
        ", ".join(PAIRS),
    )

    logger.info(
        "TIMEFRAME: 1M"
    )

    logger.info(
        "EXPIRATION: 1M"
    )

    logger.info(
        "AMOUNT: $%s",
        AMOUNT,
    )

    logger.info(
        "ENTRY WINDOW: 01–03 s"
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # Variables requeridas.
    # --------------------------------------------------------

    required = {

        "IQ_EMAIL": IQ_EMAIL,

        "IQ_PASSWORD": IQ_PASSWORD,

        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,

        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
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

    # --------------------------------------------------------
    # Conectar IQ Option.
    # --------------------------------------------------------

    try:

        connect_iq()

    except Exception as exc:

        logger.exception(
            "No se pudo iniciar IQ Option"
        )

        telegram_send(
            "❌ ERROR DE CONEXIÓN\n\n"
            f"{exc}"
        )

        return

    # --------------------------------------------------------
    # Bot listo.
    # --------------------------------------------------------

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "DIGITAL OTC\n"
        "EURUSD-OTC | "
        "GBPUSD-OTC | "
        "EURJPY-OTC\n\n"
        "⏱ Temporalidad: 1 minuto\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto\n\n"
        "N = confirmación\n"
        "🚫 N nunca se opera\n"
        "N+1 = ejecución\n"
        "🎯 Entrada: segundos 01–03"
    )

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    while True:

        try:

            # ------------------------------------------------
            # Telegram.
            # ------------------------------------------------

            check_commands()

            # ------------------------------------------------
            # Bot detenido.
            # ------------------------------------------------

            if not BOT_RUNNING:

                time.sleep(
                    1
                )

                continue

            # ------------------------------------------------
            # Conexión IQ.
            # ------------------------------------------------

            if not ensure_connection():

                time.sleep(
                    2
                )

                continue

            # ------------------------------------------------
            # Analizar pares.
            # ------------------------------------------------

            analyze_all_pairs()

            # ------------------------------------------------
            # Poll.
            # ------------------------------------------------

            time.sleep(
                POLL_INTERVAL
            )

        # ----------------------------------------------------
        # CTRL+C
        # ----------------------------------------------------

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            break

        # ----------------------------------------------------
        # Error principal.
        # ----------------------------------------------------

        except Exception as exc:

            logger.exception(
                "Error principal"
            )

            telegram_send(
                "⚠️ ERROR EN BOT\n\n"
                f"{exc}"
            )

            time.sleep(
                2
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
