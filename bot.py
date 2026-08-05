import os
import time
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# =========================
# CONFIG (Railway compatible)
# =========================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

PAIR = "EURUSD-OTC"
AMOUNT = 119
EXPIRATION = 1  # minutos

# =========================
# CONEXIÓN SEGURA
# =========================
def conectar():
    print("🔌 Conectando...")
    iq = IQ_Option(EMAIL, PASSWORD)
    status, reason = iq.connect()

    if not status:
        print("❌ ERROR CONEXIÓN:", reason)
        return None
    else:
        print("✅ Conectado correctamente")
        iq.change_balance("PRACTICE")
        return iq

iq = conectar()

if iq is None:
    exit()

# =========================
# VARIABLES CONTROL
# =========================
last_candle_time = None
operacion_ejecutada = False

# =========================
# LOOP PRINCIPAL
# =========================
while True:
    try:
        # 🔄 RECONEXIÓN AUTOMÁTICA
        if not iq.check_connect():
            print("🔁 Reconectando...")
            iq = conectar()
            if iq is None:
                time.sleep(5)
                continue

        candles = iq.get_candles(PAIR, 60, 50, time.time())

        if not candles:
            time.sleep(1)
            continue

        current_candle_time = candles[-1]["from"]

        # =========================
        # NUEVA VELA DETECTADA
        # =========================
        if last_candle_time != current_candle_time:
            last_candle_time = current_candle_time
            operacion_ejecutada = False

            print("🟢 Nueva vela")

            # =========================
            # ANALIZAR VELA CERRADA
            # =========================
            signal = pro_signal(candles)

            if signal and not operacion_ejecutada:
                print(f"🔥 SEÑAL: {signal.upper()}")

                # =========================
                # EJECUCIÓN EN APERTURA
                # =========================
                status, trade_id = iq.buy(AMOUNT, PAIR, signal, EXPIRATION)

                if status:
                    print(f"✅ ENTRADA EJECUTADA → {signal.upper()}")
                    operacion_ejecutada = True
                else:
                    print("❌ Error al ejecutar operación")

        # =========================
        # CONTROL DE VELOCIDAD (SIN SPAM)
        # =========================
        time.sleep(1)

    except Exception as e:
        print("❌ ERROR GENERAL:", e)
        time.sleep(3)
