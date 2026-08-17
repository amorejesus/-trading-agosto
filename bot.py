import os
import time
import requests
from datetime import datetime

from iqoptionapi.stable_api import IQ_Option
import strategy


PAIR = "EURUSD-OTC"
AMOUNT = 555
EXPIRATION = 1

TIMEFRAME_5S = 5
CANDLES_PER_M1 = 12

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_TOKEN}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": str(message),
            },
            timeout=10,
        )

        if not response.ok:
            print(
                f"[TELEGRAM] HTTP {response.status_code}"
            )

    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")


def verify_strategy():
    print("\n======================================")
    print("VERIFICANDO STRATEGY.PY")
    print("======================================")
    print(
        f"Archivo: "
        f"{getattr(strategy, '__file__', 'desconocido')}"
    )

    required = (
        "check_pattern",
        "get_m1_direction",
        "get_strategy_analysis",
    )

    for name in required:
        if not callable(getattr(strategy, name, None)):
            raise RuntimeError(
                f"strategy.py no contiene la función '{name}'."
            )
        print(f"✓ {name}() encontrada")

    print("✓ STRATEGY.PY COMPATIBLE")
    print("======================================\n")


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

            iq = IQ_Option(EMAIL, PASSWORD)
            check, reason = iq.connect()

            if check:
                print("✓ CONEXIÓN EXITOSA")

                try:
                    iq.change_balance("PRACTICE")
                    print("✓ CUENTA PRACTICE")
                except Exception as e:
                    print(
                        f"⚠ No se pudo cambiar a PRACTICE: {e}"
                    )

                send_telegram(
                    "🤖 BOT CONECTADO\n"
                    f"Activo: {PAIR}\n"
                    "Cuenta: PRACTICE"
                )

                return iq

            print(f"✗ Error de conexión: {reason}")

        except Exception as e:
            print(f"✗ Error conectando: {e}")

        print("Reintentando en 5 segundos...")
        time.sleep(5)


def ensure_connection(iq):
    try:
        if iq.check_connect():
            return True
    except Exception:
        pass

    print("\n⚠ CONEXIÓN PERDIDA")

    try:
        check, reason = iq.connect()

        if check:
            print("✓ CONEXIÓN RESTAURADA")
            return True

        print(f"✗ No se pudo reconectar: {reason}")

    except Exception as e:
        print(f"✗ Error reconectando: {e}")

    return False


def get_current_minute():
    now = int(time.time())
    return now - (now % 60)


def wait_for_new_m1(last_m1=None):
    while True:
        current_m1 = get_current_minute()

        if last_m1 is None:
            return current_m1 - 60

        if current_m1 > last_m1:
            return current_m1 - 60

        time.sleep(0.2)


def get_m1_5s_candles(iq, m1_start):
    m1_end = m1_start + 60

    try:
        candles = iq.get_candles(
            PAIR,
            TIMEFRAME_5S,
            20,
            m1_end,
        )
    except Exception as e:
        print(f"[CANDLES] Error: {e}")
        return None

    if not candles:
        print("[CANDLES] API no devolvió datos.")
        return None

    valid = []

    for candle in candles:
        try:
            timestamp = int(candle.get("from"))
        except Exception:
            continue

        if m1_start <= timestamp < m1_end:
            valid.append(candle)

    try:
        valid.sort(key=lambda x: int(x["from"]))
    except Exception:
        return None

    if len(valid) != CANDLES_PER_M1:
        print(
            f"[M1] Velas encontradas: "
            f"{len(valid)}/{CANDLES_PER_M1}"
        )
        return None

    timestamps = []

    for candle in valid:
        try:
            timestamps.append(int(candle["from"]))
        except Exception:
            return None

    for i in range(1, len(timestamps)):
        difference = timestamps[i] - timestamps[i - 1]

        if difference != TIMEFRAME_5S:
            print(
                "[M1] SECUENCIA INVALIDA: "
                f"diferencia={difference}s"
            )
            return None

    return valid


def print_m1_candles(candles):
    print("\n--------------------------------------")
    print("12 VELAS DE 5S")
    print("--------------------------------------")

    for index, candle in enumerate(candles, start=1):
        try:
            timestamp = int(candle["from"])
            dt = datetime.fromtimestamp(timestamp)

            open_price = float(candle["open"])
            close_price = float(candle["close"])

        except Exception:
            print(f"{index:02d} | VELA INVALIDA")
            continue

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
            f"O={open_price} | C={close_price}"
        )

    print("--------------------------------------")


