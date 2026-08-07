import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle, load_memory, save_memory
import os

# =========== CONFIG ===========

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 150
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


def get_candles(iq, timeframe):
    try:
        candles = iq.get_candles(PAIR, timeframe, 50, time.time())
        return pd.DataFrame(candles)
    except Exception as e:
        print(f"Error velas TF {timeframe}:", e)
        return None


# ==============================
# 🎯 ESPERA SNIPER (SEGUNDO 58)
# ==============================
def wait_entry():
    print("⏳ Esperando segundo 58...")

    while True:
        sec = int(time.time()) % 60
        if sec >= 58:
            return
        time.sleep(0.2)


# ==============================
# 📊 OPERACIÓN + RESULTADO
# ==============================
def trade(iq, signal, score):
    direction = signal

    print(f"🚀 {direction.upper()} | Score: {score}")
    send_telegram(f"📊 {direction.upper()} | Score: {score}")

    try:
        status, trade_id = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if not status:
            print("❌ Error al abrir operación")
            return

        print("⏳ Esperando resultado...")

        time.sleep(EXPIRATION * 60)

        result = iq.check_win_v4(trade_id)

        win = result > 0

        if win:
            print("✅ GANADA")
            send_telegram("✅ WIN")
        else:
            print("❌ PERDIDA")
            send_telegram("❌ LOSS")

        update_ai(win)

    except Exception as e:
        print("Error en trade:", e)


# ==============================
# 🧠 IA APRENDIZAJE
# ==============================
def update_ai(win):
    memory = load_memory()

    if win:
        memory["wins"] += 1
        memory["confidence"] += 0.02
    else:
        memory["losses"] += 1
        memory["confidence"] -= 0.02

    memory["confidence"] = max(0.1, min(0.9, memory["confidence"]))

    save_memory(memory)

    print(f"🧠 IA updated: {memory}")


# ==============================
# 🔁 LOOP PRINCIPAL
# ==============================
def main():
    iq = connect_iq()

    while True:
        try:
            wait_entry()

            df_m1 = get_candles(iq, 60)
            df_m5 = get_candles(iq, 300)

            if df_m1 is None or df_m5 is None:
                continue

            signal, trend, score = analyze_candle(df_m1, df_m5)

            if signal:
                print(f"📈 Cambio detectado: {trend}")
                trade(iq, signal, score)
            else:
                print("⛔ Sin señal")

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
