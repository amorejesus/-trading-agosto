from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option
from strategy import (
    analyze_live_candle,
    analyze_market,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TEMPORALIDADES
# ============================================================

TIMEFRAME = 60
CANDLE_COUNT = 62


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 1160
EXPIRATION = 1


# ============================================================
# EJECUCIÓN
# ============================================================

POLL_INTERVAL = 0.05
MAX_ENTRY_DELAY = 5  # N+1: segundos 00-05


# ============================================================
# SELECCIÓN DEL MERCADO
# ============================================================

MIN_MARKET_SCORE = 82
TOP_MARKETS_TO_LOG = 5
ASSET_REFRESH_INTERVAL = 60


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 3.0


# ============================================================
# ESTADO GLOBAL
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None

AVAILABLE_OTC_PAIRS: List[str] = []

LAST_ASSET_REFRESH = 0.0

STREAMS_STARTED_FOR: Dict[str, bool] = {}

LAST_PROCESSED_MINUTE: Optional[int] = None

PENDING_ENTRY: Optional[Dict[str, Any]] = None

LAST_TRADE_CANDLE: Optional[int] = None

LIVE_M1_STATE: Dict[str, Dict[str, Any]] = {}

# ===================== SNIPER =====================
SNIPER_STATE: Dict[str, Dict[str, Any]] = {}


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
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
        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=TELEGRAM_HTTP_TIMEOUT,
        )
        return response.status_code == 200
    except Exception as exc:
        logger.warning("Telegram no disponible: %s", exc)
        return False


# ============================================================
# TELEGRAM WORKER
# ============================================================

def telegram_worker() -> None:
    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    logger.info("Telegram worker iniciado.")

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params: Dict[str, Any] = {"timeout": 0}

            if LAST_UPDATE_ID is not None:
                params["offset"] = LAST_UPDATE_ID + 1

            response = requests.get(
                url,
                params=params,
                timeout=TELEGRAM_HTTP_TIMEOUT,
            )

            if response.status_code != 200:
                time.sleep(TELEGRAM_POLL_INTERVAL)
                continue

            data = response.json()
            if not data.get("ok"):
                time.sleep(TELEGRAM_POLL_INTERVAL)
                continue

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
                        "MODO MULTI-OTC + SNIPER\n"
                        "Pre-señal y confirmación en vivo.\n"
                        "Entrada solo en N+1."
                    )

                elif text == "/stop":
                    BOT_RUNNING = False
                    telegram_send("🔴 BOT DETENIDO")

                elif text == "/status":
                    status = "🟢 ACTIVO" if BOT_RUNNING else "🔴 DETENIDO"
                    telegram_send(
                        f"Estado: {status}\n"
                        f"OTC: {len(AVAILABLE_OTC_PAIRS)}\n"
                        f"Importe: ${AMOUNT}"
                    )

        except Exception as exc:
            logger.warning("Telegram worker: %s", exc)

        time.sleep(TELEGRAM_POLL_INTERVAL)


# ============================================================
# TIMESTAMP
# ============================================================

def get_server_timestamp() -> Optional[int]:
    if IQ is None:
        return None
    try:
        return int(float(IQ.get_server_timestamp()))
    except Exception:
        return None


# ============================================================
# CONEXIÓN
# ============================================================

def connect_iq() -> bool:
    global IQ

    IQ = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
    connected, _ = IQ.connect()

    if not connected:
        raise ConnectionError("No se pudo conectar")

    logger.info("IQ conectado.")
    return True


def ensure_connection() -> bool:
    if IQ is None:
        return connect_iq()
    if IQ.check_connect():
        return True
    return connect_iq()


# ============================================================
# STREAM
# ============================================================

def ensure_pair_stream(pair: str) -> bool:
    if STREAMS_STARTED_FOR.get(pair):
        return True
    try:
        IQ.start_candles_stream(pair, TIMEFRAME, CANDLE_COUNT)
        STREAMS_STARTED_FOR[pair] = True
        return True
    except:
        return False


# ============================================================
# DATAFRAME
# ============================================================

def realtime_dataframe(pair: str) -> Optional[pd.DataFrame]:
    try:
        candles = IQ.get_realtime_candles(pair, TIMEFRAME)
        rows = []
        for ts, c in candles.items():
            rows.append({
                "from": int(float(ts)),
                "open": float(c["open"]),
                "close": float(c["close"]),
                "high": float(c["max"]),
                "low": float(c["min"]),
            })
        df = pd.DataFrame(rows)
        df.sort_values("from", inplace=True)
        return df.tail(CANDLE_COUNT)
    except:
        return None


# ============================================================
# 🔥 MONITOR SNIPER
# ============================================================

def monitor_live_market(pair, df, server_ts):

    live = df.iloc[-1]
    live_ts = int(live["from"])
    current_minute = (server_ts // 60) * 60

    if live_ts != current_minute:
        return None

    live_analysis = analyze_live_candle(live)
    sec = int(server_ts - live_ts)

    # INIT
    if pair not in SNIPER_STATE:
        SNIPER_STATE[pair] = {
            "pre": False,
            "confirm": False,
            "direction": None,
            "timestamp": live_ts,
        }

    sniper = SNIPER_STATE[pair]

    if sniper["timestamp"] != live_ts:
        sniper.update({
            "pre": False,
            "confirm": False,
            "direction": None,
            "timestamp": live_ts,
        })

    # ================= PRE-SEÑAL =================
    if 5 <= sec <= 25 and not sniper["pre"]:
        if live_analysis["state"] == "LIVE_CONTINUITY":
            sniper["pre"] = True
            sniper["direction"] = live_analysis["direction"]
            logger.info("%s | PRE-SEÑAL %s", pair, sniper["direction"])

    # ================= CONFIRMACIÓN =================
    if 25 <= sec <= 45 and sniper["pre"] and not sniper["confirm"]:
        if live_analysis["score"] >= 10:
            sniper["confirm"] = True
            logger.info("%s | CONFIRMADO %s", pair, sniper["direction"])

    return live_analysis


# ============================================================
# SELECCIÓN CON SNIPER
# ============================================================

def select_best_market(results):

    valid = []

    for r in results:
        if not (r.get("valid") and r.get("score", 0) >= MIN_MARKET_SCORE):
            continue

        sniper = SNIPER_STATE.get(r.get("pair"), {})

        if not sniper.get("confirm"):
            continue

        valid.append(r)

    if not valid:
        return None

    return sorted(valid, key=lambda x: x["score"], reverse=True)[0]


# ============================================================
# MAIN LOOP (resumido)
# ============================================================

def main():

    connect_iq()

    threading.Thread(
        target=telegram_worker,
        daemon=True
    ).start()

    while True:

        if not BOT_RUNNING:
            time.sleep(0.2)
            continue

        if not ensure_connection():
            continue

        server_ts = get_server_timestamp()
        if not server_ts:
            continue

        for pair in AVAILABLE_OTC_PAIRS:

            ensure_pair_stream(pair)

            df = realtime_dataframe(pair)
            if df is None or len(df) < 10:
                continue

            monitor_live_market(pair, df, server_ts)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
