import pandas as pd

# ==============================
# 🔹 UTILIDADES
# ==============================

def get_trend(df):
    """Detectar tendencia por estructura"""
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
    """Detecta vela fuerte (impulso real)"""
    body = abs(candle["close"] - candle["open"])
    wick = (candle["max"] - candle["min"]) - body

    if body > wick * 1.5:
        return True

    return False


def has_pullback(df, trend):
    """Detecta retroceso de 2-4 velas"""
    last = df.tail(4)

    if trend == "bullish":
        return all(last["close"].iloc[i] < last["close"].iloc[i-1] for i in range(1, len(last)))

    if trend == "bearish":
        return all(last["close"].iloc[i] > last["close"].iloc[i-1] for i in range(1, len(last)))

    return False


def no_lateral_zone(df):
    """Evitar rango"""
    high = df["max"].tail(20).max()
    low = df["min"].tail(20).min()

    range_size = high - low

    # si rango muy pequeño → lateral
    return range_size > 0.0005


# ==============================
# 🔥 MICROSTRUCTURA (SNIPER)
# ==============================

def microstructure_score(df):
    """
    Analiza la última vela como microestructura
    """
    last = df.iloc[-1]

    body = last["close"] - last["open"]
    range_total = last["max"] - last["min"]

    if range_total == 0:
        return 0

    strength = abs(body) / range_total

    return strength  # 0 a 1


# ==============================
# 🧠 IA PRINCIPAL
# ==============================

def analyze_candle(df_m1, df_m5):
    """
    Devuelve:
    - "call"
    - "put"
    - ("call", score)
    - None
    """

    try:
        # 🔹 Tendencias
        trend_m5 = get_trend(df_m5)
        trend_m1 = get_trend(df_m1)

        # ❌ evitar lateral
        if trend_m5 == "lateral":
            return None

        # ❌ evitar zonas muertas
        if not no_lateral_zone(df_m5):
            return None

        # 🔹 Pullback
        pullback = has_pullback(df_m1, trend_m5)

        # 🔹 Vela fuerte confirmación
        last_candle = df_m1.iloc[-1]
        strong = is_strong_candle(last_candle)

        # 🔹 Microestructura
        micro_score = microstructure_score(df_m1)

        # ==========================
        # 🎯 SCORE IA
        # ==========================

        score = 0

        if trend_m5 == trend_m1:
            score += 30

        if pullback:
            score += 20

        if strong:
            score += 25

        if micro_score > 0.6:
            score += 25

        # ==========================
        # 🚀 DECISIÓN FINAL
        # ==========================

        if score >= 70:

            if trend_m5 == "bullish":
                return ("call", score)

            elif trend_m5 == "bearish":
                return ("put", score)

        return None

    except Exception as e:
        print("Error strategy:", e)
        return None
