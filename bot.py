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

# Poll pequeño para detectar el cambio de vela rápido.
POLL_INTERVAL = 0.08

# Ventana máxima para recuperar una vela nueva si get_candles()
# llega con retraso de red. No cancela la señal por un solo fallo.
OPEN_RETRY_WINDOW = 4.0

# Evita dos operaciones del mismo par en la misma vela.
TRADE_COOLDOWN = 60.0

BOT_RUNNING = False
LAST_UPDATE_ID: Optional[int] = None
IQ: Optional[IQ_Option] = None

# Estado de la vela que está viva.
LIVE_STATE: Dict[str, Dict[str, Any]] = {}

# Señales que pertenecen a la vela anterior y esperan N+1.
PENDING_ENTRY: Dict[str, Dict[str, Any]] = {}

LAST_TRADE_TIME: Dict[str, float] = {}
LAST_TRADE_CANDLE: Dict[str, int] = {}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        r = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=5,
        )
        if r.status_code != 200:
            logger.error("Telegram %s: %s", r.status_code, r.text)
            return False
        return True
    except Exception as exc:
        logger.error("Telegram error: %s", exc)
        return False


def check_commands() -> None:
    global LAST_UPDATE_ID, BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 0}

    if LAST_UPDATE_ID is not None:
        params["offset"] = LAST_UPDATE_ID + 1

    try:
        data = requests.get(url, params=params, timeout=3).json()

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            LAST_UPDATE_ID = update.get("update_id")

            message = update.get("message", {})
            text = str(message.get("text", "")).strip().lower()
            chat_id = str(message.get("chat", {}).get("id", ""))

            if chat_id != str(TELEGRAM_CHAT_ID):
                continue

            if text == "/start":
                BOT_RUNNING = True
                telegram_send(
                    "🟢 BOT ACTIVADO\n\n"
                    "DIGITAL OTC\n"
                    "EURUSD-OTC\n"
                    "GBPUSD-OTC\n"
                    "EURJPY-OTC\n\n"
                    "⏱ 1 minuto\n"
                    "💵 Importe: $10\n\n"
                    "La vela N se analiza completa.\n"
                    "La entrada pertenece EXCLUSIVAMENTE a N+1.\n"
                    "🚀 Entrada objetivo: APERTURA."
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
                    "📊 ESTADO DEL BOT\n\n"
                    f"Estado: {status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    "Importe: $10\n"
                    f"Pares: {', '.join(PAIRS)}"
                )

    except Exception as exc:
        logger.error("Error Telegram commands: %s", exc)


# ============================================================
# IQ OPTION
# ============================================================

def connect_iq() -> bool:
    global IQ

    if not IQ_EMAIL or not IQ_PASSWORD:
        raise ValueError("Faltan IQ_EMAIL/IQ_PASSWORD")

    logger.info("Conectando a IQ Option...")
    IQ = IQ_Option(IQ_EMAIL, IQ_PASSWORD)

    connected, reason = IQ.connect()

    if not connected:
        raise ConnectionError(f"No se pudo conectar: {reason}")

    logger.info("IQ Option conectado")
    telegram_send(
        "🟢 CONECTADO A IQ OPTION\n\n"
        "Mercado: DIGITAL OTC\n"
        "Entrada: apertura de N+1\n"
        "Expiración: 1 minuto"
    )
    return True


def ensure_connection() -> bool:
    global IQ

    try:
        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        logger.warning("Conexión perdida; reconectando...")
        connected, reason = IQ.connect()

        if not connected:
            logger.error("No se pudo reconectar: %s", reason)
            return False

        telegram_send("🟢 IQ Option reconectado.")
        return True

    except Exception as exc:
        logger.error("Error conexión: %s", exc)
        return False


# ============================================================
# CANDLES
# ============================================================

def get_candles(pair: str) -> Optional[pd.DataFrame]:
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
            columns={"max": "high", "min": "low"},
            inplace=True,
        )

        required = ["open", "close", "high", "low"]

        for col in required:
            if col not in df.columns:
                return None
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df.dropna(subset=required, inplace=True)

        if "from" in df.columns:
            df["from"] = pd.to_numeric(
                df["from"], errors="coerce"
            )
            df.dropna(subset=["from"], inplace=True)
            df.sort_values("from", inplace=True)

        df.reset_index(drop=True, inplace=True)

        if len(df) > CANDLE_COUNT:
            df = df.tail(CANDLE_COUNT).reset_index(drop=True)

        return df

    except Exception as exc:
        logger.error("Velas %s: %s", pair, exc)
        return None


def candle_timestamp(
    df: pd.DataFrame,
    index: int = -1,
) -> Optional[int]:
    if df is None or df.empty or "from" not in df.columns:
        return None

    try:
        return int(df.iloc[index]["from"])
    except Exception:
        return None


def candle_values(
    df: pd.DataFrame,
    index: int,
) -> Dict[str, float]:
    row = df.iloc[index]
    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    }


