import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN
# ============================================================

# Cantidad de velas utilizadas para determinar la estructura
TREND_LOOKBACK = 15

# Mínimo de puntos necesarios en la estructura
MIN_STRUCTURE_SCORE = 5

# Mínimo score final para generar señal
MIN_FINAL_SCORE = 8

# Velas utilizadas para comprobar continuidad reciente
CONTINUITY_LOOKBACK = 6

# Velas utilizadas para detectar agotamiento
EXHAUSTION_LOOKBACK = 8

# Velas utilizadas para soporte/resistencia
SR_LOOKBACK = 20

# ATR
ATR_PERIOD = 14

# Máximo movimiento permitido de la vela de confirmación
MAX_CONFIRMATION_RANGE_ATR = 1.60

MAX_CONFIRMATION_BODY_ATR = 1.20

# Tolerancia para soporte/resistencia
SR_TOLERANCE_ATR = 0.35


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

    required_columns = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required_columns:

        if column not in data.columns:
            return None

        data[column] = pd.to_numeric(
            data[column],
            errors="coerce"
        )

    data.dropna(
        subset=required_columns,
        inplace=True
    )

    data.reset_index(
        drop=True,
        inplace=True
    )

    if len(data) < TREND_LOOKBACK + 1:

        return None

    return data


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df,
    period=ATR_PERIOD
):

    high = df["high"]

    low = df["low"]

    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low

    tr2 = (
        high - previous_close
    ).abs()

    tr3 = (
        low - previous_close
    ).abs()

    true_range = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    atr = true_range.rolling(
        period
    ).mean()

    return atr


# ============================================================
# DATOS DE UNA VELA
# ============================================================

def get_candle_data(candle):

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    high_price = safe_float(
        candle["high"]
    )

    low_price = safe_float(
        candle["low"]
    )

    candle_range = (
        high_price - low_price
    )

    body = abs(
        close_price - open_price
    )

    upper_wick = (
        high_price
        - max(
            open_price,
            close_price
        )
    )

    lower_wick = (
        min(
            open_price,
            close_price
        )
        - low_price
    )

    if candle_range > 0:

        body_ratio = (
            body / candle_range
        )

        upper_wick_ratio = (
            upper_wick / candle_range
        )

        lower_wick_ratio = (
            lower_wick / candle_range
        )

    else:

        body_ratio = 0.0
        upper_wick_ratio = 0.0
        lower_wick_ratio = 0.0

    return {
        "open": open_price,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "range": candle_range,
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body_ratio,
        "upper_wick_ratio": upper_wick_ratio,
        "lower_wick_ratio": lower_wick_ratio
    }


# ============================================================
# DIRECCIÓN DE VELA
# ============================================================

def candle_direction(candle):

    if candle["close"] > candle["open"]:
        return "bullish"

    if candle["close"] < candle["open"]:
        return "bearish"

    return "neutral"


# ============================================================
# ANALIZAR ESTRUCTURA
#
# MÁXIMO 5 PUNTOS
#
# 1. Máximos
# 2. Mínimos
# 3. Desplazamiento
# 4. Continuidad
# 5. Consistencia
# ============================================================

