import pandas as pd

=========================

PULLBACK REAL

=========================

def pullback_filter(df, direction):
try:
if len(df) < 20:
return False

    candles = df.iloc[-6:-1]

    closes = candles["close"].astype(float).values
    opens = candles["open"].astype(float).values
    highs = candles["max"].astype(float).values
    lows = candles["min"].astype(float).values

    retroceso = 0

    for i in range(len(closes) - 1, 0, -1):
        if direction == "call":
            if closes[i] < opens[i]:
                retroceso += 1
            else:
                break

        elif direction == "put":
            if closes[i] > opens[i]:
                retroceso += 1
            else:
                break

    # validar longitud del pullback
    if retroceso < 2 or retroceso > 4:
        return False

    # validar debilidad del retroceso
    for i in range(-retroceso, 0):
        cuerpo = abs(closes[i] - opens[i])
        rango = highs[i] - lows[i]

        if rango == 0:
            return False

        fuerza = cuerpo / rango

        if fuerza > 0.5:
            return False

    # vela de confirmación
    last = df.iloc[-2]

    open_ = float(last["open"])
    close = float(last["close"])
    high = float(last["max"])
    low = float(last["min"])

    rango = high - low
    if rango == 0:
        return False

    cuerpo = abs(close - open_)
    fuerza = cuerpo / rango

    if fuerza < 0.6:
        return False

    # confirmación dirección
    if direction == "call" and close > open_:
        return True

    if direction == "put" and close < open_:
        return True

    return False

except:
    return False

=========================

SEÑAL PRINCIPAL

=========================

def pro_signal(df):
try:
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
    if rango == 0:
        return None

    cuerpo = abs(close - open_)
    fuerza = cuerpo / rango

    # =========================
    # FILTRO FUERZA
    # =========================
    if fuerza < 0.55:
        return None

    # =========================
    # MECHAS
    # =========================
    mecha_sup = high - max(open_, close)
    mecha_inf = min(open_, close) - low

    # evitar indecisión
    if mecha_sup > cuerpo and mecha_inf > cuerpo:
        return None

    # =========================
    # TENDENCIA REAL
    # =========================
    closes = df["close"].astype(float)
    ultimos = closes.iloc[-10:]

    alcista = all(x < y for x, y in zip(ultimos, ultimos[1:]))
    bajista = all(x > y for x, y in zip(ultimos, ultimos[1:]))

    # =========================
    # FILTRO LATERALIDAD
    # =========================
    rango_total = max(ultimos) - min(ultimos)

    if rango_total < (closes.mean() * 0.001):
        return None

    # =========================
    # EVITAR VELAS TRAMPA
    # =========================
    if cuerpo > (rango * 0.9):
        return None

    # =========================
    # CONTINUIDAD ALCISTA
    # =========================
    if (
        close > open_
        and close > float(prev["close"])
        and float(prev["close"]) > float(prev2["close"])
        and mecha_sup < cuerpo * 0.4
        and alcista
    ):
        return "call"

    # =========================
    # CONTINUIDAD BAJISTA
    # =========================
    if (
        close < open_
        and close < float(prev["close"])
        and float(prev["close"]) < float(prev2["close"])
        and mecha_inf < cuerpo * 0.4
        and bajista
    ):
        return "put"

    return None

except Exception as e:
    print("Error en estrategia:", e)
    return None
