import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN DE LA ESTRATEGIA
# ============================================================

MAX_CANDLES = 60

# Cuántas velas recientes usamos para determinar estructura
STRUCTURE_CANDLES = 20

# Ventana para detectar soporte/resistencia
SR_WINDOW = 20

# Tolerancias relativas
SR_TOLERANCE = 0.0010

# Fuerza mínima de cuerpo respecto al rango
MIN_BODY_RATIO = 0.45

# Evitar velas extremadamente pequeñas
MIN_RANGE_RATIO = 0.00005


# ============================================================
# UTILIDADES
# ============================================================

def safe_float(value, default=0.0):

    try:
        value = float(value)

        if np.isnan(value):
            return default

        return value

    except Exception:
        return default


# ============================================================
# PREPARAR DATAFRAME
# ============================================================

def prepare_dataframe(df):

    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return None

    if df.empty:
        return None

    data = df.copy()

    required = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        if column not in data.columns:
            return None

        data[column] = pd.to_numeric(
            data[column],
            errors="coerce"
        )

    data.dropna(
        subset=required,
        inplace=True
    )

    data.reset_index(
        drop=True,
        inplace=True
    )

    if len(data) < 10:
        return None

    return data


# ============================================================
# DATOS DE LA VELA
# ============================================================

def candle_range(candle):

    high = safe_float(candle["high"])
    low = safe_float(candle["low"])

    return max(
        high - low,
        0.0
    )


def candle_body(candle):

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    return abs(
        close_price - open_price
    )


def candle_direction(candle):

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    if close_price > open_price:
        return "bull"

    if close_price < open_price:
        return "bear"

    return "neutral"


# ============================================================
# CARACTERÍSTICAS DE VELA
# ============================================================

def candle_strength(candle):

    rng = candle_range(
        candle
    )

    body = candle_body(
        candle
    )

    if rng <= 0:
        return 0.0

    return body / rng


def upper_wick(candle):

    high = safe_float(
        candle["high"]
    )

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    return max(
        0.0,
        high - max(
            open_price,
            close_price
        )
    )


def lower_wick(candle):

    low = safe_float(
        candle["low"]
    )

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    return max(
        0.0,
        min(
            open_price,
            close_price
        ) - low
    )


# ============================================================
# ESTRUCTURA DE MERCADO
# ============================================================

def detect_structure(df):

    if df is None or len(df) < 6:

        return "range"

    data = df.tail(
        min(
            STRUCTURE_CANDLES,
            len(df)
        )
    ).copy()

    highs = data["high"].astype(float).values
    lows = data["low"].astype(float).values

    hh = 0
    hl = 0
    lh = 0
    ll = 0

    for i in range(1, len(highs)):

        if highs[i] > highs[i - 1]:
            hh += 1

        elif highs[i] < highs[i - 1]:
            lh += 1

        if lows[i] > lows[i - 1]:
            hl += 1

        elif lows[i] < lows[i - 1]:
            ll += 1

    # --------------------------------------------------------
    # ESTRUCTURA ALCISTA
    # --------------------------------------------------------

    bullish_score = (
        hh + hl
    )

    bearish_score = (
        lh + ll
    )

    if (
        hh >= 7
        and hl >= 7
        and bullish_score > bearish_score + 3
    ):

        return "bullish"

    # --------------------------------------------------------
    # ESTRUCTURA BAJISTA
    # --------------------------------------------------------

    if (
        lh >= 7
        and ll >= 7
        and bearish_score > bullish_score + 3
    ):

        return "bearish"

    return "range"


# ============================================================
# TENDENCIA
# ============================================================

def detect_trend(df):

    if df is None or len(df) < 10:

        return "range"

    data = df.tail(
        min(
            20,
            len(df)
        )
    )

    closes = (
        data["close"]
        .astype(float)
        .values
    )

    # --------------------------------------------------------
    # DIVIDIR EN DOS BLOQUES
    # --------------------------------------------------------

    middle = len(closes) // 2

    first = closes[:middle]
    second = closes[middle:]

    if len(first) < 3 or len(second) < 3:
        return "range"

    first_mean = np.mean(first)
    second_mean = np.mean(second)

    movement = (
        second_mean - first_mean
    )

    last_price = closes[-1]

    first_price = closes[0]

    total_move = (
        last_price - first_price
    )

    # --------------------------------------------------------
    # TOLERANCIA
    # --------------------------------------------------------

    reference = max(
        abs(first_price),
        1e-9
    )

    relative_move = (
        abs(total_move)
        / reference
    )

    # Movimiento demasiado pequeño
    # = sin tendencia clara

    if relative_move < MIN_RANGE_RATIO:

        return "range"

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if (
        movement > 0
        and total_move > 0
    ):

        return "bullish"

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if (
        movement < 0
        and total_move < 0
    ):

        return "bearish"

    return "range"


