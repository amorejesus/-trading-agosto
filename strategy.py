import math
import pandas as pd


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

MIN_CANDLES = 20

STRUCTURE_LOOKBACK = 15

SR_LOOKBACK = 20

# Distancia mínima relativa para considerar
# una zona como soporte/resistencia.
SR_ATR_DISTANCE = 0.60

# Score mínimo para considerar continuidad.
MIN_SCORE = 7

# Score máximo de estructura.
MAX_SCORE = 10

# ============================================================
# FILTROS DE FUERZA
# ============================================================

# Una vela extremadamente grande no se persigue.
MAX_CONFIRMATION_ATR = 1.80

# Una vela demasiado pequeña no confirma continuidad.
MIN_BODY_ATR = 0.05

# Cuerpo mínimo respecto al rango.
MIN_BODY_RATIO = 0.35

# Cierre cerca del extremo correcto.
MIN_CLOSE_POSITION = 0.60

# ============================================================
# ESTRUCTURA
# ============================================================

MIN_TREND_STEPS = 3

# Diferencia mínima entre estructuras.
STRUCTURE_EPSILON = 0.00001


# ============================================================
# UTILIDADES
# ============================================================

def safe_float(value, default=0.0):

    try:

        value = float(value)

        if math.isnan(value):
            return default

        if math.isinf(value):
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

    # --------------------------------------------------------
    # NORMALIZAR COLUMNAS
    # --------------------------------------------------------

    rename_map = {
        "max": "high",
        "min": "low"
    }

    data.rename(
        columns=rename_map,
        inplace=True
    )

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

    return data


# ============================================================
# INDICADORES
# ============================================================

