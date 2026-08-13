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
# EJECUCIÓN
# ============================================================

# SOLO se permite ejecutar entre segundo 01 y 03
EXECUTION_SECOND_MIN = 1
EXECUTION_SECOND_MAX = 3

# Después del segundo 03 la señal se cancela
SIGNAL_MAX_AGE = 3


# ============================================================
# CONTROL
# ============================================================

TRADE_COOLDOWN = 60

BOT_RUNNING = False

LAST_UPDATE_ID = None

LAST_TRADE_TIME = {}

LAST_TRADE_CANDLE = {}

# ------------------------------------------------------------
# SEÑALES PENDIENTES
#
# {
#   "EURUSD-OTC": {
#       "signal": "call",
#       "confirmation_timestamp": 123456,
#       "execution_timestamp": 123516,
#       "score": 10,
#       "reason": "...",
#       "confirmation_open": 1.234,
#       "confirmation_high": 1.235,
#       "confirmation_low": 1.233,
#       "confirmation_close": 1.2345
#   }
# }
# ------------------------------------------------------------

PENDING_SIGNALS = {}


# ============================================================
# CONTROL DE VELAS YA ANALIZADAS
# ============================================================

LAST_ANALYZED_CONFIRMATION = {}


# ============================================================
# IQ OPTION
# ============================================================

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
                    "Flujo:\n"
                    "1️⃣ Analiza vela cerrada\n"
                    "2️⃣ Guarda continuidad\n"
                    "3️⃣ Espera nueva vela\n"
                    "4️⃣ Ejecuta segundo 01–03\n\n"
                    "❌ No ejecuta la vela de confirmación."
                )

                logger.info(
                    "BOT ACTIVADO desde Telegram"
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
                    "BOT DETENIDO desde Telegram"
                )

            # =================================================
            # STATUS
            # =================================================

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
                    f"Señales pendientes: {pending}\n"
                    "Ventana: segundo 01–03"
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
# ASEGURAR CONEXIÓN
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
                    "%s falta en velas de %s",
                    column,
                    pair
                )

                return None

        # ----------------------------------------------------
        # NÚMEROS
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
        # ORDEN
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
# TIMESTAMP
# ============================================================

def get_timestamp(row):

    try:

        return int(
            row["from"]
        )

    except Exception:

        return None


# ============================================================
# SEGUNDO ACTUAL DE LA VELA
# ============================================================

def get_candle_second(
    candle_timestamp
):

    if candle_timestamp is None:
        return None

    try:

        elapsed = (
            time.time()
            - candle_timestamp
        )

        return int(
            elapsed
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

    return (
        elapsed < TRADE_COOLDOWN
    )


# ============================================================
# OBTENER DATOS DE VELA
# ============================================================

def candle_values(row):

    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"])
    }


# ============================================================
# GUARDAR SEÑAL
# ============================================================

def save_pending_signal(
    pair,
    signal,
    confirmation_row,
    confirmation_timestamp,
    result
):

    execution_timestamp = (
        confirmation_timestamp
        + TIMEFRAME
    )

    values = candle_values(
        confirmation_row
    )

    PENDING_SIGNALS[pair] = {

        "signal": signal,

        "confirmation_timestamp":
            confirmation_timestamp,

        "execution_timestamp":
            execution_timestamp,

        "score":
            result.get(
                "score",
                0
            ),

        "structure_score":
            result.get(
                "structure_score",
                0
            ),

        "confirmation_score":
            result.get(
                "confirmation_score",
                0
            ),

        "reason":
            result.get(
                "reason",
                ""
            ),

        "confirmation_open":
            values["open"],

        "confirmation_high":
            values["high"],

        "confirmation_low":
            values["low"],

        "confirmation_close":
            values["close"]
    }

    direction_text = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    logger.info(
        "%s | SEÑAL GUARDADA | %s | "
        "confirmación=%s | ejecución=%s | "
        "score=%s",
        pair,
        signal.upper(),
        confirmation_timestamp,
        execution_timestamp,
        result.get("score", 0)
    )

    telegram_send(
        "📊 SEÑAL DE CONTINUIDAD\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"

        "🕯 VELA DE CONFIRMACIÓN\n"
        f"Apertura: {values['open']}\n"
        f"Máximo: {values['high']}\n"
        f"Mínimo: {values['low']}\n"
        f"Cierre: {values['close']}\n\n"

        f"Score: {result.get('score', 0)}"
        f"/10\n\n"

        "✅ Señal guardada\n"
        "⏳ NO se ejecuta en esta vela\n\n"

        "PRÓXIMA VELA\n"
        "⏱ Ejecución permitida: segundo 01–03"
    )


