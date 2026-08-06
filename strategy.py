import numpy as np

def pro_signal(df_m5, df_m1):
    try:
        if len(df_m5) < 20 or len(df_m1) < 20:
            return None

        # ===== TENDENCIA M5 =====
        highs = [c['max'] for c in df_m5[-10:]]
        lows = [c['min'] for c in df_m5[-10:]]

        tendencia = None

        if all(highs[i] > highs[i-1] for i in range(1, len(highs))) and \
           all(lows[i] > lows[i-1] for i in range(1, len(lows))):
            tendencia = "call"

        elif all(highs[i] < highs[i-1] for i in range(1, len(highs))) and \
             all(lows[i] < lows[i-1] for i in range(1, len(lows))):
            tendencia = "put"

        if not tendencia:
            return None

        # ===== CONFIRMACIÓN M1 =====
        vela = df_m1[-1]

        cuerpo = abs(vela['close'] - vela['open'])
        rango = vela['max'] - vela['min']

        if rango == 0:
            return None

        fuerza = cuerpo / rango

        if tendencia == "call" and vela['close'] > vela['open'] and fuerza > 0.6:
            return "call"

        if tendencia == "put" and vela['close'] < vela['open'] and fuerza > 0.6:
            return "put"

        return None

    except Exception as e:
        print("❌ ERROR STRATEGY:", e)
        return None