# ============================================================
# ESTADO
# ============================================================

def reset_live_state(pair: str, ts: int) -> None:
    LIVE_STATE[pair] = {
        "timestamp": ts,
        "signal": None,
        "candidate_seen": False,
        "invalidated": False,
        "open": None,
        "last_close": None,
        "signal_score": 0,
    }


def update_live_state(
    pair: str,
    df: pd.DataFrame,
    result: Dict[str, Any],
) -> None:
    ts = candle_timestamp(df, -1)
    if ts is None:
        return

    state = LIVE_STATE.get(pair)

    if state is None or state["timestamp"] != ts:
        reset_live_state(pair, ts)
        state = LIVE_STATE[pair]

        values = candle_values(df, -1)
        state["open"] = values["open"]
        state["last_close"] = values["close"]

    if state["invalidated"]:
        state["last_close"] = float(df.iloc[-1]["close"])
        return

    signal = result.get("signal")

    if signal in ("call", "put"):

        if not state["candidate_seen"]:
            state["signal"] = signal
            state["candidate_seen"] = True
            state["signal_score"] = int(result.get("score") or 0)

            direction = (
                "CALL 🟢" if signal == "call" else "PUT 🔴"
            )

            telegram_send(
                "📌 SEÑAL CONFIRMADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {direction}\n\n"
                "VELA N ANALIZADA\n"
                f"Apertura: {state['open']}\n"
                f"Cierre actual: "
                f"{float(df.iloc[-1]['close'])}\n"
                f"Score: {state['signal_score']}/10\n\n"
                "✅ Señal guardada.\n"
                "🚫 NO se ejecuta en N.\n"
                "➡️ Pertenece EXCLUSIVAMENTE a N+1.\n"
                "🚀 Entrada objetivo: APERTURA."
            )

        elif state["signal"] != signal:
            state["invalidated"] = True
            state["signal"] = None

            telegram_send(
                "⚠️ SEÑAL INVALIDADA\n\n"
                f"Par: {pair}\n"
                f"Vela: {ts}\n"
                "La dirección cambió durante N.\n"
                "No habrá entrada en N+1."
            )

    else:
        # No cancelar por una lectura transitoria de la API.
        # Una señal ya confirmada permanece guardada hasta el cambio
        # real de timestamp.
        pass

    state["last_close"] = float(df.iloc[-1]["close"])


# ============================================================
# PENDING ENTRY
# ============================================================

def save_pending_entry(
    pair: str,
    state: Dict[str, Any],
) -> None:
    signal = state.get("signal")

    if signal not in ("call", "put"):
        return

    if pair in PENDING_ENTRY:
        return

    PENDING_ENTRY[pair] = {
        "signal": signal,
        "continuity_ts": int(state["timestamp"]),
        "continuity_open": float(state["open"]),
        "continuity_close": float(state["last_close"]),
        "created_at": time.time(),
        "deadline": time.time() + OPEN_RETRY_WINDOW,
    }

    logger.info(
        "%s | PENDIENTE %s | N=%s",
        pair,
        signal.upper(),
        state["timestamp"],
    )


def cooldown_active(pair: str) -> bool:
    last = LAST_TRADE_TIME.get(pair, 0.0)
    return (time.time() - last) < TRADE_COOLDOWN


# ============================================================
# DIGITAL ENTRY
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

        if isinstance(result, tuple):
            if len(result) >= 2:
                return bool(result[0]), result[1]
            return bool(result[0]), None

        if result not in (None, False, "error", -1):
            return True, result

        return False, result

    except Exception as exc:
        logger.error(
            "buy_digital %s %s: %s",
            pair,
            signal,
            exc,
        )
        return False, None


