import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN
# ============================================================

TREND_LOOKBACK = 15

MIN_STRUCTURE_SCORE = 5

MIN_FINAL_SCORE = 8

CONTINUITY_LOOKBACK = 6

EXHAUSTION_LOOKBACK = 8

SR_LOOKBACK = 20

ATR_PERIOD = 14

MAX_CONFIRMATION_RANGE_ATR = 1.60

MAX_CONFIRMATION_BODY_ATR = 1.20

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
# DATOS DE VELA
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

    upper_wick = max(
        0.0,
        high_price
        - max(
            open_price,
            close_price
        )
    )

    lower_wick = max(
        0.0,
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
# DIRECCIÓN
# ============================================================

def candle_direction(candle):

    if candle["close"] > candle["open"]:
        return "bullish"

    if candle["close"] < candle["open"]:
        return "bearish"

    return "neutral"


# ============================================================
# ANÁLISIS DE ESTRUCTURA
# ============================================================

def analyze_structure(df):

    candles = df.tail(
        TREND_LOOKBACK
    ).copy()

    if len(candles) < TREND_LOOKBACK:

        return {
            "direction": "range",
            "score": 0,
            "bullish_score": 0,
            "bearish_score": 0,
            "higher_highs": 0,
            "higher_lows": 0,
            "lower_highs": 0,
            "lower_lows": 0,
            "price_change": 0
        }

    highs = candles["high"].to_numpy()

    lows = candles["low"].to_numpy()

    closes = candles["close"].to_numpy()

    bullish_hh = 0
    bullish_hl = 0

    bearish_lh = 0
    bearish_ll = 0

    for i in range(1, len(candles)):

        if highs[i] > highs[i - 1]:

            bullish_hh += 1

        elif highs[i] < highs[i - 1]:

            bearish_lh += 1

        if lows[i] > lows[i - 1]:

            bullish_hl += 1

        elif lows[i] < lows[i - 1]:

            bearish_ll += 1

    first_close = closes[0]

    last_close = closes[-1]

    price_change = (
        last_close - first_close
    )

    bullish_score = 0

    bearish_score = 0

    if bullish_hh >= 7:
        bullish_score += 1

    if bullish_hl >= 7:
        bullish_score += 1

    if price_change > 0:
        bullish_score += 1

    recent = candles.tail(
        CONTINUITY_LOOKBACK
    )

    recent_closes = (
        recent["close"].to_numpy()
    )

    bullish_moves = 0
    bearish_moves = 0

    for i in range(1, len(recent_closes)):

        if recent_closes[i] > recent_closes[i - 1]:

            bullish_moves += 1

        elif recent_closes[i] < recent_closes[i - 1]:

            bearish_moves += 1

    if bullish_moves >= 3:
        bullish_score += 1

    bullish_candles = 0
    bearish_candles = 0

    for _, candle in candles.iterrows():

        if candle["close"] > candle["open"]:

            bullish_candles += 1

        elif candle["close"] < candle["open"]:

            bearish_candles += 1

    if bullish_candles >= 8:
        bullish_score += 1

    if bearish_lh >= 7:
        bearish_score += 1

    if bearish_ll >= 7:
        bearish_score += 1

    if price_change < 0:
        bearish_score += 1

    if bearish_moves >= 3:
        bearish_score += 1

    if bearish_candles >= 8:
        bearish_score += 1

    if (
        bullish_score >= MIN_STRUCTURE_SCORE
        and bullish_score > bearish_score
    ):

        direction = "bullish"
        score = bullish_score

    elif (
        bearish_score >= MIN_STRUCTURE_SCORE
        and bearish_score > bullish_score
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
# CONTINUIDAD
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

    highs = recent["high"].to_numpy()

    lows = recent["low"].to_numpy()

    closes = recent["close"].to_numpy()

    if direction == "bullish":

        higher_highs = 0
        higher_lows = 0

        for i in range(1, len(recent)):

            if highs[i] >= highs[i - 1]:
                higher_highs += 1

            if lows[i] >= lows[i - 1]:
                higher_lows += 1

        return (
            higher_highs >= 3
            and higher_lows >= 3
            and closes[-1] > closes[0]
        )

    if direction == "bearish":

        lower_highs = 0
        lower_lows = 0

        for i in range(1, len(recent)):

            if highs[i] <= highs[i - 1]:
                lower_highs += 1

            if lows[i] <= lows[i - 1]:
                lower_lows += 1

        return (
            lower_highs >= 3
            and lower_lows >= 3
            and closes[-1] < closes[0]
        )

    return False


# ============================================================
# AGOTAMIENTO
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

    if direction == "bullish":

        if last["upper_wick_ratio"] >= 0.55:
            return True

        if last["body_ratio"] < 0.20:
            return True

        if (
            previous["body_ratio"] < 0.25
            and
            last["body_ratio"] < 0.25
        ):
            return True

        if last["close"] < previous["low"]:
            return True

    elif direction == "bearish":

        if last["lower_wick_ratio"] >= 0.55:
            return True

        if last["body_ratio"] < 0.20:
            return True

        if (
            previous["body_ratio"] < 0.25
            and
            last["body_ratio"] < 0.25
        ):
            return True

        if last["close"] > previous["high"]:
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

    atr_series = calculate_atr(df)

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

    historical = df.iloc[:-1].tail(
        SR_LOOKBACK
    )

    if historical.empty:

        return {
            "blocked": False,
            "reason": "Sin niveles"
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
            resistance - current_price
        )
        <= tolerance
    )

    near_support = (
        abs(
            current_price - support
        )
        <= tolerance
    )

    if direction == "bullish" and near_resistance:

        return {
            "blocked": True,
            "reason":
                "CALL bloqueado: resistencia"
        }

    if direction == "bearish" and near_support:

        return {
            "blocked": True,
            "reason":
                "PUT bloqueado: soporte"
        }

    return {
        "blocked": False,
        "reason": "Ubicación válida"
    }


# ============================================================
# ANÁLISIS DE LA VELA DE CONFIRMACIÓN
#
# MUY IMPORTANTE:
#
# Esta función analiza la vela COMPLETA:
#
# OPEN
#   ↓
# MOVIMIENTO
#   ↓
# HIGH / LOW
#   ↓
# CUERPO
#   ↓
# CIERRE
#
# Esa vela define la siguiente.
# ============================================================

def confirmation_score(
    df,
    direction
):

    if len(df) < 2:

        return {
            "score": 0,
            "valid": False,
            "reason": "Sin confirmación"
        }

    confirmation = df.iloc[-1]

    candle = get_candle_data(
        confirmation
    )

    atr_series = calculate_atr(df)

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
        candle["range"] / atr
    )

    body_atr = (
        candle["body"] / atr
    )

    score = 0

    reasons = []

    # ========================================================
    # CALL
    # ========================================================

    if direction == "bullish":

        if candle["close"] > candle["open"]:

            score += 1

        else:

            reasons.append(
                "Cierre no alcista"
            )

        if candle["body_ratio"] >= 0.35:

            score += 1

        else:

            reasons.append(
                "Cuerpo insuficiente"
            )

        close_position = 0

        if candle["range"] > 0:

            close_position = (
                candle["close"]
                - candle["low"]
            ) / candle["range"]

        if close_position >= 0.65:

            score += 1

        else:

            reasons.append(
                "Cierre lejos del máximo"
            )

        if candle["upper_wick_ratio"] <= 0.45:

            score += 1

        else:

            reasons.append(
                "Rechazo superior"
            )

        if (
            range_atr <= MAX_CONFIRMATION_RANGE_ATR
            and
            body_atr <= MAX_CONFIRMATION_BODY_ATR
        ):

            score += 1

        else:

            reasons.append(
                "Movimiento excesivo"
            )

    # ========================================================
    # PUT
    # ========================================================

    elif direction == "bearish":

        if candle["close"] < candle["open"]:

            score += 1

        else:

            reasons.append(
                "Cierre no bajista"
            )

        if candle["body_ratio"] >= 0.35:

            score += 1

        else:

            reasons.append(
                "Cuerpo insuficiente"
            )

        close_position = 0

        if candle["range"] > 0:

            close_position = (
                candle["high"]
                - candle["close"]
            ) / candle["range"]

        if close_position >= 0.65:

            score += 1

        else:

            reasons.append(
                "Cierre lejos del mínimo"
            )

        if candle["lower_wick_ratio"] <= 0.45:

            score += 1

        else:

            reasons.append(
                "Rechazo inferior"
            )

        if (
            range_atr <= MAX_CONFIRMATION_RANGE_ATR
            and
            body_atr <= MAX_CONFIRMATION_BODY_ATR
        ):

            score += 1

        else:

            reasons.append(
                "Movimiento excesivo"
            )

    else:

        return {
            "score": 0,
            "valid": False,
            "reason": "Dirección inválida"
        }

    valid = score >= 4

    if reasons:

        reason = " | ".join(reasons)

    else:

        reason = "Confirmación completa"

    return {
        "score": score,
        "valid": valid,
        "reason": reason,
        "range_atr": range_atr,
        "body_atr": body_atr
    }


