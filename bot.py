import time
import os
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle

# ==============================
# CONFIG
# ==============================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 10
EXPIRATION = 1  # minutos

last_trade_time = 0
last_alert_time = 0

# ==============================
# TELEGRAM
# ==============================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        )
    except:
        pass


# ==============================
# CONEXIÓN IQ OPTION
# ==============================
def connect_iq():
    if not EMAIL:
        raise RuntimeError("❌ Falta IQ_EMAIL en Railway")

    if not PASSWORD:
        raise RuntimeError("❌ Falta IQ_PASSWORD en Railway")

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        raise RuntimeError("❌ Error conectando a IQ Option")

    iq.change_balance("PRACTICE")

    print("✅ Conectado a IQ Option")
    send_telegram("✅ Bot conectado")

    return iq


# ==============================
# OBTENER VELAS
# ==============================
def get_candles(iq, timeframe, count=50):
    try:
        data = iq.get_candles(PAIR, timeframe, count, time.time())
        if not data:
            return None

        df = pd.DataFrame(data)
        return df

    except Exception as e:
        print("Error velas:", e)
        return None


# ==============================
# TIEMPO ACTUAL
# ==============================
def current_second():
    return int(time.time()) % 60


# ==============================
# EJECUTAR TRADE
# ==============================
def execute_trade(iq, direction):
    global last_trade_time

    print(f"🚀 EJECUTANDO {direction.upper()}")
    send_telegram(f"🚀 TRADE → {direction.upper()}")

    try:
        status, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if status:
            print("✅ Trade ejecutado")
            send_telegram("✅ Trade ejecutado")
            last_trade_time = time.time()
        else:
            print("❌ Error trade")
            send_telegram("❌ Error al ejecutar trade")

    except Exception as e:
        print("Error:", e)


# ==============================
# LOOP PRINCIPAL
# ==============================
def main():
    global last_alert_time

    iq = connect_iq()

    print("===================================")
    print("🤖 BOT SNIPER 5s + M1")
    print("===================================")

    while True:
        try:
            sec = current_second()

            df_m1 = get_candles(iq, 60, 50)
            df_5s = get_candles(iq, 5, 50)

            if df_m1 is None or df_5s is None:
                print("⛔ Sin datos")
                time.sleep(1)
                continue

            # ==============================
            # ANALIZAR ESTRATEGIA
            # ==============================
            direction, signal_time = analyze_candle(df_5s, df_m1)

            # ==============================
            # ALERTA TEMPRANA (0–30s)
            # ==============================
            if direction and sec < 30:
                if time.time() - last_alert_time > 60:
                    print(f"📡 ALERTA {direction}")
                    send_telegram(f"📡 ALERTA → {direction.upper()}")
                    last_alert_time = time.time()

            # ==============================
            # EJECUCIÓN EN CIERRE
            # ==============================
            if direction and sec >= 58:

                # evitar sobreoperar
                if time.time() - last_trade_time < 120:
                    continue

                # 🔥 DIRECCIÓN REAL M1 (NO INVERTIDO)
                last_candle = df_m1.iloc[-2]

                if last_candle["close"] > last_candle["open"]:
                    real_direction = "call"
                else:
                    real_direction = "put"

                print(f"🎯 CONFIRMACIÓN FINAL: {real_direction}")

                execute_trade(iq, real_direction)

            time.sleep(0.5)

        except Exception as e:
            print("❌ ERROR:", e)
            send_telegram(f"❌ ERROR: {e}")
            time.sleep(5)


# ==============================
# START
# ==============================
if __name__ == "__main__":
    main()