def analyze_structure(df):

    candles = df.tail(
        TREND_LOOKBACK
    ).copy()

    if len(candles) < TREND_LOOKBACK:

        return {
            "direction": "range",
            "score": 0,
            "higher_highs": 0,
            "higher_lows": 0,
            "lower_highs": 0,
            "lower_lows": 0
        }

    highs = candles[
        "high"
    ].to_numpy()

    lows = candles[
        "low"
    ].to_numpy()

    closes = candles[
        "close"
    ].to_numpy()

    bullish_hh = 0
    bullish_hl = 0

    bearish_lh = 0
    bearish_ll = 0

    # --------------------------------------------------------
    # CONTAR ESTRUCTURA
    # --------------------------------------------------------

    for i in range(
        1,
        len(candles)
    ):

        if highs[i] > highs[i - 1]:
            bullish_hh += 1

        elif highs[i] < highs[i - 1]:
            bearish_lh += 1

        if lows[i] > lows[i - 1]:
            bullish_hl += 1

        elif lows[i] < lows[i - 1]:
            bearish_ll += 1

    # --------------------------------------------------------
    # DESPLAZAMIENTO
    # --------------------------------------------------------

    first_close = closes[0]

    last_close = closes[-1]

    price_change = (
        last_close - first_close
    )

    # --------------------------------------------------------
    # PUNTAJE ALCISTA
    # --------------------------------------------------------

    bullish_score = 0

    # Punto 1: máximos crecientes
    if bullish_hh >= 7:

        bullish_score += 1

    # Punto 2: mínimos crecientes
    if bullish_hl >= 7:

        bullish_score += 1

    # Punto 3: desplazamiento
    if price_change > 0:

        bullish_score += 1

    # --------------------------------------------------------
    # CONTINUIDAD DE LOS ÚLTIMOS MOVIMIENTOS
    # --------------------------------------------------------

    recent = candles.tail(
        CONTINUITY_LOOKBACK
    )

    recent_closes = (
        recent["close"].to_numpy()
    )

    bullish_moves = 0

    bearish_moves = 0

    for i in range(
        1,
        len(recent_closes)
    ):

        if (
            recent_closes[i]
            > recent_closes[i - 1]
        ):

            bullish_moves += 1

        elif (
            recent_closes[i]
            < recent_closes[i - 1]
        ):

            bearish_moves += 1

    # Punto 4
    if bullish_moves >= 3:

        bullish_score += 1

    # Punto 5: consistencia
    bullish_candles = 0

    for _, candle in candles.iterrows():

        if (
            candle["close"]
            > candle["open"]
        ):

            bullish_candles += 1

    if bullish_candles >= 8:

        bullish_score += 1

    # --------------------------------------------------------
    # PUNTAJE BAJISTA
    # --------------------------------------------------------

    bearish_score = 0

    # Punto 1
    if bearish_lh >= 7:

        bearish_score += 1

    # Punto 2
    if bearish_ll >= 7:

        bearish_score += 1

    # Punto 3
    if price_change < 0:

        bearish_score += 1

    # Punto 4
    if bearish_moves >= 3:

        bearish_score += 1

    # Punto 5
    bearish_candles = 0

    for _, candle in candles.iterrows():

        if (
            candle["close"]
            < candle["open"]
        ):

            bearish_candles += 1

    if bearish_candles >= 8:

        bearish_score += 1

    # --------------------------------------------------------
    # DETERMINAR DIRECCIÓN
    # --------------------------------------------------------

    if (
        bullish_score >= MIN_STRUCTURE_SCORE
        and
        bullish_score > bearish_score
    ):

        direction = "bullish"

        score = bullish_score

    elif (
        bearish_score >= MIN_STRUCTURE_SCORE
        and
        bearish_score > bullish_score
    ):

        direction = "bearish"

        score = bearish_score

    else:

        direction = "range"

        score = max(
            bullish_score,
            bearish_score
        )

    return {
        "direction": direction,
        "score": score,

        "bullish_score": bullish_score,
        "bearish_score": bearish_score,

        "higher_highs": bullish_hh,
        "higher_lows": bullish_hl,

        "lower_highs": bearish_lh,
        "lower_lows": bearish_ll,

        "price_change": price_change
    }


# ============================================================
# CONTINUIDAD RECIENTE
# ============================================================

def check_continuity(
    df,
    direction
):

    if len(df) < CONTINUITY_LOOKBACK:

        return False

    recent = df.tail(
        CONTINUITY_LOOKBACK
    )

    highs = recent[
        "high"
    ].to_numpy()

    lows = recent[
        "low"
    ].to_numpy()

    closes = recent[
        "close"
    ].to_numpy()

    if direction == "bullish":

        higher_highs = 0
        higher_lows = 0

        for i in range(
            1,
            len(recent)
        ):

            if highs[i] >= highs[i - 1]:

                higher_highs += 1

            if lows[i] >= lows[i - 1]:

                higher_lows += 1

        price_continues = (
            closes[-1]
            > closes[0]
        )

        return (
            higher_highs >= 3
            and
            higher_lows >= 3
            and
            price_continues
        )

    if direction == "bearish":

        lower_highs = 0
        lower_lows = 0

        for i in range(
            1,
            len(recent)
        ):

            if highs[i] <= highs[i - 1]:

                lower_highs += 1

            if lows[i] <= lows[i - 1]:

                lower_lows += 1

        price_continues = (
            closes[-1]
            < closes[0]
        )

        return (
            lower_highs >= 3
            and
            lower_lows >= 3
            and
            price_continues
        )

    return False


# ============================================================
# FINAL DE TENDENCIA / AGOTAMIENTO
# ============================================================

