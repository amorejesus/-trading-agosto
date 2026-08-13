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
    "AUDUSD-OTC",
    "EURCHF-OTC",
    "USDZAR-OTC",
]


# ============================================================
# CONTROL
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
# VENTANA DE EJECUCIÓN
# ============================================================

EXECUTION_SECOND_START = 1

EXECUTION_SECOND_END = 3


# ============================================================
# FILTRO DE MOVIMIENTO INICIAL
# ============================================================

MAX_OPENING_RANGE_ATR = 0.60

MAX_OPENING_BODY_ATR = 0.45


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
    Envía mensaje a Telegram.
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
                    "Importe: $100\n\n"
                    "La señal se confirma "
                    "al cierre de la vela.\n\n"
                    "La ejecución se realiza "
                    "únicamente en los segundos "
                    "01–03 de la siguiente vela."
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
                    "Importe: $100\n"
                    f"Pares: {len(PAIRS)}\n"
                    f"Señales pendientes: {pending}"
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
        # NORMALIZAR
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
        # NUMÉRICOS
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
                "IQ Option no devolvió timestamp "
                "para %s",
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
        # ORDEN
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
# OBTENER TIMESTAMP DE LA VELA ACTUAL
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
# OBTENER SEGUNDO ACTUAL
# ============================================================

