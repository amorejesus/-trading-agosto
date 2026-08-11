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
    "GBPUSD-OTC"
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
# SEÑALES PENDIENTES
# ============================================================

PENDING_SIGNALS = {}


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
# TELEGRAM - COMANDOS
# ============================================================

def check_commands():

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

            # =================================================
            # START
            # =================================================

            if text == "/start":

                BOT_RUNNING = True

                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "Estrategia: CONTINUIDAD\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $100\n\n"
                    "La señal se analiza durante "
                    "la vela actual.\n\n"
                    "La dirección se mantiene durante "
                    "la vela mientras no exista "
                    "una invalidación fuerte.\n\n"
                    "La operación se ejecuta únicamente "
                    "en la apertura de la siguiente vela.\n\n"
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

            # =================================================
            # STOP
            # =================================================

            elif text == "/stop":

                BOT_RUNNING = False

                PENDING_SIGNALS.clear()

                telegram_send(
                    "🔴 BOT DETENIDO\n\n"
                    "No se abrirán nuevas operaciones.\n"
                    "Las señales pendientes fueron canceladas."
                )

                logger.info(
                    "BOT DETENIDO desde Telegram"
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

                pending_count = len(
                    PENDING_SIGNALS
                )

                telegram_send(
                    "📊 ESTADO DEL BOT\n\n"
                    f"Estado: {status}\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $100\n"
                    f"Pares: {len(PAIRS)}\n"
                    f"Señales pendientes: {pending_count}"
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
# COMPROBAR CONEXIÓN
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
        # NORMALIZAR COLUMNAS
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
# PRECIO APERTURA
# ============================================================

def get_candle_open(df):

    try:

        return float(
            df.iloc[-1]["open"]
        )

    except Exception:

        return None


# ============================================================
# PRECIO CIERRE ACTUAL
# ============================================================

def get_candle_close(df):

    try:

        return float(
            df.iloc[-1]["close"]
        )

    except Exception:

        return None


# ============================================================
# COOLDOWN
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

    return elapsed < TRADE_COOLDOWN


# ============================================================
# GUARDAR SEÑAL
# ============================================================

def save_pending_signal(
    pair,
    signal,
    df,
    candle_timestamp,
    result
):

    existing = PENDING_SIGNALS.get(
        pair
    )

    # --------------------------------------------------------
    # SI YA EXISTE UNA SEÑAL EN ESTA VELA
    # --------------------------------------------------------

    if existing:

        if (
            existing["candle_timestamp"]
            == candle_timestamp
        ):

            return False

    # --------------------------------------------------------
    # PRECIOS
    # --------------------------------------------------------

    candle_open = get_candle_open(
        df
    )

    candle_close = get_candle_close(
        df
    )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    PENDING_SIGNALS[pair] = {

        "signal": signal,

        "candle_timestamp":
            candle_timestamp,

        "candle_open":
            candle_open,

        "last_close":
            candle_close,

        "score":
            result.get(
                "score",
                0
            ),

        "created_at":
            time.time()
    }

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    telegram_send(
        "📢 CONTINUIDAD DETECTADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n"
        f"Score: {result.get('score', 0)}\n\n"
        "🕯 VELA DE CONTINUIDAD\n"
        f"Apertura: {candle_open}\n"
        f"Cierre actual: {candle_close}\n\n"
        "💾 SEÑAL GUARDADA\n"
        "La dirección se mantiene durante "
        "esta vela.\n\n"
        "⏳ NO SE EJECUTA EN ESTA VELA.\n"
        "Se espera la apertura de la siguiente."
    )

    logger.info(
        "%s | SEÑAL GUARDADA | %s | "
        "vela=%s | apertura=%s | cierre=%s",
        pair,
        signal.upper(),
        candle_timestamp,
        candle_open,
        candle_close
    )

    return True


# ============================================================
# ACTUALIZAR SEÑAL PENDIENTE
# ============================================================

def update_pending_signal(
    pair,
    df,
    result
):

    pending = PENDING_SIGNALS.get(
        pair
    )

    if not pending:
        return

    signal = pending["signal"]

    direction = result.get(
        "direction"
    )

    # --------------------------------------------------------
    # ACTUALIZAR CIERRE
    # --------------------------------------------------------

    current_close = get_candle_close(
        df
    )

    if current_close is not None:

        pending["last_close"] = (
            current_close
        )

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # Si la señal es CALL:
    # NO se convierte en PUT.
    #
    # Si la señal es PUT:
    # NO se convierte en CALL.
    #
    # Solo se cancela si la estrategia
    # deja de confirmar completamente
    # la dirección original.
    # --------------------------------------------------------

    valid_direction = (
        (
            signal == "call"
            and direction == "bullish"
        )
        or
        (
            signal == "put"
            and direction == "bearish"
        )
    )

    # --------------------------------------------------------
    # Si la estrategia dice otra dirección,
    # NO cambiar la señal.
    #
    # Se mantiene mientras no haya
    # invalidación estructural.
    # --------------------------------------------------------

    if valid_direction:

        pending["last_valid_check"] = (
            time.time()
        )

        return

    # --------------------------------------------------------
    # No cambiamos CALL por PUT ni PUT por CALL.
    #
    # La señal permanece.
    #
    # La comprobación final se hará
    # en la apertura de la siguiente vela.
    # --------------------------------------------------------

    logger.info(
        "%s | Señal %s mantenida. "
        "La dirección no cambia durante "
        "la misma vela.",
        pair,
        signal.upper()
    )


# ============================================================
# EJECUTAR SEÑAL PENDIENTE
# ============================================================

def execute_pending_signal(
    pair,
    df
):

    pending = PENDING_SIGNALS.get(
        pair
    )

    if not pending:
        return False

    current_timestamp = (
        get_candle_timestamp(df)
    )

    if current_timestamp is None:
        return False

    signal_timestamp = (
        pending["candle_timestamp"]
    )

    # ========================================================
    # PROTECCIÓN PRINCIPAL
    # ========================================================
    #
    # NO ejecutar mientras estemos
    # dentro de la misma vela.
    #
    # Solo:
    #
    # current > signal
    #
    # ========================================================

    if current_timestamp <= signal_timestamp:

        return False

    # ========================================================
    # APERTURA DE LA NUEVA VELA
    # ========================================================

    execution_open = get_candle_open(
        df
    )

    if execution_open is None:

        logger.warning(
            "%s | No se pudo obtener "
            "apertura de ejecución",
            pair
        )

        return False

    # ========================================================
    # COOLDOWN
    # ========================================================

    if cooldown_active(pair):

        logger.info(
            "%s | Cooldown activo. "
            "Se cancela señal.",
            pair
        )

        del PENDING_SIGNALS[pair]

        return False

    # ========================================================
    # EVITAR DOS OPERACIONES EN LA MISMA VELA
    # ========================================================

    if (
        LAST_TRADE_CANDLE.get(pair)
        == current_timestamp
    ):

        del PENDING_SIGNALS[pair]

        return False

    # ========================================================
    # DIRECCIÓN
    # ========================================================

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    # ========================================================
    # MENSAJE ANTES DE EJECUTAR
    # ========================================================

    telegram_send(
        "🚨 NUEVA VELA DE EJECUCIÓN\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"
        "🕯 VELA DE CONTINUIDAD\n"
        f"Apertura: {pending['candle_open']}\n"
        f"Cierre: {pending['last_close']}\n\n"
        "🕯 VELA DE EJECUCIÓN\n"
        f"Apertura: {execution_open}\n\n"
        "⚡ Ejecutando operación..."
    )

    # ========================================================
    # EJECUTAR
    # ========================================================

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
                f"Dirección: {signal.upper()}\n"
                f"Apertura: {execution_open}"
            )

            logger.error(
                "%s | Operación rechazada",
                pair
            )

            del PENDING_SIGNALS[pair]

            return False

        # ====================================================
        # GUARDAR OPERACIÓN
        # ====================================================

        LAST_TRADE_TIME[pair] = (
            time.time()
        )

        LAST_TRADE_CANDLE[pair] = (
            current_timestamp
        )

        # ====================================================
        # ELIMINAR SEÑAL
        # ====================================================

        del PENDING_SIGNALS[pair]

        # ====================================================
        # TELEGRAM
        # ====================================================

        telegram_send(
            "✅ OPERACIÓN ABIERTA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            "Importe: $100\n"
            "Expiración: 1 minuto\n\n"
            "🕯 CONTINUIDAD\n"
            f"Apertura: {pending['candle_open']}\n"
            f"Cierre: {pending['last_close']}\n\n"
            "🕯 EJECUCIÓN\n"
            f"Apertura: {execution_open}\n\n"
            f"ID: {order_id}"
        )

        logger.info(
            "%s | %s | $%s | "
            "VELA CONTINUIDAD=%s | "
            "VELA EJECUCIÓN=%s | "
            "APERTURA=%s | ID=%s",
            pair,
            signal.upper(),
            AMOUNT,
            signal_timestamp,
            current_timestamp,
            execution_open,
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

        del PENDING_SIGNALS[pair]

        return False


# ============================================================
# ANALIZAR PAR
# ============================================================

def analyze_pair(pair):

    # ========================================================
    # OBTENER VELAS
    # ========================================================

    df = get_candles(
        pair
    )

    if df is None:
        return

    # ========================================================
    # MÍNIMO 60 VELAS
    # ========================================================

    if len(df) < 60:

        logger.info(
            "%s | Esperando velas: %s/60",
            pair,
            len(df)
        )

        return

    # ========================================================
    # TIMESTAMP ACTUAL
    # ========================================================

    current_timestamp = (
        get_candle_timestamp(df)
    )

    if current_timestamp is None:
        return

    # ========================================================
    # 1. SI HAY SEÑAL PENDIENTE
    # ========================================================

    pending = PENDING_SIGNALS.get(
        pair
    )

    if pending:

        signal_timestamp = (
            pending["candle_timestamp"]
        )

        # ----------------------------------------------------
        # TODAVÍA ES LA MISMA VELA
        # ----------------------------------------------------

        if current_timestamp == signal_timestamp:

            # Actualizar cierre actual
            pending["last_close"] = (
                get_candle_close(df)
            )

        # ----------------------------------------------------
        # NUEVA VELA
        # ----------------------------------------------------

        elif current_timestamp > signal_timestamp:

            # Primero ejecutar la señal
            execute_pending_signal(
                pair,
                df
            )

    # ========================================================
    # 2. ANALIZAR VELA ACTUAL
    # ========================================================

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

    # ========================================================
    # LOG
    # ========================================================

    logger.info(
        "%s | tendencia=%s | señal=%s | "
        "score=%s | %s",
        pair,
        direction,
        signal,
        score,
        reason
    )

    # ========================================================
    # SI EXISTE UNA SEÑAL PENDIENTE
    # ========================================================

    pending = PENDING_SIGNALS.get(
        pair
    )

    if pending:

        # ----------------------------------------------------
        # ACTUALIZAR CIERRE
        # ----------------------------------------------------

        if (
            pending["candle_timestamp"]
            == current_timestamp
        ):

            update_pending_signal(
                pair,
                df,
                result
            )

        # ----------------------------------------------------
        # NO CREAR OTRA SEÑAL
        # ----------------------------------------------------

        return

    # ========================================================
    # SIN SEÑAL NUEVA
    # ========================================================

    if signal not in (
        "call",
        "put"
    ):

        return

    # ========================================================
    # GUARDAR SEÑAL
    # ========================================================

    save_pending_signal(
        pair,
        signal,
        df,
        current_timestamp,
        result
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

        # ----------------------------------------------------
        # Pequeña separación entre pares
        # ----------------------------------------------------

        time.sleep(0.20)


# ============================================================
# MAIN
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
        "ESTRATEGIA: CONTINUIDAD"
    )

    logger.info(
        "TEMPORALIDAD: 1 MINUTO"
    )

    logger.info(
        "EXPIRACIÓN: 1 MINUTO"
    )

    logger.info(
        "IMPORTE: $100"
    )

    logger.info(
        "========================================"
    )

    # ========================================================
    # VALIDAR VARIABLES
    # ========================================================

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

    # ========================================================
    # CONECTAR
    # ========================================================

    try:

        connect_iq()

    except Exception as e:

        logger.error(
            "No se pudo iniciar IQ Option: %s",
            e
        )

        telegram_send(
            "❌ NO SE PUDO CONECTAR A IQ OPTION\n\n"
            + str(e)
        )

        return

    # ========================================================
    # BOT LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "Conectado a IQ Option.\n\n"
        "Configuración:\n"
        "📊 Análisis: 1 minuto\n"
        "🕯 Estructura: máximo 60 velas\n"
        "🎯 Estrategia: continuidad\n"
        "💵 Importe: $100\n"
        "⏱ Expiración: 1 minuto\n\n"
        "La señal se mantiene durante "
        "la vela de continuidad.\n\n"
        "La operación se ejecuta únicamente "
        "en la apertura de la siguiente vela.\n\n"
        "Escribe /start para comenzar."
    )

    # ========================================================
    # LOOP PRINCIPAL
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
            # ANALIZAR
            # ------------------------------------------------

            analyze_all_pairs()

            # ------------------------------------------------
            # CICLO RÁPIDO
            # ------------------------------------------------

            time.sleep(0.40)

        except KeyboardInterrupt:

            BOT_RUNNING = False

            PENDING_SIGNALS.clear()

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