def detect_end_of_trend(
    df,
    direction
):

    if len(df) < EXHAUSTION_LOOKBACK:

        return False

    recent = df.tail(
        EXHAUSTION_LOOKBACK
    )

    last = get_candle_data(
        recent.iloc[-1]
    )

    previous = get_candle_data(
        recent.iloc[-2]
    )

    # ========================================================
    # ALCISTA
    # ========================================================

    if direction == "bullish":

        # Rechazo superior
        if (
            last["upper_wick_ratio"]
            >= 0.55
        ):

            return True

        # Vela demasiado pequeña
        if (
            last["body_ratio"]
            < 0.20
        ):

            return True

        # Dos velas débiles consecutivas
        if (
            previous["body_ratio"]
            < 0.25
            and
            last["body_ratio"]
            < 0.25
        ):

            return True

        # Último cierre perdiendo estructura
        if (
            last["close"]
            < previous["low"]
        ):

            return True

    # ========================================================
    # BAJISTA
    # ========================================================

    if direction == "bearish":

        # Rechazo inferior
        if (
            last["lower_wick_ratio"]
            >= 0.55
        ):

            return True

        # Vela demasiado pequeña
        if (
            last["body_ratio"]
            < 0.20
        ):

            return True

        # Dos velas débiles
        if (
            previous["body_ratio"]
            < 0.25
            and
            last["body_ratio"]
            < 0.25
        ):

            return True

        # Pérdida de estructura
        if (
            last["close"]
            > previous["high"]
        ):

            return True

    return False


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def check_support_resistance(
    df,
    direction
):

    if len(df) < SR_LOOKBACK:

        return {
            "blocked": False,
            "reason": "Datos insuficientes"
        }

    atr_series = calculate_atr(
        df
    )

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "blocked": True,
            "reason": "ATR inválido"
        }

    current_price = safe_float(
        df.iloc[-1]["close"]
    )

    # --------------------------------------------------------
    # IMPORTANTE:
    # No utilizamos la vela de confirmación para crear
    # artificialmente un nivel extremo de soporte/resistencia.
    # --------------------------------------------------------

    historical = df.iloc[
        :-1
    ].tail(
        SR_LOOKBACK
    )

    if historical.empty:

        return {
            "blocked": False,
            "reason": "Sin niveles suficientes"
        }

    resistance = safe_float(
        historical["high"].max()
    )

    support = safe_float(
        historical["low"].min()
    )

    tolerance = (
        atr * SR_TOLERANCE_ATR
    )

    near_resistance = (
        abs(
            resistance
            - current_price
        )
        <= tolerance
    )

    near_support = (
        abs(
            current_price
            - support
        )
        <= tolerance
    )

    # ========================================================
    # CALL
    # ========================================================

    if direction == "bullish":

        if near_resistance:

            return {
                "blocked": True,
                "reason":
                    "CALL bloqueado: zona de resistencia"
            }

    # ========================================================
    # PUT
    # ========================================================

    if direction == "bearish":

        if near_support:

            return {
                "blocked": True,
                "reason":
                    "PUT bloqueado: zona de soporte"
            }

    return {
        "blocked": False,
        "reason": "Ubicación válida"
    }


# ============================================================
# SCORE DE VELA DE CONFIRMACIÓN
#
# MÁXIMO 5 PUNTOS
#
# 1. Dirección
# 2. Cuerpo
# 3. Cierre
# 4. Mecha
# 5. Movimiento
# ============================================================