def analyze_strategy(candles):
    try:
        return strategy.check_pattern(candles)
    except Exception as e:
        print(f"[STRATEGY] Error: {e}")
        return None


def get_full_analysis(candles):
    try:
        return strategy.get_strategy_analysis(candles)
    except Exception as e:
        print(f"[ANALYSIS] Error: {e}")
        return None


def normalize_signal(signal):
    if not isinstance(signal, str):
        return None

    signal = signal.strip().lower()

    if signal in ("call", "put"):
        return signal

    return None


def print_analysis(analysis):
    if analysis is None:
        return

    print("\n========================================")
    print("       ANALISIS MATEMATICO")
    print("========================================")

    dominant = analysis.get("dominant")

    print(
        f"Dominante              : "
        f"{str(dominant).upper() if dominant else 'NINGUNO'}"
    )

    print(
        f"Fuerza verde           : "
        f"{analysis.get('green_force', 0):.8f}"
    )

    print(
        f"Fuerza roja            : "
        f"{analysis.get('red_force', 0):.8f}"
    )

    print(
        f"Ratio verde            : "
        f"{analysis.get('green_ratio', 0):.4f}"
    )

    print(
        f"Ratio rojo             : "
        f"{analysis.get('red_ratio', 0):.4f}"
    )

    print(
        f"Margen dominante       : "
        f"{analysis.get('dominance_margin', 0):.4f}"
    )

    print(
        f"Desplazamiento         : "
        f"{analysis.get('displacement_ratio', 0):.4f}"
    )

    print(
        f"Posicion cierre        : "
        f"{analysis.get('close_position', 0.5):.4f}"
    )

    print(
        f"Fuerza final dominante : "
        f"{analysis.get('final_dominant_ratio', 0):.4f}"
    )

    print("----------------------------------------")

    print(
        f"Dominancia OK          : "
        f"{analysis.get('dominance_ok', False)}"
    )

    print(
        f"Desplazamiento OK      : "
        f"{analysis.get('displacement_ok', False)}"
    )

    print(
        f"Cierre OK              : "
        f"{analysis.get('close_ok', False)}"
    )

    print(
        f"Fuerza final OK        : "
        f"{analysis.get('final_strength_ok', False)}"
    )

    print("----------------------------------------")

    print(
        f"MARKET OK              : "
        f"{analysis.get('market_ok', False)}"
    )

    print(
        f"MOTIVO                 : "
        f"{analysis.get('reason', 'DESCONOCIDO')}"
    )

    print("========================================")


def execute_trade(iq, signal):
    signal = normalize_signal(signal)

    if signal not in ("call", "put"):
        print("[TRADE] Sin señal válida.")
        return False, None

    print("\n======================================")
    print("SEÑAL CONFIRMADA")
    print("======================================")
    print(f"Dirección  : {signal.upper()}")
    print(f"Activo     : {PAIR}")
    print(f"Monto      : {AMOUNT}")
    print(f"Expiración : {EXPIRATION}M")
    print("======================================")

    try:
        success, order_id = iq.buy(
            AMOUNT,
            PAIR,
            signal,
            EXPIRATION,
        )

        if success:
            print(
                f"✓ OPERACIÓN ABIERTA ID={order_id}"
            )

            send_telegram(
                "📊 OPERACIÓN ABIERTA\n\n"
                f"Activo: {PAIR}\n"
                f"Dirección: {signal.upper()}\n"
                f"Monto: {AMOUNT}\n"
                f"Expiración: {EXPIRATION}M"
            )

            return True, order_id

        print("✗ IQ Option rechazó la operación.")
        return False, None

    except Exception as e:
        print(f"✗ Error ejecutando operación: {e}")
        return False, None


def get_trade_result(iq, order_id):
    if not order_id:
        return None

    wait_seconds = EXPIRATION * 60 + 5

    print(
        f"\nEsperando resultado ({wait_seconds}s)..."
    )

    time.sleep(wait_seconds)

    try:
        result = iq.check_win_v4(order_id)

        if result is not None:
            return float(result)

    except Exception as e:
        print(f"[RESULTADO] Error: {e}")

    return None


