import pandas as pd


# ==============================
# OBTENER COLOR DE VELA
# ==============================
def candle_color(candle):
    if candle["close"] > candle["open"]:
        return "green"
    elif candle["close"] < candle["open"]:
        return "red"
    else:
        return "doji"


# ==============================
# PATRÓN 5s (primeros 30 segundos)
# ==============================
def pattern_5s(df_5s):
    """
    Toma las primeras 6 velas de 5 segundos del minuto actual
    """

    if df_5s is None or len(df_5s) < 6:
        return None

    # Tomar últimas 6 velas (representan los primeros 30s en tiempo real)
    candles = df_5s.iloc[-6:]

    colors = [candle_color(c) for _, c in candles.iterrows()]

    # Patrón CALL
    # rojo → verde → verde → verde → verde → rojo
    if colors == ["red", "green", "green", "green", "green", "red"]:
        return "call"

    # Patrón PUT
    # verde → rojo → rojo → rojo → rojo → verde
    if colors == ["green", "red", "red", "red", "red", "green"]:
        return "put"

    return None


# ==============================
# DIRECCIÓN VELA M1
# ==============================
def direction_m1(df_m1):
    """
    Usa la vela cerrada anterior (NO la actual en formación)
    """

    if df_m1 is None or len(df_m1) < 2:
        return None

    last_closed = df_m1.iloc[-2]

    return candle_color(last_closed)


# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_5s, df_m1):
    """
    Lógica EXACTA pedida:

    1. Detecta patrón en 5s
    2. Confirma con dirección de vela M1
    """

    if df_5s is None or df_m1 is None:
        return None

    if len(df_5s) < 6 or len(df_m1) < 2:
        return None

    pattern = pattern_5s(df_5s)
    m1_dir = direction_m1(df_m1)

    if pattern is None or m1_dir is None:
        return None

    # ==============================
    # SINERGIA FINAL
    # ==============================

    # CALL
    if pattern == "call" and m1_dir == "green":
        return "call"

    # PUT
    if pattern == "put" and m1_dir == "red":
        return "put"

    return None
