import pandas as pd


def analyze_candle(df):
    """
    Estrategia de continuidad + fuerza
    """

    if df is None or len(df) < 3:
        return None

    last = df.iloc[-2]
    prev = df.iloc[-3]

    open_price = last["open"]
    close_price = last["close"]
    high = last["max"]
    low = last["min"]

    body = abs(close_price - open_price)
    range_candle = high - low

    if range_candle == 0:
        return None

    body_ratio = body / range_candle

    upper_wick = high - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low

    bullish = close_price > open_price
    bearish = close_price < open_price

    strong_body = body_ratio > 0.6
    small_wicks = upper_wick < body * 0.5 and lower_wick < body * 0.5

    continuation_up = bullish and close_price > prev["close"]
    continuation_down = bearish and close_price < prev["close"]

    if strong_body and small_wicks:
        if continuation_up:
            return "call"
        elif continuation_down:
            return "put"

    return None
