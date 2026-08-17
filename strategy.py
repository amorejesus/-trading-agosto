# strategy.py
# ============================================================
# ESTRATEGIA M1 - DECISIÓN ÚNICAMENTE AL CIERRE DE LA VELA
# ============================================================
#
# REGLA PRINCIPAL:
#   La vela N se analiza durante su formación, pero NO se
#   decide CALL/PUT antes de que N termine.
#
#   Cuando N cierra exactamente en :00:
#       1. Se toman OHLC definitivos de N.
#       2. Se calculan todas las características.
#       3. Se determina la dirección.
#       4. Se genera la señal para N+1.
#
#   N+1 NO participa en el análisis de su propia señal.
#
# NO USA:
#   - Velas de 5 segundos
#   - Primeras 6 velas de 5s
#   - Conteo de 12 velas de 5s
#   - Datos parciales para decidir CALL/PUT
#   - Señales al segundo 20
#   - Señales al segundo 30
#   - Señales antes del cierre de M1
#
# ============================================================


def _num(value, default=0.0):
    """Convierte un valor a float de forma segura."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _get_ohlc(candle):
    """
    Obtiene OHLC de una vela IQ Option.

    Acepta:
        open, close, high, low

    Devuelve:
        open_, high, low, close
    """
    if not isinstance(candle, dict):
        raise ValueError("La vela debe ser un diccionario.")

    open_ = _num(candle.get("open"))
    high = _num(candle.get("max", candle.get("high")))
    low = _num(candle.get("min", candle.get("low")))
    close = _num(candle.get("close"))

    return open_, high, low, close


def get_candle_color(candle):
    """
    Color de la vela M1 ya cerrada.

    verde = cierre > apertura
    rojo  = cierre < apertura
    doji  = cierre == apertura
    """
    open_, _, _, close = _get_ohlc(candle)

    if close > open_:
        return "verde"

    if close < open_:
        return "rojo"

    return "doji"


def calculate_candle_metrics(candle):
    """
    Calcula TODAS las características de una vela M1 cerrada.

    Esta función no genera ninguna entrada.
    Solamente analiza la vela.
    """
    open_, high, low, close = _get_ohlc(candle)

    rango = max(high - low, 0.0)
    cuerpo = abs(close - open_)

    if rango > 0:
        ratio_cuerpo = cuerpo / rango
        posicion_cierre = (close - low) / rango
    else:
        ratio_cuerpo = 0.0
        posicion_cierre = 0.5

    mecha_superior = max(high - max(open_, close), 0.0)
    mecha_inferior = max(min(open_, close) - low, 0.0)

    if rango > 0:
        ratio_mecha_superior = mecha_superior / rango
        ratio_mecha_inferior = mecha_inferior / rango
    else:
        ratio_mecha_superior = 0.0
        ratio_mecha_inferior = 0.0

    if close > open_:
        direccion = "BULLISH"
    elif close < open_:
        direccion = "BEARISH"
    else:
        direccion = "NEUTRAL"

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,

        "rango": rango,
        "cuerpo": cuerpo,
        "ratio_cuerpo": ratio_cuerpo,

        "mecha_superior": mecha_superior,
        "mecha_inferior": mecha_inferior,

        "ratio_mecha_superior": ratio_mecha_superior,
        "ratio_mecha_inferior": ratio_mecha_inferior,

        "posicion_cierre": posicion_cierre,

        "direccion": direccion,
        "color": get_candle_color(candle),
    }


def classify_candle(candle):
    """
    Clasificación estructural de la vela M1.

    Prioridad:
        DOJI
        FUERZA
        DEBILIDAD
        INDECISION

    La clasificación se hace únicamente sobre la vela
    COMPLETAMENTE CERRADA.
    """
    data = calculate_candle_metrics(candle)

    rango = data["rango"]
    ratio_cuerpo = data["ratio_cuerpo"]
    posicion = data["posicion_cierre"]

    if rango <= 0:
        data["estado"] = "DOJI"
        return data

    # --------------------------------------------------------
    # DOJI
    # --------------------------------------------------------
    if ratio_cuerpo <= 0.10:
        data["estado"] = "DOJI"
        return data

    # --------------------------------------------------------
    # FUERZA
    # Cuerpo grande y cierre cerca del extremo.
    # --------------------------------------------------------
    cierre_alto = posicion >= 0.75
    cierre_bajo = posicion <= 0.25

    if ratio_cuerpo >= 0.70 and (cierre_alto or cierre_bajo):
        data["estado"] = "FUERZA"
        return data

    # --------------------------------------------------------
    # DEBILIDAD
    # Cuerpo relativamente pequeño con mechas importantes.
    # --------------------------------------------------------
    mechas = (
        data["ratio_mecha_superior"]
        + data["ratio_mecha_inferior"]
    )

    if ratio_cuerpo <= 0.40 and mechas >= 0.45:
        data["estado"] = "DEBILIDAD"
        return data

    # --------------------------------------------------------
    # INDECISIÓN
    # --------------------------------------------------------
    if ratio_cuerpo <= 0.30:
        data["estado"] = "INDECISION"
        return data

    # --------------------------------------------------------
    # Continuidad/reversión se determinan posteriormente
    # comparando con la vela anterior.
    # --------------------------------------------------------
    data["estado"] = "NEUTRAL"

    return data


def analyze_continuity_reversal(current, previous):
    """
    Determina CONTINUIDAD o REVERSIÓN usando únicamente
    velas M1 cerradas.

    current  = vela N cerrada
    previous = vela M1 anterior ya cerrada

    No utiliza datos de N+1.
    """
    if previous is None:
        return {
            "continuidad": False,
            "reversion": False,
            "estructura": None,
        }

    current_data = calculate_candle_metrics(current)
    previous_data = calculate_candle_metrics(previous)

    current_direction = current_data["direccion"]
    previous_direction = previous_data["direccion"]

    continuidad = (
        current_direction != "NEUTRAL"
        and previous_direction != "NEUTRAL"
        and current_direction == previous_direction
    )

    reversion = (
        current_direction != "NEUTRAL"
        and previous_direction != "NEUTRAL"
        and current_direction != previous_direction
    )

    if continuidad:
        estructura = "CONTINUIDAD"
    elif reversion:
        estructura = "REVERSIÓN"
    else:
        estructura = None

    return {
        "continuidad": continuidad,
        "reversion": reversion,
        "estructura": estructura,
    }


def analyze_m1(candle, previous_candle=None):
    """
    ANÁLISIS COMPLETO DE UNA VELA M1 CERRADA.

    IMPORTANTE:
    Esta función debe recibir la vela N cuando ya terminó.

    Devuelve:
        - fuerza
        - continuidad
        - reversión
        - indecisión
        - debilidad
        - doji
        - dirección
        - cuerpo
        - mechas
        - posición del cierre
        - estructura
    """
    data = classify_candle(candle)

    structure = analyze_continuity_reversal(
        candle,
        previous_candle
    )

    estado = data["estado"]

    # --------------------------------------------------------
    # Flags independientes.
    # --------------------------------------------------------
    fuerza = estado == "FUERZA"
    debilidad = estado == "DEBILIDAD"
    indecision = estado == "INDECISION"
    doji = estado == "DOJI"

    continuidad = structure["continuidad"]
    reversion = structure["reversion"]

    # --------------------------------------------------------
    # Para continuidad/reversión, la estructura tiene prioridad
    # únicamente cuando existe comparación válida.
    # --------------------------------------------------------
    if continuidad:
        estado_final = "CONTINUIDAD"
    elif reversion:
        estado_final = "REVERSIÓN"
    else:
        estado_final = estado

    data.update({
        "fuerza": fuerza,
        "continuidad": continuidad,
        "reversion": reversion,
        "indecision": indecision,
        "debilidad": debilidad,
        "doji": doji,

        "estructura": structure["estructura"],
        "estado_final": estado_final,
    })

    return data


def determine_direction(analysis):
    """
    Determina la dirección BASE de la vela M1 ya cerrada.

    Nunca mira N+1.

    Resultado:
        CALL
        PUT
        None
    """
    if not analysis:
        return None

    direccion = analysis.get("direccion")

    if direccion == "BULLISH":
        return "CALL"

    if direccion == "BEARISH":
        return "PUT"

    return None


def determine_signal(analysis):
    """
    Determina CALL/PUT exclusivamente después del cierre
    de la vela analizada.

    No devuelve señal para un DOJI/NEUTRAL.

    No inventa una dirección.
    """
    if not analysis:
        return None

    # --------------------------------------------------------
    # DOJI / indecisión sin dirección clara:
    # NO ENTRAR.
    # --------------------------------------------------------
    if analysis.get("doji"):
        return None

    if analysis.get("indecision") and (
        analysis.get("direccion") == "NEUTRAL"
    ):
        return None

    return determine_direction(analysis)


def build_n1_signal(current_candle, previous_candle=None):
    """
    FUNCIÓN PRINCIPAL DE LA ESTRATEGIA.

    current_candle:
        Es la vela N COMPLETAMENTE CERRADA.

    previous_candle:
        Es N-1, también cerrada.

    Devuelve la señal que corresponde a N+1.

    IMPORTANTE:
        La señal NO significa ejecutar ahora.
        Significa:

            N cerró
            ↓
            analizar N
            ↓
            decidir CALL/PUT
            ↓
            ejecutar en apertura de N+1
    """
    analysis = analyze_m1(
        current_candle,
        previous_candle
    )

    signal = determine_signal(analysis)

    analysis["signal_n1"] = signal
    analysis["target_candle"] = "N+1"

    return analysis


def check_pattern(candle, previous_candle=None):
    """
    Alias de compatibilidad con bot.py.

    IMPORTANTE:
    No analiza velas de 5 segundos.
    No usa 6 velas.
    No usa 12 velas.

    Analiza exclusivamente la vela M1 cerrada.
    """
    return build_n1_signal(
        candle,
        previous_candle
    )


def get_m1_direction(candle, previous_candle=None):
    """
    Devuelve únicamente la señal para N+1.

    CALL
    PUT
    None
    """
    result = build_n1_signal(
        candle,
        previous_candle
    )

    return result.get("signal_n1")


def format_analysis(analysis):
    """
    Texto para mostrar en logs/Telegram.
    """
    if not analysis:
        return "SIN ANÁLISIS"

    return (
        "\n"
        "========================================\n"
        "        ANÁLISIS M1 CERRADA\n"
        "========================================\n"
        f"Estado       : {analysis.get('estado_final')}\n"
        f"Dirección    : {analysis.get('direccion')}\n"
        f"Señal N+1    : {analysis.get('signal_n1')}\n"
        "----------------------------------------\n"
        f"Open         : {analysis.get('open')}\n"
        f"High         : {analysis.get('high')}\n"
        f"Low          : {analysis.get('low')}\n"
        f"Close        : {analysis.get('close')}\n"
        "----------------------------------------\n"
        f"Rango        : {analysis.get('rango')}\n"
        f"Cuerpo       : {analysis.get('cuerpo')}\n"
        f"Ratio cuerpo : {analysis.get('ratio_cuerpo')}\n"
        f"Mecha sup.   : {analysis.get('mecha_superior')}\n"
        f"Mecha inf.   : {analysis.get('mecha_inferior')}\n"
        f"Cierre pos.  : {analysis.get('posicion_cierre')}\n"
        "----------------------------------------\n"
        f"Fuerza       : {analysis.get('fuerza')}\n"
        f"Continuidad  : {analysis.get('continuidad')}\n"
        f"Reversión    : {analysis.get('reversion')}\n"
        f"Indecisión   : {analysis.get('indecision')}\n"
        f"Debilidad    : {analysis.get('debilidad')}\n"
        f"Doji         : {analysis.get('doji')}\n"
        "========================================\n"
    )


# ============================================================
# EJEMPLO DE FLUJO CORRECTO
# ============================================================
#
# El BOT debe hacer algo equivalente a:
#
#   vela_n = obtener_vela_m1_ya_cerrada()
#   vela_n_1 = obtener_vela_m1_anterior()
#
#   resultado = build_n1_signal(
#       vela_n,
#       vela_n_1
#   )
#
#   señal = resultado["signal_n1"]
#
#   if señal == "CALL":
#       # ejecutar únicamente en APERTURA DE N+1
#       pass
#
#   elif señal == "PUT":
#       # ejecutar únicamente en APERTURA DE N+1
#       pass
#
#   else:
#       # NO OPERAR
#       pass
#
# ============================================================
# FIN strategy.py
# ============================================================
