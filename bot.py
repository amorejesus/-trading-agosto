import time
import pandas as pd
import logging
from iqoptionapi.stable_api import IQ_Option
import requests

# ================= CONFIG =================
EMAIL = "TU_EMAIL"
PASSWORD = "TU_PASSWORD"

PAIR = "EURUSD-OTC"
AMOUNT = 5580
EXPIRATION = 1

TELEGRAM_TOKEN = "TU_TOKEN"
CHAT_ID = "TU_CHAT_ID"

# =========================================

logging.getLogger().setLevel(logging.CRITICAL)

bot_active = False
last_candle_time = None
last_signal_time = 0
trade_open = False

# ================= TELEGRAM =================

def send_telegram(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": CHAT_ID, "text": msg}
        )
    except:
        pass

def check_commands():
    global bot_active

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        data = requests.get(url).json()

        if not data["result"]:
            return

        last_msg = data["result"][-1]["message"]["text"]

        if last_msg == "/start":
            bot_active = True
            send_telegram("🤖 BOT ACTIVADO")

        elif last_msg == "/stop":
            bot_active = False
            send_telegram("🛑 BOT DETENIDO")

    except:
        pass

# ================= CONEXIÓN =================

def connect():
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error de conexión")
        send_telegram("❌ Error de conexión")
        return None

    print("✅ Conectado")
    send_telegram("✅ Bot conectado")
    iq.change_balance("PRACTICE")
    return iq

# ================= DATOS =================

def get_candles(iq):
    candles = iq.get_candles(PAIR, 60, 50, time.time())

    df = pd.DataFrame(candles)

    df.rename(columns={
        "min": "low",
        "max": "high"
    }, inplace=True)

    return df

# ================= ESTRATEGIA =================

def get_signal(df):
    # Tendencia bajista simple
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Continuidad bajista
    if prev["close"] > prev["open"] and last["close"] < last["open"]:
        return "put"

    # Continuidad alcista
    if prev["close"] < prev["open"] and last["close"] > last["open"]:
        return "call"

    return None

# ================= EJECUCIÓN =================

def execute_trade(iq, signal):
    global trade_open

    try:
        print(f"📊 Ejecutando {signal}")

        success, order_id = iq.buy(
            AMOUNT,
            PAIR,
            signal,
            EXPIRATION
        )

        if success:
            send_telegram(f"🔥 Entrada ejecutada: {signal.upper()}")
            trade_open = True
        else:
            send_telegram("❌ Error al ejecutar operación")

    except Exception as e:
        send_telegram(f"❌ Error: {str(e)}")

# ================= MAIN =================

def run():
    global last_candle_time, last_signal_time, trade_open

    iq = connect()
    if not iq:
        return

    while True:
        try:
            check_commands()

            if not bot_active:
                time.sleep(2)
                continue

            df = get_candles(iq)

            current_time = df.iloc[-1]["from"]

            # Detectar nueva vela
            if last_candle_time != current_time:
                last_candle_time = current_time
                trade_open = False
                print("🟢 Nueva vela")

                signal = get_signal(df)

                if signal and not trade_open:

                    # Esperar apertura siguiente vela
                    time.sleep(2)

                    execute_trade(iq, signal)

            time.sleep(1)

        except Exception as e:
            print(f"ERROR: {e}")
            send_telegram(f"❌ ERROR GENERAL: {str(e)}")
            time.sleep(5)

# ================= START =================

if __name__ == "__main__":
    run()
