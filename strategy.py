import pandas as pd


MIN_CANDLES = 30
TREND_CANDLES = 15
DOMINANCE_CANDLES = 10
STRENGTH_CANDLES = 3


# ============================================================
# VALIDACIÓN
# ============================================================

def validate_dataframe(df):

    if df is None:
        return False

    if not isinstance(df, pd.DataFrame):
        return False

    required = ["open", "close", "max", "min"]

    if not all(column in df.columns for column in required):
        return False

    if len(df) < MIN_CANDLES:
        return False

    return True


# ============================================================
# TENDENCIA M1
# ============================================================

def live_trend(df):

    if not validate_dataframe(df):
        return None

    recent = df.iloc[-TREND_CANDLES:]

    highs = recent["max"].astype(float).values
    lows = recent["min"].astype(float).values
    closes = recent["close"].astype(float).values
    opens = recent["open"].astype(float).values

    higher_highs = 0
    higher_lows = 0
    lower_highs = 0
    lower_lows = 0

    for i in range(1, len(recent)):

        if highs[i] > highs[i - 1]:
            higher_highs += 1

        if lows[i] > lows[i - 1]:
            higher_lows += 1

        if highs[i] < highs[i - 1]:
            lower_highs += 1

        if lows[i] < lows[i - 1]:
            lower_lows += 1

    bullish = sum(
        closes[i] > opens[i]
        for i in range(len(recent))
    )

    bearish = sum(
        closes[i] < opens[i]
        for i in range(len(recent))
    )

    # Tendencia alcista
    if (
        higher_highs >= 9
        and higher_lows >= 9
        and bullish >= 9
    ):
        return "up"

    # Tendencia bajista
    if (
        lower_highs >= 9
        and lower_lows >= 9
        and bearish >= 9
    ):
        return "down"

    return None


# ============================================================
# DOMINIO
# ============================================================

def strong_dominance(df, trend):

    if not validate_dataframe(df):
        return False

    candles = df.iloc[-DOMINANCE_CANDLES:]

    bullish = 0
    bearish = 0

    for _, candle in candles.iterrows():

        if candle["close"] > candle["open"]:
            bullish += 1

        elif candle["close"] < candle["open"]:
            bearish += 1

    if trend == "up":
        return bullish >= 7

    if trend == "down":
        return bearish >= 7

    return False


# ============================================================
# VELAS DE FUERZA
# ============================================================

def strong_candles(df, trend):

    if not validate_dataframe(df):
        return False

    candles = df.iloc[-STRENGTH_CANDLES:]

    for _, candle in candles.iterrows():

        open_price = float(candle["open"])
        close_price = float(candle["close"])
        high = float(candle["max"])
        low = float(candle["min"])

        total_range = high - low
        body = abs(close_price - open_price)

        if total_range <= 0:
            return False

        body_ratio = body / total_range

        if body_ratio < 0.55:
            return False

        if trend == "up":

            if close_price <= open_price:
                return False

        elif trend == "down":

            if close_price >= open_price:
                return False

    return True


# ============================================================
# CONTINUIDAD
# ============================================================

def continuation(df, trend):

    if not validate_dataframe(df):
        return False

    # -1 = vela actual
    # -2 = última vela cerrada
    # -3 = vela anterior

    last_closed = df.iloc[-2]
    previous = df.iloc[-3]

    last_close = float(last_closed["close"])
    previous_close = float(previous["close"])

    if trend == "up":
        return last_close > previous_close

    if trend == "down":
        return last_close < previous_close

    return False


# ============================================================
# FILTRO VELA EXTREMA
# ============================================================

def avoid_extreme_entry(df):

    if not validate_dataframe(df):
        return False

    candle = df.iloc[-2]

    open_price = float(candle["open"])
    close_price = float(candle["close"])
    high = float(candle["max"])
    low = float(candle["min"])

    total_range = high - low
    body = abs(close_price - open_price)

    if total_range <= 0:
        return False

    body_ratio = body / total_range

    if body_ratio >= 0.90:
        return False

    return True


# ============================================================
# FILTRO DE UBICACIÓN
# ============================================================