# ============================================================
# SOPORTE Y RESISTENCIA
# ============================================================

def detect_support_resistance(df):

    if df is None or len(df) < 5:

        return False, False

    data = df.tail(
        min(
            SR_WINDOW,
            len(df)
        )
    )

    current_price = safe_float(
        data.iloc[-1]["close"]
    )

    highest = safe_float(
        data["high"].max()
    )

    lowest = safe_float(
        data["low"].min()
    )

    if current_price <= 0:
        return False, False

    resistance_distance = (
        abs(
            highest - current_price
        )
        / current_price
    )

    support_distance = (
        abs(
            current_price - lowest
        )
        / current_price
    )

    near_resistance = (
        resistance_distance
        <= SR_TOLERANCE
    )

    near_support = (
        support_distance
        <= SR_TOLERANCE
    )

    return (
        near_support,
        near_resistance
    )


# ============================================================
# RECHAZO
# ============================================================

def detect_rejection(candle):

    rng = candle_range(
        candle
    )

    if rng <= 0:
        return False

    body = candle_body(
        candle
    )

    upper = upper_wick(
        candle
    )

    lower = lower_wick(
        candle
    )

    # --------------------------------------------------------
    # Rechazo superior
    # --------------------------------------------------------

    if (
        upper / rng >= 0.45
        and upper > body * 1.3
    ):

        return True

    # --------------------------------------------------------
    # Rechazo inferior
    # --------------------------------------------------------

    if (
        lower / rng >= 0.45
        and lower > body * 1.3
    ):

        return True

    return False


# ============================================================
# DEBILIDAD
# ============================================================

def detect_weakness(
    df,
    direction
):

    if df is None or len(df) < 5:
        return True

    recent = df.tail(5)

    strengths = []

    directions = []

    for _, candle in recent.iterrows():

        strengths.append(
            candle_strength(
                candle
            )
        )

        directions.append(
            candle_direction(
                candle
            )
        )

    # --------------------------------------------------------
    # Dirección esperada
    # --------------------------------------------------------

    expected = (
        "bull"
        if direction == "bullish"
        else "bear"
    )

    matching = sum(
        1
        for d in directions
        if d == expected
    )

    average_strength = np.mean(
        strengths
    )

    # Pocas velas a favor
    if matching < 2:

        return True

    # Fuerza media demasiado baja
    if average_strength < 0.25:

        return True

    return False


# ============================================================
# PULLBACK
# ============================================================

def detect_pullback(
    df,
    direction
):

    if df is None or len(df) < 6:

        return True

    recent = df.tail(6)

    bullish_count = 0
    bearish_count = 0

    for _, candle in recent.iterrows():

        direction_candle = candle_direction(
            candle
        )

        if direction_candle == "bull":
            bullish_count += 1

        elif direction_candle == "bear":
            bearish_count += 1

    # --------------------------------------------------------
    # Tendencia alcista
    # --------------------------------------------------------

    if direction == "bullish":

        if bearish_count >= 4:

            return True

    # --------------------------------------------------------
    # Tendencia bajista
    # --------------------------------------------------------

    if direction == "bearish":

        if bullish_count >= 4:

            return True

    return False


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def detect_end_of_trend(
    df,
    direction
):

    if df is None or len(df) < 8:

        return True

    recent = df.tail(8)

    ranges = []

    bodies = []

    for _, candle in recent.iterrows():

        ranges.append(
            candle_range(
                candle
            )
        )

        bodies.append(
            candle_body(
                candle
            )
        )

    # --------------------------------------------------------
    # Promedios
    # --------------------------------------------------------

    average_range = np.mean(
        ranges[:-2]
    )

    last_range = np.mean(
        ranges[-2:]
    )

    if average_range <= 0:

        return True

    # --------------------------------------------------------
    # Contracción fuerte
    # --------------------------------------------------------

    if (
        last_range
        < average_range * 0.45
    ):

        return True

    # --------------------------------------------------------
    # Últimas velas con mechas grandes
    # --------------------------------------------------------

    last_candle = recent.iloc[-1]

    rng = candle_range(
        last_candle
    )

    body = candle_body(
        last_candle
    )

    if rng > 0:

        body_ratio = (
            body / rng
        )

        if body_ratio < 0.25:

            return True

    return False


# ============================================================
# CONTINUIDAD
# ============================================================

