import pandas as pd

# ==============================
# 🔹 UTILIDADES
# ==============================

def get_trend(df):
    highs = df["max"].tail(5).values
    lows = df["min"].tail(5).values

    if all(highs[i] > highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] > lows[i-1] for i in range(1, len(lows))):
        return "bullish"

    if all(highs[i] < highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] < lows[i-1] for i in range(1, len(lows))):
        return "bearish"

    return "lateral"


def is_strong_candle(candle):
    body = abs(candle["close"] - candle["open"])
    wick = (candle["max"] - candle["min"]) - body
    return body > wick * 1.2  # 🔥 más flexible


def has_pullback(df, trend):
    last = df.tail(4)

    if trend == "bullish":
        return all(last["close"].iloc[i] < last["close"].iloc[i-1] for i in range(1, len(last)))

    if trend == "bearish":
        return all(last["close"].iloc[i] > last["close"].iloc[i-1] for i in range(1, len(last)))

    return False


def no_lateral_zone(df):
    high = df["max"].tail(20).max()
    low = df["min"].tail(20).min()

    range_size = high - low

    # 🔥 MÁS FLEXIBLE PARA OTC
    return range_size > 0.0002


# ==============================
# 🔥 MICROSTRUCTURA
# ==============================

def microstructure_score(df):
    last = df.iloc[-1]

    body = last["close"] - last["open"]
    range_total = last["max"] - last["min"]

    if range_total == 0:
        return 0

    return abs(body) / range_total


# ==============================
# 🧠 IA PRINCIPAL
# ==============================

def analyze_candle(df_m1, df_m5):
    try:
        trend_m5 = get_trend(df_m5)
        trend_m1 = get_trend(df_m1)

        if trend_m5 == "lateral":
            return None

        if not no_lateral_zone(df_m5):
            return None

        pullback = has_pullback(df_m1, trend_m5)

        last_candle = df_m1.iloc[-1]
        strong = is_strong_candle(last_candle)

        micro_score = microstructure_score(df_m1)

        # ==========================
        # 🎯 SCORE
        # ==========================

        score = 0

        if trend_m5 == trend_m1:
            score += 30

        if pullback:
            score += 15  # 🔽 bajado

        if strong:
            score += 20  # 🔽 bajado

        if micro_score > 0.5:
            score += 20  # 🔽 más fácil

        # ==========================
        # 📊 DEBUG (CLAVE)
        # ==========================

        print(f"""
PAIR DEBUG
Trend M5: {trend_m5}
Trend M1: {trend_m1}
Pullback: {pullback}
Strong: {strong}
Micro: {micro_score:.2f}
Score: {score}
""")

        # ==========================
        # 🚀 DECISIÓN
        # ==========================

        if score >= 55:  # 🔥 MÁS FLEXIBLE

            if trend_m5 == "bullish":
                return ("call", score)

            elif trend_m5 == "bearish":
                return ("put", score)

        return None

    except Exception as e:
        print("Error strategy:", e)
        return None
