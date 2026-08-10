import os
import time
import logging
import requests
import pandas as pd

from iqoptionapi.stable_api import IQ_Option

from strategy import analyze_market


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TRADING
# ============================================================

AMOUNT = 100

TIMEFRAME = 60

EXPIRATION = 1

CANDLE_COUNT = 60


# ============================================================
# PARES OTC
# ============================================================

PAIRS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "EURJPY-OTC",
]


# ============================================================
# CONTROL
# ============================================================

TRADE_COOLDOWN = 60

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
    """
    Envía un mensaje al chat configurado.
    """

    if not TELEGRAM_TOKEN:
        logger.warning(
            "TELEGRAM_TOKEN no configurado"
        )
        return False

    if not TELEGRAM_CHAT_ID:
        logger.warning(
            "TELEGRAM_CHAT_ID no configurado"
        )
        return False

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:

        response = requests.post(
            url,
            data=data,
            timeout=10
        )

        if response.status_code != 200:

            logger.error(
                "Telegram respondió: %s",
                response.text
            )

            return False

        return True

    except Exception as e:

        logger.error(
            "Error enviando Telegram: %s",
            e
        )

        return False


# ============================================================
# COMANDOS TELEGRAM
# ============================================================

def check_commands():
    """
    Lee /start, /stop y /status.
    """

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/getUpdates"
    )

    params = {
        "timeout": 1
    }

    if LAST_UPDATE_ID is not None:

        params["offset"] = (
            LAST_UPDATE_ID + 1
        )

    try:

        response = requests.get(
            url,
            params=params,
            timeout=5
        )

        data = response.json()

        if not data.get("ok"):
            return

        updates = data.get(
            "result",
            []
        )

        for update in updates:

            LAST_UPDATE_ID = update[
                "update_id"
            ]

            message = update.get(
                "message",
                {}
            )

            text = message.get(
                "text",
                ""
            )

            text = text.strip().lower()

            chat = message.get(
                "chat",
                {}
            )

            chat_id = str(
                chat.get(
                    "id",
                    ""
                )
            )

            # ------------------------------------------------
            # SEGURIDAD
            # ------------------------------------------------

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
                    "Estrategia: CONTINUIDAD\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $100\n\n"
                    "Filtros:\n"
                    "✅ Tendencia\n"
                    "✅ Estructura 1M\n"
                    "✅ Máximo 60 velas\n"
                    "✅ Continuidad\n"
                    "❌ Final de tendencia\n"
                    "❌ Rechazo\n"
                    "❌ Soporte/resistencia\n"
                    "❌ Pullback\n"
                    "❌ Debilidad"
                )

                logger.info(
                    "BOT ACTIVADO desde Telegram"
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

                logger.info(
                    "BOT DETENIDO desde Telegram"
                )

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            elif text == "/status":

                if BOT_RUNNING:

                    status = "🟢 ACTIVO"

                else:

                    status = "🔴 DETENIDO"

                telegram_send(
                    "📊 ESTADO DEL BOT\n\n"
                    f"Estado: {status}\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $100\n"
                    f"Pares: {len(PAIRS)}"
                )

    except Exception as e:

        logger.error(
            "Error leyendo Telegram: %s",
            e
        )


# ============================================================
# CONECTAR IQ OPTION
# ============================================================

def connect_iq():
    """
    Conecta con IQ Option.
    """

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
        IQ_PASSWORD
    )

    connected, reason = IQ.connect()

    if not connected:

        raise ConnectionError(
            "No se pudo conectar a IQ Option: "
            + str(reason)
        )

    logger.info(
        "Conectado correctamente a IQ Option"
    )

    telegram_send(
        "🟢 CONECTADO A IQ OPTION\n\n"
        "El bot está listo."
    )

    return True


# ============================================================
# VERIFICAR CONEXIÓN
# ============================================================

