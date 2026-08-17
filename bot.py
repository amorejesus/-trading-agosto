import os
import time
import requests
import inspect
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

TIMEFRAME_M1 = 60
TIMEFRAME_M5 = 300

# M1:
# vela de toque = N-6
# N-5
# N-4
# N-3
# N-2
# N-1
# entrada = N+1
M1_CANDLES_REQUIRED = 7

# Velas M5 para que strategy.py pueda determinar
# estructura, soporte y resistencia.
M5_CANDLES_REQUIRED = 12

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
                "desconocido"
            )
        )
    )

    required_any = (
        "get_strategy_analysis",
        "check_pattern",
    )

    found = False

    for name in required_any:
        function = getattr(
            strategy,
            name,
            None
        )

        if callable(function):
            print(
                f"✓ {name}() encontrada"
            )
            found = True

    if not found:
        raise RuntimeError(
            "strategy.py no contiene "
            "get_strategy_analysis() ni "
            "check_pattern()."
        )

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
                PASSWORD
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
                    "Modo: SNIPER M5/M1 N+1\n"
                    "Estructura: M5\n"
                    "Confirmación: M1\n"
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

def get_current_m1():
    now = int(time.time())

    return now - (
        now % TIMEFRAME_M1
    )


def wait_for_new_m1(last_timestamp):
    while True:
        current = get_current_m1()

        if current > last_timestamp:
            return current

        time.sleep(0.02)


def wait_until_timestamp(timestamp):
    while True:
        remaining = timestamp - time.time()

        if remaining <= 0:
            return

        time.sleep(
            min(
                0.01,
                remaining
            )
        )


# ============================================================
# OBTENER VELAS
# ============================================================

def get_candles(
    iq,
    pair,
    timeframe,
    amount,
    end_timestamp,
):
    try:
        candles = iq.get_candles(
            pair,
            timeframe,
            amount,
            end_timestamp,
        )

    except Exception as e:
        print(
            f"[{pair}] Error obteniendo "
            f"velas {timeframe}s: {e}"
        )

        return None

    if not candles:
        print(
            f"[{pair}] API no devolvió "
            f"velas {timeframe}s."
        )

        return None

    valid = []

    for candle in candles:
        try:
            int(candle["from"])
            float(candle["open"])
            float(candle["close"])
            float(candle["high"])
            float(candle["low"])
        except Exception:
            continue

        valid.append(candle)

    if len(valid) < amount:
        return None

    valid.sort(
        key=lambda x: int(x["from"])
    )

    return valid[-amount:]


# ============================================================
# OBTENER M1
# ============================================================

def get_m1_candles(
    iq,
    pair,
    timestamp,
):
    return get_candles(
        iq,
        pair,
        TIMEFRAME_M1,
        M1_CANDLES_REQUIRED,
        timestamp,
    )


# ============================================================
# OBTENER M5
# ============================================================

def get_m5_candles(
    iq,
    pair,
    timestamp,
):
    return get_candles(
        iq,
        pair,
        TIMEFRAME_M5,
        M5_CANDLES_REQUIRED,
        timestamp,
    )


# ============================================================
# VALIDAR SECUENCIA M1
# ============================================================

def validate_m1_sequence(candles):
    if not candles:
        return False

    if len(candles) < M1_CANDLES_REQUIRED:
        return False

    timestamps = []

    for candle in candles:
        try:
            timestamps.append(
                int(candle["from"])
            )
        except Exception:
            return False

    timestamps.sort()

    for i in range(1, len(timestamps)):
        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != TIMEFRAME_M1:
            return False

    return True


# ============================================================
# COLOR DE VELA
# ============================================================

def candle_direction(candle):
    try:
        opening = float(
            candle["open"]
        )

        closing = float(
            candle["close"]
        )

    except Exception:
        return "doji"

    if closing > opening:
        return "verde"

    if closing < opening:
        return "roja"

    return "doji"


# ============================================================
# IMPRIMIR VELA
# ============================================================

