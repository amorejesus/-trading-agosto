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

PAIR = "EURUSD-OTC"
AMOUNT = 100
EXPIRATION = 1  # minutos

# ==============================


def send_telegram(message):
    """Enviar mensaje a Telegram"""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Error Telegram:", e)


def connect_iq():
    """Conectar a IQ Option"""
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


def get_candles(iq, timeframe):
    """Obtener velas por timeframe"""
    try:
        candles = iq.get_candles(PAIR, timeframe, 50, time.time())
        df = pd.DataFrame(candles)
        return df
    except Exception as e:
        print(f"Error obteniendo velas TF {timeframe}:", e)
        return None


def wait_new_candle():
    """Esperar nueva vela M1"""
    print("⏳ Esperando nueva vela...")

    while True:
        if int(time.time()) % 60 == 0:
            return
        time.sleep(0.5)


def trade(iq, signal):
    """Ejecutar operación"""
    direction = signal

    print(f"🚀 Ejecutando {direction.upper()}")
    send_telegram(f"📊 Señal: {direction.upper()} en {PAIR}")

    try:
        status, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram("⏳ Operación abierta")
        else:
            print("❌ Error al abrir operación")
            send_telegram("❌ Error al abrir operación")

    except Exception as e:
        print("Error en trade:", e)
        send_telegram("❌ Error ejecutando trade")


def main():
    """Loop principal"""
    iq = connect_iq()

    while True:
        try:
            wait_new_candle()

            # 🔥 SNIPER M1 + M5
            df_m1 = get_candles(iq, 60)
            df_m5 = get_candles(iq, 300)

            if df_m1 is None or df_m5 is None:
                continue

            # 🔥 estrategia sniper (con control de tendencia)
            signal, trend = analyze_candle(df_m1, df_m5)

            if signal:
                print(f"📈 Cambio de tendencia detectado: {trend}")
                trade(iq, signal)
            else:
                print("⛔ Sin señal sniper")

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
