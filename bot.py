import time
import os
import requests
from iqoptionapi.stable_api import IQ_Option
from strategy import pro_signal

# =========================
# CONFIGURACIÓN
# =========================
EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
TIMEFRAME = 30
EXPIRATION = 1

last_candle_time = None
trade_open = False


# =========================
# TELEGRAM
# =========================
def enviar_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except:
        pass


# =========================
# CONEXIÓN IQ OPTION
# =========================
def conectar():
    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        print("❌ Error de conexión")
        return None

    print("✅ Conectado a IQ Option")
    iq.change_balance("PRACTICE")
    return iq


# =========================
# VALIDAR ACTIVO
# =========================
def activo_abierto(iq, pair):
    try:
        activos = iq.get_all_open_time()
        return activos["binary"][pair]["open"]
    except:
        return False


# =========================
# EJECUTAR OPERACIÓN
# =========================
def ejecutar_operacion(iq, pair, direccion, monto):
    try:
        direccion = direccion.lower()

        print(f"📡 Ejecutando: {direccion} en {pair}")

        check, order_id = iq.buy(monto, pair, direccion, EXPIRATION)

        if check:
            print("✅ OPERACIÓN EJECUTADA")
            enviar_telegram(f"✅ Operación ejecutada: {direccion.upper()}")
            return True
        else:
            print("❌ IQ no ejecutó la orden")
            enviar_telegram("❌ Error al ejecutar operación")
            return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        enviar_telegram(f"❌ Error: {e}")
        return False


# =========================
# LOOP PRINCIPAL
# =========================
def run():
    global last_candle_time, trade_open

    iq = conectar()
    if iq is None:
        return

    enviar_telegram("🤖 BOT ACTIVO")

    while True:
        try:
            # =========================
            # OBTENER VELAS
            # =========================
            velas = iq.get_candles(PAIR, TIMEFRAME, 50, time.time())

            if not velas or len(velas) < 10:
                time.sleep(1)
                continue

            current_candle_time = velas[-1]["from"]

            # =========================
            # NUEVA VELA DETECTADA
            # =========================
            if last_candle_time != current_candle_time:
                last_candle_time = current_candle_time
                trade_open = False

                print("🕯 Nueva vela detectada")

                # =========================
                # CONVERTIR A DATAFRAME
                # =========================
                import pandas as pd
                df = pd.DataFrame(velas)

                # =========================
                # ANALIZAR VELA CERRADA
                # =========================
                signal = pro_signal(df)

                if signal:
                    print(f"🔥 Señal: {signal.upper()}")
                    enviar_telegram(f"🔥 Señal detectada: {signal.upper()}")

                    # =========================
                    # VALIDAR ACTIVO
                    # =========================
                    if not activo_abierto(iq, PAIR):
                        print("⛔ Activo cerrado")
                        continue

                    # =========================
                    # CALCULAR MONTO DINÁMICO
                    # =========================
                    balance = iq.get_balance()
                    monto = balance * 0.05  # 5%

                    # =========================
                    # ESPERAR APERTURA DE VELA
                    # =========================
                    print("⏳ Esperando apertura de vela...")
                    time.sleep(1)

                    # =========================
                    # EJECUTAR
                    # =========================
                    if not trade_open:
                        ejecutado = ejecutar_operacion(iq, PAIR, signal, monto)
                        trade_open = ejecutado

            time.sleep(1)

        except Exception as e:
            print(f"❌ ERROR GENERAL: {e}")
            time.sleep(2)


# =========================
# START
# =========================
if __name__ == "__main__":
    run()