def add_indicators(df):

    data = df.copy()

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    data["ema9"] = (
        data["close"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    data["ema21"] = (
        data["close"]
        .ewm(
            span=21,
            adjust=False
        )
        .mean()
    )

    data["ema50"] = (
        data["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # TRUE RANGE
    # --------------------------------------------------------

    previous_close = (
        data["close"].shift(1)
    )

    range_1 = (
        data["high"]
        - data["low"]
    )

    range_2 = (
        data["high"]
        - previous_close
    ).abs()

    range_3 = (
        data["low"]
        - previous_close
    ).abs()

    data["tr"] = pd.concat(
        [
            range_1,
            range_2,
            range_3
        ],
        axis=1
    ).max(axis=1)

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    data["atr"] = (
        data["tr"]
        .rolling(
            14,
            min_periods=5
        )
        .mean()
    )

    return data


# ============================================================
# DIRECCIÓN DE VELA
# ============================================================

def candle_direction(candle):

    opening = safe_float(
        candle["open"]
    )

    closing = safe_float(
        candle["close"]
    )

    if closing > opening:
        return "bull"

    if closing < opening:
        return "bear"

    return "neutral"


# ============================================================
# DATOS DE UNA VELA
# ============================================================

def candle_metrics(candle):

    opening = safe_float(
        candle["open"]
    )

    closing = safe_float(
        candle["close"]
    )

    high = safe_float(
        candle["high"]
    )

    low = safe_float(
        candle["low"]
    )

    total_range = (
        high - low
    )

    body = abs(
        closing - opening
    )

    upper_wick = (
        high
        - max(opening, closing)
    )

    lower_wick = (
        min(opening, closing)
        - low
    )

    if total_range <= 0:
        body_ratio = 0.0
    else:
        body_ratio = (
            body / total_range
        )

    if total_range <= 0:
        close_position = 0.5
    else:
        close_position = (
            closing - low
        ) / total_range

    return {
        "open": opening,
        "close": closing,
        "high": high,
        "low": low,
        "range": total_range,
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body_ratio,
        "close_position": close_position
    }


# ============================================================
# ESTRUCTURA DEL MERCADO
# ============================================================

def detect_structure(df):

    if len(df) < MIN_TREND_STEPS + 2:

        return {
            "direction": "range",
            "bullish_steps": 0,
            "bearish_steps": 0
        }

    data = df.tail(
        STRUCTURE_LOOKBACK
    )

    highs = [
        safe_float(x)
        for x in data["high"]
    ]

    lows = [
        safe_float(x)
        for x in data["low"]
    ]

    bullish_steps = 0
    bearish_steps = 0

    # --------------------------------------------------------
    # CONTAR ESTRUCTURA
    # --------------------------------------------------------

    for i in range(1, len(highs)):

        previous_high = highs[i - 1]
        current_high = highs[i]

        previous_low = lows[i - 1]
        current_low = lows[i]

        if (
            current_high
            > previous_high
            + STRUCTURE_EPSILON
            and
            current_low
            > previous_low
            + STRUCTURE_EPSILON
        ):

            bullish_steps += 1

        elif (
            current_high
            < previous_high
            - STRUCTURE_EPSILON
            and
            current_low
            < previous_low
            - STRUCTURE_EPSILON
        ):

            bearish_steps += 1

    # --------------------------------------------------------
    # TENDENCIA ALCISTA
    # --------------------------------------------------------

    if (
        bullish_steps
        >= MIN_TREND_STEPS
        and
        bullish_steps
        > bearish_steps
    ):

        return {
            "direction": "bullish",
            "bullish_steps": bullish_steps,
            "bearish_steps": bearish_steps
        }

    # --------------------------------------------------------
    # TENDENCIA BAJISTA
    # --------------------------------------------------------

    if (
        bearish_steps
        >= MIN_TREND_STEPS
        and
        bearish_steps
        > bullish_steps
    ):

        return {
            "direction": "bearish",
            "bullish_steps": bullish_steps,
            "bearish_steps": bearish_steps
        }

    return {
        "direction": "range",
        "bullish_steps": bullish_steps,
        "bearish_steps": bearish_steps
    }


# ============================================================
# ESTRUCTURA MÁS PROFUNDA
# ============================================================

def structure_quality(df, direction):

    if len(df) < 8:
        return 0

    data = df.tail(8)

    highs = [
        safe_float(x)
        for x in data["high"]
    ]

    lows = [
        safe_float(x)
        for x in data["low"]
    ]

    score = 0

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        hh = 0
        hl = 0

        for i in range(1, len(highs)):

            if highs[i] > highs[i - 1]:
                hh += 1

            if lows[i] > lows[i - 1]:
                hl += 1

        if hh >= 3:
            score += 1

        if hl >= 3:
            score += 1

        if hh >= 4:
            score += 1

        if hl >= 4:
            score += 1

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    elif direction == "bearish":

        lh = 0
        ll = 0

        for i in range(1, len(highs)):

            if highs[i] < highs[i - 1]:
                lh += 1

            if lows[i] < lows[i - 1]:
                ll += 1

        if lh >= 3:
            score += 1

        if ll >= 3:
            score += 1

        if lh >= 4:
            score += 1

        if ll >= 4:
            score += 1

    return min(
        score,
        4
    )


# ============================================================
# MOMENTUM
# ============================================================

def momentum_direction(df):

    if len(df) < 5:
        return "neutral"

    recent = df.tail(5)

    bullish = 0
    bearish = 0

    for _, candle in recent.iterrows():

        direction = candle_direction(
            candle
        )

        if direction == "bull":
            bullish += 1

        elif direction == "bear":
            bearish += 1

    if bullish >= 3:
        return "bullish"

    if bearish >= 3:
        return "bearish"

    return "neutral"


# ============================================================
# DETECTAR PULLBACK
# ============================================================

def detect_pullback(
    df,
    trend
):

    if len(df) < 5:
        return False

    recent = df.tail(5)

    directions = [
        candle_direction(
            recent.iloc[i]
        )
        for i in range(len(recent))
    ]

    if trend == "bullish":

        # Corrección pequeña permitida,
        # pero no una inversión completa.
        if (
            directions[-1] == "bear"
            and
            directions[-2] == "bear"
        ):

            return True

    if trend == "bearish":

        if (
            directions[-1] == "bull"
            and
            directions[-2] == "bull"
        ):

            return True

    return False


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def get_support_resistance(
    df
):

    if len(df) < 5:

        return {
            "support": None,
            "resistance": None
        }

    data = df.tail(
        SR_LOOKBACK
    )

    support = safe_float(
        data["low"].min()
    )

    resistance = safe_float(
        data["high"].max()
    )

    return {
        "support": support,
        "resistance": resistance
    }


# ============================================================
# CERCA DE SOPORTE / RESISTENCIA
# ============================================================

def is_near_sr(
    df,
    direction=None
):

    if len(df) < 10:
        return False

    last_close = safe_float(
        df.iloc[-1]["close"]
    )

    levels = get_support_resistance(
        df.iloc[:-1]
    )

    support = levels[
        "support"
    ]

    resistance = levels[
        "resistance"
    ]

    atr = safe_float(
        df.iloc[-1].get(
            "atr",
            0
        )
    )

    if atr <= 0:

        atr = (
            df["high"]
            - df["low"]
        ).tail(14).mean()

    if atr <= 0:
        return False

    distance = (
        atr * SR_ATR_DISTANCE
    )

    # --------------------------------------------------------
    # CERCA DE RESISTENCIA
    # --------------------------------------------------------

    near_resistance = (
        resistance is not None
        and
        abs(
            last_close
            - resistance
        ) <= distance
    )

    # --------------------------------------------------------
    # CERCA DE SOPORTE
    # --------------------------------------------------------

    near_support = (
        support is not None
        and
        abs(
            last_close
            - support
        ) <= distance
    )

    # --------------------------------------------------------
    # CUALQUIER ZONA PELIGROSA
    # --------------------------------------------------------

    if direction is None:

        return (
            near_support
            or
            near_resistance
        )

    # Para CALL no queremos entrar
    # justo debajo de resistencia.
    if direction == "bullish":

        return near_resistance

    # Para PUT no queremos entrar
    # justo encima de soporte.
    if direction == "bearish":

        return near_support

    return (
        near_support
        or
        near_resistance
    )


# ============================================================
# POSICIÓN RESPECTO A LA ZONA
# ============================================================

def location_score(
    df,
    direction
):

    if len(df) < 10:
        return 0

    levels = get_support_resistance(
        df.iloc[:-1]
    )

    support = levels[
        "support"
    ]

    resistance = levels[
        "resistance"
    ]

    close = safe_float(
        df.iloc[-1]["close"]
    )

    atr = safe_float(
        df.iloc[-1].get(
            "atr",
            0
        )
    )

    if atr <= 0:
        return 0

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    if direction == "bullish":

        if resistance is None:
            return 1

        distance = (
            resistance - close
        )

        if distance > atr * 1.2:
            return 2

        if distance > atr * 0.7:
            return 1

        return 0

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    if direction == "bearish":

        if support is None:
            return 1

        distance = (
            close - support
        )

        if distance > atr * 1.2:
            return 2

        if distance > atr * 0.7:
            return 1

        return 0

    return 0


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def detect_trend_exhaustion(
    df,
    trend
):

    if len(df) < 6:
        return False

    recent = df.tail(6)

    # --------------------------------------------------------
    # CONTAR VELAS CONTRARIAS
    # --------------------------------------------------------

    opposite = 0

    for _, candle in recent.iterrows():

        direction = candle_direction(
            candle
        )

        if trend == "bullish":

            if direction == "bear":
                opposite += 1

        elif trend == "bearish":

            if direction == "bull":

                opposite += 1

    # Dos o más velas contrarias
    # consecutivas pueden representar
    # pérdida de continuidad.
    last = recent.iloc[-1]
    previous = recent.iloc[-2]

    last_direction = candle_direction(
        last
    )

    previous_direction = candle_direction(
        previous
    )

    if trend == "bullish":

        if (
            last_direction == "bear"
            and
            previous_direction == "bear"
        ):
            return True

    if trend == "bearish":

        if (
            last_direction == "bull"
            and
            previous_direction == "bull"
        ):
            return True

    if opposite >= 4:
        return True

    return False


# ============================================================
# RECHAZO FUERTE
# ============================================================

def strong_rejection(
    candle,
    trend
):

    metrics = candle_metrics(
        candle
    )

    body = metrics[
        "body"
    ]

    total_range = metrics[
        "range"
    ]

    upper_wick = metrics[
        "upper_wick"
    ]

    lower_wick = metrics[
        "lower_wick"
    ]

    if total_range <= 0:
        return True

    # --------------------------------------------------------
    # RECHAZO CONTRA ALCISTA
    # --------------------------------------------------------

    if trend == "bullish":

        # Mecha superior muy grande
        if (
            upper_wick
            > body * 1.8
        ):

            return True

        # Cierre demasiado lejos
        # del máximo
        if (
            metrics["close_position"]
            < 0.45
        ):

            return True

    # --------------------------------------------------------
    # RECHAZO CONTRA BAJISTA
    # --------------------------------------------------------

    if trend == "bearish":

        if (
            lower_wick
            > body * 1.8
        ):

            return True

        if (
            metrics["close_position"]
            > 0.55
        ):

            return True

    return False


# ============================================================
# FUERZA DE LA VELA DE CONFIRMACIÓN
# ============================================================

def confirmation_strength(
    candle,
    atr,
    trend
):

    metrics = candle_metrics(
        candle
    )

    total_range = metrics[
        "range"
    ]

    body = metrics[
        "body"
    ]

    body_ratio = metrics[
        "body_ratio"
    ]

    close_position = metrics[
        "close_position"
    ]

    if total_range <= 0:
        return {
            "valid": False,
            "strong": False,
            "score": 0,
            "reason": "vela sin rango"
        }

    if atr <= 0:

        atr = total_range

    range_atr = (
        total_range / atr
    )

    body_atr = (
        body / atr
    )

    # --------------------------------------------------------
    # VELA DEMASIADO FUERTE
    # --------------------------------------------------------

    if (
        range_atr
        > MAX_CONFIRMATION_ATR
    ):

        return {
            "valid": False,
            "strong": True,
            "score": 0,
            "reason":
                "vela de confirmación "
                "demasiado fuerte"
        }

    # --------------------------------------------------------
    # CUERPO DEMASIADO PEQUEÑO
    # --------------------------------------------------------

    if (
        body_atr
        < MIN_BODY_ATR
    ):

        return {
            "valid": False,
            "strong": False,
            "score": 0,
            "reason":
                "vela de confirmación "
                "demasiado débil"
        }

    # --------------------------------------------------------
    # CUERPO / RANGO
    # --------------------------------------------------------

    if (
        body_ratio
        < MIN_BODY_RATIO
    ):

        return {
            "valid": False,
            "strong": False,
            "score": 0,
            "reason":
                "cuerpo insuficiente"
        }

    # --------------------------------------------------------
    # CONFIRMACIÓN ALCISTA
    # --------------------------------------------------------

    if trend == "bullish":

        if (
            candle_direction(candle)
            != "bull"
        ):

            return {
                "valid": False,
                "strong": False,
                "score": 0,
                "reason":
                    "cierre no confirma "
                    "continuidad alcista"
            }

        if (
            close_position
            < MIN_CLOSE_POSITION
        ):

            return {
                "valid": False,
                "strong": False,
                "score": 0,
                "reason":
                    "cierre alcista "
                    "demasiado débil"
            }

        return {
            "valid": True,
            "strong": False,
            "score": 2,
            "reason":
                "vela alcista confirma "
                "continuidad"
        }

    # --------------------------------------------------------
    # CONFIRMACIÓN BAJISTA
    # --------------------------------------------------------

    if trend == "bearish":

        if (
            candle_direction(candle)
            != "bear"
        ):

            return {
                "valid": False,
                "strong": False,
                "score": 0,
                "reason":
                    "cierre no confirma "
                    "continuidad bajista"
            }

        if (
            close_position
            > (
                1
                - MIN_CLOSE_POSITION
            )
        ):

            return {
                "valid": False,
                "strong": False,
                "score": 0,
                "reason":
                    "cierre bajista "
                    "demasiado débil"
            }

        return {
            "valid": True,
            "strong": False,
            "score": 2,
            "reason":
                "vela bajista confirma "
                "continuidad"
        }

    return {
        "valid": False,
        "strong": False,
        "score": 0,
        "reason": "sin tendencia"
    }


# ============================================================
# CONTINUIDAD DE LAS ÚLTIMAS VELAS
# ============================================================

def continuity_score(
    df,
    trend
):

    if len(df) < 6:
        return 0

    recent = df.tail(6)

    score = 0

    for _, candle in recent.iterrows():

        direction = candle_direction(
            candle
        )

        if trend == "bullish":

            if direction == "bull":
                score += 1

        elif trend == "bearish":

            if direction == "bear":
                score += 1

    return min(
        score,
        6
    )


# ============================================================
# VELOCIDAD DEL MOVIMIENTO
# ============================================================

def movement_is_too_strong(
    df,
    trend
):

    if len(df) < 5:
        return False

    recent = df.tail(5)

    atr = safe_float(
        df.iloc[-1].get(
            "atr",
            0
        )
    )

    if atr <= 0:
        return False

    total_move = (
        safe_float(
            recent.iloc[-1]["close"]
        )
        -
        safe_float(
            recent.iloc[0]["open"]
        )
    )

    if trend == "bearish":

        total_move = abs(
            total_move
        )

    elif trend == "bullish":

        total_move = abs(
            total_move
        )

    else:

        return False

    # Movimiento acumulado
    # excesivamente grande.
    if total_move > atr * 4.5:
        return True

    return False


# ============================================================
# SCORE DE ESTRUCTURA
# ============================================================

def calculate_structure_score(
    df,
    trend
):

    score = 0

    structure = detect_structure(
        df
    )

    # --------------------------------------------------------
    # ESTRUCTURA BASE
    # --------------------------------------------------------

    if structure["direction"] == trend:

        score += 3

    else:

        return 0

    # --------------------------------------------------------
    # CALIDAD
    # --------------------------------------------------------

    quality = structure_quality(
        df,
        trend
    )

    score += quality

    # --------------------------------------------------------
    # CONTINUIDAD
    # --------------------------------------------------------

    continuity = continuity_score(
        df,
        trend
    )

    if continuity >= 4:

        score += 2

    elif continuity >= 3:

        score += 1

    # --------------------------------------------------------
    # MOMENTUM
    # --------------------------------------------------------

    momentum = momentum_direction(
        df
    )

    if momentum == trend:

        score += 1

    # --------------------------------------------------------
    # UBICACIÓN
    # --------------------------------------------------------

    location = location_score(
        df,
        trend
    )

    score += location

    return min(
        score,
        MAX_SCORE
    )


# ============================================================
# SCORE QUE PASA A LA VELA DE CONFIRMACIÓN
# ============================================================

def confirmation_score(
    structure_score,
    candle_score,
    df,
    trend
):

    score = structure_score

    # --------------------------------------------------------
    # LA VELA DE CONFIRMACIÓN
    # APORTA PUNTOS SIN BORRAR
    # LA ESTRUCTURA
    # --------------------------------------------------------

    score += candle_score

    # --------------------------------------------------------
    # PENALIZAR UBICACIÓN PELIGROSA
    # --------------------------------------------------------

    if is_near_sr(
        df,
        trend
    ):

        score -= 3

    # --------------------------------------------------------
    # PENALIZAR AGOTAMIENTO
    # --------------------------------------------------------

    if detect_trend_exhaustion(
        df,
        trend
    ):

        score -= 3

    return max(
        0,
        min(
            score,
            MAX_SCORE
        )
    )


# ============================================================
# DIRECCIÓN DE OPERACIÓN
# ============================================================

def get_signal(
    trend
):

    if trend == "bullish":

        return "call"

    if trend == "bearish":

        return "put"

    return None


# ============================================================
# RAZÓN
# ============================================================

def build_reason(
    trend,
    score,
    structure,
    candle_result
):

    return (
        f"continuidad {trend} | "
        f"estructura "
        f"{structure['bullish_steps']}/"
        f"{structure['bearish_steps']} | "
        f"confirmación: "
        f"{candle_result['reason']} | "
        f"score={score}/10"
    )


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def analyze_market(df):

    """
    FUNCIÓN PRINCIPAL UTILIZADA POR bot.py.

    IMPORTANTE:

    bot.py entrega las velas disponibles.
    Esta estrategia utiliza solamente las velas
    cerradas que recibe.

    Devuelve:

    {
        "signal": "call" / "put" / None,
        "direction": "bullish" / "bearish" / "range",
        "reason": "...",
        "score": número
    }
    """

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    data = prepare_dataframe(
        df
    )

    if data is None:

        return {
            "signal": None,
            "direction": "range",
            "reason": "datos inválidos",
            "score": 0
        }

    if len(data) < MIN_CANDLES:

        return {
            "signal": None,
            "direction": "range",
            "reason":
                "insuficientes velas",
            "score": 0
        }

    # ========================================================
    # INDICADORES
    # ========================================================

    data = add_indicators(
        data
    )

    # ========================================================
    # ESTRUCTURA
    # ========================================================

    structure = detect_structure(
        data
    )

    trend = structure[
        "direction"
    ]

    # ========================================================
    # NO OPERAR EN RANGE
    # ========================================================

    if trend == "range":

        return {
            "signal": None,
            "direction": "range",
            "reason":
                "no existe una tendencia "
                "clara",
            "score": 0
        }

    # ========================================================
    # SCORE DE ESTRUCTURA
    # ========================================================

    structure_score = (
        calculate_structure_score(
            data,
            trend
        )
    )

    # ========================================================
    # UBICACIÓN
    # ========================================================

    if is_near_sr(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason":
                (
                    "precio en zona de "
                    "soporte/resistencia "
                    "— operación bloqueada"
                ),
            "score": structure_score
        }

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    if detect_trend_exhaustion(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason":
                (
                    "posible final de tendencia "
                    "— operación bloqueada"
                ),
            "score": structure_score
        }

    # ========================================================
    # MOVIMIENTO DEMASIADO FUERTE
    # ========================================================

    if movement_is_too_strong(
        data,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason":
                (
                    "movimiento acumulado "
                    "demasiado fuerte "
                    "— operación bloqueada"
                ),
            "score": structure_score
        }

    # ========================================================
    # VELA DE CONFIRMACIÓN
    # ========================================================

    confirmation = data.iloc[-1]

    atr = safe_float(
        confirmation.get(
            "atr",
            0
        )
    )

    candle_result = (
        confirmation_strength(
            confirmation,
            atr,
            trend
        )
    )

    # ========================================================
    # VELA NO CONFIRMA
    # ========================================================

    if not candle_result[
        "valid"
    ]:

        return {
            "signal": None,
            "direction": trend,
            "reason":
                candle_result["reason"],
            "score": structure_score
        }

    # ========================================================
    # RECHAZO
    # ========================================================

    if strong_rejection(
        confirmation,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason":
                (
                    "rechazo fuerte "
                    "en vela de confirmación"
                ),
            "score": structure_score
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
            "reason":
                (
                    "pullback detectado "
                    "— no es continuidad limpia"
                ),
            "score": structure_score
        }

    # ========================================================
    # SCORE FINAL
    # ========================================================

    final_score = confirmation_score(
        structure_score,
        candle_result["score"],
        data,
        trend
    )

    # ========================================================
    # SCORE INSUFICIENTE
    # ========================================================

    if final_score < MIN_SCORE:

        return {
            "signal": None,
            "direction": trend,
            "reason":
                (
                    "score insuficiente "
                    f"{final_score}/10"
                ),
            "score": final_score
        }

    # ========================================================
    # SEÑAL
    # ========================================================

    signal = get_signal(
        trend
    )

    if signal is None:

        return {
            "signal": None,
            "direction": trend,
            "reason":
                "no hay señal válida",
            "score": final_score
        }

    # ========================================================
    # RAZÓN FINAL
    # ========================================================

    reason = build_reason(
        trend,
        final_score,
        structure,
        candle_result
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "signal": signal,
        "direction": trend,
        "reason": reason,
        "score": final_score
    }


# ============================================================
# FUNCIÓN DE PRUEBA
# ============================================================

def test_strategy(df):

    result = analyze_market(
        df
    )

    print(
        "================================"
    )

    print(
        "RESULTADO DE ESTRATEGIA"
    )

    print(
        "================================"
    )

    print(
        "Señal:",
        result.get("signal")
    )

    print(
        "Dirección:",
        result.get("direction")
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
        "================================"
    )

    return result
