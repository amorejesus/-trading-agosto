# ============================================================
# BOT.PY
# IQ OPTION - ESTRATEGIA M1 + 12 VELAS DE 5 SEGUNDOS
# ============================================================

import os
import time
import requests
from datetime import datetime

from iqoptionapi.stable_api import IQ_Option

from strategy import check_pattern


# ============================================================
# CONFIGURACIÓN
# ============================================================

PAIR = "EURUSD-OTC"

AMOUNT = 55

# Expiración de la operación en minutos
EXPIRATION = 1

# Intervalo de las microvelas
TIMEFRAME_5S = 5

# Cantidad exacta de velas de 5s que forman una M1
CANDLES_PER_M1 = 12

# ============================================================
# CREDENCIALES
# ============================================================

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """
    Envía un mensaje a Telegram.
    Si Telegram no está configurado, simplemente continúa.
    """

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_TOKEN}/sendMessage"
        )

        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }

        requests.post(
            url,
            data=data,
            timeout=10
        )

    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():
    """
    Conecta con IQ Option.
    Reintenta hasta conseguir conexión.
    """

    if not EMAIL:
        raise RuntimeError(
            "Falta la variable de entorno IQ_EMAIL"
        )

    if not PASSWORD:
        raise RuntimeError(
            "Falta la variable de entorno IQ_PASSWORD"
        )

    while True:

        try:

            print("\n======================================")
            print("CONECTANDO A IQ OPTION")
            print("======================================")

            iq = IQ_Option(
                EMAIL,
                PASSWORD
            )

            check, reason = iq.connect()

            if check:

                print("✓ CONEXIÓN EXITOSA")

                try:
                    iq.change_balance("PRACTICE")
                    print("✓ CUENTA PRACTICE")
                except Exception:
                    pass

                send_telegram(
                    "🤖 BOT CONECTADO\n"
                    f"Activo: {PAIR}\n"
                    "Cuenta: PRACTICE"
                )

                return iq

            print(
                f"✗ Error de conexión: {reason}"
            )

        except Exception as e:

            print(
                f"✗ Error conectando: {e}"
            )

        print(
            "Reintentando en 5 segundos..."
        )

        time.sleep(5)


# ============================================================
# COMPROBAR CONEXIÓN
# ============================================================

def ensure_connection(iq):
    """
    Comprueba que la conexión siga activa.
    """

    try:

        if iq.check_connect():
            return True

    except Exception:
        pass

    print(
        "\n⚠ CONEXIÓN PERDIDA"
    )

    try:
        check, reason = iq.connect()

        if check:

            print(
                "✓ CONEXIÓN RESTAURADA"
            )

            return True

        print(
            f"✗ No se pudo reconectar: {reason}"
        )

    except Exception as e:

        print(
            f"✗ Error reconectando: {e}"
        )

    return False


# ============================================================
# TIEMPO
# ============================================================

def get_current_minute():
    """
    Devuelve el timestamp de inicio de la M1 actual.

    Ejemplo:

    12:35:27
       ↓
    12:35:00
    """

    now = int(time.time())

    return now - (now % 60)


# ============================================================
# ESPERAR AL CIERRE DE M1
# ============================================================

def wait_for_new_m1(last_m1=None):
    """
    Espera hasta que aparezca una nueva M1 cerrada.

    Devuelve:

        m1_start

    que corresponde al inicio de la M1 que acaba de terminar.
    """

    while True:

        current_m1 = get_current_minute()

        if last_m1 is None:
            return current_m1 - 60

        if current_m1 > last_m1:

            return current_m1 - 60

        time.sleep(0.2)


# ============================================================
# OBTENER LAS 12 VELAS DE 5S DE UNA M1
# ============================================================