def get_current_second():

    now = time.time()

    return int(
        now % TIMEFRAME
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
    # ELIMINAR LA VELA ACTUAL
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

    # --------------------------------------------------------
    # MÁXIMO 60 VELAS CERRADAS
    # --------------------------------------------------------

    data = data.tail(
        CANDLE_COUNT
    ).copy()

    data.reset_index(
        drop=True,
        inplace=True
    )

    return data


# ============================================================
# TIMESTAMP DE LA ÚLTIMA VELA CERRADA
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
# CALCULAR ATR DE LA VELA CERRADA
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
# COMPROBAR MOVIMIENTO DE APERTURA
# ============================================================

def opening_movement_too_strong(
    current_candle,
    previous_df,
    signal
):
    """
    Comprueba el movimiento de la NUEVA vela.

    No queremos entrar si en los segundos 01–03
    la nueva vela ya hizo un movimiento demasiado fuerte.
    """

    if current_candle is None:
        return True

    if previous_df is None:
        return True

    atr = calculate_atr(
        previous_df
    )

    if atr is None:
        return True

    candle_open = float(
        current_candle["open"]
    )

    candle_high = float(
        current_candle["high"]
    )

    candle_low = float(
        current_candle["low"]
    )

    candle_close = float(
        current_candle["close"]
    )

    candle_range = (
        candle_high
        - candle_low
    )

    body = abs(
        candle_close
        - candle_open
    )

    # --------------------------------------------------------
    # RANGO INICIAL
    # --------------------------------------------------------

    if (
        candle_range
        > atr * MAX_OPENING_RANGE_ATR
    ):

        return True

    # --------------------------------------------------------
    # CUERPO INICIAL
    # --------------------------------------------------------

    if (
        body
        > atr * MAX_OPENING_BODY_ATR
    ):

        return True

    # --------------------------------------------------------
    # MOVIMIENTO EN CONTRA
    # --------------------------------------------------------

    if signal == "call":

        movement_against = (
            candle_open
            - candle_low
        )

        if (
            movement_against
            > atr * 0.40
        ):

            return True

    elif signal == "put":

        movement_against = (
            candle_high
            - candle_open
        )

        if (
            movement_against
            > atr * 0.40
        ):

            return True

    return False


# ============================================================
# OBTENER VELA ACTUAL
# ============================================================

def get_current_candle(
    pair
):

    df = get_candles(
        pair
    )

    if df is None:
        return None

    current_timestamp = (
        get_current_candle_timestamp()
    )

    current = df[
        df["from"]
        == current_timestamp
    ]

    if current.empty:

        return None

    return current.iloc[-1]


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
    Guarda la señal para ejecutarla
    solamente en la siguiente vela.
    """

    execution_timestamp = (
        confirmation_timestamp
        + TIMEFRAME
    )

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
        "📌 CONTINUIDAD CONFIRMADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"
        "VELA DE CONFIRMACIÓN\n"
        f"Apertura: {confirmation_candle['open']}\n"
        f"Máximo: {confirmation_candle['high']}\n"
        f"Mínimo: {confirmation_candle['low']}\n"
        f"Cierre: {confirmation_candle['close']}\n\n"
        f"Score: {score}/8\n\n"
        "✅ Señal guardada\n"
        "⏳ NO se ejecuta en esta vela\n\n"
        "PRÓXIMA VELA\n"
        "⏱️ Ejecución permitida: segundo 01–03"
    )

    logger.info(
        "%s | Señal guardada | %s | "
        "confirmación=%s | ejecución=%s",
        pair,
        signal.upper(),
        confirmation_timestamp,
        execution_timestamp
    )


# ============================================================
# ANALIZAR VELA CERRADA
# ============================================================

def analyze_closed_candle(
    pair,
    df
):
    """
    Analiza exclusivamente la última vela CERRADA.

    Nunca pasa la vela actual en formación a strategy.py.
    """

    closed_df = (
        get_closed_candle_dataframe(
            df
        )
    )

    if closed_df is None:

        logger.warning(
            "%s | No hay vela cerrada",
            pair
        )

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
    # NO ANALIZAR DOS VECES LA MISMA VELA
    # --------------------------------------------------------

    previous = (
        LAST_ANALYZED_CLOSED_CANDLE.get(
            pair
        )
    )

    if previous == closed_timestamp:

        return

    # --------------------------------------------------------
    # MARCAR COMO ANALIZADA
    # --------------------------------------------------------

    LAST_ANALYZED_CLOSED_CANDLE[pair] = (
        closed_timestamp
    )

    # --------------------------------------------------------
    # ANALIZAR ESTRATEGIA
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
        "%s | CIERRE %s | tendencia=%s | "
        "señal=%s | score=%s | %s",
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
    # EVITAR SEÑAL DUPLICADA
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
# ELIMINAR SEÑALES VENCIDAS
# ============================================================

def clean_expired_signals():

    if not PENDING_SIGNALS:
        return

    now = int(
        time.time()
    )

    expired = []

    for pair, pending in (
        PENDING_SIGNALS.items()
    ):

        execution_timestamp = (
            pending["execution_timestamp"]
        )

        # ----------------------------------------------------
        # SI PASÓ LA VELA DE EJECUCIÓN
        # ----------------------------------------------------

        if now >= (
            execution_timestamp
            + TIMEFRAME
        ):

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
                "No se ejecutó dentro de "
                "la ventana permitida 01–03."
            )

            logger.info(
                "%s | Señal vencida",
                pair
            )


# ============================================================
# EJECUTAR SEÑAL PENDIENTE
# ============================================================

def execute_pending_signal(
    pair
):
    """
    Ejecuta únicamente:

    segundo 01
    segundo 02
    segundo 03

    de la siguiente vela.
    """

    pending = PENDING_SIGNALS.get(
        pair
    )

    if pending is None:
        return False

    now = time.time()

    current_timestamp = int(
        now - (
            now % TIMEFRAME
        )
    )

    current_second = int(
        now % TIMEFRAME
    )

    execution_timestamp = (
        pending["execution_timestamp"]
    )

    # ========================================================
    # TODAVÍA NO ES LA VELA DE EJECUCIÓN
    # ========================================================

    if current_timestamp < execution_timestamp:

        return False

    # ========================================================
    # YA PASÓ LA VELA DE EJECUCIÓN
    # ========================================================

    if current_timestamp > execution_timestamp:

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        logger.info(
            "%s | Señal vencida antes de ejecutar",
            pair
        )

        return False

    # ========================================================
    # SOLO SEGUNDOS 01–03
    # ========================================================

    if (
        current_second
        < EXECUTION_SECOND_START
        or
        current_second
        > EXECUTION_SECOND_END
    ):

        # Si ya pasó el segundo 03,
        # cancelar la señal.
        if (
            current_second
            > EXECUTION_SECOND_END
        ):

            PENDING_SIGNALS.pop(
                pair,
                None
            )

            telegram_send(
                "⌛ SEÑAL CANCELADA\n\n"
                f"Par: {pair}\n"
                "Se perdió la ventana "
                "de ejecución 01–03."
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

        return False

    # ========================================================
    # EVITAR OPERAR LA MISMA VELA
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

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # OBTENER VELA ACTUAL
    # ========================================================

    current_df = get_candles(
        pair
    )

    if current_df is None:
        return False

    current_candle = (
        current_df[
            current_df["from"]
            == execution_timestamp
        ]
    )

    if current_candle.empty:

        logger.warning(
            "%s | No se encontró vela de ejecución",
            pair
        )

        return False

    current_candle = (
        current_candle.iloc[-1]
    )

    # ========================================================
    # OBTENER VELAS ANTERIORES
    # ========================================================

    previous_df = (
        current_df[
            current_df["from"]
            < execution_timestamp
        ].copy()
    )

    previous_df = previous_df.tail(
        CANDLE_COUNT
    )

    # ========================================================
    # FILTRO MOVIMIENTO INICIAL
    # ========================================================

    signal = pending["signal"]

    too_strong = (
        opening_movement_too_strong(
            current_candle,
            previous_df,
            signal
        )
    )

    if too_strong:

        telegram_send(
            "⚠️ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            "La nueva vela comenzó con "
            "un movimiento demasiado fuerte.\n\n"
            "❌ No se ejecuta."
        )

        logger.info(
            "%s | Movimiento inicial demasiado fuerte",
            pair
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # PRECIO DE APERTURA
    # ========================================================

    execution_open = float(
        current_candle["open"]
    )

    # ========================================================
    # MENSAJE
    # ========================================================

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    telegram_send(
        "🚀 EJECUTANDO CONTINUIDAD\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n"
        f"Segundo: {current_second:02d}\n\n"
        "VELA DE CONFIRMACIÓN\n"
        f"Apertura: {pending['confirmation_open']}\n"
        f"Máximo: {pending['confirmation_high']}\n"
        f"Mínimo: {pending['confirmation_low']}\n"
        f"Cierre: {pending['confirmation_close']}\n\n"
        "VELA DE EJECUCIÓN\n"
        f"Apertura: {execution_open}\n\n"
        "⏱️ Expiración: 1 minuto\n"
        "💵 Importe: $100"
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

        if not status:

            telegram_send(
                "❌ OPERACIÓN RECHAZADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {signal.upper()}\n"
                "IQ Option rechazó la operación."
            )

            logger.error(
                "%s | Operación rechazada",
                pair
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
        # ELIMINAR SEÑAL PENDIENTE
        # ====================================================

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        # ====================================================
        # TELEGRAM
        # ====================================================

        telegram_send(
            "✅ OPERACIÓN ABIERTA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"Entrada: {execution_open}\n"
            "Importe: $100\n"
            "Expiración: 1 minuto\n"
            f"Segundo de entrada: {current_second:02d}\n"
            f"ID: {order_id}"
        )

        logger.info(
            "%s | %s | $%s | "
            "entrada=%s | segundo=%s | ID=%s",
            pair,
            signal.upper(),
            AMOUNT,
            execution_open,
            current_second,
            order_id
        )

        return True

    except Exception as e:

        logger.error(
            "Error ejecutando %s: %s",
            pair,
            e
        )

        telegram_send(
            "❌ ERROR AL OPERAR\n\n"
            f"Par: {pair}\n"
            f"Error: {str(e)}"
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(pair):

    # ========================================================
    # OBTENER VELAS
    # ========================================================

    df = get_candles(
        pair
    )

    if df is None:
        return

    # ========================================================
    # 1. DETECTAR NUEVA VELA CERRADA
    # ========================================================

    analyze_closed_candle(
        pair,
        df
    )

    # ========================================================
    # 2. COMPROBAR SEÑAL PENDIENTE
    # ========================================================

    execute_pending_signal(
        pair
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

            logger.error(
                "Error procesando %s: %s",
                pair,
                e
            )

        # ----------------------------------------------------
        # Pequeña pausa
        # ----------------------------------------------------

        time.sleep(0.15)


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
        "CONFIRMACIÓN: CIERRE DE VELA"
    )

    logger.info(
        "EJECUCIÓN: SEGUNDO 01–03"
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
        "Importe: $100\n"
        "Expiración: 1 minuto\n\n"
        "La continuidad se confirma "
        "al cierre de la vela.\n\n"
        "La entrada solo puede ocurrir "
        "en los segundos 01–03 "
        "de la siguiente vela.\n\n"
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
            # LIMPIAR SEÑALES VENCIDAS
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
            # PAUSA CORTA
            # ------------------------------------------------

            time.sleep(0.10)

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
