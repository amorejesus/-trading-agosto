# ============================================================
# BOT.PY
# IQ OPTION
# M1 + EXACTAMENTE 12 VELAS DE 5 SEGUNDOS
# ============================================================

import os
import time
import requests
from datetime import datetime

import strategy
from iqoptionapi.stable_api import IQ_Option


# ============================================================
# CONFIGURACIÓN
# ============================================================

PAIR = "EURUSD-OTC"

AMOUNT = 55

EXPIRATION = 1

TIMEFRAME_5S = 5

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

            print()
            print("======================================")
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

                    print("✓ CUENTA PRACTICE")

                except Exception as e:

                    print(
                        f"[BALANCE] {e}"
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

    print()
    print("⚠ CONEXIÓN PERDIDA")

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

    now = int(time.time())

    return now - (now % 60)


# ============================================================
# ESPERAR M1 CERRADA
# ============================================================

def wait_for_new_m1(last_m1=None):

    while True:

        current_m1 = get_current_minute()

        if last_m1 is None:

            return current_m1 - 60

        if current_m1 > last_m1:

            return current_m1 - 60

        time.sleep(0.2)


# ============================================================
# OBTENER EXACTAMENTE 12 VELAS DE 5S
# ============================================================

def get_m1_5s_candles(iq, m1_start):

    m1_end = m1_start + 60

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
            "[CANDLES] API no devolvió velas."
        )

        return None

    valid = []

    for candle in candles:

        try:

            timestamp = int(
                candle.get("from")
            )

        except Exception:

            continue

        # ====================================================
        # SOLO VELAS PERTENECIENTES A ESTA M1
        # ====================================================

        if m1_start <= timestamp < m1_end:

            valid.append(candle)

    # ========================================================
    # ORDEN CRONOLÓGICO
    # ========================================================

    valid.sort(
        key=lambda x: int(x["from"])
    )

    # ========================================================
    # EXACTAMENTE 12
    # ========================================================

    if len(valid) != CANDLES_PER_M1:

        print(
            f"[M1] Velas encontradas: "
            f"{len(valid)}/{CANDLES_PER_M1}"
        )

        return None

    # ========================================================
    # COMPROBAR QUE SEAN REALMENTE DE 5S
    # ========================================================

    timestamps = [
        int(candle["from"])
        for candle in valid
    ]

    for i in range(1, len(timestamps)):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:

            print(
                "[M1] Secuencia inválida."
            )

            print(
                f"Diferencia encontrada: "
                f"{difference}s"
            )

            return None

    # ========================================================
    # COMPROBAR OHLC
    # ========================================================

    for index, candle in enumerate(valid, start=1):

        required = (
            "open",
            "close",
            "high",
            "low"
        )

        for key in required:

            if candle.get(key) is None:

                print(
                    f"[M1] Vela {index} "
                    f"sin dato '{key}'."
                )

                return None

    return valid


# ============================================================
# MOSTRAR LAS 12 VELAS
# ============================================================

def print_m1_candles(candles):

    print()
    print("--------------------------------------")
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

        open_price = float(
            candle["open"]
        )

        close_price = float(
            candle["close"]
        )

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
# ANALIZAR STRATEGY.PY
# ============================================================

