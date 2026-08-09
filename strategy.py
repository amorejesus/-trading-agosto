import pandas as pd


# ============================================================
# ⚙️ CONFIGURACIÓN
# ============================================================

MIN_CANDLES = 30
TREND_CANDLES = 15
DOMINANCE_CANDLES = 10
STRENGTH_CANDLES = 3


# ============================================================
# 🧹 VALIDACIÓN DEL DATAFRAME
# ============================================================

def validate_dataframe(df):
    """
    Comprueba que el DataFrame tenga las columnas necesarias.
    """

    if df is None:
        return False

    if not isinstance(df, pd.DataFrame):
        return False

    required = ["open", "close", "max", "min"]

    for column in required:
        if column not in df.columns:
            return False

    if len(df) < MIN_CANDLES:
        return False

    return True


# ============================================================
# 🔥 TENDENCIA CLARA EN M1
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

    # ========================================================
    # 📈 TENDENCIA ALCISTA
    # ========================================================

    if (
        higher_highs >= 9
        and higher_lows >= 9
        and bullish >= 9
    ):
        return "up"

    # ========================================================
    # 📉 TENDENCIA BAJISTA
    # ========================================================

    if (
        lower_highs >= 9
        and lower_lows >= 9
        and bearish >= 9
    ):
        return "down"

    return None


# ============================================================
# 💥 DOMINIO DEL MERCADO
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
# 🔥 VELAS DE FUERZA
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

        # Evitar división por cero
        if total_range <= 0:
            return False

        body_ratio = body / total_range

        # Cuerpo mínimo
        if body_ratio < 0.55:
            return False

        # Dirección
        if trend == "up":

            if close_price <= open_price:
                return False

        elif trend == "down":

            if close_price >= open_price:
                return False

    return True


# ============================================================
# 🚀 CONTINUIDAD
# ============================================================

def continuation(df, trend):

    if not validate_dataframe(df):
        return False

    # --------------------------------------------------------
    # IMPORTANTE:
    # -1 = vela actual / posiblemente todavía abierta
    # -2 = última vela cerrada
    # -3 = vela anterior
    # --------------------------------------------------------

    last_closed = df.iloc[-2]
    previous = df.iloc[-3]

    last_close = float(last_closed["close"])
    previous_close = float(previous["close"])

    if trend == "up":
