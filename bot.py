import os
import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

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
    enviar_telegram("✅ SNIPER conectado")

    iq.change_balance("PRACTICE")
    return iq


iq = conectar()
if iq is None:
    exit()


# =========================
# ESPERA ACTIVA SNIPER
# =========================
def esperar_inicio_vela():
    while True:
        t = time.time()
        segundos = int(t) % 60
        miliseg = int((t - int(t)) * 1000)

        # 🎯 VENTANA SNIPER
        if segundos == 0 and miliseg >= 800:
            return

        time.sleep(0.001)  # 🔥 ultra precisión


# =========================
# LOOP
# =========================
last_candle_time = None

while True:
    try:
        if not bot_activo:
            time.sleep(1)
            continue

        if not iq.check_connect():
            enviar_telegram("🔁 Reconectando...")
            iq = conectar()
            continue

        # 🔥 ESPERA SNIPER
        esperar_inicio_vela()

        candles = iq.get_candles(PAIR, 60, 100, time.time())
        df = pd.DataFrame(candles)

        current_candle_time = df.iloc[-1]["from"]

        if last_candle_time == current_candle_time:
            continue

        last_candle_time = current_candle_time

        signal = pro_signal(df)

        if signal:
            enviar_telegram(f"🔥 SNIPER: {signal.upper()}")

            # 🔥 VALIDAR MERCADO
            open_assets = iq.get_all_open_time()

            if not open_assets["binary"][PAIR]["open"]:
                enviar_telegram("❌ Mercado cerrado")
                continue

            # 🔥 EJECUCIÓN INMEDIATA
            t1 = time.time()

            status, trade_id = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

            t2 = time.time()

            delay = round((t2 - t1) * 1000, 2)

            print("⏱ Delay:", delay, "ms")

            if status:
                enviar_telegram(f"✅ SNIPER OK ({delay}ms)")
            else:
                enviar_telegram(f"❌ ERROR IQ: {trade_id}")

        time.sleep(0.5)

    except Exception as e:
        print("❌ ERROR:", e)
        enviar_telegram(f"❌ ERROR: {e}")
        time.sleep(2)