def analyze_strategy(candles):

    """
    La matemática pertenece exclusivamente
    a strategy.py.

    Orden de compatibilidad:

    1. check_pattern()
    2. get_strategy_analysis()

    El bot NO calcula la dirección.
    """

    # ========================================================
    # OPCIÓN 1
    # ========================================================

    check_pattern = getattr(
        strategy,
        "check_pattern",
        None
    )

    if callable(check_pattern):

        try:

            return check_pattern(
                candles
            )

        except Exception as e:

            print(
                f"[STRATEGY] Error en "
                f"check_pattern(): {e}"
            )

            return None

    # ========================================================
    # OPCIÓN 2
    # ========================================================

    get_strategy_analysis = getattr(
        strategy,
        "get_strategy_analysis",
        None
    )

    if callable(get_strategy_analysis):

        try:

            return get_strategy_analysis(
                candles
            )

        except Exception as e:

            print(
                f"[STRATEGY] Error en "
                f"get_strategy_analysis(): {e}"
            )

            return None

    # ========================================================
    # NO EXISTE FUNCIÓN COMPATIBLE
    # ========================================================

    print()
    print("======================================")
    print("ERROR DE COMPATIBILIDAD")
    print("======================================")
    print(
        "strategy.py no contiene:"
    )
    print(
        "  check_pattern()"
    )
    print(
        "  ni get_strategy_analysis()"
    )
    print("======================================")

    return None


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(signal):

    if signal is None:

        return None

    # --------------------------------------------------------
    # STRING
    # --------------------------------------------------------

    if isinstance(signal, str):

        value = signal.strip().lower()

        if value == "call":

            return "call"

        if value == "put":

            return "put"

        return None

    # --------------------------------------------------------
    # DICCIONARIO
    # --------------------------------------------------------

    if isinstance(signal, dict):

        for key in (
            "signal",
            "direction",
            "action",
            "trade"
        ):

            value = signal.get(key)

            if isinstance(value, str):

                value = value.strip().lower()

                if value == "call":

                    return "call"

                if value == "put":

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

    print()
    print("======================================")
    print("SEÑAL CONFIRMADA")
    print("======================================")

    if signal == "call":

        print("🟢 CALL")

    else:

        print("🔴 PUT")

    print(
        f"Activo      : {PAIR}"
    )

    print(
        f"Monto       : {AMOUNT}"
    )

    print(
        f"Expiración  : {EXPIRATION}M"
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

    if not order_id:

        return None

    wait_seconds = (
        EXPIRATION * 60
    ) + 5

    print()
    print(
        f"Esperando resultado "
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

            return float(result)

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

        print()
        print(
            "⚠ RESULTADO NO DISPONIBLE"
        )

        return

    if result > 0:

        print()
        print("🟢 WIN")
        print(
            f"Resultado: +{result}"
        )

        send_telegram(
            "🟢 WIN\n"
            f"Resultado: +{result}"
        )

    elif result < 0:

        print()
        print("🔴 LOSS")
        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "🔴 LOSS\n"
            f"Resultado: {result}"
        )

    else:

        print()
        print("⚪ EMPATE")
        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "⚪ EMPATE\n"
            f"Resultado: {result}"
        )


# ============================================================
# INFORMACIÓN INICIAL
# ============================================================

def print_startup():

    print()
    print("==========================================")
    print("             BOT IQ OPTION")
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
        f"TIMEFRAME    : {TIMEFRAME_5S}s"
    )

    print(
        "ESTRATEGIA   : strategy.py"
    )

    print("==========================================")


# ============================================================
# COMPROBAR QUE STRATEGY.PY TENGA UNA INTERFAZ VÁLIDA
# ============================================================

def check_strategy_interface():

    check_pattern = getattr(
        strategy,
        "check_pattern",
        None
    )

    get_strategy_analysis = getattr(
        strategy,
        "get_strategy_analysis",
        None
    )

    if callable(check_pattern):

        print(
            "✓ strategy.py: check_pattern()"
        )

        return True

    if callable(get_strategy_analysis):

        print(
            "✓ strategy.py: "
            "get_strategy_analysis()"
        )

        return True

    print()
    print("======================================")
    print("✗ ERROR: STRATEGY.PY INCOMPATIBLE")
    print("======================================")
    print(
        "Debe existir una de estas funciones:"
    )
    print()
    print(
        "check_pattern(candles_5s)"
    )
    print()
    print(
        "o"
    )
    print()
    print(
        "get_strategy_analysis(candles_5s)"
    )
    print("======================================")

    return False


# ============================================================
# MAIN
# ============================================================

def main():

    print_startup()

    # ========================================================
    # COMPROBAR STRATEGY.PY
    # ========================================================

    if not check_strategy_interface():

        raise RuntimeError(
            "strategy.py no tiene una función "
            "compatible."
        )

    # ========================================================
    # CONECTAR
    # ========================================================

    iq = connect_iq()

    # ========================================================
    # CONTROL DE M1
    # ========================================================

    last_processed_m1 = None

    # ========================================================
    # CONTROL DE OPERACIÓN
    # ========================================================

    operation_in_progress = False

    # ========================================================
    # LOOP PRINCIPAL
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

            print()
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
            # OBTENER 12 VELAS
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
                    f" intento "
                    f"{attempt + 1}/5"
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

                print()
                print(
                    "⚠ M1 DESCARTADA"
                )

                print(
                    "No existen exactamente "
                    "12 velas válidas de 5s."
                )

                send_telegram(
                    "⚠ M1 DESCARTADA\n"
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

            print()
            print(
                "Analizando las 12 velas..."
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

            print()
            print("--------------------------------------")
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
                    "strategy.py no generó "
                    "una señal válida."
                )

                continue

            # =================================================
            # NO DUPLICAR OPERACIÓN
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

            print()
            print(
                "BOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT DETENIDO"
            )

            break

        # =====================================================
        # ERROR GENERAL
        # =====================================================

        except Exception as e:

            print()
            print("======================================")
            print("ERROR GENERAL")
            print("======================================")
            print(
                str(e)
            )
            print("======================================")

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
