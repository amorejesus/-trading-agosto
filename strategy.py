import pandas as pd

# ==============================
# 📊 ZONAS CLAVE (SOPORTE / RESISTENCIA)
# ==============================

def detect_resistance(df):
    if df is None or len(df) < 20:
        return None
    return df["max"].rolling(window=20).max().iloc[-1]


def detect_support(df):
    if df is None or len(df) < 20:
        return None
    return df["min"].rolling(window=20).min().iloc[-1]


def near_resistance(df, threshold=0.0005):
    resistance = detect_resistance(df)
    if resistance is None:
        return False

    price = df["close"].iloc[-1]
    return abs(price - resistance) < threshold


def near_support(df, threshold=0.0005):
    support = detect_support(df)
    if support is None:
        return False

    price = df["close"].iloc[-1]
    return abs(price - support) < threshold


# ==============================
# 🧠 MICROESTRUCTURA (M1)
# ==============================

def rejection_candle(df):
    if df is None or len(df) < 1:
        return None

    last = df.iloc[-1]

    body = abs(last["close"] - last["open"])
    upper_wick = last["max"] - max(last["close"], last["open"])
    lower_wick = min(last["close"], last["open"]) - last["min"]

    if body == 0:
        return None

    # rechazo arriba → posible caída
    if upper_wick > body * 2:
        return "bearish_rejection"

    # rechazo abajo → posible subida
    if lower_wick > body * 2:
        return "bullish_rejection"

    return None


def strong_candle(df):
    if df is None or len(df) < 1:
        return None

    last = df.iloc[-1]

    total = last["max"] - last["min"]
    body = abs(last["close"] - last["open"])

    if total == 0:
        return None

    strength = body / total

    if strength > 0.6:
        if last["close"] > last["open"]:
            return "bullish"
        else:
            return "bearish"

    return None


# ==============================
# 📈 TENDENCIA
# ==============================

def trend_m5(df):
    if df is None or len(df) < 5:
        return None

    highs = df["max"].tail(5)
    lows = df["min"].tail(5)

    if highs.is_monotonic_increasing and lows.is_monotonic_increasing:
        return "bullish"

    if highs.is_monotonic_decreasing and lows.is_monotonic_decreasing:
        return "bearish"

    return None


def trend_m1(df):
    if df is None or len(df) < 5:
        return None

    highs = df["max"].tail(5)
    lows = df["min"].tail(5)

    if highs.is_monotonic_increasing and lows.is_monotonic_increasing:
        return "bullish"

    if highs.is_monotonic_decreasing and lows.is_monotonic_decreasing:
        return "bearish"

    return None


# ==============================
# 🎯 SCORE INTELIGENTE
# ==============================

def calculate_score(t5, t1, strength, rejection):
    score = 0

    if t5:
        score += 30

    if t1:
        score += 25

    if strength:
        score += 25

    # penalizar rechazo
    if rejection is None:
        score += 20
    else:
        score -= 10

    return score


# ==============================
# 🚀 SEÑAL PRINCIPAL
# ==============================

def analyze_candle(df_m1, df_m5):
    try:
        # =========================
        # Validaciones básicas
        # =========================
        if df_m1 is None or df_m5 is None:
            print("⛔ DataFrame vacío")
            return None

        if len(df_m1) < 10 or len(df_m5) < 10:
            print("⛔ No hay suficientes datos")
            return None

        # =========================
        # 📈 TENDENCIA
        # =========================
        t5 = trend_m5(df_m5)
        t1 = trend_m1(df_m1)

        if not t5 or not t1:
            print("⛔ Sin tendencia clara")
            return None

        if t5 != t1:
            print("⚠️ Tendencias no alineadas")
            return None

        # =========================
        # 🧠 MICRO
        # =========================
        rejection = rejection_candle(df_m1)
        strength = strong_candle(df_m1)

        # =========================
        # 🎯 SCORE
        # =========================
        score = calculate_score(t5, t1, strength, rejection)

        if score < 70:
            print(f"⛔ Score bajo: {score}")
            return None

        # =========================
        # 🚫 FILTRO ZONAS
        # =========================
        if t5 == "bullish":

            if near_resistance(df_m5):
                print("🚫 Evitando CALL en resistencia")
                return None

            if rejection == "bearish_rejection":
                print("🚫 Rechazo bajista detectado")
                return None

            print(f"✅ CALL | Score: {score}")
            return "call"

        elif t5 == "bearish":

            if near_support(df_m5):
                print("🚫 Evitando PUT en soporte")
                return None

            if rejection == "bullish_rejection":
                print("🚫 Rechazo alcista detectado")
                return None

            print(f"✅ PUT | Score: {score}")
            return "put"

        return None

    except Exception as e:
        print("❌ Error en estrategia:", e)
        return None
