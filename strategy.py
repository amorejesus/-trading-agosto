import pandas as pd

# =========================
# VELA FUERTE SIN MECHAS
# =========================
def vela_fuerte_sin_mecha(df):
    try:
        vela = df.iloc[-2]

        open_ = float(vela["open"])
        close = float(vela["close"])
        high = float(vela["max"])
        low = float(vela["min"])

        cuerpo = abs(close - open_)
        rango = high - low

        if rango == 0:
            return None

        mecha_sup = high - max(open_, close)
        mecha_inf = min(open_, close) - low

        # vela fuerte real (sin mechas)
        if mecha_sup < cuerpo * 0.1 and mecha_inf < cuerpo * 0.1:

            # evitar velas pequeñas
            if cuerpo < (rango * 0.6):
                return None

            if close > open_:
                return "call"
            elif close < open_:
                return "put"

        return None

    except:
        return None


# =========================
# PULLBACK REAL
# =========================
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

        for i in range(len(closes) - 1, -1, -1):
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

        # validar tamaño del pullback
        if retroceso < 2 or retroceso > 4:
            return False

        # validar debilidad
        for i in range(-retroceso, 0):
            cuerpo = abs(closes[i] - opens[i])
            rango = highs[i] - lows[i]

            if rango == 0:
                return False

            fuerza = cuerpo / rango

            if fuerza > 0.5:
                return False

        # confirmación (vela fuerte)
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

        if direction == "call" and close > open_:
            return True

        if direction == "put" and close < open_:
            return True

        return False

    except:
        return False


# =========================
# SEÑAL PRINCIPAL
# =========================
def pro_signal(df):
    try:
        if df is None or len(df) < 30:
            return None

        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        # 1. detectar vela fuerte sin mecha
        direccion = vela_fuerte_sin_mecha(df)

        if not direccion:
            return None

        # 2. validar pullback real
        if not pullback_filter(df, direccion):
            return None

        return direccion

    except Exception as e:
        print("Error estrategia:", e)
        return None
