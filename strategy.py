import numpy as np

# ==============================
# RESULTADOS
# ==============================
wins = 0
losses = 0

def update_result(result):
    global wins, losses

    if result > 0:
        wins += 1
    else:
        losses += 1

    print(f"📊 WIN: {wins} | LOSS: {losses}")


# ==============================
# ANALIZAR VELA
# ==============================
def analizar_vela(df):
    vela = df.iloc[-1]

    cuerpo = abs(vela["close"] - vela["open"])
    rango = vela["max"] - vela["min"]

    if rango == 0:
        return None

    fuerza = cuerpo / rango

    if fuerza < 0.5:
        return None

    if vela["close"] > vela["open"]:
        return "call"
    elif vela["close"] < vela["open"]:
        return "put"

    return None


# ==============================
# FILTRO IMPULSO
# ==============================
def filtro_impulso(df):
    ultimas = df.tail(6)

    alcistas = sum(ultimas["close"] > ultimas["open"])
    bajistas = sum(ultimas["close"] < ultimas["open"])

    return not (alcistas >= 4 or bajistas >= 4)


# ==============================
# FILTRO ZONA
# ==============================
def filtro_zona(df):
    precio = df["close"].iloc[-1]

    max_60 = df["max"].tail(60).max()
    min_60 = df["min"].tail(60).min()

    if abs(precio - max_60) < (max_60 * 0.0002):
        return False

    if abs(precio - min_60) < (min_60 * 0.0002):
        return False

    return True


# ==============================
# CONTINUIDAD
# ==============================
def filtro_continuidad(df, direccion):
    ultimas = df.tail(4)

    if direccion == "call":
        return sum(ultimas["close"] > ultimas["open"]) >= 2

    if direccion == "put":
        return sum(ultimas["close"] < ultimas["open"]) >= 2

    return False


# ==============================
# AGOTAMIENTO
# ==============================
def filtro_agotamiento(df):
    vela = df.iloc[-1]

    cuerpo = abs(vela["close"] - vela["open"])
    rango = vela["max"] - vela["min"]

    if rango == 0:
        return False

    return cuerpo >= (rango * 0.4)


# ==============================
# CONTRA TENDENCIA
# ==============================
def filtro_contra_tendencia(df, direccion):
    ultimas = df.tail(10)

    alcistas = sum(ultimas["close"] > ultimas["open"])
    bajistas = sum(ultimas["close"] < ultimas["open"])

    if bajistas >= 6 and direccion == "call":
        return False

    if alcistas >= 6 and direccion == "put":
        return False

    return True


# ==============================
# 🔥 DETECCIÓN DE MANIPULACIÓN
# ==============================
def detectar_manipulacion(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["max"] > prev["max"] and last["close"] < prev["max"]:
        return "put"

    if last["min"] < prev["min"] and last["close"] > prev["min"]:
        return "call"

    return None


# ==============================
# ⚡ FILTRO VELOCIDAD
# ==============================
def filtro_velocidad(df):
    rango = (df["max"] - df["min"]).tail(10).mean()
    return rango > 0.0003


# ==============================
# 🚫 MICRO RANGO
# ==============================
def micro_rango(df):
    ultimas = df.tail(5)
    rango = ultimas["max"].max() - ultimas["min"].min()
    return rango < 0.0005


# ==============================
# 💪 CONFIRMACIÓN FUERZA
# ==============================
def confirmacion_fuerza(df, direccion):
    last = df.iloc[-1]

    cuerpo = abs(last["close"] - last["open"])
    rango = last["max"] - last["min"]

    if rango == 0:
        return False

    fuerza = cuerpo / rango
    return fuerza > 0.6


# ==============================
# 🚀 SEÑAL FINAL
# ==============================
def pro_signal(df, aggressive=True):
    try:
        if len(df) < 60:
            return None

        direccion = analizar_vela(df)

        if direccion is None:
            return None

        # 🔥 Manipulación primero
        trap = detectar_manipulacion(df)
        if trap:
            direccion = trap

        if not filtro_velocidad(df):
            return None

        if micro_rango(df):
            return None

        if not filtro_impulso(df):
            return None

        if not filtro_zona(df):
            return None

        if not filtro_continuidad(df, direccion):
            return None

        if not filtro_agotamiento(df):
            return None

        if not filtro_contra_tendencia(df, direccion):
            return None

        if not confirmacion_fuerza(df, direccion):
            return None

        score = 40

        return {
            "direction": direccion,
            "score": score
        }

    except Exception as e:
        print("❌ ERROR estrategia:", e)
        return None
