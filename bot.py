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
    MICRO_TIMEFRAME,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# Pares OTC
PAIRS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "EURJPY-OTC",
]


# Temporalidad principal
TIMEFRAME = 60

# Expiración operación digital
EXPIRATION = 1

# Importe
AMOUNT = 100

# Historial principal
CANDLE_COUNT = 60


# ============================================================
# EJECUCIÓN
# ============================================================

POLL_INTERVAL = 0.08

# Entrada exclusivamente en N+1
# segundo 01–03
ENTRY_MIN_SECOND = 1.0
ENTRY_MAX_SECOND = 3.0

TRADE_COOLDOWN = 60.0


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TIMEOUT = 1.5

# Evita bombardear Telegram si está caído.
TELEGRAM_COMMAND_INTERVAL = 2.0

LAST_TELEGRAM_COMMAND_CHECK = 0.0


# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

LAST_UPDATE_ID: Optional[int] = None

IQ: Optional[IQ_Option] = None


# Última vela N cerrada procesada por cada par.
LAST_CONFIRMED_CANDLE: Dict[str, int] = {}


# Señales pendientes para ejecutar en N+1.
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}


# Última operación por par.
LAST_TRADE_TIME: Dict[str, float] = {}

LAST_TRADE_CANDLE: Dict[str, int] = {}


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
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
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

    except requests.exceptions.Timeout:

        logger.warning(
            "Telegram timeout enviando mensaje."
        )

        return False

    except requests.exceptions.RequestException as exc:

        logger.warning(
            "Telegram no disponible: %s",
            exc,
        )

        return False

    except Exception as exc:

        logger.warning(
            "Error Telegram: %s",
            exc,
        )

        return False


# ============================================================
# COMANDOS TELEGRAM
# ============================================================