def try_execute_pending(pair: str) -> bool:
    pending = PENDING_ENTRY.get(pair)

    if pending is None:
        return False

    if cooldown_active(pair):
        return False

    if time.time() > pending["deadline"]:
        telegram_send(
            "⏳ ENTRADA NO EJECUTADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {pending['signal'].upper()}\n"
            "La nueva vela no pudo confirmarse dentro de "
            f"{OPEN_RETRY_WINDOW:.1f} s.\n\n"
            "La señal no se ejecutó en N."
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    df = get_candles(pair)

    if df is None or len(df) < 2:
        return False

    execution_ts = candle_timestamp(df, -1)

    if execution_ts is None:
        return False

    continuity_ts = int(pending["continuity_ts"])

    # CLAVE:
    # si la API sigue entregando N, NO cancelamos la señal.
    # Esperamos a que aparezca N+1.
    if execution_ts <= continuity_ts:
        return False

    if LAST_TRADE_CANDLE.get(pair) == execution_ts:
        PENDING_ENTRY.pop(pair, None)
        return False

    execution_values = candle_values(df, -1)
    open_price = execution_values["open"]
    signal = pending["signal"]

    direction_text = (
        "CALL 🟢" if signal == "call" else "PUT 🔴"
    )

    telegram_send(
        "⚡ ENTRADA EN APERTURA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction_text}\n\n"
        "VELA N (CONFIRMACIÓN):\n"
        f"Apertura: {pending['continuity_open']}\n"
        f"Cierre: {pending['continuity_close']}\n\n"
        "VELA N+1 (EJECUCIÓN):\n"
        f"Timestamp: {execution_ts}\n"
        f"Apertura: {open_price}\n\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto\n"
        "🎯 Mercado: DIGITAL OTC"
    )

    ok, order_id = buy_digital(pair, signal)

    if not ok:
        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"Apertura detectada: {open_price}\n\n"
            "La señal pertenecía a N+1, pero IQ Option "
            "no aceptó la orden."
        )
        logger.error(
            "%s | DIGITAL RECHAZADA | %s | N+1=%s",
            pair,
            signal,
            execution_ts,
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    LAST_TRADE_TIME[pair] = time.time()
    LAST_TRADE_CANDLE[pair] = execution_ts
    PENDING_ENTRY.pop(pair, None)

    telegram_send(
        "✅ OPERACIÓN DIGITAL ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"Entrada: {open_price}\n"
        "💵 Importe: $10\n"
        "⏱ Expiración: 1 minuto\n"
        f"Timestamp N+1: {execution_ts}\n"
        f"ID: {order_id}"
    )

    logger.info(
        "%s | DIGITAL %s | entrada=%s | N+1=%s | ID=%s",
        pair,
        signal.upper(),
        open_price,
        execution_ts,
        order_id,
    )

    return True


# ============================================================
# PROCESS PAIR
# ============================================================

def process_pair(pair: str) -> None:
    df = get_candles(pair)

    if df is None or len(df) < 30:
        return

    ts = candle_timestamp(df, -1)

    if ts is None:
        return

    state = LIVE_STATE.get(pair)

    if state is None:
        reset_live_state(pair, ts)
        state = LIVE_STATE[pair]

    elif int(state["timestamp"]) != ts:

        previous_ts = int(state["timestamp"])
        previous_signal = state.get("signal")
        invalidated = bool(state.get("invalidated", False))

        # Guardar señal N para ejecutar en N+1.
        if (
            previous_signal in ("call", "put")
            and not invalidated
            and previous_ts < ts
        ):
            save_pending_entry(pair, state)

        reset_live_state(pair, ts)

    # La entrada pendiente tiene prioridad absoluta.
    if pair in PENDING_ENTRY:
        try_execute_pending(pair)

    # Analizar la vela actual.
    result = analyze_market(df)

    logger.info(
        "%s | ts=%s | signal=%s | score=%s | %s",
        pair,
        ts,
        result.get("signal"),
        result.get("score"),
        result.get("reason"),
    )

    update_live_state(pair, df, result)


# ============================================================
# MAIN LOOP
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
            logger.exception("Error procesando %s", pair)


def main() -> None:
    global BOT_RUNNING

    logger.info("====================================")
    logger.info("BOT DIGITAL OTC - CONTINUIDAD")
    logger.info("PARES: %s", ", ".join(PAIRS))
    logger.info("TIMEFRAME: 1M")
    logger.info("EXPIRATION: 1M")
    logger.info("AMOUNT: $%s", AMOUNT)
    logger.info("====================================")

    required = {
        "IQ_EMAIL": IQ_EMAIL,
        "IQ_PASSWORD": IQ_PASSWORD,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }

    missing = [k for k, v in required.items() if not v]

    if missing:
        logger.error(
            "Faltan variables: %s",
            ", ".join(missing),
        )
        return

    try:
        connect_iq()
    except Exception as exc:
        logger.exception("No se pudo iniciar IQ Option")
        telegram_send(
            "❌ ERROR DE CONEXIÓN\n\n"
            f"{exc}"
        )
        return

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "DIGITAL OTC\n"
        "EURUSD-OTC | GBPUSD-OTC | EURJPY-OTC\n\n"
        "⏱ 1 minuto\n"
        "💵 $10\n\n"
        "La señal se detecta en N.\n"
        "🚫 N nunca se opera.\n"
        "➡️ La operación pertenece a N+1.\n"
        "🚀 Objetivo: apertura de N+1."
    )

    while True:
        try:
            check_commands()

            if not BOT_RUNNING:
                time.sleep(1)
                continue

            if not ensure_connection():
                time.sleep(2)
                continue

            analyze_all_pairs()
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            BOT_RUNNING = False
            telegram_send("🔴 BOT DETENIDO MANUALMENTE")
            break

        except Exception as exc:
            logger.exception("Error principal")
            telegram_send(
                "⚠️ ERROR EN BOT\n\n"
                f"{exc}"
            )
            time.sleep(2)


if __name__ == "__main__":
    main()
