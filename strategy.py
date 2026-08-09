# strategy.py

def get_candle_color(candle):
    """
    Retorna el color de la vela
    """
    return "verde" if candle["close"] > candle["open"] else "rojo"


def check_pattern(candles_5s):
    """
    ✔ SOLO usa:
    - Primeras 6 velas de 5 segundos (primeros 30s)
    - Patrón EXACTO

    ❌ No aproxima
    ❌ No interpreta
    ❌ No usa mayoría
    """

    # Validación mínima
    if candles_5s is None or len(candles_5s) < 6:
        return None

    # Tomar SOLO las primeras 6 velas (30 segundos)
    first_6 = candles_5s[:6]

    # Convertir a colores
    colors = [get_candle_color(c) for c in first_6]

    # 🔥 PATRONES EXACTOS (NO SE CAMBIAN)
    patron_call = ["rojo", "verde", "verde", "verde", "verde", "rojo"]
    patron_put  = ["verde", "rojo", "rojo", "rojo", "rojo", "verde"]

    # Comparación EXACTA
    if colors == patron_call:
        return "CALL"

    if colors == patron_put:
        return "PUT"

    # ❌ Cualquier otra cosa = NO OPERAR
    return None


def get_m1_direction(candle_m1):
    """
    ✔ SOLO usa:
    - Dirección de la vela M1
    """

    if candle_m1 is None:
        return None

    if candle_m1["close"] > candle_m1["open"]:
        return "CALL"
    else:
        return "PUT"