# ============================================================
# ANALIZAR VELA CERRADA
# ============================================================

def analyze_closed_candle(
    pair,
    df
):

    # --------------------------------------------------------
    # NECESITAMOS UNA VELA ACTUAL Y UNA CERRADA
    # --------------------------------------------------------

    if len(df) < 3:

        logger.info(
            "%s | Esperando suficientes velas",
            pair
        )

        return

    # --------------------------------------------------------
    # LA ÚLTIMA VELA PUEDE ESTAR ABIERTA
    #
    # Por eso:
    #
    # -1 = vela actual
    # -2 = última vela cerrada
    #
    # La estrategia SOLO analiza -2.
    # --------------------------------------------------------

    confirmation_row = df.iloc[-2]

    confirmation_timestamp = (
        get_timestamp(
            confirmation_row
        )
    )

    if confirmation_timestamp is None:

        logger.warning(
            "%s | Timestamp inválido",
            pair
        )

        return

    # --------------------------------------------------------
    # NO ANALIZAR LA MISMA VELA DOS VECES
    # --------------------------------------------------------

    previous = (
        LAST_ANALYZED_CONFIRMATION.get(
            pair
        )
    )

    if previous == confirmation_timestamp:

        return

    # --------------------------------------------------------
    # MARCAR COMO ANALIZADA
    # --------------------------------------------------------

    LAST_ANALYZED_CONFIRMATION[pair] = (
        confirmation_timestamp
    )

    # --------------------------------------------------------
    # ANALIZAR SOLO HASTA LA VELA CERRADA
    #
    # MUY IMPORTANTE:
    #
    # NO incluimos la vela actual.
    # --------------------------------------------------------

    analysis_df = df.iloc[
        :-1
    ].copy()

    if len(analysis_df) < 20:

        logger.info(
            "%s | Datos insuficientes para estrategia",
            pair
        )

        return

    # --------------------------------------------------------
    # ANALIZAR ESTRATEGIA
    # --------------------------------------------------------

    try:

        result = analyze_market(
            analysis_df
        )

    except Exception as e:

        logger.exception(
            "%s | Error en strategy.py",
            pair
        )

        return

    if not isinstance(
        result,
        dict
    ):

        logger.error(
            "%s | strategy.py no devolvió dict",
            pair
        )

        return

    signal = result.get(
        "signal"
    )

    direction = result.get(
        "direction"
    )

    score = result.get(
        "score",
        0
    )

    reason = result.get(
        "reason",
        ""
    )

    logger.info(
        "%s | vela_cerrada=%s | "
        "tendencia=%s | señal=%s | "
        "score=%s | %s",
        pair,
        confirmation_timestamp,
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
    # SI YA EXISTE UNA SEÑAL PENDIENTE
    # --------------------------------------------------------

    if pair in PENDING_SIGNALS:

        logger.info(
            "%s | Ya existe una señal pendiente",
            pair
        )

        return

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    save_pending_signal(
        pair,
        signal,
        confirmation_row,
        confirmation_timestamp,
        result
    )


# ============================================================
# VALIDAR ACTIVO ANTES DE COMPRAR
# ============================================================

def check_asset_before_buy(
    pair
):

    diagnostics = {
        "connected": False,
        "asset_found": False,
        "binary_open": None,
        "error": None
    }

    try:

        diagnostics["connected"] = (
            IQ is not None
            and IQ.check_connect()
        )

        if not diagnostics["connected"]:

            diagnostics["error"] = (
                "IQ Option no está conectado"
            )

            return diagnostics

        # ----------------------------------------------------
        # CONSULTAR ESTADO DE ACTIVOS
        # ----------------------------------------------------

        try:

            all_open = (
                IQ.get_all_open_time()
            )

            if isinstance(
                all_open,
                dict
            ):

                binary_data = (
                    all_open.get(
                        "binary",
                        {}
                    )
                )

                if pair in binary_data:

                    diagnostics[
                        "asset_found"
                    ] = True

                    asset_info = (
                        binary_data[pair]
                    )

                    if isinstance(
                        asset_info,
                        dict
                    ):

                        diagnostics[
                            "binary_open"
                        ] = asset_info.get(
                            "open"
                        )

                else:

                    diagnostics[
                        "error"
                    ] = (
                        "Activo no encontrado "
                        "en get_all_open_time()"
                    )

        except Exception as e:

            diagnostics[
                "error"
            ] = (
                "No se pudo consultar "
                f"estado del activo: {e}"
            )

        return diagnostics

    except Exception as e:

        diagnostics[
            "error"
        ] = str(e)

        return diagnostics


# ============================================================
# DIAGNÓSTICO DE RECHAZO
# ============================================================

def diagnose_rejection(
    pair,
    signal,
    execution_timestamp,
    current_second
):

    diagnostics = check_asset_before_buy(
        pair
    )

    connected = diagnostics.get(
        "connected"
    )

    asset_found = diagnostics.get(
        "asset_found"
    )

    binary_open = diagnostics.get(
        "binary_open"
    )

    error = diagnostics.get(
        "error"
    )

    logger.error(
        "================================================"
    )

    logger.error(
        "DIAGNÓSTICO DE OPERACIÓN RECHAZADA"
    )

    logger.error(
        "Par: %s",
        pair
    )

    logger.error(
        "Dirección: %s",
        signal.upper()
    )

    logger.error(
        "Timestamp ejecución: %s",
        execution_timestamp
    )

    logger.error(
        "Segundo detectado: %s",
        current_second
    )

    logger.error(
        "Conexión: %s",
        connected
    )

    logger.error(
        "Activo encontrado: %s",
        asset_found
    )

    logger.error(
        "Binary abierto: %s",
        binary_open
    )

    if error:

        logger.error(
            "Diagnóstico adicional: %s",
            error
        )

    logger.error(
        "Importe: $%s",
        AMOUNT
    )

    logger.error(
        "Expiración: %s minuto",
        EXPIRATION
    )

    logger.error(
        "================================================"
    )

    telegram_send(
        "🔎 DIAGNÓSTICO DEL RECHAZO\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"Segundo: {current_second}\n"
        f"Conexión: {connected}\n"
        f"Activo encontrado: {asset_found}\n"
        f"Binary abierto: {binary_open}\n"
        f"Importe: ${AMOUNT}\n"
        f"Expiración: {EXPIRATION} minuto\n\n"
        f"Información adicional: "
        f"{error if error else 'IQ Option no entregó una causa textual.'}"
    )


# ============================================================
# EJECUTAR SEÑAL PENDIENTE
# ============================================================

def execute_pending_signal(
    pair,
    df
):

    pending = (
        PENDING_SIGNALS.get(
            pair
        )
    )

    if pending is None:
        return

    # --------------------------------------------------------
    # DATOS
    # --------------------------------------------------------

    execution_timestamp = (
        pending[
            "execution_timestamp"
        ]
    )

    signal = pending[
        "signal"
    ]

    # --------------------------------------------------------
    # TIMESTAMP DE LA VELA ACTUAL
    # --------------------------------------------------------

    current_row = df.iloc[-1]

    current_timestamp = (
        get_timestamp(
            current_row
        )
    )

    if current_timestamp is None:

        return

    # --------------------------------------------------------
    # TODAVÍA NO LLEGAMOS A LA VELA
    # --------------------------------------------------------

    if current_timestamp < execution_timestamp:

        return

    # --------------------------------------------------------
    # SI POR ALGÚN MOTIVO LA API SALTÓ UNA VELA
    # --------------------------------------------------------

    if current_timestamp > execution_timestamp:

        logger.warning(
            "%s | Se perdió la vela de ejecución. "
            "Esperada=%s | Actual=%s",
            pair,
            execution_timestamp,
            current_timestamp
        )

        telegram_send(
            "⏳ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "Se perdió la vela de ejecución."
        )

        del PENDING_SIGNALS[pair]

        return

    # --------------------------------------------------------
    # SEGUNDO ACTUAL
    # --------------------------------------------------------

    current_second = (
        get_candle_second(
            current_timestamp
        )
    )

    if current_second is None:

        return

    # --------------------------------------------------------
    # ANTES DE 01
    # --------------------------------------------------------

    if current_second < EXECUTION_SECOND_MIN:

        return

    # --------------------------------------------------------
    # DESPUÉS DE 03
    # --------------------------------------------------------

    if current_second > EXECUTION_SECOND_MAX:

        logger.warning(
            "%s | Ventana perdida | segundo=%s",
            pair,
            current_second
        )

        telegram_send(
            "⏳ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "Se perdió la ventana de ejecución 01–03."
        )

        del PENDING_SIGNALS[pair]

        return

    # ========================================================
    # ESTAMOS ENTRE 01 Y 03
    # ========================================================

    logger.info(
        "%s | VENTANA DE EJECUCIÓN | "
        "segundo=%s | señal=%s",
        pair,
        current_second,
        signal.upper()
    )

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    if cooldown_active(pair):

        logger.info(
            "%s | Cooldown activo | señal cancelada",
            pair
        )

        telegram_send(
            "⏳ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "Cooldown activo."
        )

        del PENDING_SIGNALS[pair]

        return

    # --------------------------------------------------------
    # EVITAR DOBLE OPERACIÓN
    # --------------------------------------------------------

    if (
        LAST_TRADE_CANDLE.get(pair)
        == current_timestamp
    ):

        logger.warning(
            "%s | Ya existe operación "
            "en esta vela",
            pair
        )

        del PENDING_SIGNALS[pair]

        return

    # --------------------------------------------------------
    # DATOS DE VELA DE EJECUCIÓN
    # --------------------------------------------------------

    execution_values = candle_values(
        current_row
    )

    confirmation_open = pending[
        "confirmation_open"
    ]

    confirmation_high = pending[
        "confirmation_high"
    ]

    confirmation_low = pending[
        "confirmation_low"
    ]

    confirmation_close = pending[
        "confirmation_close"
    ]

    score = pending[
        "score"
    ]

    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    telegram_send(
        "🚀 EJECUTANDO CONTINUIDAD\n\n"

        f"Par: {pair}\n"
        f"Dirección: {signal.upper()} 🔴"
        if signal == "put"
        else
        "🚀 EJECUTANDO CONTINUIDAD\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()} 🟢"
    )

    telegram_send(
        f"Segundo: {current_second:02d}\n\n"

        "🕯 VELA DE CONFIRMACIÓN\n"
        f"Apertura: {confirmation_open}\n"
        f"Máximo: {confirmation_high}\n"
        f"Mínimo: {confirmation_low}\n"
        f"Cierre: {confirmation_close}\n\n"

        f"Score: {score}/10\n\n"

        "🕯 VELA DE EJECUCIÓN\n"
        f"Apertura: {execution_values['open']}\n\n"

        "⏱ Expiración: 1 minuto\n"
        f"💰 Importe: ${AMOUNT}"
    )

    # ========================================================
    # PRE-CHECK
    # ========================================================

    precheck = check_asset_before_buy(
        pair
    )

    if not precheck.get(
        "connected",
        False
    ):

        logger.error(
            "%s | No se ejecuta: "
            "IQ Option desconectado",
            pair
        )

        telegram_send(
            "❌ OPERACIÓN NO EJECUTADA\n\n"
            f"Par: {pair}\n"
            "IQ Option no está conectado."
        )

        del PENDING_SIGNALS[pair]

        return

    # ========================================================
    # EJECUTAR
    # ========================================================

    try:

        logger.info(
            "%s | ENVIANDO ORDEN | "
            "%s | segundo=%s | amount=%s",
            pair,
            signal.upper(),
            current_second,
            AMOUNT
        )

        status, order_id = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION
        )

        # ====================================================
        # RECHAZADA
        # ====================================================

        if not status:

            logger.error(
                "%s | IQ OPTION RECHAZÓ "
                "LA OPERACIÓN | order_id=%s",
                pair,
                order_id
            )

            telegram_send(
                "❌ OPERACIÓN RECHAZADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {signal.upper()}\n"
                f"Segundo: {current_second:02d}\n"
                "IQ Option rechazó la operación."
            )

            diagnose_rejection(
                pair,
                signal,
                execution_timestamp,
                current_second
            )

            del PENDING_SIGNALS[pair]

            return

        # ====================================================
        # OPERACIÓN ACEPTADA
        # ====================================================

        LAST_TRADE_TIME[pair] = (
            time.time()
        )

        LAST_TRADE_CANDLE[pair] = (
            current_timestamp
        )

        telegram_send(
            "✅ OPERACIÓN ABIERTA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"Segundo: {current_second:02d}\n"
            f"Importe: ${AMOUNT}\n"
            "Expiración: 1 minuto\n"
            f"ID: {order_id}"
        )

        logger.info(
            "%s | OPERACIÓN ABIERTA | "
            "%s | segundo=%s | "
            "$%s | ID=%s",
            pair,
            signal.upper(),
            current_second,
            AMOUNT,
            order_id
        )

        # ----------------------------------------------------
        # BORRAR SEÑAL
        # ----------------------------------------------------

        del PENDING_SIGNALS[pair]

    except Exception as e:

        logger.exception(
            "%s | EXCEPCIÓN EJECUTANDO ORDEN",
            pair
        )

        telegram_send(
            "❌ ERROR AL OPERAR\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"Segundo: {current_second:02d}\n\n"
            f"Error: {str(e)}"
        )

        diagnose_rejection(
            pair,
            signal,
            execution_timestamp,
            current_second
        )

        del PENDING_SIGNALS[pair]


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(pair):

    df = get_candles(
        pair
    )

    if df is None:
        return

    if len(df) < 20:

        logger.info(
            "%s | Esperando datos: %s",
            pair,
            len(df)
        )

        return

    # ========================================================
    # 1. PRIMERO EJECUTAR SEÑAL PENDIENTE
    # ========================================================

    if pair in PENDING_SIGNALS:

        execute_pending_signal(
            pair,
            df
        )

    # ========================================================
    # 2. DESPUÉS ANALIZAR NUEVA VELA CERRADA
    #
    # Esto permite que la nueva vela se convierta en la
    # siguiente confirmación mientras la anterior ya terminó.
    # ========================================================

    if pair not in PENDING_SIGNALS:

        analyze_closed_candle(
            pair,
            df
        )