def get_m1_5s_candles(iq, m1_start):
    """
    Obtiene EXACTAMENTE las 12 velas de 5 segundos
    pertenecientes a una M1 cerrada.

    M1:

        m1_start
             |
             +-- 00-05
             +-- 05-10
             +-- 10-15
             +-- 15-20
             +-- 20-25
             +-- 25-30
             +-- 30-35
             +-- 35-40
             +-- 40-45
             +-- 45-50
             +-- 50-55
             +-- 55-60
             |
        m1_start + 60

    SOLO se aceptan timestamps dentro de ese rango.
    """

    m1_end = m1_start + 60

    try:

        # Pedimos más de 12 para tener margen
        # y posteriormente filtramos exactamente
        # las correspondientes a esta M1.

        candles = iq.get_candles(
            PAIR,
            TIMEFRAME_5S,
            20,
            m1_end
        )

    except Exception as e:

        print(
            f"[CANDLES] Error obteniendo velas: {e}"
        )

        return None

    if not candles:

        return None

    # --------------------------------------------------------
    # Normalizar timestamp
    # --------------------------------------------------------

    valid = []

    for candle in candles:

        try:

            timestamp = int(
                candle.get("from")
            )

        except Exception:

            continue

        # EXACTAMENTE dentro de la M1
        if m1_start <= timestamp < m1_end:

            valid.append(candle)

    # --------------------------------------------------------
    # Orden cronológico
    # --------------------------------------------------------

    valid.sort(
        key=lambda x: int(x["from"])
    )

    # --------------------------------------------------------
    # Debemos tener exactamente 12
    # --------------------------------------------------------

    if len(valid) != CANDLES_PER_M1:

        print(
            f"[M1] Velas encontradas: "
            f"{len(valid)}/12"
        )

        return None

    # --------------------------------------------------------
    # Comprobación adicional:
    # deben estar separadas exactamente 5 segundos.
    # --------------------------------------------------------

    timestamps = [
        int(c["from"])
        for c in valid
    ]

    for i in range(1, len(timestamps)):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:

            print(
                "[M1] Secuencia 5s inválida:"
                f" diferencia={difference}"
            )

            return None

    return valid


# ============================================================
# MOSTRAR LAS 12 VELAS
# ============================================================

def print_m1_candles(candles):
    """
    Imprime las 12 velas utilizadas.
    """

    print("\n--------------------------------------")
    print("12 VELAS DE 5S")
    print("--------------------------------------")

    for index, candle in enumerate(candles, start=1):

        timestamp = int(
            candle["from"]
        )

        dt = datetime.fromtimestamp(
            timestamp
        )

        open_price = candle.get("open")
        close_price = candle.get("close")

        if close_price > open_price:
            direction = "VERDE"
            symbol = "🟢"

        elif close_price < open_price:
            direction = "ROJA"
            symbol = "🔴"

        else:
            direction = "DOJI"
            symbol = "⚪"

        print(
            f"{index:02d} | "
            f"{dt.strftime('%H:%M:%S')} | "
            f"{symbol} {direction} | "
            f"O={open_price} | "
            f"C={close_price}"
        )

    print("--------------------------------------")


# ============================================================
# ANALIZAR ESTRATEGIA
# ============================================================

def analyze_strategy(candles):
    """
    Entrega las 12 velas cerradas a strategy.py.

    IMPORTANTE:

    La lógica de dirección NO se calcula aquí.

    Toda la lógica matemática pertenece a strategy.py.

    De esta forma bot.py solamente:

        1. obtiene datos
        2. verifica que estén completos
        3. llama a strategy.py
        4. ejecuta la señal
    """

    try:

        signal = check_pattern(
            candles
        )

        return signal

    except Exception as e:

        print(
            f"[STRATEGY] Error: {e}"
        )

        return None


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(signal):
    """
    Normaliza la respuesta de strategy.py.

    Valores aceptados:

        CALL
        PUT

    También acepta minúsculas.
    """

    if signal is None:
        return None

    if isinstance(signal, str):

        signal = signal.strip().lower()

        if signal == "call":
            return "call"

        if signal == "put":
            return "put"

    return None


# ============================================================
# EJECUTAR OPERACIÓN
# ============================================================

