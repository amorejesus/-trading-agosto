import time
import os
import requests
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# ================= CONFIG =================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAR = "EURUSD-OTC"
MONTO = 2
EXPIRACION = 1

# ================= VARIABLES =================
iq = None
bot_activo = True
last_update_id = 0
ultimo_trade = 0
last_candle_time = None

# ================= TELEGRAM =================
def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("❌ Error Telegram:", e)


def leer_comandos():
    global bot_activo, last_update_id

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={last_update_id+1}"
        res = requests.get(url).json()

        for upd in res.get("result", []):
            last_update_id = upd["update_id"]

            if "message" in upd:
                text = upd["message"].get("text", "")

                if text == "/start":
                    bot_activo = True
                    enviar_telegram("🟢 BOT ACTIVADO")

                elif text == "/stop":
                    bot_activo = False
                    enviar_telegram("🔴 BOT DETENIDO")

    except Exception as e:
        print("❌ Error comandos:", e)

# ================= CONEXIÓN =================
def conectar():
    global iq

    while True:
        try:
            iq = IQ_Option(EMAIL, PASSWORD)
            iq.connect()

            if iq.check_connect():
                print("✅ Conectado a IQ Option")
                enviar_telegram("✅ Bot conectado")
                iq.change_balance("PRACTICE")
                return
            else:
                print("❌ Error conexión")

        except Exception as e:
            print("❌ Error conexión:", e)

        time.sleep(5)

# ================= EJECUCIÓN =================
def ejecutar(signal):
    global ultimo_trade

    # evitar repetir en la misma vela
    if time.time() - ultimo_trade < 55:
        return

    try:
        print(f"🔥 Ejecutando {signal}")

        status, trade_id = iq.buy(MONTO, PAR, signal, EXPIRACION)

        if status:
            print("✅ Operación ejecutada")
            enviar_telegram(f"✅ OPERACIÓN {signal.upper()}")
            ultimo_trade = time.time()
        else:
            print("❌ Error IQ:", trade_id)
            enviar_telegram(f"❌ ERROR IQ: {trade_id}")

    except Exception as e:
        print("❌ Error ejecución:", e)
        enviar_telegram(f"❌ ERROR: {e}")

# ================= LOOP PRINCIPAL =================
def main():
    global last_candle_time

    conectar()

    while True:
        try:
            print("🔄 Bot corriendo...")

            leer_comandos()

            if not bot_activo:
                time.sleep(1)
                continue

            if not iq.check_connect():
                print("🔄 Reconectando...")
                conectar()

            # ===== OBTENER VELAS =====
            velas = iq.get_candles(PAR, 60, 10, time.time())

            if not velas:
                continue

            current_candle_time = velas[-1]["from"]

            # ===== NUEVA VELA =====
            if current_candle_time != last_candle_time:
                last_candle_time = current_candle_time

                señal = pro_signal(velas)

                if señal:
                    print(f"📊 Señal detectada: {señal.upper()}")
                    enviar_telegram(f"📊 Señal: {señal.upper()}")

                    ejecutar(señal)

            time.sleep(1)

        except Exception as e:
            print("❌ ERROR GLOBAL:", e)
            enviar_telegram(f"❌ ERROR GLOBAL: {e}")
            time.sleep(5)

# ================= START =================
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("💥 CRASH:", e)
            time.sleep(5)
