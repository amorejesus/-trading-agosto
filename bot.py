import time
import os
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

PAR = "EURUSD-OTC"
MONTO = 2
EXPIRACION = 1

iq = None
ultimo_trade = 0


# ================= CONEXIÓN =================
def conectar():
    global iq
    while True:
        try:
            iq = IQ_Option(EMAIL, PASSWORD)
            iq.connect()

            if iq.check_connect():
                print("✅ Conectado")
                iq.change_balance("PRACTICE")
                return
            else:
                print("❌ Error conexión")

        except Exception as e:
            print("❌ ERROR:", e)

        time.sleep(5)


# ================= TIEMPO SNIPER =================
def esperar_pre_cierre():
    while True:
        t = time.time()
        sec = int(t) % 60
        ms = int((t - int(t)) * 1000)

        if (sec == 58 and ms >= 500) or sec == 59:
            return

        time.sleep(0.001)


# ================= EJECUCIÓN =================
def ejecutar(signal):
    global ultimo_trade

    if time.time() - ultimo_trade < 55:
        return

    esperar_pre_cierre()

    try:
        print(f"🔥 Ejecutando {signal}")

        status, trade_id = iq.buy(MONTO, PAR, signal, EXPIRACION)

        if status:
            print(f"✅ OPERACIÓN {signal}")
            ultimo_trade = time.time()
        else:
            print(f"❌ ERROR REAL: {trade_id}")

    except Exception as e:
        print(f"❌ ERROR EJECUCIÓN: {e}")


# ================= LOOP =================
def main():
    conectar()

    while True:
        try:
            if not iq.check_connect():
                print("🔄 Reconectando...")
                conectar()

            # Obtener velas
            velas_m1 = iq.get_candles(PAR, 60, 50, time.time())
            velas_m5 = iq.get_candles(PAR, 300, 50, time.time())

            if not velas_m1 or not velas_m5:
                continue

            # 🔥 AQUÍ YA NO FALLA
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
            time.sleep(5)


# ================= START =================
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("💥 CRASH:", e)
            time.sleep(5)
