from __future__ import annotations

import os
import time
import traceback
from datetime import datetime

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option

import strategy


# ============================================================
# CONFIGURACION
# ============================================================

PAIR = os.getenv(
    "IQ_PAIR",
    "EURUSD-OTC",
)

AMOUNT = float(
    os.getenv(
        "IQ_AMOUNT",
        "550",
    )
)

EXPIRATION = int(
    os.getenv(
        "IQ_EXPIRATION",
        "1",
    )
)

TIMEFRAME_5S = 5
TIMEFRAME_M1 = 60

CANDLES_PER_M1 = 12

EMAIL = os.getenv(
    "IQ_EMAIL",
)

PASSWORD = os.getenv(
    "IQ_PASSWORD",
)

BALANCE_TYPE = os.getenv(
    "IQ_BALANCE_TYPE",
    "PRACTICE",
)

TELEGRAM_TOKEN = os.getenv(
    "TELEGRAM_TOKEN",
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
)

DATA_RETRY_SECONDS = 1
DATA_RETRY_COUNT = 12

POST_CLOSE_WAIT = 2

RESULT_CHECK_DELAY = 2
RESULT_CHECK_COUNT = 45


# ============================================================
# LOG
# ============================================================

def log(message: str) -> None:
    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        f"{now} | {message}",
        flush=True,
    )


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message: str) -> None:

    if not TELEGRAM_TOKEN:
        return

    if not TELEGRAM_CHAT_ID:
        return

    url = (
        "https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    try:
        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=10,
        )
    except Exception as exc:
        log(
            f"Telegram error: {exc}"
        )


# ============================================================
# CONEXION
# ============================================================

def connect_iq() -> IQ_Option:

    if not EMAIL:
        raise RuntimeError(
            "Falta IQ_EMAIL"
        )

    if not PASSWORD:
        raise RuntimeError(
            "Falta IQ_PASSWORD"
        )

    log(
        "Conectando a IQ Option..."
    )

    iq = IQ_Option(
        EMAIL,
        PASSWORD,
    )

    connected, reason = iq.connect()

    if not connected:
        raise RuntimeError(
            f"No se pudo conectar a IQ Option: "
            f"{reason}"
        )

    try:
        iq.change_balance(
            BALANCE_TYPE
        )
    except Exception as exc:
        log(
            f"No se pudo cambiar balance: {exc}"
        )

    log(
        f"Conectado | BALANCE={BALANCE_TYPE}"
    )

    return iq


# ============================================================
# NORMALIZAR VELA
# ============================================================

