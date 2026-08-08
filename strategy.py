import pandas as pd

# ============================================================
# DETECTAR TENDENCIA EN VIVO (M1)
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
# DETECTAR IMPULSO
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
# DETECTAR PULLBACK (MITAD DE TENDENCIA)
# ============================================================

def detect_pullback(df, trend):

    candles = df.iloc[-4:-1]

    if trend == "up":
        return all(c["close"] < c["open"] for _, c in candles.iterrows())

    if trend == "down":
        return all(c["close"] > c["open"] for _, c in candles.iterrows())

    return False


# ============================================================
# EVITAR ENTRAR EN EXTREMOS
# ============================================================

def not_at_extreme(df, trend):

    recent_high = df["max"].iloc[-10:].max()
    recent_low = df["min"].iloc[-10:].min()

    price = df.iloc[-2]["close"]

    if trend == "up":
        return price < recent_high * 0.999  # no en techo

    if trend == "down":
        return price > recent_low * 1.001  # no en suelo

    return False


# ============================================================
# VELA DE CONTINUIDAD (FUERZA)
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

    if df_m1 is None or len(df_m1) < 30:
        return None, None

    # 1. Tendencia en vivo
    trend = live_trend(df_m1)

    if trend is None:
        print("⛔ Sin tendencia clara")
        return None, None

    print(f"📈 Tendencia en vivo: {trend}")

    # 2. Impulso previo
    if not detect_impulse(df_m1, trend):
        print("⛔ Sin impulso claro")
        return None, trend

    # 3. Pullback (mitad)
    if not detect_pullback(df_m1, trend):
        print("⛔ No hay retroceso válido")
        return None, trend

    print("🔄 Pullback detectado")

    # 4. Evitar extremos
    if not not_at_extreme(df_m1, trend):
        print("⛔ Entrada en extremo")
        return None, trend

    # 5. Confirmación de fuerza
    if not strong_candle(df_m1, trend):
        print("⛔ Sin vela de fuerza")
        return None, trend

    print("🔥 Continuidad confirmada")

    # 6. Entrada final
    if trend == "up":
        return "call", trend

    if trend == "down":
        return "put", trend

    return None, trend
