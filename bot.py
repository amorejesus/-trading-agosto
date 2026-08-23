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
# TEMPORALIDAD
# ============================================================

TIMEFRAME = 60
CANDLE_COUNT = 62


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 116
EXPIRATION = 1

POLL_INTERVAL = 0.05
MAX_ENTRY_DELAY = 5


# ============================================================
# MERCADOS
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
            timeout=TELEGRAM_HTTP_TIMEOUT,
        )
        return r.status_code == 200
    except Exception as exc:
        logger.warning("Telegram error: %s", exc)
        return False


# ============================================================
# TELEGRAM WORKER
# ============================================================

def telegram_worker() -> None:
    global LAST_UPDATE_ID, BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            params: Dict[str, Any] = {"timeout": 0}

            if LAST_UPDATE_ID is not None:
                params["offset"] = LAST_UPDATE_ID + 1

            r = requests.get(url, params=params, timeout=TELEGRAM_HTTP_TIMEOUT)
            if r.status_code != 200:
                time.sleep(TELEGRAM_POLL_INTERVAL)
                continue

            data = r.json()
            if not data.get("ok"):
                continue

            for update in data.get("result", []):
                LAST_UPDATE_ID = update.get("update_id")

                msg = update.get("message", {})
                text = str(msg.get("text", "")).strip().lower()
                chat_id = str(msg.get("chat", {}).get("id", ""))

                if chat_id != str(TELEGRAM_CHAT_ID):
                    continue

                if text == "/start":
                    BOT_RUNNING = True
                    telegram_send("🟢 BOT ACTIVADO")

                elif text == "/stop":
                    BOT_RUNNING = False
                    telegram_send("🔴 BOT DETENIDO")

                elif text == "/status":
                    telegram_send(
                        f"Estado: {'ACTIVO' if BOT_RUNNING else 'DETENIDO'}\n"
                        f"Mercados: {len(AVAILABLE_OTC_PAIRS)}\n"
                        f"Score min: {MIN_MARKET_SCORE}"
                    )

        except Exception as exc:
            logger.warning("Telegram worker error: %s", exc)

        time.sleep(TELEGRAM_POLL_INTERVAL)


# ============================================================
# IQ CONNECTION
# ============================================================

def connect_iq() -> bool:
    global IQ

    if not IQ_EMAIL or not IQ_PASSWORD:
        raise ValueError("Faltan credenciales")

    IQ = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
    ok, reason = IQ.connect()

    if not ok:
        raise ConnectionError(reason)

    logger.info("IQ conectado")
    return True


def ensure_connection() -> bool:
    global IQ

    try:
        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        return connect_iq()

    except Exception as exc:
        logger.error("Conexion error: %s", exc)
        return False


# ============================================================
# STREAMS Y DATA
# ============================================================

def ensure_pair_stream(pair: str) -> bool:
    if IQ is None:
        return False

    if STREAMS_STARTED_FOR.get(pair):
        return True

    try:
        IQ.start_candles_stream(pair, TIMEFRAME, CANDLE_COUNT)
        STREAMS_STARTED_FOR[pair] = True
        return True
    except Exception:
        return False


def realtime_dataframe(pair: str) -> Optional[pd.DataFrame]:
    if IQ is None:
        return None

    candles = IQ.get_realtime_candles(pair, TIMEFRAME)
    if not candles:
        return None

    rows = []

    for ts, c in candles.items():
        try:
            rows.append({
                "from": int(float(ts)),
                "open": float(c["open"]),
                "close": float(c["close"]),
                "high": float(c.get("max", c.get("high"))),
                "low": float(c.get("min", c.get("low"))),
            })
        except Exception:
            continue

    df = pd.DataFrame(rows)
    df.sort_values("from", inplace=True)
    df.drop_duplicates(subset=["from"], keep="last", inplace=True)

    return df.tail(CANDLE_COUNT)


# ============================================================
# LIVE + CIERRE
# ============================================================

def get_closed_candle(df: pd.DataFrame, ts: int):
    current_minute = (ts // TIMEFRAME) * TIMEFRAME
    valid = df[df["from"] < current_minute]
    if len(valid) == 0:
        return None
    return valid.iloc[-1]


def analyze_all_markets(server_ts: int):
    results = []

    for pair in AVAILABLE_OTC_PAIRS:
        if not BOT_RUNNING:
            break

        if not ensure_pair_stream(pair):
            continue

        df = realtime_dataframe(pair)
        if df is None:
            continue

        closed = get_closed_candle(df, server_ts)
        if closed is None:
            continue

        history = df[df["from"] <= closed["from"]]
        res = analyze_market(closed, previous_m1=history)

        res["pair"] = pair
        results.append(res)

    return results


# ============================================================
# SELECCIÓN
# ============================================================

def select_best_market(results):
    valid = [
        r for r in results
        if r.get("valid")
        and r.get("signal") in ("call", "put")
        and r.get("score", 0) >= MIN_MARKET_SCORE
    ]

    if not valid:
        return None

    return sorted(valid, key=lambda x: x["score"], reverse=True)[0]


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def process_market_cycle():
    server_ts = int(time.time())

    results = analyze_all_markets(server_ts)
    if not results:
        return

    best = select_best_market(results)

    if not best:
        return

    telegram_send(
        f"🏆 MEJOR MERCADO\n"
        f"{best['pair']} | {best['signal']} | {best['score']}"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    global BOT_RUNNING

    connect_iq()

    threading.Thread(target=telegram_worker, daemon=True).start()

    telegram_send("🤖 BOT LISTO")

    while True:
        if not BOT_RUNNING:
            time.sleep(0.2)
            continue

        if not ensure_connection():
            time.sleep(1)
            continue

        process_market_cycle()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