def normalize_candle(
    candle,
) -> dict:

    if not isinstance(
        candle,
        dict,
    ):
        return {}

    result = dict(candle)

    if "max" in result and "high" not in result:
        result["high"] = result["max"]

    if "min" in result and "low" not in result:
        result["low"] = result["min"]

    for key in (
        "from",
        "to",
        "open",
        "close",
        "high",
        "low",
        "max",
        "min",
    ):
        if key in result:
            try:
                result[key] = float(
                    result[key]
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

    return result


# ============================================================
# DATAFRAME 5S
# ============================================================

def candles_to_dataframe(
    candles,
) -> pd.DataFrame:

    if candles is None:
        return pd.DataFrame()

    if isinstance(
        candles,
        pd.DataFrame,
    ):
        df = candles.copy()

    else:
        if not isinstance(
            candles,
            (list, tuple),
        ):
            return pd.DataFrame()

        rows = []

        for candle in candles:
            normalized = normalize_candle(
                candle
            )

            if normalized:
                rows.append(
                    normalized
                )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)

    rename = {}

    if "max" in df.columns and "high" not in df.columns:
        rename["max"] = "high"

    if "min" in df.columns and "low" not in df.columns:
        rename["min"] = "low"

    if rename:
        df.rename(
            columns=rename,
            inplace=True,
        )

    required = [
        "from",
        "open",
        "close",
    ]

    if any(
        column not in df.columns
        for column in required
    ):
        return pd.DataFrame()

    for column in (
        "from",
        "to",
        "open",
        "close",
        "high",
        "low",
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
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

    df.drop_duplicates(
        subset=["from"],
        keep="last",
        inplace=True,
    )

    df.reset_index(
        drop=True,
        inplace=True,
    )

    return df


# ============================================================
# OBTENER M1 CERRADA
# ============================================================

def get_closed_m1(
    iq: IQ_Option,
    m1_start: int,
):

    try:
        candles = iq.get_candles(
            PAIR,
            TIMEFRAME_M1,
            3,
            m1_start + 1,
        )
    except Exception as exc:
        log(
            f"Error obteniendo M1: {exc}"
        )
        return None

    if not candles:
        return None

    normalized = [
        normalize_candle(candle)
        for candle in candles
    ]

    normalized = [
        candle
        for candle in normalized
        if candle
    ]

    for candle in normalized:

        try:
            candle_from = int(
                float(candle["from"])
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            continue

        if candle_from == m1_start:
            return candle

    return None


# ============================================================
# OBTENER LAS 12 MICROVELAS
# ============================================================

def get_m1_5s_candles(
    iq: IQ_Option,
    m1_start: int,
) -> pd.DataFrame:

    m1_end = m1_start + TIMEFRAME_M1

    for attempt in range(
        DATA_RETRY_COUNT
    ):

        try:

            candles = iq.get_candles(
                PAIR,
                TIMEFRAME_5S,
                30,
                m1_end + 1,
            )

        except Exception as exc:

            log(
                f"Error 5S intento "
                f"{attempt + 1}: {exc}"
            )

            time.sleep(
                DATA_RETRY_SECONDS
            )

            continue

        df = candles_to_dataframe(
            candles
        )

        if df.empty:

            time.sleep(
                DATA_RETRY_SECONDS
            )

            continue

        df = df[
            (df["from"] >= m1_start)
            & (df["from"] < m1_end)
        ].copy()

        df.sort_values(
            "from",
            inplace=True,
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        df.reset_index(
            drop=True,
            inplace=True,
        )

        if len(df) != CANDLES_PER_M1:

            log(
                f"5S recibidas "
                f"{len(df)}/{CANDLES_PER_M1}"
            )

            time.sleep(
                DATA_RETRY_SECONDS
            )

            continue

        timestamps = (
            df["from"]
            .astype(float)
            .tolist()
        )

        valid_sequence = True

        for index in range(
            1,
            len(timestamps),
        ):

            if (
                timestamps[index]
                - timestamps[index - 1]
                != TIMEFRAME_5S
            ):
                valid_sequence = False
                break

        if not valid_sequence:

            log(
                "Secuencia 5S inválida"
            )

            time.sleep(
                DATA_RETRY_SECONDS
            )

            continue

        return df

    return pd.DataFrame()


# ============================================================
# ESPERAR AL CIERRE DE M1
# ============================================================

def wait_for_m1_close() -> int:

    now = int(
        time.time()
    )

    current_start = (
        now // TIMEFRAME_M1
    ) * TIMEFRAME_M1

    current_end = (
        current_start
        + TIMEFRAME_M1
    )

    wait_seconds = (
        current_end
        - now
        + POST_CLOSE_WAIT
    )

    if wait_seconds > 0:
        time.sleep(
            wait_seconds
        )

    return current_start


# ============================================================
# VERIFICAR STRATEGY
# ============================================================

def verify_strategy() -> None:

    log(
        "========================================"
    )

    log(
        "VERIFICANDO STRATEGY.PY"
    )

    required = (
        "check_pattern",
        "get_m1_direction",
        "get_strategy_analysis",
    )

    for function_name in required:

        function = getattr(
            strategy,
            function_name,
            None,
        )

        if not callable(function):

            raise RuntimeError(
                "strategy.py no contiene "
                f"la función '{function_name}'."
            )

        log(
            f"OK {function_name}() encontrada"
        )

    log(
        "strategy.py compatible"
    )

    log(
        "========================================"
    )


# ============================================================
# IMPRIMIR 5S
# ============================================================

def print_micro_candles(
    df: pd.DataFrame,
) -> None:

    log(
        f"12 VELAS DE 5S"
    )

    for index, row in df.iterrows():

        opening = float(
            row["open"]
        )

        closing = float(
            row["close"]
        )

        if closing > opening:
            color = "VERDE"
        elif closing < opening:
            color = "ROJA"
        else:
            color = "DOJI"

        timestamp = int(
            float(row["from"])
        )

        clock = datetime.fromtimestamp(
            timestamp
        ).strftime(
            "%H:%M:%S"
        )

        log(
            f"{index + 1:02d} | "
            f"{clock} | "
            f"{color} | "
            f"O={opening:.6f} | "
            f"C={closing:.6f}"
        )


# ============================================================
# ANALISIS
# ============================================================

def analyze(
    candle_1m: dict,
    candles_5s: pd.DataFrame,
):

    candle_series = pd.Series(
        candle_1m
    )

    result = strategy.get_strategy_analysis(
        candle_1m=candle_series,
        candles_5s=candles_5s,
        previous_m1=None,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise RuntimeError(
            "get_strategy_analysis() "
            "debe devolver un dict."
        )

    return result


# ============================================================
# EJECUTAR OPERACION
# ============================================================

def execute_trade(
    iq: IQ_Option,
    signal: str,
):

    direction = str(
        signal
    ).strip().lower()

    if direction not in (
        "call",
        "put",
    ):
        log(
            f"Señal inválida: {signal}"
        )
        return None

    log(
        f"OPERACIÓN: {direction.upper()}"
    )

    try:

        success, order_id = iq.buy(
            AMOUNT,
            PAIR,
            direction,
            EXPIRATION,
        )

    except Exception as exc:

        log(
            f"Error ejecutando operación: {exc}"
        )

        return None

    if not success:

        log(
            "IQ Option rechazó la operación"
        )

        return None

    log(
        f"OPERACIÓN ABIERTA | ID={order_id}"
    )

    send_telegram(
        f"EURUSD-OTC\n"
        f"SEÑAL: {direction.upper()}\n"
        f"MONTO: {AMOUNT}\n"
        f"EXPIRACIÓN: {EXPIRATION}M"
    )

    return order_id


# ============================================================
# RESULTADO
# ============================================================

def get_trade_result(
    iq: IQ_Option,
    order_id,
):

    if order_id is None:
        return None

    time.sleep(
        RESULT_CHECK_DELAY
    )

    for _ in range(
        RESULT_CHECK_COUNT
    ):

        try:

            result = iq.check_win_v4(
                order_id
            )

            if result is not None:

                try:
                    return float(
                        result
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    return result

        except Exception:
            pass

        time.sleep(1)

    return None


# ============================================================
# PROCESAR UNA M1
# ============================================================

def process_minute(
    iq: IQ_Option,
    m1_start: int,
) -> None:

    log(
        "========================================"
    )

    log(
        f"M1 CERRADA: "
        f"{datetime.fromtimestamp(m1_start).strftime('%Y-%m-%d %H:%M:%S')}"
    )

    candle_1m = get_closed_m1(
        iq,
        m1_start,
    )

    if candle_1m is None:

        log(
            "No se pudo obtener la M1 cerrada"
        )

        return

    opening = float(
        candle_1m["open"]
    )

    closing = float(
        candle_1m["close"]
    )

    if closing > opening:
        m1_color = "VERDE"

    elif closing < opening:
        m1_color = "ROJA"

    else:
        m1_color = "DOJI"

    log(
        f"M1 | {m1_color} | "
        f"O={opening:.6f} | "
        f"C={closing:.6f}"
    )

    candles_5s = get_m1_5s_candles(
        iq,
        m1_start,
    )

    if candles_5s.empty:

        log(
            "ERROR: no se obtuvieron "
            "exactamente 12 velas 5S"
        )

        return

    print_micro_candles(
        candles_5s
    )

    log(
        "Analizando las 12 velas..."
    )

    try:

        result = analyze(
            candle_1m,
            candles_5s,
        )

    except Exception as exc:

        log(
            "ERROR GENERAL EN STRATEGY"
        )

        log(
            str(exc)
        )

        traceback.print_exc()

        return

    log(
        "========================================"
    )

    log(
        "ANALISIS MATEMATICO"
    )

    log(
        "========================================"
    )

    log(
        f"Dominante: "
        f"{result.get('dominant')}"
    )

    log(
        f"BUY SCORE: "
        f"{result.get('buy_score')}"
    )

    log(
        f"SELL SCORE: "
        f"{result.get('sell_score')}"
    )

    log(
        f"Dominancia: "
        f"{result.get('dominance_ratio'):.2%}"
    )

    log(
        f"Eficiencia: "
        f"{result.get('efficiency'):.2%}"
    )

    log(
        f"Control final: "
        f"{result.get('final_control')}"
    )

    log(
        f"Posición cierre: "
        f"{result.get('close_position')}"
    )

    log(
        f"Razón: "
        f"{result.get('reason')}"
    )

    signal = result.get(
        "signal"
    )

    if signal not in (
        "call",
        "put",
    ):

        log(
            "SIN OPERACIÓN"
        )

        return

    log(
        f"SEÑAL CONFIRMADA: "
        f"{signal.upper()}"
    )

    order_id = execute_trade(
        iq,
        signal,
    )

    if order_id is None:
        return

    trade_result = get_trade_result(
        iq,
        order_id,
    )

    if trade_result is None:

        log(
            "Resultado no disponible"
        )

        return

    if trade_result > 0:

        log(
            f"RESULTADO: WIN | "
            f"+{trade_result}"
        )

        send_telegram(
            f"EURUSD-OTC\n"
            f"RESULTADO: WIN\n"
            f"+{trade_result}"
        )

    elif trade_result < 0:

        log(
            f"RESULTADO: LOSS | "
            f"{trade_result}"
        )

        send_telegram(
            f"EURUSD-OTC\n"
            f"RESULTADO: LOSS\n"
            f"{trade_result}"
        )

    else:

        log(
            "RESULTADO: EMPATE"
        )

        send_telegram(
            "EURUSD-OTC\n"
            "RESULTADO: EMPATE"
        )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    log(
        "========================================"
    )

    log(
        "BOT IQ OPTION"
    )

    log(
        "M1 + 12 VELAS DE 5S"
    )

    log(
        "========================================"
    )

    log(
        f"ACTIVO      : {PAIR}"
    )

    log(
        f"MONTO       : {AMOUNT}"
    )

    log(
        f"EXPIRACIÓN  : {EXPIRATION}M"
    )

    log(
        f"MICROVELAS  : {CANDLES_PER_M1}"
    )

    log(
        "ESTRATEGIA  : strategy.py"
    )

    log(
        "========================================"
    )

    verify_strategy()

    iq = connect_iq()

    last_processed_m1 = None

    while True:

        try:

            now = int(
                time.time()
            )

            current_m1_start = (
                now // TIMEFRAME_M1
            ) * TIMEFRAME_M1

            current_m1_end = (
                current_m1_start
                + TIMEFRAME_M1
            )

            sleep_seconds = (
                current_m1_end
                - now
                + POST_CLOSE_WAIT
            )

            if sleep_seconds > 0:

                time.sleep(
                    sleep_seconds
                )

            m1_to_process = (
                current_m1_start
            )

            if last_processed_m1 == m1_to_process:
                time.sleep(1)
                continue

            process_minute(
                iq,
                m1_to_process,
            )

            last_processed_m1 = (
                m1_to_process
            )

        except KeyboardInterrupt:

            log(
                "BOT DETENIDO"
            )

            break

        except Exception as exc:

            log(
                "ERROR GENERAL"
            )

            log(
                str(exc)
            )

            traceback.print_exc()

            time.sleep(5)

            try:

                if not iq.check_connect():

                    log(
                        "Reconectando..."
                    )

                    iq.connect()

            except Exception:
                pass


if __name__ == "__main__":
    main()
