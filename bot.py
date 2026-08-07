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

# ==============================


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        })
    except Exception as e:
        print("Error Telegram:", e)


def connect_iq():
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error conectando a IQ Option")
        send_telegram("❌ Error conectando a IQ Option")
        exit()

    iq.change_balance("PRACTICE")

    print("✅ Conectado a IQ Option")
    send_telegram("✅ Bot conectado a IQ Option")

    return iq


def get_candles(iq, pair, timeframe):
    try:
        candles = iq.get_candles(pair, timeframe, 50, time.time())
        df = pd.DataFrame(candles)
        return df
    except Exception as e:
        print(f"Error velas {pair} TF {timeframe}:", e)
        return None


def wait_second_58():
    print("⏳ Esperando segundo 58...")
    while True:
        if int(time.time()) % 60 == 58:
            return
        time.sleep(0.2)


def trade(iq, pair, signal):
    print(f"🚀 {pair} → {signal.upper()}")
    send_telegram(f"📊 {pair} → {signal.upper()}")

    try:
        status, _ = iq.buy(AMOUNT, pair, signal, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram(f"✅ Trade abierto en {pair}")
        else:
            print("❌ Error al abrir operación")
            send_telegram(f"❌ Error trade en {pair}")

    except Exception as e:
        print("Error trade:", e)
        send_telegram(f"❌ Error ejecutando trade {pair}")


def main():
    iq = connect_iq()

    while True:
        try:
            wait_second_58()

            for pair in PAIRS:
                try:
                    df_m1 = get_candles(iq, pair, 60)
                    df_m5 = get_candles(iq, pair, 300)

                    if df_m1 is None or df_m5 is None:
                        continue

                    signal = analyze_candle(df_m1, df_m5)

                    if signal:
                        trade(iq, pair, signal)
                    else:
                        print(f"⛔ {pair} sin señal")

                except Exception as e:
                    print(f"Error en {pair}:", e)

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error general: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
