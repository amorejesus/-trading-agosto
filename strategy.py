import time

last_signal_time = 0


# ==============================
# 🧠 TENDENCIA REAL EN M1
# ==============================
def trend_m1(df):
    highs = df["max"].iloc[-5:]
    lows = df["min"].iloc[-5:]

    up = all(x < y for x, y in zip(highs, highs[1:])) and \
         all(x < y for x, y in zip(lows, lows[1:]))

    down = all(x > y for x, y in zip(highs, highs[1:])) and \
           all(x > y for x, y in zip(lows, lows[1:]))

    if up:
        return "call"
    elif down:
        return "put"

    return None


# ==============================
# 🔥 FUERZA DE VELA (DOMINIO)
# ==============================
def candle_strength(candle):
    body = abs(candle["close"] - candle["open"])
    total = candle["max"] - candle["min"]

    if total == 0:
        return 0

    return body / total


# ==============================
# 🔁 CONTINUIDAD (MOVIMIENTO LIMPIO)
# ==============================
def continuity(df):
    candles = df.iloc[-4:]

    bullish = sum(1 for _, c in candles.iterrows() if c["close"] > c["open"])
    bearish = sum(1 for _, c in candles.iterrows() if c["close"] < c["open"])

    if bullish >= 3:
        return "call"
    elif bearish >= 3:
        return "put"

    return None


# ==============================
# ⚠️ EVITAR LATERAL
# ==============================
def is_lateral(df):
    recent = df.iloc[-10:]
    rango = recent["max"].max() - recent["min"].min()
    promedio = (recent["max"] - recent["min"]).mean()

    return rango < promedio * 2


# ==============================
# 🚫 EVITAR SOPORTE / RESISTENCIA
# ==============================
def near_zone(df):
    max_recent = df["max"].iloc[-20:].max()
    min_recent = df["min"].iloc[-20:].min()
    price = df.iloc[-2]["close"]

    if price >= max_recent * 0.999:
        return True

    if price <= min_recent * 1.001:
        return True

    return False


# ==============================
# ⚡ MICROESTRUCTURA (5s)
# ==============================
def microstructure(df_5s):
    if df_5s is None or len(df_5s) < 12:
        return None

    last = df_5s.iloc[-12:]  # últimos 60s

    up_moves = 0
    down_moves = 0

    for i in range(1, len(last)):
        if last.iloc[i]["close"] > last.iloc[i - 1]["close"]:
            up_moves += 1
        else:
            down_moves += 1

    # dominio claro
    if up_moves > down_moves * 1.5:
        return "call"

    elif down_moves > up_moves * 1.5:
        return "put"

    return None


# ==============================
# 🎯 FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_5s):
    global last_signal_time

    # validar data
    if df_m1 is None or df_5s is None:
        return None, 0

    if len(df_m1) < 30:
        return None, 0

    # ❌ evitar lateral
    if is_lateral(df_m1):
        return None, 0

    # ❌ evitar zonas peligrosas
    if near_zone(df_m1):
        return None, 0

    # 📈 tendencia M1
    trend = trend_m1(df_m1)
    if trend is None:
        return None, 0

    # 🔁 continuidad
    cont = continuity(df_m1)
    if cont != trend:
        return None, 0

    # ⚡ microestructura
    micro = microstructure(df_5s)
    if micro != trend:
        return None, 0

    # 🔥 fuerza vela actual
    last = df_m1.iloc[-2]
    strength = candle_strength(last)

    if strength < 0.65:
        return None, 0

    # ⏱️ evitar sobreoperar
    if time.time() - last_signal_time < 60:
        return None, 0

    last_signal_time = time.time()

    score = int(strength * 100)

    return trend, score
