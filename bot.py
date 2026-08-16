from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option

from strategy import (
    analyze_market,
    MICRO_CANDLE_COUNT,
)


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

TIMEFRAME = 60
MICRO_TIMEFRAME = 5

EXPIRATION = 1
AMOUNT = 10

CANDLE_COUNT = 60

# Cantidad adicional para poder localizar exactamente
# las 12 microvelas correspondientes a N.
MICRO_FETCH_COUNT = 20

# ============================================================
# LOOP
# ============================================================

POLL_INTERVAL = 0.08

# ============================================================
# ENTRADA N+1
# ============================================================

ENTRY_MIN_SECOND = 1.0
ENTRY_MAX_SECOND = 3.0

TRADE_COOLDOWN = 60.0

# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_COMMAND_INTERVAL = 2.0
TELEGRAM_TIMEOUT = 0.8

# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

LAST_UPDATE_ID: Optional[int] = None

IQ: Optional[IQ_Option] = None

LAST_CONFIRMED_CANDLE: Dict[str, int] = {}

PENDING_ENTRY: Dict[
    str,
    Dict[str, Any],
] = {}

LAST_TRADE_TIME: Dict[
    str,
    float,
] = {}

LAST_TRADE_CANDLE: Dict[
    str,
    int,
] = {}

LAST_TELEGRAM_CHECK = 0.0


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# HTTP SESSION
# ============================================================

HTTP = requests.Session()

HTTP.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 "
            "Railway-IQ-Bot"
        )
    }
)


# ============================================================
# TELEGRAM
# ============================================================


def telegram_send(
    message: str,
) -> bool:

    if not TELEGRAM_TOKEN:
        return False

    if not TELEGRAM_CHAT_ID:
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        response = HTTP.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=TELEGRAM_TIMEOUT,
        )

        if response.status_code != 200:

            logger.warning(
                "Telegram HTTP %s: %s",
                response.status_code,
                response.text[:200],
            )

            return False

        return True

    except requests.RequestException as exc:

        logger.warning(
            "Telegram envío no disponible: %s",
            exc,
        )

        return False

    except Exception as exc:

        logger.warning(
            "Telegram error: %s",
            exc,
        )

        return False


# ============================================================
# TELEGRAM COMMANDS
# ============================================================