def execute_trade(iq, signal):
    """
    Ejecuta una operación de 1 minuto.
    """

    signal = normalize_signal(
        signal
    )

    if signal not in ("call", "put"):

        print(
            "[TRADE] Sin señal válida."
        )

        return False, None

    print("\n======================================")
    print("SEÑAL CONFIRMADA")
    print("======================================")

    if signal == "call":
        print("🟢 CALL")
    else:
        print("🔴 PUT")

    print(
        f"Activo: {PAIR}"
    )

    print(
        f"Monto: {AMOUNT}"
    )

    print(
        f"Expiración: {EXPIRATION} minuto"
    )

    print("======================================")

    try:

        success, order_id = iq.buy(
            AMOUNT,
            PAIR,
            signal,
            EXPIRATION
        )

        if success:

            print(
                f"✓ OPERACIÓN ABIERTA "
                f"ID={order_id}"
            )

            send_telegram(
                "📊 OPERACIÓN ABIERTA\n\n"
                f"Activo: {PAIR}\n"
                f"Dirección: {signal.upper()}\n"
                f"Monto: {AMOUNT}\n"
                f"Expiración: {EXPIRATION}M"
            )

            return True, order_id

        print(
            "✗ IQ Option rechazó la operación."
        )

        return False, None

    except Exception as e:

        print(
            f"✗ Error ejecutando operación: {e}"
        )

        return False, None


# ============================================================
# RESULTADO DE OPERACIÓN
# ============================================================

def get_trade_result(iq, order_id):
    """
    Espera hasta que la operación termine
    y obtiene el resultado.
    """

    if not order_id:
        return None

    # Esperamos aproximadamente el tiempo
    # de expiración + margen.

    wait_seconds = (
        EXPIRATION * 60
    ) + 5

    print(
        f"\nEsperando resultado "
        f"({wait_seconds}s)..."
    )

    time.sleep(
        wait_seconds
    )

    # --------------------------------------------------------
    # Método recomendado de stable_api
    # --------------------------------------------------------

    try:

        result = iq.check_win_v4(
            order_id
        )

        if result is not None:

            return float(result)

    except Exception as e:

        print(
            f"[RESULTADO] Error: {e}"
        )

    # --------------------------------------------------------
    # Si la API no devuelve resultado
    # --------------------------------------------------------

    return None


# ============================================================
# MOSTRAR RESULTADO
# ============================================================

