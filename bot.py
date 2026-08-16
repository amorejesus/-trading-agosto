
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests
from iqoptionapi.stable_api import IQ_Option

from strategy import analyze_market


# ============================================================
# CONFIG
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

TIMEFRAME = 60
EXPIRATION = 1
AMOUNT = 10
CANDLE_COUNT = 60

# MODO SNIPER:
# La señal se analiza sobre N cerrada.
# En cuanto el reloj del servidor pasa a N+1, se envía la orden.
SNIPER_POLL = 0.02

# Cantidad de velas mantenidas por el stream realtime.
REALTIME_MAXDICT = 80

# Tolerancia máxima permitida entre el timestamp esperado y el
# timestamp de la vela realtime. NO es una espera de ejecución.
# Solo evita usar una vela de otro minuto.
MAX_TS_DRIFT = 1

TRADE_COOLDOWN = 60.0

BOT_RUNNING = False
IQ: Optional[IQ_Option] = None

LIVE_STATE: Dict[str, Dict[str, Any]] = {}
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}

LAST_TRADE_TIME: Dict[str, float] = {}
LAST_TRADE_CANDLE: Dict[str, int] = {}

STREAM_STARTED: Dict[str, bool] = {}
STATE_LOCK = threading.RLock()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def _telegram_post(endpoint: str, data: Dict[str, Any], timeout: float = 3.0) -> bool:
    if not TELEGRAM_TOKEN:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{endpoint}"

    try:
        response = requests.post(
            url,
            data=data,
            timeout=timeout,
        )
        if response.status_code != 200:
            logger.warning(
                "Telegram %s: HTTP %s",
                endpoint,
                response.status_code,
            )
            return False
        return True
    except Exception as exc:
        # Telegram NUNCA debe detener ni retrasar el sniper.
        logger.warning("Telegram %s: %s", endpoint, exc)
        return False


