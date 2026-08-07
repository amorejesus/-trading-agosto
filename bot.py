import os
import time
import requests
import pandas as pd
from iqoptionapi.stable_api import IQ_Option

from strategy import analyze_candle


# ============================================================
# CONFIGURACIÓN
# ============================================================

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# ÚNICO PAR AUTORIZADO
# ============================================================

PAIRS = [
    "EURUSD-OTC"
]


# ============================================================
# CONFIGURACIÓN DE OPERACIÓN
# ============================================================

AMOUNT = 3333

# Expiración en minutos
EXPIRATION = 1

# Tiempo mínimo entre operaciones
TRADE_COOLDOWN = 120


last_trade_time = {
    "EURUSD-OTC": 0
}


# ============================================================
# VALIDAR CONFIGURACIÓN DE PARES
# ============================================================

def validate_pairs():

    print("")
    print("====================================")
    print("🔎 VALIDANDO PARES")
    print("====================================")

    if not isinstance(PAIRS, list):

        raise RuntimeError(
            "PAIRS debe ser una lista."
        )

    if PAIRS != ["EURUSD-OTC"]:

        raise RuntimeError(
            "Configuración inválida. "
            "Este bot solo puede operar EURUSD-OTC."
        )

    for pair in PAIRS:

        if not isinstance(pair, str):

            raise RuntimeError(
                f"Par inválido: {pair}"
            )

        pair = pair.strip()

        if pair != "EURUSD-OTC":

            raise RuntimeError(
                f"Par no autorizado: {pair}"
            )

        print(
            f"✅ {pair}"
        )

    print("====================================")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print(
            "⚠️ Telegram no configurado"
        )

        return False

    try:

        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },
            timeout=10
        )

        if response.ok:

            return True

        print(
            f"⚠️ Error Telegram: "
            f"{response.status_code}"
        )

        return False

    except Exception as e:

        print(
            f"⚠️ Error Telegram: {e}"
        )

        return False


# ============================================================
# VARIABLES DE ENTORNO
# ============================================================

def check_environment():

    global EMAIL
    global PASSWORD
    global TELEGRAM_TOKEN
    global TELEGRAM_CHAT_ID

    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    TELEGRAM_TOKEN = os.getenv(
        "TELEGRAM_TOKEN"
    )

    TELEGRAM_CHAT_ID = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    print("")
    print("====================================")
    print("🔐 VARIABLES DE ENTORNO")
    print("====================================")

    print(
        "IQ_EMAIL: "
        + (
            "✅ configurado"
            if EMAIL
            else "❌ AUSENTE"
        )
    )

    print(
        "IQ_PASSWORD: "
        + (
            "✅ configurado"
            if PASSWORD
            else "❌ AUSENTE"
        )
    )

    print(
        "TELEGRAM_TOKEN: "
        + (
            "✅ configurado"
            if TELEGRAM_TOKEN
            else "⚠️ AUSENTE"
        )
    )

    print(
        "TELEGRAM_CHAT_ID: "
        + (
            "✅ configurado"
            if TELEGRAM_CHAT_ID
            else "⚠️ AUSENTE"
        )
    )

    print("====================================")

    if not EMAIL or not PASSWORD:

        return False

    return True


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():

    global EMAIL
    global PASSWORD

    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    if not EMAIL or not PASSWORD:

        send_telegram(
            "❌ BOT DETENIDO\n\n"
            "Faltan IQ_EMAIL o IQ_PASSWORD "
            "en Railway."
        )

        raise RuntimeError(
            "Faltan IQ_EMAIL o IQ_PASSWORD"
        )

    print("")
    print("====================================")
    print("🔌 CONECTANDO A IQ OPTION")
    print("====================================")

    try:

        iq = IQ_Option(
            EMAIL,
            PASSWORD
        )

        iq.connect()

    except Exception as e:

        print(
            f"❌ Error creando conexión: {e}"
        )

        raise

    connected = False

    for attempt in range(10):

        try:

            if iq.check_connect():

                connected = True
                break

        except Exception:

            pass

        print(
            f"⏳ Esperando conexión "
            f"{attempt + 1}/10..."
        )

        time.sleep(1)

    if not connected:

        print(
            "❌ No se pudo conectar "
            "a IQ Option"
        )

        send_telegram(
            "❌ No se pudo conectar "
            "a IQ Option."
        )

        raise RuntimeError(
            "No se pudo conectar a IQ Option"
        )

    # ========================================================
    # CUENTA PRACTICE
    # ========================================================

    try:

        iq.change_balance(
            "PRACTICE"
        )

        print(
            "💰 Cuenta: PRACTICE"
        )

    except Exception as e:

        print(
            f"⚠️ Error cambiando cuenta: {e}"
        )

    print("")
    print("====================================")
    print("✅ CONECTADO A IQ OPTION")
    print("====================================")

    send_telegram(
        "✅ BOT CONECTADO A IQ OPTION\n\n"
        "📊 Par: EURUSD-OTC\n"
        "📈 Marcos: M5 + M1\n"
        "🎯 Modo: SNIPER\n"
        f"💰 Monto: {AMOUNT}\n"
        f"⏱ Expiración: {EXPIRATION} minuto\n"
        "💼 Cuenta: PRACTICE"
    )

    return iq


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(
    iq,
    pair,
    timeframe
):

    # Seguridad adicional
    if pair != "EURUSD-OTC":

        print(
            f"⛔ Activo bloqueado: {pair}"
        )

        return None

    try:

        candles = iq.get_candles(
            pair,
            timeframe,
            50,
            time.time()
        )

        if not candles:

            print(
                f"⚠️ Sin velas "
                f"{pair} TF={timeframe}"
            )

            return None

        df = pd.DataFrame(
            candles
        )

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

        df = df.dropna(
            subset=required_columns
        )

        if len(df) < 20:

            print(
                f"⚠️ Datos insuficientes "
                f"{pair} TF={timeframe}: "
                f"{len(df)} velas"
            )

            return None

        return df

    except Exception as e:

        print(
            f"❌ Error obteniendo velas "
            f"{pair} TF={timeframe}: {e}"
        )

        return None


