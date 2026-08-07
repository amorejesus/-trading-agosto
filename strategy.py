import pandas as pd
import json
import os

MEMORY_FILE = "ai_memory.json"
last_trend = None


# ==============================
# IA MEMORY
# ==============================
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"wins": 0, "losses": 0, "confidence": 0.5}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)


def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)


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
# PULLBACK
# ==============================
def pullback_m5(df, trend):
    candles = df.iloc[-4:-1]

    if trend == "up":
        return all(c["close"] < c["open"] for _, c in candles.iterrows())
    elif trend == "down":
        return all(c["close"] > c["open"] for _, c in candles.iterrows())

    return False


# ==============================
# MICROESTRUCTURA M1
# ==============================
def microstructure(df):
    last = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    total = last["max"] - last["min"]

    if total == 0:
        return 0

    body_ratio = body / total

    upper = last["max"] - max(last["open"], last["close"])
    lower = min(last["open"], last["close"]) - last["min"]

    score = 0

    # fuerza
    if body_ratio > 0.65:
        score += 2

    # rechazo bajo
    if upper < body * 0.4 and lower < body * 0.4:
        score += 2

    return score


# ==============================
# LATERAL
# ==============================
def is_lateral(df):
    recent = df.iloc[-10:]
    return (recent["max"].max() - recent["min"].min()) < (recent["max"] - recent["min"]).mean() * 2


# ==============================
# FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_m5):
    global last_trend

    memory = load_memory()

    if len(df_m1) < 20 or len(df_m5) < 10:
        return None, last_trend, 0

    trend = trend_m5(df_m5)

    if trend is None:
        return None, last_trend, 0

    # solo cambio de tendencia
    if last_trend == trend:
        return None, last_trend, 0

    if not pullback_m5(df_m5, trend):
        return None, last_trend, 0

    if is_lateral(df_m1):
        return None, last_trend, 0

    micro_score = microstructure(df_m1)

    # IA ajusta exigencia
    threshold = 3 + (0.5 - memory["confidence"]) * 2

    if micro_score < threshold:
        return None, last_trend, micro_score

    last = df_m1.iloc[-2]
    prev = df_m1.iloc[-3]

    if trend == "up" and last["close"] > prev["close"]:
        last_trend = trend
        return "call", trend, micro_score

    elif trend == "down" and last["close"] < prev["close"]:
        last_trend = trend
        return "put", trend, micro_score

    return None, last_trend, micro_score
