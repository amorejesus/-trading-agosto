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

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID"
)


# ============================================================
# ÚNICO PAR
# ============================================================

PAIR = "EURUSD-OTC"


# ============================================================
# OPERACIÓN
# ============================================================

AMOUNT = 333

EXPIRATION = 1

# Tiempo mínimo entre operaciones
TRADE_COOLDOWN = 120

# Tiempo máximo de un ciclo de búsqueda
MAX_SEARCH_TIME = 30 * 60


last_trade_time = 0


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TELEGRAM_TOKEN:
        return

    if not TELEGRAM_CHAT_ID:
        return

    try:

        requests.post(
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendMessage",

            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message
            },

            timeout=10
        )

    except Exception as e:

        print(
            f"⚠️ Telegram: {e}"
        )


# ============================================================
# VARIABLES DE ENTORNO
# ============================================================

def validate_environment():

    global EMAIL
    global PASSWORD

    global TELEGRAM_TOKEN
    global TELEGRAM_CHAT_ID

    EMAIL = os.getenv(
        "IQ_EMAIL"
    )

    PASSWORD = os.getenv(
        "IQ_PASSWORD"
    )

    TELEGRAM_TOKEN = os.getenv(
        "TELEGRAM_TOKEN"
    )

    TELEGRAM_CHAT_ID = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    print("")
    print(
        "========================================"
    )

    print(
        "IQ_EMAIL: "
        +
        (
            "✅ OK"
            if EMAIL
            else "❌ FALTA"
        )
    )

    print(
        "IQ_PASSWORD: "
        +
        (
            "✅ OK"
            if PASSWORD
            else "❌ FALTA"
        )
    )

    print(
        "TELEGRAM_TOKEN: "
        +
        (
            "✅ OK"
            if TELEGRAM_TOKEN
            else "⚠️ FALTA"
        )
    )

    print(
        "TELEGRAM_CHAT_ID: "
        +
        (
            "✅ OK"
            if TELEGRAM_CHAT_ID
            else "⚠️ FALTA"
        )
    )

    print(
        "========================================"
    )

    if not EMAIL:
        raise RuntimeError(
            "Falta IQ_EMAIL"
        )

    if not PASSWORD:
        raise RuntimeError(
            "Falta IQ_PASSWORD"
        )


# ============================================================
# CONEXIÓN
# ============================================================

def connect_iq():

    print("")
    print(
        "🔌 Conectando a IQ Option..."
    )

    iq = IQ_Option(
        EMAIL,
        PASSWORD
    )

    iq.connect()

    for attempt in range(10):

        try:

            if iq.check_connect():

                print(
                    "✅ IQ Option conectado"
                )

                try:

                    iq.change_balance(
                        "PRACTICE"
                    )

                    print(
                        "💰 Cuenta PRACTICE"
                    )

                except Exception as e:

                    print(
                        f"⚠️ Balance: {e}"
                    )

                send_telegram(
                    "🤖 BOT INICIADO\n\n"
                    "📊 EURUSD-OTC\n"
                    "📈 M5 + M1\n"
                    "🎯 Continuidad + fuerza\n"
                    "💼 PRACTICE"
                )

                return iq

        except Exception:
            pass

        print(
            f"⏳ Conectando "
            f"{attempt + 1}/10..."
        )

        time.sleep(2)

    raise RuntimeError(
        "No se pudo conectar a IQ Option"
    )


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(
    iq,
    timeframe
):

    try:

        candles = iq.get_candles(
            PAIR,
            timeframe,
            50,
            time.time()
        )

        if not candles:

            print(
                f"⚠️ Sin velas "
                f"{PAIR} TF={timeframe}"
            )

            return None

        df = pd.DataFrame(
            candles
        )

        required = [
            "open",
            "close",
            "max",
            "min"
        ]

        for column in required:

            if column not in df.columns:

                print(
                    f"❌ Falta {column}"
                )

                return None

        df = df.dropna(
            subset=required
        )

        if len(df) < 20:

            print(
                f"⚠️ Pocas velas "
                f"TF={timeframe}: "
                f"{len(df)}"
            )

            return None

        return df

    except Exception as e:

        print(
            f"❌ Error velas "
            f"TF={timeframe}: {e}"
        )

        return None


# ============================================================
# ESPERAR SIGUIENTE VENTANA
# ============================================================

