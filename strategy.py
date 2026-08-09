import pandas as pd

MIN_CANDLES = 30


# ============================================================
# 🔥 TENDENCIA CLARA EN M1 (VERSIÓN PRO)
# ============================================================

def live_trend(df):

    recent = df.iloc[-15:]

    highs = recent["max"].values
    lows = recent["min"].values
    closes = recent["close"].values
    opens = recent["open"].values

    # Estructura
    higher_highs = sum(highs[i] > highs[i-1] for i in range(1, len(highs)))
    higher_lows = sum(lows[i] > lows[i-1] for i in range(1, len(lows)))

    lower_highs = sum(highs[i] < highs[i-1] for i in range(1, len(highs)))
    lower_lows = sum(lows[i] < lows[i-1] for i in range(1, len(lows)))

    # Dominancia de velas
    bullish = sum(closes > opens)
    bearish = sum(closes < opens)

    avg_price = closes.mean()
    last_price = closes[-1]

    # Tendencia alcista REAL
    if (
        higher_highs >= 8 and
        higher_lows >= 8 and
        bullish >= 9 and
        last_price > avg_price
    ):
        return "up"

    # Tendencia bajista REAL
    if (
        lower_highs >= 8 and
        lower_lows >= 8 and
        bearish >= 9 and
        last_price < avg_price
    ):
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
# PULLBACK (RETROCESO)
# ============================================================

def detect_pullback(df, trend):

    candles = df.iloc[-4:-1]

    if trend == "up":
        return all(c["close"] < c["open"] for _, c in candles.iterrows())

    if trend == "down":
        return all(c["close"] > c["open"] for _, c in candles.iterrows())

    return False


# ============================================================
# 🎯 ZONA MEDIA (CLAVE REAL)
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
# 🚫 FILTROS DE ZONAS
# ============================================================

def near_resistance(df):

    recent = df.iloc[-15:]
    resistance = recent["max"].max()
    price = df.iloc[-2]["close"]

    return abs(resistance - price) < (resistance * 0.0015)


def near_support(df):

    recent = df.iloc[-15:]
    support = recent["min"].min()
    price = df.iloc[-2]["close"]

    return abs(price - support) < (support * 0.0015)


# ============================================================
# 🔥 VELA DE FUERZA (CONTINUIDAD)
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
# 🧠 FUNCIÓN PRINCIPAL
# ============================================================

def analyze_candle(df_m1, df_m5=None):

    if df_m1 is None or len(df_m1) < MIN_CANDLES:
        return None, None

    # 1. Tendencia
    trend = live_trend(df_m1)

    if trend is None:
        print("⛔ Sin tendencia clara M1")
        return None, None

    print(f"📈 Tendencia M1: {trend}")

    # 2. Impulso
    if not detect_impulse(df_m1, trend):
        print("⛔ Sin impulso")
        return None, trend

    # 3. Pullback
    if not detect_pullback(df_m1, trend):
        print("⛔ Sin pullback")
        return None, trend

    print("🔄 Pullback detectado")

    # 4. Zona media (CRÍTICO)
    if not mid_trend_zone(df_m1):
        print("⛔ Fuera de zona media")
        return None, trend

    # 5. Filtro zonas peligrosas
    if trend == "up" and near_resistance(df_m1):
        print("⛔ Cerca de resistencia")
        return None, trend

    if trend == "down" and near_support(df_m1):
        print("⛔ Cerca de soporte")
        return None, trend

    # 6. Confirmación de fuerza
    if not strong_candle(df_m1, trend):
        print("⛔ Sin vela de fuerza")
        return None, trend

    print("🔥 Continuidad confirmada")

    # 7. Entrada
    if trend == "up":
        print("🎯 CALL")
        return "call", trend

    if trend == "down":
        print("🎯 PUT")
        return "put", trend

    return None, trend
