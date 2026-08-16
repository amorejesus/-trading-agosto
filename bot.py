from __future__ import annotations

import logging
import os
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

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC"]

TIMEFRAME = 60
EXPIRATION = 1
AMOUNT = 276
CANDLE_COUNT = 60

POLL_INTERVAL = 0.08

# Entrada exclusivamente entre segundo 1.0 y 3.0 de N+1.
ENTRY_MIN_SECOND = 1.0
ENTRY_MAX_SECOND = 3.0

TRADE_COOLDOWN = 60.0

BOT_RUNNING = False
LAST_UPDATE_ID: Optional[int] = None
IQ: Optional[IQ_Option] = None

# Última vela cerrada que ya fue procesada.
LAST_CONFIRMED_CANDLE: Dict[str, int] = {}

# Señal creada al cierre de N y esperando N+1.
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
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=1.5,
        )
        if r.status_code != 200:
            logger.warning("Telegram HTTP %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("Telegram no disponible: %s", exc)
        return False


def check_commands() -> None:
    global LAST_UPDATE_ID, BOT_RUNNING
    if not TELEGRAM_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params: Dict[str, Any] = {"timeout": 0}
    if LAST_UPDATE_ID is not None:
        params["offset"] = LAST_UPDATE_ID + 1
    try:
        data = requests.get(url, params=params, timeout=1.5).json()
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
                    "EURUSD-OTC\nGBPUSD-OTC\nEURJPY-OTC\n\n"
                    "N se analiza SOLO después de cerrar.\n"
                    "N nunca se opera.\n"
                    "Entrada: N+1, segundo 01–03."
                )
            elif text == "/stop":
                BOT_RUNNING = False
                telegram_send("🔴 BOT DETENIDO\n\nNo se abrirán nuevas operaciones.")
            elif text == "/status":
                status = "🟢 ACTIVO" if BOT_RUNNING else "🔴 DETENIDO"
                telegram_send(
                    "📊 ESTADO\n\n"
                    f"Estado: {status}\n"
                    "Mercado: DIGITAL OTC\n"
                    "Temporalidad: 1 minuto\n"
                    "Expiración: 1 minuto\n"
                    f"Importe: ${AMOUNT}\n"
                    f"Pares: {', '.join(PAIRS)}"
                )
    except Exception as exc:
        logger.warning("Error Telegram commands: %s", exc)


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
        "Confirmación: N cerrada\n"
        "Entrada: N+1, segundo 01–03\n"
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
            pair, TIMEFRAME, CANDLE_COUNT, time.time()
        )
        if not candles:
            return None
        df = pd.DataFrame(candles)
        if df.empty:
            return None
        df.rename(columns={"max": "high", "min": "low"}, inplace=True)
        required = ["open", "close", "high", "low"]
        for c in required:
            if c not in df.columns:
                return None
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df.dropna(subset=required, inplace=True)
        if "from" not in df.columns:
            logger.warning("%s | IQ no devolvió 'from'", pair)
            return None
        df["from"] = pd.to_numeric(df["from"], errors="coerce")
        df.dropna(subset=["from"], inplace=True)
        df["from"] = df["from"].astype("int64")
        df.sort_values("from", inplace=True)
        df.drop_duplicates(subset=["from"], keep="last", inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df.tail(CANDLE_COUNT).reset_index(drop=True)
    except Exception as exc:
        logger.error("Velas %s: %s", pair, exc)
        return None


def candle_timestamp(df: pd.DataFrame, index: int) -> Optional[int]:
    if df is None or df.empty or "from" not in df.columns:
        return None
    try:
        value = df.iloc[index]["from"]
        return None if pd.isna(value) else int(value)
    except Exception:
        return None


def candle_values(df: pd.DataFrame, index: int) -> Dict[str, float]:
    row = df.iloc[index]
    return {
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
    }


def sequential(previous_ts: int, current_ts: int) -> bool:
    return current_ts == previous_ts + TIMEFRAME


def cooldown_active(pair: str) -> bool:
    return time.time() - LAST_TRADE_TIME.get(pair, 0.0) < TRADE_COOLDOWN


# ============================================================
# CONFIRMAR N Y CREAR PENDIENTE PARA N+1
# ============================================================

def save_pending_entry(pair: str, df: pd.DataFrame) -> bool:
    if pair in PENDING_ENTRY or len(df) < 2:
        return False

    n_ts = candle_timestamp(df, -2)
    n1_ts = candle_timestamp(df, -1)
    if n_ts is None or n1_ts is None:
        return False

    if not sequential(n_ts, n1_ts):
        logger.warning(
            "%s | N/N+1 no consecutivas | N=%s N+1=%s",
            pair, n_ts, n1_ts
        )
        return False

    n = candle_values(df, -2)
    n1 = candle_values(df, -1)

    # CLAVE: se analiza exclusivamente N cerrada.
    result = analyze_market(df, confirmation_index=-2)
    signal = result.get("signal")

    logger.info(
        "%s | N cerrada | ts=%s | signal=%s | score=%s | %s",
        pair, n_ts, signal, result.get("score"), result.get("reason")
    )

    if signal not in ("call", "put"):
        return False

    PENDING_ENTRY[pair] = {
        "signal": signal,
        "n_ts": n_ts,
        "n_open": n["open"],
        "n_high": n["high"],
        "n_low": n["low"],
        "n_close": n["close"],
        "n1_ts": n1_ts,
        "n1_open": n1["open"],
        "score": int(result.get("score") or 0),
        "reason": str(result.get("reason", "")),
    }

    logger.info(
        "\n==================================================\n"
        "%s | CAMBIO DE VELA CONFIRMADO\n"
        "N CERRADA:\n"
        "  timestamp = %s\n"
        "  open      = %.10f\n"
        "  high      = %.10f\n"
        "  low       = %.10f\n"
        "  close     = %.10f\n"
        "\nN+1 ABIERTA:\n"
        "  timestamp = %s\n"
        "  open      = %.10f\n"
        "\nSEÑAL: %s | score=%s/10\n"
        "==================================================",
        pair, n_ts, n["open"], n["high"], n["low"], n["close"],
        n1_ts, n1["open"], signal.upper(), result.get("score")
    )

    direction = "CALL 🟢" if signal == "call" else "PUT 🔴"
    telegram_send(
        "📌 SEÑAL CONFIRMADA AL CIERRE\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "VELA N — CERRADA:\n"
        f"Timestamp: {n_ts}\n"
        f"Apertura: {n['open']}\n"
        f"Máximo: {n['high']}\n"
        f"Mínimo: {n['low']}\n"
        f"Cierre: {n['close']}\n\n"
        "VELA N+1 — ABIERTA:\n"
        f"Timestamp: {n1_ts}\n"
        f"Apertura: {n1['open']}\n\n"
        f"Score: {result.get('score')}/10\n"
        "🚫 N nunca se opera.\n"
        "🎯 Entrada N+1, segundo 01–03."
    )
    return True


# ============================================================
# ORDEN DIGITAL
# ============================================================

def buy_digital(pair: str, signal: str) -> Tuple[bool, Optional[Any]]:
    if IQ is None:
        return False, None
    try:
        result = IQ.buy_digital_spot(
            pair, AMOUNT, signal, EXPIRATION
        )
        if isinstance(result, tuple):
            if len(result) >= 2:
                return bool(result[0]), result[1]
            return (bool(result[0]), None) if result else (False, None)
        if result not in (None, False, "error", -1):
            return True, result
        return False, result
    except Exception as exc:
        logger.error("buy_digital %s %s: %s", pair, signal, exc)
        return False, None


# ============================================================
# EJECUTAR N+1
# ============================================================

def try_execute_pending(pair: str) -> bool:
    pending = PENDING_ENTRY.get(pair)
    if pending is None or cooldown_active(pair):
        return False

    df = get_candles(pair)
    if df is None or len(df) < 2:
        return False

    current_ts = candle_timestamp(df, -1)
    if current_ts is None:
        return False

    n1_ts = int(pending["n1_ts"])

    if current_ts < n1_ts:
        return False

    # Si ya pasó a N+2, se perdió la entrada de N+1.
    if current_ts > n1_ts:
        logger.warning(
            "%s | N+1 perdida | esperada=%s | actual=%s",
            pair, n1_ts, current_ts
        )
        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1 esperada: {n1_ts}\n"
            f"Vela actual: {current_ts}\n"
            "No se ejecuta tarde."
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    if not sequential(int(pending["n_ts"]), current_ts):
        return False

    try:
        n1 = candle_values(df, -1)
        live_open = n1["open"]
    except Exception:
        return False

    # Epoch de IQ: permite medir el segundo de N+1 sin depender
    # de la zona horaria de Railway.
    elapsed = time.time() - float(n1_ts)

    if elapsed < ENTRY_MIN_SECOND:
        return False

    if elapsed > ENTRY_MAX_SECOND:
        logger.warning(
            "%s | fuera de ventana | elapsed=%.3fs",
            pair, elapsed
        )
        telegram_send(
            "⏳ ENTRADA CANCELADA\n\n"
            f"Par: {pair}\n"
            f"N+1: {n1_ts}\n"
            f"Tiempo: {elapsed:.3f}s\n"
            "La ventana 01–03 ya terminó."
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    if LAST_TRADE_CANDLE.get(pair) == n1_ts:
        PENDING_ENTRY.pop(pair, None)
        return False

    captured_open = float(pending["n1_open"])
    diff = abs(live_open - captured_open)

    logger.info(
        "%s | N+1 | timestamp=%s | open_capturada=%.10f | "
        "open_actual=%.10f | diff=%.12f | segundo=%.3f",
        pair, n1_ts, captured_open, live_open, diff, elapsed
    )

    signal = pending["signal"]
    direction = "CALL 🟢" if signal == "call" else "PUT 🔴"

    telegram_send(
        "⚡ EJECUTANDO N+1\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n\n"
        "N CERRADA:\n"
        f"Apertura: {pending['n_open']}\n"
        f"Cierre: {pending['n_close']}\n\n"
        "N+1:\n"
        f"Timestamp: {n1_ts}\n"
        f"Apertura IQ: {live_open}\n"
        f"Segundo: {elapsed:.3f}\n\n"
        f"💵 ${AMOUNT} | ⏱ {EXPIRATION} minuto"
    )

    ok, order_id = buy_digital(pair, signal)

    if not ok:
        logger.error(
            "%s | DIGITAL RECHAZADA | signal=%s | N+1=%s | "
            "open=%.10f | elapsed=%.3f | respuesta=%r",
            pair, signal, n1_ts, live_open, elapsed, order_id
        )
        telegram_send(
            "❌ OPERACIÓN DIGITAL RECHAZADA\n\n"
            f"Par: {pair}\n"
            f"Dirección: {signal.upper()}\n"
            f"N+1: {n1_ts}\n"
            f"Apertura: {live_open}\n"
            f"Segundo: {elapsed:.3f}\n"
            f"Respuesta: {order_id!r}"
        )
        PENDING_ENTRY.pop(pair, None)
        return False

    LAST_TRADE_TIME[pair] = time.time()
    LAST_TRADE_CANDLE[pair] = n1_ts
    PENDING_ENTRY.pop(pair, None)

    logger.info(
        "%s | DIGITAL ABIERTA | %s | open=%.10f | "
        "elapsed=%.3f | N+1=%s | ID=%s",
        pair, signal.upper(), live_open, elapsed, n1_ts, order_id
    )
    telegram_send(
        "✅ OPERACIÓN DIGITAL ABIERTA\n\n"
        f"Par: {pair}\n"
        f"Dirección: {signal.upper()}\n"
        f"Entrada detectada: {live_open}\n"
        f"Segundo: {elapsed:.3f}\n"
        f"ID: {order_id}"
    )
    return True


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(pair: str) -> None:
    df = get_candles(pair)
    if df is None or len(df) < 2:
        return

    # -1 = vela viva; -2 = última vela cerrada.
    live_ts = candle_timestamp(df, -1)
    closed_ts = candle_timestamp(df, -2)
    if live_ts is None or closed_ts is None:
        return

    # Primero intentamos ejecutar una señal ya confirmada.
    if pair in PENDING_ENTRY:
        try_execute_pending(pair)

    previous = LAST_CONFIRMED_CANDLE.get(pair)

    # Primera sincronización: NO entrar.
    if previous is None:
        LAST_CONFIRMED_CANDLE[pair] = closed_ts
        logger.info(
            "%s | sincronización inicial | cerrada=%s | viva=%s",
            pair, closed_ts, live_ts
        )
        return

    # La misma N cerrada: no analizar repetidamente.
    if closed_ts == previous:
        return

    if closed_ts < previous:
        logger.warning(
            "%s | timestamp retrocedió | anterior=%s actual=%s",
            pair, previous, closed_ts
        )
        return

    # Si hubo salto de más de una vela, no inventamos señales.
    if not sequential(previous, closed_ts):
        logger.warning(
            "%s | salto de vela | anterior=%s actual=%s | sincronizando",
            pair, previous, closed_ts
        )
        LAST_CONFIRMED_CANDLE[pair] = closed_ts
        return

    n = candle_values(df, -2)
    n1 = candle_values(df, -1)

    logger.info(
        "\n--------------------------------------------------\n"
        "%s | NUEVA VELA CONFIRMADA\n"
        "N CERRADA: ts=%s open=%.10f high=%.10f low=%.10f close=%.10f\n"
        "N+1 VIVA:  ts=%s open=%.10f\n"
        "--------------------------------------------------",
        pair, closed_ts, n["open"], n["high"], n["low"], n["close"],
        live_ts, n1["open"]
    )

    # N ya fue cerrada. La procesamos una sola vez.
    LAST_CONFIRMED_CANDLE[pair] = closed_ts

    # La estrategia SOLO recibe N como confirmación.
    save_pending_entry(pair, df)


# ============================================================
# LOOP
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
    logger.info("BOT DIGITAL OTC - N CERRADA / N+1")
    logger.info("PARES: %s", ", ".join(PAIRS))
    logger.info("TIMEFRAME: 1M")
    logger.info("EXPIRATION: 1M")
    logger.info("AMOUNT: $%s", AMOUNT)
    logger.info(
        "ENTRY WINDOW: %.1f - %.1f s",
        ENTRY_MIN_SECOND, ENTRY_MAX_SECOND
    )
    logger.info("====================================")

    required = {
        "IQ_EMAIL": IQ_EMAIL,
        "IQ_PASSWORD": IQ_PASSWORD,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.error("Faltan variables: %s", ", ".join(missing))
        return

    try:
        connect_iq()
    except Exception as exc:
        logger.exception("No se pudo iniciar IQ Option")
        telegram_send(f"❌ ERROR DE CONEXIÓN\n\n{exc}")
        return

    telegram_send(
        "🤖 BOT LISTO\n\n"
        "DIGITAL OTC\n"
        "EURUSD-OTC | GBPUSD-OTC | EURJPY-OTC\n\n"
        "🔒 N se analiza solo al cierre.\n"
        "🚫 N nunca se opera.\n"
        "➡️ Entrada exclusivamente en N+1.\n"
        "🎯 Segundo 01–03."
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
            telegram_send(f"⚠️ ERROR EN BOT\n\n{exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
