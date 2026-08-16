# ============================================================
# strategy.py
# ============================================================
#
# ESTRATEGIA DE 12 VELAS DE 5 SEGUNDOS
#
# 1 M1 = 12 velas de 5s
#
# REGLAS:
#   1. Se analizan las 12 velas completas.
#   2. La primera vela NO determina la dirección.
#   3. Se calcula fuerza alcista y bajista.
#   4. Se determina un dominante matemático.
#   5. Se exige margen mínimo del dominante.
#   6. Se exige desplazamiento suficiente.
#   7. Se exige que el cierre confirme la dirección.
#   8. Se comprueba la fuerza de las últimas 3 velas.
#   9. Si cualquier filtro falla -> NO OPERAR.
#
# RESULTADOS:
#   "call"
#   "put"
#   None
#
# ============================================================


# ============================================================
# CONFIGURACIÓN PRINCIPAL
# ============================================================

M1_CANDLES = 12

FINAL_CANDLES = 3


# ============================================================
# FILTRO DE DOMINANCIA
# ============================================================
#
# Diferencia mínima entre la fuerza dominante y la contraria.
#
# Ejemplo:
#
# CALL = 0.60
# PUT  = 0.40
#
# margen = 0.20
#
# Si margen < 0.10 -> NO OPERAR
#
# ============================================================

MIN_DOMINANCE_MARGIN = 0.10


# ============================================================
# FILTRO DE DESPLAZAMIENTO
# ============================================================
#
# Se calcula:
#
# abs(cierre_final - apertura_inicial)
# ------------------------------------
#          rango_total
#
# ============================================================

MIN_DISPLACEMENT_RATIO = 0.20


# ============================================================
# FILTRO DE POSICIÓN DEL CIERRE
# ============================================================
#
# Posición del cierre dentro del rango total.
#
# 1.00 = máximo
# 0.50 = mitad
# 0.00 = mínimo
#
# ============================================================

CALL_MIN_CLOSE_POSITION = 0.65

PUT_MAX_CLOSE_POSITION = 0.35


# ============================================================
# FILTRO DE FUERZA FINAL
# ============================================================
#
# Se analizan las últimas 3 velas.
#
# El dominante debe conservar al menos este porcentaje
# de la fuerza de esas últimas velas.
#
# ============================================================

MIN_FINAL_DOMINANT_RATIO = 0.34


# ============================================================
# FUNCIONES BÁSICAS
# ============================================================

def _get_value(candle, key, default=None):

    if not isinstance(candle, dict):
        return default

    value = candle.get(key, default)

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_ohlc(candle):

    if not isinstance(candle, dict):
        return None

    open_price = _get_value(candle, "open")

    close_price = _get_value(candle, "close")

    high_price = _get_value(candle, "max")

    if high_price is None:
        high_price = _get_value(candle, "high")

    low_price = _get_value(candle, "min")

    if low_price is None:
        low_price = _get_value(candle, "low")

    if (
        open_price is None
        or close_price is None
        or high_price is None
        or low_price is None
    ):
        return None

    return (
        open_price,
        close_price,
        high_price,
        low_price
    )


def _valid_candle(candle):

    ohlc = _get_ohlc(candle)

    if ohlc is None:
        return False

    open_price, close_price, high_price, low_price = ohlc

    if high_price < low_price:
        return False

    if high_price < open_price:
        return False

    if high_price < close_price:
        return False

    if low_price > open_price:
        return False

    if low_price > close_price:
        return False

    return True


# ============================================================
# COLOR DE VELA
# ============================================================

def get_candle_color(candle):

    if not _valid_candle(candle):
        return None

    open_price, close_price, _, _ = _get_ohlc(candle)

    if close_price > open_price:
        return "verde"

    if close_price < open_price:
        return "rojo"

    return "doji"


# ============================================================
# FUERZA DE UNA VELA
# ============================================================
#
# Fuerza =
#
# cuerpo × presión del cierre
#
# La presión mide qué tan cerca termina el cierre
# del extremo favorable de la vela.
#
# ============================================================

def _candle_force(candle):

    if not _valid_candle(candle):
        return None

    open_price, close_price, high_price, low_price = _get_ohlc(candle)

    candle_range = high_price - low_price

    body = abs(close_price - open_price)

    if candle_range <= 0:

        return {
            "green": 0.0,
            "red": 0.0
        }

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if close_price > open_price:

        pressure = (
            (close_price - low_price)
            / candle_range
        )

        force = body * pressure

        return {
            "green": force,
            "red": 0.0
        }

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if close_price < open_price:

        pressure = (
            (high_price - close_price)
            / candle_range
        )

        force = body * pressure

        return {
            "green": 0.0,
            "red": force
        }

    # --------------------------------------------------------
    # DOJI
    # --------------------------------------------------------

    return {
        "green": 0.0,
        "red": 0.0
    }


# ============================================================
# ANALIZAR LAS 12 VELAS
# ============================================================

