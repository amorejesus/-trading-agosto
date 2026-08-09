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
# DIRECCIÓN VELA
# =========================
def get_candle_color(candle):
    if candle["close"] > candle["open"]:
        return "verde"
    else:
        return "rojo"

# =========================
# MAIN
# =========================
def main():
    iq = connect_iq()
    if iq is None:
        print("⏳ Reintentando en 60s...")
        time.sleep(60)
        return main()

    last_minute = None
    alert_sent = False
    signal_direction = None

    print("🚀 BOT SNIPER 5s + M1 INICIADO")

    while True:
        try:
            now = datetime.now()
            current_minute = now.minute
            current_second = now.second

            # Reinicio cada minuto
            if last_minute != current_minute:
                last_minute = current_minute
                alert_sent = False
                signal_direction = None
                print(f"\n🕐 Nueva vela M1: {current_minute}")

            # =========================
            # 🔎 ANALISIS EN SEGUNDO 30
            # =========================
            if current_second == 30 and not alert_sent:

                candles_5s = get_candles(iq, 5, 6)

                if len(candles_5s) < 6:
                    continue

                pattern_signal = check_pattern(candles_5s)

                if pattern_signal:
                    signal_direction = pattern_signal
                    alert_sent = True

                    send_telegram(f"📡 ALERTA SNIPER\nPar: {PAIR}\nDirección: {signal_direction.upper()}\n(Esperando cierre M1)")

                    print(f"📡 Señal detectada: {signal_direction}")

                else:
                    print("❌ Sin patrón válido")

            # =========================
            # 🎯 EJECUCIÓN EN CIERRE M1
            # =========================
            if current_second == 58 and signal_direction:

                candles_1m = get_candles(iq, 60, 1)

                if len(candles_1m) == 0:
                    continue

                last_candle = candles_1m[-1]
                candle_color = get_candle_color(last_candle)

                print(f"📊 Cierre M1: {candle_color}")

                # VALIDACIÓN FINAL (SIN INVERSIÓN)
                if signal_direction == "call" and candle_color == "verde":
                    direction = "call"
                elif signal_direction == "put" and candle_color == "rojo":
                    direction = "put"
                else:
                    print("❌ No coincide con M1 → NO OPERAR")
                    signal_direction = None
                    continue

                print(f"🚀 EJECUTANDO {direction.upper()}")

                check, id = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

                if check:
                    send_telegram(f"✅ ENTRADA EJECUTADA\nPar: {PAIR}\nDirección: {direction.upper()}")
                    print("✅ Operación enviada")
                else:
                    print("❌ Error al ejecutar operación")

                signal_direction = None

            time.sleep(1)

        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
