import os
import time
import json
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
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass

# =========================
# CONEXIÓN ROBUSTA (ANTI JSON ERROR)
# =========================
def connect_iq():
    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    if not EMAIL or not PASSWORD:
        print("❌ Faltan credenciales")
        return None

    iq = IQ_Option(EMAIL, PASSWORD)

    print("🔄 Conectando a IQ Option...")

    for i in range(5):
        try:
            status, reason = iq.connect()
            print(f"Intento {i+1}: {status} | {reason}")

            if status:
                print("✅ Conectado correctamente")
                iq.change_balance("PRACTICE")
                return iq

            # 🔥 Manejo de respuesta inválida
            try:
                if reason:
                    data = json.loads(reason)
                    print("⚠️ Respuesta IQ:", data)
            except:
                print("⚠️ Respuesta NO válida (posible bloqueo o captcha)")

        except Exception as e:
            print("❌ Error conexión:", e)

        time.sleep(5)

    print("❌ No se pudo conectar a IQ Option")
    return None

# =========================
# OBTENER VELAS
# =========================
def get_candles(iq, timeframe, count):
    try:
        candles = iq.get_candles(PAIR, timeframe, count, time.time())
        return sorted(candles, key=lambda x: x["from"])
    except Exception as e:
        print("⚠️ Error obteniendo velas:", e)
        return None

# =========================
# COLOR VELA
# =========================
def get_color(candle):
    return "verde" if candle["close"] > candle["open"] else "rojo"

# =========================
# MAIN
# =========================
def main():

    print("🚀 BOT SNIPER ACTIVO")

    iq = connect_iq()

    if iq is None:
        print("⏳ Reintentando conexión en 60s...")
        time.sleep(60)
        return main()

    last_minute = None
    alert_sent = False
    signal = None

    while True:
        try:
            now = datetime.now()
            minute = now.minute
            second = now.second

            # 🔄 Reset cada nueva vela
            if minute != last_minute:
                last_minute = minute
                alert_sent = False
                signal = None
                print(f"\n🕐 Nueva vela M1: {minute}")

            # =========================
            # 🔎 DETECCIÓN (SEGUNDO 30)
            # =========================
            if second == 30 and not alert_sent:

                candles_5s = get_candles(iq, 5, 6)

                if not candles_5s or len(candles_5s) < 6:
                    print("⚠️ No hay suficientes velas")
                    continue

                pattern = check_pattern(candles_5s)

                if pattern:
                    signal = pattern
                    alert_sent = True

                    print(f"📡 Señal detectada: {signal.upper()}")

                    send_telegram(
                        f"🚨 ALERTA SNIPER\n"
                        f"Par: {PAIR}\n"
                        f"Dirección: {signal.upper()}\n"
                        f"⏳ Esperando apertura"
                    )
                else:
                    print("❌ Sin patrón válido")

            # =========================
            # 🎯 EJECUCIÓN (SEGUNDO 0)
            # =========================
            if second == 0 and signal:

                candles_1m = get_candles(iq, 60, 2)

                if not candles_1m or len(candles_1m) < 2:
                    continue

                last_closed = candles_1m[-2]
                color = get_color(last_closed)

                print(f"📊 M1 cerrada: {color}")

                # Validación final
                if signal == "call" and color == "verde":
                    direction = "call"
                elif signal == "put" and color == "rojo":
                    direction = "put"
                else:
                    print("❌ No coincide con M1 → NO OPERAR")
                    signal = None
                    continue

                print(f"🚀 EJECUTANDO {direction.upper()}")

                try:
                    check, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

                    if check:
                        print("✅ Operación ejecutada")
                        send_telegram(
                            f"✅ ENTRADA\n{PAIR}\n{direction.upper()}"
                        )
                    else:
                        print("❌ Error al ejecutar operación")

                except Exception as e:
                    print("❌ Error en trade:", e)

                signal = None

            time.sleep(1)

        except Exception as e:
            print(f"❌ ERROR GENERAL: {e}")
            time.sleep(5)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    main()
