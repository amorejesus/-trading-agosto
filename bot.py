import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle
import os

# =========== CONFIG ===========

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = ["EURUSD-OTC", "GBPUSD-OTC", "EURJPY-OTC"]

AMOUNT = 100
EXPIRATION = 1  # minutos

# Control de tendencia fuerte
last_trend = {pair: None for pair in PAIRS}

# ==============================


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        })
    except:
        pass


def connect_iq():
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error conexión")
        send_telegram("❌ Error conexión IQ Option")
        exit()

    iq.change_balance("PRACTICE")

    print("✅ Conectado")
    send_telegram("✅ Bot conectado")

    return iq


def get_candles(iq, pair, timeframe=60, count=50):
    try:
        candles = iq.get_candles(pair, timeframe, count, time.time())
        df = pd.DataFrame(candles)
        return df
    except Exception as e:
        print(f"Error velas {pair}:", e)
        return None


def wait_sniper_entry():
    """Entrada exacta en segundo 58"""
    while True:
        sec = int(time.time()) % 60
        if sec == 58:
            return
        time.sleep(0.2)


def process_signal(signal):
    """
    Soporta:
    - "call"
    - "put"
    - ("call", score)
    - None
    """
    if signal is None:
        return None, None

    if isinstance(signal, tuple):
        return signal[0], signal[1]

    return signal, None


def trade(iq, pair, direction, score=None):
    try:
        print(f"🚀 {pair} → {direction.upper()} | score: {score}")

        send_telegram(f"📊 {pair} → {direction.upper()} | score: {score}")

        status, _ = iq.buy(AMOUNT, pair, direction, EXPIRATION)

        if status:
            print("✅ Entrada ejecutada")
        else:
            print("❌ Error entrada")

    except Exception as e:
        print(f"Error trade {pair}:", e)


def main():
    iq = connect_iq()

    while True:
        try:
            wait_sniper_entry()

            for pair in PAIRS:

                df_m1 = get_candles(iq, pair, 60, 50)
                df_m5 = get_candles(iq, pair, 300, 50)

                if df_m1 is None or df_m5 is None:
                    continue

                # 🔥 ANALISIS IA
                signal_raw = analyze_candle(df_m1, df_m5)

                direction, score = process_signal(signal_raw)

                # ❌ evitar errores
                if direction not in ["call", "put"]:
                    continue

                # 🎯 CONTROL: solo operar cuando cambia tendencia fuerte
                if last_trend[pair] == direction:
                    continue

                # actualizar tendencia
                last_trend[pair] = direction

                # 🚀 ejecutar
                trade(iq, pair, direction, score)

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