def check_commands() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING
    global LAST_TELEGRAM_COMMAND_CHECK

    if not TELEGRAM_TOKEN:
        return

    now = time.time()

    # No consultar Telegram en cada vuelta del loop.
    if (
        now - LAST_TELEGRAM_COMMAND_CHECK
        < TELEGRAM_COMMAND_INTERVAL
    ):
        return

    LAST_TELEGRAM_COMMAND_CHECK = now

    url = (
        f"https://api.telegram.org/"
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

        response = requests.get(
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

            # =================================================
            # START
            # =================================================

            if text == "/start":

                BOT_RUNNING = True

                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "DIGITAL OTC\n"
                    "EURUSD-OTC\n"
                    "GBPUSD-OTC\n"
                    "EURJPY-OTC\n\n"
                    "N se analiza SOLO después "
                    "de cerrar.\n"
                    "N nunca se opera.\n"
                    "Entrada: N+1, segundo 01–03."
                )

                logger.info(
                    "Telegram: BOT ACTIVADO"
                )

            # =================================================
            # STOP
            # =================================================

            elif text == "/stop":

                BOT_RUNNING = False

                telegram_send(
                    "🔴 BOT DETENIDO\n\n"
                    "No se abrirán nuevas operaciones."
                )

                logger.info(
                    "Telegram: BOT DETENIDO"
                )

            # =================================================
            # STATUS
            # =================================================

            elif text == "/status":

                status = (
                    "🟢 ACTIVO"
                    if BOT_RUNNING
                    else "🔴 DETENIDO"
                )

                telegram_send(
                    "📊 ESTADO\n\n"
                    f"Estado: {status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Microvelas: 5 segundos\n"
                    f"Microvelas requeridas: "
                    f"{MICRO_CANDLE_COUNT}\n"
                    "Expiración: 1 minuto\n"
                    f"Importe: ${AMOUNT}\n"
                    f"Pares: {', '.join(PAIRS)}"
                )

    except requests.exceptions.Timeout:

        # No llenamos Railway con traceback.
        logger.warning(
            "Telegram commands: timeout"
        )

    except requests.exceptions.RequestException as exc:

        logger.warning(
            "Telegram commands: %s",
            exc,
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
        "Confirmación: N cerrada\n"
        "Entrada: N+1, segundo 01–03\n"
        "Microanálisis: 12 velas de 5S\n"
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
# OBTENER VELAS DE 1 MINUTO
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

        # IQ Option normalmente devuelve:
        # max = high
        # min = low
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

                logger.warning(
                    "%s | Falta columna %s",
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

        if "from" not in df.columns:

            logger.warning(
                "%s | IQ no devolvió 'from'",
                pair,
            )

            return None

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce",
        )

        df.dropna(
            subset=["from"],
            inplace=True,
        )

        df["from"] = df[
            "from"
        ].astype("int64")

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

        return df.tail(
            CANDLE_COUNT
        ).reset_index(
            drop=True
        )

    except Exception as exc:

        logger.error(
            "Velas %s: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# OBTENER MICROVELAS DE 5 SEGUNDOS
# ============================================================

def get_micro_candles(
    pair: str,
    minute_timestamp: int,
) -> Optional[pd.DataFrame]:

    if IQ is None:
        return None

    try:

        # N dura exactamente 60 segundos.
        #
        # Ejemplo:
        #
        # N empieza:
        # 12:30:00
        #
        # N termina:
        # 12:31:00
        #
        # Las 12 microvelas son:
        #
        # 12:30:00
        # 12:30:05
        # ...
        # 12:30:55
        #
        # Por eso solicitamos las microvelas
        # hasta el final de N.

        end_timestamp = (
            int(minute_timestamp)
            + TIMEFRAME
        )

        micro = IQ.get_candles(
            pair,
            MICRO_TIMEFRAME,
            MICRO_CANDLE_COUNT,
            end_timestamp,
        )

        if not micro:

            logger.info(
                "%s | No se obtuvieron "
                "microvelas 5S | N=%s",
                pair,
                minute_timestamp,
            )

            return None

        micro_df = pd.DataFrame(
            micro
        )

        if micro_df.empty:
            return None

        micro_df.rename(
            columns={
                "max": "high",
                "min": "low",
            },
            inplace=True,
        )

        required = [
            "open",
            "close",
        ]

        for column in required:

            if column not in micro_df.columns:

                logger.warning(
                    "%s | microvelas sin %s",
                    pair,
                    column,
                )

                return None

            micro_df[column] = pd.to_numeric(
                micro_df[column],
                errors="coerce",
            )

        micro_df.dropna(
            subset=required,
            inplace=True,
        )

        if "from" in micro_df.columns:

            micro_df["from"] = pd.to_numeric(
                micro_df["from"],
                errors="coerce",
            )

            micro_df.dropna(
                subset=["from"],
                inplace=True,
            )

            micro_df["from"] = (
                micro_df["from"]
                .astype("int64")
            )

            micro_df.sort_values(
                "from",
                inplace=True,
            )

            micro_df.drop_duplicates(
                subset=["from"],
                keep="last",
                inplace=True,
            )

        micro_df.reset_index(
            drop=True,
            inplace=True,
        )

        micro_df = micro_df.tail(
            MICRO_CANDLE_COUNT
        ).reset_index(
            drop=True
        )

        if len(micro_df) != MICRO_CANDLE_COUNT:

            logger.info(
                "%s | 5S incompletas | "
                "esperadas=%s | recibidas=%s",
                pair,
                MICRO_CANDLE_COUNT,
                len(micro_df),
            )

            return None

        return micro_df

    except Exception as exc:

        logger.error(
            "%s | Error microvelas 5S: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# TIMESTAMP DE VELA
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


# ============================================================
# VALORES DE VELA
# ============================================================

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


# ============================================================
# SECUENCIA DE VELAS
# ============================================================

def sequential(
    previous_ts: int,
    current_ts: int,
) -> bool:

    return (
        current_ts
        == previous_ts + TIMEFRAME
    )


# ============================================================
# COOLDOWN
# ============================================================

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
# ANALIZAR N CERRADA
# Y CREAR PENDIENTE PARA N+1
# ============================================================

def save_pending_entry(
    pair: str,
    df: pd.DataFrame,
) -> bool:

    # Ya existe una señal pendiente.
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

    if n_ts is None or n1_ts is None:
        return False

    if not sequential(
        n_ts,
        n1_ts,
    ):

        logger.warning(
            "%s | N/N+1 no consecutivas | "
            "N=%s N+1=%s",
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

    # ========================================================
    # OJO:
    #
    # AQUÍ ESTÁ LA CORRECCIÓN PRINCIPAL.
    #
    # La estrategia NO recibe un DataFrame.
    # Recibe:
    #
    #     candle
    #     micro
    #
    # ========================================================

    candle_n = df.iloc[
        -2
    ].copy()

    # --------------------------------------------------------
    # Obtener las 12 microvelas de N.
    # --------------------------------------------------------

    micro = get_micro_candles(
        pair,
        n_ts,
    )

    if micro is None:

        logger.info(
            "%s | N cerrada=%s | "
            "sin 12 microvelas 5S | "
            "SIN ENTRADA",
            pair,
            n_ts,
        )

        return False

    logger.info(
        "%s | 5S N completas | "
        "N=%s | cantidad=%s | "
        "última=%s",
        pair,
        n_ts,
        len(micro),
        (
            int(micro.iloc[-1]["from"])
            if "from" in micro.columns
            and not micro.empty
            else "N/A"
        ),
    )

    # ========================================================
    # LLAMADA CORRECTA A STRATEGY.PY
    #
    # analyze_market(candle, micro)
    #
    # NO:
    #
    # analyze_market(df)
    #
    # NO:
    #
    # analyze_market(
    #     df,
    #     confirmation_index=-2
    # )
    # ========================================================

    try:

        result = analyze_market(
            candle_n,
            micro,
        )

    except Exception as exc:

        logger.exception(
            "%s | ERROR EN STRATEGY | "
            "N=%s",
            pair,
            n_ts,
        )

        telegram_send(
            "⚠️ ERROR EN STRATEGY\n\n"
            f"Par: {pair}\n"
            f"N: {n_ts}\n"
            f"Error: {exc}"
        )

        return False

    if not isinstance(
        result,
        dict,
    ):

        logger.error(
            "%s | strategy devolvió "
            "tipo inválido: %r",
            pair,
            type(result),
        )

        return False

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
        "signal=%s | score=%s | "
        "%s",
        pair,
        n_ts,
        signal,
        score,
        reason,
    )

    # ========================================================
    # SIN SEÑAL
    # ========================================================

    if signal not in (
        "call",
        "put",
    ):

        logger.info(
            "%s | SIN ENTRADA | "
            "N=%s | razón=%s",
            pair,
            n_ts,
            reason,
        )

        return False

    # ========================================================
    # CREAR PENDIENTE
    # ========================================================

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
        "%s | SEÑAL CONFIRMADA\n"
        "N CERRADA:\n"
        "  timestamp = %s\n"
        "  open      = %.10f\n"
        "  high      = %.10f\n"
        "  low       = %.10f\n"
        "  close     = %.10f\n"
        "\n"
        "N+1 ABIERTA:\n"
        "  timestamp = %s\n"
        "  open      = %.10f\n"
        "\n"
        "SEÑAL = %s\n"
        "SCORE = %s\n"
        "RAZÓN = %s\n"
        "\n"
        "🚫 N NO SE OPERA\n"
        "🎯 ENTRADA SOLO N+1 01–03\n"
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
        reason,
    )

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "📌 SEÑAL CONFIRMADA AL CIERRE\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N — CERRADA:\n"
        f"Timestamp: {n_ts}\n"
        f"Apertura: {n['open']}\n"
        f"Máximo: {n['high']}\n"
        f"Mínimo: {n['low']}\n"
        f"Cierre: {n['close']}\n\n"
        "VELA N+1 — ABIERTA:\n"
        f"Timestamp: {n1_ts}\n"
        f"Apertura: {n1['open']}\n\n"
        f"Score: {score}\n"
        f"Razón: {reason}\n\n"
        "🚫 N nunca se opera.\n"
        "🎯 Entrada N+1, segundo 01–03."
    )

    return True


# ============================================================
# COMPRA DIGITAL
# ============================================================

def buy_digital(
    pair: str,
    signal: str,
) -> Tuple[bool, Optional[Any]]:

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

            if result:

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

        logger.error(
            "buy_digital %s %s: %s",
            pair,
            signal,
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
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    if cooldown_active(pair):

        logger.info(
            "%s | cooldown activo | "
            "entrada no ejecutada",
            pair,
        )

        return False

    df = get_candles(
        pair
    )

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

    # ========================================================
    # TODAVÍA NO LLEGÓ N+1
    # ========================================================

    if current_ts < n1_ts:
        return False

    # ========================================================
    # N+1 YA TERMINÓ
    # NO ENTRAR TARDE
    # ========================================================

    if current_ts > n1_ts:

        logger.warning(
            "%s | N+1 perdida | "
            "esperada=%s | actual=%s",
            pair,
            n1_ts,
            current_ts,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1 esperada: {n1_ts}\n"
            f"Vela actual: {current_ts}\n"
            "No se ejecuta tarde."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # VERIFICAR SECUENCIA
    # ========================================================

    if not sequential(
        int(pending["n_ts"]),
        current_ts,
    ):

        return False

    # ========================================================
    # APERTURA REAL DE N+1
    # ========================================================

    try:

        n1 = candle_values(
            df,
            -1,
        )

        live_open = n1[
            "open"
        ]

    except Exception:

        return False

    # ========================================================
    # TIEMPO REAL DESDE EL INICIO DE N+1
    # ========================================================

    elapsed = (
        time.time()
        - float(n1_ts)
    )

    # ========================================================
    # ANTES DEL SEGUNDO 1
    # ========================================================

    if elapsed < ENTRY_MIN_SECOND:

        return False

    # ========================================================
    # DESPUÉS DEL SEGUNDO 3
    # ========================================================

    if elapsed > ENTRY_MAX_SECOND:

        logger.warning(
            "%s | fuera de ventana | "
            "elapsed=%.3fs",
            pair,
            elapsed,
        )

        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1: {n1_ts}\n"
            f"Tiempo: {elapsed:.3f}s\n"
            "La ventana 01–03 ya terminó."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # EVITAR DOBLE OPERACIÓN
    # ========================================================

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
        "%s | N+1 | timestamp=%s | "
        "open_capturada=%.10f | "
        "open_actual=%.10f | "
        "diff=%.12f | "
        "segundo=%.3f",
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

    # ========================================================
    # MENSAJE DE EJECUCIÓN
    # ========================================================

    telegram_send(
        "⚡ EJECUTANDO N+1\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "N CERRADA:\n"
        f"Apertura: {pending['n_open']}\n"
        f"Cierre: {pending['n_close']}\n\n"
        "N+1:\n"
        f"Timestamp: {n1_ts}\n"
        f"Apertura IQ: {live_open}\n"
        f"Segundo: {elapsed:.3f}\n\n"
        f"💵 ${AMOUNT}\n"
        f"⏱ {EXPIRATION} minuto"
    )

    # ========================================================
    # EJECUTAR
    # ========================================================

    ok, order_id = buy_digital(
        pair,
        signal,
    )

    # ========================================================
    # RECHAZADA
    # ========================================================

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
            f"Respuesta: {order_id!r}"
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # OPERACIÓN ABIERTA
    # ========================================================

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
        "elapsed=%.3f | N+1=%s | "
        "ID=%s",
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

    # ========================================================
    # -1 = vela viva
    # -2 = última vela cerrada
    # ========================================================

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

    # ========================================================
    # PRIMERO:
    # intentar ejecutar una señal pendiente.
    # ========================================================

    if pair in PENDING_ENTRY:

        try_execute_pending(
            pair
        )

    # ========================================================
    # ÚLTIMA VELA CERRADA PROCESADA
    # ========================================================

    previous = LAST_CONFIRMED_CANDLE.get(
        pair
    )

    # ========================================================
    # PRIMERA SINCRONIZACIÓN
    #
    # No entrar.
    # ========================================================

    if previous is None:

        LAST_CONFIRMED_CANDLE[
            pair
        ] = closed_ts

        logger.info(
            "%s | sincronización inicial | "
            "cerrada=%s | viva=%s",
            pair,
            closed_ts,
            live_ts,
        )

        return

    # ========================================================
    # MISMA VELA
    #
    # No analizar otra vez.
    # ========================================================

    if closed_ts == previous:
        return

    # ========================================================
    # TIMESTAMP RETROCEDIÓ
    # ========================================================

    if closed_ts < previous:

        logger.warning(
            "%s | timestamp retrocedió | "
            "anterior=%s actual=%s",
            pair,
            previous,
            closed_ts,
        )

        return

    # ========================================================
    # SALTO DE MÁS DE UNA VELA
    #
    # No inventar señales.
    # ========================================================

    if not sequential(
        previous,
        closed_ts,
    ):

        logger.warning(
            "%s | salto de vela | "
            "anterior=%s actual=%s | "
            "sincronizando",
            pair,
            previous,
            closed_ts,
        )

        LAST_CONFIRMED_CANDLE[
            pair
        ] = closed_ts

        return

    # ========================================================
    # DATOS DE N Y N+1
    # ========================================================

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
        "  ts    = %s\n"
        "  open  = %.10f\n"
        "  high  = %.10f\n"
        "  low   = %.10f\n"
        "  close = %.10f\n"
        "\n"
        "N+1 VIVA:\n"
        "  ts    = %s\n"
        "  open  = %.10f\n"
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

    # ========================================================
    # MARCAR N COMO PROCESADA
    # ========================================================

    LAST_CONFIRMED_CANDLE[
        pair
    ] = closed_ts

    # ========================================================
    # ANALIZAR N
    #
    # La función obtiene las microvelas 5S de N.
    # ========================================================

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
        "N CERRADA / N+1"
    )

    logger.info(
        "PARES: %s",
        ", ".join(PAIRS),
    )

    logger.info(
        "TIMEFRAME: 1M"
    )

    logger.info(
        "MICROTIMEFRAME: 5S"
    )

    logger.info(
        "MICRO CANDLES: %s",
        MICRO_CANDLE_COUNT,
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

    # ========================================================
    # VARIABLES OBLIGATORIAS
    # ========================================================

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

    # ========================================================
    # CONEXIÓN IQ
    # ========================================================

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

    # ========================================================
    # BOT LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "DIGITAL OTC\n"
        "EURUSD-OTC | GBPUSD-OTC | EURJPY-OTC\n\n"
        "🔒 N se analiza solo al cierre.\n"
        "🚫 N nunca se opera.\n"
        "➡️ Entrada exclusivamente en N+1.\n"
        "📊 N se analiza con 12 microvelas de 5S.\n"
        "🎯 Entrada segundo 01–03."
    )

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    while True:

        try:

            # Telegram no bloquea el loop constantemente.
            check_commands()

            if not BOT_RUNNING:

                time.sleep(1)

                continue

            # =================================================
            # IQ OPTION
            # =================================================

            if not ensure_connection():

                time.sleep(2)

                continue

            # =================================================
            # ANALIZAR
            # =================================================

            analyze_all_pairs()

            # =================================================
            # POLLING
            # =================================================

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
