import pandas as pd

# ============================================================
# CONFIG
# ============================================================

MIN_CANDLES = 30


# ============================================================
# TENDENCIA EN VIVO (M1)
# ============================================================

def live_trend(df):

    highs = df["max"].iloc[-10:]
    lows = df["min"].iloc[-10:]

    up = all(x < y for x, y in zip(highs, highs[1:])) and \
         all(x < y for x, y in zip(lows, lows[1:]))

    down = all(x > y for x, y in zip(highs, highs[1:])) and \
           all(x > y for x, y in zip(lows, lows[1:]))

    if up:
        return "up"

    if down:
        return "down"

    return None


# ============================================================
# IMPULSO
# ============================================================

def detect_impulse(df, trend):

    candles = df.iloc[-6:-2]

    if trend == "up":
        bullish = sum(c["close"] > c["open"] for _, c in candles.iterrows())
        return bullish >= 3

    if trend == "down":
        bearish = sum(c["close"] < c["open"] for _, c in candles.iterrows())
        return bearish >= 3

    return False


# ============================================================
# PULLBACK (MITAD DE TENDENCIA)
# ============================================================

def detect_pullback(df, trend):

    candles = df.iloc[-4:-1]

    if trend == "up":
        return all(c["close"] < c["open"] for _, c in candles.iterrows())

    if trend == "down":
        return all(c["close"] > c["open"] for _, c in candles.iterrows())

    return False


# ============================================================
# ZONA MEDIA (CLAVE)
# ============================================================

def mid_trend_zone(df):

    recent = df.iloc[-20:]

    high = recent["max"].max()
    low = recent["min"].min()

    price = df.iloc[-2]["close"]

    zone_low = low + (high - low) * 0.45
    zone_high = low + (high - low) * 0.70

    return zone_low <= price <= zone_high


# ============================================================
# EVITAR RESISTENCIA
# ============================================================

def near_resistance(df):

    recent = df.iloc[-15:]

    resistance = recent["max"].max()
    price = df.iloc[-2]["close"]

    return abs(resistance - price) < (resistance * 0.0015)


# ============================================================
# EVITAR SOPORTE
# ============================================================

def near_support(df):

    recent = df.iloc[-15:]

    support = recent["min"].min()
    price = df.iloc[-2]["close"]

    return abs(price - support) < (support * 0.0015)


# ============================================================
# VELA DE FUERZA
# ============================================================

def strong_candle(df, trend):

    last = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    range_candle = last["max"] - last["min"]

    if range_candle == 0:
        return False

    body_ratio = body / range_candle

    if trend == "up":
        return last["close"] > last["open"] and body_ratio > 0.6

    if trend == "down":
        return last["close"] < last["open"] and body_ratio > 0.6

    return False


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def analyze_candle(df_m1, df_m5=None):

    if df_m1 is None or len(df_m1) < MIN_CANDLES:
        return None, None

    # ========================================================
    # 1. TENDENCIA
    # ========================================================

    trend = live_trend(df_m1)

    if trend is None:
        print("⛔ Sin tendencia clara")
        return None, None

    print(f"📈 Tendencia: {trend}")

    # ========================================================
    # 2. IMPULSO
    # ========================================================

    if not detect_impulse(df_m1, trend):
        print("⛔ Sin impulso")
        return None, trend

    # ========================================================
    # 3. PULLBACK
    # ========================================================

    if not detect_pullback(df_m1, trend):
        print("⛔ Sin pullback")
        return None, trend

    print("🔄 Pullback válido")

    # ========================================================
    # 4. ZONA MEDIA (IMPORTANTE)
    # ========================================================

    if not mid_trend_zone(df_m1):
        print("⛔ No está en zona media")
        return None, trend

    # ========================================================
    # 5. FILTRO ANTI ZONAS
    # ========================================================

    if trend == "up" and near_resistance(df_m1):
        print("⛔ Cerca de resistencia")
        return None, trend

    if trend == "down" and near_support(df_m1):
        print("⛔ Cerca de soporte")
        return None, trend

    # ========================================================
    # 6. VELA DE FUERZA
    # ========================================================

    if not strong_candle(df_m1, trend):
        print("⛔ Sin vela de fuerza")
        return None, trend

    print("🔥 Continuidad confirmada")

    # ========================================================
    # 7. ENTRADA FINAL
    # ========================================================

    if trend == "up":
        print("🎯 CALL")
        return "call", trend

    if trend == "down":
        print("🎯 PUT")
        return "put", trend

    return None, trend
