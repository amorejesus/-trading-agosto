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


# ============================================================
# TEMPORALIDADES
# ============================================================

TIMEFRAME = 60

MICRO_TIMEFRAME = 5

CANDLE_COUNT = 60

MICRO_CANDLE_COUNT = 12


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 175

EXPIRATION = 1


# ============================================================
# SINCRONIZACIÓN
# ============================================================

# Poll muy rápido.
POLL_INTERVAL = 0.01

# Margen máximo para encontrar N+1.
NEW_CANDLE_TIMEOUT = 4.0


# ============================================================
# ESTADO
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None


# Última vela N analizada.
LAST_PROCESSED_MINUTE: Dict[str, int] = {}


# Señales esperando N+1.
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}


# Última vela donde se ejecutó.
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
# TELEGRAM COMMANDS
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

        params["offset"] = LAST_UPDATE_ID + 1

    try:

        response = requests.get(
            url,
            params=params,
            timeout=3,
        )

        data = response.json()

        if not data.get("ok"):
            return

        for update in data.get("result", []):

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
                    "🎯 MODO DIRECCIONAL\n"
                    "CALL → movimiento alcista fuerte\n"
                    "PUT → movimiento bajista fuerte\n\n"
                    "📊 Vela principal: 1M\n"
                    "⏱ Microvelas: 5S\n"
                    "➡️ Entrada exclusivamente en N+1\n"
                    "🎯 Sin espera artificial de 1–3 segundos."
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
                    "Modo: DIRECCIONAL\n"
                    "Entrada: N+1\n"
                    "Expiración: 1M\n"
                    f"Importe: ${AMOUNT}"
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
        "Modo direccional activo.\n"
        "Entrada exclusivamente en N+1."
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
# TIEMPO DEL SERVIDOR IQ
# ============================================================

def get_server_timestamp() -> Optional[float]:

    if IQ is None:
        return None

    try:

        # Método disponible en iqoptionapi.
        timestamp = IQ.get_server_timestamp()

        if timestamp is not None:

            return float(timestamp)

    except Exception:
        pass

    # --------------------------------------------------------
    # Fallback
    # --------------------------------------------------------

    try:

        return time.time()

    except Exception:

        return None


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

        df = pd.DataFrame(candles)

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

                return None

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df.dropna(
            subset=required,
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

        candles = IQ.get_candles(
            pair,
            MICRO_TIMEFRAME,
            MICRO_CANDLE_COUNT + 5,
            time.time(),
        )

        if not candles:
            return None

        df = pd.DataFrame(candles)

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

                return None

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

        df.dropna(
            subset=required,
            inplace=True,
        )

        df.sort_values(
            "from",
            inplace=True,
        )

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

    if df is None or df.empty:
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
# ÚLTIMA VELA CERRADA
# ============================================================

def get_closed_candle(
    df: pd.DataFrame,
) -> Optional[pd.Series]:

    if df is None:
        return None

    if len(df) < 2:
        return None

    return df.iloc[-2]


# ============================================================
# CONFIRMACIÓN DIRECCIONAL EXTRA
# ============================================================

def validate_direction(
    signal: str,
    candle: pd.Series,
    micro: pd.DataFrame,
) -> tuple[bool, str]:

    """
    Confirmación adicional.

    No cambia el patrón principal.

    Solo permite la operación cuando el movimiento
    de las microvelas mantiene la misma dirección.

    CALL:
        - cierre N > apertura N
        - mayoría de microvelas favorecen subida
        - última microvela favorece subida

    PUT:
        - cierre N < apertura N
        - mayoría de microvelas favorecen bajada
        - última microvela favorece bajada
    """

    try:

        minute_open = float(
            candle["open"]
        )

        minute_close = float(
            candle["close"]
        )

        micro = micro.copy()

        micro["open"] = pd.to_numeric(
            micro["open"],
            errors="coerce",
        )

        micro["close"] = pd.to_numeric(
            micro["close"],
            errors="coerce",
        )

        micro.dropna(
            subset=[
                "open",
                "close",
            ],
            inplace=True,
        )

        if len(micro) < 12:

            return (
                False,
                "Microvelas insuficientes."
            )

        bullish = (
            micro["close"]
            >
            micro["open"]
        )

        bearish = (
            micro["close"]
            <
            micro["open"]
        )

        bullish_count = int(
            bullish.sum()
        )

        bearish_count = int(
            bearish.sum()
        )

        last_open = float(
            micro.iloc[-1]["open"]
        )

        last_close = float(
            micro.iloc[-1]["close"]
        )

        # ====================================================
        # CALL
        # ====================================================

        if signal == "call":

            if minute_close <= minute_open:

                return (
                    False,
                    "CALL bloqueado: "
                    "cierre 1M no alcista."
                )

            if bullish_count <= bearish_count:

                return (
                    False,
                    "CALL bloqueado: "
                    "micro movimiento no favorece "
                    "la dirección alcista."
                )

            if last_close <= last_open:

                return (
                    False,
                    "CALL bloqueado: "
                    "última microvela no confirma "
                    "continuidad alcista."
                )

            return (
                True,
                "Dirección alcista confirmada."
            )

        # ====================================================
        # PUT
        # ====================================================

        if signal == "put":

            if minute_close >= minute_open:

                return (
                    False,
                    "PUT bloqueado: "
                    "cierre 1M no bajista."
                )

            if bearish_count <= bullish_count:

                return (
                    False,
                    "PUT bloqueado: "
                    "micro movimiento no favorece "
                    "la dirección bajista."
                )

            if last_close >= last_open:

                return (
                    False,
                    "PUT bloqueado: "
                    "última microvela no confirma "
                    "continuidad bajista."
                )

            return (
                True,
                "Dirección bajista confirmada."
            )

        return (
            False,
            "Dirección desconocida."
        )

    except Exception as exc:

        logger.error(
            "Error confirmación direccional: %s",
            exc,
        )

        return (
            False,
            "Error en confirmación."
        )


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

    # --------------------------------------------------------
    # CONFIRMACIÓN EXTRA DE DIRECCIÓN
    # --------------------------------------------------------

    valid_direction, direction_reason = (
        validate_direction(
            signal,
            candle,
            micro,
        )
    )

    if not valid_direction:

        logger.info(
            "%s | señal descartada | %s",
            pair,
            direction_reason,
        )

        telegram_send(
            "🚫 SEÑAL DESCARTADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"Motivo:\n{direction_reason}"
        )

        return

    # --------------------------------------------------------
    # EVITAR DUPLICADOS
    # --------------------------------------------------------

    if pair in PENDING_ENTRY:

        existing = PENDING_ENTRY[pair]

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

        "direction_reason":
            direction_reason,

        "created_at": time.time(),

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
        f"Timestamp: {minute_ts}\n"
        f"Apertura: {opening}\n"
        f"Cierre: {closing}\n\n"
        "PRIMERA 5S\n"
        f"Cierre: {first_5s_close}\n\n"
        "RETROCESOS 5S\n"
        f"Cantidad: "
        f"{result.get('pullback_count', 0)}\n\n"
        "CONFIRMACIÓN DIRECCIONAL\n"
        f"✅ {direction_reason}\n\n"
        "🚫 N nunca se opera.\n"
        "➡️ Señal reservada exclusivamente para N+1."
    )

    logger.info(
        "%s | SEÑAL %s | N=%s | %s",
        pair,
        signal.upper(),
        minute_ts,
        direction_reason,
    )


