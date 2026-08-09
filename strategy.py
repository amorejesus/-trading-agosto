import time

# ==============================
# OBTENER PRIMERAS 6 VELAS (0–30s)
# ==============================
def get_first_6_candles(df_5s):
    now = int(time.time())

    # inicio del minuto actual
    current_minute = now - (now % 60)

    # filtrar solo velas del minuto actual
    candles = df_5s[df_5s["from"] >= current_minute]

    # ordenar por tiempo
    candles = candles.sort_values("from")

    # tomar SOLO las primeras 6 velas (0–30s)
    return candles.head(6)


# ==============================
# DETECTAR COLOR VELA
# ==============================
def get_color(candle):
    if candle["close"] > candle["open"]:
        return "g"
    else:
        return "r"


# ==============================
# DETECTAR PATRÓN
# ==============================
def detect_pattern(df_5s):
    candles = get_first_6_candles(df_5s)

    if len(candles) < 6:
        return None

    colors = [get_color(c) for _, c in candles.iterrows()]

    # patrón 1
    pattern_1 = ["r", "g", "g", "g", "g", "r"]

    # patrón 2
    pattern_2 = ["g", "r", "r", "r", "r", "g"]

    if colors == pattern_1 or colors == pattern_2:
        return True

    return False


# ==============================
# DIRECCIÓN M1
# ==============================
def get_m1_direction(df_m1):
    last = df_m1.iloc[-2]  # vela cerrada

    if last["close"] > last["open"]:
        return "call"
    else:
        return "put"


# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_5s, df_m1):
    if df_5s is None or df_m1 is None:
        return None, None

    if len(df_5s) < 10 or len(df_m1) < 5:
        return None, None

    # 🔥 validar patrón
    valid_pattern = detect_pattern(df_5s)

    if not valid_pattern:
        return None, None

    # 🔥 dirección SOLO M1
    direction = get_m1_direction(df_m1)

    return direction, time.time()
