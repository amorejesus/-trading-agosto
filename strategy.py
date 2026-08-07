import pandas as pd

last_trend = None


# ==============================
# TENDENCIA M5
# ==============================
def trend_m5(df):
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
# PULLBACK EN M5
# ==============================
def pullback_m5(df, trend):
    candles = df.iloc[-4:-1]

    if trend == "up":
        return all(c["close"] < c["open"] for _, c in candles.iterrows())

    elif trend == "down":
        return all(c["close"] > c["open"] for _, c in candles.iterrows())

    return False


# ==============================
# VELA SNIPER M1
# ==============================
def sniper_entry(df):
    last = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    range_candle = last["max"] - last["min"]

    if range_candle == 0:
        return False

    body_ratio = body / range_candle

    upper_wick = last["max"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["min"]

    # 🔥 vela limpia (sin manipulación)
    return body_ratio > 0.65 and upper_wick < body * 0.4 and lower_wick < body * 0.4


# ==============================
# EVITAR LATERAL M1
# ==============================
def is_lateral(df):
    recent = df.iloc[-10:]
    return (recent["max"].max() - recent["min"].min()) < (recent["max"] - recent["min"]).mean() * 2


# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_m5):
    global last_trend

    if df_m1 is None or df_m5 is None:
        return None, last_trend

    if len(df_m1) < 20 or len(df_m5) < 10:
        return None, last_trend

    trend = trend_m5(df_m5)

    if trend is None:
        return None, last_trend

    # 🔥 SOLO 1 TRADE POR CAMBIO
    if last_trend == trend:
        return None, last_trend

    # 🔥 esperar pullback real
    if not pullback_m5(df_m5, trend):
        return None, last_trend

    # ❌ evitar lateral
    if is_lateral(df_m1):
        return None, last_trend

    # 🔥 confirmación sniper
    if not sniper_entry(df_m1):
        return None, last_trend

    last = df_m1.iloc[-2]
    prev = df_m1.iloc[-3]

    # ==============================
    # ENTRADA FINAL
    # ==============================
    if trend == "up" and last["close"] > prev["close"]:
        last_trend = trend
        return "call", trend

    elif trend == "down" and last["close"] < prev["close"]:
        last_trend = trend
        return "put", trend

    return None, last_trend