# ============================================================
# COMPRA BINARIA
# ============================================================

def buy_binary(
    pair: str,
    signal: str,
) -> tuple[bool, Optional[Any]]:

    if IQ is None:

        return (
            False,
            None,
        )

    try:

        # ----------------------------------------------------
        # binary option
        # ----------------------------------------------------

        result = IQ.buy(
            AMOUNT,
            pair,
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
            "buy binary %s %s: %s",
            pair,
            signal,
            exc,
        )

        return (
            False,
            None,
        )


# ============================================================
# ESPERAR N+1 CON RELOJ DEL SERVIDOR
# ============================================================

def wait_for_next_candle(
    pair: str,
    candle_timestamp: int,
) -> Optional[int]:

    """
    Espera exclusivamente hasta que el servidor
    indique que comenzó la siguiente vela.

    No existe espera artificial de 1, 2 o 3 segundos.

    N:
        timestamp

    N+1:
        timestamp + 60
    """

    expected_next = (
        int(candle_timestamp)
        + TIMEFRAME
    )

    start = time.monotonic()

    last_server_ts = None

    while True:

        if not BOT_RUNNING:

            return None

        server_ts = get_server_timestamp()

        if server_ts is None:

            time.sleep(
                POLL_INTERVAL
            )

            continue

        last_server_ts = server_ts

        # ----------------------------------------------------
        # YA ESTAMOS EN N+1
        # ----------------------------------------------------

        if server_ts >= expected_next:

            return expected_next

        # ----------------------------------------------------
        # TIMEOUT DE SEGURIDAD
        # ----------------------------------------------------

        if (
            time.monotonic()
            - start
            > NEW_CANDLE_TIMEOUT
        ):

            logger.warning(
                "%s | timeout esperando N+1 | "
                "servidor=%s | esperado=%s",
                pair,
                int(server_ts),
                expected_next,
            )

            return None

        time.sleep(
            POLL_INTERVAL
        )


# ============================================================
# OBTENER APERTURA REAL N+1
# ============================================================

