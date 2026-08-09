import os
import time
import requests
from iqoptionapi.stable_api import IQ_Option
from strategy import check_pattern


# ============================================================
# CONFIG
# ============================================================

PAIR = "EURUSD-OTC"

AMOUNT = 10

EXPIRATION = 1


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(msg):

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:

        print("⚠️ Telegram no configurado")

        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": msg
            },
            timeout=10
        )

    except Exception as e:

        print(f"⚠️ Error Telegram: {e}")


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():

    email = os.getenv("IQ_EMAIL")
    password = os.getenv("IQ_PASSWORD")

    if not email or not password:

        print(
            "❌ ERROR: Faltan "
            "IQ_EMAIL o IQ_PASSWORD"
        )

        return None

    try:

        print("🔌 Conectando a IQ Option...")

        iq = IQ_Option(
            email,
            password
        )

        iq.connect()

        # Esperar unos segundos para establecer conexión
        for _ in range(10):

            if iq.check_connect():

                break

            time.sleep(1)

        if not iq.check_connect():

            print(
                "❌ IQ Option no confirmó la conexión"
            )

            return None

        # PRACTICE
        iq.change_balance("PRACTICE")

        print(
            "✅ Conectado a IQ Option"
        )

        return iq

    except Exception as e:

        print(
            f"❌ Error real conectando "
            f"a IQ Option: {e}"
        )

        return None


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(iq, timeframe, count):

    candles = iq.get_candles(
        PAIR,
        timeframe,
        count,
        time.time()
    )

    if not candles:

        return []

    return sorted(
        candles,
        key=lambda x: x["from"]
    )


# ============================================================
# OBTENER LAS 6 VELAS 5S
# EXACTAMENTE DEL SEGUNDO 0 AL 30
# ============================================================

def get_first_30_seconds(iq):

    now = int(time.time())

    current_minute = now // 60

    minute_start = current_minute * 60

    # Pedimos más de 6 para asegurarnos
    # de recibir las velas necesarias.
    candles = get_candles(
        iq,
        5,
        15
    )

    selected = []

    for candle in candles:

        candle_time = int(candle["from"])

        # Solo velas del minuto actual
        if (
            candle_time >= minute_start
            and candle_time < minute_start + 30
        ):

            selected.append(candle)

    selected = sorted(
        selected,
        key=lambda x: x["from"]
    )

    # Deben existir exactamente las 6:
    #
    # 00-05
    # 05-10
    # 10-15
    # 15-20
    # 20-25
    # 25-30

    if len(selected) != 6:

        print(
            f"⚠️ Solo se encontraron "
            f"{len(selected)}/6 velas 5S"
        )

        return []

    return selected


# ============================================================
# OBTENER LA ÚLTIMA M1 CERRADA
# ============================================================

def get_last_closed_m1(iq):

    candles = get_candles(
        iq,
        60,
        3
    )

    if len(candles) < 2:

        return None

    now = int(time.time())

    current_minute = now // 60

    current_minute_start = current_minute * 60

    closed = []

    for candle in candles:

        candle_time = int(candle["from"])

        # La vela pertenece a un minuto anterior
        if candle_time < current_minute_start:

            closed.append(candle)

    if not closed:

        return None

    closed = sorted(
        closed,
        key=lambda x: x["from"]
    )

    return closed[-1]


# ============================================================
# COLOR DE VELA
# ============================================================

def get_color(candle):

    if candle["close"] > candle["open"]:

        return "verde"

    if candle["close"] < candle["open"]:

        return "rojo"

    return "neutral"


# ============================================================
# ESPERAR SEGUNDO EXACTO
# ============================================================

def wait_for_second(target_second):

    while True:

        now = time.time()

        second = int(now) % 60

        if second == target_second:

            return

        time.sleep(0.05)


# ============================================================
# MAIN
# ============================================================