# ============================================================
# ANALIZAR MOVIMIENTO COMPLETO
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

    candle = get_candle_data(
        df.iloc[-1]
    )

    atr_series = calculate_atr(df)

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "valid": False,
            "reason": "ATR inválido"
        }

    range_atr = (
        candle["range"] / atr
    )

    body_atr = (
        candle["body"] / atr
    )

    if range_atr > MAX_CONFIRMATION_RANGE_ATR:

        return {
            "valid": False,
            "reason":
                "Movimiento de confirmación excesivo"
        }

    if body_atr > MAX_CONFIRMATION_BODY_ATR:

        return {
            "valid": False,
            "reason":
                "Cuerpo de confirmación excesivo"
        }

    if direction == "bullish":

        if candle["upper_wick_ratio"] > 0.45:

            return {
                "valid": False,
                "reason":
                    "Rechazo superior en confirmación"
            }

    if direction == "bearish":

        if candle["lower_wick_ratio"] > 0.45:

            return {
                "valid": False,
                "reason":
                    "Rechazo inferior en confirmación"
            }

    return {
        "valid": True,
        "reason":
            "Movimiento completo controlado",
        "range_atr": range_atr,
        "body_atr": body_atr
    }


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(df):

    result = {

        "signal": None,

        "direction": "range",

        "reason": "Sin señal",

        "score": 0,

        "structure_score": 0,

        "confirmation_score": 0,

        "final_score": 0
    }

    data = prepare_dataframe(df)

    if data is None:

        result["reason"] = (
            "Datos insuficientes"
        )

        return result

    # ========================================================
    # ESTRUCTURA
    # ========================================================

    structure = analyze_structure(data)

    direction = structure["direction"]

    structure_score = structure["score"]

    result["direction"] = direction

    result["structure_score"] = structure_score

    result["score"] = structure_score

    if direction == "range":

        result["reason"] = (
            "No existe tendencia clara"
        )

        return result

    if structure_score < MIN_STRUCTURE_SCORE:

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
    # AGOTAMIENTO
    # ========================================================

    if detect_end_of_trend(
        data,
        direction
    ):

        result["reason"] = (
            "Posible agotamiento"
        )

        return result

    # ========================================================
    # UBICACIÓN
    # ========================================================

    sr = check_support_resistance(
        data,
        direction
    )

    if sr["blocked"]:

        result["reason"] = sr["reason"]

        return result

    # ========================================================
    # MOVIMIENTO COMPLETO DE CONFIRMACIÓN
    # ========================================================

    movement = analyze_confirmation_movement(
        data,
        direction
    )

    if not movement["valid"]:

        result["reason"] = movement["reason"]

        return result

    # ========================================================
    # SCORE DE CONFIRMACIÓN
    # ========================================================

    confirmation = confirmation_score(
        data,
        direction
    )

    confirmation_value = (
        confirmation["score"]
    )

    result["confirmation_score"] = (
        confirmation_value
    )

    # ========================================================
    # SCORE FINAL
    # ========================================================

    final_score = (
        structure_score
        + confirmation_value
    )

    result["final_score"] = final_score

    result["score"] = final_score

    if not confirmation["valid"]:

        result["reason"] = (
            "Confirmación insuficiente | "
            + confirmation["reason"]
        )

        return result

    if final_score < MIN_FINAL_SCORE:

        result["reason"] = (
            "Score final insuficiente: "
            + str(final_score)
            + "/10"
        )

        return result

    # ========================================================
    # CALL
    # ========================================================

    if direction == "bullish":

        result["signal"] = "call"

        result["reason"] = (
            "CONTINUIDAD CALL | "
            "VELA COMPLETA CONFIRMADA | "
            "Estructura "
            + str(structure_score)
            + "/5 | "
            "Confirmación "
            + str(confirmation_value)
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            "Movimiento controlado"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    if direction == "bearish":

        result["signal"] = "put"

        result["reason"] = (
            "CONTINUIDAD PUT | "
            "VELA COMPLETA CONFIRMADA | "
            "Estructura "
            + str(structure_score)
            + "/5 | "
            "Confirmación "
            + str(confirmation_value)
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            "Movimiento controlado"
        )

        return result

    return result
