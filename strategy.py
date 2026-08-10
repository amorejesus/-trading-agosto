# =========================
# STRATEGY SNIPER 5s + M1
# =========================

def check_pattern(candles_5s):
    """
    SOLO usa:
    ✔ Primeras 6 velas de 5 segundos (primeros 30s)
    ✔ Patrones exactos definidos

    PATRONES:

    1) rojo → verde → verde → verde → verde → rojo  → CALL
    2) verde → rojo → rojo → rojo → rojo → verde  → PUT
    """

    # Validación mínima
    if len(candles_5s) < 6:
        return None

    # Obtener colores EXACTOS
    colors = []
    for c in candles_5s[:6]:
        if c["close"] > c["open"]:
            colors.append("verde")
        else:
            colors.append("rojo")

    print(f"📊 Patrón detectado: {colors}")

    # =========================
    # PATRÓN CALL
    # =========================
    if colors == ["rojo", "verde", "verde", "verde", "verde", "rojo"]:
        print("✅ Patrón CALL válido")
        return "call"

    # =========================
    # PATRÓN PUT
    # =========================
    if colors == ["verde", "rojo", "rojo", "rojo", "rojo", "verde"]:
        print("✅ Patrón PUT válido")
        return "put"

    # =========================
    # NO HAY SEÑAL
    # =========================
    print("❌ Patrón NO válido")
    return None