def ensure_connection():

    global IQ

    try:

        if IQ is None:

            connect_iq()

            return True

        if not IQ.check_connect():

            logger.warning(
                "Conexión IQ Option perdida."
            )

            telegram_send(
                "⚠️ Conexión IQ Option perdida.\n"
                "Intentando reconectar..."
            )

            connected, reason = IQ.connect()

            if not connected:

                logger.error(
                    "No se pudo reconectar: %s",
                    reason
                )

                return False

            telegram_send(
                "🟢 IQ Option reconectado."
            )

        return True

    except Exception as e:

        logger.error(
            "Error de conexión: %s",
            e
        )

        return False


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(pair):
    """
    Obtiene las últimas 60 velas de 1 minuto.
    """

    if IQ is None:
        return None

    try:

        candles = IQ.get_candles(
            pair,
            TIMEFRAME,
            CANDLE_COUNT,
            time.time()
        )

        if not candles:

            logger.warning(
                "%s no devolvió velas",
                pair
            )

            return None

        df = pd.DataFrame(
            candles
        )

        if df.empty:
            return None

        # ----------------------------------------------------
        # NORMALIZAR COLUMNAS IQ OPTION
        # ----------------------------------------------------

        df.rename(
            columns={
                "max": "high",
                "min": "low"
            },
            inplace=True
        )

        required = [
            "open",
            "close",
            "high",
            "low"
        ]

        for column in required:

            if column not in df.columns:

                logger.error(
                    "%s falta en velas de %s",
                    column,
                    pair
                )

                return None

        # ----------------------------------------------------
        # CONVERTIR A NÚMEROS
        # ----------------------------------------------------

        for column in required:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df.dropna(
            subset=required,
            inplace=True
        )

        # ----------------------------------------------------
        # ORDEN CRONOLÓGICO
        # ----------------------------------------------------

        if "from" in df.columns:

            df["from"] = pd.to_numeric(
                df["from"],
                errors="coerce"
            )

            df.sort_values(
                "from",
                inplace=True
            )

        df.reset_index(
            drop=True,
            inplace=True
        )

        return df

    except Exception as e:

        logger.error(
            "Error obteniendo velas %s: %s",
            pair,
            e
        )

        return None


# ============================================================
# TIMESTAMP DE VELA
# ============================================================

def get_candle_timestamp(df):

    if df is None:
        return None

    if df.empty:
        return None

    if "from" not in df.columns:
        return None

    try:

        return int(
            df.iloc[-1]["from"]
        )

    except Exception:

        return None


# ============================================================
# COMPROBAR COOLDOWN
# ============================================================

def cooldown_active(pair):

    last_time = LAST_TRADE_TIME.get(
        pair,
        0
    )

    elapsed = (
        time.time()
        - last_time
    )

    if elapsed < TRADE_COOLDOWN:

        return True

    return False


# ============================================================
# EJECUTAR OPERACIÓN
# ============================================================

def execute_trade(
    pair,
    signal,
    candle_timestamp
):
    """
    Ejecuta CALL o PUT por $100
    con expiración de 1 minuto.
    """

    global LAST_TRADE_TIME
    global LAST_TRADE_CANDLE

    # --------------------------------------------------------
    # EVITAR OPERAR LA MISMA VELA
    # --------------------------------------------------------

    previous_candle = (
        LAST_TRADE_CANDLE.get(
            pair
        )
    )

    if (
        previous_candle
        == candle_timestamp
    ):

        logger.info(
            "%s | Ya se operó esta vela",
            pair
        )

        return False

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    if cooldown_active(pair):

        logger.info(
            "%s | Cooldown activo",
            pair
        )

        return False

    # --------------------------------------------------------
    # VALIDAR SEÑAL
    # --------------------------------------------------------

    if signal not in (
        "call",
        "put"
    ):

        return False

    # --------------------------------------------------------
    # MENSAJE PREVIO
    # --------------------------------------------------------

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    telegram_send(
        "📢 SEÑAL DE CONTINUIDAD\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n"
        "Temporalidad: 1 minuto\n"
        "Expiración: 1 minuto\n"
        "Importe: $100\n\n"
        "✅ Tendencia confirmada\n"
        "✅ Estructura confirmada\n"
        "✅ Continuidad confirmada"
    )

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    try:

        status, order_id = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION
        )

        if not status:

            telegram_send(
                "❌ OPERACIÓN RECHAZADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {signal.upper()}"
            )

            logger.error(
                "%s | Operación rechazada",
                pair
            )

            return False

        # ----------------------------------------------------
        # GUARDAR OPERACIÓN
        # ----------------------------------------------------

        LAST_TRADE_TIME[pair] = (
            time.time()
        )

        LAST_TRADE_CANDLE[pair] = (
            candle_timestamp
        )

        telegram_send(
            "✅ OPERACIÓN ABIERTA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            "Importe: $100\n"
            "Expiración: 1 minuto\n"
            f"ID: {order_id}"
        )

        logger.info(
            "%s | %s | $%s | ID=%s",
            pair,
            signal.upper(),
            AMOUNT,
            order_id
        )

        return True

    except Exception as e:

        logger.error(
            "Error ejecutando operación %s: %s",
            pair,
            e
        )

        telegram_send(
            "❌ ERROR AL OPERAR\n\n"
            f"Par: {pair}\n"
            f"Error: {str(e)}"
        )

        return False


# ============================================================
# ANALIZAR PAR
# ============================================================

