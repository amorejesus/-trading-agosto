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
# TRADING DIGITAL
# ============================================================

AMOUNT = 10

TIMEFRAME = 60

EXPIRATION = 1

CANDLE_COUNT = 60


# ============================================================
# 3 PARES OTC DIGITAL
# ============================================================

PAIRS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "EURJPY-OTC",
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
# EJECUCIÓN
#
# OBJETIVO:
#
# 00.xx de la NUEVA vela
#
# Ya no:
#
# 01–03
#
# ============================================================

EXECUTION_SECOND_START = 0

EXECUTION_SECOND_END = 1


# ============================================================
# FILTRO DE APERTURA
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

    if not TELEGRAM_TOKEN:
        return False

    if not TELEGRAM_CHAT_ID:
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
            timeout=5
        )

        return response.status_code == 200

    except Exception as e:

        logger.error(
            "Telegram: %s",
            e
        )

        return False


# ============================================================
# TELEGRAM COMMANDS
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
            timeout=3
        )

        data = response.json()

        if not data.get("ok"):
            return

        for update in data.get(
            "result",
            []
        ):

            LAST_UPDATE_ID = update[
                "update_id"
            ]

            message = update.get(
                "message",
                {}
            )

            text = str(
                message.get(
                    "text",
                    ""
                )
            ).strip().lower()

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

            if chat_id != str(
                TELEGRAM_CHAT_ID
            ):

                continue

            if text == "/start":

                BOT_RUNNING = True

                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "DIGITAL OTC\n"
                    "EURUSD-OTC\n"
                    "GBPUSD-OTC\n"
                    "EURJPY-OTC\n\n"
                    "⏱️ 1 minuto\n"
                    "💵 Importe: $10\n\n"
                    "La vela anterior se analiza "
                    "completa.\n\n"
                    "La siguiente vela define "
                    "la entrada.\n\n"
                    "🚀 Entrada objetivo: apertura "
                    "de la nueva vela."
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
                    f"{status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $10\n"
                    f"Pares: {len(PAIRS)}\n"
                    f"Pendientes: "
                    f"{len(PENDING_SIGNALS)}"
                )

    except Exception as e:

        logger.error(
            "Telegram commands: %s",
            e
        )


# ============================================================
# CONEXIÓN IQ OPTION
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
            "No se pudo conectar: "
            + str(reason)
        )

    logger.info(
        "IQ Option conectado"
    )

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "Mercado: DIGITAL OTC\n"
        "Temporalidad: 1 minuto"
    )

    return True


# ============================================================
# CONEXIÓN
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

            connected, reason = IQ.connect()

            if not connected:

                logger.error(
                    "Reconexión fallida: %s",
                    reason
                )

                return False

        return True

    except Exception as e:

        logger.error(
            "Conexión: %s",
            e
        )

        return False


# ============================================================
# HORA DEL SERVIDOR
# ============================================================

def get_server_timestamp():

    try:

        if IQ is not None:

            server_time = (
                IQ.get_server_timestamp()
            )

            if server_time:

                return float(
                    server_time
                )

    except Exception:

        pass

    return time.time()


# ============================================================
# TIMESTAMP VELA ACTUAL
# ============================================================

def get_current_candle_timestamp():

    now = get_server_timestamp()

    return int(
        now
        - (
            now % TIMEFRAME
        )
    )


# ============================================================
# SEGUNDO DE VELA
# ============================================================

