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

AMOUNT = 10

TIMEFRAME = 60

EXPIRATION = 1

CANDLE_COUNT = 60


# ============================================================
# PARES OTC
# ============================================================

PAIRS = [
    "EURAUD-OTC",
]


# ============================================================
# CONTROL DEL BOT
# ============================================================

BOT_RUNNING = False

LAST_UPDATE_ID = None

IQ = None


# ============================================================
# CONTROL DE OPERACIONES
# ============================================================

LAST_TRADE_TIME = {}

LAST_TRADE_CANDLE = {}


# ============================================================
# CONTROL DE VELAS
# ============================================================

LAST_ANALYZED_CLOSED_CANDLE = {}

PENDING_SIGNALS = {}


# ============================================================
# COOLDOWN
# ============================================================

TRADE_COOLDOWN = 60


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
    Envía mensajes a Telegram.
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
                    f"Importe: ${AMOUNT}\n\n"
                    "La vela completa se analiza "
                    "desde apertura hasta cierre.\n\n"
                    "La decisión se toma al cierre "
                    "de la vela de confirmación.\n\n"
                    "La operación se intenta ejecutar "
                    "en la apertura de la siguiente vela."
                )

                logger.info(
                    "BOT ACTIVADO"
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
                    "BOT DETENIDO"
                )

            # ------------------------------------------------
            # STATUS
            # ------------------------------------------------

            elif text == "/status":

                if BOT_RUNNING:
                    status = "🟢 ACTIVO"
                else:
                    status = "🔴 DETENIDO"

                pending = len(
                    PENDING_SIGNALS
                )

                telegram_send(
                    "📊 ESTADO DEL BOT\n\n"
                    f"Estado: {status}\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    f"Importe: ${AMOUNT}\n"
                    f"Pares: {len(PAIRS)}\n"
                    f"Señales pendientes: {pending}\n\n"
                    "Entrada: apertura de nueva vela"
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
                    "%s falta en %s",
                    column,
                    pair
                )

                return None

        # ----------------------------------------------------
        # CONVERTIR A NUMÉRICOS
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
        # TIMESTAMP
        # ----------------------------------------------------

        if "from" not in df.columns:

            logger.error(
                "IQ Option no devolvió timestamp para %s",
                pair
            )

            return None

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce"
        )

        df.dropna(
            subset=["from"],
            inplace=True
        )

        df["from"] = df["from"].astype(
            int
        )

        # ----------------------------------------------------
        # ORDEN CRONOLÓGICO
        # ----------------------------------------------------

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
# TIMESTAMP DE LA VELA ACTUAL
# ============================================================

def get_current_candle_timestamp():

    now = int(
        time.time()
    )

    return (
        now
        - (now % TIMEFRAME)
    )


# ============================================================
# OBTENER VELA CERRADA
# ============================================================

def get_closed_candle_dataframe(df):

    if df is None:
        return None

    if df.empty:
        return None

    current_timestamp = (
        get_current_candle_timestamp()
    )

    data = df.copy()

    # --------------------------------------------------------
    # EXCLUIR VELA ACTUAL
    # --------------------------------------------------------

    data = data[
        data["from"]
        < current_timestamp
    ].copy()

    if data.empty:
        return None

    data.sort_values(
        "from",
        inplace=True
    )

    data.reset_index(
        drop=True,
        inplace=True
    )

    data = data.tail(
        CANDLE_COUNT
    ).copy()

    data.reset_index(
        drop=True,
        inplace=True
    )

    return data


# ============================================================
# TIMESTAMP ÚLTIMA VELA CERRADA
# ============================================================

