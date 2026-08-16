from typing import Optional, List, Dict, Any


CANDLES_PER_M1 = 12


def get_candle_color(candle: Dict[str, Any]) -> str:
    open_price = float(candle["open"])
    close_price = float(candle["close"])

    if close_price > open_price:
        return "verde"

    if close_price < open_price:
        return "rojo"

    return "doji"


def candle_body(candle: Dict[str, Any]) -> float:
    return (
        float(candle["close"])
        - float(candle["open"])
    )


def validate_candles(
    candles_5s: List[Dict[str, Any]]
) -> bool:

    if candles_5s is None:
        return False

    if not isinstance(candles_5s, list):
        return False

    if len(candles_5s) != CANDLES_PER_M1:
        return False

    for candle in candles_5s:

        if not isinstance(candle, dict):
            return False

        if "open" not in candle:
            return False

        if "close" not in candle:
            return False

        try:
            float(candle["open"])
            float(candle["close"])
        except Exception:
            return False

    return True


def check_pattern(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:

    if not validate_candles(candles_5s):
        return None

    buy_score = 0.0
    sell_score = 0.0

    for candle in candles_5s:

        body = candle_body(candle)

        if body > 0:
            buy_score += body

        elif body < 0:
            sell_score += abs(body)

    total_score = buy_score + sell_score

    if total_score <= 0:
        return None

    dominance = (
        abs(buy_score - sell_score)
        / total_score
    )

    if dominance < 0.25:
        return None

    m1_open = float(
        candles_5s[0]["open"]
    )

    m1_close = float(
        candles_5s[-1]["close"]
    )

    m1_move = abs(
        m1_close - m1_open
    )

    total_body = 0.0

    for candle in candles_5s:

        total_body += abs(
            candle_body(candle)
        )

    if total_body <= 0:
        return None

    efficiency = (
        m1_move / total_body
    )

    if efficiency < 0.45:
        return None

    final_net = 0.0

    for candle in candles_5s[-3:]:

        final_net += candle_body(
            candle
        )

    if final_net > 0:
        return "call"

    if final_net < 0:
        return "put"

    return None


def get_strategy_analysis(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:

    return check_pattern(
        candles_5s
    )


def get_m1_direction(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:

    if not validate_candles(candles_5s):
        return None

    try:

        m1_open = float(
            candles_5s[0]["open"]
        )

        m1_close = float(
            candles_5s[-1]["close"]
        )

    except Exception:

        return None

    if m1_close > m1_open:
        return "call"

    if m1_close < m1_open:
        return "put"

    return None
