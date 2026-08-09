import pandas as pd


# ============================================================
# 🎯 CONFIGURACIÓN
# ============================================================

MIN_5S_CANDLES = 6


# ============================================================
# 🧹 VALIDAR DATAFRAME
# ============================================================

def valid_dataframe(df):

    if df is None:
        return False

    if not isinstance(df, pd.DataFrame):
        return False

    required = ["open", "close"]

    for column in required:
        if column not in df.columns:
            return False

    return True


# ============================================================
# 🕯️ COLOR DE VELA
# ============================================================

def candle_color(candle):

    open_price = float(candle["open"])
    close_price = float(candle["close"])

    if close_price > open_price:
        return "green"

    if close_price < open_price:
        return "red"

    return "neutral"


# ============================================================
# 🔍 OBTENER LAS 6 VELAS DE 5 SEGUNDOS
# ============================================================

def get_first_30_seconds(df_5s):

    if not valid_dataframe(df_5s):
        return None

    if len(df_5s) < MIN_5S_CANDLES:
        return None

    # Últimas 6 velas de 5 segundos.
    candles = df_5s.iloc[-6:].copy()

    return candles


# ============================================================
# 🟢 PATRÓN CALL
#
# ROJO → VERDE → VERDE → VERDE → VERDE → ROJO
# ============================================================

def is_call_pattern(df_5s):

    candles = get_first_30_seconds(df_5s)

    if candles is None:
        return False

    pattern = [
        candle_color(candles.iloc[0]),
        candle_color(candles.iloc[1]),
        candle_color(candles.iloc[2]),
        candle_color(candles.iloc[3]),
        candle_color(candles.iloc[4]),
        candle_color(candles.iloc[5]),
    ]

    expected = [
        "red",
        "green",
        "green",
        "green",
        "green",
        "red",
    ]

    return pattern == expected


# ============================================================
# 🔴 PATRÓN PUT
#
# VERDE → ROJO → ROJO → ROJO → ROJO → VERDE
# ============================================================

def is_put_pattern(df_5s):

    candles = get_first_30_seconds(df_5s)

    if candles is None:
        return False

    pattern = [
        candle_color(candles.iloc[0]),
        candle_color(candles.iloc[1]),
        candle_color(candles.iloc[2]),
        candle_color(candles.iloc[3]),
        candle_color(candles.iloc[4]),
        candle_color(candles.iloc[5]),
    ]

    expected = [
        "green",
        "red",
        "red",
        "red",
        "red",
        "green",
    ]

    return pattern == expected


# ============================================================
# 🚨 DETECTAR PATRÓN EXACTO
#
# SE EJECUTA AL SEGUNDO 30
# ============================================================

def detect_5s_pattern(df_5s):

    if not valid_dataframe(df_5s):
        return None

    # CALL
    if is_call_pattern(df_5s):

        print(
            "🟢 PATRÓN CALL DETECTADO:"
            " RED → GREEN → GREEN → GREEN → GREEN → RED"
        )

        return "call"

    # PUT
    if is_put_pattern(df_5s):

        print(
            "🔴 PATRÓN PUT DETECTADO:"
            " GREEN → RED → RED → RED → RED → GREEN"
        )

        return "put"

    # Cualquier otra combinación = NO SEÑAL
    print("⛔ Sin patrón exacto")

    return None


# ============================================================
# 📊 VALIDACIÓN DE LA VELA M1 CERRADA
# ============================================================

def validate_m1(signal, df_m1):

    if signal not in ("call", "put"):
        return False

    if not valid_dataframe(df_m1):
        return False

    # Última vela M1 cerrada
    candle = df_m1.iloc[-1]

    color = candle_color(candle)

    # CALL necesita M1 verde
    if signal == "call":

        if color == "green":

            print(
                "✅ CALL CONFIRMADO:"
                " M1 cerró VERDE"
            )

            return True

        print(
            "❌ CALL CANCELADO:"
            " M1 no cerró verde"
        )

        return False

    # PUT necesita M1 roja
    if signal == "put":

        if color == "red":

            print(
                "✅ PUT CONFIRMADO:"
                " M1 cerró ROJA"
            )

            return True

        print(
            "❌ PUT CANCELADO:"
            " M1 no cerró roja"
        )

        return False

    return False


# ============================================================
# 🎯 VALIDACIÓN FINAL
#
# PATRÓN 5S + CIERRE M1
# ============================================================

def check_pattern(df_5s, df_m1=None):

    # --------------------------------------------------------
    # PASO 1
    # Buscar patrón exacto en 5 segundos
    # --------------------------------------------------------

    signal = detect_5s_pattern(df_5s)

    if signal is None:
        return None

    # --------------------------------------------------------
    # PASO 2
    # Si todavía no tenemos M1 cerrada,
    # existe una señal pendiente.
    # --------------------------------------------------------

    if df_m1 is None:

        print(
            f"🚨 ALERTA {signal.upper()}: "
            "esperando cierre de M1"
        )

        return signal

    # --------------------------------------------------------
    # PASO 3
    # Confirmar color de M1
    # --------------------------------------------------------

    if validate_m1(signal, df_m1):

        print(
            f"🎯 ENTRADA CONFIRMADA: "
            f"{signal.upper()}"
        )

        return signal

    # --------------------------------------------------------
    # PASO 4
    # M1 no confirmó
    # --------------------------------------------------------

    print("⛔ SEÑAL CANCELADA")

    return None


# ============================================================
# 🔔 FUNCIÓN PARA LA ALERTA DEL SEGUNDO 30
# ============================================================

def get_alert(df_5s):

    signal = detect_5s_pattern(df_5s)

    if signal == "call":

        return {
            "signal": "call",
            "message": (
                "🚨 ALERTA CALL\n"
                "Patrón 5S exacto detectado.\n"
                "Esperando cierre de M1."
            )
        }

    if signal == "put":

        return {
            "signal": "put",
            "message": (
                "🚨 ALERTA PUT\n"
                "Patrón 5S exacto detectado.\n"
                "Esperando cierre de M1."
            )
        }

    return None


# ============================================================
# 🎯 DECISIÓN FINAL
# ============================================================

def final_decision(signal, df_m1):

    if signal is None:
        return None

    if validate_m1(signal, df_m1):

        return signal

    return None
