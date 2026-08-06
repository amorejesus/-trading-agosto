import os
import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# =========================
# CONFIG
# =========================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 2
EXPIRATION = 1

bot_activo = True
last_update_id = None


# =========================
# TELEGRAM
# =========================
def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except:
        pass


def leer_comandos():
    global bot_activo, last_update_id

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        response = requests.get(url).json()

        for update in response["result"]:
            update_id = update["update_id"]

            if last_update_id and update_id <= last_update_id:
                continue

            last_update_id = update_id

            if "message" in update:
                text = update["message"].get("text", "")

                if text == "/start":
                    bot_activo = True
                    enviar_telegram("🟢 BOT ACTIVADO")

                elif text == "/stop":
                    bot_activo = False
                    enviar_telegram("🔴 BOT DETENIDO")

    except:
        pass


# =========================
# CONEXIÓN
# =========================
def conectar():
    iq = IQ_Option(EMAIL, PASSWORD)
    status, reason = iq.connect()

    if not status:
        print("❌ ERROR:", reason)
        return None

    print("✅ Conectado")
    enviar_telegram("✅ Bot conectado a IQ Option")
    iq.change_balance("REAL")
    return iq


iq = conectar()
if iq is None:
    exit()


# =========================
# CONTROL
# =========================
last_candle_time = None
operacion_ejecutada = False


# =========================
# LOOP
# =========================
while True:
    try:
        leer_comandos()

        if not bot_activo:
            time.sleep(1)
            continue

        if not iq.check_connect():
            enviar_telegram("🔁 Reconectando...")
            iq = conectar()
            time.sleep(3)
            continue

        candles = iq.get_candles(PAIR, 60, 100, time.time())

        if not candles:
            time.sleep(1)
            continue

        df = pd.DataFrame(candles)
        current_candle_time = df.iloc[-1]["from"]

        # =========================
        # NUEVA VELA
        # =========================
        if last_candle_time != current_candle_time:
            last_candle_time = current_candle_time
            operacion_ejecutada = False

            print("🟢 Nueva vela")

            signal = pro_signal(df)

            if signal and not operacion_ejecutada:
                enviar_telegram(f"🔥 Señal detectada: {signal.upper()}")

                status, trade_id = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

                if status:
                    enviar_telegram(f"✅ OPERACIÓN: {signal.upper()}")
                    operacion_ejecutada = True
                else:
                    enviar_telegram("❌ Error al ejecutar operación")

        time.sleep(1)

    except Exception as e:
        print("❌ ERROR:", e)
        enviar_telegram(f"❌ ERROR: {e}")
        time.sleep(3)
