import numpy as np

# ========= HELPERS =========

def tendencia_m5(df):
    if len(df) < 20:
        return None

    highs = [c['max'] for c in df[-10:]]
    lows = [c['min'] for c in df[-10:]]

    if all(highs[i] > highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] > lows[i-1] for i in range(1, len(lows))):
        return "call"

    if all(highs[i] < highs[i-1] for i in range(1, len(highs))) and \
       all(lows[i] < lows[i-1] for i in range(1, len(lows))):
        return "put"

    return None


def evitar_rango(df):
    closes = [c['close'] for c in df[-20:]]
    rango = max(closes) - min(closes)

    return rango > (np.mean(closes) * 0.001)  # evita mercado lateral


def pullback_valido(df, tendencia):
    velas = df[-5:]

    if tendencia == "call":
        bajistas = sum(1 for v in velas if v['close'] < v['open'])
        return 2 <= bajistas <= 4

    if tendencia == "put":
        alcistas = sum(1 for v in velas if v['close'] > v['open'])
        return 2 <= alcistas <= 4

    return False


def vela_fuerza(df, tendencia):
    vela = df[-1]

    cuerpo = abs(vela['close'] - vela['open'])
    rango = vela['max'] - vela['min']

    if rango == 0:
        return False

    fuerza = cuerpo / rango

    if tendencia == "call":
        return vela['close'] > vela['open'] and fuerza > 0.6

    if tendencia == "put":
        return vela['close'] < vela['open'] and fuerza > 0.6

    return False


def rechazo_mecha(df, tendencia):
    vela = df[-1]

    upper_wick = vela['max'] - max(vela['close'], vela['open'])
    lower_wick = min(vela['close'], vela['open']) - vela['min']

    if tendencia == "call":
        return lower_wick > upper_wick  # rechazo abajo

    if tendencia == "put":
        return upper_wick > lower_wick  # rechazo arriba

    return False


def evitar_fake_breakout(df):
    ultima = df[-1]
    anterior = df[-2]

    # evita velas exageradas
    rango = ultima['max'] - ultima['min']
    rango_prev = anterior['max'] - anterior['min']

    return rango < (rango_prev * 2)


# ========= SCORE =========

def calcular_score(tendencia, df_m5, df_m1):
    score = 0

    if tendencia:
        score += 2

    if evitar_rango(df_m5):
        score += 2

    if pullback_valido(df_m1, tendencia):
        score += 2

    if vela_fuerza(df_m1, tendencia):
        score += 2

    if rechazo_mecha(df_m1, tendencia):
        score += 1

    if evitar_fake_breakout(df_m1):
        score += 1

    return score


# ========= FUNCIÓN PRINCIPAL =========

def pro_signal(df_m5, df_m1):

    try:
        if len(df_m5) < 20 or len(df_m1) < 20:
            return None

        tendencia = tendencia_m5(df_m5)

        if not tendencia:
            return None

        score = calcular_score(tendencia, df_m5, df_m1)

        print(f"📊 Score estrategia: {score}")

        # SOLO ENTRADAS DE ALTA CALIDAD
        if score >= 7:
            return tendencia

        return None

    except Exception as e:
        print(f"❌ ERROR STRATEGY: {e}")
        return None
