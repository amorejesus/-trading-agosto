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

AMOUNT = 3333
EXPIRATION = 1  # minutos

# Control de tiempo por par (evita sobreoperar)
last_trade_time = {pair: 0 for pair in PAIRS}

# ==============================


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )
    except:
        pass


def connect_iq():
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error conexión IQ Option")
        send_telegram("❌ Error conexión IQ Option")
        exit()

    iq.change_balance("PRACTICE")

    print("✅ Conectado a IQ Option")
    send_telegram("✅ Bot conectado")

    return iq


def get_candles(iq, pair, timeframe):
    try:
        candles = iq.get_candles(pair, timeframe, 50, time.time())
        return pd.DataFrame(candles)
    except Exception as e:
        print(f"Error velas {pair} TF {timeframe}: {e}")
        return None


# 🎯 Entrada sniper (segundo 58)
def wait_entry():
    while True:
        if int(time.time()) % 60 >= 58:
            return
        time.sleep(0.2)


# 🧠 Procesar señal (soporta tuple)
def process_signal(signal):
    if signal is None:
        return None, None

    if isinstance(signal, tuple):
        return signal[0], signal[1]

    return signal, None


# 🚀 Ejecutar trade
def trade(iq, pair, direction, score):
    print(f"🚀 {pair} → {direction.upper()} | Score: {score}")
    send_telegram(f"📊 {pair} → {direction.upper()} | Score: {score}")

    try:
        status, _ = iq.buy(AMOUNT, pair, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram(f"✅ Trade en {pair}")
        else:
            print("❌ Error al abrir operación")
            send_telegram(f"❌ Error trade {pair}")

    except Exception as e:
        print(f"Error trade {pair}:", e)


# 🔁 LOOP PRINCIPAL
def main():
    iq = connect_iq()

    while True:
        try:
            wait_entry()

            for pair in PAIRS:

                # ⏱️ evitar operar demasiado seguido
                if time.time() - last_trade_time[pair] < 120:
                    continue

                df_m1 = get_candles(iq, pair, 60)
                df_m5 = get_candles(iq, pair, 300)

                if df_m1 is None or df_m5 is None:
                    continue

                signal_raw = analyze_candle(df_m1, df_m5)

                direction, score = process_signal(signal_raw)

                # ❌ validar señal
                if direction not in ["call", "put"]:
                    continue

                # 🚀 ejecutar trade
                trade(iq, pair, direction, score)

                # guardar tiempo de última operación
                last_trade_time[pair] = time.time()

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
