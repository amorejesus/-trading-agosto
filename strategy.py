import pandas as pd


def analyze_candle(df):
    """
    Analiza la última vela cerrada y detecta:
    - Fuerza (cuerpo dominante)
    - Continuidad (misma dirección que la anterior)

    Retorna:
        "call" -> compra
        "put"  -> venta
        None   -> no operar
    """

    # Validación básica
    if df is None or len(df) < 3:
        return None

    # Vela cerrada actual
    last = df.iloc[-2]

    # Vela anterior
    prev = df.iloc[-3]

    # Datos de la vela
    open_price = last["open"]
    close_price = last["close"]
    high = last["max"]
    low = last["min"]

    # Cálculo del cuerpo
    body = abs(close_price - open_price)

    # Rango total de la vela
    range_candle = high - low

    if range_candle == 0:
        return None

    # Proporción del cuerpo (fuerza)
    body_ratio = body / range_candle

    # Mechas
    upper_wick = high - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low

    # Dirección
    bullish = close_price > open_price
    bearish = close_price < open_price

    # ==============================
    # CONDICIONES DE FUERZA
    # ==============================

    strong_body = body_ratio > 0.6  # cuerpo grande
    small_wicks = (
        upper_wick < body * 0.5 and
        lower_wick < body * 0.5
    )

    # ==============================
    # CONTINUIDAD
    # ==============================

    continuation_up = bullish and close_price > prev["close"]
    continuation_down = bearish and close_price < prev["close"]

    # ==============================
    # DECISIÓN FINAL
    # ==============================

    if strong_body and small_wicks:

        if continuation_up:
            return "call"

        elif continuation_down:
            return "put"

    return None