def detect_continuity(
    df,
    direction
):

    if df is None or len(df) < 5:

        return False

    current = df.iloc[-1]

    previous = df.iloc[-2]

    current_direction = candle_direction(
        current
    )

    previous_direction = candle_direction(
        previous
    )

    current_strength = candle_strength(
        current
    )

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        if current_direction != "bull":
            return False

        if current_strength < MIN_BODY_RATIO:
            return False

        # La vela actual debe mantener
        # estructura respecto a la anterior.

        if (
            safe_float(current["close"])
            < safe_float(previous["close"])
        ):

            return False

        return True

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if direction == "bearish":

        if current_direction != "bear":
            return False

        if current_strength < MIN_BODY_RATIO:
            return False

        if (
            safe_float(current["close"])
            > safe_float(previous["close"])
        ):

            return False

        return True

    return False


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    df,
    direction
):

    score = 0

    # --------------------------------------------------------
    # Estructura
    # --------------------------------------------------------

    structure = detect_structure(
        df
    )

    if structure == direction:

        score += 2

    # --------------------------------------------------------
    # Tendencia
    # --------------------------------------------------------

    trend = detect_trend(
        df
    )

    if trend == direction:

        score += 2

    # --------------------------------------------------------
    # Continuidad
    # --------------------------------------------------------

    if detect_continuity(
        df,
        direction
    ):

        score += 2

    # --------------------------------------------------------
    # Vela fuerte
    # --------------------------------------------------------

    current = df.iloc[-1]

    if (
        candle_strength(current)
        >= MIN_BODY_RATIO
    ):

        score += 1

    return score


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(df):

    data = prepare_dataframe(
        df
    )

    if data is None:

        return {
            "signal": None,
            "direction": "range",
            "reason": "Datos insuficientes",
            "score": 0
        }

    # ========================================================
    # MÁXIMO 60 VELAS
    # ========================================================

    if len(data) > MAX_CANDLES:

        data = data.tail(
            MAX_CANDLES
        ).reset_index(
            drop=True
        )

    # ========================================================
    # TENDENCIA
    # ========================================================

    trend = detect_trend(
        data
    )

    structure = detect_structure(
        data
    )

    # --------------------------------------------------------
    # SIN TENDENCIA
    # --------------------------------------------------------

    if trend == "range":

        return {
            "signal": None,
            "direction": "range",
            "reason": "No existe tendencia clara",
            "score": 0
        }

    # ========================================================
    # LA ESTRUCTURA DEBE COINCIDIR
    # ========================================================

    if structure != trend:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "La estructura no confirma "
                "la tendencia"
            ),
            "score": 0
        }

    # ========================================================
    # SOPORTE / RESISTENCIA
    # ========================================================

    near_support, near_resistance = (
        detect_support_resistance(
            data
        )
    )

    if near_support:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "PRECIO EN SOPORTE - "
                "OPERACIÓN BLOQUEADA"
            ),
            "score": 0
        }

    if near_resistance:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "PRECIO EN RESISTENCIA - "
                "OPERACIÓN BLOQUEADA"
            ),
            "score": 0
        }

    # ========================================================
    # RECHAZO
    # ========================================================

    current = data.iloc[-1]

    if detect_rejection(
        current
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Zona de rechazo - "
                "operación bloqueada"
            ),
            "score": 0
        }

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    if detect_end_of_trend(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Posible final de tendencia - "
                "operación bloqueada"
            ),
            "score": 0
        }

    # ========================================================
    # PULLBACK
    # ========================================================

    if detect_pullback(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Pullback detectado - "
                "operación bloqueada"
            ),
            "score": 0
        }

    # ========================================================
    # DEBILIDAD
    # ========================================================

    if detect_weakness(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Debilidad detectada - "
                "operación bloqueada"
            ),
            "score": 0
        }

    # ========================================================
    # CONTINUIDAD
    # ========================================================

    continuity = detect_continuity(
        data,
        trend
    )

    if not continuity:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "No existe continuidad "
                "confirmada"
            ),
            "score": 0
        }

    # ========================================================
    # SCORE
    # ========================================================

    score = calculate_score(
        data,
        trend
    )

    # ========================================================
    # SCORE MÍNIMO
    # ========================================================

    if score < 5:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Continuidad insuficiente "
                f"(score={score})"
            ),
            "score": score
        }

    # ========================================================
    # SEÑAL
    # ========================================================

    if trend == "bullish":

        signal = "call"

        reason = (
            "CONTINUIDAD ALCISTA "
            "CONFIRMADA"
        )

    elif trend == "bearish":

        signal = "put"

        reason = (
            "CONTINUIDAD BAJISTA "
            "CONFIRMADA"
        )

    else:

        signal = None

        reason = "Sin señal"

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "signal": signal,
        "direction": trend,
        "reason": reason,
        "score": score
    }


# ============================================================
# FUNCIÓN DE PRUEBA
# ============================================================

def test_strategy(df):

    result = analyze_market(
        df
    )

    print(
        "===================================="
    )

    print(
        "RESULTADO DE ESTRATEGIA"
    )

    print(
        "===================================="
    )

    print(
        "Dirección:",
        result.get("direction")
    )

    print(
        "Señal:",
        result.get("signal")
    )

    print(
        "Score:",
        result.get("score")
    )

    print(
        "Razón:",
        result.get("reason")
    )

    print(
        "===================================="
    )

    return result
