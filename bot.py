import os
import time
import requests
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from strategy import check_pattern

# =========================
# CONFIG
# =========================
PAIR = "EURUSD-OTC"
AMOUNT = 10
EXPIRATION = 1

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass

# =========================
# ✅ CONEXIÓN (LA TUYA QUE FUNCIONA)
# =========================
def connect_iq():
    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    if not EMAIL or not PASSWORD:
        print("❌ Faltan credenciales")
        return None

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if iq.check_connect():
        print("✅ Conectado a IQ Option")
        iq.change_balance("PRACTICE")
        return iq
    else:
        print("❌ Error conectando")
        return None

# =========================
# OBTENER VELAS
# =========================
def get_candles(iq, timeframe, count):
    candles = iq.get_candles(PAIR, timeframe, count, time.time())
    return sorted(candles, key=lambda x: x["from"])

# =========================
# COLOR VELA
# =========================
def get_color(candle):
    return "verde" if candle["close"] > candle["open"] else "rojo"

# =========================
# MAIN
# =========================
def main():

    iq = connect_iq()

    if iq is None:
        print("⏳ Reintentando en 30s...")
        time.sleep(30)
        return main()

    print("🚀 BOT SNIPER ACTIVO")

    last_minute = None
    signal = None
    alert_sent = False

    while True:
        try:
            now = datetime.now()
            minute = now.minute
            second = now.second

            # 🔄 Reset por nueva vela
            if minute != last_minute:
                last_minute = minute
                signal = None
                alert_sent = False
                print(f"\n🕐 Nueva vela M1: {minute}")

            # =========================
            # 🔎 DETECCIÓN (SEGUNDO 30)
            # =========================
            if second == 30 and not alert_sent:

                candles_5s = get_candles(iq, 5, 6)

                if len(candles_5s) < 6:
                    continue

                pattern = check_pattern(candles_5s)

                if pattern:
                    signal = pattern
                    alert_sent = True

                    print(f"📡 Señal detectada: {signal.upper()}")

                    send_telegram(
                        f"🚨 ALERTA SNIPER\n"
                        f"{PAIR}\n"
                        f"Dirección: {signal.upper()}\n"
                        f"⏳ Esperando apertura"
                    )

            # =========================
            # 🎯 EJECUCIÓN (SEGUNDO 0)
            # =========================
            if second == 0 and signal:

                candles_1m = get_candles(iq, 60, 2)

                if len(candles_1m) < 2:
                    continue

                last_closed = candles_1m[-2]
                color = get_color(last_closed)

                print(f"📊 M1 cerrada: {color}")

                if signal == "call" and color == "verde":
                    direction = "call"
                elif signal == "put" and color == "rojo":
                    direction = "put"
                else:
                    print("❌ No coincide → NO OPERAR")
                    signal = None
                    continue

                print(f"🚀 EJECUTANDO {direction.upper()}")

                check, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

                if check:
                    print("✅ Trade ejecutado")
                    send_telegram(f"✅ Entrada {direction.upper()}")
                else:
                    print("❌ Error en trade")

                signal = None

            time.sleep(1)

        except Exception as e:
            print("❌ ERROR:", e)
            time.sleep(5)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()
