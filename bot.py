from __future__ import annotations

import os
import time
import requests
from datetime import datetime
from typing import Any, Optional

import pandas as pd
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

# La estrategia actual trabaja con velas M1.
TIMEFRAME_M1 = 60

# Cantidad de velas M1 entregadas a strategy.py.
# Se usan para detectar:
#
# N-1 = toque/ruptura de soporte o resistencia M5
# N-2
# N-3
# N-4
# N-5
# N-6 = sexta vela posterior
#
# La entrada se realiza en N+1.
CANDLES_REQUIRED = 7

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> None:
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

def verify_strategy() -> None:
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
        function = getattr(
            strategy,
            name,
            None,
        )

        if not callable(function):
            raise RuntimeError(
                "strategy.py no contiene "
                f"la función '{name}'."
            )

        print(
            f"✓ {name}() encontrada"
        )

    print("✓ STRATEGY.PY COMPATIBLE")
    print("======================================\n")


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq() -> IQ_Option:
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
                    "Modo: SNIPER N+1\n"
                    "Estructura: M5\n"
                    "Análisis: M1\n"
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

def ensure_connection(iq: IQ_Option) -> bool:
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

def get_current_m1() -> int:
    now = int(time.time())

    return now - (
        now % TIMEFRAME_M1
    )


def wait_for_new_m1(
    last_timestamp: int,
) -> int:

    while True:
        current = get_current_m1()

        if current > last_timestamp:
            return current

        time.sleep(0.05)


def wait_until_open(
    timestamp: int,
) -> None:

    while True:
        remaining = (
            timestamp
            - time.time()
        )

        if remaining <= 0:
            return

        time.sleep(
            min(
                0.01,
                remaining,
            )
        )


# ============================================================
# OBTENER VELAS M1
# ============================================================

def get_m1_candles(
    iq: IQ_Option,
    pair: str,
    end_timestamp: int,
    amount: int = CANDLES_REQUIRED,
) -> Optional[list]:

    try:
        candles = iq.get_candles(
            pair,
            TIMEFRAME_M1,
            amount,
            end_timestamp,
        )

    except Exception as e:
        print(
            f"[{pair}] Error obteniendo "
            f"velas M1: {e}"
        )

        return None

    if not candles:
        print(
            f"[{pair}] API no devolvió "
            "velas M1."
        )

        return None

    valid = []

    for candle in candles:

        if not isinstance(
            candle,
            dict,
        ):
            continue

        try:
            timestamp = int(
                candle.get("from")
            )
        except Exception:
            continue

        required_fields = (
            "open",
            "close",
            "max",
            "min",
        )

        valid_candle = True

        for field in required_fields:
            if field not in candle:
                valid_candle = False
                break

            try:
                float(candle[field])
            except Exception:
                valid_candle = False
                break

        if not valid_candle:
            continue

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

    # Eliminar timestamps duplicados.
    unique = {}

    for candle in valid:
        try:
            timestamp = int(
                candle["from"]
            )
        except Exception:
            continue

        unique[timestamp] = candle

    valid = list(
        unique.values()
    )

    valid.sort(
        key=lambda x: int(
            x["from"]
        )
    )

    if len(valid) < amount:
        print(
            f"[{pair}] M1 insuficientes: "
            f"{len(valid)}/{amount}"
        )

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

    # Verificar que las velas sean consecutivas.
    for i in range(
        1,
        len(timestamps),
    ):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != TIMEFRAME_M1:
            print(
                f"[{pair}] SECUENCIA M1 "
                f"INVALIDA: {difference}s"
            )

            return None

    return valid


# ============================================================
# CONVERTIR VELAS A DATAFRAME
# ============================================================