# ============================================================
# ESPERAR SEGUNDO 58
# ============================================================

def wait_entry():

    print(
        "⏳ Esperando ventana sniper..."
    )

    while True:

        second = int(
            time.time()
        ) % 60

        if second >= 58:

            print(
                f"🎯 Ventana sniper "
                f"segundo {second}"
            )

            return

        time.sleep(0.10)


# ============================================================
# PROCESAR SEÑAL
# ============================================================

def process_signal(signal):

    if signal is None:

        return None, None

    if isinstance(
        signal,
        tuple
    ):

        if len(signal) >= 2:

            return (
                signal[0],
                signal[1]
            )

        if len(signal) == 1:

            return (
                signal[0],
                None
            )

        return None, None

    if isinstance(
        signal,
        str
    ):

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

    # Seguridad absoluta
    if pair != "EURUSD-OTC":

        print(
            f"⛔ OPERACIÓN BLOQUEADA: "
            f"{pair}"
        )

        return False

    if direction not in (
        "call",
        "put"
    ):

        print(
            f"⛔ Dirección inválida: "
            f"{direction}"
        )

        return False

    print("")
    print("====================================")
    print("🚀 SEÑAL CONFIRMADA")
    print("====================================")
    print(
        f"📊 Par: {pair}"
    )
    print(
        f"➡️ Dirección: "
        f"{direction.upper()}"
    )
    print(
        f"📈 Tendencia M5: "
        f"{trend}"
    )
    print(
        f"⏱ Expiración: "
        f"{EXPIRATION} minuto"
    )
    print("====================================")

    send_telegram(
        "🎯 SEÑAL CONFIRMADA\n\n"
        f"📊 {pair}\n"
        f"➡️ {direction.upper()}\n"
        f"📈 M5: {trend}\n"
        f"⏱ Expiración: {EXPIRATION} minuto"
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
                "✅ OPERACIÓN ABIERTA"
            )

            print(
                f"🆔 ID: {order_id}"
            )

            send_telegram(
                "✅ OPERACIÓN ABIERTA\n\n"
                f"📊 {pair}\n"
                f"➡️ {direction.upper()}\n"
                f"📈 M5: {trend}\n"
                f"⏱ {EXPIRATION} minuto"
            )

            return True

        print(
            "❌ IQ Option rechazó "
            "la operación"
        )

        send_telegram(
            "❌ OPERACIÓN RECHAZADA\n\n"
            f"📊 {pair}"
        )

        return False

    except Exception as e:

        print(
            f"❌ Error ejecutando "
            f"trade: {e}"
        )

        send_telegram(
            "❌ ERROR EJECUTANDO TRADE\n\n"
            f"📊 {pair}\n"
            f"Error: {e}"
        )

        return False


# ============================================================
# ANALIZAR EURUSD-OTC
# ============================================================

