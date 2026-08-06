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

iq = None
bot_activo = True
ultimo_trade = 0
last_update_id = 0

# ================= TELEGRAM =================
def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Error Telegram:", e)


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
            print("❌ Error conexión:", e)

        time.sleep(5)

# ================= SNIPER =================
def esperar_pre_cierre():
    while True:
        t = time.time()
        sec = int(t) % 60
        ms = int((t - int(t)) * 1000)

        if (sec == 58 and ms >= 500) or sec == 59:
            return

        time.sleep(0.001)

# ================= OPERAR =================
def ejecutar(signal):
    global ultimo_trade

    if time.time() - ultimo_trade < 55:
        return

    esperar_pre_cierre()

    try:
        print(f"🔥 Ejecutando {signal}")

        status, trade_id = iq.buy(MONTO, PAR, signal, EXPIRACION)

        if status:
            enviar_telegram(f"✅ OPERACIÓN {signal}")
            print("✅ Operación ejecutada")
            ultimo_trade = time.time()
        else:
            enviar_telegram(f"❌ ERROR IQ: {trade_id}")
            print("❌ Error:", trade_id)

    except Exception as e:
        enviar_telegram(f"❌ ERROR: {e}")
        print("❌ Error ejecución:", e)

# ================= MAIN =================
def main():
    conectar()

    while True:
        try:
            print("🔄 Bot corriendo...")  # 🔥 mantiene vivo Railway

            leer_comandos()

            if not bot_activo:
                time.sleep(1)
                continue

            if not iq.check_connect():
                print("🔄 Reconectando...")
                conectar()

            velas_m1 = iq.get_candles(PAR, 60, 50, time.time())
            velas_m5 = iq.get_candles(PAR, 300, 50, time.time())

            if not velas_m1 or not velas_m5:
                continue

            señal = pro_signal(velas_m5, velas_m1)

            if señal == "call":
                print("📈 CALL")
                ejecutar("call")

            elif señal == "put":
                print("📉 PUT")
                ejecutar("put")

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
