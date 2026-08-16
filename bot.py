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

AMOUNT = 750

# Expiración en minutos
EXPIRATION = 1

# Duración de cada microvela
TIMEFRAME_5S = 5

# Una M1 contiene 12 velas de 5 segundos
CANDLES_PER_M1 = 12

# SOLO estas 6 se utilizan para strategy.py
STRATEGY_CANDLES = 6


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
            "https://api.telegram.org/bot"
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

    print()
    print("⚠ CONEXIÓN PERDIDA")

    try:

        check, reason = iq.connect()

        if check:

            print(
                "✓ CONEXIÓN RESTAURADA"
            )

            try:

                iq.change_balance(
                    "PRACTICE"
                )

            except Exception:

                pass

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

        # ----------------------------------------------------
        # PRIMERA EJECUCIÓN
        #
        # Si son las 16:05:xx:
        #
        # current_m1 = 16:05:00
        #
        # La última M1 cerrada es:
        #
        # 16:04:00 -> 16:04:59
        # ----------------------------------------------------

        if last_m1 is None:

            return current_m1 - 60

        # ----------------------------------------------------
        # ESPERAR A QUE APAREZCA UNA NUEVA M1 CERRADA
        # ----------------------------------------------------

        if current_m1 > last_m1:

            return current_m1 - 60

        time.sleep(0.2)


# ============================================================
# NORMALIZAR UNA VELA
# ============================================================

def normalize_candle(candle):

    if not isinstance(
        candle,
        dict
    ):

        return None

    result = dict(
        candle
    )

    # ========================================================
    # TIMESTAMP
    # ========================================================

    timestamp = result.get(
        "from"
    )

    if timestamp is None:

        return None

    try:

        timestamp = int(
            float(timestamp)
        )

    except Exception:

        return None

    result["from"] = timestamp

    # ========================================================
    # OPEN
    # ========================================================

    if result.get(
        "open"
    ) is None:

        return None

    try:

        result["open"] = float(
            result["open"]
        )

    except Exception:

        return None

    # ========================================================
    # CLOSE
    # ========================================================

    if result.get(
        "close"
    ) is None:

        return None

    try:

        result["close"] = float(
            result["close"]
        )

    except Exception:

        return None

    # ========================================================
    # HIGH
    # ========================================================

    if result.get(
        "high"
    ) is None:

        if result.get(
            "max"
        ) is not None:

            result["high"] = result["max"]

    if result.get(
        "high"
    ) is not None:

        try:

            result["high"] = float(
                result["high"]
            )

        except Exception:

            result["high"] = None

    # ========================================================
    # LOW
    # ========================================================

    if result.get(
        "low"
    ) is None:

        if result.get(
            "min"
        ) is not None:

            result["low"] = result["min"]

    if result.get(
        "low"
    ) is not None:

        try:

            result["low"] = float(
                result["low"]
            )

        except Exception:

            result["low"] = None

    return result


# ============================================================
# OBTENER LAS 12 VELAS DE LA M1
# ============================================================

def get_m1_5s_candles(
    iq,
    m1_start
):

    # --------------------------------------------------------
    # La M1 termina exactamente 60 segundos después.
    # --------------------------------------------------------

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

        # ----------------------------------------------------
        # SOLO VELAS DE ESTA M1
        #
        # m1_start <= timestamp < m1_end
        # ----------------------------------------------------

        if (
            m1_start
            <= timestamp
            < m1_end
        ):

            valid.append(
                candle
            )

    # ========================================================
    # ORDENAR POR TIEMPO
    # ========================================================

    valid.sort(
        key=lambda candle: candle["from"]
    )

    # ========================================================
    # ELIMINAR DUPLICADOS POR TIMESTAMP
    # ========================================================

    unique = []

    seen = set()

    for candle in valid:

        timestamp = candle["from"]

        if timestamp in seen:

            continue

        seen.add(
            timestamp
        )

        unique.append(
            candle
        )

    valid = unique

    # ========================================================
    # DEBEN EXISTIR EXACTAMENTE 12
    # ========================================================

    if len(valid) != CANDLES_PER_M1:

        print()
        print(
            "⚠ M1 DESCARTADA"
        )

        print(
            f"No existen exactamente "
            f"{CANDLES_PER_M1} velas válidas de 5s."
        )

        print(
            f"Encontradas: {len(valid)}"
        )

        print(
            f"M1: "
            f"{datetime.fromtimestamp(m1_start).strftime('%H:%M:%S')}"
            f" → "
            f"{datetime.fromtimestamp(m1_end).strftime('%H:%M:%S')}"
        )

        return None

    # ========================================================
    # COMPROBAR SECUENCIA EXACTA DE 5 SEGUNDOS
    # ========================================================

    expected_timestamp = m1_start

    for index, candle in enumerate(
        valid
    ):

        timestamp = candle["from"]

        if timestamp != expected_timestamp:

            print()
            print(
                "⚠ SECUENCIA DE VELAS INVÁLIDA"
            )

            print(
                f"Vela {index + 1}"
            )

            print(
                f"Esperado : "
                f"{datetime.fromtimestamp(expected_timestamp).strftime('%H:%M:%S')}"
            )

            print(
                f"Recibido : "
                f"{datetime.fromtimestamp(timestamp).strftime('%H:%M:%S')}"
            )

            return None

        expected_timestamp += 5

    # ========================================================
    # COMPROBACIÓN FINAL
    # ========================================================

    print()
    print(
        "✓ M1 COMPLETA"
    )

    print(
        f"Inicio : "
        f"{datetime.fromtimestamp(m1_start).strftime('%H:%M:%S')}"
    )

    print(
        f"Cierre : "
        f"{datetime.fromtimestamp(m1_end).strftime('%H:%M:%S')}"
    )

    print(
        f"Velas  : {len(valid)}/12"
    )

    return valid


