import pandas as pd

def pro_signal(df):
    try:
        # =========================
        # VALIDACIÓN
        # =========================
        if df is None or len(df) < 10:
            return None

        # =========================
        # ASEGURAR DATAFRAME
        # =========================
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        # =========================
        # TOMAR VELAS
        # =========================
        last = df.iloc[-2]      # vela cerrada (IMPORTANTE)
        prev = df.iloc[-3]
        prev2 = df.iloc[-4]

        open_ = float(last["open"])
        close = float(last["close"])
        high = float(last["max"])
        low = float(last["min"])

        # =========================
        # CÁLCULO DE FUERZA
        # =========================
        rango = high - low
        cuerpo = abs(close - open_)

        if rango == 0:
            return None

        fuerza = cuerpo / rango

        # =========================
        # MECHAS (RECHAZO)
        # =========================
        mecha_sup = high - max(open_, close)
        mecha_inf = min(open_, close) - low

        # =========================
        # DIRECCIÓN PREVIA
        # =========================
        prev_close = float(prev["close"])
        prev2_close = float(prev2["close"])

        # =========================
        # FILTROS BASE
        # =========================
        # Evitar velas débiles
        if fuerza < 0.5:
            return None

        # Evitar indecisión
        if mecha_sup > cuerpo and mecha_inf > cuerpo:
            return None

        # =========================
        # CONTINUIDAD BAJISTA (PUT)
        # =========================
        if (
            close < open_                        # vela roja
            and fuerza > 0.5                     # fuerza
            and close < prev_close               # continuación
            and prev_close < prev2_close         # tendencia previa
            and mecha_inf < cuerpo * 0.5         # poco rechazo abajo
        ):
            return "put"

        # =========================
        # CONTINUIDAD ALCISTA (CALL)
        # =========================
        if (
            close > open_                        # vela verde
            and fuerza > 0.5
            and close > prev_close
            and prev_close > prev2_close
            and mecha_sup < cuerpo * 0.5
        ):
            return "call"

        return None

    except Exception as e:
        print("Error en estrategia:", e)
        return None
