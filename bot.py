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

PAIR = "EURUSD"
AMOUNT = 54.60
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

        for update in response.get("result", []):
            update_id = update["update_id"]

            # evitar repetidos
            if last_update_id is not None and update_id <= last_update_id:
                continue

            last_update_id = update_id

            if "message" in update:
                text = update["message"].get("text", "")

                if text == "/start" and not bot_activo:
                    bot_activo = True
                    enviar_telegram("🟢 BOT ACTIVADO")

                elif text == "/stop" and bot_activo:
                    bot_activo = False
                    enviar_telegram("🔴 BOT DETENIDO")

    except Exception as e:
        print("Error Telegram:", e)


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
    iq.change_balance("PRACTICE")
    return iq


iq = conectar()
if iq is None:
    exit()

# limpiar comandos viejos
leer_comandos()
time.sleep(2)

# =========================
# CONTROL
# =========================
last_candle_time = None
operacion_ejecutada = False
last_trade_time = 0

# =========================
# LOOP PRINCIPAL
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

        # =========================
        # OBTENER VELAS
        # =========================
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

        # =========================
        # SEÑAL
        # =========================
        signal = pro_signal(df)

        if signal not in ["call", "put"]:
            time.sleep(0.5)
            continue

        # =========================
        # ANTI-SPAM (IQ BLOCK)
        # =========================
        if time.time() - last_trade_time < 10:
            continue

        # =========================
        # TIMING PERFECTO
        # =========================
        segundo = int(time.time()) % 60

        if (
            signal
            and not operacion_ejecutada
            and 2 <= segundo <= 6
        ):
            enviar_telegram(f"🔥 ENTRADA: {signal.upper()}")

            action = "call" if signal == "call" else "put"

            open_time = iq.get_all_open_time()

            digital_open = False
            binary_open = False

            try:
                digital_open = open_time["digital"][PAIR]["open"]
            except:
                pass

            try:
                binary_open = open_time["binary"][PAIR]["open"]
            except:
                pass

            status = False
            trade_id = None

            # =========================
            # DIGITAL
            # =========================
            if digital_open:
                print("📊 DIGITAL")
                status, trade_id = iq.buy_digital_spot(PAIR, AMOUNT, action, EXPIRATION)

            # =========================
            # BINARIA
            # =========================
            elif binary_open:
                print("📊 BINARIA")
                status, trade_id = iq.buy(AMOUNT, PAIR, action, EXPIRATION)

            else:
                enviar_telegram("❌ ACTIVO CERRADO")
                print("❌ Activo no disponible")

            # =========================
            # RESULTADO
            # =========================
            if status:
                enviar_telegram(f"✅ OPERACIÓN: {signal.upper()}")
                operacion_ejecutada = True
                last_trade_time = time.time()
            else:
                enviar_telegram(f"❌ ERROR REAL: {trade_id}")
                print("ERROR DETALLE:", trade_id)

        time.sleep(0.5)

    except Exception as e:
        print("❌ ERROR:", e)
        enviar_telegram(f"❌ ERROR: {e}")
        time.sleep(3)