# ============================================================
# MOSTRAR LAS 12 VELAS
# ============================================================

def print_m1_candles(
    candles,
    m1_start
):

    print()
    print("======================================")
    print("M1 COMPLETA")
    print("======================================")

    print(
        "M1 INICIO : "
        f"{datetime.fromtimestamp(m1_start).strftime('%H:%M:%S')}"
    )

    print(
        "M1 CIERRE : "
        f"{datetime.fromtimestamp(m1_start + 60).strftime('%H:%M:%S')}"
    )

    print(
        "--------------------------------------"
    )

    print(
        "12 VELAS DE 5S"
    )

    print(
        "--------------------------------------"
    )

    # ========================================================
    # MOSTRAR SIEMPRE EN ORDEN 01 → 12
    # ========================================================

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
        # COLOR
        # ----------------------------------------------------

        if close_price > open_price:

            symbol = "🟢"
            direction = "VERDE"

        elif close_price < open_price:

            symbol = "🔴"
            direction = "ROJA"

        else:

            symbol = "⚪"
            direction = "DOJI"

        print(
            f"{index:02d} | "
            f"{dt.strftime('%H:%M:%S')} | "
            f"{symbol} {direction} | "
            f"O={open_price} | "
            f"C={close_price} | "
            f"H={high_price} | "
            f"L={low_price}"
        )

    print(
        "--------------------------------------"
    )


# ============================================================
# OBTENER SOLO LAS PRIMERAS 6
# ============================================================

def get_strategy_candles(
    candles
):

    if candles is None:

        return None

    if len(candles) != CANDLES_PER_M1:

        print(
            "[STRATEGY] No se recibieron exactamente 12 velas."
        )

        return None

    # ========================================================
    # PRIMERAS 6
    # ========================================================

    first_6 = candles[
        :STRATEGY_CANDLES
    ]

    if len(first_6) != STRATEGY_CANDLES:

        print(
            "[STRATEGY] No existen exactamente "
            "6 velas para analizar."
        )

        return None

    # ========================================================
    # VERIFICACIÓN DE TIMESTAMPS
    # ========================================================

    for index, candle in enumerate(
        first_6
    ):

        expected_offset = (
            index * 5
        )

        expected_timestamp = (
            candles[0]["from"]
            + expected_offset
        )

        if candle["from"] != expected_timestamp:

            print(
                "[STRATEGY] Secuencia incorrecta "
                "en las primeras 6 velas."
            )

            return None

    # ========================================================
    # MOSTRAR EXACTAMENTE LAS QUE USA STRATEGY.PY
    # ========================================================

    print()
    print("======================================")
    print("VELAS USADAS POR STRATEGY.PY")
    print("======================================")

    print(
        "SOLO PRIMERAS 6 VELAS DE 5S"
    )

    print(
        "Periodo: "
        f"{datetime.fromtimestamp(first_6[0]['from']).strftime('%H:%M:%S')}"
        " → "
        f"{datetime.fromtimestamp(first_6[-1]['from'] + 5).strftime('%H:%M:%S')}"
    )

    print(
        "--------------------------------------"
    )

    for index, candle in enumerate(
        first_6,
        start=1
    ):

        timestamp = int(
            candle["from"]
        )

        dt = datetime.fromtimestamp(
            timestamp
        )

        open_price = candle["open"]
        close_price = candle["close"]

        if close_price > open_price:

            symbol = "🟢"
            direction = "VERDE"

        elif close_price < open_price:

            symbol = "🔴"
            direction = "ROJA"

        else:

            symbol = "⚪"
            direction = "DOJI"

        print(
            f"{index:02d} | "
            f"{dt.strftime('%H:%M:%S')} | "
            f"{symbol} {direction} | "
            f"O={open_price} | "
            f"C={close_price}"
        )

    print(
        "--------------------------------------"
    )

    return first_6


