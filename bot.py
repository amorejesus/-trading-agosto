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
AMOUNT = 333
EXPIRATION = 1  # minutos

last_trade_time = 0
MIN_TRADE_INTERVAL = 60  # 1 trade por minuto

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


def get_candles(iq, pair, timeframe, count):
    try:
        candles = iq.get_candles(pair, timeframe, count, time.time())
        df = pd.DataFrame(candles)

        if df.empty:
            return None

        return df.sort_values("from")

    except Exception as e:
        print(f"Error velas {pair} TF {timeframe}: {e}")
        return None


# 🔥 esperar segundo 58
def wait_sniper():
    while True:
        sec = int(time.time()) % 60
        if sec >= 58:
            return
        time.sleep(0.2)


# 🔍 obtener primeras 6 velas de 5s del minuto actual
def get_first_6_candles(df_5s):
    if df_5s is None or len(df_5s) < 6:
        return None

    # tomar velas del mismo minuto actual
    current_minute = int(time.time() // 60)

    df_5s["minute"] = df_5s["from"] // 60
    df_minute = df_5s[df_5s["minute"] == current_minute]

    if len(df_minute) < 6:
        return None

    return df_minute.head(6)


# 🚀 ejecutar trade
def trade(iq, direction):
    print(f"🚀 {PAIR} → {direction.upper()}")
    send_telegram(f"📊 {PAIR} → {direction.upper()}")

    try:
        status, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram("✅ Trade ejecutado")
        else:
            print("❌ Error al abrir operación")
            send_telegram("❌ Error al abrir trade")

    except Exception as e:
        print("Error trade:", e)


# ==============================
# 🔁 LOOP PRINCIPAL
# ==============================
def main():
    global last_trade_time

    print("====================================")
    print("🤖 BOT SNIPER 5s + M1")
    print("====================================")

    iq = connect_iq()

    while True:
        try:
            print("⏳ Esperando ventana sniper...")
            wait_sniper()

            # ⛔ evitar sobreoperar
            if time.time() - last_trade_time < MIN_TRADE_INTERVAL:
                continue

            print(f"🔎 ANALIZANDO {PAIR}")

            # 📊 obtener velas
            df_m1 = get_candles(iq, PAIR, 60, 10)
            df_5s = get_candles(iq, PAIR, 5, 20)

            if df_m1 is None or df_5s is None:
                print("⛔ Sin datos")
                continue

            # 🔥 obtener SOLO primeras 6 velas del minuto
            df_5s_first = get_first_6_candles(df_5s)

            if df_5s_first is None:
                print("⛔ No hay patrón 5s completo")
                continue

            # 🧠 señal
            signal = analyze_candle(df_m1, df_5s_first)

            if signal not in ["call", "put"]:
                print("⛔ Sin señal")
                continue

            # 🚀 ejecutar
            trade(iq, signal)
            last_trade_time = time.time()

        except Exception as e:
            print("❌ Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
