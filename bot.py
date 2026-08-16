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


# Vela principal
TIMEFRAME = 60

# Microvelas
MICRO_TIMEFRAME = 5

# Cantidad de velas 1M
CANDLE_COUNT = 60

# Cantidad de microvelas 5s.
# 60 segundos / 5 = 12 microvelas.
MICRO_CANDLE_COUNT = 12


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 10
EXPIRATION = 1


# ============================================================
# SINCRONIZACIÓN
# ============================================================

POLL_INTERVAL = 0.05

# Después de detectar el cambio de minuto,
# se permiten unos segundos para que IQ Option
# entregue correctamente la nueva vela.
OPEN_RETRY_WINDOW = 3.0


# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None


# Último minuto cerrado que ya fue procesado.
LAST_PROCESSED_MINUTE: Dict[str, int] = {}


# Señales pendientes para la siguiente vela.
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}


# Última operación por vela.
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
            timeout=5,
        )

        if response.status_code != 200:

            logger.error(
                "Telegram error %s: %s",
                response.status_code,
                response.text,
            )

            return False

        return True

    except Exception as exc:

        logger.error(
            "Telegram exception: %s",
            exc,
        )

        return False


# ============================================================
# COMANDOS TELEGRAM
# ============================================================

def check_commands() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING

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

        response = requests.get(
            url,
            params=params,
            timeout=3,
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
                    "ESTRATEGIA 1M + 5S\n\n"
                    "EURUSD-OTC\n"
                    "GBPUSD-OTC\n"
                    "EURJPY-OTC\n\n"
                    "📊 Vela principal: 1 minuto\n"
                    "⏱ Microvelas: 5 segundos\n"
                    "💵 Importe: $10\n\n"
                    "CALL:\n"
                    "Primera 5s > apertura 1M\n"
                    "Retroceso 5s < apertura 1M\n"
                    "Cierre 1M verde\n\n"
                    "PUT:\n"
                    "Primera 5s < apertura 1M\n"
                    "Retroceso 5s > apertura 1M\n"
                    "Cierre 1M rojo\n\n"
                    "➡️ Entrada en la siguiente vela 1M."
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
                    else
                    "🔴 DETENIDO"
                )

                telegram_send(
                    "📊 ESTADO\n\n"
                    f"Estado: {status}\n"
                    "Temporalidad: 1M\n"
                    "Microvelas: 5S\n"
                    "Expiración: 1M\n"
                    "Importe: $10\n"
                    f"Pares: {', '.join(PAIRS)}"
                )

    except Exception as exc:

        logger.error(
            "Error comandos Telegram: %s",
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
        "IQ Option conectado."
    )

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "Estrategia 1M + 5S\n"
        "Entrada: siguiente vela 1M"
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
            "Conexión perdida. Reconectando..."
        )

        connected, reason = IQ.connect()

        if not connected:

            logger.error(
                "Reconexión fallida: %s",
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
# OBTENER VELAS 1M
# ============================================================

def get_1m_candles(
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

        if "from" not in df.columns:
            return None

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

        return df

    except Exception as exc:

        logger.error(
            "%s | error velas 1M: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# OBTENER MICROVELAS 5S
# ============================================================

def get_5s_candles(
    pair: str,
    minute_timestamp: int,
) -> Optional[pd.DataFrame]:

    if IQ is None:
        return None

    try:

        # Pedimos algunas microvelas adicionales
        # para compensar pequeños retrasos de API.
        candles = IQ.get_candles(
            pair,
            MICRO_TIMEFRAME,
            MICRO_CANDLE_COUNT + 4,
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
        ]

        for column in required:

            if column not in df.columns:
                return None

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        if "from" not in df.columns:
            return None

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce",
        )

        df.dropna(
            subset=[
                "from",
                "open",
                "close",
            ],
            inplace=True,
        )

        df.sort_values(
            "from",
            inplace=True,
        )

        # ----------------------------------------------------
        # SOLO MICROVELAS DEL MINUTO ANALIZADO
        # ----------------------------------------------------

        start = int(
            minute_timestamp
        )

        end = start + 60

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

    except Exception as exc:

        logger.error(
            "%s | error velas 5S: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# TIMESTAMP
# ============================================================

def get_timestamp(
    df: pd.DataFrame,
    index: int = -1,
) -> Optional[int]:

    if df is None:
        return None

    if df.empty:
        return None

    if "from" not in df.columns:
        return None

    try:

        return int(
            float(
                df.iloc[index]["from"]
            )
        )

    except Exception:

        return None


# ============================================================
# VELA CERRADA
# ============================================================

def get_closed_candle(
    df: pd.DataFrame,
) -> Optional[pd.Series]:

    if df is None:
        return None

    if len(df) < 2:
        return None

    # IQ Option puede devolver la vela actual
    # todavía viva en la última posición.
    #
    # Por eso:
    #
    # -1 = vela viva
    # -2 = última vela cerrada
    #

    return df.iloc[-2]


# ============================================================
# CREAR SEÑAL PENDIENTE
# ============================================================

def create_pending_signal(
    pair: str,
    candle: pd.Series,
    micro: pd.DataFrame,
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

    # Evitar duplicados.
    if pair in PENDING_ENTRY:

        existing = PENDING_ENTRY[
            pair
        ]

        if int(
            existing["minute_timestamp"]
        ) == int(minute_ts):

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

    PENDING_ENTRY[pair] = {

        "signal": signal,

        "minute_timestamp": int(
            minute_ts
        ),

        "minute_open": opening,

        "minute_close": closing,

        "first_5s_close": first_5s_close,

        "pullback_count": result.get(
            "pullback_count",
            0,
        ),

        "reason": result.get(
            "reason",
            "",
        ),

        "created_at": time.time(),

        "deadline": (
            time.time()
            + OPEN_RETRY_WINDOW
        ),
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
        f"Apertura: {opening}\n"
        f"Cierre: {closing}\n\n"
        "PRIMERA 5S\n"
        f"Cierre: {first_5s_close}\n\n"
        "RETROCESOS 5S\n"
        f"Cantidad: {result.get('pullback_count', 0)}\n\n"
        "✅ Patrón confirmado.\n"
        "🚫 NO SE OPERA N.\n"
        "➡️ Señal pertenece a N+1."
    )

    logger.info(
        "%s | SEÑAL %s | N=%s",
        pair,
        signal.upper(),
        minute_ts,
    )


# ============================================================
# COMPRA DIGITAL
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

            if len(result) == 1:

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
# EJECUTAR EN N+1
# ============================================================

def execute_pending(
    pair: str,
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:
        return False

    continuity_ts = int(
        pending[
            "minute_timestamp"
        ]
    )

    # --------------------------------------------------------
    # OBTENER VELAS ACTUALES
    # --------------------------------------------------------

    df = get_1m_candles(
        pair
    )

    if df is None:
        return False

    if len(df) < 2:
        return False

    current_live_ts = get_timestamp(
        df,
        -1,
    )

    if current_live_ts is None:
        return False

    # ========================================================
    # CLAVE DE SEGURIDAD
    # ========================================================
    #
    # Si la última vela sigue siendo N:
    #
    #       NO OPERAR
    #
    # Solo cuando:
    #
    #       current_live_ts > continuity_ts
    #
    # significa que ya comenzó N+1.
    #
    # ========================================================

    if current_live_ts <= continuity_ts:

        logger.info(
            "%s | esperando N+1 | "
            "N=%s | actual=%s",
            pair,
            continuity_ts,
            current_live_ts,
        )

        return False

    # --------------------------------------------------------
    # EVITAR DUPLICAR OPERACIÓN
    # --------------------------------------------------------

    if (
        LAST_TRADE_CANDLE.get(pair)
        == current_live_ts
    ):

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # OBTENER APERTURA DE N+1
    # --------------------------------------------------------

    execution_candle = df.iloc[-1]

    try:

        execution_open = float(
            execution_candle["open"]
        )

    except Exception:

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

    # --------------------------------------------------------
    # INFORMAR QUE N+1 YA COMENZÓ
    # --------------------------------------------------------

    telegram_send(
        "⚡ N+1 DETECTADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        f"Timestamp N: {continuity_ts}\n"
        f"Timestamp N+1: {current_live_ts}\n\n"
        f"Apertura N+1 detectada: "
        f"{execution_open}\n\n"
        "🎯 EJECUTANDO EN N+1"
    )

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    ok, order_id = buy_digital(
        pair,
        signal,
    )

    if not ok:

        telegram_send(
            "❌ OPERACIÓN RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"N: {continuity_ts}\n"
            f"N+1: {current_live_ts}\n"
            f"Apertura detectada: "
            f"{execution_open}\n\n"
            "IQ Option no aceptó la operación."
        )

        logger.error(
            "%s | ORDEN RECHAZADA | "
            "%s | N=%s | N+1=%s",
            pair,
            signal.upper(),
            continuity_ts,
            current_live_ts,
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # --------------------------------------------------------
    # REGISTRAR OPERACIÓN
    # --------------------------------------------------------

    LAST_TRADE_CANDLE[
        pair
    ] = current_live_ts

    PENDING_ENTRY.pop(
        pair,
        None,
    )

    telegram_send(
        "✅ OPERACIÓN ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "VELA N\n"
        f"Apertura: "
        f"{pending['minute_open']}\n"
        f"Cierre: "
        f"{pending['minute_close']}\n\n"
        "VELA N+1\n"
        f"Apertura detectada: "
        f"{execution_open}\n\n"
        f"💵 Importe: ${AMOUNT}\n"
        "⏱ Expiración: 1 minuto\n"
        f"🆔 ID: {order_id}"
    )

    logger.info(
        "%s | OPERACIÓN %s | "
        "N=%s | N+1=%s | "
        "OPEN=%s | ID=%s",
        pair,
        signal.upper(),
        continuity_ts,
        current_live_ts,
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

    df = get_1m_candles(
        pair
    )

    if df is None:
        return

    if len(df) < 2:
        return

    # --------------------------------------------------------
    # 1. EJECUTAR PENDIENTE SI YA COMENZÓ N+1
    # --------------------------------------------------------

    if pair in PENDING_ENTRY:

        execute_pending(
            pair
        )

    # --------------------------------------------------------
    # 2. IDENTIFICAR ÚLTIMA VELA CERRADA
    # --------------------------------------------------------

    closed_candle = get_closed_candle(
        df
    )

    if closed_candle is None:
        return

    closed_ts = get_timestamp(
        df,
        -2,
    )

    if closed_ts is None:
        return

    # --------------------------------------------------------
    # 3. EVITAR ANALIZAR LA MISMA VELA
    # --------------------------------------------------------

    if (
        LAST_PROCESSED_MINUTE.get(pair)
        == closed_ts
    ):

        return

    # Marcamos primero como procesada.
    LAST_PROCESSED_MINUTE[
        pair
    ] = closed_ts

    # --------------------------------------------------------
    # 4. OBTENER LAS 5S DE ESA VELA
    # --------------------------------------------------------

    candles_5s = get_5s_candles(
        pair,
        closed_ts,
    )

    if candles_5s is None:

        logger.warning(
            "%s | no se pudieron obtener "
            "microvelas 5S | N=%s",
            pair,
            closed_ts,
        )

        return

    # --------------------------------------------------------
    # 5. DEBEN EXISTIR LAS 12 MICROVELAS
    # --------------------------------------------------------

    if len(candles_5s) < 12:

        logger.warning(
            "%s | microvelas insuficientes "
            "para N=%s | recibidas=%s/12",
            pair,
            closed_ts,
            len(candles_5s),
        )

        telegram_send(
            "⚠️ VELA NO ANALIZADA\n\n"
            f"Par: {pair}\n"
            f"Vela: {closed_ts}\n"
            f"Microvelas recibidas: "
            f"{len(candles_5s)}/12\n\n"
            "No se genera señal."
        )

        return

    # --------------------------------------------------------
    # 6. ANALIZAR ESTRATEGIA
    # --------------------------------------------------------

    result = analyze_market(
        closed_candle,
        candles_5s,
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

    # --------------------------------------------------------
    # 7. SI HAY SEÑAL, GUARDAR PARA N+1
    # --------------------------------------------------------

    if signal in (
        "call",
        "put",
    ):

        create_pending_signal(
            pair,
            closed_candle,
            candles_5s,
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
# ANALIZAR TODOS LOS PARES
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
        "======================================"
    )

    logger.info(
        "BOT DIGITAL OTC"
    )

    logger.info(
        "ESTRATEGIA 1M + 5S"
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
        "======================================"
    )

    # --------------------------------------------------------
    # VARIABLES
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CONEXIÓN
    # --------------------------------------------------------

    try:

        connect_iq()

    except Exception as exc:

        logger.exception(
            "No se pudo conectar a IQ Option."
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
        "ESTRATEGIA 1M + 5S\n\n"
        "CALL:\n"
        "🟢 Primera 5S > apertura 1M\n"
        "🔴 Retroceso 5S < apertura 1M\n"
        "🟢 Cierre 1M verde\n\n"
        "PUT:\n"
        "🔴 Primera 5S < apertura 1M\n"
        "🟢 Retroceso 5S > apertura 1M\n"
        "🔴 Cierre 1M rojo\n\n"
        "➡️ Entrada únicamente en N+1.\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto"
    )

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    while True:

        try:

            # Telegram
            check_commands()

            if not BOT_RUNNING:

                time.sleep(1)

                continue

            # IQ Option
            if not ensure_connection():

                time.sleep(2)

                continue

            # Analizar
            analyze_all_pairs()

            # Poll rápido.
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
        # ERROR GENERAL
        # ----------------------------------------------------

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
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
