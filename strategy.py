# strategy.py

def get_candle_color(candle):
    return "verde" if candle["close"] > candle["open"] else "rojo"


def check_pattern(candles_5s):
    """
    SOLO valida patrones EXACTOS
    """

    if candles_5s is None or len(candles_5s) < 6:
        return None

    # ordenar por tiempo (MUY IMPORTANTE)
    candles_5s = sorted(candles_5s, key=lambda x: x["from"])

    first_6 = candles_5s[:6]

    colors = [get_candle_color(c) for c in first_6]

    print(f"📊 Patrón: {colors}")

    patron_call = ["rojo", "verde", "verde", "verde", "verde", "rojo"]
    patron_put  = ["verde", "rojo", "rojo", "rojo", "rojo", "verde"]

    if colors == patron_call:
        print("✅ PATRÓN CALL")
        return "call"

    if colors == patron_put:
        print("✅ PATRÓN PUT")
        return "put"

    print("❌ Patrón inválido")
    return None


def get_m1_direction(candle):
    if candle["close"] > candle["open"]:
        return "call"
    else:
        return "put"