def print_result(result):

    if result is None:

        print(
            "\n⚠ RESULTADO NO DISPONIBLE"
        )

        return

    if result > 0:

        print(
            "\n🟢 WIN"
        )

        print(
            f"Resultado: +{result}"
        )

        send_telegram(
            "🟢 WIN\n"
            f"Resultado: +{result}"
        )

    elif result < 0:

        print(
            "\n🔴 LOSS"
        )

        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "🔴 LOSS\n"
            f"Resultado: {result}"
        )

    else:

        print(
            "\n⚪ EMPATE"
        )

        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "⚪ EMPATE\n"
            f"Resultado: {result}"
        )


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def main():

    print("\n")
    print("==========================================")
    print("        BOT IQ OPTION")
    print("        M1 + 12 VELAS DE 5S")
    print("==========================================")
    print(
        f"ACTIVO       : {PAIR}"
    )
    print(
        f"MONTO        : {AMOUNT}"
    )
    print(
        f"EXPIRACIÓN   : {EXPIRATION}M"
    )
    print(
        f"MICROVELAS   : {CANDLES_PER_M1}"
    )
    print(
        "DIRECCIÓN    : strategy.py"
    )
    print("==========================================")

    iq = connect_iq()

    # --------------------------------------------------------
    # Evitar analizar dos veces la misma M1
    # --------------------------------------------------------

    last_processed_m1 = None

    # --------------------------------------------------------
    # Evitar abrir una segunda operación mientras
    # la anterior todavía está activa.
    # --------------------------------------------------------

    operation_in_progress = False

    while True:

        try:

            # =================================================
            # COMPROBAR CONEXIÓN
            # =================================================

            if not ensure_connection(iq):

                time.sleep(5)

                iq = connect_iq()

                continue

            # =================================================
            # ESPERAR UNA M1 COMPLETA
            # =================================================

            m1_start = wait_for_new_m1(
                last_processed_m1
            )

            # -------------------------------------------------
            # Seguridad contra duplicados
            # -------------------------------------------------

            if (
                last_processed_m1
                == m1_start
            ):

                time.sleep(0.2)

                continue

            print("\n")
            print("======================================")
            print(
                "M1 CERRADA"
            )
            print(
                datetime.fromtimestamp(
                    m1_start
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
            print("======================================")

            # =================================================
            # OBTENER 12 VELAS
            # =================================================

            candles = None

            # En caso de que la API tarde en actualizar,
            # hacemos varios intentos.
            for attempt in range(5):

                candles = get_m1_5s_candles(
                    iq,
                    m1_start
                )

                if candles is not None:
                    break

                print(
                    f"[M1] Esperando datos..."
                    f" intento {attempt + 1}/5"
                )

                time.sleep(1)

            # =================================================
            # MARCAR LA M1 COMO PROCESADA
            # =================================================

            last_processed_m1 = m1_start

            # =================================================
            # DATOS INCOMPLETOS
            # =================================================

            if candles is None:

                print(
                    "\n⚠ M1 DESCARTADA"
                )

                print(
                    "No se obtuvieron exactamente "
                    "12 velas cerradas de 5s."
                )

                send_telegram(
                    "⚠ M1 DESCARTADA\n"
                    "Datos 5s incompletos."
                )

                continue

            # =================================================
            # MOSTRAR LAS 12 VELAS
            # =================================================

            print_m1_candles(
                candles
            )

            # =================================================
            # ANALIZAR ESTRATEGIA
            # =================================================

            print(
                "\nAnalizando "
                "las 12 velas..."
            )

            signal = analyze_strategy(
                candles
            )

            signal = normalize_signal(
                signal
            )

            # =================================================
            # RESULTADO DEL ANÁLISIS
            # =================================================

            print("\n--------------------------------------")
            print("RESULTADO DE STRATEGY.PY")
            print("--------------------------------------")

            if signal == "call":

                print(
                    "🟢 DIRECCIÓN DOMINANTE: CALL"
                )

            elif signal == "put":

                print(
                    "🔴 DIRECCIÓN DOMINANTE: PUT"
                )

            else:

                print(
                    "⚪ SIN SEÑAL"
                )

            print("--------------------------------------")

            # =================================================
            # NO HAY SEÑAL
            # =================================================

            if signal is None:

                print(
                    "M1 descartada."
                )

                send_telegram(
                    "⚪ SIN OPERACIÓN\n"
                    f"{PAIR}\n"
                    "Las condiciones matemáticas "
                    "no fueron suficientes."
                )

                continue

            # =================================================
            # SEGURIDAD
            # =================================================

            if operation_in_progress:

                print(
                    "⚠ Ya existe una operación "
                    "en progreso."
                )

                continue

            # =================================================
            # EJECUTAR
            # =================================================

            success, order_id = execute_trade(
                iq,
                signal
            )

            if not success:

                continue

            operation_in_progress = True

            # =================================================
            # ESPERAR RESULTADO
            # =================================================

            result = get_trade_result(
                iq,
                order_id
            )

            print_result(
                result
            )

            operation_in_progress = False

        # =====================================================
        # CTRL+C
        # =====================================================

        except KeyboardInterrupt:

            print(
                "\n\nBOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT DETENIDO"
            )

            break

        # =====================================================
        # ERROR GENERAL
        # =====================================================

        except Exception as e:

            print(
                "\n======================================"
            )

            print(
                "ERROR GENERAL"
            )

            print(
                str(e)
            )

            print(
                "======================================"
            )

            send_telegram(
                "⚠ ERROR EN BOT\n"
                f"{str(e)}"
            )

            # No cerramos el programa por un error
            # temporal.

            time.sleep(3)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