def get_last_closed_timestamp(df):

    if df is None:
        return None

    if df.empty:
        return None

    try:

        return int(
            df.iloc[-1]["from"]
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
# ATR
# ============================================================

def calculate_atr(df):

    if df is None:
        return None

    if len(df) < 14:
        return None

    data = df.copy()

    previous_close = (
        data["close"].shift(1)
    )

    tr1 = (
        data["high"]
        - data["low"]
    )

    tr2 = (
        data["high"]
        - previous_close
    ).abs()

    tr3 = (
        data["low"]
        - previous_close
    ).abs()

    tr = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    atr = tr.tail(14).mean()

    if pd.isna(atr):
        return None

    if atr <= 0:
        return None

    return float(atr)


# ============================================================
# GUARDAR SEÑAL PENDIENTE
# ============================================================

def save_pending_signal(
    pair,
    signal,
    confirmation_timestamp,
    confirmation_candle,
    score,
    reason
):
    """
    La señal pertenece EXCLUSIVAMENTE a la siguiente vela.

    confirmation_timestamp:
        timestamp de la vela que acaba de cerrar.

    execution_timestamp:
        timestamp de la siguiente vela.
    """

    execution_timestamp = (
        confirmation_timestamp
        + TIMEFRAME
    )

    # --------------------------------------------------------
    # SEGURIDAD
    # --------------------------------------------------------

    if execution_timestamp <= confirmation_timestamp:

        logger.error(
            "%s | ERROR: timestamp de ejecución inválido",
            pair
        )

        return False

    PENDING_SIGNALS[pair] = {

        "signal": signal,

        "confirmation_timestamp":
            confirmation_timestamp,

        "execution_timestamp":
            execution_timestamp,

        "confirmation_open":
            float(
                confirmation_candle["open"]
            ),

        "confirmation_high":
            float(
                confirmation_candle["high"]
            ),

        "confirmation_low":
            float(
                confirmation_candle["low"]
            ),

        "confirmation_close":
            float(
                confirmation_candle["close"]
            ),

        "score":
            score,

        "reason":
            reason
    }

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    telegram_send(
        "📌 SEÑAL CONFIRMADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"

        "VELA DE CONFIRMACIÓN\n"
        f"Apertura: {confirmation_candle['open']}\n"
        f"Máximo: {confirmation_candle['high']}\n"
        f"Mínimo: {confirmation_candle['low']}\n"
        f"Cierre: {confirmation_candle['close']}\n\n"

        f"Score: {score}/10\n\n"

        "✅ Vela completamente cerrada\n"
        "✅ Señal guardada\n"
        "⛔ No se ejecuta en esta vela\n\n"

        "PRÓXIMA VELA\n"
        "⚡ Entrada en la apertura"
    )

    logger.info(
        "%s | SEÑAL GUARDADA | %s | "
        "confirmación=%s | ejecución=%s",
        pair,
        signal.upper(),
        confirmation_timestamp,
        execution_timestamp
    )

    return True


# ============================================================
# ANALIZAR VELA CERRADA
# ============================================================

def analyze_closed_candle(
    pair,
    df
):
    """
    Analiza ÚNICAMENTE la última vela completamente cerrada.

    La vela actual nunca se entrega a strategy.py.
    """

    closed_df = (
        get_closed_candle_dataframe(
            df
        )
    )

    if closed_df is None:

        return

    if len(closed_df) < 50:

        logger.info(
            "%s | Velas cerradas %s/50",
            pair,
            len(closed_df)
        )

        return

    closed_timestamp = (
        get_last_closed_timestamp(
            closed_df
        )
    )

    if closed_timestamp is None:
        return

    # --------------------------------------------------------
    # EVITAR ANALIZAR DOS VECES LA MISMA VELA
    # --------------------------------------------------------

    previous = (
        LAST_ANALYZED_CLOSED_CANDLE.get(
            pair
        )
    )

    if previous == closed_timestamp:

        return

    # --------------------------------------------------------
    # MARCAR VELA COMO ANALIZADA
    # --------------------------------------------------------

    LAST_ANALYZED_CLOSED_CANDLE[pair] = (
        closed_timestamp
    )

    # --------------------------------------------------------
    # ANALIZAR STRATEGY.PY
    # --------------------------------------------------------

    result = analyze_market(
        closed_df
    )

    signal = result.get(
        "signal"
    )

    direction = result.get(
        "direction"
    )

    reason = result.get(
        "reason",
        ""
    )

    score = result.get(
        "score",
        0
    )

    logger.info(
        "%s | CIERRE=%s | "
        "dirección=%s | señal=%s | "
        "score=%s | %s",
        pair,
        closed_timestamp,
        direction,
        signal,
        score,
        reason
    )

    # --------------------------------------------------------
    # SIN SEÑAL
    # --------------------------------------------------------

    if signal not in (
        "call",
        "put"
    ):

        return

    # --------------------------------------------------------
    # SI YA EXISTE UNA SEÑAL PARA ESTE PAR
    # --------------------------------------------------------

    if pair in PENDING_SIGNALS:

        pending = PENDING_SIGNALS[pair]

        if (
            pending["confirmation_timestamp"]
            == closed_timestamp
        ):

            return

    # --------------------------------------------------------
    # VELA DE CONFIRMACIÓN
    # --------------------------------------------------------

    confirmation_candle = (
        closed_df.iloc[-1]
    )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    save_pending_signal(
        pair=pair,
        signal=signal,
        confirmation_timestamp=closed_timestamp,
        confirmation_candle=confirmation_candle,
        score=score,
        reason=reason
    )


# ============================================================
# EJECUTAR SEÑAL EN APERTURA
# ============================================================

def execute_pending_signal(
    pair,
    df
):
    """
    EJECUCIÓN EN LA APERTURA DE LA NUEVA VELA.

    La señal fue generada por la vela anterior.

    Ejemplo:

        Vela 18:24
        timestamp = 123456

        ↓ cierre

        señal PUT

        ↓

        Vela 18:25
        timestamp = 123516

        ↓

        ejecutar PUT
    """

    pending = PENDING_SIGNALS.get(
        pair
    )

    if pending is None:
        return False

    # ========================================================
    # HORA ACTUAL
    # ========================================================

    now = time.time()

    current_timestamp = int(
        now - (
            now % TIMEFRAME
        )
    )

    # ========================================================
    # TIMESTAMP DE EJECUCIÓN
    # ========================================================

    execution_timestamp = int(
        pending["execution_timestamp"]
    )

    confirmation_timestamp = int(
        pending["confirmation_timestamp"]
    )

    # ========================================================
    # PROTECCIÓN ABSOLUTA
    # ========================================================

    if execution_timestamp <= confirmation_timestamp:

        logger.error(
            "%s | SEÑAL INVALIDADA | "
            "La vela de ejecución no es posterior.",
            pair
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # TODAVÍA NO LLEGÓ LA NUEVA VELA
    # ========================================================

    if current_timestamp < execution_timestamp:

        return False

    # ========================================================
    # SE PERDIÓ LA APERTURA
    # ========================================================

    if current_timestamp > execution_timestamp:

        logger.warning(
            "%s | SEÑAL CANCELADA | "
            "Se perdió la apertura de la vela.",
            pair
        )

        telegram_send(
            "⌛ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {pending['signal'].upper()}\n\n"
            "No se pudo ejecutar en la "
            "apertura de la nueva vela."
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # ESTAMOS EXACTAMENTE EN LA VELA DE EJECUCIÓN
    # ========================================================

    signal = pending["signal"]

    # ========================================================
    # EVITAR DUPLICAR OPERACIÓN
    # ========================================================

    previous_trade_candle = (
        LAST_TRADE_CANDLE.get(
            pair
        )
    )

    if (
        previous_trade_candle
        == execution_timestamp
    ):

        logger.warning(
            "%s | Operación duplicada bloqueada",
            pair
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # COOLDOWN
    # ========================================================

    if cooldown_active(pair):

        logger.info(
            "%s | Cooldown activo",
            pair
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        telegram_send(
            "⚠️ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            "Cooldown activo."
        )

        return False

    # ========================================================
    # BUSCAR LA NUEVA VELA
    # ========================================================

    if df is None:

        logger.warning(
            "%s | No hay dataframe para ejecución",
            pair
        )

        return False

    current_candle = df[
        df["from"]
        == execution_timestamp
    ]

    # --------------------------------------------------------
    # SI IQ OPTION TODAVÍA NO DEVOLVIÓ LA VELA
    # --------------------------------------------------------

    if current_candle.empty:

        logger.info(
            "%s | Nueva vela todavía no disponible "
            "en get_candles().",
            pair
        )

        return False

    current_candle = (
        current_candle.iloc[-1]
    )

    # ========================================================
    # IMPORTANTE:
    #
    # NO analizamos el movimiento de la nueva vela.
    #
    # No existe:
    # opening_movement_too_strong()
    #
    # porque queremos entrar en apertura.
    # ========================================================

    execution_open = float(
        current_candle["open"]
    )

    current_second = int(
        now % TIMEFRAME
    )

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    # ========================================================
    # LOG DE PRECISIÓN
    # ========================================================

    logger.info(
        "%s | APERTURA NUEVA VELA | "
        "timestamp=%s | segundo=%s.%03d | "
        "señal=%s | open=%s",
        pair,
        execution_timestamp,
        current_second,
        int(
            (now % 1) * 1000
        ),
        signal.upper(),
        execution_open
    )

    # ========================================================
    # TELEGRAM
    # ========================================================

    telegram_send(
        "⚡ ENTRADA EN APERTURA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"

        "VELA DE CONFIRMACIÓN\n"
        f"Apertura: {pending['confirmation_open']}\n"
        f"Máximo: {pending['confirmation_high']}\n"
        f"Mínimo: {pending['confirmation_low']}\n"
        f"Cierre: {pending['confirmation_close']}\n\n"

        "VELA NUEVA\n"
        f"Apertura: {execution_open}\n\n"

        f"Timestamp ejecución: {execution_timestamp}\n"
        f"Segundo detectado: {current_second:02d}\n\n"

        f"💵 Importe: ${AMOUNT}\n"
        "⏱️ Expiración: 1 minuto"
    )

    # ========================================================
    # EJECUTAR IQ OPTION
    # ========================================================

    try:

        status, order_id = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION
        )

        # ====================================================
        # IQ OPTION RECHAZÓ
        # ====================================================

        if not status:

            logger.error(
                "%s | OPERACIÓN RECHAZADA | "
                "signal=%s | timestamp=%s | "
                "segundo=%s | order_id=%s",
                pair,
                signal.upper(),
                execution_timestamp,
                current_second,
                order_id
            )

            telegram_send(
                "❌ OPERACIÓN RECHAZADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {signal.upper()}\n\n"
                f"Timestamp: {execution_timestamp}\n"
                f"Segundo: {current_second:02d}\n\n"
                "IQ Option rechazó la operación.\n\n"
                f"Respuesta: {order_id}"
            )

            PENDING_SIGNALS.pop(
                pair,
                None
            )

            return False

        # ====================================================
        # GUARDAR OPERACIÓN
        # ====================================================

        LAST_TRADE_TIME[pair] = (
            time.time()
        )

        LAST_TRADE_CANDLE[pair] = (
            execution_timestamp
        )

        # ====================================================
        # ELIMINAR SEÑAL
        # ====================================================

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        # ====================================================
        # CONFIRMACIÓN
        # ====================================================

        telegram_send(
            "✅ OPERACIÓN ABIERTA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"Entrada: {execution_open}\n"
            f"Importe: ${AMOUNT}\n"
            "Expiración: 1 minuto\n"
            f"Segundo detectado: {current_second:02d}\n"
            f"Timestamp: {execution_timestamp}\n"
            f"ID: {order_id}"
        )

        logger.info(
            "%s | OPERACIÓN ABIERTA | "
            "%s | $%s | entrada=%s | "
            "segundo=%s | timestamp=%s | ID=%s",
            pair,
            signal.upper(),
            AMOUNT,
            execution_open,
            current_second,
            execution_timestamp,
            order_id
        )

        return True

    except Exception as e:

        logger.exception(
            "%s | ERROR EJECUTANDO OPERACIÓN",
            pair
        )

        telegram_send(
            "❌ ERROR AL OPERAR\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"Error: {str(e)}"
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False


# ============================================================
# LIMPIAR SEÑALES VENCIDAS
# ============================================================

def clean_expired_signals():

    if not PENDING_SIGNALS:
        return

    current_timestamp = (
        get_current_candle_timestamp()
    )

    expired = []

    for pair, pending in (
        PENDING_SIGNALS.items()
    ):

        execution_timestamp = int(
            pending["execution_timestamp"]
        )

        # ----------------------------------------------------
        # SI YA PASÓ COMPLETAMENTE LA VELA
        # ----------------------------------------------------

        if current_timestamp > execution_timestamp:

            expired.append(
                pair
            )

    for pair in expired:

        pending = PENDING_SIGNALS.pop(
            pair,
            None
        )

        if pending:

            telegram_send(
                "⌛ SEÑAL CANCELADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {pending['signal'].upper()}\n\n"
                "No se ejecutó en la apertura "
                "de la nueva vela."
            )

            logger.info(
                "%s | Señal vencida",
                pair
            )


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(pair):

    # ========================================================
    # OBTENER DATOS
    # ========================================================

    df = get_candles(
        pair
    )

    if df is None:
        return

    # ========================================================
    # PRIORIDAD #1
    #
    # PRIMERO intentar ejecutar una señal pendiente.
    #
    # Esto es importante porque al comenzar una nueva vela
    # NO queremos gastar tiempo analizando antes de ejecutar.
    # ========================================================

    if pair in PENDING_SIGNALS:

        execute_pending_signal(
            pair,
            df
        )

    # ========================================================
    # PRIORIDAD #2
    #
    # DESPUÉS analizar la vela que acaba de cerrar.
    #
    # Esta señal quedará preparada para la PRÓXIMA vela.
    # ========================================================

    analyze_closed_candle(
        pair,
        df
    )


# ============================================================
# PROCESAR TODOS LOS PARES
# ============================================================

def process_all_pairs():

    if not BOT_RUNNING:
        return

    for pair in PAIRS:

        if not BOT_RUNNING:
            return

        try:

            process_pair(
                pair
            )

        except Exception as e:

            logger.exception(
                "Error procesando %s",
                pair
            )

        # ----------------------------------------------------
        # PAUSA MUY PEQUEÑA
        # ----------------------------------------------------

        time.sleep(0.03)


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
        "IMPORTE: $%s",
        AMOUNT
    )

    logger.info(
        "CONFIRMACIÓN: VELA COMPLETA"
    )

    logger.info(
        "ENTRADA: APERTURA DE NUEVA VELA"
    )

    logger.info(
        "========================================"
    )

    # ========================================================
    # VARIABLES
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
    # CONEXIÓN
    # ========================================================

    try:

        connect_iq()

    except Exception as e:

        logger.error(
            "No se pudo conectar: %s",
            e
        )

        telegram_send(
            "❌ No se pudo conectar a IQ Option.\n\n"
            + str(e)
        )

        return

    # ========================================================
    # BOT LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "Conectado a IQ Option.\n\n"
        "Estrategia: CONTINUIDAD\n"
        "Velas: 1 minuto\n"
        f"Importe: ${AMOUNT}\n"
        "Expiración: 1 minuto\n\n"

        "📖 LÓGICA\n"
        "La vela se analiza completa:\n"
        "Apertura → Máximo → Mínimo → Cierre\n\n"

        "La decisión se toma al cierre.\n\n"

        "⚡ ENTRADA\n"
        "La señal se ejecuta en la "
        "apertura de la siguiente vela.\n\n"

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
            # LIMPIAR SEÑALES
            # ------------------------------------------------

            clean_expired_signals()

            # ------------------------------------------------
            # BOT DETENIDO
            # ------------------------------------------------

            if not BOT_RUNNING:

                time.sleep(0.5)

                continue

            # ------------------------------------------------
            # CONEXIÓN
            # ------------------------------------------------

            if not ensure_connection():

                time.sleep(3)

                continue

            # ------------------------------------------------
            # PROCESAR MERCADO
            # ------------------------------------------------

            process_all_pairs()

            # ------------------------------------------------
            # LOOP RÁPIDO
            # ------------------------------------------------

            time.sleep(0.03)

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

            time.sleep(3)


# ============================================================
# ARRANQUE
# ============================================================

if __name__ == "__main__":

    main()