def confirmation_score(
    df,
    direction
):

    if len(df) < 2:

        return {
            "score": 0,
            "valid": False,
            "reason": "Sin vela de confirmación"
        }

    confirmation = df.iloc[-1]

    candle = get_candle_data(
        confirmation
    )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    atr_series = calculate_atr(
        df
    )

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "score": 0,
            "valid": False,
            "reason": "ATR inválido"
        }

    range_atr = (
        candle["range"]
        / atr
    )

    body_atr = (
        candle["body"]
        / atr
    )

    score = 0

    reasons = []

    # ========================================================
    # CALL
    # ========================================================

    if direction == "bullish":

        # ----------------------------------------------------
        # 1. Cierre alcista
        # ----------------------------------------------------

        if (
            candle["close"]
            > candle["open"]
        ):

            score += 1

        else:

            reasons.append(
                "La vela no cerró alcista"
            )

        # ----------------------------------------------------
        # 2. Cuerpo adecuado
        # ----------------------------------------------------

        if (
            candle["body_ratio"]
            >= 0.35
        ):

            score += 1

        else:

            reasons.append(
                "Cuerpo insuficiente"
            )

        # ----------------------------------------------------
        # 3. Cierre cerca de máximos
        # ----------------------------------------------------

        close_position = 0

        if candle["range"] > 0:

            close_position = (
                (
                    candle["close"]
                    - candle["low"]
                )
                / candle["range"]
            )

        if close_position >= 0.65:

            score += 1

        else:

            reasons.append(
                "Cierre no suficientemente alto"
            )

        # ----------------------------------------------------
        # 4. Mecha superior controlada
        # ----------------------------------------------------

        if (
            candle["upper_wick_ratio"]
            <= 0.45
        ):

            score += 1

        else:

            reasons.append(
                "Rechazo superior"
            )

        # ----------------------------------------------------
        # 5. Movimiento controlado
        # ----------------------------------------------------

        if (
            range_atr
            <= MAX_CONFIRMATION_RANGE_ATR
            and
            body_atr
            <= MAX_CONFIRMATION_BODY_ATR
        ):

            score += 1

        else:

            reasons.append(
                "Movimiento excesivamente fuerte"
            )

    # ========================================================
    # PUT
    # ========================================================

    elif direction == "bearish":

        # ----------------------------------------------------
        # 1. Cierre bajista
        # ----------------------------------------------------

        if (
            candle["close"]
            < candle["open"]
        ):

            score += 1

        else:

            reasons.append(
                "La vela no cerró bajista"
            )

        # ----------------------------------------------------
        # 2. Cuerpo adecuado
        # ----------------------------------------------------

        if (
            candle["body_ratio"]
            >= 0.35
        ):

            score += 1

        else:

            reasons.append(
                "Cuerpo insuficiente"
            )

        # ----------------------------------------------------
        # 3. Cierre cerca de mínimos
        # ----------------------------------------------------

        close_position = 0

        if candle["range"] > 0:

            close_position = (
                (
                    candle["high"]
                    - candle["close"]
                )
                / candle["range"]
            )

        if close_position >= 0.65:

            score += 1

        else:

            reasons.append(
                "Cierre no suficientemente bajo"
            )

        # ----------------------------------------------------
        # 4. Mecha inferior controlada
        # ----------------------------------------------------

        if (
            candle["lower_wick_ratio"]
            <= 0.45
        ):

            score += 1

        else:

            reasons.append(
                "Rechazo inferior"
            )

        # ----------------------------------------------------
        # 5. Movimiento controlado
        # ----------------------------------------------------

        if (
            range_atr
            <= MAX_CONFIRMATION_RANGE_ATR
            and
            body_atr
            <= MAX_CONFIRMATION_BODY_ATR
        ):

            score += 1

        else:

            reasons.append(
                "Movimiento excesivamente fuerte"
            )

    else:

        return {
            "score": 0,
            "valid": False,
            "reason": "Dirección inválida"
        }

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    valid = (
        score >= 4
    )

    if reasons:

        reason = " | ".join(
            reasons
        )

    else:

        reason = (
            "Confirmación completa"
        )

    return {
        "score": score,
        "valid": valid,
        "reason": reason,
        "range_atr": range_atr,
        "body_atr": body_atr
    }


# ============================================================
# ANALIZAR MOVIMIENTO COMPLETO DE LA VELA
# ============================================================