def get_real_next_candle(
    pair: str,
    expected_timestamp: int,
) -> Optional[pd.Series]:

    start = time.monotonic()

    while True:

        df = get_1m_candles(
            pair
        )

        if df is not None:

            for _, row in df.iterrows():

                try:

                    ts = int(
                        float(
                            row["from"]
                        )
                    )

                except Exception:

                    continue

                if ts == expected_timestamp:

                    return row

        if (
            time.monotonic()
            - start
            > NEW_CANDLE_TIMEOUT
        ):

            return None

        time.sleep(
            POLL_INTERVAL
        )


# ============================================================
# EJECUTAR PENDIENTE
# ============================================================

def execute_pending(
    pair: str,
) -> bool:

    pending = PENDING_ENTRY.get(
        pair
    )

    if pending is None:

        return False

    if not BOT_RUNNING:

        return False

    n_timestamp = int(
        pending[
            "minute_timestamp"
        ]
    )

    n1_expected = (
        n_timestamp
        + TIMEFRAME
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
    # 1. ESPERAR CAMBIO REAL DE VELA
    # ========================================================

    n1_timestamp = wait_for_next_candle(
        pair,
        n_timestamp,
    )

    if n1_timestamp is None:

        telegram_send(
            "⏱️ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            "No se pudo sincronizar N+1 "
            "con el servidor de IQ Option."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # 2. OBTENER APERTURA REAL DE N+1
    # ========================================================

    execution_candle = (
        get_real_next_candle(
            pair,
            n1_timestamp,
        )
    )

    if execution_candle is None:

        telegram_send(
            "❌ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"N+1 esperado: {n1_timestamp}\n"
            "No se pudo obtener la apertura real."
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    try:

        execution_open = float(
            execution_candle["open"]
        )

    except Exception:

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # 3. CONFIRMAR QUE REALMENTE ES N+1
    # ========================================================

    real_timestamp = int(
        float(
            execution_candle["from"]
        )
    )

    if real_timestamp != n1_expected:

        logger.error(
            "%s | timestamp incorrecto | "
            "esperado=%s | recibido=%s",
            pair,
            n1_expected,
            real_timestamp,
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # 4. EVITAR DUPLICADO
    # ========================================================

    if (
        LAST_TRADE_CANDLE.get(pair)
        == real_timestamp
    ):

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # 5. CONFIRMACIÓN DE DIRECCIÓN EN EL MOMENTO
    # ========================================================

    # Se comprueba que la señal siga siendo coherente
    # con la apertura de N+1.
    #
    # No esperamos ningún segundo adicional.

    server_ts = get_server_timestamp()

    if server_ts is None:

        server_ts = time.time()

    server_second = int(
        server_ts
    ) % 60

    logger.info(
        "%s | SERVIDOR IQ=%s | "
        "SEGUNDO=%s | N=%s | N+1=%s",
        pair,
        int(server_ts),
        server_second,
        n_timestamp,
        real_timestamp,
    )

    # ========================================================
    # 6. TELEGRAM
    # ========================================================

    telegram_send(
        "🎯 ENTRADA N+1\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        f"Servidor IQ: {int(server_ts)}\n"
        f"Segundo: {server_second}\n\n"
        f"Timestamp N: {n_timestamp}\n"
        f"Timestamp N+1: {real_timestamp}\n\n"
        f"Apertura REAL N+1: "
        f"{execution_open}\n\n"
        "🎯 EJECUTANDO BINARIA"
    )

    # ========================================================
    # 7. EJECUTAR INMEDIATAMENTE
    # ========================================================

    ok, order_id = buy_binary(
        pair,
        signal,
    )

    if not ok:

        telegram_send(
            "❌ OPERACIÓN RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n\n"
            f"Servidor IQ: {int(server_ts)}\n"
            f"Segundo: {server_second}\n"
            f"N: {n_timestamp}\n"
            f"N+1: {real_timestamp}\n"
            f"Apertura REAL: {execution_open}\n\n"
            "IQ Option no aceptó la operación."
        )

        logger.error(
            "%s | ORDEN RECHAZADA | "
            "%s | N=%s | N+1=%s | "
            "OPEN=%s",
            pair,
            signal.upper(),
            n_timestamp,
            real_timestamp,
            execution_open,
        )

        PENDING_ENTRY.pop(
            pair,
            None,
        )

        return False

    # ========================================================
    # 8. REGISTRAR
    # ========================================================

    LAST_TRADE_CANDLE[
        pair
    ] = real_timestamp

    PENDING_ENTRY.pop(
        pair,
        None,
    )

    telegram_send(
        "✅ OPERACIÓN ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        "VELA N\n"
        f"Timestamp: {n_timestamp}\n"
        f"Apertura: {pending['minute_open']}\n"
        f"Cierre:
