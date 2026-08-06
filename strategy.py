import pandas as pd

def pro_signal(df):
try:
# =========================
# VALIDACIÓN
# =========================
if df is None or len(df) < 30:
return None

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # =========================
    # VELAS CLAVE
    # =========================
    last = df.iloc[-2]
    prev = df.iloc[-3]
    prev2 = df.iloc[-4]

    open_ = float(last["open"])
    close = float(last["close"])
    high = float(last["max"])
    low = float(last["min"])

    rango = high - low
    cuerpo = abs(close - open_)

    if rango == 0:
        return None

    fuerza = cuerpo / rango

    # =========================
    # FILTRO DE FUERZA
    # =========================
    if fuerza < 0.55:
        return None

    # =========================
    # MECHAS
    # =========================
    mecha_sup = high - max(open_, close)
    mecha_inf = min(open_, close) - low

    # evitar indecisión total
    if mecha_sup > cuerpo and mecha_inf > cuerpo:
        return None

    # =========================
    # TENDENCIA REAL (estructura)
    # =========================
    closes = df["close"].astype(float)

    # últimos swings
    ultimos = closes.iloc[-10:]

    maximos_crecientes = all(x < y for x, y in zip(ultimos, ultimos[1:]))
    minimos_decrecientes = all(x > y for x, y in zip(ultimos, ultimos[1:]))

    # =========================
    # FILTRO DE RANGO
    # =========================
    rango_total = max(ultimos) - min(ultimos)

    if rango_total < (closes.mean() * 0.001):
        return None  # mercado lateral

    # =========================
    # EVITAR SOBREEXTENSIÓN
    # =========================
    if cuerpo > (rango * 0.9):
        return None  # vela exagerada (posible trampa)

    # =========================
    # CONTINUIDAD ALCISTA (CALL)
    # =========================
    if (
        close > open_
        and close > float(prev["close"])
        and float(prev["close"]) > float(prev2["close"])
        and mecha_sup < cuerpo * 0.4
        and maximos_crecientes
    ):
        return "call"

    # =========================
    # CONTINUIDAD BAJISTA (PUT)
    # =========================
    if (
        close < open_
        and close < float(prev["close"])
        and float(prev["close"]) < float(prev2["close"])
        and mecha_inf < cuerpo * 0.4
        and minimos_decrecientes
    ):
        return "put"

    return None

except Exception as e:
    print("Error en estrategia:", e)
    return None
