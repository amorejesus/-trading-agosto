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

PAIRS = "EURUSD-OTC"
AMOUNT = 3333

# Expiración en minutos
EXPIRATION = 1

# Tiempo mínimo entre operaciones del mismo par
TRADE_COOLDOWN = 120

# Control de operaciones
last_trade_time = {
    pair: 0
    for pair in PAIRS
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """Enviar mensaje a Telegram."""

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram no configurado")
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
            f"⚠️ Error enviando Telegram: {e}"
        )

        return False


# ============================================================
# COMPROBAR VARIABLES
# ============================================================

def check_environment():
    """
    Comprueba las variables necesarias sin mostrar
    ninguna contraseña o token.
    """

    print("")
    print("🔐 COMPROBANDO VARIABLES DE ENTORNO")
    print("------------------------------------")

    email_ok = bool(EMAIL)
    password_ok = bool(PASSWORD)
    telegram_token_ok = bool(TELEGRAM_TOKEN)
    telegram_chat_ok = bool(TELEGRAM_CHAT_ID)

    print(
        f"IQ_EMAIL: "
        f"{'✅ configurado' if email_ok else '❌ AUSENTE'}"
    )

    print(
        f"IQ_PASSWORD: "
        f"{'✅ configurado' if password_ok else '❌ AUSENTE'}"
    )

    print(
        f"TELEGRAM_TOKEN: "
        f"{'✅ configurado' if telegram_token_ok else '⚠️ AUSENTE'}"
    )

    print(
        f"TELEGRAM_CHAT_ID: "
        f"{'✅ configurado' if telegram_chat_ok else '⚠️ AUSENTE'}"
    )

    print("------------------------------------")

    if not email_ok or not password_ok:

        print(
            "❌ Faltan las credenciales de IQ Option."
        )

        print(
            "Configura IQ_EMAIL e IQ_PASSWORD "
            "en las Variables del servicio worker de Railway."
        )

        return False

    return True


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():
    """Conectar a IQ Option."""

    global EMAIL
    global PASSWORD

    # Volver a leer variables por seguridad
    EMAIL = os.getenv("IQ_EMAIL")
    PASSWORD = os.getenv("IQ_PASSWORD")

    if not check_environment():

        send_telegram(
            "❌ BOT DETENIDO\n\n"
            "Faltan IQ_EMAIL o IQ_PASSWORD "
            "en las variables de Railway."
        )

        raise RuntimeError(
            "Faltan IQ_EMAIL o IQ_PASSWORD"
        )

    print("")
    print("🔌 Conectando a IQ Option...")

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

        send_telegram(
            f"❌ Error conectando a IQ Option:\n{e}"
        )

        raise

    # --------------------------------------------------------
    # ESPERAR CONEXIÓN
    # --------------------------------------------------------

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
            f"({attempt + 1}/10)..."
        )

        time.sleep(1)

    if not connected:

        print(
            "❌ No se pudo conectar a IQ Option"
        )

        send_telegram(
            "❌ No se pudo conectar a IQ Option."
        )

        raise RuntimeError(
            "No se pudo conectar a IQ Option"
        )

    # --------------------------------------------------------
    # CUENTA PRACTICE
    # --------------------------------------------------------

    try:

        iq.change_balance("PRACTICE")

        print(
            "💰 Cuenta seleccionada: PRACTICE"
        )

    except Exception as e:

        print(
            f"⚠️ No se pudo cambiar a PRACTICE: {e}"
        )

    print("")
    print("====================================")
    print("✅ CONECTADO A IQ OPTION")
    print("====================================")

    send_telegram(
        "✅ BOT CONECTADO A IQ OPTION\n\n"
        "📊 Cuenta: PRACTICE\n"
        f"💰 Monto: {AMOUNT}\n"
        f"⏱ Expiración: {EXPIRATION} minuto\n"
        "📈 Marcos: M5 + M1\n"
        "🎯 Modo: SNIPER"
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
                f"⚠️ Sin velas "
                f"{pair} TF={timeframe}"
            )

            return None

        df = pd.DataFrame(candles)

        required = [
            "open",
            "close",
            "max",
            "min"
        ]

        for column in required:

            if column not in df.columns:

                print(
                    f"❌ Falta columna "
                    f"{column} en {pair}"
                )

                return None

        df = df.dropna(
            subset=required
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
    """
    Espera la ventana de entrada alrededor
    del segundo 58.
    """

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
    """
    Compatible con strategy.py.

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
    """Ejecutar operación."""

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
    print("🚀 SEÑAL DE ENTRADA")
    print("====================================")
    print(f"📊 Par: {pair}")
    print(f"➡️ Dirección: {direction.upper()}")
    print(f"📈 Tendencia M5: {trend}")
    print(f"⏱ Expiración: {EXPIRATION} minuto")
    print("====================================")

    send_telegram(
        "🎯 SEÑAL CONFIRMADA\n\n"
        f"📊 Par: {pair}\n"
        f"➡️ Dirección: {direction.upper()}\n"
        f"📈 Tendencia M5: {trend}\n"
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
                f"✅ Operación abierta "
                f"{pair}"
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
            f"❌ IQ Option rechazó "
            f"la operación {pair}"
        )

        send_telegram(
            "❌ OPERACIÓN RECHAZADA\n\n"
            f"📊 {pair}"
        )

        return False

    except Exception as e:

        print(
            f"❌ Error ejecutando "
            f"trade {pair}: {e}"
        )

        send_telegram(
            "❌ ERROR EJECUTANDO TRADE\n\n"
            f"📊 {pair}\n"
            f"Error: {e}"
        )

        return False


# ============================================================
# ANALIZAR UN PAR
# ============================================================

def analyze_pair(iq, pair):
    """
    Analiza:

        M5 = estructura principal
        M1 = confirmación

    La estrategia se encarga de:
        - tendencia
        - pullback
        - continuidad
        - fuerza
        - lateralidad
        - resistencia
        - soporte
        - score
    """

    print("")
    print("------------------------------------")
    print(f"🔎 ANALIZANDO {pair}")
    print("------------------------------------")

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
            f"⏳ {pair}: cooldown "
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
            f"⛔ {pair}: sin datos M1"
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
            f"⛔ {pair}: sin datos M5"
        )

        return

    print(
        f"📊 {pair}: "
        f"M1={len(df_m1)} "
        f"M5={len(df_m5)}"
    )

    # --------------------------------------------------------
    # ANALIZAR ESTRATEGIA
    # --------------------------------------------------------

    try:

        signal_raw = analyze_candle(
            df_m1,
            df_m5
        )

    except Exception as e:

        print(
            f"❌ Error strategy "
            f"{pair}: {e}"
        )

        send_telegram(
            f"❌ Error strategy\n"
            f"📊 {pair}\n"
            f"{e}"
        )

        return

    # --------------------------------------------------------
    # PROCESAR RESULTADO
    # --------------------------------------------------------

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
            f"sin señal válida"
        )

        return

    # --------------------------------------------------------
    # CONFIRMACIÓN DE TENDENCIA
    # --------------------------------------------------------

    if direction == "call":

        if trend != "up":

            print(
                f"🚫 CALL bloqueado "
                f"por tendencia M5={trend}"
            )

            return

    if direction == "put":

        if trend != "down":

            print(
                f"🚫 PUT bloqueado "
                f"por tendencia M5={trend}"
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
# MAIN
# ============================================================

def main():

    print("")
    print("====================================")
    print("🤖 BOT SNIPER M1 + M5")
    print("====================================")

    print(
        f"📊 Pares: {', '.join(PAIRS)}"
    )

    print(
        f"💰 Monto: {AMOUNT}"
    )

    print(
        f"⏱ Expiración: {EXPIRATION} minuto"
    )

    print(
        "📈 Estructura: M5 + M1"
    )

    print(
        "🎯 Entrada: segundo 58"
    )

    print(
        "===================================="
    )

    # --------------------------------------------------------
    # COMPROBAR VARIABLES
    # --------------------------------------------------------

    if not check_environment():

        print("")
        print(
            "🛑 BOT DETENIDO"
        )

        print(
            "Configura las variables "
            "en Railway."
        )

        return

    # --------------------------------------------------------
    # CONECTAR
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # LOOP
    # --------------------------------------------------------

    while True:

        try:

            # ------------------------------------------------
            # VERIFICAR CONEXIÓN
            # ------------------------------------------------

            if not iq.check_connect():

                print(
                    "⚠️ Conexión perdida."
                )

                send_telegram(
                    "⚠️ Conexión IQ Option perdida.\n"
                    "Intentando reconectar..."
                )

                try:

                    iq = connect_iq()

                except Exception as e:

                    print(
                        f"❌ Reconexión fallida: {e}"
                    )

                    time.sleep(10)

                    continue

            # ------------------------------------------------
            # ESPERAR VENTANA SNIPER
            # ------------------------------------------------

            wait_entry()

            print("")
            print("====================================")
            print("🎯 INICIANDO ANÁLISIS SNIPER")
            print("====================================")

            # ------------------------------------------------
            # ANALIZAR PARES
            # ------------------------------------------------

            for pair in PAIRS:

                try:

                    analyze_pair(
                        iq,
                        pair
                    )

                except Exception as e:

                    print(
                        f"❌ Error en {pair}: {e}"
                    )

                    send_telegram(
                        f"❌ Error en {pair}\n"
                        f"{e}"
                    )

                time.sleep(0.3)

            print("")
            print(
                "✅ Ciclo de análisis terminado."
            )

            # Evita volver a entrar
            # inmediatamente en el mismo minuto.
            time.sleep(2)

        except KeyboardInterrupt:

            print("")
            print(
                "🛑 Bot detenido manualmente."
            )

            send_telegram(
                "🛑 Bot detenido manualmente."
            )

            break

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
