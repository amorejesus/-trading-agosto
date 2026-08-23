from __future__ import annotations

import os
import time
import requests
import pandas as pd
from datetime import datetime

from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_live_candle


# ============================================================
# CONFIG
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 10
EXPIRATION = 1

TIMEFRAME = 5   # 5s candles
COUNT = 12      # EXACTAMENTE 12 velas


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        })
    except Exception as e:
        print("Telegram error:", e)


# ============================================================
# IQ OPTION CONNECTION
# ============================================================

def connect_iq():
    if not IQ_EMAIL or not IQ_PASSWORD:
        raise RuntimeError("Faltan IQ_EMAIL o IQ_PASSWORD")

    iq = IQ_Option(IQ_EMAIL, IQ_PASSWORD)
    iq.connect()

    if not iq.check_connect():
        raise RuntimeError("No se pudo conectar a IQ Option")

    iq.change_balance("PRACTICE")
    print("✅ Conectado a IQ Option")
    return iq


# ============================================================
# CANDLES
# ============================================================

def get_candles(iq, pair, timeframe, count):
    try:
        candles = iq.get_candles(pair, timeframe, count, time.time())
        candles = sorted(candles, key=lambda x: x["from"])
        return candles
    except Exception as e:
        print("Error candles:", e)
        return []


# ============================================================
# CONVERSIÓN A M1 + 5S DATA
# ============================================================

def build_inputs(candles_5s):
    if not candles_5s or len(candles_5s) != COUNT:
        return None, None

    df = pd.DataFrame(candles_5s)

    if "from" not in df.columns:
        return None, None

    df = df.sort_values("from")

    first = df.iloc[0]
    last = df.iloc[-1]

    try:
        minute_start = int(first["from"] // 60) * 60
    except:
        return None, None

    candle_1m = {
        "from": minute_start,
        "open": first["open"],
        "close": last["close"],
        "high": df["max"].max() if "max" in df.columns else max(df["open"].max(), df["close"].max()),
        "low": df["min"].min() if "min" in df.columns else min(df["open"].min(), df["close"].min()),
    }

    return candle_1m, df


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def run_bot():
    iq = connect_iq()

    print("🚀 BOT INICIADO")

    while True:
        try:
            candles = get_candles(iq, PAIR, TIMEFRAME, COUNT)

            candle_1m, micro = build_inputs(candles)

            if candle_1m is None or micro is None:
                time.sleep(1)
                continue

            signal = analyze_live_candle(candle_1m, micro)

            if signal:
                msg = f"📊 SIGNAL: {signal.upper()} | {PAIR} | {datetime.now()}"
                print(msg)
                send_telegram(msg)

                # evita spam
                time.sleep(10)
            else:
                print("⏳ Sin señal")

            time.sleep(1)

        except Exception as e:
            print("❌ ERROR LOOP:", e)
            time.sleep(5)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    run_bot()
