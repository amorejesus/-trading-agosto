import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_candle
import os


# ============================================================
# CONFIGURACIÓN
# ============================================================

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 3 pares OTC
PAIRS = "EURUSD-OTC"
AMOUNT = 3333

# Expiración de la operación
EXPIRATION = 1


# Tiempo mínimo entre operaciones del mismo par
TRADE_COOLDOWN = 120

last_trade_time = {
    pair: 0
    for pair in PAIRS
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """Enviar mensajes a Telegram."""

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
        return

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=10
        )

        if not response.ok:
            print(
                "⚠️ Error Telegram:",
                response.text
            )

    except Exception as e:
        print(
            f"⚠️ Error enviando Telegram: {e}"
        )


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():
    """Conectar con IQ Option."""

    if not EMAIL or not PASSWORD:
        raise RuntimeError(
            "Faltan IQ_EMAIL o IQ_PASSWORD"
        )

    print("🔌 Conectando a IQ Option...")

    iq = IQ_Option(
        EMAIL,
        PASSWORD
    )

    iq.connect()

    # Esperar un poco para establecer conexión
    for _ in range(10):

        if iq.check_connect():
            break

        print("⏳ Esperando conexión...")
        time.sleep(1)

    if not iq.check_connect():

        print("❌ Error conexión IQ Option")

        send_telegram(
            "❌ No se pudo conectar a IQ Option"
        )

        raise RuntimeError(
            "No se pudo conectar a IQ Option"
        )

    # Cuenta PRACTICE
    iq.change_balance("PRACTICE")

    print(
        "✅ Conectado a IQ Option"
    )

    send_telegram(
        "✅ Bot conectado a IQ Option\n"
        "📊 Modo: PRACTICE\n"
        f"💰 Monto: {AMOUNT}\n"
        f"⏱ Expiración: {EXPIRATION} minuto"
    )

    return iq


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(iq, pair, timeframe):
    """
    Obtiene 50 velas.

    timeframe:
        60  = M1
        300 = M5
    """

    try:

        candles = iq.get_candles(
            pair,
            timeframe,
            50,
            time.time()
        )

        if not candles:
            print(
                f"⚠️ Sin velas: {pair} "
                f"TF={timeframe}"
            )
            return None

        df = pd.DataFrame(candles)

        required_columns = [
            "open",
            "close",
            "max",
            "min"
        ]

        for column in required_columns:

            if column not in df.columns:

                print(
                    f"❌ Falta columna "
                    f"{column} en {pair}"
                )

                return None

        # Eliminar filas inválidas
        df = df.dropna(
            subset=required_columns
        )

        if len(df) < 10:
            print(
                f"⚠️ Pocas velas "
                f"{pair} TF={timeframe}"
            )
            return None

        return df

    except Exception as e:

        print(
            f"❌ Error velas "
            f"{pair} TF={timeframe}: {e}"
        )

        return None


# ============================================================
# ESPERAR SEGUNDO 58
# ============================================================

def wait_entry():
    """
    Espera hasta el segundo 58 de cada minuto.
    """

    while True:

        current_second = int(
            time.time()
        ) % 60

        if current_second >= 58:
            return

        time.sleep(0.10)


# ============================================================
# PROCESAR SEÑAL
# ============================================================

def process_signal(signal):
    """
    Compatible con la estrategia actual.

    strategy.py devuelve:

        ("call", "up")

    o:

        ("put", "down")

    o:

        (None, last_trend)
    """

    if signal is None:
        return None, None

    if isinstance(signal, tuple):

        if len(signal) >= 2:

            direction = signal[0]
            trend = signal[1]

            return direction, trend

        if len(signal) == 1:

            return signal[0], None

        return None, None

    if isinstance(signal, str):

        if signal in (
            "call",
            "put"
        ):
            return signal, None

    return None, None


# ============================================================
# EJECUTAR OPERACIÓN
# ============================================================

def trade(
    iq,
    pair,
    direction,
    trend
):
    """
    Ejecuta la operación después
    de validar la señal.
    """

    if direction not in (
        "call",
        "put"
    ):
        print(
            f"⛔ Dirección inválida: "
            f"{direction}"
        )
        return False

    print(
        f"🚀 {pair} → "
        f"{direction.upper()} | "
        f"M5={trend}"
    )

    send_telegram(
        f"🎯 SEÑAL CONFIRMADA\n"
        f"📊 Par: {pair}\n"
        f"➡️ Dirección: {direction.upper()}\n"
        f"📈 Estructura M5: {trend}\n"
        f"⏱ Expiración: {EXPIRATION} min"
    )

    try:

        status, order_id = iq.buy(
            AMOUNT,
            pair,
            direction,
            EXPIRATION
        )

        if status:

            print(
                f"✅ Operación abierta "
                f"{pair} | ID={order_id}"
            )

            send_telegram(
                f"✅ OPERACIÓN ABIERTA\n"
                f"📊 {pair}\n"
                f"➡️ {direction.upper()}\n"
                f"⏱ {EXPIRATION} minuto"
            )

            return True

        print(
            f"❌ IQ Option rechazó "
            f"la operación {pair}"
        )

        send_telegram(
            f"❌ IQ Option rechazó "
            f"la operación\n"
            f"📊 {pair}"
        )

        return False

    except Exception as e:

        print(
            f"❌ Error trade "
            f"{pair}: {e}"
        )

        send_telegram(
            f"❌ Error ejecutando trade\n"
            f"📊 {pair}\n"
            f"Error: {e}"
        )

        return False


