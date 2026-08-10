# =========================
# STRATEGY SNIPER 5s
# =========================

def get_candle_color(candle):
    """
    Retorna 'verde' o 'rojo' según la vela
    """
    return "verde" if candle["close"] > candle["open"] else "rojo"


# =========================
# PATRÓN PRINCIPAL
# =========================
def check_pattern(candles_5s):
    """
    Evalúa SOLO los primeros 30 segundos (6 velas de 5s)

    PATRONES VÁLIDOS:

    1) rojo → verde → verde → verde → verde → rojo  → CALL
    2) verde → rojo → rojo → rojo → rojo → verde  → PUT
    """

    if len(candles_5s) < 6:
        return None

    # Obtener colores
    colors = [get_candle_color(c) for c in candles_5s[:6]]

    print(f"📊 Patrón detectado: {colors}")

    # =========================
    # PATRÓN CALL
    # rojo → verde → verde → verde → verde → rojo
    # =========================
    if colors == ["rojo", "verde", "verde", "verde", "verde", "rojo"]:
        return "call"

    # =========================
    # PATRÓN PUT
    # verde → rojo → rojo → rojo → rojo → verde
    # =========================
    if colors == ["verde", "rojo", "rojo", "rojo", "rojo", "verde"]:
        return "put"

    return None
