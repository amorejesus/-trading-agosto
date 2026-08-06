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

# ================= TELEGRAM =================
def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)


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
        print("Error comandos:", e)

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
            print("Error conexión:", e)

        time.sleep(3)

# ================= ULTRA TIMING =================
def esperar_cierre_ultra():
    while True:
        t = time.time()

        sec = int(t) % 60
        ms = int((t - int(t)) * 1000)

        # 🎯 detectar cierre en 59.800 ms
        if sec == 59 and ms >= 800:
            return

        time.sleep(0.0001)  # ultra precisión

# ================= LOOP PRINCIPAL =================
def main():
    global ultimo_trade

    conectar()

    while True:
        try:
            leer_comandos()

            if not bot_activo:
                time.sleep(0.2)
                continue

            if not iq.check_connect():
                print("🔄 Reconectando...")
                conectar()

            # ⚡ ESPERA CIERRE PRECISO
            esperar_cierre_ultra()

            # ⚡ SOLO UNA LLAMADA (menos latencia)
            velas = iq.get_candles(PAR, 60, 5, time.time())

            if not velas:
                continue

            señal = pro_signal(velas)

            # ⚡ CONTROL DE SPAM DE OPERACIONES
            if señal and time.time() - ultimo_trade > 55:

                print(f"⚡ SEÑAL: {señal.upper()}")

                # ⚡ EJECUCIÓN INMEDIATA
                status, trade_id = iq.buy(MONTO, PAR, señal, EXPIRACION)

                print("STATUS:", status)
                print("RESPUESTA:", trade_id)

                if status:
                    ultimo_trade = time.time()
                    enviar_telegram(f"⚡ OPERACIÓN {señal.upper()}")
                else:
                    enviar_telegram(f"❌ ERROR: {trade_id}")

        except Exception as e:
            print("❌ ERROR GLOBAL:", e)
            enviar_telegram(f"❌ ERROR: {e}")
            time.sleep(1)

# ================= START =================
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("💥 CRASH:", e)
            time.sleep(2)
