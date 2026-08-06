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

    enviar_telegram("✅ BOT SNIPER CONECTADO")
    iq.change_balance("PRACTICE")
    return iq


iq = conectar()
if iq is None:
    exit()


# =========================
# ESPERA ANTES DEL CIERRE
# =========================
def esperar_pre_cierre():
    while True:
        t = time.time()
        segundos = int(t) % 60
        miliseg = int((t - int(t)) * 1000)

        # 🎯 ventana ideal antes del cierre
        if segundos == 58 and miliseg >= 500:
            return

        if segundos == 59:
            return

        time.sleep(0.001)


# =========================
# LOOP
# =========================
last_trade_time = 0

while True:
    try:
        if not iq.check_connect():
            enviar_telegram("🔁 Reconectando...")
            iq = conectar()
            continue

        # 🔥 esperar momento sniper
        esperar_pre_cierre()

        now = time.time()

        # evitar doble entrada
        if now - last_trade_time < 55:
            continue

        candles = iq.get_candles(PAIR, 60, 100, time.time())
        df = pd.DataFrame(candles)

        signal = pro_signal(df)

        if signal:
            enviar_telegram(f"🔥 SNIPER PRE-CIERRE: {signal.upper()}")

            # validar mercado
            open_assets = iq.get_all_open_time()

            if not open_assets["binary"][PAIR]["open"]:
                enviar_telegram("❌ Mercado cerrado")
                continue

            t1 = time.time()

            status, trade_id = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

            t2 = time.time()
            delay = round((t2 - t1) * 1000, 2)

            print("⏱ Delay:", delay, "ms")

            if status:
                enviar_telegram(f"✅ OPERADA ({delay}ms)")
                last_trade_time = now
            else:
                enviar_telegram(f"❌ ERROR IQ: {trade_id}")

        time.sleep(0.5)

    except Exception as e:
        print("❌ ERROR:", e)
        enviar_telegram(f"❌ ERROR: {e}")
        time.sleep(2)