def analyze_pair(pair):

    # --------------------------------------------------------
    # OBTENER VELAS
    # --------------------------------------------------------

    df = get_candles(
        pair
    )

    if df is None:
        return

    # --------------------------------------------------------
    # NECESITAMOS 60 VELAS
    # --------------------------------------------------------

    if len(df) < 60:

        logger.info(
            "%s | Esperando velas: %s/60",
            pair,
            len(df)
        )

        return

    # --------------------------------------------------------
    # ANALIZAR ESTRATEGIA
    # --------------------------------------------------------

    result = analyze_market(
        df
    )

    signal = result.get(
        "signal"
    )

    direction = result.get(
        "direction"
    )

    reason = result.get(
        "reason"
    )

    score = result.get(
        "score",
        0
    )

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    logger.info(
        "%s | tendencia=%s | señal=%s | "
        "score=%s | %s",
        pair,
        direction,
        signal,
        score,
        reason
    )

    # --------------------------------------------------------
    # SIN SEÑAL
    # --------------------------------------------------------

    if signal is None:
        return

    # --------------------------------------------------------
    # TIMESTAMP DE VELA
    # --------------------------------------------------------

    candle_timestamp = (
        get_candle_timestamp(
            df
        )
    )

    if candle_timestamp is None:
        return

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    execute_trade(
        pair,
        signal,
        candle_timestamp
    )


# ============================================================
# ANALIZAR TODOS LOS PARES
# ============================================================

def analyze_all_pairs():

    for pair in PAIRS:

        if not BOT_RUNNING:
            return

        try:

            analyze_pair(
                pair
            )

        except Exception as e:

            logger.error(
                "Error analizando %s: %s",
                pair,
                e
            )

        # Pequeña separación entre peticiones
        time.sleep(0.5)


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():

    global BOT_RUNNING

    logger.info(
        "========================================"
    )

    logger.info(
        "BOT IQ OPTION INICIANDO"
    )

    logger.info(
        "Estrategia: CONTINUIDAD"
    )

    logger.info(
        "Temporalidad: 1 MINUTO"
    )

    logger.info(
        "Importe: $100"
    )

    logger.info(
        "========================================"
    )

    # --------------------------------------------------------
    # VALIDAR VARIABLES
    # --------------------------------------------------------

    if not IQ_EMAIL:

        logger.error(
            "IQ_EMAIL no configurado"
        )

        telegram_send(
            "❌ Falta IQ_EMAIL en Railway."
        )

        return

    if not IQ_PASSWORD:

        logger.error(
            "IQ_PASSWORD no configurado"
        )

        telegram_send(
            "❌ Falta IQ_PASSWORD en Railway."
        )

        return

    if not TELEGRAM_TOKEN:

        logger.error(
            "TELEGRAM_TOKEN no configurado"
        )

        return

    if not TELEGRAM_CHAT_ID:

        logger.error(
            "TELEGRAM_CHAT_ID no configurado"
        )

        return

    # --------------------------------------------------------
    # CONECTAR IQ OPTION
    # --------------------------------------------------------

    try:

        connect_iq()

    except Exception as e:

        logger.error(
            "No se pudo iniciar IQ Option: %s",
            e
        )

        telegram_send(
            "❌ No se pudo conectar a IQ Option.\n\n"
            + str(e)
        )

        return

    # --------------------------------------------------------
    # BOT ESPERANDO /START
    # --------------------------------------------------------

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "Conectado a IQ Option.\n"
        "Escribe /start para comenzar.\n"
        "Escribe /status para consultar estado."
    )

    # ========================================================
    # LOOP
    # ========================================================

    while True:

        try:

            # ------------------------------------------------
            # TELEGRAM
            # ------------------------------------------------

            check_commands()

            # ------------------------------------------------
            # BOT DETENIDO
            # ------------------------------------------------

            if not BOT_RUNNING:

                time.sleep(1)

                continue

            # ------------------------------------------------
            # CONEXIÓN
            # ------------------------------------------------

            if not ensure_connection():

                time.sleep(5)

                continue

            # ------------------------------------------------
            # ANALIZAR MERCADO
            # ------------------------------------------------

            analyze_all_pairs()

            # ------------------------------------------------
            # PAUSA
            # ------------------------------------------------

            time.sleep(1)

        except KeyboardInterrupt:

            BOT_RUNNING = False

            logger.info(
                "Bot detenido manualmente."
            )

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            break

        except Exception as e:

            logger.exception(
                "Error en loop principal"
            )

            telegram_send(
                "⚠️ ERROR EN BOT\n\n"
                + str(e)
            )

            time.sleep(5)


# ============================================================
# ARRANQUE
# ============================================================

if __name__ == "__main__":

    main()
