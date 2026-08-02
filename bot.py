import os
import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal, update_result

# ==============================
# CONFIGURACIÓN
# ==============================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIRS = [
    "EURUSD-OTC",
    "EURJPY-OTC"
]

AMOUNT = 3338
EXPIRATION = 1
MAX_OPERATIONS = 4  # 🔥 SOLO 4 OPERACIONES

bot_active = True
operations_count = 0
last_candle_time = {}
last_update_id = None

# ==============================
# TELEGRAM
# ==============================
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg
        })
    except Exception as e:
        print(f"❌ Error Telegram: {e}")

# ==============================
# COMANDOS TELEGRAM
# ==============================
def check_telegram_commands():
    global bot_active, last_update_id, operations_count

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        resp = requests.get(url).json()

        if not resp.get("ok"):
            return

        for update in resp.get("result", []):
            update_id = update["update_id"]

            if last_update_id is None or update_id > last_update_id:
                last_update_id = update_id

                if "message" in update:
                    text = update["message"].get("text", "")

                    if text == "/stop":
                        bot_active = False
                        send_telegram("⛔ BOT DETENIDO")

                    elif text == "/start":
                        bot_active = True
                        operations_count = 0  # 🔥 reinicia contador
                        send_telegram("✅ BOT REINICIADO")

    except Exception as e:
        print("❌ Error Telegram:", e)

# ==============================
# 🎯 SNIPER PRO (confirmación final)
# ==============================
def confirmacion_final(df, direccion):
    last = df.iloc[-1]

    if direccion == "call":
        return last["close"] >= last["open"]

    if direccion == "put":
        return last["close"] <= last["open"]

    return False

def esperar_y_confirmar(df, direccion):
    while True:
        segundos = time.time() % 60

        if segundos >= 57:  # últimos segundos
            if confirmacion_final(df, direccion):
                print("✅ Confirmación final OK")
                return True
            else:
                print("❌ Entrada cancelada")
                return False

        time.sleep(0.1)

# ==============================
# CONEXIÓN IQ OPTION
# ==============================
print("🔌 Conectando...")
Iq = IQ_Option(EMAIL, PASSWORD)
Iq.connect()

if not Iq.check_connect():
    print("❌ Error conexión")
    exit()

print("✅ Conectado")
send_telegram("🤖 BOT SNIPER ACTIVADO")

# ==============================
# LOOP PRINCIPAL
# ==============================
while True:
    try:
        check_telegram_commands()

        if not bot_active:
            time.sleep(2)
            continue

        # 🔥 LIMITE DE OPERACIONES
        if operations_count >= MAX_OPERATIONS:
            bot_active = False
            send_telegram("🏁 Límite de 3 operaciones alcanzado. Bot detenido.")
            continue

        for pair in PAIRS:
            try:
                candles = Iq.get_candles(pair, 60, 100, time.time())

                if not candles:
                    continue

                df = pd.DataFrame([{
                    "open": c["open"],
                    "close": c["close"],
                    "max": c["max"],
                    "min": c["min"]
                } for c in candles])

                current_time = candles[-1]["from"]

                # evitar repetir vela
                if pair in last_candle_time and last_candle_time[pair] == current_time:
                    continue

                last_candle_time[pair] = current_time

                print(f"📊 {pair} nueva vela")

                # ==============================
                # SEÑAL
                # ==============================
                signal = pro_signal(df, aggressive=True)

                if not signal:
                    continue

                direccion = signal["direction"]
                score = signal["score"]

                print(f"🔥 {pair} → {direccion} | score {score}")

                send_telegram(
                    f"📊 {pair}\n"
                    f"Señal: {direccion.upper()}\n"
                    f"Score: {score}"
                )

                # ==============================
                # 🎯 SNIPER PRO
                # ==============================
                print("⏳ Esperando confirmación...")

                if not esperar_y_confirmar(df, direccion):
                    continue

                print("🎯 DISPARO SNIPER")

                status, trade_id = Iq.buy(AMOUNT, pair, direccion, EXPIRATION)

                if status:
                    operations_count += 1

                    send_telegram(f"🚀 {pair} → {direccion.upper()}")

                    time.sleep(EXPIRATION * 60)

                    result = Iq.check_win_v4(trade_id)

                    update_result(result)

                    send_telegram(f"📈 Resultado: {result}")

                else:
                    print("❌ Error operación")

            except Exception as e:
                print(f"❌ Error en {pair}: {e}")

        time.sleep(1)

    except Exception as e:
        print("❌ ERROR GENERAL:", e)
        time.sleep(5)