def get_current_second():

    now = get_server_timestamp()

    return int(
        now % TIMEFRAME
    )


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

            return None

        df = pd.DataFrame(
            candles
        )

        if df.empty:
            return None

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
            "low",
            "from"
        ]

        for column in required:

            if column not in df.columns:

                logger.error(
                    "%s | falta %s",
                    pair,
                    column
                )

                return None

        for column in [
            "open",
            "close",
            "high",
            "low",
            "from"
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        df.dropna(
            subset=required,
            inplace=True
        )

        df["from"] = df[
            "from"
        ].astype(int)

        df.sort_values(
            "from",
            inplace=True
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True
        )

        df.reset_index(
            drop=True,
            inplace=True
        )

        return df

    except Exception as e:

        logger.error(
            "%s | Error velas: %s",
            pair,
            e
        )

        return None


# ============================================================
# VELAS CERRADAS
# ============================================================

def get_closed_candle_dataframe(df):

    if df is None or df.empty:
        return None

    current_timestamp = (
        get_current_candle_timestamp()
    )

    data = df[
        df["from"]
        < current_timestamp
    ].copy()

    if data.empty:
        return None

    data.sort_values(
        "from",
        inplace=True
    )

    data = data.tail(
        CANDLE_COUNT
    )

    data.reset_index(
        drop=True,
        inplace=True
    )

    return data


# ============================================================
# ÚLTIMA VELA CERRADA
# ============================================================

def get_last_closed_timestamp(df):

    if df is None or df.empty:
        return None

    try:

        return int(
            df.iloc[-1]["from"]
        )

    except Exception:

        return None


# ============================================================
# ATR
# ============================================================

def calculate_atr(df):

    if df is None:
        return None

    if len(df) < 14:
        return None

    previous_close = (
        df["close"].shift(1)
    )

    tr1 = (
        df["high"]
        - df["low"]
    )

    tr2 = (
        df["high"]
        - previous_close
    ).abs()

    tr3 = (
        df["low"]
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
# VERIFICAR DIGITAL ABIERTO
# ============================================================

def digital_is_open(pair):

    try:

        open_time = (
            IQ.get_all_open_time()
        )

        digital = open_time.get(
            "digital",
            {}
        )

        info = digital.get(
            pair,
            {}
        )

        return bool(
            info.get(
                "open",
                False
            )
        )

    except Exception as e:

        logger.warning(
            "%s | No se pudo verificar "
            "Digital: %s",
            pair,
            e
        )

        return False


# ============================================================
# COOLDOWN
# ============================================================

def cooldown_active(pair):

    last_time = LAST_TRADE_TIME.get(
        pair,
        0
    )

    return (
        time.time()
        - last_time
        < TRADE_COOLDOWN
    )


# ============================================================
# GUARDAR SEÑAL
# ============================================================

def save_pending_signal(
    pair,
    signal,
    confirmation_timestamp,
    confirmation_candle,
    score,
    reason
):

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

    direction = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    telegram_send(
        "📌 SEÑAL DIGITAL CONFIRMADA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA COMPLETA ANALIZADA\n"
        f"Open: {confirmation_candle['open']}\n"
        f"High: {confirmation_candle['high']}\n"
        f"Low: {confirmation_candle['low']}\n"
        f"Close: {confirmation_candle['close']}\n\n"
        f"Score: {score}/10\n\n"
        "✅ La señal pertenece a esta vela.\n"
        "➡️ La operación pertenece "
        "EXCLUSIVAMENTE a la siguiente vela.\n\n"
        "🚀 Entrada objetivo: APERTURA."
    )

    logger.info(
        "%s | Señal %s | "
        "confirmación=%s | "
        "ejecución=%s",
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

    closed_df = (
        get_closed_candle_dataframe(df)
    )

    if closed_df is None:
        return

    if len(closed_df) < 50:

        return

    closed_timestamp = (
        get_last_closed_timestamp(
            closed_df
        )
    )

    if closed_timestamp is None:
        return

    previous = (
        LAST_ANALYZED_CLOSED_CANDLE.get(
            pair
        )
    )

    if previous == closed_timestamp:
        return

    LAST_ANALYZED_CLOSED_CANDLE[pair] = (
        closed_timestamp
    )

    # ========================================================
    # MUY IMPORTANTE
    #
    # strategy.py SOLO RECIBE VELAS CERRADAS.
    #
    # La última vela ya terminó.
    # ========================================================

    result = analyze_market(
        closed_df
    )

    signal = result.get(
        "signal"
    )

    reason = result.get(
        "reason",
        ""
    )

    score = result.get(
        "score",
        0
    )

    direction = result.get(
        "direction",
        "range"
    )

    logger.info(
        "%s | VELA CERRADA | "
        "dirección=%s | señal=%s | "
        "score=%s | %s",
        pair,
        direction,
        signal,
        score,
        reason
    )

    if signal not in (
        "call",
        "put"
    ):

        return

    confirmation_candle = (
        closed_df.iloc[-1]
    )

    save_pending_signal(
        pair=pair,
        signal=signal,
        confirmation_timestamp=closed_timestamp,
        confirmation_candle=confirmation_candle,
        score=score,
        reason=reason
    )


# ============================================================
# FILTRO DE APERTURA
# ============================================================

def opening_movement_too_strong(
    current_candle,
    previous_df,
    signal
):

    if current_candle is None:
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

    if (
        candle_range
        > atr * MAX_OPENING_RANGE_ATR
    ):

        return True

    if (
        body
        > atr * MAX_OPENING_BODY_ATR
    ):

        return True

    # Movimiento adverso

    if signal == "call":

        adverse = (
            candle_open
            - candle_low
        )

        if adverse > atr * 0.40:

            return True

    elif signal == "put":

        adverse = (
            candle_high
            - candle_open
        )

        if adverse > atr * 0.40:

            return True

    return False


# ============================================================
# EJECUTAR DIGITAL
# ============================================================

def execute_digital_order(
    pair,
    signal
):

    try:

        logger.info(
            "%s | ENVIANDO ORDEN DIGITAL | %s",
            pair,
            signal.upper()
        )

        result = IQ.buy_digital_spot(
            pair,
            AMOUNT,
            signal,
            EXPIRATION
        )

        # ====================================================
        # FORMATO NORMAL:
        #
        # (True, order_id)
        # ====================================================

        if isinstance(
            result,
            tuple
        ):

            status = result[0]

            order_id = (
                result[1]
                if len(result) > 1
                else None
            )

        else:

            # Algunas versiones de la API
            # pueden devolver directamente el ID.

            if result in (
                None,
                False,
                "error",
                -1
            ):

                status = False

                order_id = result

            else:

                status = True

                order_id = result

        return bool(status), order_id

    except Exception as e:

        logger.error(
            "%s | Error Digital: %s",
            pair,
            e
        )

        return False, str(e)


# ============================================================
# EJECUTAR SEÑAL PENDIENTE
# ============================================================

def execute_pending_signal(pair):

    pending = PENDING_SIGNALS.get(
        pair
    )

    if pending is None:
        return False

    now = get_server_timestamp()

    current_timestamp = int(
        now
        - (
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
    # TODAVÍA NO LLEGÓ LA NUEVA VELA
    # ========================================================

    if current_timestamp < execution_timestamp:

        return False

    # ========================================================
    # YA PERDIMOS LA NUEVA VELA
    # ========================================================

    if current_timestamp > execution_timestamp:

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        logger.info(
            "%s | Señal vencida",
            pair
        )

        return False

    # ========================================================
    # SOLO APERTURA
    # ========================================================

    if current_second > EXECUTION_SECOND_END:

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        telegram_send(
            "⌛ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "No llegó a ejecutarse "
            "en la apertura de la nueva vela."
        )

        return False

    # ========================================================
    # COOLDOWN
    # ========================================================

    if cooldown_active(pair):

        return False

    # ========================================================
    # NO REPETIR VELA
    # ========================================================

    if (
        LAST_TRADE_CANDLE.get(pair)
        == execution_timestamp
    ):

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # DIGITAL ABIERTO
    # ========================================================

    if not digital_is_open(pair):

        logger.warning(
            "%s | Digital cerrado",
            pair
        )

        telegram_send(
            "⚠️ OPERACIÓN CANCELADA\n\n"
            f"Par: {pair}\n"
            "El mercado Digital no está abierto."
        )

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

    current = current_df[
        current_df["from"]
        == execution_timestamp
    ]

    if current.empty:

        logger.warning(
            "%s | No apareció la nueva vela",
            pair
        )

        return False

    current_candle = (
        current.iloc[-1]
    )

    # ========================================================
    # VELAS ANTERIORES
    # ========================================================

    previous_df = current_df[
        current_df["from"]
        < execution_timestamp
    ].copy()

    previous_df = previous_df.tail(
        CANDLE_COUNT
    )

    # ========================================================
    # FILTRO DE APERTURA
    #
    # No queremos entrar si desde el comienzo
    # la nueva vela ya se desplazó demasiado.
    # ========================================================

    signal = pending["signal"]

    if opening_movement_too_strong(
        current_candle,
        previous_df,
        signal
    ):

        telegram_send(
            "⚠️ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            "La nueva vela presentó "
            "movimiento inicial excesivo.\n\n"
            "❌ No se entra."
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # APERTURA
    # ========================================================

    execution_open = float(
        current_candle["open"]
    )

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else
        "PUT 🔴"
    )

    # ========================================================
    # TELEGRAM ANTES DE ORDEN
    # ========================================================

    telegram_send(
        "🚀 ENTRADA EN APERTURA\n\n"
        f"Par: {pair}\n"
        f"Mercado: DIGITAL OTC\n"
        f"Dirección: {direction_text}\n"
        f"Segundo servidor: {current_second:02d}\n\n"
        "VELA DE CONFIRMACIÓN\n"
        f"Open: {pending['confirmation_open']}\n"
        f"High: {pending['confirmation_high']}\n"
        f"Low: {pending['confirmation_low']}\n"
        f"Close: {pending['confirmation_close']}\n\n"
        "NUEVA VELA\n"
        f"Open: {execution_open}\n\n"
        "⏱️ Expiración: 1 minuto\n"
        f"💵 Importe: ${AMOUNT}"
    )

    # ========================================================
    # ORDEN DIGITAL
    # ========================================================

    status, order_id = (
        execute_digital_order(
            pair,
            signal
        )
    )

    # ========================================================
    # RECHAZADA
    # ========================================================

    if not status:

        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"Respuesta: {order_id}"
        )

        logger.error(
            "%s | DIGITAL RECHAZADA | %s",
            pair,
            order_id
        )

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        return False

    # ========================================================
    # GUARDAR OPERACIÓN
    # ========================================================

    LAST_TRADE_TIME[pair] = time.time()

    LAST_TRADE_CANDLE[pair] = (
        execution_timestamp
    )

    PENDING_SIGNALS.pop(
        pair,
        None
    )

    # ========================================================
    # CONFIRMACIÓN
    # ========================================================

    telegram_send(
        "✅ OPERACIÓN DIGITAL ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"Entrada: {execution_open}\n"
        f"Segundo: {current_second:02d}\n"
        f"Importe: ${AMOUNT}\n"
        "Expiración: 1 minuto\n"
        f"ID: {order_id}"
    )

    logger.info(
        "%s | DIGITAL %s | "
        "entrada=%s | segundo=%s | ID=%s",
        pair,
        signal.upper(),
        execution_open,
        current_second,
        order_id
    )

    return True


# ============================================================
# LIMPIAR SEÑALES
# ============================================================

def clean_expired_signals():

    if not PENDING_SIGNALS:
        return

    now = get_server_timestamp()

    expired = []

    for pair, pending in (
        PENDING_SIGNALS.items()
    ):

        execution_timestamp = (
            pending["execution_timestamp"]
        )

        if now >= (
            execution_timestamp
            + TIMEFRAME
        ):

            expired.append(pair)

    for pair in expired:

        PENDING_SIGNALS.pop(
            pair,
            None
        )

        telegram_send(
            "⌛ SEÑAL EXPIRADA\n\n"
            f"Par: {pair}\n"
            "No se ejecutó en la apertura "
            "de la siguiente vela."
        )


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(pair):

    df = get_candles(
        pair
    )

    if df is None:
        return

    # ========================================================
    # PRIMERO:
    # Detectar que terminó una vela.
    #
    # ========================================================

    analyze_closed_candle(
        pair,
        df
    )

    # ========================================================
    # SEGUNDO:
    # Si existe señal anterior,
    # intentar entrar en la NUEVA vela.
    # ========================================================

    execute_pending_signal(
        pair
    )


# ============================================================
# TODOS LOS PARES
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
                "%s | Error procesando",
                pair
            )

        time.sleep(0.05)


# ============================================================
# MAIN
# ============================================================

def main():

    global BOT_RUNNING

    logger.info(
        "========================================"
    )

    logger.info(
        "BOT DIGITAL OTC INICIANDO"
    )

    logger.info(
        "EURUSD-OTC"
    )

    logger.info(
        "GBPUSD-OTC"
    )

    logger.info(
        "EURJPY-OTC"
    )

    logger.info(
        "TEMPORALIDAD: 1 MINUTO"
    )

    logger.info(
        "EXPIRACIÓN: 1 MINUTO"
    )

    logger.info(
        "ENTRADA: APERTURA DE NUEVA VELA"
    )

    logger.info(
        "========================================"
    )

    if not IQ_EMAIL:

        logger.error(
            "Falta IQ_EMAIL"
        )

        telegram_send(
            "❌ Falta IQ_EMAIL."
        )

        return

    if not IQ_PASSWORD:

        logger.error(
            "Falta IQ_PASSWORD"
        )

        telegram_send(
            "❌ Falta IQ_PASSWORD."
        )

        return

    if not TELEGRAM_TOKEN:

        logger.error(
            "Falta TELEGRAM_TOKEN"
        )

        return

    if not TELEGRAM_CHAT_ID:

        logger.error(
            "Falta TELEGRAM_CHAT_ID"
        )

        return

    # ========================================================
    # CONECTAR
    # ========================================================

    try:

        connect_iq()

    except Exception as e:

        logger.error(
            "Conexión fallida: %s",
            e
        )

        telegram_send(
            "❌ ERROR DE CONEXIÓN\n\n"
            + str(e)
        )

        return

    # ========================================================
    # LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT DIGITAL OTC LISTO\n\n"
        "Pares:\n"
        "• EURUSD-OTC\n"
        "• GBPUSD-OTC\n"
        "• EURJPY-OTC\n\n"
        "⏱️ Velas: 1 minuto\n"
        "⏱️ Expiración: 1 minuto\n"
        f"💵 Importe: ${AMOUNT}\n\n"
        "La vela de confirmación se "
        "analiza completa.\n\n"
        "La siguiente vela es la vela "
        "de operación.\n\n"
        "🚀 Entrada objetivo: APERTURA.\n\n"
        "Escribe /start."
    )

    # ========================================================
    # LOOP
    # ========================================================

    while True:

        try:

            check_commands()

            clean_expired_signals()

            if not BOT_RUNNING:

                time.sleep(0.5)

                continue

            if not ensure_connection():

                time.sleep(2)

                continue

            process_all_pairs()

            # Muy corto para detectar
            # el cambio de vela rápidamente.

            time.sleep(0.03)

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
            )

            break

        except Exception as e:

            logger.exception(
                "Error principal"
            )

            telegram_send(
                "⚠️ ERROR DEL BOT\n\n"
                + str(e)
            )

            time.sleep(2)


# ============================================================
# ARRANQUE
# ============================================================

if __name__ == "__main__":

    main()