def print_candle(
    pair,
    candle,
    label,
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

        closing = float(
            candle["close"]
        )

        high = float(
            candle["high"]
        )

        low = float(
            candle["low"]
        )

    except Exception:
        return

    direction = candle_direction(
        candle
    )

    if direction == "verde":
        symbol = "🟢"
    elif direction == "roja":
        symbol = "🔴"
    else:
        symbol = "⚪"

    print(
        f"[{pair}] {label} "
        f"{dt.strftime('%H:%M:%S')} | "
        f"{symbol} {direction.upper()} | "
        f"O={opening} "
        f"H={high} "
        f"L={low} "
        f"C={closing}"
    )


# ============================================================
# IMPRIMIR ESTRUCTURA M1
# ============================================================

def print_m1_structure(
    pair,
    candles,
):
    if not candles:
        return

    print("\n--------------------------------------")
    print(
        f"SECUENCIA M1 {pair}"
    )
    print("--------------------------------------")

    labels = [
        "N-6",
        "N-5",
        "N-4",
        "N-3",
        "N-2",
        "N-1",
        "N",
    ]

    start = max(
        0,
        len(candles) - len(labels)
    )

    selected = candles[start:]

    for label, candle in zip(
        labels[-len(selected):],
        selected,
    ):
        print_candle(
            pair,
            candle,
            label,
        )

    print("--------------------------------------")


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(signal):
    if not isinstance(
        signal,
        str
    ):
        return None

    signal = (
        signal
        .strip()
        .lower()
    )

    if signal in (
        "call",
        "put",
    ):
        return signal

    return None


# ============================================================
# LLAMAR A STRATEGY.PY
# ============================================================

def call_strategy_function(
    function,
    m5_candles,
    m1_candles,
):
    """
    Permite que strategy.py utilice:
    
    get_strategy_analysis(m5, m1)
    
    o
    
    get_strategy_analysis(m1)
    
    o
    
    get_strategy_analysis(m5)
    
    según la firma existente.
    """

    try:
        signature = inspect.signature(
            function
        )

        parameters = [
            p
            for p in signature.parameters.values()
            if p.kind
            in (
                p.POSITIONAL_ONLY,
                p.POSITIONAL_OR_KEYWORD,
            )
        ]

        required = [
            p
            for p in parameters
            if p.default
            is inspect.Parameter.empty
        ]

        count = len(required)

        if count >= 2:
            return function(
                m5_candles,
                m1_candles,
            )

        if count == 1:
            return function(
                m1_candles
            )

        return function()

    except Exception:
        # Compatibilidad adicional:
        # primero intenta M5 + M1.
        try:
            return function(
                m5_candles,
                m1_candles,
            )

        except TypeError:
            try:
                return function(
                    m1_candles
                )

            except TypeError:
                return function(
                    m5_candles
                )


# ============================================================
# ANALIZAR ESTRATEGIA
# ============================================================

def get_full_analysis(
    m5_candles,
    m1_candles,
):
    function = getattr(
        strategy,
        "get_strategy_analysis",
        None,
    )

    if not callable(function):
        return None

    try:
        return call_strategy_function(
            function,
            m5_candles,
            m1_candles,
        )

    except Exception as e:
        print(
            f"[ANALYSIS] Error: {e}"
        )

        return None


# ============================================================
# OBTENER SEÑAL
# ============================================================

def get_strategy_signal(
    m5_candles,
    m1_candles,
    analysis,
):
    """
    Prioridad:

    1. analysis["signal"]
    2. strategy.check_pattern()
    """

    if isinstance(
        analysis,
        dict,
    ):
        signal = normalize_signal(
            analysis.get(
                "signal"
            )
        )

        if signal:
            return signal

    function = getattr(
        strategy,
        "check_pattern",
        None,
    )

    if not callable(function):
        return None

    try:
        result = call_strategy_function(
            function,
            m5_candles,
            m1_candles,
        )

        return normalize_signal(
            result
        )

    except Exception as e:
        print(
            f"[STRATEGY] Error: {e}"
        )

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

    if not isinstance(
        analysis,
        dict,
    ):
        print(
            f"[{pair}] "
            f"Análisis recibido: "
            f"{analysis}"
        )

        return

    print("\n--------------------------------------")
    print(
        f"ANÁLISIS DE ESTRUCTURA {pair}"
    )
    print("--------------------------------------")

    support = analysis.get(
        "support"
    )

    resistance = analysis.get(
        "resistance"
    )

    touch = analysis.get(
        "touch"
    )

    zone = analysis.get(
        "zone"
    )

    count = analysis.get(
        "count"
    )

    signal = normalize_signal(
        analysis.get(
            "signal"
        )
    )

    reason = analysis.get(
        "reason"
    )

    print(
        f"Soporte M5      : {support}"
    )

    print(
        f"Resistencia M5  : {resistance}"
    )

    print(
        f"Toque/Ruptura   : {touch}"
    )

    print(
        f"Zona            : {zone}"
    )

    print(
        f"Conteo          : {count}"
    )

    print(
        f"Señal           : "
        f"{signal.upper() if signal else 'NINGUNA'}"
    )

    print(
        f"Motivo          : "
        f"{reason if reason else 'N/A'}"
    )

    print("--------------------------------------")


# ============================================================
# PROCESAR PAR
# ============================================================

def process_pair(
    iq,
    pair,
    candle_timestamp,
):
    # --------------------------------------------------------
    # M5 = ESTRUCTURA
    # --------------------------------------------------------

    m5_candles = get_m5_candles(
        iq,
        pair,
        candle_timestamp,
    )

    if not m5_candles:
        print(
            f"[{pair}] "
            "M5 insuficiente."
        )

        return None

    # --------------------------------------------------------
    # M1 = TOQUE + CONTEO
    # --------------------------------------------------------

    m1_candles = get_m1_candles(
        iq,
        pair,
        candle_timestamp,
    )

    if not m1_candles:
        print(
            f"[{pair}] "
            "M1 insuficiente."
        )

        return None

    if not validate_m1_sequence(
        m1_candles
    ):
        print(
            f"[{pair}] "
            "Secuencia M1 inválida."
        )

        return None

    print_m1_structure(
        pair,
        m1_candles,
    )

    # --------------------------------------------------------
    # ANÁLISIS
    # --------------------------------------------------------

    print(
        f"\n[{pair}] "
        "Analizando M5 + M1..."
    )

    analysis = get_full_analysis(
        m5_candles,
        m1_candles,
    )

    print_analysis(
        pair,
        analysis,
    )

    # --------------------------------------------------------
    # SEÑAL
    # --------------------------------------------------------

    signal = get_strategy_signal(
        m5_candles,
        m1_candles,
        analysis,
    )

    if signal is None:
        print(
            f"[{pair}] "
            "⚪ SIN ENTRADA"
        )

        return None

    if signal == "call":
        print(
            f"[{pair}] "
            "🟢 SOPORTE M5 → CALL"
        )

    elif signal == "put":
        print(
            f"[{pair}] "
            "🔴 RESISTENCIA M5 → PUT"
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
        print(
            f"[{pair}] "
            "Señal inválida."
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
            return float(
                result
            )

    except Exception as e:
        print(
            f"[RESULTADO] Error: {e}"
        )

    return None


# ============================================================
# IMPRIMIR RESULTADO
# ============================================================

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
# MAIN
# ============================================================

def main():
    print("\n")
    print("==========================================")
    print("       BOT IQ OPTION SNIPER")
    print("           ESTRUCTURA M5")
    print("        CONFIRMACIÓN M1 N+1")
    print("==========================================")
    print("ESTRUCTURA    : M5")
    print("ANÁLISIS      : M1")
    print("ENTRADA       : N+1")
    print("MODO          : SNIPER")
    print(f"MONTO         : {AMOUNT}")
    print(
        f"EXPIRACIÓN    : {EXPIRATION}M"
    )
    print(
        f"M1 VELAS      : {M1_CANDLES_REQUIRED}"
    )
    print(
        f"M5 VELAS      : {M5_CANDLES_REQUIRED}"
    )
    print(
        f"PARES         : {len(PAIRS)}"
    )
    print("==========================================")

    for pair in PAIRS:
        print(
            f"✓ {pair}"
        )

    print(
        "=========================================="
    )

    verify_strategy()

    iq = connect_iq()

    # Última vela M1 cerrada.
    last_timestamp = (
        get_current_m1()
        - TIMEFRAME_M1
    )

    while True:
        try:
            # ------------------------------------------------
            # CONEXIÓN
            # ------------------------------------------------

            if not ensure_connection(
                iq
            ):
                time.sleep(5)

                iq = connect_iq()

                continue

            # ------------------------------------------------
            # ESPERAR NUEVA VELA M1
            # ------------------------------------------------

            current_timestamp = (
                wait_for_new_m1(
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
                "🔔 NUEVA VELA M1"
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

            # ------------------------------------------------
            # ANALIZAR TODOS LOS PARES
            # ------------------------------------------------

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
                        f"Error procesando: {e}"
                    )

            # ------------------------------------------------
            # SIN SEÑALES
            # ------------------------------------------------

            if not signals:
                print(
                    "\n⚪ Ningún par cumplió "
                    "las condiciones."
                )

                continue

            # ------------------------------------------------
            # MOSTRAR SEÑALES
            # ------------------------------------------------

            print(
                "\n=========================================="
            )

            print(
                "🎯 ENTRADAS PREPARADAS PARA N+1"
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
            # APERTURA N+1
            # ------------------------------------------------

            next_candle = (
                current_timestamp
                + TIMEFRAME_M1
            )

            wait_until_timestamp(
                next_candle
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
                    "%Y-%m-%d %H:%M:%S"
                )
            )

            print(
                "=========================================="
            )

            # ------------------------------------------------
            # EJECUCIÓN
            # ------------------------------------------------

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
                        f"Error operación: {e}"
                    )

        # ----------------------------------------------------
        # DETENER
        # ----------------------------------------------------

        except KeyboardInterrupt:
            print(
                "\n\nBOT DETENIDO "
                "POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT SNIPER M5/M1 "
                "DETENIDO"
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

            time.sleep(3)


# ============================================================
# INICIO
# ============================================================

if __name__ == "__main__":
    main()