def analyze_pair(
    iq,
    pair
):

    print("")
    print("------------------------------------")
    print(
        f"🔎 ANALIZANDO {pair}"
    )
    print("------------------------------------")

    # Seguridad principal
    if pair != "EURUSD-OTC":

        print(
            f"⛔ Par rechazado: {pair}"
        )

        return

    # ========================================================
    # COOLDOWN
    # ========================================================

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
            f"⏳ EURUSD-OTC: "
            f"cooldown {remaining}s"
        )

        return

    # ========================================================
    # M1
    # ========================================================

    df_m1 = get_candles(
        iq,
        "EURUSD-OTC",
        60
    )

    if df_m1 is None:

        print(
            "⛔ EURUSD-OTC: "
            "sin datos M1"
        )

        return

    # ========================================================
    # M5
    # ========================================================

    df_m5 = get_candles(
        iq,
        "EURUSD-OTC",
        300
    )

    if df_m5 is None:

        print(
            "⛔ EURUSD-OTC: "
            "sin datos M5"
        )

        return

    print(
        f"📊 EURUSD-OTC: "
        f"M1={len(df_m1)} "
        f"M5={len(df_m5)}"
    )

    # ========================================================
    # ANALIZAR ESTRATEGIA
    # ========================================================

    try:

        signal_raw = analyze_candle(
            df_m1,
            df_m5
        )

    except Exception as e:

        print(
            f"❌ Error strategy: {e}"
        )

        send_telegram(
            "❌ ERROR STRATEGY\n\n"
            f"EURUSD-OTC\n"
            f"{e}"
        )

        return

    # ========================================================
    # PROCESAR SEÑAL
    # ========================================================

    direction, trend = process_signal(
        signal_raw
    )

    # ========================================================
    # SIN SEÑAL
    # ========================================================

    if direction not in (
        "call",
        "put"
    ):

        print(
            "⛔ EURUSD-OTC: "
            "sin señal"
        )

        return

    # ========================================================
    # CONFIRMACIÓN M5
    # ========================================================

    if direction == "call":

        if trend != "up":

            print(
                f"🚫 CALL bloqueado. "
                f"Tendencia M5={trend}"
            )

            return

    if direction == "put":

        if trend != "down":

            print(
                f"🚫 PUT bloqueado. "
                f"Tendencia M5={trend}"
            )

            return

    # ========================================================
    # EJECUTAR
    # ========================================================

    success = trade(
        iq,
        "EURUSD-OTC",
        direction,
        trend
    )

    if success:

        last_trade_time[
            "EURUSD-OTC"
        ] = time.time()


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("====================================")
    print("🤖 BOT SNIPER M1 + M5")
    print("====================================")

    # ========================================================
    # VALIDAR PAR
    # ========================================================

    validate_pairs()

    print("")
    print(
        "📊 ÚNICO PAR AUTORIZADO:"
    )
    print(
        "   ✅ EURUSD-OTC"
    )

    print("")
    print(
        f"💰 Monto: {AMOUNT}"
    )

    print(
        f"⏱ Expiración: "
        f"{EXPIRATION} minuto"
    )

    print(
        "📈 Marcos: M5 + M1"
    )

    print(
        "🎯 Entrada sniper: "
        "segundo 58"
    )

    print("====================================")

    # ========================================================
    # VARIABLES
    # ========================================================

    if not check_environment():

        print("")
        print(
            "🛑 BOT DETENIDO"
        )

        print(
            "Configura IQ_EMAIL "
            "e IQ_PASSWORD en Railway."
        )

        return

    # ========================================================
    # CONEXIÓN
    # ========================================================

    try:

        iq = connect_iq()

    except Exception as e:

        print("")
        print(
            "🛑 No se pudo iniciar el bot."
        )

        print(
            f"Error: {e}"
        )

        return

    # ========================================================
    # LOOP PRINCIPAL
    # ========================================================

    while True:

        try:

            # ==================================================
            # COMPROBAR CONEXIÓN
            # ==================================================

            try:

                connected = (
                    iq.check_connect()
                )

            except Exception:

                connected = False

            if not connected:

                print(
                    "⚠️ Conexión perdida."
                )

                send_telegram(
                    "⚠️ CONEXIÓN PERDIDA\n\n"
                    "Intentando reconectar..."
                )

                try:

                    iq = connect_iq()

                except Exception as e:

                    print(
                        f"❌ Reconexión fallida: "
                        f"{e}"
                    )

                    time.sleep(10)

                    continue

            # ==================================================
            # ESPERAR SEGUNDO 58
            # ==================================================

            wait_entry()

            print("")
            print("====================================")
            print("🎯 INICIANDO ANÁLISIS")
            print("====================================")
            print(
                "📊 PAR: EURUSD-OTC"
            )
            print(
                "📈 ESTRUCTURA: M5 + M1"
            )
            print("====================================")

            # ==================================================
            # SOLO EURUSD-OTC
            # ==================================================

            analyze_pair(
                iq,
                "EURUSD-OTC"
            )

            print("")
            print(
                "✅ Ciclo de análisis terminado."
            )

            time.sleep(2)

        # ======================================================
        # CTRL+C
        # ======================================================

        except KeyboardInterrupt:

            print("")
            print(
                "🛑 Bot detenido manualmente."
            )

            send_telegram(
                "🛑 Bot detenido manualmente."
            )

            break

        # ======================================================
        # ERROR GENERAL
        # ======================================================

        except Exception as e:

            print(
                f"❌ ERROR GENERAL: {e}"
            )

            send_telegram(
                f"❌ ERROR GENERAL\n{e}"
            )

            time.sleep(5)


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":

    main()
