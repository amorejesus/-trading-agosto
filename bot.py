import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle
import os

================= CONFIG =================

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

PAIR = "EURUSD-OTC"
AMOUNT = 55
EXPIRATION = 1  # minutos

==========================================

def send_telegram(message):
url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
data = {
"chat_id": TELEGRAM_CHAT_ID,
"text": message
}
try:
requests.post(url, data=data)
except:
pass

def connect_iq():
iq = IQ_Option(EMAIL, PASSWORD)
iq.connect()

if not iq.check_connect():
    print("❌ Error conectando a IQ Option")
    send_telegram("❌ Error conectando a IQ Option")
    exit()

iq.change_balance("PRACTICE")
print("✅ Conectado a IQ Option")
send_telegram("✅ Bot conectado a IQ Option")

return iq

def get_candles(iq):
candles = iq.get_candles(PAIR, 60, 50, time.time())
df = pd.DataFrame(candles)

df.rename(columns={
    "max": "max",
    "min": "min"
}, inplace=True)

return df

def wait_new_candle():
while True:
seconds = int(time.time()) % 60
if seconds == 0:
return
time.sleep(0.5)

def trade(iq, signal):
direction = "call" if signal == "call" else "put"

print(f"🚀 Ejecutando {direction.upper()}")

send_telegram(f"📊 Señal: {direction.upper()} en {PAIR}")

status, id = iq.buy(AMOUNT, PAIR, direction, EXPIRATION)

if status:
    send_telegram("⏳ Operación abierta...")
else:
    send_telegram("❌ Error al abrir operación")

def main():
iq = connect_iq()

last_signal = None

while True:
    wait_new_candle()

    df = get_candles(iq)

    signal = analyze_candle(df)

    if signal:
        trade(iq, signal)

    time.sleep(1)

if name == "main":
main()