def check_commands(
    force: bool = False,
) -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING
    global LAST_TELEGRAM_CHECK

    now = time.time()

    # No consultar Telegram cada 0.08 segundos.
    if not force:

        if (
            now - LAST_TELEGRAM_CHECK
            < TELEGRAM_COMMAND_INTERVAL
        ):
            return

    LAST_TELEGRAM_CHECK = now

    if not TELEGRAM_TOKEN:
        return

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

    try:

        response = HTTP.get(
            url,
            params=params,
            timeout=TELEGRAM_TIMEOUT,
        )

        data = response.json()

        if not data.get("ok"):
            return

        for update in data.get(
            "result",
            [],
        ):

            LAST_UPDATE_ID = (
                update.get("update_id")
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

            if (
                chat_id
                != str(TELEGRAM_CHAT_ID)
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
                    "N se analiza SOLO "
                    "después de cerrar.\n"
                    "N nunca se opera.\n"
                    "Entrada: N+1 "
                    "segundo 01–03."
                )

            # ------------------------------------------------
            # STOP
            # ------------------------------------------------

            elif text == "/stop":

                BOT_RUNNING = False

                telegram_send(
                    "🔴 BOT DETENIDO\n\n"
                    "No se abrirán "
                    "nuevas operaciones."
                )

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            elif text == "/status":

                status = (
                    "🟢 ACTIVO"
                    if BOT_RUNNING
                    else
                    "🔴 DETENIDO"
                )

                pending = (
                    ", ".join(
                        PENDING_ENTRY.keys()
                    )
                    if PENDING_ENTRY
                    else "ninguna"
                )

                telegram_send(
                    "📊 ESTADO\n\n"
                    f"Estado: {status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Micro: 5 segundos\n"
                    "Expiración: 1 minuto\n"
                    f"Importe: ${AMOUNT}\n"
                    f"Pares: "
                    f"{', '.join(PAIRS)}\n"
                    f"Pendientes: {pending}"
                )

    except requests.RequestException as exc:

        # No llenamos Railway con miles de errores.
        logger.warning(
            "Telegram commands: %s",
            exc,
        )

    except Exception as exc:

        logger.warning(
            "Telegram commands: %s",
            exc,
        )


# ============================================================
# IQ OPTION
# ============================================================


def connect_iq() -> bool:

    global IQ

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
        "IQ Option conectado"
    )

    telegram_send(
        "🟢 CONECTADO A IQ OPTION\n\n"
        "Confirmación: N cerrada\n"
        "Entrada: N+1, segundo 01–03\n"
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
# CANDLES 1M
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
            "from",
        ]

        for column in required:

            if column not in df.columns:

                logger.warning(
                    "%s | falta columna %s",
                    pair,
                    column,
                )

                return None

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df.dropna(
            subset=required,
            inplace=True,
        )

        df["from"] = (
            df["from"]
            .astype("int64")
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

        return (
            df.tail(
                CANDLE_COUNT
            )
            .reset_index(drop=True)
        )

    except Exception as exc:

        logger.error(
            "Velas %s: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# MICROVELAS 5S DE N
# ============================================================


def get_micro_candles_for_minute(
    pair: str,
    minute_ts: int,
) -> pd.DataFrame:

    if IQ is None:
        return pd.DataFrame()

    try:

        # Pedimos algunas más para evitar que IQ
        # entregue una vela adicional de borde.
        end_time = (
            minute_ts
            + TIMEFRAME
            - 1
        )

        candles = IQ.get_candles(
            pair,
            MICRO_TIMEFRAME,
            MICRO_FETCH_COUNT,
            end_time,
        )

        if not candles:

            logger.info(
                "%s | N=%s | sin microvelas",
                pair,
                minute_ts,
            )

            return pd.DataFrame()

        micro = pd.DataFrame(
            candles
        )

        if micro.empty:
            return pd.DataFrame()

        micro.rename(
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
            "from",
        ]

        for column in required:

            if column not in micro.columns:

                logger.warning(
                    "%s | micro falta %s",
                    pair,
                    column,
                )

                return pd.DataFrame()

            micro[column] = pd.to_numeric(
                micro[column],
                errors="coerce",
            )

        micro.dropna(
            subset=required,
            inplace=True,
        )

        micro["from"] = (
            micro["from"]
            .astype("int64")
        )

        micro.sort_values(
            "from",
            inplace=True,
        )

        micro.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        # ----------------------------------------------------
        # EXACTAMENTE LAS MICROVELAS DE N
        # ----------------------------------------------------

        start = minute_ts

        end = (
            minute_ts
            + TIMEFRAME
        )

        micro = micro[
            (micro["from"] >= start)
            &
            (micro["from"] < end)
        ].copy()

        micro.sort_values(
            "from",
            inplace=True,
        )

        micro.reset_index(
            drop=True,
            inplace=True,
        )

        # ----------------------------------------------------
        # Validar continuidad
        # ----------------------------------------------------

        if len(micro) != MICRO_CANDLE_COUNT:

            logger.info(
                "%s | N=%s | 5S incompletas "
                "| recibidas=%s esperadas=%s",
                pair,
                minute_ts,
                len(micro),
                MICRO_CANDLE_COUNT,
            )

            return pd.DataFrame()

        expected = start

        for ts in micro["from"]:

            if int(ts) != expected:

                logger.info(
                    "%s | N=%s | hueco 5S "
                    "| esperado=%s recibido=%s",
                    pair,
                    minute_ts,
                    expected,
                    int(ts),
                )

                return pd.DataFrame()

            expected += MICRO_TIMEFRAME

        return micro

    except Exception as exc:

        logger.error(
            "%s | error microvelas N=%s: %s",
            pair,
            minute_ts,
            exc,
        )

        return pd.DataFrame()


# ============================================================
# UTILIDADES DE VELA
# ============================================================


def candle_timestamp(
    df: pd.DataFrame,
    index: int,
) -> Optional[int]:

    if (
        df is None
        or df.empty
        or "from" not in df.columns
    ):
        return None

    try:

        value = df.iloc[index]["from"]

        if pd.isna(value):
            return None

        return int(value)

    except Exception:

        return None


def candle_values(
    df: pd.DataFrame,
    index: int,
) -> Dict[str, float]:

    row = df.iloc[index]

    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    }


def sequential(
    previous_ts: int,
    current_ts: int,
) -> bool:

    return (
        current_ts
        == previous_ts + TIMEFRAME
    )


def cooldown_active(
    pair: str,
) -> bool:

    return (
        time.time()
        - LAST_TRADE_TIME.get(
            pair,
            0.0,
        )
        < TRADE_COOLDOWN
    )


# ============================================================
# CREAR PENDIENTE N+1
# ============================================================


def save_pending_entry(
    pair: str,
    df: pd.DataFrame,
) -> bool:

    if pair in PENDING_ENTRY:
        return False

    if len(df) < 2:
        return False

    # --------------------------------------------------------
    # N = última cerrada
    # N+1 = vela viva
    # --------------------------------------------------------

    n_ts = candle_timestamp(
        df,
        -2,
    )

    n1_ts = candle_timestamp(
        df,
        -1,
    )

    if (
        n_ts is None
        or n1_ts is None
    ):
        return False

    if not sequential(
        n_ts,
        n1_ts,
    ):

        logger.warning(
            "%s | N/N+1 no consecutivas "
            "| N=%s N+1=%s",
            pair,
            n_ts,
            n1_ts,
        )

        return False

    n = candle_values(
        df,
        -2,
    )

    n1 = candle_values(
        df,
        -1,
    )

    # --------------------------------------------------------
    # OBTENER MICROVELAS DE N
    # --------------------------------------------------------

    micro = get_micro_candles_for_minute(
        pair,
        n_ts,
    )

    if micro.empty:

        logger.info(
            "%s | N cerrada=%s | "
            "SIN ENTRADA | microvelas 5S "
            "no disponibles",
            pair,
            n_ts,
        )

        return False

    logger.info(
        "%s | N=%s | 5S completas=%s",
        pair,
        n_ts,
        len(micro),
    )

    # --------------------------------------------------------
    # ANALIZAR N + MICROVELAS
    # --------------------------------------------------------

    n_series = df.iloc[-2].copy()

    result = analyze_market(
        n_series,
        micro,
    )

    signal = result.get(
        "signal"
    )

    score = result.get(
        "score",
        0,
    )

    reason = str(
        result.get(
            "reason",
            "",
        )
    )

    logger.info(
        "%s | N cerrada | ts=%s | "
        "signal=%s | score=%s | %s",
        pair,
        n_ts,
        signal,
        score,
        reason,
    )

    # --------------------------------------------------------
    # NO HAY SEÑAL
    # --------------------------------------------------------

    if signal not in (
        "call",
        "put",
    ):

        logger.info(
            "%s | SIN ENTRADA | N=%s | "
            "score=%s | motivo=%s",
            pair,
            n_ts,
            score,
            reason,
        )

        return False

    # --------------------------------------------------------
    # CREAR PENDIENTE
    # --------------------------------------------------------

    PENDING_ENTRY[pair] = {

        "signal": signal,

        "n_ts": n_ts,

        "n_open": n["open"],
        "n_high": n["high"],
        "n_low": n["low"],
        "n_close": n["close"],

        "n1_ts": n1_ts,
        "n1_open": n1["open"],

        "score": int(
            score or 0
        ),

        "reason": reason,
    }

    logger.info(
        "\n"
        "==================================================\n"
        "%s | SEÑAL PENDIENTE N+1\n"
        "N CERRADA\n"
        " timestamp = %s\n"
        " open      = %.10f\n"
        " high      = %.10f\n"
        " low       = %.10f\n"
        " close     = %.10f\n"
        "\n"
        "N+1 ABIERTA\n"
        " timestamp = %s\n"
        " open      = %.10f\n"
        "\n"
        "SEÑAL = %s\n"
        "SCORE = %s/10\n"
        "==================================================",
        pair,
        n_ts,
        n["open"],
        n["high"],
        n["low"],
        n["close"],
        n1_ts,
        n1["open"],
        signal.upper(),
        score,
    )

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "📌 SEÑAL CONFIRMADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N — CERRADA\n"
        f"Timestamp: {n_ts}\n"
        f"Apertura: {n['open']}\n"
        f"Máximo: {n['high']}\n"
        f"Mínimo: {n['low']}\n"
        f"Cierre: {n['close']}\n\n"
        "VELA N+1 — ABIERTA\n"
        f"Timestamp: {n1_ts}\n"
        f"Apertura: {n1['open']}\n\n"
        f"Score: {score}/10\n"
        f"Motivo: {reason}\n\n"
        "🚫 N nunca se opera.\n"
        "🎯 Entrada N+1 segundo 01–03."
    )

    return True


