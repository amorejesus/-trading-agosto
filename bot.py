import os
import time
import requests
from datetime import datetime

from iqoptionapi.stable_api import IQ_Option
import strategy


# ============================================================
# CONFIGURACIÓN
# ============================================================

PAIRS = [
    "EURUSD-OTC",
    "EURJPY-OTC",
    "EURGBP-OTC",
    "GBPUSD-OTC",
]

AMOUNT = 30
EXPIRATION = 1

TIMEFRAME_M1 = 60
CANDLES_REQUIRED_M1 = 3

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


# ============================================================
# VERIFICAR STRATEGY.PY
# ============================================================

def verify_strategy():
    print("\n======================================")
    print("VERIFICANDO STRATEGY.PY")
    print("======================================")

    print(
        "Archivo: "
        + str(
            getattr(
                strategy,
                "__file__",
                "desconocido",
            )
        )
    )

    required = (
        "check_pattern",
        "get_m1_direction",
        "get_strategy_analysis",
    )

    for name in required:
        if not callable(
            getattr(strategy, name, None)
        ):
            raise RuntimeError(
                f"strategy.py no contiene "
                f"la función '{name}'."
            )

        print(f"✓ {name}() encontrada")

    print("✓ STRATEGY.PY COMPATIBLE")
    print("======================================\n")


