import pandas as pd

last_signal_time = 0


# ==============================
# 🔥 DETECTAR FUERZA REAL
# ==============================
def strong_candle(candle):
    body = abs(candle["close"] - candle["open"])
    total = candle["max"] - candle["min"]

    if total == 0:
        return False

    body_ratio = body / total

    upper_wick = candle["max"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["min"]

    # 🔥 vela fuerte = cuerpo dominante + pocas mechas
    return body_ratio > 0.7 and upper_wick < body * 0.3 and lower_wick < body * 0.3


# ==============================
# 🔥 DETECTAR CONTINUIDAD (CLAVE)
# ==============================
def momentum_sequence(df):
    c1 = df.iloc[-2]
    c2 = df.iloc[-3]
    c3 = df.iloc[-4]

    # CALL: 3 velas fuertes alcistas consecutivas
    if (
        strong_candle(c1)
        and strong_candle(c2)
        and strong_candle(c3)
        and c1["close"] > c1["open"]
        and c2["close"] > c2["open"]
        and c3["close"] > c3["open"]
        and c1["close"] > c2["close"] > c3["close"]
    ):
        return "call"

    # PUT: 3 velas fuertes bajistas consecutivas
    if (
        strong_candle(c1)
        and strong_candle(c2)
        and strong_candle(c3)
        and c1["close"] < c1["open"]
        and c2["close"] < c2["open"]
        and c3["close"] < c3["open"]
        and c1["close"] < c2["close"] < c3["close"]
    ):
        return "put"

    return None


# ==============================
# ⚠️ EVITAR MERCADO MUERTO
# ==============================
def low_volatility(df):
    recent = df.iloc[-10:]

    avg_range = (recent["max"] - recent["min"]).mean()
    total_range = recent["max"].max() - recent["min"].min()

    # si el rango total es muy pequeño → mercado muerto
    return total_range < avg_range * 2


# ==============================
# 🚀 FUNCIÓN PRINCIPAL
# ==============================
def analyze_candle(df_m1, df_m5=None):
    global last_signal_time

    if df_m1 is None or len(df_m1) < 10:
        return None, None

    # ❌ evitar mercado sin movimiento
    if low_volatility(df_m1):
        return None, None

    # 🔥 detectar momentum real
    direction = momentum_sequence(df_m1)

    if direction is None:
        return None, None

    # ⏱️ evitar sobreoperar (1 trade cada 30s)
    import time
    if time.time() - last_signal_time < 30:
        return None, None

    last_signal_time = time.time()

    # 🎯 score alto porque es entrada fuerte
    score = 90

    return direction, score
