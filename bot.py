import os
import time
import logging
import requests
import pandas as pd

from datetime import datetime

from iqoptionapi.stable_api import IQ_Option

from strategy import analyze_market


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Importe solicitado
AMOUNT = 100

# Velas de 1 minuto
TIMEFRAME = 60

# Expiración 1 minuto
EXPIRATION = 1

# Pares OTC
PAIRS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "EURJPY-OTC",
]

# Máximo de velas analizadas
CANDLE_COUNT = 60

# Tiempo mínimo entre operaciones del mismo par
TRADE_COOLDOWN = 60

# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

LAST_UPDATE_ID = None

LAST_TRADE_TIME = {}

LAST_TRADE_CANDLE = {}

IQ = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(
            url,
            data=data,
            timeout=10
        )

    except Exception as e:

        logger.error(
            f"Error Telegram: {e}"
        )


# ============================================================
# TELEGRAM COMMANDS
# ============================================================

def check_commands():

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/getUpdates"
    )

    params = {
        "timeout": 1
    }

    if LAST_UPDATE_ID is not None:

        params["offset"] = LAST_UPDATE_ID + 1

    try:

        response = requests.get(
            url,
            params=params,
            timeout=5
        )

        data = response.json()

        if not data.get("ok"):
            return

        for update in data.get("result", []):

            LAST_UPDATE_ID = update["update_id"]

            message = update.get(
                "message",
                {}
            )

            text = message.get(
                "text",
                ""
            ).strip().lower()

            chat_id = str(
                message.get(
                    "chat",
                    {}
                ).get(
                    "id",
                    ""
                )
            )

            # Seguridad: solo el chat configurado
            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text == "/start":

                BOT_RUNNING = True

                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "Estrategia: CONTINUIDAD\n"
                    "Marco: 1 minuto\n"
                    "Importe: $100\n\n"
                    "Filtros activos:\n"
                    "• Tendencia\n"
                    "• Estructura 60 velas\n"
                    "• Sin rechazo\n"
                    "• Sin soporte/resistencia\n"
                    "• Sin pullback\n"
                    "• Sin debilidad\n"
                    "• Sin final de tendencia"
                )

            elif text == "/stop":

                BOT_RUNNING = False

                telegram_send(
                    "🔴 BOT DETENIDO"
                )

            elif text == "/status":

                estado = (
                    "ACTIVO"
                    if BOT_RUNNING
                    else "DETENIDO"
                )

                telegram_send(
                    f"📊 Estado: {estado}\n"
                    f"💵 Importe: ${AMOUNT}\n"
                    f"⏱ Expiración: 1 minuto"
                )

    except Exception as e:

        logger.error(
            f"Telegram error: {e}"
        )


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():

    global IQ

    if not IQ_EMAIL or not IQ_PASSWORD:

        raise ValueError(
            "Faltan IQ_EMAIL o IQ_PASSWORD"
        )

    logger.info(
        "Conectando a IQ Option..."
    )

    IQ = IQ_Option(
        IQ_EMAIL,
        IQ_PASSWORD
    )

    check, reason = IQ.connect()

    if not check:

        raise ConnectionError(
            f"No se pudo conectar a IQ Option: {reason}"
        )

    logger.info(
        "Conectado correctamente a IQ Option"
    )

    telegram_send(
        "🟢 Conectado a IQ Option"
    )

    return IQ


# ============================================================
# RECONEXIÓN
# ============================================================

def ensure_connection():

    global IQ

    try:

        if IQ is None:
            connect_iq()
            return True

        if not IQ.check_connect():

            logger.warning(
                "Conexión perdida. Reconectando..."
            )

            check, reason = IQ.connect()

            if not check:

                telegram_send(
                    f"⚠️ Error reconectando: {reason}"
                )

                return False

        return True

    except Exception as e:

        logger.error(
            f"Error conexión: {e}"
        )

        return False


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(pair):

    try:

        candles = IQ.get_candles(
            pair,
            TIMEFRAME,
            CANDLE_COUNT,
            time.time()
        )

        if not candles:
            return None

        df = pd.DataFrame(candles)

        if df.empty:
            return None

        # Normalizar columnas
        df = df.rename(
            columns={
                "max": "high",
                "min": "low"
            }
        )

        required = [
            "open",
            "close",
            "high",
            "low"
        ]

        for column in required:

            if column not in df.columns:
                return None

        # timestamp
        if "from" in df.columns:

            df["timestamp"] = pd.to_datetime(
                df["from"],
                unit="s"
            )

        df = df.sort_values(
            "from"
        ).reset_index(
            drop=True
        )

        return df

    except Exception as e:

        logger.error(
            f"Error obteniendo velas {pair}: {e}"
        )

        return None