# ============================================================
# ORDEN DIGITAL
# ============================================================


def buy_digital(
    pair: str,
    signal: str,
) -> Tuple[bool, Optional[Any]]:

    if IQ is None:
        return False, None

    try:

        logger.info(
            "%s | enviando DIGITAL | "
            "signal=%s | amount=%s | exp=%s",
            pair,
            signal,
            AMOUNT,
            EXPIRATION,
        )

        result = IQ.buy_digital_spot(
            pair,
            AMOUNT,
            signal,
            EXPIRATION,
        )

        logger.info(
            "%s | respuesta IQ DIGITAL: %r",
            pair,
            result,
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

            if len(result) == 1:

                return (
                    bool(result[0]),
                    None,
                )

            return (
                False,
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

        logger.exception(
            "%s | error buy_digital: %s",
            pair,
            exc,
        )

        return (
            False,
            None,
        )


# ============================================================
# EJECUTAR N+1
# ============================================================


def try_execute_pending(
    pair: str,
    df: pd.DataFrame,
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    if cooldown_active(pair):

        logger.info(
            "%s | entrada pendiente "
            "pero cooldown activo",
            pair,
        )

        return False

    if df is None or len(df) < 2:
        return False

    current_ts = candle_timestamp(
        df,
        -1,
    )

    if current_ts is None:
        return False

    n1_ts = int(
        pending["n1_ts"]
    )

    # --------------------------------------------------------
    # TODAVÍA NO LLEGÓ N+1
    # --------------------------------------------------------

    if current_ts < n1_ts:
        return False

    # --------------------------------------------------------
    # YA PASÓ N+1
    # --------------------------------------------------------

    if current_ts > n1_ts:

        logger.warning(
            "%s | N+1 PERDIDA | "
            "esperada=%s | actual=%s",
            pair,
            n1_ts,
            current_ts,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1 esperada: {n1_ts}\n"
            f"Vela actual: {current_ts}\n\n"
            "No se ejecuta tarde."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # N+1 DEBE SER EXACTAMENTE LA SIGUIENTE
    # --------------------------------------------------------

    if not sequential(
        int(pending["n_ts"]),
        current_ts,
    ):

        logger.warning(
            "%s | N+1 no es consecutiva",
            pair,
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # DATOS ACTUALES DE N+1
    # --------------------------------------------------------

    try:

        n1 = candle_values(
            df,
            -1,
        )

        live_open = n1["open"]

    except Exception:

        return False

    # --------------------------------------------------------
    # SEGUNDO EXACTO
    # --------------------------------------------------------

    elapsed = (
        time.time()
        - float(n1_ts)
    )

    # Antes de segundo 1.
    if elapsed < ENTRY_MIN_SECOND:
        return False

    # Después de segundo 3.
    if elapsed > ENTRY_MAX_SECOND:

        logger.warning(
            "%s | FUERA DE VENTANA | "
            "elapsed=%.3f",
            pair,
            elapsed,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1: {n1_ts}\n"
            f"Tiempo: {elapsed:.3f}s\n"
            "Ventana 01–03 terminada."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # NO REPETIR OPERACIÓN
    # --------------------------------------------------------

    if (
        LAST_TRADE_CANDLE.get(
            pair
        )
        == n1_ts
    ):

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    captured_open = float(
        pending["n1_open"]
    )

    diff = abs(
        live_open
        - captured_open
    )

    logger.info(
        "%s | N+1 | ts=%s | "
        "open_capturada=%.10f | "
        "open_actual=%.10f | "
        "diff=%.12f | segundo=%.3f",
        pair,
        n1_ts,
        captured_open,
        live_open,
        diff,
        elapsed,
    )

    signal = pending[
        "signal"
    ]

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "⚡ EJECUTANDO N+1\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "N CERRADA:\n"
        f"Apertura: "
        f"{pending['n_open']}\n"
        f"Cierre: "
        f"{pending['n_close']}\n\n"
        "N+1:\n"
        f"Apertura: {live_open}\n"
        f"Segundo: {elapsed:.3f}\n\n"
        f"💵 ${AMOUNT}\n"
        f"⏱ {EXPIRATION} minuto"
    )

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    ok, order_id = buy_digital(
        pair,
        signal,
    )

    # --------------------------------------------------------
    # RECHAZADA
    # --------------------------------------------------------

    if not ok:

        logger.error(
            "%s | DIGITAL RECHAZADA | "
            "signal=%s | N+1=%s | "
            "open=%.10f | elapsed=%.3f | "
            "respuesta=%r",
            pair,
            signal,
            n1_ts,
            live_open,
            elapsed,
            order_id,
        )

        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"N+1: {n1_ts}\n"
            f"Apertura: {live_open}\n"
            f"Segundo: {elapsed:.3f}\n"
            f"Respuesta IQ: {order_id!r}"
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # ABIERTA
    # --------------------------------------------------------

    LAST_TRADE_TIME[pair] = (
        time.time()
    )

    LAST_TRADE_CANDLE[pair] = (
        n1_ts
    )

    PENDING_ENTRY.pop(
        pair,
        None,
    )

    logger.info(
        "%s | DIGITAL ABIERTA | "
        "%s | open=%.10f | "
        "elapsed=%.3f | "
        "N+1=%s | ID=%s",
        pair,
        signal.upper(),
        live_open,
        elapsed,
        n1_ts,
        order_id,
    )

    telegram_send(
        "✅ OPERACIÓN DIGITAL ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"Entrada: {live_open}\n"
        f"Segundo: {elapsed:.3f}\n"
        f"ID: {order_id}"
    )

    return True


# ============================================================
# PROCESAR PAR
# ============================================================


def process_pair(
    pair: str,
) -> None:

    df = get_candles(
        pair
    )

    if df is None or len(df) < 2:
        return

    # --------------------------------------------------------
    # -1 = VELA VIVA
    # -2 = ÚLTIMA CERRADA
    # --------------------------------------------------------

    live_ts = candle_timestamp(
        df,
        -1,
    )

    closed_ts = candle_timestamp(
        df,
        -2,
    )

    if (
        live_ts is None
        or closed_ts is None
    ):
        return

    # --------------------------------------------------------
    # PRIMERO: INTENTAR EJECUTAR
    # UNA SEÑAL YA PENDIENTE
    # --------------------------------------------------------

    if pair in PENDING_ENTRY:

        try_execute_pending(
            pair,
            df,
        )

    # --------------------------------------------------------
    # ÚLTIMA N CERRADA PROCESADA
    # --------------------------------------------------------

    previous = (
        LAST_CONFIRMED_CANDLE.get(
            pair
        )
    )

    # --------------------------------------------------------
    # PRIMERA SINCRONIZACIÓN
    # --------------------------------------------------------

    if previous is None:

        LAST_CONFIRMED_CANDLE[
            pair
        ] = closed_ts

        logger.info(
            "%s | sincronización inicial | "
            "N cerrada=%s | N+1=%s",
            pair,
            closed_ts,
            live_ts,
        )

        return

    # --------------------------------------------------------
    # MISMA N
    # --------------------------------------------------------

    if closed_ts == previous:
        return

    # --------------------------------------------------------
    # TIMESTAMP RETROCEDIÓ
    # --------------------------------------------------------

    if closed_ts < previous:

        logger.warning(
            "%s | timestamp retrocedió | "
            "anterior=%s actual=%s",
            pair,
            previous,
            closed_ts,
        )

        return

    # --------------------------------------------------------
    # SALTO DE MÁS DE UNA VELA
    # --------------------------------------------------------

    if not sequential(
        previous,
        closed_ts,
    ):

        logger.warning(
            "%s | salto de vela | "
            "anterior=%s actual=%s | "
            "sin inventar señal",
            pair,
            previous,
            closed_ts,
        )

        LAST_CONFIRMED_CANDLE[
            pair
        ] = closed_ts

        return

    # --------------------------------------------------------
    # NUEVA N CONFIRMADA
    # --------------------------------------------------------

    n = candle_values(
        df,
        -2,
    )

    n1 = candle_values(
        df,
        -1,
    )

    logger.info(
        "\n"
        "--------------------------------------------------\n"
        "%s | NUEVA VELA CONFIRMADA\n"
        "\n"
        "N CERRADA:\n"
        " ts=%s\n"
        " open=%.10f\n"
        " high=%.10f\n"
        " low=%.10f\n"
        " close=%.10f\n"
        "\n"
        "N+1 VIVA:\n"
        " ts=%s\n"
        " open=%.10f\n"
        "--------------------------------------------------",
        pair,
        closed_ts,
        n["open"],
        n["high"],
        n["low"],
        n["close"],
        live_ts,
        n1["open"],
    )

    # --------------------------------------------------------
    # MARCAR N COMO PROCESADA
    # --------------------------------------------------------

    LAST_CONFIRMED_CANDLE[
        pair
    ] = closed_ts

    # --------------------------------------------------------
    # ANALIZAR N
    # --------------------------------------------------------

    save_pending_entry(
        pair,
        df,
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
        "BOT DIGITAL OTC"
    )

    logger.info(
        "N CERRADA -> N+1"
    )

    logger.info(
        "PARES: %s",
        ", ".join(PAIRS),
    )

    logger.info(
        "TIMEFRAME: 1M"
    )

    logger.info(
        "MICRO: 5S"
    )

    logger.info(
        "EXPIRATION: 1M"
    )

    logger.info(
        "AMOUNT: $%s",
        AMOUNT,
    )

    logger.info(
        "ENTRY WINDOW: %.1f - %.1f s",
        ENTRY_MIN_SECOND,
        ENTRY_MAX_SECOND,
    )

    logger.info(
        "===================================="
    )

    # --------------------------------------------------------
    # VARIABLES
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
    # CONEXIÓN IQ
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
    # BOT LISTO
    # --------------------------------------------------------

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "DIGITAL OTC\n"
        "EURUSD-OTC | "
        "GBPUSD-OTC | "
        "EURJPY-OTC\n\n"
        "🔒 N se analiza únicamente "
        "al cierre.\n"
        "🚫 N nunca se opera.\n"
        "➡️ Señal creada para N+1.\n"
        "🎯 Entrada únicamente "
        "segundo 01–03."
    )

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    while True:

        try:

            # Telegram se revisa cada 2 segundos,
            # no cada 0.08 segundos.
            check_commands()

            if not BOT_RUNNING:

                time.sleep(0.5)

                continue

            if not ensure_connection():

                time.sleep(2)

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

            break

        except Exception as exc:

            logger.exception(
                "Error principal"
            )

            telegram_send(
                "⚠️ ERROR EN BOT\n\n"
                f"{exc}"
            )

            time.sleep(2)


# ============================================================
# START
# ============================================================


if __name__ == "__main__":
    main()