def analyze_dominance(candles_5s):

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if candles_5s is None:
        return None

    if len(candles_5s) < M1_CANDLES:
        return None

    # ========================================================
    # IMPORTANTE:
    #
    # SOLO LAS 12 VELAS DE ESTA M1
    # ========================================================

    candles = list(
        candles_5s[:M1_CANDLES]
    )

    # Todas deben estar cerradas y ser válidas.

    for candle in candles:

        if not _valid_candle(candle):
            return None

    # ========================================================
    # FUERZA TOTAL
    # ========================================================

    green_force = 0.0

    red_force = 0.0

    candle_forces = []

    for candle in candles:

        force = _candle_force(candle)

        if force is None:
            return None

        green_force += force["green"]

        red_force += force["red"]

        candle_forces.append(force)

    total_force = (
        green_force +
        red_force
    )

    # ========================================================
    # SIN FUERZA
    # ========================================================

    if total_force <= 0:

        return {
            "dominant": None,

            "green_force": 0.0,
            "red_force": 0.0,

            "green_ratio": 0.0,
            "red_ratio": 0.0,

            "dominance_margin": 0.0,

            "displacement_ratio": 0.0,

            "close_position": 0.5,

            "final_green_force": 0.0,
            "final_red_force": 0.0,

            "final_dominant_ratio": 0.0,

            "dominance_ok": False,
            "displacement_ok": False,
            "close_ok": False,
            "final_strength_ok": False,

            "market_ok": False,

            "reason": "SIN_FUERZA"
        }

    # ========================================================
    # RATIOS
    # ========================================================

    green_ratio = (
        green_force /
        total_force
    )

    red_ratio = (
        red_force /
        total_force
    )

    # ========================================================
    # MARGEN
    # ========================================================

    dominance_margin = abs(
        green_ratio -
        red_ratio
    )

    # ========================================================
    # DOMINANTE
    # ========================================================

    if green_force > red_force:

        dominant = "call"

    elif red_force > green_force:

        dominant = "put"

    else:

        dominant = None

    # ========================================================
    # DATOS DE PRECIO
    # ========================================================

    opens = []
    closes = []
    highs = []
    lows = []

    for candle in candles:

        o, c, h, l = _get_ohlc(candle)

        opens.append(o)
        closes.append(c)
        highs.append(h)
        lows.append(l)

    first_open = opens[0]

    final_close = closes[-1]

    total_high = max(highs)

    total_low = min(lows)

    total_range = (
        total_high -
        total_low
    )

    # ========================================================
    # RANGO CERO
    # ========================================================

    if total_range <= 0:

        return {
            "dominant": dominant,

            "green_force": green_force,
            "red_force": red_force,

            "green_ratio": green_ratio,
            "red_ratio": red_ratio,

            "dominance_margin": dominance_margin,

            "displacement_ratio": 0.0,

            "close_position": 0.5,

            "final_green_force": 0.0,
            "final_red_force": 0.0,

            "final_dominant_ratio": 0.0,

            "dominance_ok": False,
            "displacement_ok": False,
            "close_ok": False,
            "final_strength_ok": False,

            "market_ok": False,

            "reason": "RANGO_CERO"
        }

    # ========================================================
    # FILTRO DE DESPLAZAMIENTO
    # ========================================================

    net_displacement = abs(
        final_close -
        first_open
    )

    displacement_ratio = (
        net_displacement /
        total_range
    )

    displacement_ok = (
        displacement_ratio >=
        MIN_DISPLACEMENT_RATIO
    )

    # ========================================================
    # POSICIÓN DEL CIERRE
    # ========================================================

    close_position = (
        final_close -
        total_low
    ) / total_range

    if dominant == "call":

        close_ok = (
            close_position >=
            CALL_MIN_CLOSE_POSITION
        )

    elif dominant == "put":

        close_ok = (
            close_position <=
            PUT_MAX_CLOSE_POSITION
        )

    else:

        close_ok = False

    # ========================================================
    # FUERZA DE LAS ÚLTIMAS 3 VELAS
    # ========================================================

    final_forces = candle_forces[
        -FINAL_CANDLES:
    ]

    final_green_force = sum(
        item["green"]
        for item in final_forces
    )

    final_red_force = sum(
        item["red"]
        for item in final_forces
    )

    final_total_force = (
        final_green_force +
        final_red_force
    )

    if final_total_force > 0:

        if dominant == "call":

            final_dominant_ratio = (
                final_green_force /
                final_total_force
            )

        elif dominant == "put":

            final_dominant_ratio = (
                final_red_force /
                final_total_force
            )

        else:

            final_dominant_ratio = 0.0

    else:

        final_dominant_ratio = 0.0

    final_strength_ok = (
        final_dominant_ratio >=
        MIN_FINAL_DOMINANT_RATIO
    )

    # ========================================================
    # MARGEN DEL DOMINANTE
    # ========================================================

    dominance_ok = (
        dominance_margin >=
        MIN_DOMINANCE_MARGIN
    )

    # ========================================================
    # DECISIÓN FINAL
    # ========================================================

    market_ok = (
        dominant is not None
        and dominance_ok
        and displacement_ok
        and close_ok
        and final_strength_ok
    )

    # ========================================================
    # MOTIVO
    # ========================================================

    if dominant is None:

        reason = "SIN_DOMINANTE"

    elif not dominance_ok:

        reason = "DOMINANTE_DEBIL"

    elif not displacement_ok:

        reason = "POCO_DESPLAZAMIENTO"

    elif not close_ok:

        reason = "CIERRE_NO_CONFIRMA"

    elif not final_strength_ok:

        reason = "PERDIDA_DE_FUERZA_FINAL"

    else:

        reason = "OK"

    # ========================================================
    # RESULTADO COMPLETO
    # ========================================================

    return {

        # Dirección
        "dominant": dominant,

        # Fuerzas
        "green_force": green_force,
        "red_force": red_force,

        # Ratios
        "green_ratio": green_ratio,
        "red_ratio": red_ratio,

        # Margen
        "dominance_margin": dominance_margin,

        # Precios
        "first_open": first_open,
        "final_close": final_close,

        "total_high": total_high,
        "total_low": total_low,
        "total_range": total_range,

        # Movimiento
        "net_displacement": net_displacement,
        "displacement_ratio": displacement_ratio,

        # Posición cierre
        "close_position": close_position,

        # Fuerza final
        "final_green_force": final_green_force,
        "final_red_force": final_red_force,

        "final_dominant_ratio":
            final_dominant_ratio,

        # Filtros
        "dominance_ok": dominance_ok,
        "displacement_ok": displacement_ok,
        "close_ok": close_ok,
        "final_strength_ok":
            final_strength_ok,

        # Resultado
        "market_ok": market_ok,

        "reason": reason
    }