# ============================================================
# ANALIZAR PAR
# ============================================================

def analyze_pair(iq, pair):
    """
    Analiza un par utilizando:

    M5 = estructura principal
    M1 = confirmación
    """

    print(
        f"\n🔎 Analizando {pair}"
    )

    # --------------------------------------------------------
    # COOLDOWN
    # --------------------------------------------------------

    elapsed = (
        time.time()
        -
        last_trade_time[pair]
    )

    if elapsed < TRADE_COOLDOWN:

        remaining = int(
            TRADE_COOLDOWN - elapsed
        )

        print(
            f"⏳ {pair} en cooldown: "
            f"{remaining}s"
        )

        return

    # --------------------------------------------------------
    # M1
    # --------------------------------------------------------

    df_m1 = get_candles(
        iq,
        pair,
        60
    )

    if df_m1 is None:

        print(
            f"⛔ No hay datos M1 "
            f"para {pair}"
        )

        return

    # --------------------------------------------------------
    # M5
    # --------------------------------------------------------

    df_m5 = get_candles(
        iq,
        pair,
        300
    )

    if df_m5 is None:

        print(
            f"⛔ No hay datos M5 "
            f"para {pair}"
        )

        return

    print(
        f"📊 Datos {pair}: "
        f"M1={len(df_m1)} "
        f"M5={len(df_m5)}"
    )

    # --------------------------------------------------------
    # ESTRATEGIA
    # --------------------------------------------------------

    signal_raw = analyze_candle(
        df_m1,
        df_m5
    )

    direction, trend = process_signal(
        signal_raw
    )

    # --------------------------------------------------------
    # SIN SEÑAL
    # --------------------------------------------------------

    if direction not in (
        "call",
        "put"
    ):

        print(
            f"⛔ {pair}: "
            f"sin señal"
        )

        return

    # --------------------------------------------------------
    # SEGURIDAD DE TENDENCIA
    # --------------------------------------------------------

    if direction == "call" and trend != "up":

        print(
            f"🚫 CALL bloqueado: "
            f"tendencia M5={trend}"
        )

        return

    if direction == "put" and trend != "down":

        print(
            f"🚫 PUT bloqueado: "
            f"tendencia M5={trend}"
        )

        return

    # --------------------------------------------------------
    # EJECUTAR
    # --------------------------------------------------------

    success = trade(
        iq,
        pair,
        direction,
        trend
    )

    if success:

        last_trade_time[pair] = (
            time.time()
        )


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():

    print(
        "===================================="
    )

    print(
        "🤖 BOT SNIPER M1 + M5"
    )

    print(
        "===================================="
    )

    iq = connect_iq()

    while True:

        try:

            # ------------------------------------------------
            # Comprobar conexión
            # ------------------------------------------------

            if not iq.check_connect():

                print(
                    "⚠️ Conexión perdida"
                )

                send_telegram(
                    "⚠️ Conexión IQ Option perdida. "
                    "Intentando reconectar..."
                )

                iq = connect_iq()

            # ------------------------------------------------
            # Esperar segundo 58
            # ------------------------------------------------

            wait_entry()

            print(
                "\n"
                "===================================="
            )

            print(
                "🎯 VENTANA SNIPER"
            )

            print(
                "===================================="
            )

            # ------------------------------------------------
            # Analizar los 3 pares
            # ------------------------------------------------

            for pair in PAIRS:

                try:

                    analyze_pair(
                        iq,
                        pair
                    )

                except Exception as e:

                    print(
                        f"❌ Error analizando "
                        f"{pair}: {e}"
                    )

                    send_telegram(
                        f"❌ Error analizando "
                        f"{pair}\n"
                        f"{e}"
                    )

                # Pequeña pausa entre pares
                time.sleep(0.3)

            # ------------------------------------------------
            # Evitar repetir el mismo segundo
            # ------------------------------------------------

            time.sleep(2)

        except KeyboardInterrupt:

            print(
                "\n🛑 Bot detenido manualmente"
            )

            send_telegram(
                "🛑 Bot detenido manualmente"
            )

            break

        except Exception as e:

            print(
                f"❌ Error general: {e}"
            )

            send_telegram(
                f"❌ Error general:\n{e}"
            )

            time.sleep(5)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