# ============================================================
# ANALIZAR TODOS LOS PARES
# ============================================================

def analyze_all_pairs():

    for pair in PAIRS:

        if not BOT_RUNNING:
            return

        try:

            process_pair(
                pair
            )

        except Exception as e:

            logger.exception(
                "Error analizando %s",
                pair
            )

        # ----------------------------------------------------
        # No hacer una pausa grande.
        #
        # La ventana es solamente 3 segundos.
        # ----------------------------------------------------

        time.sleep(0.10)


# ============================================================
# LIMPIAR SEÑALES VENCIDAS
# ============================================================

def cleanup_pending_signals():

    now = time.time()

    expired = []

    for pair, signal_data in (
        PENDING_SIGNALS.items()
    ):

        execution_timestamp = (
            signal_data[
                "execution_timestamp"
            ]
        )

        if now > (
            execution_timestamp
            + SIGNAL_MAX_AGE
        ):

            expired.append(
                pair
            )

    for pair in expired:

        logger.warning(
            "%s | Señal pendiente expirada",
            pair
        )

        telegram_send(
            "⏳ SEÑAL CANCELADA\n\n"
            f"Par: {pair}\n"
            "La ventana 01–03 terminó."
        )

        del PENDING_SIGNALS[pair]


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
        "Expiración: 1 MINUTO"
    )

    logger.info(
        "Importe: $%s",
        AMOUNT
    )

    logger.info(
        "Ventana ejecución: 01–03"
    )

    logger.info(
        "========================================"
    )

    # ========================================================
    # VALIDACIONES
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

        logger.exception(
            "No se pudo iniciar IQ Option"
        )

        telegram_send(
            "❌ No se pudo conectar a IQ Option.\n\n"
            + str(e)
        )

        return

    # ========================================================
    # LISTO
    # ========================================================

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "Conectado a IQ Option.\n"
        "Escribe /start para comenzar.\n"
        "Escribe /status para consultar estado.\n\n"
        "⏱ Ventana de ejecución: "
        "segundo 01–03"
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
            # DETENIDO
            # ------------------------------------------------

            if not BOT_RUNNING:

                time.sleep(1)

                continue

            # ------------------------------------------------
            # CONEXIÓN
            # ------------------------------------------------

            if not ensure_connection():

                time.sleep(3)

                continue

            # ------------------------------------------------
            # LIMPIAR
            # ------------------------------------------------

            cleanup_pending_signals()

            # ------------------------------------------------
            # ANALIZAR
            # ------------------------------------------------

            analyze_all_pairs()

            # ------------------------------------------------
            # PAUSA MUY CORTA
            # ------------------------------------------------

            time.sleep(0.20)

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