def wait_sniper_window():

    while True:

        second = (
            int(time.time())
            % 60
        )

        if second >= 58:

            print(
                f"🎯 Ventana sniper "
                f"segundo {second}"
            )

            return

        time.sleep(0.10)


# ============================================================
# ESPERAR SIGUIENTE MINUTO
# ============================================================

def wait_next_minute():

    current_second = (
        int(time.time())
        % 60
    )

    remaining = (
        60 -
        current_second
    )

    if remaining > 0:

        time.sleep(
            min(
                remaining,
                5
            )
        )


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

        direction = (
            signal[0]
            if len(signal) >= 1
            else None
        )

        trend = (
            signal[1]
            if len(signal) >= 2
            else None
        )

        return direction, trend

    if signal in (
        "call",
        "put"
    ):

        return signal, None

    return None, None


# ============================================================
# EJECUTAR TRADE
# ============================================================

def execute_trade(
    iq,
    direction,
    trend
):

    global last_trade_time

    if PAIR != "EURUSD-OTC":

        print(
            "⛔ OPERACIÓN BLOQUEADA"
        )

        return False

    if direction not in (
        "call",
        "put"
    ):

        return False

    # --------------------------------------------------------
    # COOL DOWN
    # --------------------------------------------------------

    elapsed = (
        time.time()
        -
        last_trade_time
    )

    if elapsed < TRADE_COOLDOWN:

        remaining = int(
            TRADE_COOLDOWN -
            elapsed
        )

        print(
            f"⏳ Cooldown "
            f"{remaining}s"
        )

        return False

    print("")
    print(
        "========================================"
    )

    print(
        "🚀 EJECUTANDO OPERACIÓN"
    )

    print(
        f"📊 {PAIR}"
    )

    print(
        f"➡️ {direction.upper()}"
    )

    print(
        f"📈 M5: {trend}"
    )

    print(
        f"💰 Monto: {AMOUNT}"
    )

    print(
        f"⏱ Expiración: "
        f"{EXPIRATION} minuto"
    )

    print(
        "========================================"
    )

    send_telegram(
        "🎯 SEÑAL SNIPER\n\n"
        f"📊 {PAIR}\n"
        f"➡️ {direction.upper()}\n"
        f"📈 M5: {trend}\n"
        f"💰 {AMOUNT}\n"
        f"⏱ {EXPIRATION} minuto"
    )

    try:

        status, order_id = iq.buy(
            AMOUNT,
            PAIR,
            direction,
            EXPIRATION
        )

        if status:

            last_trade_time = (
                time.time()
            )

            print(
                "✅ OPERACIÓN ABIERTA"
            )

            print(
                f"🆔 {order_id}"
            )

            send_telegram(
                "✅ OPERACIÓN ABIERTA\n\n"
                f"📊 {PAIR}\n"
                f"➡️ {direction.upper()}\n"
                f"🆔 {order_id}"
            )

            return True

        print(
            "❌ IQ Option rechazó "
            "la operación"
        )

        return False

    except Exception as e:

        print(
            f"❌ Error trade: {e}"
        )

        send_telegram(
            "❌ ERROR TRADE\n\n"
            f"{PAIR}\n"
            f"{e}"
        )

        return False


# ============================================================
# ANALIZAR EURUSD
# ============================================================

def analyze_market(iq):

    print("")
    print(
        "----------------------------------------"
    )

    print(
        "🔎 ANALIZANDO EURUSD-OTC"
    )

    print(
        "----------------------------------------"
    )

    # ========================================================
    # M1
    # ========================================================

    df_m1 = get_candles(
        iq,
        60
    )

    if df_m1 is None:

        print(
            "⛔ EURUSD-OTC: "
            "sin datos M1"
        )

        return False

    # ========================================================
    # M5
    # ========================================================

    df_m5 = get_candles(
        iq,
        300
    )

    if df_m5 is None:

        print(
            "⛔ EURUSD-OTC: "
            "sin datos M5"
        )

        return False

    print(
        f"📊 EURUSD-OTC: "
        f"M1={len(df_m1)} "
        f"M5={len(df_m5)}"
    )

    # ========================================================
    # ESTRATEGIA
    # ========================================================

    try:

        signal = analyze_candle(
            df_m1,
            df_m5
        )

    except Exception as e:

        print(
            f"❌ Error strategy: "
            f"{e}"
        )

        send_telegram(
            f"❌ ERROR STRATEGY\n{e}"
        )

        return False

    direction, trend = (
        process_signal(signal)
    )

    if direction not in (
        "call",
        "put"
    ):

        print(
            "⛔ EURUSD-OTC: "
            "sin señal"
        )

        return False

    # ========================================================
    # EJECUTAR
    # ========================================================

    return execute_trade(
        iq,
        direction,
        trend
    )


