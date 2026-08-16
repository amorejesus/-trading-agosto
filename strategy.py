# ============================================================
# STRATEGY.PY
# IQ OPTION
#
# REGLA:
# - Una M1 = 12 velas de 5 segundos
# - Espera las 12 velas cerradas
# - Analiza las 12 velas COMPLETAS
# - La señal corresponde a la SIGUIENTE M1
# - No utiliza datos de la siguiente M1
# ============================================================

from typing import Optional, List, Dict, Any


# ============================================================
# CONFIGURACIÓN
# ============================================================

CANDLES_PER_M1 = 12


# ============================================================
# COLOR DE VELA
# ============================================================

def get_candle_color(
    candle: Dict[str, Any]
) -> str:
    """
    Determina el color de una vela usando exclusivamente
    OPEN y CLOSE.

        close > open  -> verde
        close < open  -> rojo
        close == open -> doji
    """

    try:

        open_price = float(
            candle["open"]
        )

        close_price = float(
            candle["close"]
        )

    except Exception:

        return "doji"

    if close_price > open_price:
        return "verde"

    if close_price < open_price:
        return "rojo"

    return "doji"


# ============================================================
# CUERPO DE VELA
# ============================================================

def candle_body(
    candle: Dict[str, Any]
) -> float:
    """
    Cuerpo real de la vela:

        close - open
    """

    try:

        return (
            float(candle["close"])
            - float(candle["open"])
        )

    except Exception:

        return 0.0


# ============================================================
# VALIDAR VELAS
# ============================================================

def validate_candles(
    candles_5s: List[Dict[str, Any]]
) -> bool:
    """
    Comprueba que existan exactamente 12 velas
    y que todas tengan OPEN y CLOSE válidos.
    """

    if candles_5s is None:
        return False

    if not isinstance(
        candles_5s,
        list
    ):
        return False

    if len(candles_5s) != CANDLES_PER_M1:

        print(
            "[STRATEGY] ERROR: "
            f"se esperaban {CANDLES_PER_M1} velas "
            f"y llegaron {len(candles_5s)}."
        )

        return False

    for index, candle in enumerate(
        candles_5s,
        start=1
    ):

        if not isinstance(
            candle,
            dict
        ):

            print(
                f"[STRATEGY] Vela {index} inválida."
            )

            return False

        if "open" not in candle:

            print(
                f"[STRATEGY] Vela {index} "
                "sin OPEN."
            )

            return False

        if "close" not in candle:

            print(
                f"[STRATEGY] Vela {index} "
                "sin CLOSE."
            )

            return False

        try:

            float(
                candle["open"]
            )

            float(
                candle["close"]
            )

        except Exception:

            print(
                f"[STRATEGY] Vela {index} "
                "tiene precios inválidos."
            )

            return False

    return True


# ============================================================
# OBTENER LOS 12 COLORES
# ============================================================

def get_colors(
    candles_5s: List[Dict[str, Any]]
) -> List[str]:
    """
    Devuelve los colores de las 12 velas
    en orden cronológico.
    """

    return [
        get_candle_color(candle)
        for candle in candles_5s
    ]


# ============================================================
# MOSTRAR PATRÓN
# ============================================================

def print_pattern(
    candles_5s: List[Dict[str, Any]]
) -> None:
    """
    Muestra las 12 velas utilizadas por la estrategia.
    """

    colors = get_colors(
        candles_5s
    )

    print(
        "\n======================================"
    )

    print(
        "PATRÓN COMPLETO - 12 VELAS DE 5S"
    )

    print(
        "======================================"
    )

    for index, color in enumerate(
        colors,
        start=1
    ):

        if color == "verde":

            symbol = "🟢"

        elif color == "rojo":

            symbol = "🔴"

        else:

            symbol = "⚪"

        print(
            f"{index:02d}: "
            f"{symbol} {color.upper()}"
        )

    print(
        "======================================"
    )


# ============================================================
# ANALIZAR FUERZA DE LAS 12 VELAS
# ============================================================