# ============================================================
# VELA ACTUAL
# ============================================================

def get_current_candle_timestamp(df):

    if df is None or df.empty:
        return None

    return int(
        df.iloc[-1]["from"]
    )


# ============================================================
# EJECUTAR OPERACIÓN
# ============================================================

def execute_trade(pair, direction):

    global LAST_TRADE_TIME
    global LAST_TRADE_CANDLE

    now = time.time()

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    previous_trade = LAST_TRADE_TIME.get(
        pair,
        0
    )

    if now - previous_trade < TRADE_COOLDOWN:

        return False

    # --------------------------------------------------------
    # OPERACIÓN
    # --------------------------------------------------------

    try:

        action = (
            "call"
            if direction == "call"
            else "put"
        )

        telegram_send(
            f"📈 SEÑAL CONFIRMADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {action.upper()}\n"
            f"Importe: ${AMOUNT}\n"
            f"Expiración: 1 minuto\n"
            f"Motivo: CONTINUIDAD"
        )

        status, order_id = IQ.buy(
            AMOUNT,
            pair,
            action,
            EXPIRATION
        )

        if not status:

            telegram_send(
                f"❌ OPERACIÓN RECHAZADA\n"
                f"{pair}"
            )

            return False

        LAST_TRADE_TIME[pair] = now

        telegram_send(
            f"✅ OPERACIÓN ABIERTA\n\n"
            f"{pair}\n"
            f"{action.upper()}\n"
            f"${AMOUNT}\n"
            f"Expiración: 1 minuto\n"
            f"ID: {order_id}"
        )

        return True

    except Exception as e:

        logger.error(
            f"Error ejecutando operación: {e}"
        )

        telegram_send(
            f"❌ ERROR OPERACIÓN\n"
            f"{pair}\n"
            f"{str(e)}"
        )

        return False


# ============================================================
# ANALIZAR PAR
# ============================================================

def analyze_pair(pair):

    df = get_candles(pair)

    if df is None:
        return

    if len(df) < 60:
        return

    # --------------------------------------------------------
    # IMPORTANTE
    #
    # La última vela puede estar actualmente formándose.
    # La estrategia recibe las últimas 60 velas y analiza
    # también el cierre/precio actual de esa vela.
    # --------------------------------------------------------

    result = analyze_market(df)

    signal = result.get(
        "signal"
    )

    reason = result.get(
        "reason"
    )

    direction = result.get(
        "direction"
    )

    score = result.get(
        "score",
        0
    )

    # --------------------------------------------------------
    # SIN OPERACIÓN
    # --------------------------------------------------------

    if signal is None:

        logger.info(
            f"{pair} | "
            f"{direction} | "
            f"NO OPERAR | "
            f"{reason}"
        )

        return

    # --------------------------------------------------------
    # EVITAR REPETIR LA MISMA VELA
    # --------------------------------------------------------

    candle_timestamp = (
        get_current_candle_timestamp(df)
    )

    if candle_timestamp is None:
        return

    if LAST_TRADE_CANDLE.get(pair) == candle_timestamp:

        return

    # --------------------------------------------------------
    # ENTRADA
    # --------------------------------------------------------

    logger.info(
        f"{pair} | "
        f"SEÑAL {signal.upper()} | "
        f"SCORE {score}"
    )

    success = execute_trade(
        pair,
        signal
    )

    if success:

        LAST_TRADE_CANDLE[pair] = (
            candle_timestamp
        )


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():

    global BOT_RUNNING

    telegram_send(
        "🤖 BOT INICIADO\n\n"
        "Esperando /start"
    )

    while True:

        try:

            # Telegram siempre se revisa
            check_commands()

            # Si está detenido no opera
            if not BOT_RUNNING:

                time.sleep(1)
                continue

            # Verificar conexión
            if not ensure_connection():

                time.sleep(5)
                continue

            # ------------------------------------------------
            # ANALIZAR TODOS LOS PARES
            # ------------------------------------------------

            for pair in PAIRS:

                if not BOT_RUNNING:
                    break

                try:

                    analyze_pair(pair)

                except Exception as e:

                    logger.error(
                        f"Error analizando "
                        f"{pair}: {e}"
                    )

                # pequeña pausa
                time.sleep(0.3)

            # No saturar API
            time.sleep(1)

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            break

        except Exception as e:

            logger.error(
                f"Error principal: {e}"
            )

            time.sleep(3)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