def analyze_confirmation_movement(
    df,
    direction
):

    if len(df) < 2:

        return {
            "valid": False,
            "reason": "Sin datos"
        }

    candle = df.iloc[-1]

    data = get_candle_data(
        candle
    )

    atr_series = calculate_atr(
        df
    )

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "valid": False,
            "reason": "ATR inválido"
        }

    range_atr = (
        data["range"]
        / atr
    )

    body_atr = (
        data["body"]
        / atr
    )

    # --------------------------------------------------------
    # Movimiento excesivo
    # --------------------------------------------------------

    if (
        range_atr
        > MAX_CONFIRMATION_RANGE_ATR
    ):

        return {
            "valid": False,
            "reason":
                "La vela tuvo un movimiento excesivamente fuerte"
        }

    if (
        body_atr
        > MAX_CONFIRMATION_BODY_ATR
    ):

        return {
            "valid": False,
            "reason":
                "El cuerpo de la vela fue excesivamente fuerte"
        }

    # --------------------------------------------------------
    # Rechazo
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            data["upper_wick_ratio"]
            > 0.45
        ):

            return {
                "valid": False,
                "reason":
                    "La vela terminó con rechazo superior"
            }

    if direction == "bearish":

        if (
            data["lower_wick_ratio"]
            > 0.45
        ):

            return {
                "valid": False,
                "reason":
                    "La vela terminó con rechazo inferior"
            }

    return {
        "valid": True,
        "reason":
            "Movimiento de confirmación controlado",
        "range_atr": range_atr,
        "body_atr": body_atr
    }


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(df):

    # ========================================================
    # RESPUESTA ESTÁNDAR
    # ========================================================

    result = {
        "signal": None,

        "direction": "range",

        "reason": "Sin señal",

        "score": 0,

        "structure_score": 0,

        "confirmation_score": 0,

        "final_score": 0
    }

    # ========================================================
    # PREPARAR DATOS
    # ========================================================

    data = prepare_dataframe(
        df
    )

    if data is None:

        result["reason"] = (
            "Datos insuficientes"
        )

        return result

    # ========================================================
    # ESTRUCTURA
    # ========================================================

    structure = analyze_structure(
        data
    )

    direction = structure[
        "direction"
    ]

    structure_score = structure[
        "score"
    ]

    result["direction"] = direction

    result["structure_score"] = (
        structure_score
    )

    result["score"] = (
        structure_score
    )

    # ========================================================
    # SIN TENDENCIA CLARA
    # ========================================================

    if direction == "range":

        result["reason"] = (
            "No existe una tendencia clara"
        )

        return result

    # ========================================================
    # ESTRUCTURA INSUFICIENTE
    # ========================================================

    if (
        structure_score
        < MIN_STRUCTURE_SCORE
    ):

        result["reason"] = (
            "Estructura insuficiente"
        )

        return result

    # ========================================================
    # CONTINUIDAD
    # ========================================================

    if not check_continuity(
        data,
        direction
    ):

        result["reason"] = (
            "No existe continuidad"
        )

        return result

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    if detect_end_of_trend(
        data,
        direction
    ):

        result["reason"] = (
            "Posible final de tendencia o agotamiento"
        )

        return result

    # ========================================================
    # SOPORTE / RESISTENCIA
    # ========================================================

    sr = check_support_resistance(
        data,
        direction
    )

    if sr["blocked"]:

        result["reason"] = (
            sr["reason"]
        )

        return result

    # ========================================================
    # MOVIMIENTO DE LA VELA
    # ========================================================

    movement = (
        analyze_confirmation_movement(
            data,
            direction
        )
    )

    if not movement["valid"]:

        result["reason"] = (
            movement["reason"]
        )

        return result

    # ========================================================
    # SCORE DE CONFIRMACIÓN
    # ========================================================

    confirmation = (
        confirmation_score(
            data,
            direction
        )
    )

    confirmation_score_value = (
        confirmation["score"]
    )

    result["confirmation_score"] = (
        confirmation_score_value
    )

    # ========================================================
    # SCORE FINAL
    # ========================================================

    final_score = (
        structure_score
        + confirmation_score_value
    )

    result["final_score"] = (
        final_score
    )

    result["score"] = (
        final_score
    )

    # ========================================================
    # CONFIRMACIÓN INSUFICIENTE
    # ========================================================

    if not confirmation["valid"]:

        result["reason"] = (
            "Vela de confirmación insuficiente | "
            + confirmation["reason"]
        )

        return result

    # ========================================================
    # SCORE FINAL INSUFICIENTE
    # ========================================================

    if final_score < MIN_FINAL_SCORE:

        result["reason"] = (
            "Score final insuficiente: "
            + str(final_score)
            + "/10"
        )

        return result

    # ========================================================
    # SEÑAL CALL
    # ========================================================

    if direction == "bullish":

        result["signal"] = "call"

        result["reason"] = (
            "CONTINUIDAD CALL CONFIRMADA | "
            "Estructura "
            + str(structure_score)
            + "/5 | "
            "Confirmación "
            + str(confirmation_score_value)
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            "Sin rechazo | "
            "Sin soporte/resistencia | "
            "Sin agotamiento | "
            "Movimiento controlado"
        )

        return result

    # ========================================================
    # SEÑAL PUT
    # ========================================================

    if direction == "bearish":

        result["signal"] = "put"

        result["reason"] = (
            "CONTINUIDAD PUT CONFIRMADA | "
            "Estructura "
            + str(structure_score)
            + "/5 | "
            "Confirmación "
            + str(confirmation_score_value)
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            "Sin rechazo | "
            "Sin soporte/resistencia | "
            "Sin agotamiento | "
            "Movimiento controlado"
        )

        return result

    # ========================================================
    # SEGURIDAD
    # ========================================================

    result["signal"] = None

    result["reason"] = (
        "Sin señal válida"
    )

    return result


# ============================================================
# FIN DE strategy.py
# ============================================================