def avoid_bad_location(
    df,
    lookback=20,
    tolerance=0.0003
):

    if not validate_dataframe(df):
        return False

    if len(df) < lookback + 3:
        return True

    closed = df.iloc[:-1]

    last_close = float(
        closed.iloc[-1]["close"]
    )

    recent_high = float(
        closed["max"].iloc[-lookback:].max()
    )

    recent_low = float(
        closed["min"].iloc[-lookback:].min()
    )

    distance_high = abs(
        last_close - recent_high
    )

    distance_low = abs(
        last_close - recent_low
    )

    if distance_high <= tolerance:
        return False

    if distance_low <= tolerance:
        return False

    return True


# ============================================================
# LECTURA DE LA ÚLTIMA VELA CERRADA
# ============================================================

def read_last_candle(df):

    if not validate_dataframe(df):
        return "unknown"

    candle = df.iloc[-2]

    if candle["close"] > candle["open"]:
        return "bullish"

    if candle["close"] < candle["open"]:
        return "bearish"

    return "neutral"


# ============================================================
# STRUCTURE SCORE
# ============================================================

def structure_score(df, trend):

    if not validate_dataframe(df):
        return 0

    recent = df.iloc[-8:]

    highs = recent["max"].astype(float).values
    lows = recent["min"].astype(float).values

    score = 0

    if trend == "up":

        for i in range(1, len(recent)):

            if highs[i] > highs[i - 1]:
                score += 1

            if lows[i] > lows[i - 1]:
                score += 1

    elif trend == "down":

        for i in range(1, len(recent)):

            if highs[i] < highs[i - 1]:
                score += 1

            if lows[i] < lows[i - 1]:
                score += 1

    return min(score, 5)


# ============================================================
# FUNCIÓN COMPATIBLE CON bot.py
# ============================================================

def check_pattern(df):

    return analyze_candle(df)


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def analyze_candle(df_m1, df_m5=None):

    if not validate_dataframe(df_m1):

        print("⛔ Datos M1 insuficientes o incorrectos")

        return None, None

    # --------------------------------------------------------
    # 1. TENDENCIA
    # --------------------------------------------------------

    trend = live_trend(df_m1)

    if trend is None:

        print("⛔ Sin tendencia clara M1")

        return None, None

    print(f"📈 Tendencia M1: {trend}")

    # --------------------------------------------------------
    # 2. DOMINIO
    # --------------------------------------------------------

    if not strong_dominance(df_m1, trend):

        print("⛔ Sin dominio claro")

        return None, trend

    print("💪 Dominio confirmado")

    # --------------------------------------------------------
    # 3. ESTRUCTURA
    # --------------------------------------------------------

    score = structure_score(
        df_m1,
        trend
    )

    print(f"📊 Structure Score: {score}/5")

    if score < 5:

        print("⛔ Estructura insuficiente")

        return None, trend

    # --------------------------------------------------------
    # 4. VELAS DE FUERZA
    # --------------------------------------------------------

    if not strong_candles(
        df_m1,
        trend
    ):

        print("⛔ Sin velas de fuerza")

        return None, trend

    print("🔥 Velas de fuerza confirmadas")

    # --------------------------------------------------------
    # 5. CONTINUIDAD
    # --------------------------------------------------------

    if not continuation(
        df_m1,
        trend
    ):

        print("⛔ Sin continuidad")

        return None, trend

    print("🚀 Continuidad confirmada")

    # --------------------------------------------------------
    # 6. UBICACIÓN
    # --------------------------------------------------------

    if not avoid_bad_location(df_m1):

        print(
            "⛔ Mala ubicación / "
            "posible zona de reversión"
        )

        return None, trend

    print("📍 Ubicación aceptable")

    # --------------------------------------------------------
    # 7. VELA EXTREMA
    # --------------------------------------------------------

    if not avoid_extreme_entry(df_m1):

        print(
            "⛔ Vela demasiado extendida"
        )

        return None, trend

    # --------------------------------------------------------
    # 8. LECTURA
    # --------------------------------------------------------

    candle_read = read_last_candle(
        df_m1
    )

    print(
        f"🕯️ Última vela cerrada: "
        f"{candle_read}"
    )

    # --------------------------------------------------------
    # 9. ENTRADA
    # --------------------------------------------------------

    if trend == "up":

        print(
            "🎯 CALL - "
            "CONTINUIDAD ALCISTA"
        )

        return "call", trend

    if trend == "down":

        print(
            "🎯 PUT - "
            "CONTINUIDAD BAJISTA"
        )

        return "put", trend

    return None, trend
