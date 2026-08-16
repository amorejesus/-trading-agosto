# ============================================================
# BOT.PY
# IQ OPTION - M1 + 12 VELAS DE 5 SEGUNDOS
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

AMOUNT = 550

# Expiración en minutos
EXPIRATION = 1

# Cada vela = 5 segundos
TIMEFRAME_5S = 5

# Una M1 = 12 velas de 5 segundos
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

        response = requests.post(
            url,
            data=data,
            timeout=10
        )

        if not response.ok:

            print(
                f"[TELEGRAM] HTTP {response.status_code}"
            )

    except Exception as e:

        print(
            f"[TELEGRAM] Error: {e}"
        )


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():

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

                    iq.change_balance(
                        "PRACTICE"
                    )

                    print(
                        "✓ CUENTA PRACTICE"
                    )

                except Exception as e:

                    print(
                        f"[BALANCE] Aviso: {e}"
                    )

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

    now = int(
        time.time()
    )

    return now - (
        now % 60
    )


# ============================================================
# ESPERAR M1 CERRADA
# ============================================================

def wait_for_new_m1(last_m1=None):

    while True:

        current_m1 = get_current_minute()

        # Primera ejecución:
        # tomar la M1 anterior ya cerrada.

        if last_m1 is None:

            return current_m1 - 60

        # Nueva M1 cerrada.

        if current_m1 > last_m1:

            return current_m1 - 60

        time.sleep(0.2)


# ============================================================
# NORMALIZAR UNA VELA DE IQ OPTION
# ============================================================

def normalize_candle(candle):

    """
    IQ Option normalmente entrega:

        open
        close
        min
        max
        from
        to
        volume

    Algunas partes de la estrategia pueden utilizar:

        low
        high

    Por eso aquí normalizamos ambos formatos.

    IMPORTANTE:
    NO modificamos los precios.
    Solo damos nombres compatibles.
    """

    if not isinstance(candle, dict):

        return None

    result = dict(candle)

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    timestamp = result.get("from")

    if timestamp is None:

        return None

    try:

        result["from"] = int(
            timestamp
        )

    except Exception:

        return None

    # --------------------------------------------------------
    # OPEN
    # --------------------------------------------------------

    if result.get("open") is None:

        return None

    # --------------------------------------------------------
    # CLOSE
    # --------------------------------------------------------

    if result.get("close") is None:

        return None

    # --------------------------------------------------------
    # HIGH
    #
    # IQ Option usa normalmente "max".
    # --------------------------------------------------------

    if result.get("high") is None:

        if result.get("max") is not None:

            result["high"] = result["max"]

    # --------------------------------------------------------
    # LOW
    #
    # IQ Option usa normalmente "min".
    # --------------------------------------------------------

    if result.get("low") is None:

        if result.get("min") is not None:

            result["low"] = result["min"]

    # --------------------------------------------------------
    # Si existe high pero no max
    # --------------------------------------------------------

    if result.get("max") is None:

        if result.get("high") is not None:

            result["max"] = result["high"]

    # --------------------------------------------------------
    # Si existe low pero no min
    # --------------------------------------------------------

    if result.get("min") is None:

        if result.get("low") is not None:

            result["min"] = result["low"]

    # --------------------------------------------------------
    # Validar high
    # --------------------------------------------------------

    if result.get("high") is None:

        print(
            "[M1] Vela sin dato HIGH/MAX."
        )

        return None

    # --------------------------------------------------------
    # Validar low
    # --------------------------------------------------------

    if result.get("low") is None:

        print(
            "[M1] Vela sin dato LOW/MIN."
        )

        return None

    return result


# ============================================================
# OBTENER LAS 12 VELAS DE 5S
# ============================================================

def get_m1_5s_candles(iq, m1_start):

    m1_end = (
        m1_start + 60
    )

    try:

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

        print(
            "[M1] IQ Option no devolvió velas."
        )

        return None

    valid = []

    # ========================================================
    # NORMALIZAR Y FILTRAR
    # ========================================================

    for raw_candle in candles:

        candle = normalize_candle(
            raw_candle
        )

        if candle is None:

            continue

        timestamp = candle["from"]

        # EXACTAMENTE dentro de la M1

        if (
            m1_start
            <= timestamp
            < m1_end
        ):

            valid.append(
                candle
            )

    # ========================================================
    # ORDEN CRONOLÓGICO
    # ========================================================

    valid.sort(
        key=lambda x: x["from"]
    )

    # ========================================================
    # EXACTAMENTE 12
    # ========================================================

    if len(valid) != CANDLES_PER_M1:

        print(
            f"[M1] Velas válidas: "
            f"{len(valid)}/{CANDLES_PER_M1}"
        )

        return None

    # ========================================================
    # COMPROBAR SECUENCIA DE 5 SEGUNDOS
    # ========================================================

    timestamps = [
        candle["from"]
        for candle in valid
    ]

    for i in range(
        1,
        len(timestamps)
    ):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:

            print(
                "[M1] Secuencia 5s inválida: "
                f"{timestamps[i - 1]} -> "
                f"{timestamps[i]} "
                f"(diferencia={difference})"
            )

            return None

    # ========================================================
    # COMPROBACIÓN FINAL
    # ========================================================

    print(
        f"✓ M1 contiene exactamente "
        f"{len(valid)} velas de 5s"
    )

    return valid


