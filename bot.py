import os
import time
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from strategy import check_pattern
import requests

# ==============================
# CONFIG
# ==============================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 55
EXPIRATION = 1  # 1 minuto

# ==============================
# TELEGRAM
# ==============================
def send_telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        try:
            requests.post(url, data=data)
        except:
            pass

# ==============================
# CONEXION IQ
# ==============================
def connect_iq():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("❌ Faltan IQ_EMAIL o IQ_PASSWORD")

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        raise RuntimeError("❌ Error conectando a IQ Option")

    iq.change_balance("PRACTICE")
    return iq

# ==============================
# OBTENER VELAS
# ==============================
def get_candles(iq):
    # 5 segundos (últimas 6)
    candles_5s = iq.get_candles(PAIR, 5, 6, time.time())

    # 1 minuto (últimas 2, usamos la cerrada)
    candles_1m = iq.get_candles(PAIR, 60, 2, time.time())

    return candles_5s, candles_1m

# ==============================
# MAIN
# ==============================
def main():
    print("🚀 BOT SNIPER 5s + M1 INICIADO")

    iq = connect_iq()

    last_minute = None
    signal = None
    alert_sent = False

    while True:
        try:
            now = datetime.now()
            second = now.second
            minute = now.minute

            candles_5s, candles_1m = get_candles(iq)

            # ==============================
            # 1. DETECTAR PATRON (0s - 30s)
            # ==============================
            if 5 <= second <= 30:
                pattern_signal = check_pattern(candles_5s)

                if pattern_signal and not signal:
                    # Validar con vela M1 CERRADA
                    last_m1 = candles_1m[-2]

                    if last_m1["close"] > last_m1["open"]:
                        direction = "call"
                    else:
                        direction = "put"

                    signal = direction
                    print(f"✅ Señal detectada: {signal.upper()}")

                    # ALERTA TELEGRAM
                    if not alert_sent:
                        send_telegram(f"🚨 Señal: {signal.upper()} en próxima vela")
                        alert_sent = True

            # ==============================
            # 2. EJECUTAR SOLO EN SEGUNDO 0
            # ==============================
            if second == 0 and signal and minute != last_minute:
                print(f"🎯 EJECUTANDO {signal.upper()}")

                check, id = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

                if check:
                    print("✅ Entrada ejecutada")
                    send_telegram(f"📈 Entrada {signal.upper()} ejecutada")
                else:
                    print("❌ Error al ejecutar")

                # Reset
                signal = None
                alert_sent = False
                last_minute = minute

            time.sleep(1)

        except Exception as e:
            print(f"⚠️ Error: {e}")
            time.sleep(2)

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    main()