def candles_to_dataframe(
    candles: list,
) -> pd.DataFrame:

    df = pd.DataFrame(candles)

    if df.empty:
        return df

    rename = {}

    if "max" in df.columns:
        rename["max"] = "high"

    if "min" in df.columns:
        rename["min"] = "low"

    if "Open" in df.columns:
        rename["Open"] = "open"

    if "High" in df.columns:
        rename["High"] = "high"

    if "Low" in df.columns:
        rename["Low"] = "low"

    if "Close" in df.columns:
        rename["Close"] = "close"

    if rename:
        df.rename(
            columns=rename,
            inplace=True,
        )

    required = (
        "from",
        "open",
        "close",
    )

    for column in required:
        if column not in df.columns:
            return pd.DataFrame()

    df["from"] = pd.to_numeric(
        df["from"],
        errors="coerce",
    )

    df["open"] = pd.to_numeric(
        df["open"],
        errors="coerce",
    )

    df["close"] = pd.to_numeric(
        df["close"],
        errors="coerce",
    )

    if "high" in df.columns:
        df["high"] = pd.to_numeric(
            df["high"],
            errors="coerce",
        )

    if "low" in df.columns:
        df["low"] = pd.to_numeric(
            df["low"],
            errors="coerce",
        )

    df.dropna(
        subset=[
            "from",
            "open",
            "close",
        ],
        inplace=True,
    )

    df.sort_values(
        "from",
        inplace=True,
    )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# MOSTRAR VELA
# ============================================================

def print_candle(
    pair: str,
    candle: Any,
    label: str = "N",
) -> None:

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
        f"{label} | "
        f"{symbol} {direction} | "
        f"O={opening} | "
        f"C={closing}"
    )


# ============================================================
# ANALIZAR ESTRATEGIA
# ============================================================

def analyze_strategy(
    candles: list,
) -> Optional[str]:

    try:
        return strategy.check_pattern(
            candles
        )

    except Exception as e:
        print(
            f"[STRATEGY] Error: {e}"
        )

        return None


def get_full_analysis(
    candles: list,
) -> Optional[dict]:

    try:
        result = (
            strategy.get_strategy_analysis(
                candles
            )
        )

        if isinstance(
            result,
            dict,
        ):
            return result

    except Exception as e:
        print(
            f"[ANALYSIS] Error: {e}"
        )

    return None


# ============================================================
# NORMALIZAR SEÑAL
# ============================================================

def normalize_signal(
    signal: Any,
) -> Optional[str]:

    if not isinstance(
        signal,
        str,
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
# MOSTRAR ANÁLISIS
# ============================================================

def print_analysis(
    pair: str,
    analysis: Optional[dict],
) -> None:

    if not isinstance(
        analysis,
        dict,
    ):
        return

    print("\n--------------------------------------")
    print(
        f"ANÁLISIS SNIPER {pair}"
    )
    print("--------------------------------------")

    # Mostrar información de soporte/resistencia
    # si strategy.py la proporciona.

    signal = analysis.get(
        "signal"
    )

    if signal is not None:
        print(
            f"Señal          : "
            f"{str(signal).upper()}"
        )

    support = analysis.get(
        "support"
    )

    if support is not None:
        print(
            f"Soporte M5     : "
            f"{support}"
        )

    resistance = analysis.get(
        "resistance"
    )

    if resistance is not None:
        print(
            f"Resistencia M5  : "
            f"{resistance}"
        )

    interaction = analysis.get(
        "interaction"
    )

    if interaction is not None:
        print(
            f"Interacción     : "
            f"{str(interaction).upper()}"
        )

    reference = analysis.get(
        "reference_candle"
    )

    if reference is not None:
        print(
            f"Vela referencia : "
            f"{reference}"
        )

    follow_candles = analysis.get(
        "follow_candles"
    )

    if follow_candles is not None:
        print(
            f"Velas espera    : "
            f"{follow_candles}"
        )

    final_state = analysis.get(
        "final_state"
    )

    if final_state is not None:
        print(
            f"Estado final    : "
            f"{str(final_state).upper()}"
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
# EJECUTAR OPERACIÓN
# ============================================================

def execute_trade(
    iq: IQ_Option,
    pair: str,
    signal: str,
) -> tuple:

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
        f"Activo       : {pair}"
    )
    print(
        f"Dirección    : "
        f"{signal.upper()}"
    )
    print(
        f"Monto        : {AMOUNT}"
    )
    print(
        f"Expiración   : "
        f"{EXPIRATION}M"
    )
    print(
        "Ejecución    : APERTURA N+1"
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
                f"Dirección: "
                f"{signal.upper()}\n"
                f"Monto: {AMOUNT}\n"
                f"Expiración: "
                f"{EXPIRATION}M"
            )

            return True, order_id

        print(
            f"✗ IQ Option rechazó "
            f"la operación en {pair}."
        )

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
    iq: IQ_Option,
    order_id: Any,
) -> Optional[float]:

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
    pair: str,
    result: Optional[float],
) -> None:

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
# PROCESAR UN PAR
# ============================================================

