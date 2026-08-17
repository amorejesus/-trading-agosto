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
    "EURUSD",
    "AUDCHF",
    "AUDUSD",
    "EURGBP",
    "EURNZD",
    "GBPAUD",
    "GBPCAD",
    "GBPJPY",
    "GBPNZD",
    "GBPUSD",
    "NZDUSD",
]

AMOUNT = 9230
EXPIRATION = 1

TIMEFRAME_5S = 5
CANDLES_REQUIRED = 12

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
                f"strategy.py no contiene la función "
                f"'{name}'."
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
                        "⚠ No se pudo cambiar a PRACTICE: "
                        + str(e)
                    )

                send_telegram(
                    "🤖 BOT CONECTADO\n"
                    "Modo: SNIPER N+1\n"
                    "Mercado: FOREX\n"
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
# TIEMPO
# ============================================================

def get_current_5s():
    now = int(time.time())

    return now - (
        now % TIMEFRAME_5S
    )


def wait_for_new_5s(last_timestamp):
    while True:
        current = get_current_5s()

        if current > last_timestamp:
            return current

        time.sleep(0.02)


# ============================================================
# OBTENER VELAS 5S
# ============================================================

def get_5s_candles(
    iq,
    pair,
    end_timestamp,
    amount=CANDLES_REQUIRED,
):
    try:
        candles = iq.get_candles(
            pair,
            TIMEFRAME_5S,
            amount,
            end_timestamp,
        )

    except Exception as e:
        print(
            f"[{pair}] Error obteniendo velas: {e}"
        )
        return None

    if not candles:
        print(
            f"[{pair}] API no devolvió datos."
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

        if timestamp <= 0:
            continue

        valid.append(candle)

    if not valid:
        return None

    try:
        valid.sort(
            key=lambda x: int(x["from"])
        )

    except Exception:
        return None

    if len(valid) < amount:
        return None

    valid = valid[-amount:]

    timestamps = []

    for candle in valid:
        try:
            timestamps.append(
                int(candle["from"])
            )

        except Exception:
            return None

    for i in range(1, len(timestamps)):
        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != TIMEFRAME_5S:
            print(
                f"[{pair}] SECUENCIA 5S INVALIDA: "
                f"{difference}s"
            )
            return None

    return valid


# ============================================================
# IMPRIMIR VELA
# ============================================================

def print_candle(pair, candle):
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

        closing = float(
            candle["close"]
        )

    except Exception:
        print(
            f"[{pair}] VELA INVALIDA"
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
        f"C={closing}"
    )


# ============================================================
# ANALIZAR STRATEGY.PY
# ============================================================

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
        return

    print("\n--------------------------------------")
    print(
        f"ANÁLISIS {pair}"
    )
    print("--------------------------------------")

    dominant = analysis.get(
        "dominant"
    )

    if dominant:
        dominant_text = str(
            dominant
        ).upper()

    else:
        dominant_text = "NINGUNO"

    print(
        f"Dominante       : "
        f"{dominant_text}"
    )

    print(
        f"Dominancia      : "
        f"{analysis.get('dominance_ratio', 0):.8f}"
    )

    print(
        f"Eficiencia      : "
        f"{analysis.get('efficiency', 0):.8f}"
    )

    final_control = analysis.get(
        "final_control"
    )

    if final_control is None:
        final_control_text = "NONE"

    else:
        final_control_text = str(
            final_control
        ).upper()

    print(
        f"Control final   : "
        f"{final_control_text}"
    )

    print(
        f"Cierre 5S      : "
        f"{analysis.get('last_5s_close')}"
    )

    print(
        f"Posición cierre : "
        f"{analysis.get('close_position')}"
    )

    print(
        f"Rango OK        : "
        f"{analysis.get('range_ok')}"
    )

    print(
        f"MARKET OK       : "
        f"{analysis.get('valid')}"
    )

    print(
        f"MOTIVO          : "
        f"{analysis.get('reason', 'DESCONOCIDO')}"
    )

    print("--------------------------------------")


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
        print(
            f"[{pair}] Sin señal válida."
        )
        return False, None

    print("\n======================================")
    print("🎯 SNIPER N+1")
    print("======================================")

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
        "Ejecución  : APERTURA N+1"
    )

    print("======================================")

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
                "🎯 SNIPER N+1\n\n"
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
        EXPIRATION * 60
        + 5
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
            f"\n⚠ {pair} "
            f"RESULTADO NO DISPONIBLE"
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
# PROCESAR UN PAR
# ============================================================

def process_pair(
    iq,
    pair,
    candle_timestamp,
):
    candles = get_5s_candles(
        iq,
        pair,
        candle_timestamp,
        CANDLES_REQUIRED,
    )

    if candles is None:
        print(
            f"[{pair}] "
            f"Datos 5S insuficientes."
        )
        return None

    candle_n = candles[-1]

    print_candle(
        pair,
        candle_n,
    )

    print(
        f"[{pair}] "
        f"Analizando cierre de N..."
    )

    analysis = get_full_analysis(
        candles
    )

    print_analysis(
        pair,
        analysis,
    )

    signal = normalize_signal(
        analyze_strategy(
            candles
        )
    )

    if signal is None:
        print(
            f"[{pair}] "
            f"⚪ SIN OPERACIÓN"
        )
        return None

    if signal == "call":
        print(
            f"[{pair}] "
            f"🟢 SEÑAL CALL → N+1"
        )

    else:
        print(
            f"[{pair}] "
            f"🔴 SEÑAL PUT → N+1"
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
        "             MODO N+1"
    )
    print(
        "=========================================="
    )

    print(
        "MERCADO      : FOREX"
    )

    print(
        f"MONTO        : {AMOUNT}"
    )

    print(
        f"EXPIRACIÓN   : {EXPIRATION}M"
    )

    print(
        f"TIMEFRAME    : {TIMEFRAME_5S}S"
    )

    print(
        f"VELAS        : {CANDLES_REQUIRED}"
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

    last_timestamp = (
        get_current_5s()
        - TIMEFRAME_5S
    )

    while True:
        try:
            if not ensure_connection(iq):
                time.sleep(5)
                iq = connect_iq()
                continue

            current_timestamp = (
                wait_for_new_5s(
                    last_timestamp
                )
            )

            last_timestamp = (
                current_timestamp
            )

            print(
                "\n\n=========================================="
            )

            print(
                "🔔 CIERRE DE VELA N"
            )

            print(
                datetime.fromtimestamp(
                    current_timestamp
                ).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            signals = []

            for pair in PAIRS:
                try:
                    signal = process_pair(
                        iq,
                        pair,
                        current_timestamp,
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
                        f"Error procesando: "
                        f"{e}"
                    )

            if not signals:
                print(
                    "\n⚪ Ningún par cumplió "
                    "las condiciones."
                )
                continue

            print(
                "\n=========================================="
            )

            print(
                "🎯 SEÑALES PARA N+1"
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

            next_candle = (
                current_timestamp
                + TIMEFRAME_5S
            )

            while True:
                now = time.time()

                remaining = (
                    next_candle
                    - now
                )

                if remaining <= 0:
                    break

                time.sleep(
                    min(
                        0.01,
                        remaining
                    )
                )

            print(
                "\n=========================================="
            )

            print(
                "🚀 APERTURA N+1"
            )

            print(
                datetime.fromtimestamp(
                    next_candle
                ).strftime(
                    "%H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            for pair, signal in signals:
                try:
                    success, order_id = (
                        execute_trade(
                            iq,
                            pair,
                            signal,
                        )
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
                        f"Error operación: "
                        f"{e}"
                    )

        except KeyboardInterrupt:
            print(
                "\n\nBOT DETENIDO "
                "POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT SNIPER N+1 "
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


# ============================================================
# PUNTO DE ENTRADA
# ============================================================

if __name__ == "__main__":
    main()
