def vela_fuerte_sin_mecha(df):
    try:
        vela = df.iloc[-2]  # vela cerrada

        open_ = float(vela["open"])
        close = float(vela["close"])
        high = float(vela["max"])
        low = float(vela["min"])

        cuerpo = abs(close - open_)
        rango = high - low

        if rango == 0:
            return None

        # calcular mechas
        mecha_sup = high - max(open_, close)
        mecha_inf = min(open_, close) - low

        # condición: casi sin mechas
        if mecha_sup < cuerpo * 0.1 and mecha_inf < cuerpo * 0.1:
            
            # dirección
            if close > open_:
                return "call"
            elif close < open_:
                return "put"

        return None

    except:
        return None
