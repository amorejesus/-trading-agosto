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

# Control de operaciones por tendencia
last_trend = {pair: None for pair in PAIRS}

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


# ==============================
# 📊 DATOS
# ==============================

def get_candles(iq, pair, timeframe, count):
    try:
        candles = iq.get_candles(pair, timeframe, count, time.time())

        if not candles:
            return None

        df = pd.DataFrame(candles)

        # Normalizar nombres
        df.rename(columns={
            "max": "max",
            "min": "min",
            "open": "open",
            "close": "close"
        }, inplace=True)

        return df

    except Exception as e:
        print(f"Error velas {pair}:", e)
        return None


# ==============================
# ⏱️ SNIPER (SEGUNDO 58)
# ==============================

def wait_sniper_entry():
    print("⏳ Esperando segundo 58...")

    while True:
        sec = int(time.time()) % 60
        if sec >= 58:
            return
        time.sleep(0.2)


# ==============================
# 🚀 TRADE
# ==============================

def trade(iq, pair, direction):
    try:
        print(f"🚀 {pair} → {direction.upper()}")
        send_telegram(f"📊 {pair} → {direction.upper()}")

        status, _ = iq.buy(AMOUNT, pair, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram(f"✅ Trade ejecutado en {pair}")
        else:
            print("❌ Error al abrir operación")
            send_telegram(f"❌ Error trade {pair}")

    except Exception as e:
        print(f"Error trade {pair}:", e)
        send_telegram(f"❌ Error trade {pair}: {e}")


# ==============================
# 🔁 LOOP PRINCIPAL
# ==============================

def main():
    iq = connect_iq()

    while True:
        try:
            wait_sniper_entry()

            for pair in PAIRS:
                try:
                    # Obtener datos
                    df_m1 = get_candles(iq, pair, 60, 50)
                    df_m5 = get_candles(iq, pair, 300, 50)

                    if df_m1 is None or df_m5 is None:
                        print(f"⛔ Sin datos {pair}")
                        continue

                    # Señal
                    signal = analyze_candle(df_m1, df_m5)

                    if signal is None:
                        print(f"⛔ Sin señal en {pair}")
                        continue

                    # =========================
                    # CONTROL DE TENDENCIA
                    # =========================
                    if last_trend[pair] == signal:
                        print(f"⚠️ Ya operado en esta tendencia {pair}")
                        continue

                    # Ejecutar trade
                    trade(iq, pair, signal)

                    # Guardar tendencia
                    last_trend[pair] = signal

                except Exception as e:
                    print(f"Error en {pair}:", e)

            time.sleep(1)

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error general: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
