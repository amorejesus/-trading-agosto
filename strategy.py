import pandas as pd

last_trend = None  # 🔥 memoria global


# ==============================
# DETECTAR TENDENCIA
# ==============================
def detect_trend(df):
    if len(df) < 10:
        return None

    highs = df["max"].iloc[-6:]
    lows = df["min"].iloc[-6:]

    up = all(x < y for x, y in zip(highs, highs[1:])) and \
         all(x < y for x, y in zip(lows, lows[1:]))

    down = all(x > y for x, y in zip(highs, highs[1:])) and \
           all(x > y for x, y in zip(lows, lows[1:]))

    if up:
        return "up"
    elif down:
        return "down"

    return None


# ==============================
# LATERAL
# ==============================
def is_lateral(df):
    recent = df.iloc[-15:]

    max_range = recent["max"].max()
    min_range = recent["min"].min()

    return (max_range - min_range) < (recent["max"] - recent["min"]).mean() * 3


# ==============================
# VELA FUERTE
# ==============================
def strong_candle(df):
    last = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    range_candle = last["max"] - last["min"]

    if range_candle == 0:
        return False

    body_ratio = body / range_candle

    upper_wick = last["max"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["min"]

    return body_ratio > 0.6 and upper_wick < body * 0.5 and lower_wick < body * 0.5


# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_m5, df_m15):
    global last_trend

    if df_m1 is None or df_m5 is None or df_m15 is None:
        return None, last_trend

    if len(df_m1) < 20 or len(df_m5) < 10 or len(df_m15) < 10:
        return None, last_trend

    # 🔥 tendencias
    trend_m15 = detect_trend(df_m15)
    trend_m5 = detect_trend(df_m5)

    if trend_m15 is None or trend_m5 is None:
        return None, last_trend

    # ❌ si no coinciden → no operar
    if trend_m15 != trend_m5:
        return None, last_trend

    # 🔥 SOLO OPERAR SI CAMBIA LA TENDENCIA
    if last_trend == trend_m15:
        return None, last_trend

    # ❌ evitar lateral
    if is_lateral(df_m1):
        return None, last_trend

    # ✔ vela fuerte
    if not strong_candle(df_m1):
        return None, last_trend

    last = df_m1.iloc[-2]
    prev = df_m1.iloc[-3]

    # ==============================
    # DECISIÓN FINAL
    # ==============================
    if trend_m15 == "up" and last["close"] > prev["close"]:
        last_trend = trend_m15
        return "call", last_trend

    elif trend_m15 == "down" and last["close"] < prev["close"]:
        last_trend = trend_m15
        return "put", last_trend

    return None, last_trend