def main():

    iq = connect_iq()

    if iq is None:

        print(
            "⏳ Reintentando conexión "
            "en 30 segundos..."
        )

        time.sleep(30)

        return main()

    print()
    print("================================")
    print("🚀 BOT SNIPER ACTIVO")
    print(f"💱 PAR: {PAIR}")
    print("⏱️ EXPIRACIÓN: 1 MINUTO")
    print("================================")
    print()

    current_minute = None

    # Señal detectada en segundo 30
    signal = None

    # Evita detectar dos veces
    alert_sent = False

    while True:

        try:

            now = int(time.time())

            minute_id = now // 60

            second = now % 60

            # =================================================
            # NUEVA VELA M1
            # =================================================

            if minute_id != current_minute:

                current_minute = minute_id

                signal = None

                alert_sent = False

                print()
                print(
                    f"🕐 NUEVA VELA M1 "
                    f"| {time.strftime('%H:%M:%S')}"
                )

            # =================================================
            # SEGUNDO 30
            # ANALIZAR 6 VELAS DE 5S
            # =================================================

            if second == 30 and not alert_sent:

                print()
                print(
                    "🔎 SEGUNDO 30 "
                    "→ ANALIZANDO MICROESTRUCTURA"
                )

                candles_5s = get_first_30_seconds(
                    iq
                )

                if len(candles_5s) != 6:

                    print(
                        "⛔ No se puede analizar: "
                        "faltan velas 5S"
                    )

                else:

                    pattern = check_pattern(
                        candles_5s
                    )

                    # =========================================
                    # PATRÓN EXACTO
                    # =========================================

                    if pattern:

                        signal = pattern

                        alert_sent = True

                        print()
                        print(
                            f"🚨 ALERTA "
                            f"{signal.upper()}"
                        )

                        send_telegram(
                            f"🚨 ALERTA SNIPER\n\n"
                            f"Par: {PAIR}\n"
                            f"Dirección: "
                            f"{signal.upper()}\n\n"
                            f"Microestructura 5S "
                            f"confirmada.\n"
                            f"⏳ Esperando cierre M1."
                        )

                    else:

                        alert_sent = True

                        print(
                            "❌ Sin patrón exacto"
                        )

            # =================================================
            # SEGUNDO 0
            # NUEVA VELA M1
            # =================================================

            if second == 0 and signal:

                print()
                print(
                    "⏱️ SEGUNDO 0 "
                    "→ VALIDACIÓN FINAL"
                )

                # ---------------------------------------------
                # OBTENER VELA M1 QUE ACABA DE CERRAR
                # ---------------------------------------------

                closed_candle = get_last_closed_m1(
                    iq
                )

                if closed_candle is None:

                    print(
                        "⛔ No se pudo obtener "
                        "la M1 cerrada"
                    )

                    signal = None

                    continue

                color = get_color(
                    closed_candle
                )

                print(
                    f"📊 M1 cerrada: {color}"
                )

                # ---------------------------------------------
                # CALL
                # ---------------------------------------------

                if (
                    signal == "call"
                    and color == "verde"
                ):

                    direction = "call"

                # ---------------------------------------------
                # PUT
                # ---------------------------------------------

                elif (
                    signal == "put"
                    and color == "rojo"
                ):

                    direction = "put"

                # ---------------------------------------------
                # NO CONFIRMA
                # ---------------------------------------------

                else:

                    print()
                    print(
                        "❌ M1 NO CONFIRMÓ "
                        "LA SEÑAL"
                    )

                    send_telegram(
                        f"❌ SEÑAL CANCELADA\n\n"
                        f"Par: {PAIR}\n"
                        f"Señal: "
                        f"{signal.upper()}\n"
                        f"M1 cerró: {color}\n\n"
                        f"Sin operación."
                    )

                    signal = None

                    continue

                # =================================================
                # ENTRADA
                # =================================================

                print()
                print(
                    f"🎯 ENTRADA "
                    f"{direction.upper()}"
                )

                check, order_id = iq.buy(
                    AMOUNT,
                    PAIR,
                    direction,
                    EXPIRATION
                )

                if check:

                    print(
                        "✅ OPERACIÓN EJECUTADA"
                    )

                    send_telegram(
                        f"✅ ENTRADA EJECUTADA\n\n"
                        f"Par: {PAIR}\n"
                        f"Dirección: "
                        f"{direction.upper()}\n"
                        f"Importe: {AMOUNT}\n"
                        f"Expiración: "
                        f"{EXPIRATION} minuto"
                    )

                else:

                    print(
                        "❌ IQ Option rechazó "
                        "la operación"
                    )

                    send_telegram(
                        f"❌ ERROR EN ENTRADA\n\n"
                        f"Par: {PAIR}\n"
                        f"Dirección: "
                        f"{direction.upper()}"
                    )

                # Limpiar señal
                signal = None

            # =================================================
            # COMPROBAR CONEXIÓN
            # =================================================

            if not iq.check_connect():

                print(
                    "⚠️ Conexión IQ Option perdida"
                )

                send_telegram(
                    "⚠️ Conexión con IQ Option perdida."
                )

                iq = connect_iq()

                if iq is None:

                    print(
                        "⛔ No se pudo reconectar"
                    )

                    time.sleep(10)

                    continue

                print(
                    "✅ Reconectado"
                )

            # Dormir muy poco para no perder
            # los segundos 0 y 30.
            time.sleep(0.1)

        except Exception as e:

            print()
            print(
                f"❌ ERROR GENERAL: {e}"
            )

            time.sleep(2)


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":

    main()
