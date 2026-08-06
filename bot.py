import time
import os
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# ================= CONFIG =================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

PAR = "EURUSD-OTC"
MONTO = 2
EXPIRACION = 1  # 1 minuto

# =========================================

iq = None
bot_active = True
ultimo_trade = 0


# ========= CONEXIÓN =========
def conectar():
    global iq
    while True:
        try:
            iq = IQ_Option(EMAIL, PASSWORD)
            iq.connect()

            if iq.check_connect():
                print("✅ Conectado a IQ Option")
                iq.change_balance("PRACTICE")
                return
            else:
                print("❌ Error conectando...")
        except Exception as e:
            print(f"❌ Error conexión: {e}")

        time.sleep(5)


# ========= OBTENER DATOS =========
def get_candles(par, timeframe, cantidad):
    try:
        velas = iq.get_candles(par, timeframe, cantidad, time.time())
        return velas
    except Exception as e:
        print(f"❌ Error obteniendo velas: {e}")
        return []


# ========= SNIPER TIME =========
def esperar_cierre():
    while True:
        segundos = time.time() % 60

        if segundos >= 58:
            break

        time.sleep(0.2)


# ========= EJECUTAR OPERACIÓN =========
def ejecutar_operacion(par, accion):
    global ultimo_trade

    # Evitar spam
    if time.time() - ultimo_trade < 60:
        return

    esperar_cierre()

    try:
        print(f"🔥 Ejecutando {accion} en {par}")

        status, trade_id = iq.buy(MONTO, par, accion, EXPIRACION)

        if status:
            print(f"✅ OPERACIÓN ABIERTA: {accion}")
            ultimo_trade = time.time()
        else:
            print("❌ IQ Option rechazó la operación")

    except Exception as e:
        print(f"❌ ERROR EJECUCIÓN: {e}")


# ========= LOOP PRINCIPAL =========
def main():
    global iq

    conectar()

    while True:
        try:
            if not iq.check_connect():
                print("🔄 Reconectando...")
                conectar()

            if not bot_active:
                time.sleep(1)
                continue

            # Obtener datos
            velas_m1 = get_candles(PAR, 60, 50)
            velas_m5 = get_candles(PAR, 300, 50)

            if not velas_m1 or not velas_m5:
                continue

            # Señal
            señal = pro_signal(velas_m5, velas_m1)

            if señal == "call":
                print("📈 Señal CALL detectada")
                ejecutar_operacion(PAR, "call")

            elif señal == "put":
                print("📉 Señal PUT detectada")
                ejecutar_operacion(PAR, "put")

            time.sleep(1)

        except Exception as e:
            print(f"❌ ERROR GLOBAL: {e}")
            time.sleep(5)


# ========= START =========
if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print(f"💥 CRASH: {e}")
            time.sleep(5)
