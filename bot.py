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

PAIRS = [
    "EURUSD-OTC",
    "GBPUSD-OTC",
    "EURJPY-OTC"
]

AMOUNT = 100
EXPIRATION = 1  # minutos

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


# 🧠 IA aprendizaje
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

    print(f"🧠 IA: {memory}")


# 🚀 Ejecutar trade
def trade(iq, pair, signal, score):
    print(f"🚀 {pair} | {signal.upper()} | Score: {score}")
    send_telegram(f"📊 {pair} | {signal.upper()} | Score: {score}")

    try:
        status, trade_id = iq.buy(AMOUNT, pair, signal, EXPIRATION)

        if not status:
            print("❌ No se pudo abrir operación")
            return

        print("⏳ Esperando resultado...")
        time.sleep(EXPIRATION * 60)

        result = iq.check_win_v4(trade_id)
        win = result > 0

        if win:
            print("✅ WIN")
            send_telegram(f"✅ WIN {pair}")
        else:
            print("❌ LOSS")
            send_telegram(f"❌ LOSS {pair}")

        update_ai(win)

    except Exception as e:
        print("Error trade:", e)


# 🔍 Buscar mejor oportunidad
def find_best_trade(iq):
    best_pair = None
    best_signal = None
    best_score = 0

    for pair in PAIRS:
        df_m1 = get_candles(iq, pair, 60)
        df_m5 = get_candles(iq, pair, 300)

        if df_m1 is None or df_m5 is None:
            continue

        signal, trend, score = analyze_candle(df_m1, df_m5)

        # SOLO imprime si hay señal (evita saturar Railway)
        if signal:
            print(f"{pair} → {signal} | score: {score}")

        if signal and score > best_score:
            best_pair = pair
            best_signal = signal
            best_score = score

    if best_pair:
        return best_pair, best_signal, best_score

    return None


# 🔁 Loop principal
def main():
    iq = connect_iq()

    while True:
        try:
            wait_entry()

            best = find_best_trade(iq)

            if best:
                pair, signal, score = best
                trade(iq, pair, signal, score)
            else:
                print("⛔ Sin oportunidades")

        except Exception as e:
            print("Error general:", e)
            send_telegram(f"❌ Error: {e}")

        time.sleep(1)


if __name__ == "__main__":
    main()