def telegram_send(message: str) -> None:
    """
    Envío asíncrono. El hilo de trading no espera a Telegram.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    def worker() -> None:
        _telegram_post(
            "sendMessage",
            {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=3.0,
        )

    threading.Thread(
        target=worker,
        daemon=True,
        name="telegram-send",
    ).start()


def telegram_command_loop() -> None:
    global BOT_RUNNING

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    last_update_id: Optional[int] = None
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"

    while True:
        try:
            params: Dict[str, Any] = {
                "timeout": 1,
            }

            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            response = requests.get(
                url,
                params=params,
                timeout=3,
            )

            if response.status_code != 200:
                time.sleep(1)
                continue

            data = response.json()

            if not data.get("ok"):
                time.sleep(0.5)
                continue

            for update in data.get("result", []):
                update_id = update.get("update_id")
                if update_id is not None:
                    last_update_id = int(update_id)

                message = update.get("message") or {}
                text = str(message.get("text", "")).strip().lower()
                chat_id = str(
                    (message.get("chat") or {}).get("id", "")
                )

                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text == "/start":
                    BOT_RUNNING = True
                    telegram_send(
                        "🟢 BOT SNIPER ACTIVADO\n\n"
                        "DIGITAL OTC\n"
                        "EURUSD-OTC\n"
                        "GBPUSD-OTC\n"
                        "EURJPY-OTC\n\n"
                        "⏱ Temporalidad: 1 minuto\n"
                        "💵 Importe: $10\n\n"
                        "N se analiza cerrada.\n"
                        "N nunca se opera.\n"
                        "🎯 N+1 se ejecuta inmediatamente al abrir.\n"
                        "⚡ MODO SNIPER: sin ventana 01–03."
                    )

                elif text == "/stop":
                    BOT_RUNNING = False
                    telegram_send(
                        "🔴 BOT DETENIDO\n\n"
                        "No se abrirán nuevas operaciones."
                    )

                elif text == "/status":
                    status = "🟢 ACTIVO" if BOT_RUNNING else "🔴 DETENIDO"
                    telegram_send(
                        "📊 ESTADO\n\n"
                        f"Estado: {status}\n"
                        "Modo: SNIPER\n"
                        "Mercado: DIGITAL OTC\n"
                        "Temporalidad: 1 minuto\n"
                        "Expiración: 1 minuto\n"
                        "Importe: $10\n"
                        f"Pares: {', '.join(PAIRS)}"
                    )

        except Exception as exc:
            logger.warning("Telegram commands: %s", exc)
            time.sleep(1)


# ============================================================
# IQ OPTION
# ============================================================

def connect_iq() -> bool:
    global IQ

    if not IQ_EMAIL or not IQ_PASSWORD:
        raise ValueError("Faltan IQ_EMAIL/IQ_PASSWORD")

    logger.info("Conectando a IQ Option...")

    IQ = IQ_Option(
        IQ_EMAIL,
        IQ_PASSWORD,
    )

    connected, reason = IQ.connect()

    if not connected:
        raise ConnectionError(
            f"No se pudo conectar a IQ Option: {reason}"
        )

    logger.info("IQ Option conectado.")

    # IMPORTANTE:
    # El reloj usado para el sniper es el reloj del servidor de IQ.
    server_ts = get_iq_server_timestamp()

    logger.info(
        "Reloj IQ sincronizado: %.3f | minuto=%d",
        server_ts,
        int(server_ts // TIMEFRAME) * TIMEFRAME,
    )

    start_realtime_streams()

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "⚡ MODO SNIPER\n"
        "N cerrada → N+1 inmediata\n"
        "Sin ventana 01–03."
    )

    return True


def ensure_connection() -> bool:
    global IQ

    try:
        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        logger.warning("Conexión perdida. Reconectando...")

        connected, reason = IQ.connect()

        if not connected:
            logger.error(
                "No se pudo reconectar: %s",
                reason,
            )
            return False

        STREAM_STARTED.clear()
        start_realtime_streams()

        telegram_send("🟢 IQ Option reconectado.")

        return True

    except Exception as exc:
        logger.error("Error de conexión: %s", exc)
        return False


def get_iq_server_timestamp() -> float:
    if IQ is None:
        return time.time()

    try:
        value = IQ.get_server_timestamp()
        value = float(value)

        if value > 0:
            return value

    except Exception as exc:
        logger.debug(
            "get_server_timestamp error: %s",
            exc,
        )

    # Fallback solamente si la API no responde.
    return time.time()


# ============================================================
# REALTIME CANDLE STREAM
# ============================================================

def start_realtime_streams() -> None:
    if IQ is None:
        return

    for pair in PAIRS:
        try:
            if STREAM_STARTED.get(pair):
                continue

            IQ.start_candles_stream(
                pair,
                TIMEFRAME,
                REALTIME_MAXDICT,
            )

            STREAM_STARTED[pair] = True

            logger.info(
                "%s | realtime stream iniciado | %ss",
                pair,
                TIMEFRAME,
            )

        except Exception as exc:
            STREAM_STARTED[pair] = False
            logger.warning(
                "%s | no se pudo iniciar realtime stream: %s",
                pair,
                exc,
            )


def realtime_candles(pair: str) -> Dict[Any, Any]:
    if IQ is None:
        return {}

    try:
        data = IQ.get_realtime_candles(
            pair,
            TIMEFRAME,
        )

        if isinstance(data, dict):
            return data

    except Exception as exc:
        logger.debug(
            "%s | realtime candles: %s",
            pair,
            exc,
        )

    return {}


def realtime_dataframe(pair: str) -> pd.DataFrame:
    """
    Convierte el buffer realtime de IQ Option a OHLC.
    """
    candles = realtime_candles(pair)

    if not candles:
        return pd.DataFrame()

    rows = []

    for key, candle in candles.items():
        if not isinstance(candle, dict):
            continue

        try:
            ts = int(
                float(
                    candle.get(
                        "from",
                        key,
                    )
                )
            )

            o = float(candle.get("open"))
            h = float(
                candle.get(
                    "max",
                    candle.get("high"),
                )
            )
            l = float(
                candle.get(
                    "min",
                    candle.get("low"),
                )
            )
            c = float(candle.get("close"))

            rows.append(
                {
                    "from": ts,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                }
            )

        except Exception:
            continue

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    df.drop_duplicates(
        subset=["from"],
        keep="last",
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

    return df.tail(CANDLE_COUNT).reset_index(drop=True)


# ============================================================
# HISTORICAL CLOSED CANDLES
# ============================================================

def get_closed_candles(pair: str) -> Optional[pd.DataFrame]:
    """
    get_candles() se usa solamente para historial/cierre.
    No se utiliza para detectar el inicio de N+1.
    """
    if IQ is None:
        return None

    try:
        candles = IQ.get_candles(
            pair,
            TIMEFRAME,
            CANDLE_COUNT,
            get_iq_server_timestamp(),
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
        ]

        for col in required:
            if col not in df.columns:
                return None

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce",
            )

        if "from" not in df.columns:
            return None

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce",
        )

        df.dropna(
            subset=required + ["from"],
            inplace=True,
        )

        df["from"] = df["from"].astype(int)

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

        return df.tail(CANDLE_COUNT).reset_index(drop=True)

    except Exception as exc:
        logger.warning(
            "%s | error historial cerrado: %s",
            pair,
            exc,
        )
        return None


# ============================================================
# TIME / CANDLE HELPERS
# ============================================================

def floor_candle_timestamp(
    timestamp: float,
) -> int:
    return int(timestamp // TIMEFRAME) * TIMEFRAME


def candle_values(
    row: pd.Series,
) -> Dict[str, float]:
    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    }


def get_row_by_ts(
    df: pd.DataFrame,
    ts: int,
) -> Optional[pd.Series]:
    if df is None or df.empty or "from" not in df.columns:
        return None

    rows = df[df["from"].astype(int) == int(ts)]

    if rows.empty:
        return None

    return rows.iloc[-1]


# ============================================================
# STATE
# ============================================================

def reset_live_state(
    pair: str,
    ts: int,
) -> None:
    LIVE_STATE[pair] = {
        "timestamp": int(ts),
        "signal": None,
        "score": 0,
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "analyzed": False,
        "invalidated": False,
    }


def save_pending_signal(
    pair: str,
    continuity_ts: int,
    signal: str,
    score: int,
    values: Dict[str, float],
) -> None:
    """
    Guarda una señal de N.

    N+1 SIEMPRE es continuidad_ts + 60.
    """
    execution_ts = int(
        continuity_ts + TIMEFRAME
    )

    with STATE_LOCK:
        PENDING_ENTRY[pair] = {
            "signal": signal,
            "score": int(score),
            "continuity_ts": int(continuity_ts),
            "execution_ts": execution_ts,
            "continuity_open": float(values["open"]),
            "continuity_high": float(values["high"]),
            "continuity_low": float(values["low"]),
            "continuity_close": float(values["close"]),
            "created_at": time.time(),
            "executed": False,
        }

    logger.info(
        "%s | SNIPER ARMADO | %s | N=%s | N+1=%s",
        pair,
        signal.upper(),
        continuity_ts,
        execution_ts,
    )


def cooldown_active(pair: str) -> bool:
    last = LAST_TRADE_TIME.get(pair, 0.0)

    return (
        time.time() - last
    ) < TRADE_COOLDOWN


# ============================================================
# ANALYZE CLOSED N
# ============================================================

def analyze_closed_candle(
    pair: str,
    expected_closed_ts: int,
) -> bool:
    """
    Busca la vela N cerrada y genera la señal.

    Prioridad:
      1. realtime stream
      2. get_candles() como respaldo

    Nunca analiza N+1 para crear una señal.
    """
    realtime = realtime_dataframe(pair)

    closed_row = get_row_by_ts(
        realtime,
        expected_closed_ts,
    )

    df = realtime

    if closed_row is None:
        historical = get_closed_candles(pair)

        if historical is not None:
            closed_row = get_row_by_ts(
                historical,
                expected_closed_ts,
            )
            df = historical

    if closed_row is None:
        logger.warning(
            "%s | N cerrada %s todavía no disponible",
            pair,
            expected_closed_ts,
        )
        return False

    if df is None or len(df) < 35:
        logger.warning(
            "%s | historial insuficiente para N=%s",
            pair,
            expected_closed_ts,
        )
        return False

    # Asegurar que la última vela usada por strategy sea EXACTAMENTE N.
    df = df[df["from"].astype(int) <= expected_closed_ts].copy()

    if len(df) < 35:
        return False

    result = analyze_market(df)

    values = candle_values(closed_row)

    signal = result.get("signal")
    score = int(result.get("score") or 0)

    logger.info(
        "%s | CIERRE N | ts=%s | O=%s H=%s L=%s C=%s | "
        "signal=%s | score=%s | %s",
        pair,
        expected_closed_ts,
        values["open"],
        values["high"],
        values["low"],
        values["close"],
        signal,
        score,
        result.get("reason"),
    )

    if signal not in ("call", "put"):
        return True

    with STATE_LOCK:
        LIVE_STATE[pair] = {
            "timestamp": int(expected_closed_ts),
            "signal": signal,
            "score": score,
            "open": values["open"],
            "high": values["high"],
            "low": values["low"],
            "close": values["close"],
            "analyzed": True,
            "invalidated": False,
        }

    save_pending_signal(
        pair,
        expected_closed_ts,
        signal,
        score,
        values,
    )

    direction = (
        "CALL 🟢"
        if signal == "call"
        else "PUT 🔴"
    )

    telegram_send(
        "📌 SEÑAL CONFIRMADA AL CIERRE\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N — CERRADA:\n"
        f"Timestamp: {expected_closed_ts}\n"
        f"Apertura: {values['open']}\n"
        f"Máximo: {values['high']}\n"
        f"Mínimo: {values['low']}\n"
        f"Cierre: {values['close']}\n\n"
        "VELA N+1 — OBJETIVO:\n"
        f"Timestamp: {expected_closed_ts + TIMEFRAME}\n\n"
        f"Score: {score}/10\n"
        "🚫 N nunca se opera.\n"
        "⚡ SNIPER: ejecutar al abrir N+1."
    )

    return True


# ============================================================
# SNIPER ENTRY
# ============================================================

def get_realtime_open(
    pair: str,
    execution_ts: int,
) -> Optional[float]:
    df = realtime_dataframe(pair)

    row = get_row_by_ts(
        df,
        execution_ts,
    )

    if row is None:
        return None

    try:
        return float(row["open"])
    except Exception:
        return None


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

        if isinstance(result, tuple):
            if len(result) >= 2:
                return (
                    bool(result[0]),
                    result[1],
                )

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
            return True, result

        return False, result

    except Exception as exc:
        logger.error(
            "%s | buy_digital error: %s",
            pair,
            exc,
        )
        return False, None


def execute_sniper(
    pair: str,
    pending: Dict[str, Any],
) -> bool:
    """
    Ejecuta SOLO cuando el reloj del servidor ya está en N+1.

    No existe ventana 01-03.
    No existe espera artificial.
    No existe cancelación por elapsed > 3.
    """
    execution_ts = int(
        pending["execution_ts"]
    )
    signal = str(
        pending["signal"]
    )

    # --------------------------------------------------------
    # 1. Verificación del reloj de IQ.
    # --------------------------------------------------------
    server_now = get_iq_server_timestamp()
    current_candle_ts = floor_candle_timestamp(
        server_now
    )

    if current_candle_ts < execution_ts:
        return False

    # Si por alguna razón el bot quedó dormido y ya estamos en
    # un minuto posterior, NO trasladamos la señal a otro minuto.
    if current_candle_ts > execution_ts:
        logger.warning(
            "%s | SNIPER DESCARTADO | objetivo=%s | "
            "servidor=%s | minuto_actual=%s",
            pair,
            execution_ts,
            server_now,
            current_candle_ts,
        )

        with STATE_LOCK:
            PENDING_ENTRY.pop(pair, None)

        telegram_send(
            "⚠️ SNIPER DESCARTADO\n\n"
            f"Par: {pair}\n"
            f"N+1 objetivo: {execution_ts}\n"
            f"Minuto actual IQ: {current_candle_ts}\n\n"
            "No se trasladó la señal a otra vela."
        )

        return False

    # --------------------------------------------------------
    # 2. Evitar duplicación.
    # --------------------------------------------------------
    if LAST_TRADE_CANDLE.get(pair) == execution_ts:
        with STATE_LOCK:
            PENDING_ENTRY.pop(pair, None)
        return False

    if cooldown_active(pair):
        return False

    # --------------------------------------------------------
    # 3. Leer apertura realtime de N+1.
    #
    # Esto es solo informativo. NO esperamos a que aparezca
    # para ejecutar. El disparador es el reloj de IQ.
    # --------------------------------------------------------
    realtime_open = get_realtime_open(
        pair,
        execution_ts,
    )

    if realtime_open is None:
        logger.warning(
            "%s | N+1=%s | realtime open aún no llegó; "
            "ejecutando por reloj IQ",
            pair,
            execution_ts,
        )

    elapsed = server_now - execution_ts

    logger.info(
        "%s | ⚡ SNIPER DISPARO | N+1=%s | "
        "server=%.3f | elapsed=%.3f | realtime_open=%s",
        pair,
        execution_ts,
        server_now,
        elapsed,
        realtime_open,
    )

    # --------------------------------------------------------
    # 4. TELEGRAM NO SE ESPERA.
    # El mensaje se manda después/en paralelo.
    # --------------------------------------------------------
    telegram_send(
        "⚡ SNIPER EJECUTANDO\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        f"N cierre: {pending['continuity_close']}\n"
        f"N+1 timestamp: {execution_ts}\n"
        f"N+1 apertura realtime: {realtime_open}\n"
        f"Reloj IQ: {server_now:.3f}\n"
        f"Offset N+1: {elapsed:.3f}s\n\n"
        "🚫 N nunca se opera.\n"
        "⚡ Entrada inmediata en N+1."
    )

    # --------------------------------------------------------
    # 5. ÚLTIMA VERIFICACIÓN JUSTO ANTES DE LA ORDEN.
    # --------------------------------------------------------
    server_now_2 = get_iq_server_timestamp()
    current_ts_2 = floor_candle_timestamp(
        server_now_2
    )

    if current_ts_2 != execution_ts:
        logger.warning(
            "%s | ORDEN CANCELADA POR CAMBIO DE VELA | "
            "objetivo=%s | actual=%s",
            pair,
            execution_ts,
            current_ts_2,
        )

        with STATE_LOCK:
            PENDING_ENTRY.pop(pair, None)

        return False

    # --------------------------------------------------------
    # 6. ORDEN.
    # --------------------------------------------------------
    sent_at = get_iq_server_timestamp()

    ok, order_id = buy_digital(
        pair,
        signal,
    )

    if not ok:
        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"N+1: {execution_ts}\n"
            f"Reloj IQ al envío: {sent_at:.3f}\n"
            f"Apertura realtime: {realtime_open}\n\n"
            "La señal NO se trasladará a otra vela."
        )

        logger.error(
            "%s | DIGITAL RECHAZADA | signal=%s | "
            "N+1=%s | send_ts=%.3f | open=%s",
            pair,
            signal,
            execution_ts,
            sent_at,
            realtime_open,
        )

        with STATE_LOCK:
            PENDING_ENTRY.pop(pair, None)

        return False

    # --------------------------------------------------------
    # 7. REGISTRO FINAL.
    # --------------------------------------------------------
    LAST_TRADE_TIME[pair] = time.time()
    LAST_TRADE_CANDLE[pair] = execution_ts

    with STATE_LOCK:
        PENDING_ENTRY.pop(pair, None)

    telegram_send(
        "✅ SNIPER EJECUTADO\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n\n"
        f"N cierre: {pending['continuity_close']}\n"
        f"N+1 timestamp: {execution_ts}\n"
        f"N+1 apertura realtime: {realtime_open}\n"
        f"Reloj IQ envío: {sent_at:.3f}\n"
        f"ID: {order_id}\n\n"
        "⚡ Entrada inmediata en N+1\n"
        "⏱ Expiración: 1 minuto"
    )

    logger.info(
        "%s | ✅ SNIPER EJECUTADO | %s | "
        "N=%s | N+1=%s | open=%s | send=%.3f | ID=%s",
        pair,
        signal.upper(),
        pending["continuity_ts"],
        execution_ts,
        realtime_open,
        sent_at,
        order_id,
    )

    return True


# ============================================================
# PAIR ENGINE
# ============================================================

def process_pair(pair: str) -> None:
    if IQ is None:
        return

    # --------------------------------------------------------
    # El reloj del servidor define cuál es N.
    #
    # Ejemplo:
    # server=...479.4
    # current=...420
    # N cerrado=...360
    #
    # Al entrar en ...480, N será ...420.
    # --------------------------------------------------------
    server_now = get_iq_server_timestamp()
    current_ts = floor_candle_timestamp(server_now)
    closed_ts = current_ts - TIMEFRAME

    state = LIVE_STATE.get(pair)

    # --------------------------------------------------------
    # Si aún no tenemos analizada la vela N, analizarla.
    # --------------------------------------------------------
    if (
        state is None
        or int(state.get("timestamp", -1)) != closed_ts
    ):
        LIVE_STATE[pair] = {
            "timestamp": closed_ts,
            "signal": None,
            "score": 0,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "analyzed": False,
            "invalidated": False,
        }

        # Intentar inmediatamente obtener N cerrada.
        analyze_closed_candle(
            pair,
            closed_ts,
        )

    # --------------------------------------------------------
    # SNIPER:
    # si hay señal para N, N+1 es exactamente current_ts.
    # No se espera a que get_candles() "descubra" N+1.
    # --------------------------------------------------------
    pending = PENDING_ENTRY.get(pair)

    if pending is None:
        return

    if int(pending["execution_ts"]) != current_ts:
        return

    execute_sniper(
        pair,
        pending,
    )


# ============================================================
# MAIN
# ============================================================

def analyze_all_pairs() -> None:
    if not BOT_RUNNING:
        return

    for pair in PAIRS:
        if not BOT_RUNNING:
            return

        try:
            process_pair(pair)
        except Exception:
            logger.exception(
                "Error procesando %s",
                pair,
            )


def main() -> None:
    global BOT_RUNNING

    logger.info("======================================")
    logger.info("BOT DIGITAL OTC - MODO SNIPER")
    logger.info(
        "PARES: %s",
        ", ".join(PAIRS),
    )
    logger.info("TIMEFRAME: 1M")
    logger.info("EXPIRATION: 1M")
    logger.info("AMOUNT: $%s", AMOUNT)
    logger.info("SNIPER POLL: %.3fs", SNIPER_POLL)
    logger.info("======================================")

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

    # Telegram commands se ejecutan en otro hilo.
    threading.Thread(
        target=telegram_command_loop,
        daemon=True,
        name="telegram-commands",
    ).start()

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

    BOT_RUNNING = False

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "⚡ MODO SNIPER\n\n"
        "N = vela cerrada analizada.\n"
        "N+1 = siguiente vela.\n"
        "🚫 N nunca se opera.\n"
        "⚡ N+1 se ejecuta inmediatamente.\n"
        "⏱ Sin ventana 01–03.\n"
        "💵 $10\n"
        "⏱ Expiración 1 minuto."
    )

    while True:
        try:
            if not BOT_RUNNING:
                time.sleep(0.25)
                continue

            if not ensure_connection():
                time.sleep(1)
                continue

            # Poll corto solamente para no perder el cambio de minuto.
            analyze_all_pairs()

            time.sleep(SNIPER_POLL)

        except KeyboardInterrupt:
            BOT_RUNNING = False
            telegram_send(
                "🔴 BOT DETENIDO MANUALMENTE"
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
            time.sleep(1)


if __name__ == "__main__":
    main()
