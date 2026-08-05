import time
import os
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# ================= CONFIG =================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

PAIR = "EURUSD-OTC"
AMOUNT = 30
EXPIRATION = 1  # 1 minuto

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ================= TELEGRAM =================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        })
    except:
        pass

# ================= CONEXIÓN =================
def connect_iq():
    print("🔌 Conectando...")
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error de conexión")
        send_telegram("❌ Error de conexión")
        return None

    iq.change_balance("PRACTICE")
    print("✅ Conectado correctamente")
    send_telegram("🤖 BOT ACTIVO")
    return iq

iq = connect_iq()
if iq is None:
    exit()

# ================= VARIABLES =================
last_candle_time = None
signal_ready = None
waiting_entry = False
bot_active = True

# ================= LOOP =================
while True:
    try:
        if not iq.check_connect():
            print("🔄 Reconectando...")
            iq = connect_iq()
            time.sleep(3)
            continue

        candles = iq.get_candles(PAIR, 60, 50, time.time())

        if candles is None or len(candles) == 0:
            continue

        df = pd.DataFrame(candles)

        # 🔥 CORRECCIÓN CLAVE (evita error iloc)
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["open"] = pd.to_numeric(df["open"], errors="coerce")

        current_candle_time = df.iloc[-1]["from"]

        # ================= NUEVA VELA =================
        if current_candle_time != last_candle_time:
            print("🟢 Nueva vela detectada")

            # ================= EJECUTAR ENTRADA =================
            if waiting_entry and signal_ready:
                print(f"🚀 Ejecutando {signal_ready}")

                check, trade_id = iq.buy(
                    AMOUNT,
                    PAIR,
                    "call" if signal_ready == "CALL" else "put",
                    EXPIRATION
                )

                if check:
                    print("✅ Entrada ejecutada")
                    send_telegram(f"✅ Entrada ejecutada: {signal_ready}")
                else:
                    print("❌ Error al ejecutar operación")
                    send_telegram("❌ Error al ejecutar operación")

                # RESET
                waiting_entry = False
                signal_ready = None

            # ================= DETECTAR SEÑAL =================
            signal = pro_signal(df)

            if signal:
                print(f"🔥 Señal detectada: {signal}")
                send_telegram(f"🔥 Señal detectada: {signal}")

                # 👇 IMPORTANTE: esperar siguiente vela
                signal_ready = signal
                waiting_entry = True

            last_candle_time = current_candle_time

        time.sleep(1)

    except Exception as e:
        print("❌ ERROR GENERAL:", e)
        send_telegram(f"❌ ERROR: {e}")
        time.sleep(5)
