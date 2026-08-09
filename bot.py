import time
import requests
import pandas as pd
import os
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

AMOUNT = 333
EXPIRATION = 1  # minutos

last_trade_time = 0


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
# CONEXIÓN IQ
# ==============================
def connect_iq():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("Faltan IQ_EMAIL o IQ_PASSWORD")

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


# ==============================
# OBTENER VELAS
# ==============================
def get_candles(iq, pair, timeframe):
    try:
        candles = iq.get_candles(pair, timeframe, 100, time.time())

        if not candles or len(candles) == 0:
            print(f"⚠️ Sin velas {pair} TF={timeframe}")
            return None

        df = pd.DataFrame(candles)

        # normalizar columnas
        df.rename(columns={
            "max": "max",
            "min": "min",
            "open": "open",
            "close": "close"
        }, inplace=True)

        return df

    except Exception as e:
        print(f"❌ Error velas {pair}: {e}")
        return None


# ==============================
# ESPERAR ENTRADA SNIPER
# ==============================
def wait_entry():
    while True:
        sec = int(time.time()) % 60
        if sec >= 58:
            print("🎯 Ventana sniper segundo 58")
            return
        time.sleep(0.2)


# ==============================
# EJECUTAR TRADE
# ==============================
def trade(iq, direction, score):
    global last_trade_time

    print(f"🚀 {PAIR} → {direction.upper()} | Score: {score}")
    send_telegram(f"📊 {PAIR} → {direction.upper()} | Score: {score}")

    try:
        status, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram(f"✅ Trade en {PAIR}")
            last_trade_time = time.time()
        else:
            print("❌ Error al abrir operación")
            send_telegram("❌ Error al abrir operación")

    except Exception as e:
        print(f"❌ Error trade: {e}")


# ==============================
# LOOP PRINCIPAL
# ==============================
def main():
    global last_trade_time

    print("====================================")
    print("🤖 BOT SNIPER M1 + MICRO (5s)")
    print("====================================")

    iq = connect_iq()

    while True:
        try:
            wait_entry()

            # evitar sobreoperar
            if time.time() - last_trade_time < 60:
                print("⏳ Esperando siguiente oportunidad...")
                continue

            print("\n🔎 ANALIZANDO EURUSD-OTC")

            df_m1 = get_candles(iq, PAIR, 60)
            df_5s = get_candles(iq, PAIR, 5)

            if df_m1 is None:
                print("⛔ sin datos M1")
                continue

            if df_5s is None:
                print("⛔ sin datos 5s")
                continue

            print(f"📊 M1={len(df_m1)} | 5s={len(df_5s)}")

            direction, score = analyze_candle(df_m1, df_5s)

            if direction not in ["call", "put"]:
                print("⛔ Sin señal")
                continue

            trade(iq, direction, score)

        except Exception as e:
            print(f"❌ Error general: {e}")
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    main()