# ============================================================
# MOSTRAR LAS 12 VELAS
# ============================================================

def print_m1_candles(candles):

    print("\n--------------------------------------")
    print("12 VELAS DE 5S")
    print("--------------------------------------")

    for index, candle in enumerate(
        candles,
        start=1
    ):

        timestamp = int(
            candle["from"]
        )

        dt = datetime.fromtimestamp(
            timestamp
        )

        open_price = candle.get(
            "open"
        )

        close_price = candle.get(
            "close"
        )

        high_price = candle.get(
            "high"
        )

        low_price = candle.get(
            "low"
        )

        # ----------------------------------------------------
        # DIRECCIÓN
        # ----------------------------------------------------

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
            f"C={close_price} | "
            f"H={high_price} | "
            f"L={low_price}"
        )

    print("--------------------------------------")


# ============================================================
# ANALIZAR STRATEGY.PY
# ============================================================

def analyze_strategy(candles):

    """
    BOT.PY NO calcula la estrategia.

    Solo entrega las 12 velas cerradas
    directamente a:

        strategy.check_pattern()

    """

    if not candles:

        return None

    if len(candles) != CANDLES_PER_M1:

        print(
            "[STRATEGY] Cantidad incorrecta de velas."
        )

        return None

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

    if signal is None:

        return None

    if isinstance(
        signal,
        str
    ):

        signal = (
            signal
            .strip()
            .lower()
        )

        if signal == "call":

            return "call"

        if signal == "put":

            return "put"

    return None


# ============================================================
# EJECUTAR OPERACIÓN
# ============================================================

def execute_trade(iq, signal):

    signal = normalize_signal(
        signal
    )

    if signal not in (
        "call",
        "put"
    ):

        print(
            "[TRADE] Sin señal válida."
        )

        return False, None

    print("\n======================================")
    print("SEÑAL CONFIRMADA")
    print("======================================")

    if signal == "call":

        print(
            "🟢 CALL"
        )

    else:

        print(
            "🔴 PUT"
        )

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

def get_trade_result(
    iq,
    order_id
):

    if not order_id:

        return None

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

    try:

        result = iq.check_win_v4(
            order_id
        )

        if result is not None:

            return float(
                result
            )

    except Exception as e:

        print(
            f"[RESULTADO] Error: {e}"
        )

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
    print("           BOT IQ OPTION")
    print("           M1 + 12 VELAS DE 5S")
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
        "ESTRATEGIA   : strategy.py"
    )

    print("==========================================")

    # ========================================================
    # CONEXIÓN
    # ========================================================

    iq = connect_iq()

    # ========================================================
    # CONTROL DE M1
    # ========================================================

    last_processed_m1 = None

    # ========================================================
    # CICLO
    # ========================================================

    while True:

        try:

            # =================================================
            # CONEXIÓN
            # =================================================

            if not ensure_connection(iq):

                time.sleep(5)

                iq = connect_iq()

                continue

            # =================================================
            # ESPERAR M1 CERRADA
            # =================================================

            m1_start = wait_for_new_m1(
                last_processed_m1
            )

            # =================================================
            # EVITAR DUPLICADOS
            # =================================================

            if (
                last_processed_m1
                == m1_start
            ):

                time.sleep(0.2)

                continue

            print("\n")
            print("======================================")
            print("M1 CERRADA")
            print(
                datetime.fromtimestamp(
                    m1_start
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )
            print("======================================")

            # =================================================
            # OBTENER LAS 12 VELAS
            # =================================================

            candles = None

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
            # MARCAR COMO PROCESADA
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
                    "No existen exactamente "
                    "12 velas válidas de 5s."
                )

                send_telegram(
                    "⚠ M1 DESCARTADA\n"
                    f"{PAIR}\n"
                    "Datos 5s incompletos."
                )

                continue

            # =================================================
            # MOSTRAR VELAS
            # =================================================

            print_m1_candles(
                candles
            )

            # =================================================
            # ANALIZAR
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
            # RESULTADO
            # =================================================

            print("\n--------------------------------------")
            print("RESULTADO DE STRATEGY.PY")
            print("--------------------------------------")

            if signal == "call":

                print(
                    "🟢 SEÑAL: CALL"
                )

            elif signal == "put":

                print(
                    "🔴 SEÑAL: PUT"
                )

            else:

                print(
                    "⚪ SIN SEÑAL"
                )

            print("--------------------------------------")

            # =================================================
            # SIN SEÑAL
            # =================================================

            if signal is None:

                print(
                    "M1 descartada."
                )

                send_telegram(
                    "⚪ SIN OPERACIÓN\n"
                    f"{PAIR}\n"
                    "strategy.py no generó CALL/PUT."
                )

                continue

            # =================================================
            # EJECUTAR OPERACIÓN
            # =================================================

            success, order_id = execute_trade(
                iq,
                signal
            )

            if not success:

                continue

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

            time.sleep(3)


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