# ============================================================
# CICLO DE BÚSQUEDA DE 30 MINUTOS
# ============================================================

def search_for_entry(iq):

    start_time = time.time()

    print("")
    print(
        "========================================"
    )

    print(
        "🔍 INICIANDO BÚSQUEDA DE ENTRADA"
    )

    print(
        "📊 EURUSD-OTC"
    )

    print(
        "⏱ Tiempo máximo: 30 minutos"
    )

    print(
        "========================================"
    )

    while True:

        elapsed = (
            time.time()
            -
            start_time
        )

        # ====================================================
        # LÍMITE DE 30 MINUTOS
        # ====================================================

        if elapsed >= MAX_SEARCH_TIME:

            print("")
            print(
                "⏰ Se cumplieron "
                "30 minutos."
            )

            print(
                "🔄 Reiniciando búsqueda."
            )

            return False

        # ====================================================
        # VENTANA SNIPER
        # ====================================================

        wait_sniper_window()

        # ====================================================
        # ANALIZAR
        # ====================================================

        success = analyze_market(
            iq
        )

        # ====================================================
        # SI OPERÓ
        # ====================================================

        if success:

            print("")
            print(
                "✅ ENTRADA EJECUTADA"
            )

            return True

        # ====================================================
        # SIGUIENTE MINUTO
        # ====================================================

        print("")
        print(
            "⏳ Sin entrada."
        )

        remaining = int(
            MAX_SEARCH_TIME -
            elapsed
        )

        print(
            f"⏱ Tiempo restante "
            f"del ciclo: "
            f"{max(remaining, 0)}s"
        )

        wait_next_minute()


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print(
        "========================================"
    )

    print(
        "🤖 BOT SNIPER M1 + M5"
    )

    print(
        "========================================"
    )

    print(
        "📊 PAR: EURUSD-OTC"
    )

    print(
        "📈 ESTRUCTURA: M5 + M1"
    )

    print(
        "🎯 ESTRATEGIA: "
        "CONTINUIDAD + FUERZA"
    )

    print(
        "⏱ EXPIRACIÓN: 1 MINUTO"
    )

    print(
        "🎯 ENTRADA: VELA M1 CERRADA"
    )

    print(
        "⏰ BÚSQUEDA: MÁXIMO 30 MINUTOS"
    )

    print(
        "========================================"
    )

    # ========================================================
    # VARIABLES
    # ========================================================

    try:

        validate_environment()

    except Exception as e:

        print(
            f"🛑 {e}"
        )

        return

    # ========================================================
    # CONECTAR
    # ========================================================

    try:

        iq = connect_iq()

    except Exception as e:

        print(
            f"🛑 Error conexión: {e}"
        )

        return

    # ========================================================
    # LOOP
    # ========================================================

    while True:

        try:

            # ------------------------------------------------
            # COMPROBAR CONEXIÓN
            # ------------------------------------------------

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

                try:

                    iq = connect_iq()

                except Exception as e:

                    print(
                        f"❌ Reconexión: {e}"
                    )

                    time.sleep(10)

                    continue

            # ------------------------------------------------
            # BÚSQUEDA
            # ------------------------------------------------

            search_for_entry(
                iq
            )

            print("")
            print(
                "========================================"
            )

            print(
                "✅ CICLO DE BÚSQUEDA TERMINADO"
            )

            print(
                "========================================"
            )

            # Pequeña pausa antes
            # del siguiente ciclo

            time.sleep(2)

        except KeyboardInterrupt:

            print("")
            print(
                "🛑 BOT DETENIDO"
            )

            send_telegram(
                "🛑 BOT DETENIDO MANUALMENTE"
            )

            break

        except Exception as e:

            print("")
            print(
                f"❌ ERROR GENERAL: {e}"
            )

            send_telegram(
                f"❌ ERROR GENERAL\n{e}"
            )

            time.sleep(5)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
