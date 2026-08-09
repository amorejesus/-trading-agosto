import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle
import os

# ================= CONFIG =================

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 335
EXPIRATION = 1  # minutos

last_trade_time = 0
alert_sent = False

# ==========================================


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": message}
        )
    except:
        pass


def connect_iq():
    if not EMAIL:
        raise RuntimeError("❌ Falta IQ_EMAIL en Railway")
    if not PASSWORD:
        raise RuntimeError("❌ Falta IQ_PASSWORD en Railway")

    iq = IQ_Option(EMAIL, PASSWORD)
    iq.connect()

    if not iq.check_connect():
        raise RuntimeError("❌ Error conectando a IQ Option")

    iq.change_balance("PRACTICE")

    print("✅ Conectado a IQ Option")
    send_telegram("✅ Bot conectado")

    return iq


def get_candles(iq, pair, timeframe, count=100):
    try:
        candles = iq.get_candles(pair, timeframe, count, time.time())
        if not candles:
            return None

        df = pd.DataFrame(candles)

        # normalizar nombres
        df.rename(columns={
            "max": "high",
            "min": "low"
        }, inplace=True)

        return df

    except Exception as e:
        print(f"❌ Error obteniendo velas: {e}")
        return None


# ⏳ Espera hasta segundo 58 (entrada real)
def wait_execution():
    while True:
        if int(time.time()) % 60 >= 58:
            return
        time.sleep(0.2)


# ⏳ Espera zona de análisis (primeros 30s)
def in_analysis_window():
    sec = int(time.time()) % 60
    return sec <= 30


# 🚀 Ejecutar trade
def execute_trade(iq, direction):
    global last_trade_time

    print(f"🚀 EJECUTANDO {direction.upper()}")
    send_telegram(f"🚀 EJECUTANDO {direction.upper()}")

    try:
        status, _ = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

        if status:
            print("✅ Operación abierta")
            send_telegram("✅ Trade ejecutado")
            last_trade_time = time.time()
        else:
            print("❌ Error al abrir operación")
            send_telegram("❌ Error al ejecutar trade")

    except Exception as e:
        print("❌ Error trade:", e)


# ================= MAIN =================

def main():
    global alert_sent

    print("====================================")
    print("🤖 BOT SNIPER 5s + M1")
    print("====================================")

    iq = connect_iq()

    while True:
        try:
            sec = int(time.time()) % 60

            df_m1 = get_candles(iq, PAIR, 60)
            df_5s = get_candles(iq, PAIR, 5)

            if df_m1 is None or df_5s is None:
                print("⛔ Sin datos")
                time.sleep(1)
                continue

            # 🔎 ANALISIS SOLO EN PRIMEROS 30s
            if in_analysis_window():

                signal = analyze_candle(df_5s, df_m1)

                if signal and not alert_sent:
                    print(f"📢 ALERTA: {signal.upper()}")
                    send_telegram(f"📢 ALERTA: {signal.upper()} (esperando cierre M1)")
                    alert_sent = True

            # 🎯 EJECUCIÓN EN SEGUNDO 58
            if sec >= 58:

                signal = analyze_candle(df_5s, df_m1)

                if signal:
                    execute_trade(iq, signal)
                else:
                    print("⛔ Sin señal")

                alert_sent = False  # reset ciclo

            time.sleep(0.5)

        except Exception as e:
            print("❌ Error general:", e)
            send_telegram(f"❌ Error: {e}")
            time.sleep(2)


# ========================================

if __name__ == "__main__":
    main()
