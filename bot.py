import time
import os
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from strategy import check_pattern

# ========= CONFIG =========
PAIR = "EURUSD-OTC"
AMOUNT = 5580
EXPIRATION = 1

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

# ========= TELEGRAM =========
import requests

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass

# ========= CONEXION =========
def connect_iq():
    if not EMAIL or not PASSWORD:
        raise RuntimeError("❌ Faltan IQ_EMAIL o IQ_PASSWORD en Railway")

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        raise RuntimeError("❌ Error conectando a IQ Option")

    iq.change_balance("PRACTICE")
    return iq

# ========= FUNCION OBTENER VELAS =========
def get_candles(iq, timeframe, count):
    return iq.get_candles(PAIR, timeframe, count, time.time())

# ========= COLOR VELA =========
def get_color(candle):
    return "green" if candle["close"] > candle["open"] else "red"

# ========= LOOP PRINCIPAL =========
def main():
    print("🚀 BOT SNIPER 5s + M1 INICIADO")
    iq = connect_iq()

    last_minute = None
    alert_sent = False

    while True:
        now = datetime.now()

        # Detectar nuevo minuto
        if last_minute != now.minute:
            last_minute = now.minute
            alert_sent = False
            print(f"\n🕐 Nuevo minuto: {last_minute}")

        seconds = now.second

        # ========= LEER SOLO EXACTAMENTE SEGUNDO 30 =========
        if seconds == 30 and not alert_sent:
            try:
                candles = get_candles(iq, 5, 6)

                pattern = [get_color(c) for c in candles]

                print("📊 Patrón detectado:", pattern)

                if check_pattern(pattern):
                    send_telegram(f"🚨 ALERTA PATRÓN DETECTADO\n{pattern}")
                    print("✅ PATRÓN VÁLIDO - ALERTA ENVIADA")
                    alert_sent = True
                else:
                    print("❌ Patrón NO válido")

            except Exception as e:
                print("Error patrón:", e)

        # ========= EJECUTAR AL CIERRE DEL MINUTO =========
        if seconds == 59 and alert_sent:
            try:
                candles_m1 = get_candles(iq, 60, 1)
                last_candle = candles_m1[-1]

                direction = "call" if last_candle["close"] > last_candle["open"] else "put"

                print("🎯 Ejecutando:", direction)

                iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

                send_telegram(f"🎯 ENTRADA {direction.upper()} ejecutada")

                alert_sent = False

            except Exception as e:
                print("Error entrada:", e)

        time.sleep(0.5)

# ========= RUN =========
if __name__ == "__main__":
    main()