# ============================================================
# ANALIZAR STRATEGY.PY
# ============================================================

def analyze_strategy(
    candles
):

    if candles is None:

        return None

    if len(candles) != CANDLES_PER_M1:

        print(
            "[STRATEGY] Se esperaban "
            f"{CANDLES_PER_M1} velas completas."
        )

        return None

    # ========================================================
    # IMPORTANTE:
    #
    # BOT.PY recibe 12 para comprobar la M1,
    # pero strategy.py recibe SOLO las primeras 6.
    # ========================================================

    strategy_candles = get_strategy_candles(
        candles
    )

    if strategy_candles is None:

        return None

    print()
    print(
        "Analizando SOLO las primeras 6 velas..."
    )

    try:

        signal = check_pattern(
            strategy_candles
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

def normalize_signal(
    signal
):

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

def execute_trade(
    iq,
    signal
):

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

        print(
            "🟢 CALL"
        )

    else:

        print(
            "🔴 PUT"
        )

    print(
        f"Activo      : {PAIR}"
    )

    print(
        f"Monto       : {AMOUNT}"
    )

    print(
        f"Expiración  : {EXPIRATION} minuto"
    )

    print(
        "======================================"
    )

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

def print_result(
    result
):

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

    print()
    print("==========================================")
    print("             BOT IQ OPTION")
    print("==========================================")

    print(
        f"ACTIVO          : {PAIR}"
    )

    print(
        f"MONTO           : {AMOUNT}"
    )

    print(
        f"EXPIRACIÓN      : {EXPIRATION}M"
    )

    print(
        f"VELAS M1        : {CANDLES_PER_M1}"
    )

    print(
        f"VELAS ESTRATEGIA: {STRATEGY_CANDLES}"
    )

    print(
        "ESTRATEGIA      : strategy.py"
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
            # COMPROBAR CONEXIÓN
            # =================================================

            if not ensure_connection(
                iq
            ):

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

            m1_end = (
                m1_start + 60
            )

            # =================================================
            # MOSTRAR CORRECTAMENTE EL BLOQUE
            # =================================================

            print()
            print("======================================")
            print("M1 CERRADA")
            print("======================================")

            print(
                "M1 ANALIZADA:"
            )

            print(
                f"{datetime.fromtimestamp(m1_start).strftime('%H:%M:%S')}"
                " → "
                f"{datetime.fromtimestamp(m1_end).strftime('%H:%M:%S')}"
            )

            print(
                "======================================"
            )

            # =================================================
            # OBTENER LAS 12 VELAS
            # =================================================

            candles = None

            for attempt in range(5):

                print(
                    f"[M1] Esperando datos... "
                    f"intento {attempt + 1}/5"
                )

                candles = get_m1_5s_candles(
                    iq,
                    m1_start
                )

                if candles is not None:

                    break

                time.sleep(1)

            # =================================================
            # MARCAR COMO PROCESADA
            #
            # IMPORTANTE:
            # Aunque falle la descarga, no volvemos a analizar
            # la misma M1 infinitamente.
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
                    f"{PAIR}\n"
                    "Datos 5s incompletos."
                )

                continue

            # =================================================
            # MOSTRAR LAS 12
            # =================================================

            print_m1_candles(
                candles,
                m1_start
            )

            # =================================================
            # ANALIZAR
            # =================================================

            print()
            print("======================================")
            print("RESULTADO DE STRATEGY.PY")
            print("======================================")

            signal = analyze_strategy(
                candles
            )

            signal = normalize_signal(
                signal
            )

            print(
                "--------------------------------------"
            )

            # =================================================
            # RESULTADO
            # =================================================

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

            print(
                "======================================"
            )

            # =================================================
            # SIN SEÑAL
            # =================================================

            if signal is None:

                print(
                    "M1 descartada: "
                    "STRATEGY_NO_GENERO_SEÑAL"
                )

                send_telegram(
                    "⚪ SIN OPERACIÓN\n"
                    f"{PAIR}\n"
                    "strategy.py no generó CALL/PUT."
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

            # =================================================
            # RESULTADO
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

            print()
            print("======================================")
            print("ERROR GENERAL")
            print("======================================")

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