# ============================================================
# CONEXIÓN
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
                PASSWORD,
            )

            check, reason = iq.connect()

            if check:
                print("✓ CONEXIÓN EXITOSA")

                try:
                    iq.change_balance("PRACTICE")
                    print("✓ CUENTA PRACTICE")

                except Exception as e:
                    print(
                        "⚠ No se pudo cambiar "
                        f"a PRACTICE: {e}"
                    )

                send_telegram(
                    "🤖 BOT CONECTADO\n"
                    "Modo: SNIPER M1 N+1\n"
                    "Mercado: OTC\n"
                    "Importe: 30\n"
                    "Expiración: 1M\n"
                    "Pares: EURUSD-OTC, EURJPY-OTC, "
                    "EURGBP-OTC, GBPUSD-OTC"
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

    print("\n⚠ CONEXIÓN PERDIDA")

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
# TIEMPO M1
# ============================================================

def get_current_minute():
    now = int(time.time())

    return now - (
        now % TIMEFRAME_M1
    )


def wait_for_next_minute(last_timestamp):
    while True:
        current = get_current_minute()

        if current > last_timestamp:
            return current

        time.sleep(0.01)


# ============================================================
# ESPERAR CIERRE REAL DE N
# ============================================================

def wait_for_candle_close(
    iq,
    pair,
    candle_timestamp,
):
    """
    candle_timestamp = apertura de la vela N+1.

    La vela N corresponde a:

        candle_timestamp - 60

    No se analiza hasta comprobar que N
    ya terminó.
    """

    expected_closed_timestamp = (
        candle_timestamp - TIMEFRAME_M1
    )

    deadline = time.time() + 8

    while time.time() < deadline:

        try:
            candles = iq.get_candles(
                pair,
                TIMEFRAME_M1,
                CANDLES_REQUIRED_M1,
                candle_timestamp,
            )

        except Exception as e:
            print(
                f"[{pair}] Error obteniendo M1: {e}"
            )

            time.sleep(0.05)
            continue

        if not candles:
            time.sleep(0.05)
            continue

        valid = []

        for candle in candles:
            try:
                timestamp = int(
                    candle.get("from")
                )

            except Exception:
                continue

            valid.append(
                (
                    timestamp,
                    candle,
                )
            )

        valid.sort(
            key=lambda x: x[0]
        )

        for timestamp, candle in reversed(valid):

            if timestamp == expected_closed_timestamp:

                print(
                    f"[{pair}] ✓ VELA N CERRADA"
                )

                return candle

        time.sleep(0.05)

    print(
        f"[{pair}] ⚠ No se confirmó "
        f"el cierre de N."
    )

    return None


# ============================================================
# OBTENER M1 CERRADA
# ============================================================

def get_closed_m1_candles(
    iq,
    pair,
    next_candle_timestamp,
):
    """
    Obtiene exclusivamente información M1.

    La vela N:

        next_candle_timestamp - 60

    es la vela que acaba de cerrar.
    """

    expected_n = (
        next_candle_timestamp
        - TIMEFRAME_M1
    )

    try:
        candles = iq.get_candles(
            pair,
            TIMEFRAME_M1,
            CANDLES_REQUIRED_M1,
            next_candle_timestamp,
        )

    except Exception as e:
        print(
            f"[{pair}] Error API M1: {e}"
        )
        return None

    if not candles:
        print(
            f"[{pair}] API no devolvió M1."
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

        valid.append(
            (
                timestamp,
                candle,
            )
        )

    valid.sort(
        key=lambda x: x[0]
    )

    closed = []

    for timestamp, candle in valid:

        if timestamp < next_candle_timestamp:
            closed.append(candle)

    if not closed:
        print(
            f"[{pair}] No hay M1 cerradas."
        )
        return None

    found_n = False

    for candle in closed:

        try:
            timestamp = int(
                candle.get("from")
            )

        except Exception:
            continue

        if timestamp == expected_n:
            found_n = True
            break

    if not found_n:
        print(
            f"[{pair}] No se encontró "
            f"la vela N esperada."
        )
        return None

    return closed


# ============================================================
# IMPRIMIR VELA M1
# ============================================================

def print_m1_candle(
    pair,
    candle,
):
    try:
        timestamp = int(
            candle["from"]
        )

        dt = datetime.fromtimestamp(
            timestamp
        )

        opening = float(
            candle["open"]
        )

        high = float(
            candle.get(
                "max",
                candle.get("high"),
            )
        )

        low = float(
            candle.get(
                "min",
                candle.get("low"),
            )
        )

        closing = float(
            candle["close"]
        )

    except Exception:
        print(
            f"[{pair}] VELA M1 INVALIDA"
        )
        return

    if closing > opening:
        direction = "VERDE"
        symbol = "🟢"

    elif closing < opening:
        direction = "ROJA"
        symbol = "🔴"

    else:
        direction = "DOJI"
        symbol = "⚪"

    print(
        f"[{pair}] "
        f"{dt.strftime('%H:%M:%S')} | "
        f"{symbol} {direction} | "
        f"O={opening} | "
        f"H={high} | "
        f"L={low} | "
        f"C={closing}"
    )


# ============================================================
# ANÁLISIS
# ============================================================

def get_full_analysis(candles):
    try:
        return strategy.get_strategy_analysis(
            candles
        )

    except Exception as e:
        print(
            f"[ANALYSIS] Error: {e}"
        )
        return None


def analyze_strategy(candles):
    try:
        return strategy.check_pattern(
            candles
        )

    except Exception as e:
        print(
            f"[STRATEGY] Error: {e}"
        )
        return None


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(signal):
    if not isinstance(signal, str):
        return None

    signal = signal.strip().lower()

    if signal in (
        "call",
        "put",
    ):
        return signal

    return None


# ============================================================
# MOSTRAR ANÁLISIS
# ============================================================

def print_analysis(
    pair,
    analysis,
):
    if analysis is None:
        return

    print("\n--------------------------------------")
    print(
        f"ANÁLISIS M1 - {pair}"
    )
    print("--------------------------------------")

    print(
        f"Estado        : "
        f"{str(analysis.get('state')).upper()}"
    )

    print(
        f"Dirección     : "
        f"{str(analysis.get('direction')).upper()}"
    )

    print(
        f"Cuerpo        : "
        f"{analysis.get('body')}"
    )

    print(
        f"Ratio cuerpo  : "
        f"{analysis.get('body_ratio')}"
    )

    print(
        f"Mecha superior: "
        f"{analysis.get('upper_wick')}"
    )

    print(
        f"Mecha inferior: "
        f"{analysis.get('lower_wick')}"
    )

    print(
        f"Posición cierre: "
        f"{analysis.get('close_position')}"
    )

    print(
        f"Señal N+1     : "
        f"{str(analysis.get('signal')).upper()}"
    )

    print(
        f"Motivo        : "
        f"{analysis.get('reason')}"
    )

    print("--------------------------------------")


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(
    iq,
    pair,
    next_candle_timestamp,
):
    """
    Analiza N cuando N ya terminó.

    next_candle_timestamp es exactamente
    la apertura de N+1.
    """

    candles = get_closed_m1_candles(
        iq,
        pair,
        next_candle_timestamp,
    )

    if candles is None:
        print(
            f"[{pair}] ⚪ SIN DATOS M1"
        )
        return None

    candle_n = None

    expected_n = (
        next_candle_timestamp
        - TIMEFRAME_M1
    )

    for candle in candles:

        try:
            timestamp = int(
                candle["from"]
            )

        except Exception:
            continue

        if timestamp == expected_n:
            candle_n = candle
            break

    if candle_n is None:
        print(
            f"[{pair}] ⚪ No se encontró N."
        )
        return None

    print_m1_candle(
        pair,
        candle_n,
    )

    print(
        f"[{pair}] Analizando "
        f"VELA N CERRADA..."
    )

    analysis = get_full_analysis(
        candles
    )

    print_analysis(
        pair,
        analysis,
    )

    signal = normalize_signal(
        analyze_strategy(candles)
    )

    if signal is None:
        print(
            f"[{pair}] ⚪ SIN OPERACIÓN N+1"
        )
        return None

    if signal == "call":
        print(
            f"[{pair}] 🟢 CALL → N+1"
        )

    else:
        print(
            f"[{pair}] 🔴 PUT → N+1"
        )

    return signal


# ============================================================
# EJECUTAR SNIPER N+1
# ============================================================

def execute_trade(
    iq,
    pair,
    signal,
):
    signal = normalize_signal(
        signal
    )

    if signal not in (
        "call",
        "put",
    ):
        return False, None

    print(
        f"🚀 [{pair}] "
        f"ENTRADA N+1 → "
        f"{signal.upper()}"
    )

    try:
        success, order_id = iq.buy(
            AMOUNT,
            pair,
            signal,
            EXPIRATION,
        )

        if success:

            print(
                f"✓ [{pair}] "
                f"OPERACIÓN ABIERTA "
                f"ID={order_id}"
            )

            send_telegram(
                "🎯 SNIPER M1 N+1\n\n"
                f"Activo: {pair}\n"
                f"Dirección: {signal.upper()}\n"
                f"Importe: {AMOUNT}\n"
                f"Expiración: {EXPIRATION}M"
            )

            return True, order_id

        print(
            f"✗ [{pair}] "
            "IQ Option rechazó la operación."
        )

        return False, None

    except Exception as e:
        print(
            f"✗ [{pair}] "
            f"Error ejecutando: {e}"
        )

        return False, None


# ============================================================
# RESULTADO
# ============================================================

def get_trade_result(
    iq,
    order_id,
):
    if not order_id:
        return None

    wait_seconds = (
        EXPIRATION * 60 + 5
    )

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


def print_result(
    pair,
    result,
):
    if result is None:
        print(
            f"[{pair}] "
            "⚠ RESULTADO NO DISPONIBLE"
        )
        return

    if result > 0:

        print(
            f"🟢 WIN | {pair} | "
            f"+{result}"
        )

        send_telegram(
            "🟢 WIN\n"
            f"Activo: {pair}\n"
            f"Resultado: +{result}"
        )

    elif result < 0:

        print(
            f"🔴 LOSS | {pair} | "
            f"{result}"
        )

        send_telegram(
            "🔴 LOSS\n"
            f"Activo: {pair}\n"
            f"Resultado: {result}"
        )

    else:

        print(
            f"⚪ EMPATE | {pair} | "
            f"{result}"
        )

        send_telegram(
            "⚪ EMPATE\n"
            f"Activo: {pair}\n"
            f"Resultado: {result}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print(
        "=========================================="
    )
    print(
        "       BOT IQ OPTION SNIPER M1"
    )
    print(
        "             MODO N+1"
    )
    print(
        "=========================================="
    )

    print(
        "MERCADO      : OTC"
    )

    print(
        f"IMPORTE      : {AMOUNT}"
    )

    print(
        f"EXPIRACIÓN   : {EXPIRATION} MINUTO"
    )

    print(
        "TIMEFRAME    : M1"
    )

    print(
        "ENTRADA       : APERTURA N+1"
    )

    print(
        "=========================================="
    )

    for pair in PAIRS:
        print(f"✓ {pair}")

    print(
        "=========================================="
    )

    verify_strategy()

    iq = connect_iq()

    last_minute = (
        get_current_minute()
        - TIMEFRAME_M1
    )

    while True:

        try:

            # ------------------------------------------------
            # CONEXIÓN
            # ------------------------------------------------

            if not ensure_connection(iq):

                time.sleep(2)

                iq = connect_iq()

                continue

            # ------------------------------------------------
            # ESPERAR APERTURA DE N+1
            # ------------------------------------------------

            next_candle = (
                wait_for_next_minute(
                    last_minute
                )
            )

            last_minute = next_candle

            next_dt = datetime.fromtimestamp(
                next_candle
            )

            print("\n")
            print(
                "=========================================="
            )

            print(
                "🔔 CIERRE DE N / APERTURA DE N+1"
            )

            print(
                next_dt.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            # ------------------------------------------------
            # ANALIZAR TODAS LAS VELAS N CERRADAS
            # ------------------------------------------------

            signals = []

            for pair in PAIRS:

                try:

                    signal = process_pair(
                        iq,
                        pair,
                        next_candle,
                    )

                    if signal is not None:

                        signals.append(
                            (
                                pair,
                                signal,
                            )
                        )

                except Exception as e:

                    print(
                        f"[{pair}] "
                        f"Error procesando: {e}"
                    )

            # ------------------------------------------------
            # SIN SEÑALES
            # ------------------------------------------------

            if not signals:

                print(
                    "\n⚪ NINGÚN PAR "
                    "CUMPLIÓ LAS CONDICIONES."
                )

                continue

            # ------------------------------------------------
            # SEÑALES CONFIRMADAS
            # ------------------------------------------------

            print("\n")
            print(
                "=========================================="
            )

            print(
                "🎯 SEÑALES CONFIRMADAS PARA N+1"
            )

            print(
                "=========================================="
            )

            for pair, signal in signals:

                print(
                    f"{pair} → "
                    f"{signal.upper()}"
                )

            print(
                "=========================================="
            )

            # ------------------------------------------------
            # EJECUCIÓN INMEDIATA N+1
            # ------------------------------------------------

            print(
                "\n🚀 EJECUTANDO "
                "EN APERTURA DE N+1..."
            )

            opened_trades = []

            for pair, signal in signals:

                try:

                    success, order_id = (
                        execute_trade(
                            iq,
                            pair,
                            signal,
                        )
                    )

                    if success:

                        opened_trades.append(
                            (
                                pair,
                                order_id,
                            )
                        )

                except Exception as e:

                    print(
                        f"[{pair}] "
                        f"Error operación: {e}"
                    )

            # ------------------------------------------------
            # RESULTADOS
            # ------------------------------------------------
            #
            # IMPORTANTE:
            # Todas las órdenes se intentan abrir primero.
            # Solo después esperamos resultados.
            #
            # Así una operación no bloquea la entrada
            # de otro par.
            # ------------------------------------------------

            if opened_trades:

                print(
                    "\n=========================================="
                )

                print(
                    "⏳ ESPERANDO RESULTADOS"
                )

                print(
                    "=========================================="
                )

                for pair, order_id in (
                    opened_trades
                ):

                    try:

                        result = (
                            get_trade_result(
                                iq,
                                order_id,
                            )
                        )

                        print_result(
                            pair,
                            result,
                        )

                    except Exception as e:

                        print(
                            f"[{pair}] "
                            f"Error resultado: {e}"
                        )

        # ----------------------------------------------------
        # DETENER
        # ----------------------------------------------------

        except KeyboardInterrupt:

            print(
                "\n\n"
                "🛑 BOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT SNIPER M1 N+1 DETENIDO"
            )

            break

        # ----------------------------------------------------
        # ERROR GENERAL
        # ----------------------------------------------------

        except Exception as e:

            print(
                "\n======================================"
            )

            print(
                "ERROR GENERAL"
            )

            print(
                "======================================"
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

            time.sleep(2)


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
