# ==============================
# RESULTADOS
# ==============================
wins = 0
losses = 0

def update_result(result):
    global wins, losses

    try:
        result = float(result)
    except:
        result = 0

    if result > 0:
        wins += 1
    else:
        losses += 1

    print(f"📊 WIN: {wins} | LOSS: {losses}", flush=True)


# ==============================
# ANALIZAR VELA
# ==============================
def analizar_vela(vela):
    open_ = vela["open"]
    close = vela["close"]
    high = vela["max"]
    low = vela["min"]

    cuerpo = abs(close - open_)
    rango = high - low

    if rango == 0:
        return None

    fuerza = cuerpo / rango

    return {
        "alcista": close > open_,
        "bajista": close < open_,
        "cuerpo": cuerpo,
        "rango": rango,
        "fuerza": fuerza,
        "open": open_,
        "close": close,
        "high": high,
        "low": low
    }


# ==============================
# DETECTAR TENDENCIA
# ==============================
def detectar_tendencia(df):
    ultimas = df.tail(5)

    highs = ultimas["max"].values
    lows = ultimas["min"].values

    alcista = all(highs[i] > highs[i-1] for i in range(1, len(highs)))
    bajista = all(lows[i] < lows[i-1] for i in range(1, len(lows)))

    if alcista:
        return "call"

    if bajista:
        return "put"

    return None


# ==============================
# SEÑAL PRINCIPAL (CORREGIDA)
# ==============================
def pro_signal(df):

    if len(df) < 10:
        return None

    # 🔥 USAMOS SOLO VELAS CERRADAS
    vela_fuerza = df.iloc[-3]
    vela_confirm = df.iloc[-2]

    info_fuerza = analizar_vela(vela_fuerza)
    info_confirm = analizar_vela(vela_confirm)

    if info_fuerza is None or info_confirm is None:
        return None

    # ==============================
    # TENDENCIA
    # ==============================
    direccion = detectar_tendencia(df)

    if direccion is None:
        return None

    # ==============================
    # IMPULSO (vela fuerte)
    # ==============================
    if info_fuerza["fuerza"] < 0.6:
        return None

    if direccion == "call" and not info_fuerza["alcista"]:
        return None

    if direccion == "put" and not info_fuerza["bajista"]:
        return None

    # ==============================
    # 🔥 VALIDACIÓN REAL (ANTI ERROR)
    # ==============================
    if direccion == "call":

        # ❌ si vela roja → cancelar
        if info_confirm["close"] <= info_confirm["open"]:
            return None

        # ❌ si rompe mínimo → giro
        if info_confirm["low"] < info_fuerza["low"]:
            return None

    if direccion == "put":

        # ❌ si vela verde → cancelar
        if info_confirm["close"] >= info_confirm["open"]:
            return None

        # ❌ si rompe máximo → giro
        if info_confirm["high"] > info_fuerza["high"]:
            return None

    # ==============================
    # FUERZA CONFIRMACIÓN
    # ==============================
    if info_confirm["fuerza"] < 0.55:
        return None

    # ==============================
    # SEÑAL FINAL
    # ==============================
    return direccion, "continuidad_sniper", 100