# ============================================================
# DIRECCIÓN DE LA M1
# ============================================================

def get_m1_direction(candles_5s):

    analysis = analyze_dominance(
        candles_5s
    )

    if analysis is None:
        return None

    if not analysis["market_ok"]:
        return None

    return analysis["dominant"]


# ============================================================
# CHECK_PATTERN
# ============================================================
#
# Mantengo esta función para que tu bot.py actual
# pueda continuar utilizando:
#
# from strategy import check_pattern
#
# ============================================================

def check_pattern(candles_5s):

    return get_m1_direction(
        candles_5s
    )


# ============================================================
# ANÁLISIS COMPLETO PARA EL BOT
# ============================================================

def get_strategy_analysis(candles_5s):

    return analyze_dominance(
        candles_5s
    )


# ============================================================
# FORMATO PARA TELEGRAM / CONSOLA
# ============================================================

def format_analysis(candles_5s):

    analysis = analyze_dominance(
        candles_5s
    )

    if analysis is None:

        return (
            "\n"
            "================================\n"
            "ERROR ANALIZANDO M1\n"
            "Se necesitan 12 velas válidas "
            "de 5s.\n"
            "================================"
        )

    dominant = analysis["dominant"]

    if dominant == "call":

        dominant_text = "CALL / ALCISTA"

    elif dominant == "put":

        dominant_text = "PUT / BAJISTA"

    else:

        dominant_text = "SIN DOMINANTE"

    result = (
        "OPERAR"
        if analysis["market_ok"]
        else
        "NO OPERAR"
    )

    return (
        "\n"
        "========================================\n"
        "       ANALISIS MATEMATICO M1\n"
        "========================================\n"
        f"Velas analizadas       : "
        f"{M1_CANDLES}\n"
        f"Dominante              : "
        f"{dominant_text}\n"
        "\n"
        f"Fuerza verde           : "
        f"{analysis['green_force']:.8f}\n"
        f"Fuerza roja            : "
        f"{analysis['red_force']:.8f}\n"
        "\n"
        f"Ratio verde            : "
        f"{analysis['green_ratio']:.4f}\n"
        f"Ratio rojo             : "
        f"{analysis['red_ratio']:.4f}\n"
        f"Margen dominante       : "
        f"{analysis['dominance_margin']:.4f}\n"
        "\n"
        f"Desplazamiento         : "
        f"{analysis['displacement_ratio']:.4f}\n"
        f"Posicion cierre        : "
        f"{analysis['close_position']:.4f}\n"
        f"Fuerza final dominante : "
        f"{analysis['final_dominant_ratio']:.4f}\n"
        "\n"
        "----------------------------------------\n"
        f"Dominante OK           : "
        f"{analysis['dominance_ok']}\n"
        f"Desplazamiento OK      : "
        f"{analysis['displacement_ok']}\n"
        f"Cierre OK              : "
        f"{analysis['close_ok']}\n"
        f"Fuerza final OK        : "
        f"{analysis['final_strength_ok']}\n"
        "----------------------------------------\n"
        f"RESULTADO              : "
        f"{result}\n"
        f"MOTIVO                 : "
        f"{analysis['reason']}\n"
        "========================================\n"
    )


# ============================================================
# PRUEBA DIRECTA
# ============================================================

if __name__ == "__main__":

    print(
        "strategy.py cargada correctamente."
    )

    print(
        f"M1 = {M1_CANDLES} velas de 5 segundos"
    )

    print(
        "Primera vela: SIN PRIORIDAD"
    )

    print(
        "Decision: dominante + filtros matematicos"
    )
