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
    "EURGBP-OTC",
    "EURJPY-OTC",
    "AUDUSD-OTC",
    "EURGBP-OTC",
]

AMOUNT = 9230
EXPIRATION = 1

TIMEFRAME_M1 = 60

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
        print(
            f"[TELEGRAM] Error: {e}"
        )


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
            getattr(
                strategy,
                name,
                None,
            )
        ):
            raise RuntimeError(
                "strategy.py no contiene "
                f"la función '{name}'."
            )

        print(
            f"✓ {name}() encontrada"
        )

    print(
        "✓ STRATEGY.PY COMPATIBLE"
    )

    print(
        "✓ ANÁLISIS EXCLUSIVO M1"
    )

    print(
        "✓ EJECUCIÓN EN N+1"
    )

    print(
        "======================================\n"
    )


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

            print(
                "\n======================================"
            )

            print(
                "CONECTANDO A IQ OPTION"
            )

            print(
                "======================================"
            )

            iq = IQ_Option(
                EMAIL,
                PASSWORD,
            )

            check, reason = iq.connect()

            if check:

                print(
                    "✓ CONEXIÓN EXITOSA"
                )

                try:

                    iq.change_balance(
                        "PRACTICE"
                    )

                    print(
                        "✓ CUENTA PRACTICE"
                    )

                except Exception as e:

                    print(
                        "⚠ No se pudo cambiar "
                        f"a PRACTICE: {e}"
                    )

                send_telegram(
                    "🤖 BOT CONECTADO\n"
                    "Modo: M1 → N+1\n"
                    "Mercado: FOREX REAL\n"
                    f"Pares: {len(PAIRS)}"
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
# CONEXIÓN
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
# TIEMPO M1
# ============================================================

def get_current_m1():

    now = int(time.time())

    return now - (
        now % TIMEFRAME_M1
    )


def wait_for_next_m1(last_m1):

    while True:

        current = get_current_m1()

        if current > last_m1:
            return current

        time.sleep(0.02)


# ============================================================
# OBTENER VELA M1 CERRADA
# ============================================================

def get_closed_m1_candle(
    iq,
    pair,
    candle_timestamp,
):

    try:

        candles = iq.get_candles(
            pair,
            TIMEFRAME_M1,
            2,
            candle_timestamp,
        )

    except Exception as e:

        print(
            f"[{pair}] Error obteniendo M1: {e}"
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

        if timestamp < candle_timestamp:

            valid.append(candle)

    if not valid:

        return None

    try:

        valid.sort(
            key=lambda x: int(
                x["from"]
            )
        )

    except Exception:

        return None

    candle = valid[-1]

    try:

        timestamp = int(
            candle["from"]
        )

        opening = float(
            candle["open"]
        )

        closing = float(
            candle["close"]
        )

        high = float(
            candle.get(
                "max",
                candle.get(
                    "high"
                )
            )
        )

        low = float(
            candle.get(
                "min",
                candle.get(
                    "low"
                )
            )
        )

    except Exception as e:

        print(
            f"[{pair}] M1 inválida: {e}"
        )

        return None

    return {
        "from": timestamp,
        "open": opening,
        "max": high,
        "min": low,
        "high": high,
        "low": low,
        "close": closing,
    }


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
                candle.get(
                    "high"
                )
            )
        )

        low = float(
            candle.get(
                "min",
                candle.get(
                    "low"
                )
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

        symbol = "🟢"

    elif closing < opening:

        symbol = "🔴"

    else:

        symbol = "⚪"

    candle_range = high - low
    body = abs(closing - opening)

    if candle_range > 0:

        body_ratio = (
            body / candle_range
        )

    else:

        body_ratio = 0.0

    print(
        f"[{pair}] "
        f"{dt.strftime('%H:%M:%S')} | "
        f"{symbol} M1 | "
        f"O={opening} | "
        f"H={high} | "
        f"L={low} | "
        f"C={closing} | "
        f"BODY={body_ratio:.2%}"
    )


# ============================================================
# ANALIZAR STRATEGY.PY
# ============================================================

def analyze_strategy(
    candle,
):

    try:

        return strategy.get_strategy_analysis(
            [candle]
        )

    except Exception as e:

        print(
            f"[STRATEGY] Error: {e}"
        )

        return None


def get_signal(
    candle,
):

    try:

        signal = strategy.check_pattern(
            [candle]
        )

        return normalize_signal(
            signal
        )

    except Exception as e:

        print(
            f"[STRATEGY] Error obteniendo señal: {e}"
        )

        return None


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(signal):

    if not isinstance(
        signal,
        str,
    ):
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

        print(
            f"[{pair}] Sin análisis."
        )

        return

    print(
        "\n--------------------------------------"
    )

    print(
        f"ANÁLISIS M1 — {pair}"
    )

    print(
        "--------------------------------------"
    )

    state = analysis.get(
        "state"
    )

    signal = normalize_signal(
        analysis.get(
            "signal"
        )
    )

    direction = analysis.get(
        "direction"
    )

    reason = analysis.get(
        "reason",
        "DESCONOCIDO",
    )

    print(
        "Estado          : "
        + str(
            state or "NINGUNO"
        ).upper()
    )

    print(
        "Dirección       : "
        + str(
            direction or "NEUTRAL"
        ).upper()
    )

    print(
        "Señal N+1       : "
        + str(
            signal or "NINGUNA"
        ).upper()
    )

    print(
        f"Open            : "
        f"{analysis.get('open')}"
    )

    print(
        f"High            : "
        f"{analysis.get('high')}"
    )

    print(
        f"Low             : "
        f"{analysis.get('low')}"
    )

    print(
        f"Close           : "
        f"{analysis.get('close')}"
    )

    print(
        f"Rango           : "
        f"{analysis.get('range')}"
    )

    print(
        f"Cuerpo          : "
        f"{analysis.get('body')}"
    )

    print(
        f"Ratio cuerpo    : "
        f"{analysis.get('body_ratio', 0):.4f}"
    )

    print(
        f"Mecha superior  : "
        f"{analysis.get('upper_wick')}"
    )

    print(
        f"Mecha inferior  : "
        f"{analysis.get('lower_wick')}"
    )

    print(
        f"Posición cierre : "
        f"{analysis.get('close_position')}"
    )

    print(
        f"Motivo          : "
        f"{reason}"
    )

    print(
        "--------------------------------------"
    )


# ============================================================
# EJECUTAR N+1
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

        print(
            f"[{pair}] Sin señal válida."
        )

        return False, None

    print(
        "\n======================================"
    )

    print(
        "🎯 EJECUCIÓN N+1"
    )

    print(
        "======================================"
    )

    print(
        f"Activo     : {pair}"
    )

    print(
        f"Dirección  : {signal.upper()}"
    )

    print(
        f"Monto      : {AMOUNT}"
    )

    print(
        f"Expiración : {EXPIRATION}M"
    )

    print(
        "Entrada     : APERTURA N+1"
    )

    print(
        "======================================"
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
                f"✓ OPERACIÓN ABIERTA "
                f"ID={order_id}"
            )

            send_telegram(
                "🎯 ENTRADA N+1\n\n"
                f"Activo: {pair}\n"
                f"Dirección: {signal.upper()}\n"
                f"Monto: {AMOUNT}\n"
                f"Expiración: {EXPIRATION}M"
            )

            return True, order_id

        print(
            f"✗ IQ Option rechazó "
            f"la operación en {pair}."
        )

        return False, None

    except Exception as e:

        print(
            f"✗ Error ejecutando "
            f"{pair}: {e}"
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

            return float(
                result
            )

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
            f"\n⚠ {pair} "
            "RESULTADO NO DISPONIBLE"
        )

        return

    if result > 0:

        print(
            f"\n🟢 WIN | {pair}"
        )

        print(
            f"Resultado: +{result}"
        )

        send_telegram(
            "🟢 WIN\n"
            f"Activo: {pair}\n"
            f"Resultado: +{result}"
        )

    elif result < 0:

        print(
            f"\n🔴 LOSS | {pair}"
        )

        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "🔴 LOSS\n"
            f"Activo: {pair}\n"
            f"Resultado: {result}"
        )

    else:

        print(
            f"\n⚪ EMPATE | {pair}"
        )

        print(
            f"Resultado: {result}"
        )

        send_telegram(
            "⚪ EMPATE\n"
            f"Activo: {pair}\n"
            f"Resultado: {result}"
        )


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(
    iq,
    pair,
    candle_timestamp,
):

    candle = get_closed_m1_candle(
        iq,
        pair,
        candle_timestamp,
    )

    if candle is None:

        print(
            f"[{pair}] "
            "No se pudo obtener M1 cerrada."
        )

        return None

    print_m1_candle(
        pair,
        candle,
    )

    analysis = analyze_strategy(
        candle
    )

    print_analysis(
        pair,
        analysis,
    )

    signal = get_signal(
        candle
    )

    if signal is None:

        print(
            f"[{pair}] ⚪ "
            "SIN OPERACIÓN N+1"
        )

        return None

    if signal == "call":

        print(
            f"[{pair}] 🟢 "
            "CALL → N+1"
        )

    else:

        print(
            f"[{pair}] 🔴 "
            "PUT → N+1"
        )

    return signal


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")

    print(
        "=========================================="
    )

    print(
        "          BOT IQ OPTION SNIPER"
    )

    print(
        "             M1 → N+1"
    )

    print(
        "=========================================="
    )

    print(
        "MERCADO      : FOREX REAL"
    )

    print(
        f"MONTO        : {AMOUNT}"
    )

    print(
        f"EXPIRACIÓN   : {EXPIRATION}M"
    )

    print(
        "TIMEFRAME    : 1M"
    )

    print(
        f"PARES        : {len(PAIRS)}"
    )

    print(
        "=========================================="
    )

    for pair in PAIRS:

        print(
            f"✓ {pair}"
        )

    print(
        "=========================================="
    )

    verify_strategy()

    iq = connect_iq()

    # La última vela cerrada antes de iniciar.
    last_m1 = (
        get_current_m1()
        - TIMEFRAME_M1
    )

    while True:

        try:

            if not ensure_connection(
                iq
            ):

                time.sleep(5)

                iq = connect_iq()

                continue

            # Esperar el cierre de una nueva M1.
            current_m1 = wait_for_next_m1(
                last_m1
            )

            last_m1 = current_m1

            print(
                "\n\n=========================================="
            )

            print(
                "🔔 CIERRE DE VELA N"
            )

            print(
                datetime.fromtimestamp(
                    current_m1
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            signals = []

            # ==================================================
            # ANALIZAR TODOS LOS PARES
            # ==================================================

            for pair in PAIRS:

                try:

                    signal = process_pair(
                        iq,
                        pair,
                        current_m1,
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

            # ==================================================
            # SIN SEÑALES
            # ==================================================

            if not signals:

                print(
                    "\n⚪ NINGÚN PAR "
                    "CUMPLIÓ LAS CONDICIONES."
                )

                continue

            # ==================================================
            # SEÑALES CONFIRMADAS
            # ==================================================

            print(
                "\n=========================================="
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

            # ==================================================
            # ESPERAR EXACTAMENTE APERTURA N+1
            # ==================================================

            next_m1 = (
                current_m1
                + TIMEFRAME_M1
            )

            print(
                "\n⏳ ESPERANDO APERTURA N+1..."
            )

            while True:

                remaining = (
                    next_m1
                    - time.time()
                )

                if remaining <= 0:

                    break

                time.sleep(
                    min(
                        0.005,
                        remaining,
                    )
                )

            # ==================================================
            # EJECUCIÓN
            # ==================================================

            print(
                "\n=========================================="
            )

            print(
                "🚀 APERTURA N+1"
            )

            print(
                datetime.fromtimestamp(
                    next_m1
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            for pair, signal in signals:

                try:

                    success, order_id = execute_trade(
                        iq,
                        pair,
                        signal,
                    )

                    if not success:

                        continue

                    result = get_trade_result(
                        iq,
                        order_id,
                    )

                    print_result(
                        pair,
                        result,
                    )

                except Exception as e:

                    print(
                        f"[{pair}] "
                        f"Error operación: {e}"
                    )

        except KeyboardInterrupt:

            print(
                "\n\nBOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT SNIPER M1 → N+1 "
                "DETENIDO"
            )

            break

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

            time.sleep(3)


if __name__ == "__main__":
    main()