def process_pair(
    iq: IQ_Option,
    pair: str,
    candle_timestamp: int,
) -> Optional[str]:

    candles = get_m1_candles(
        iq,
        pair,
        candle_timestamp,
        CANDLES_REQUIRED,
    )

    if candles is None:
        print(
            f"[{pair}] Datos M1 insuficientes."
        )

        return None

    print(
        f"\n[{pair}] "
        "VELAS M1 RECIBIDAS"
    )

    labels = [
        "N-6",
        "N-5",
        "N-4",
        "N-3",
        "N-2",
        "N-1",
        "N",
    ]

    for index, candle in enumerate(
        candles
    ):
        label = labels[index]

        print_candle(
            pair,
            candle,
            label,
        )

    print(
        f"\n[{pair}] "
        "Analizando estructura M5..."
    )

    print(
        f"[{pair}] "
        "Buscando toque/ruptura "
        "y confirmación de 6 velas..."
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
            "⚪ SIN OPERACIÓN"
        )

        return None

    if signal == "call":

        print(
            f"[{pair}] "
            "🟢 SEÑAL CALL → N+1"
        )

    else:

        print(
            f"[{pair}] "
            "🔴 SEÑAL PUT → N+1"
        )

    return signal


# ============================================================
# MAIN
# ============================================================

def main() -> None:

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
        "ESTRUCTURA   : SOPORTE/RESISTENCIA M5"
    )
    print(
        "ANÁLISIS     : VELAS M1"
    )
    print(
        "CONFIRMACIÓN : 6 VELAS"
    )
    print(
        "ENTRADA      : APERTURA N+1"
    )
    print(
        f"MONTO        : {AMOUNT}"
    )
    print(
        f"EXPIRACIÓN   : {EXPIRATION}M"
    )
    print(
        f"TIMEFRAME    : {TIMEFRAME_M1}s"
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

            # Esperar exactamente al cambio
            # de minuto.
            current_timestamp = (
                wait_for_new_m1(
                    last_timestamp
                )
            )

            last_timestamp = (
                current_timestamp
            )

            print("\n\n")
            print(
                "=========================================="
            )
            print(
                "🔔 NUEVO CICLO M1"
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

            # ------------------------------------------------
            # ANALIZAR TODOS LOS PARES
            # ------------------------------------------------

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

            print("\n")
            print(
                "=========================================="
            )
            print(
                "🎯 SEÑALES CONFIRMADAS"
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

            print(
                "\n⏱ Esperando apertura N+1..."
            )

            wait_until_open(
                next_candle
            )

            print("\n")
            print(
                "=========================================="
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
            # IMPORTANTE:
            #
            # PRIMERO SE EJECUTAN TODAS LAS SEÑALES.
            #
            # NO se espera el resultado de una operación
            # antes de abrir la siguiente.
            # ------------------------------------------------

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

            if not opened_trades:

                print(
                    "\n⚠ No se pudo abrir "
                    "ninguna operación."
                )

                continue

            print("\n")
            print(
                "=========================================="
            )
            print(
                "📊 ESPERANDO RESULTADOS"
            )
            print(
                "=========================================="
            )

            # Esperar una sola vez para no retrasar
            # las entradas.
            wait_seconds = (
                EXPIRATION * 60
                + 5
            )

            print(
                f"Esperando "
                f"{wait_seconds}s..."
            )

            time.sleep(
                wait_seconds
            )

            for pair, order_id in opened_trades:

                try:

                    result = (
                        iq.check_win_v4(
                            order_id
                        )
                    )

                    if result is not None:
                        result = float(
                            result
                        )

                    print_result(
                        pair,
                        result,
                    )

                except Exception as e:

                    print(
                        f"[{pair}] "
                        f"Error consultando "
                        f"resultado: {e}"
                    )

        except KeyboardInterrupt:

            print(
                "\n\n"
                "BOT DETENIDO POR EL USUARIO."
            )

            send_telegram(
                "🛑 BOT SNIPER N+1 DETENIDO"
            )

            break

        except Exception as e:

            print("\n")
            print(
                "======================================"
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
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
