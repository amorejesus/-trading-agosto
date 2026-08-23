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


TIMEFRAME = 60
CANDLE_COUNT = 62

AMOUNT = 116
EXPIRATION = 1

POLL_INTERVAL = 0.05
MAX_ENTRY_DELAY = 5

MIN_MARKET_SCORE = 82
TOP_MARKETS_TO_LOG = 5

ASSET_REFRESH_INTERVAL = 60

TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 3.0


# ============================================================
# ESTADO GLOBAL
# ============================================================

BOT_RUNNING = False
IQ: Optional[IQ_Option] = None

PENDING_ENTRY: Optional[Dict[str, Any]] = None
AVAILABLE_OTC_PAIRS: List[str] = []

LAST_PROCESSED_MINUTE: Optional[int] = None
LAST_TRADE_CANDLE: Optional[int] = None

STREAMS_STARTED_FOR: Dict[str, bool] = {}


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

def telegram_send(msg: str):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(
            url,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
            timeout=TELEGRAM_HTTP_TIMEOUT,
        )
        return True
    except Exception:
        return False


# ============================================================
# CONEXIÓN IQ
# ============================================================

def connect_iq():

    global IQ

    IQ = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
    ok, reason = IQ.connect()

    if not ok:
        raise Exception(f"No conecta: {reason}")

    logger.info("IQ conectado")


def ensure_connection():

    global IQ

    try:
        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        IQ.connect()
        return True

    except Exception:
        return False


# ============================================================
# DATA REALTIME
# ============================================================

def realtime_dataframe(pair: str):

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
        df.drop_duplicates("from", inplace=True)

        return df.tail(CANDLE_COUNT)

    except Exception:
        return None


# ============================================================
# STREAM
# ============================================================

def ensure_pair_stream(pair: str):

    if STREAMS_STARTED_FOR.get(pair):
        return True

    try:
        IQ.start_candles_stream(pair, TIMEFRAME, CANDLE_COUNT)
        STREAMS_STARTED_FOR[pair] = True
        return True
    except:
        return False


# ============================================================
# CIERRE DE VELA
# ============================================================

def get_closed_candle(df, server_ts):

    current_minute = (server_ts // TIMEFRAME) * TIMEFRAME
    closed = df[df["from"] < current_minute]

    if len(closed) == 0:
        return None

    return closed.iloc[-1]


# ============================================================
# ANALIZAR PAR
# ============================================================

def analyze_pair(pair, df, candle):

    history = df[df["from"] <= candle["from"]]

    result = analyze_market(
        candle,
        previous_m1=history
    )

    result["pair"] = pair
    result["minute_timestamp"] = candle["from"]

    return result


# ============================================================
# ANALIZAR TODOS
# ============================================================

def analyze_all_markets(server_ts):

    results = []

    for pair in AVAILABLE_OTC_PAIRS:

        if not BOT_RUNNING:
            break

        try:

            ensure_pair_stream(pair)

            df = realtime_dataframe(pair)
            if df is None or len(df) < 10:
                continue

            closed = get_closed_candle(df, server_ts)
            if closed is None:
                continue

            res = analyze_pair(pair, df, closed)

            results.append(res)

        except Exception:
            continue

    return results


# ============================================================
# SELECCIÓN
# ============================================================

def select_best_market(results):

    valid = [
        r for r in results
        if r.get("valid") and r.get("score", 0) >= MIN_MARKET_SCORE
    ]

    if not valid:
        return None

    return sorted(valid, key=lambda x: x["score"], reverse=True)[0]


# ============================================================
# PENDING ENTRY
# ============================================================

def create_pending_entry(result):

    global PENDING_ENTRY

    pair = result["pair"]
    signal = result["signal"]
    minute_ts = result["minute_timestamp"]

    PENDING_ENTRY = {
        "pair": pair,
        "signal": signal,
        "minute_timestamp": minute_ts,
        "next_timestamp": minute_ts + TIMEFRAME,
        "score": result["score"],
        "created_at": time.time(),
        "entry_notified": False,
    }

    telegram_send(
        f"🏆 MEJOR MERCADO\n{pair}\n{signal}\nScore {result['score']}\nN+1 activo"
    )


# ============================================================
# EJECUCIÓN
# ============================================================

def execute_pending_entry():

    global PENDING_ENTRY
    global LAST_TRADE_CANDLE

    if not PENDING_ENTRY:
        return False

    ts = int(time.time())

    if ts < PENDING_ENTRY["next_timestamp"]:
        return False

    if LAST_TRADE_CANDLE == PENDING_ENTRY["next_timestamp"]:
        PENDING_ENTRY = None
        return True

    pair = PENDING_ENTRY["pair"]
    signal = PENDING_ENTRY["signal"]

    try:
        ok, order_id = IQ.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION
        )

        if ok:

            LAST_TRADE_CANDLE = PENDING_ENTRY["next_timestamp"]

            telegram_send(
                f"✅ ENTRADA EJECUTADA\n{pair}\n{signal}\nID {order_id}"
            )

            PENDING_ENTRY = None

            return True

    except Exception:
        pass

    return False


# ============================================================
# CICLO
# ============================================================

def process_cycle():

    server_ts = int(time.time())

    execute_pending_entry()

    results = analyze_all_markets(server_ts)

    if not results:
        return

    best = select_best_market(results)

    if best and not PENDING_ENTRY:
        create_pending_entry(best)


# ============================================================
# MAIN
# ============================================================

def main():

    global BOT_RUNNING

    connect_iq()

    BOT_RUNNING = True

    telegram_send("🤖 BOT SNIPER ACTIVO")

    while True:

        if not BOT_RUNNING:
            time.sleep(0.2)
            continue

        if not ensure_connection():
            time.sleep(1)
            continue

        process_cycle()

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
