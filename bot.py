import os
import time
import requests
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from strategy import check_pattern, get_m1_direction

# ==============================
# CONFIG
# ==============================
PAIR = "EURUSD-OTC"
AMOUNT = 75
EXPIRATION = 1

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==============================
# TELEGRAM
# ==============================
def send_telegram(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=5)
    except:
        pass


# ==============================
# CONEXIÓN ROBUSTA (NO SE CAE)
# ==============================
def connect_iq():
    if not EMAIL or not PASSWORD:
        print("❌ Faltan credenciales")
        return None

    iq = IQ_Option(EMAIL, PASSWORD)

    print("🔄 Conectando a IQ Option...")

    for i in range(5):
        try:
            status, reason = iq.connect()
            print(f"Intento {i+1} → {status} | {reason}")

            if iq.check_connect():
                print("✅ Conectado correctamente")
                iq.change_balance("PRACTICE")
                return iq

        except Exception as e:
            print("Error conexión:", e)

        time.sleep(3)

    print("❌ No se pudo conectar a IQ Option")
    return None


# ==============================
# RECONEXIÓN AUTOMÁTICA
# ==============================
def ensure_connection(iq):
    if iq is None or not iq.check_connect():
        print("🔁 Reconectando...")
        return connect_iq()
    return iq


# ==============================
# OBTENER VELAS
# ==============================
def get_candles(iq):
    try:
        candles_5s = iq.get_candles(PAIR, 5, 6, time.time())
        candles_1m = iq.get_candles(PAIR, 60, 2, time.time())
        return candles_5s, candles_1m
    except Exception as e:
        print("⚠️ Error obteniendo velas:", e)
        return None, None


# ==============================
# MAIN
# ==============================
def main():
    print("🚀 BOT SNIPER INICIADO")

    iq = connect_iq()

    signal = None
    alert_sent = False
    last_minute = None

    while True:
        try:
            iq = ensure_connection(iq)

            if iq is None:
                print("⏳ Esperando conexión...")
                time.sleep(10)
                continue

            now = datetime.now()
            second = now.second
            minute = now.minute

            # RESET cada nuevo minuto
            if minute != last_minute:
                signal = None
                alert_sent = False
                last_minute = minute
                print(f"\n🕐 Nuevo minuto: {minute}")

            candles_5s, candles_1m = get_candles(iq)

            if not candles_5s or not candles_1m:
                continue

            # ==========================
            # DETECCIÓN (PRIMEROS 30s)
            # ==========================
            if 5 <= second <= 30 and signal is None:

                pattern = check_pattern(candles_5s)

                if pattern:
                    last_closed_m1 = candles_1m[-2]
                    direction = get_m1_direction(last_closed_m1)

                    signal = direction

                    print(f"📡 Señal detectada: {signal.upper()}")

                    if not alert_sent:
                        send_telegram(f"🚨 Señal {signal.upper()} próxima vela")
                        alert_sent = True

            # ==========================
            # EJECUCIÓN (SEGUNDO 0)
            # ==========================
            if second == 0 and signal:

                print(f"🎯 Ejecutando {signal.upper()}")

                try:
                    status, _ = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

                    if status:
                        print("✅ Trade ejecutado")
                        send_telegram(f"✅ Entrada {signal.upper()}")
                    else:
                        print("❌ Error al ejecutar trade")

                except Exception as e:
                    print("❌ Error al operar:", e)

                signal = None

            time.sleep(1)

        except Exception as e:
            print("❌ Error general:", e)
            time.sleep(5)


# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    main()
