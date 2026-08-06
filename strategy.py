def pro_signal(df):
    try:
        if df is None or len(df) < 3:
            return None

        # ===== VELA CERRADA =====
        vela = df[-2]

        open_ = float(vela["open"])
        close = float(vela["close"])
        high = float(vela["max"])
        low = float(vela["min"])

        # ===== VALIDAR RANGO =====
        rango = high - low
        if rango == 0:
            return None

        # ===== CALCULAR MECHAS =====
        mecha_sup = high - max(open_, close)
        mecha_inf = min(open_, close) - low

        # ===== CONDICIÓN SIN MECHAS =====
        # tolerancia mínima por precisión del broker
        tolerancia = 0.00001

        if mecha_sup <= tolerancia and mecha_inf <= tolerancia:

            # ===== DIRECCIÓN =====
            if close > open_:
                return "call"

            elif close < open_:
                return "put"

        return None

    except Exception as e:
        print("❌ ERROR STRATEGY:", e)
        return None