def analyze_12_candles(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Analiza las 12 velas completas.

    La señal obtenida corresponde a la SIGUIENTE M1.

    Se utilizan:

    1. Dirección de los cuerpos de las 12 velas.
    2. Fuerza total alcista.
    3. Fuerza total bajista.
    4. Movimiento neto de toda la M1.
    5. Confirmación de las últimas 3 velas.

    No utiliza ninguna vela futura.
    """

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not validate_candles(
        candles_5s
    ):

        return None

    # --------------------------------------------------------
    # CONTADORES
    # --------------------------------------------------------

    green_count = 0
    red_count = 0
    doji_count = 0

    # --------------------------------------------------------
    # FUERZA
    # --------------------------------------------------------

    buy_score = 0.0
    sell_score = 0.0

    # --------------------------------------------------------
    # ANALIZAR LAS 12
    # --------------------------------------------------------

    for candle in candles_5s:

        color = get_candle_color(
            candle
        )

        body = candle_body(
            candle
        )

        if color == "verde":

            green_count += 1
            buy_score += body

        elif color == "rojo":

            red_count += 1
            sell_score += abs(body)

        else:

            doji_count += 1

    # --------------------------------------------------------
    # MOSTRAR INFORMACIÓN
    # --------------------------------------------------------

    print(
        "\n[STRATEGY] RESUMEN DE LAS 12 VELAS"
    )

    print(
        f"[STRATEGY] Verdes : {green_count}"
    )

    print(
        f"[STRATEGY] Rojas  : {red_count}"
    )

    print(
        f"[STRATEGY] Dojis  : {doji_count}"
    )

    print(
        f"[STRATEGY] Fuerza CALL: {buy_score}"
    )

    print(
        f"[STRATEGY] Fuerza PUT : {sell_score}"
    )

    # --------------------------------------------------------
    # SI TODAS SON DOJI
    # --------------------------------------------------------

    if (
        buy_score == 0
        and sell_score == 0
    ):

        print(
            "[STRATEGY] SIN SEÑAL: "
            "no existe movimiento."
        )

        return None

    # ========================================================
    # MOVIMIENTO TOTAL DE LA M1
    # ========================================================

    try:

        m1_open = float(
            candles_5s[0]["open"]
        )

        m1_close = float(
            candles_5s[-1]["close"]
        )

    except Exception:

        return None

    m1_move = (
        m1_close
        - m1_open
    )

    # ========================================================
    # FUERZA TOTAL
    # ========================================================

    total_score = (
        buy_score
        + sell_score
    )

    if total_score <= 0:

        return None

    # ========================================================
    # DOMINANCIA
    # ========================================================

    dominance = (
        abs(
            buy_score
            - sell_score
        )
        / total_score
    )

    print(
        f"[STRATEGY] Dominancia: "
        f"{dominance:.4f}"
    )

    # --------------------------------------------------------
    # No operar si la fuerza está demasiado equilibrada.
    # --------------------------------------------------------

    if dominance < 0.25:

        print(
            "[STRATEGY] SIN SEÑAL: "
            "fuerzas demasiado equilibradas."
        )

        return None

    # ========================================================
    # ÚLTIMAS 3 VELAS
    # ========================================================

    final_3_move = 0.0

    for candle in candles_5s[-3:]:

        final_3_move += candle_body(
            candle
        )

    print(
        f"[STRATEGY] Movimiento últimas 3: "
        f"{final_3_move}"
    )

    # ========================================================
    # DECISIÓN
    # ========================================================

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    if buy_score > sell_score:

        # La M1 terminó positiva.
        if m1_move <= 0:

            print(
                "[STRATEGY] SIN CALL: "
                "la fuerza alcista no coincide "
                "con el movimiento final."
            )

            return None

        # Las últimas 3 no deben contradecir
        # completamente la dirección.
        if final_3_move < 0:

            print(
                "[STRATEGY] SIN CALL: "
                "últimas 3 velas bajistas."
            )

            return None

        print(
            "\n🟢 [STRATEGY] SEÑAL PARA "
            "LA SIGUIENTE M1: CALL"
        )

        return "call"

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    if sell_score > buy_score:

        # La M1 terminó negativa.
        if m1_move >= 0:

            print(
                "[STRATEGY] SIN PUT: "
                "la fuerza bajista no coincide "
                "con el movimiento final."
            )

            return None

        # Las últimas 3 no deben contradecir
        # completamente la dirección.
        if final_3_move > 0:

            print(
                "[STRATEGY] SIN PUT: "
                "últimas 3 velas alcistas."
            )

            return None

        print(
            "\n🔴 [STRATEGY] SEÑAL PARA "
            "LA SIGUIENTE M1: PUT"
        )

        return "put"

    # ========================================================
    # SIN SEÑAL
    # ========================================================

    print(
        "[STRATEGY] SIN SEÑAL."
    )

    return None


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def check_pattern(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    FUNCIÓN UTILIZADA POR BOT.PY.

    IMPORTANTE:

    Las 12 velas recibidas deben pertenecer a una M1
    COMPLETAMENTE CERRADA.

    La función analiza esas 12 velas y devuelve
    la dirección para la SIGUIENTE M1.

        "call" -> operar CALL en siguiente M1
        "put"  -> operar PUT en siguiente M1
        None   -> no operar
    """

    print(
        "\n======================================"
    )

    print(
        "[STRATEGY] ANALIZANDO M1 CERRADA"
    )

    print(
        "[STRATEGY] 12 VELAS DE 5S"
    )

    print(
        "[STRATEGY] SEÑAL = SIGUIENTE M1"
    )

    print(
        "======================================"
    )

    if not validate_candles(
        candles_5s
    ):

        print(
            "[STRATEGY] Datos incompletos."
        )

        return None

    # --------------------------------------------------------
    # Mostrar las 12
    # --------------------------------------------------------

    print_pattern(
        candles_5s
    )

    # --------------------------------------------------------
    # Analizar
    # --------------------------------------------------------

    signal = analyze_12_candles(
        candles_5s
    )

    # --------------------------------------------------------
    # Resultado
    # --------------------------------------------------------

    if signal == "call":

        print(
            "\n🟢 RESULTADO:"
        )

        print(
            "CALL → SIGUIENTE M1"
        )

    elif signal == "put":

        print(
            "\n🔴 RESULTADO:"
        )

        print(
            "PUT → SIGUIENTE M1"
        )

    else:

        print(
            "\n⚪ RESULTADO:"
        )

        print(
            "NO OPERAR"
        )

    return signal


# ============================================================
# ALIAS DE COMPATIBILIDAD
# ============================================================

def get_strategy_analysis(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:

    return check_pattern(
        candles_5s
    )


# ============================================================
# DIRECCIÓN DE LA M1 YA CERRADA
# ============================================================

def get_m1_direction(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Función auxiliar.

    Devuelve la dirección de la M1 que YA terminó.

    NO debe utilizarse para decidir la siguiente operación.
    """

    if not validate_candles(
        candles_5s
    ):

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
