import pandas as pd

MIN_CANDLES = 30


# ============================================================
# 🔥 TENDENCIA CLARA EN M1
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

    # Dominancia
    bullish = sum(closes > opens)
    bearish = sum(closes < opens)

    # Tendencia fuerte
    if higher_highs >= 9 and higher_lows >= 9 and bullish >= 10:
        return "up"

    if lower_highs >= 9 and lower_lows >= 9 and bearish >= 10:
        return "down"

    return None


# ============================================================
# 💥 DOMINIO DEL MERCADO
# ============================================================

def strong_dominance(df, trend):

    candles = df.iloc[-10:]

    if trend == "up":
        bullish = sum(c["close"] > c["open"] for _, c in candles.iterrows())
        return bullish >= 7

    if trend == "down":
        bearish = sum(c["close"] < c["open"] for _, c in candles.iterrows())
        return bearish >= 7

    return False


# ============================================================
# 🔥 VELAS DE FUERZA (CUERPO GRANDE)
# ============================================================

def strong_candles(df, trend):

    candles = df.iloc[-3:]

    for _, c in candles.iterrows():

        body = abs(c["close"] - c["open"])
        total = c["max"] - c["min"]

        if total == 0:
            return False

        body_ratio = body / total

        # Debe ser vela fuerte
        if body_ratio < 0.6:
            return False

        # Dirección correcta
        if trend == "up" and c["close"] <= c["open"]:
            return False

        if trend == "down" and c["close"] >= c["open"]:
            return False

    return True


# ============================================================
# 🚀 CONTINUIDAD
# ============================================================

def continuation(df, trend):

    last = df.iloc[-2]
    prev = df.iloc[-3]

    if trend == "up":
        return last["close"] > prev["close"]

    if trend == "down":
        return last["close"] < prev["close"]

    return False


# ============================================================
# 🚫 FILTRO ANTI VELA EXTREMA (EVITA ENTRAR TARDE)
# ============================================================

def avoid_extreme_entry(df):

    last = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    total = last["max"] - last["min"]

    if total == 0:
        return False

    # Si la vela es exageradamente grande → probablemente ya explotó
    return body < (total * 0.9)


# ============================================================
# 🧠 FUNCIÓN PRINCIPAL
# ============================================================

def analyze_candle(df_m1, df_m5=None):

    if df_m1 is None or len(df_m1) < MIN_CANDLES:
        return None, None

    # 1. Tendencia clara
    trend = live_trend(df_m1)

    if trend is None:
        print("⛔ Sin tendencia clara M1")
        return None, None

    print(f"📈 Tendencia: {trend}")

    # 2. Dominio del mercado
    if not strong_dominance(df_m1, trend):
        print("⛔ Sin dominio claro")
        return None, trend

    # 3. Velas fuertes
    if not strong_candles(df_m1, trend):
        print("⛔ Sin velas de fuerza")
        return None, trend

    # 4. Continuidad real
    if not continuation(df_m1, trend):
        print("⛔ Sin continuidad")
        return None, trend

    # 5. Evitar entrar demasiado tarde
    if not avoid_extreme_entry(df_m1):
        print("⛔ Vela demasiado extendida (riesgo alto)")
        return None, trend

    print("🔥 FUERZA + DOMINIO + CONTINUIDAD CONFIRMADA")

    # 6. Entrada
    if trend == "up":
        print("🎯 CALL")
        return "call", trend

    if trend == "down":
        print("🎯 PUT")
        return "put", trend

    return None, trend
