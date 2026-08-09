import pandas as pd

# ==============================
# 🔍 PATRONES PERMITIDOS (5s)
# ==============================

# ROJO → VERDE → VERDE → VERDE → VERDE → ROJO
PATTERN_1 = ["red", "green", "green", "green", "green", "red"]

# VERDE → ROJO → ROJO → ROJO → ROJO → VERDE
PATTERN_2 = ["green", "red", "red", "red", "red", "green"]


# ==============================
# 🎯 COLOR DE VELA
# ==============================
def candle_color(c):
    if c["close"] > c["open"]:
        return "green"
    else:
        return "red"


# ==============================
# 🧠 DETECTAR PATRÓN EN 5s
# ==============================
def detect_pattern(df_5s):
    if df_5s is None or len(df_5s) < 6:
        return False

    first_6 = df_5s.iloc[:6]  # 🔥 SOLO primeras 6 velas del minuto

    colors = [candle_color(c) for _, c in first_6.iterrows()]

    if colors == PATTERN_1 or colors == PATTERN_2:
        return True

    return False


# ==============================
# 📊 DIRECCIÓN VELA M1
# ==============================
def m1_direction(df_m1):
    if df_m1 is None or len(df_m1) < 2:
        return None

    last = df_m1.iloc[-2]  # vela cerrada

    if last["close"] > last["open"]:
        return "green"
    else:
        return "red"


# ==============================
# 🚀 FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_5s):
    """
    Lógica EXACTA:
    1. Detecta patrón en primeras 6 velas de 5s
    2. Mira dirección de vela M1
    3. Ejecuta en la MISMA dirección
    """

    if df_m1 is None or df_5s is None:
        return None

    # 🔍 patrón 5s
    pattern_ok = detect_pattern(df_5s)

    if not pattern_ok:
        return None

    # 📊 dirección M1
    direction_m1 = m1_direction(df_m1)

    if direction_m1 is None:
        return None

    # ==============================
    # 🎯 ENTRADA FINAL
    # ==============================
    if direction_m1 == "green":
        return "call"

    elif direction_m1 == "red":
        return "put"

    return None
