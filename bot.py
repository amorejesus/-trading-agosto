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
AMOUNT = 55
EXPIRATION = 1  # minutos

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass

# =========================
# CONEXIÓN IQ OPTION
# =========================
def connect_iq():
    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    if not EMAIL or not PASSWORD:
        print("❌ ERROR: Faltan credenciales IQ Option")
        return None

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error conectando a IQ Option")
        return None

    iq.change_balance("PRACTICE")
    print("✅ Conectado a IQ Option")

    return iq

# =========================
# OBTENER VELAS
# =========================
def get_candles(iq, timeframe, count):
    candles = iq.get_candles(PAIR, timeframe, count, time.time())
    candles = sorted(candles, key=lambda x: x['from'])
    return candles

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
        print("⏳ Reintentando conexión en 60s...")
        time.sleep(60)
        return main()

    print("🚀 BOT SNIPER ACTIVO")

    last_minute = None
    alert_sent = False
    signal = None

    while True:
        try:
            now = datetime.now()
            minute = now.minute
            second = now.second

            # RESET cada nueva vela M1
            if minute != last_minute:
                last_minute = minute
                alert_sent = False
                signal = None
                print(f"\n🕐 Nueva vela M1: {minute}")

            # =========================
            # 🔎 ANALISIS SEGUNDO 30
            # =========================
            if second == 30 and not alert_sent:

                candles_5s = get_candles(iq, 5, 6)

                if len(candles_5s) < 6:
                    print("⚠️ No hay suficientes velas")
                    continue

                pattern = check_pattern(candles_5s)

                if pattern:
                    signal = pattern
                    alert_sent = True

                    print(f"📡 Señal detectada: {signal}")

                    send_telegram(
                        f"📡 ALERTA SNIPER\n"
                        f"Par: {PAIR}\n"
                        f"Dirección: {signal.upper()}\n"
                        f"⏳ Esperando cierre M1"
                    )
                else:
                    print("❌ Sin patrón válido")

            # =========================
            # 🎯 EJECUCIÓN SEGUNDO 58
            # =========================
            if second == 58 and signal:

                candles_1m = get_candles(iq, 60, 1)

                if len(candles_1m) == 0:
                    continue

                candle = candles_1m[-1]
                color = get_color(candle)

                print(f"📊 Cierre M1: {color}")

                # VALIDACIÓN FINAL (CLAVE)
                if signal == "call" and color == "verde":
                    direction = "call"
                elif signal == "put" and color == "rojo":
                    direction = "put"
                else:
                    print("❌ No coincide con M1 → NO OPERAR")
                    signal = None
                    continue

                print(f"🚀 EJECUTANDO {direction.upper()}")

                check, order_id = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

                if check:
                    print("✅ Operación ejecutada")

                    send_telegram(
                        f"✅ ENTRADA EJECUTADA\n"
                        f"Par: {PAIR}\n"
                        f"Dirección: {direction.upper()}"
                    )
                else:
                    print("❌ Error al ejecutar operación")

                signal = None

            time.sleep(1)

        except Exception as e:
            print(f"❌ ERROR GENERAL: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