def print_result(result):
    if result is None:
        print("\n⚠ RESULTADO NO DISPONIBLE")
        return

    if result > 0:
        print("\n🟢 WIN")
        print(f"Resultado: +{result}")
        send_telegram(
            "🟢 WIN\n"
            f"Resultado: +{result}"
        )

    elif result < 0:
        print("\n🔴 LOSS")
        print(f"Resultado: {result}")
        send_telegram(
            "🔴 LOSS\n"
            f"Resultado: {result}"
        )

    else:
        print("\n⚪ EMPATE")
        print(f"Resultado: {result}")
        send_telegram(
            "⚪ EMPATE\n"
            f"Resultado: {result}"
        )


def main():
    print("\n")
    print("==========================================")
    print("             BOT IQ OPTION")
    print("        M1 + 12 VELAS DE 5S")
    print("==========================================")
    print(f"ACTIVO       : {PAIR}")
    print(f"MONTO        : {AMOUNT}")
    print(f"EXPIRACIÓN   : {EXPIRATION}M")
    print(f"MICROVELAS   : {CANDLES_PER_M1}")
    print("ESTRATEGIA   : strategy.py")
    print("==========================================")

    verify_strategy()

    iq = connect_iq()

    last_processed_m1 = None
    operation_in_progress = False

    while True:
        try:
            if not ensure_connection(iq):
                time.sleep(5)
                iq = connect_iq()
                continue

            m1_start = wait_for_new_m1(
                last_processed_m1
            )

            if last_processed_m1 == m1_start:
                time.sleep(0.2)
                continue

            print("\n")
            print("======================================")
            print("M1 CERRADA")
            print(
                datetime.fromtimestamp(
                    m1_start
                ).strftime("%Y-%m-%d %H:%M:%S")
            )
            print("======================================")

            candles = None

            for attempt in range(5):
                candles = get_m1_5s_candles(
                    iq,
                    m1_start
                )

                if candles is not None:
                    break

                print(
                    f"[M1] Esperando datos... "
                    f"intento {attempt + 1}/5"
                )

                time.sleep(1)

            last_processed_m1 = m1_start

            if candles is None:
                print("\n⚠ M1 DESCARTADA")
                print(
                    "No se obtuvieron exactamente "
                    "12 velas cerradas de 5s."
                )

                send_telegram(
                    "⚠ M1 DESCARTADA\n"
                    "Datos 5s incompletos."
                )

                continue

            print_m1_candles(candles)

            print(
                "\nAnalizando las 12 velas..."
            )

            analysis = get_full_analysis(candles)
            print_analysis(analysis)

            signal = normalize_signal(
                analyze_strategy(candles)
            )

            print("\n--------------------------------------")
            print("RESULTADO DE STRATEGY.PY")
            print("--------------------------------------")

            if signal == "call":
                print("🟢 DIRECCIÓN: CALL")
            elif signal == "put":
                print("🔴 DIRECCIÓN: PUT")
            else:
                print("⚪ SIN OPERACIÓN")

            print("--------------------------------------")

            if signal is None:
                reason = "CONDICIONES_NO_CUMPLIDAS"

                if analysis is not None:
                    reason = analysis.get(
                        "reason",
                        reason
                    )

                print(
                    f"M1 descartada: {reason}"
                )

                send_telegram(
                    "⚪ SIN OPERACIÓN\n"
                    f"Activo: {PAIR}\n"
                    f"Motivo: {reason}"
                )

                continue

            if operation_in_progress:
                print(
                    "⚠ Ya existe una operación en progreso."
                )
                continue

            success, order_id = execute_trade(
                iq,
                signal
            )

            if not success:
                continue

            operation_in_progress = True

            result = get_trade_result(
                iq,
                order_id
            )

            print_result(result)

            operation_in_progress = False

        except KeyboardInterrupt:
            print(
                "\n\nBOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT DETENIDO"
            )

            break

        except Exception as e:
            print("\n======================================")
            print("ERROR GENERAL")
            print("======================================")
            print(str(e))
            print("======================================")

            send_telegram(
                "⚠ ERROR EN BOT\n"
                f"{str(e)}"
            )

            time.sleep(3)


if __name__ == "__main__":
    main()
