import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN DE LA ESTRATEGIA
# ============================================================

MIN_CANDLES = 20

TREND_LOOKBACK = 15

MIN_TREND_SCORE = 5

MAX_CONFIRMATION_RANGE_ATR = 1.60

MAX_CONFIRMATION_BODY_ATR = 1.20

SR_LOOKBACK = 20

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

    if len(data) < MIN_CANDLES:
        return None

    data.reset_index(
        drop=True,
        inplace=True
    )

    return data


# ============================================================
# ATR
# ============================================================

def calculate_atr(df, period=14):

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
# EMA
# ============================================================

def calculate_ema(df, period):

    return df["close"].ewm(
        span=period,
        adjust=False
    ).mean()


# ============================================================
# DATOS DE VELA
# ============================================================

def candle_data(candle):

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
        - max(open_price, close_price)
    )

    lower_wick = (
        min(open_price, close_price)
        - low_price
    )

    if candle_range > 0:

        body_ratio = (
            body / candle_range
        )

        upper_ratio = (
            upper_wick / candle_range
        )

        lower_ratio = (
            lower_wick / candle_range
        )

    else:

        body_ratio = 0

        upper_ratio = 0

        lower_ratio = 0

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
        "upper_ratio": upper_ratio,
        "lower_ratio": lower_ratio
    }


# ============================================================
# DIRECCIÓN DE VELA
# ============================================================

def candle_direction(candle):

    if candle["close"] > candle["open"]:
        return "bull"

    if candle["close"] < candle["open"]:
        return "bear"

    return "neutral"


# ============================================================
# ESTRUCTURA DE 15 VELAS
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

    higher_highs = 0
    higher_lows = 0

    lower_highs = 0
    lower_lows = 0

    for i in range(1, len(candles)):

        if highs[i] > highs[i - 1]:
            higher_highs += 1

        elif highs[i] < highs[i - 1]:
            lower_highs += 1

        if lows[i] > lows[i - 1]:
            higher_lows += 1

        elif lows[i] < lows[i - 1]:
            lower_lows += 1

    # --------------------------------------------------------
    # PENDIENTE DEL PRECIO
    # --------------------------------------------------------

    first_close = closes[0]

    last_close = closes[-1]

    price_change = (
        last_close - first_close
    )

    if first_close != 0:

        percentage_change = (
            price_change
            / first_close
        )

    else:

        percentage_change = 0

    # --------------------------------------------------------
    # SCORE ALCISTA
    # --------------------------------------------------------

    bullish_score = 0

    if higher_highs >= 7:
        bullish_score += 2

    elif higher_highs >= 5:
        bullish_score += 1

    if higher_lows >= 7:
        bullish_score += 2

    elif higher_lows >= 5:
        bullish_score += 1

    if price_change > 0:
        bullish_score += 1

    # --------------------------------------------------------
    # SCORE BAJISTA
    # --------------------------------------------------------

    bearish_score = 0

    if lower_highs >= 7:
        bearish_score += 2

    elif lower_highs >= 5:
        bearish_score += 1

    if lower_lows >= 7:
        bearish_score += 2

    elif lower_lows >= 5:
        bearish_score += 1

    if price_change < 0:
        bearish_score += 1

    # --------------------------------------------------------
    # DETERMINAR DIRECCIÓN
    # --------------------------------------------------------

    if bullish_score >= MIN_TREND_SCORE:

        direction = "bullish"

        score = bullish_score

    elif bearish_score >= MIN_TREND_SCORE:

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
        "higher_highs": higher_highs,
        "higher_lows": higher_lows,
        "lower_highs": lower_highs,
        "lower_lows": lower_lows,
        "price_change": price_change,
        "percentage_change": percentage_change
    }


# ============================================================
# FUERZA GENERAL DE LA TENDENCIA
# ============================================================

def trend_strength(df, direction):

    candles = df.tail(
        TREND_LOOKBACK
    )

    if len(candles) < TREND_LOOKBACK:
        return 0

    bullish = 0

    bearish = 0

    for _, candle in candles.iterrows():

        if candle["close"] > candle["open"]:
            bullish += 1

        elif candle["close"] < candle["open"]:
            bearish += 1

    if direction == "bullish":

        return bullish

    if direction == "bearish":

        return bearish

    return 0


# ============================================================
# CONTINUIDAD DE ESTRUCTURA
# ============================================================

def continuity_check(df, direction):

    if len(df) < 6:
        return False

    recent = df.tail(6)

    highs = recent["high"].to_numpy()

    lows = recent["low"].to_numpy()

    closes = recent["close"].to_numpy()

    if direction == "bullish":

        hh = 0
        hl = 0

        for i in range(1, len(recent)):

            if highs[i] >= highs[i - 1]:
                hh += 1

            if lows[i] >= lows[i - 1]:
                hl += 1

        price_up = (
            closes[-1] > closes[0]
        )

        return (
            hh >= 3
            and hl >= 3
            and price_up
        )

    if direction == "bearish":

        lh = 0
        ll = 0

        for i in range(1, len(recent)):

            if highs[i] <= highs[i - 1]:
                lh += 1

            if lows[i] <= lows[i - 1]:
                ll += 1

        price_down = (
            closes[-1] < closes[0]
        )

        return (
            lh >= 3
            and ll >= 3
            and price_down
        )

    return False


# ============================================================
# ANALIZAR VELA DE CONFIRMACIÓN CERRADA
# ============================================================

def analyze_confirmation_candle(
    df,
    direction
):

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # df contiene velas cerradas entregadas por IQ Option.
    #
    # La última vela se utiliza como confirmación.
    # --------------------------------------------------------

    if len(df) < 16:

        return {
            "valid": False,
            "reason": "No hay suficientes velas"
        }

    confirmation = df.iloc[-1]

    previous = df.iloc[-2]

    data = candle_data(
        confirmation
    )

    previous_data = candle_data(
        previous
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

    # --------------------------------------------------------
    # MOVIMIENTO DE LA VELA
    # --------------------------------------------------------

    range_atr = (
        data["range"] / atr
    )

    body_atr = (
        data["body"] / atr
    )

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    if direction == "bullish":

        correct_direction = (
            data["close"]
            > data["open"]
        )

        good_body = (
            data["body_ratio"]
            >= 0.35
        )

        not_excessive = (
            range_atr
            <= MAX_CONFIRMATION_RANGE_ATR
        )

        body_not_excessive = (
            body_atr
            <= MAX_CONFIRMATION_BODY_ATR
        )

        weak_upper_wick = (
            data["upper_ratio"]
            <= 0.45
        )

        previous_support = (
            previous_data["close"]
            >= previous_data["open"]
            or
            previous_data["close"]
            >= previous_data["low"]
        )

        valid = (
            correct_direction
            and good_body
            and not_excessive
            and body_not_excessive
            and weak_upper_wick
        )

        if not valid:

            return {
                "valid": False,
                "reason":
                    "Confirmación CALL débil o movimiento excesivo",
                "range_atr": range_atr,
                "body_atr": body_atr
            }

        return {
            "valid": True,
            "reason":
                "Vela de confirmación CALL cerrada correctamente",
            "range_atr": range_atr,
            "body_atr": body_atr
        }

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    if direction == "bearish":

        correct_direction = (
            data["close"]
            < data["open"]
        )

        good_body = (
            data["body_ratio"]
            >= 0.35
        )

        not_excessive = (
            range_atr
            <= MAX_CONFIRMATION_RANGE_ATR
        )

        body_not_excessive = (
            body_atr
            <= MAX_CONFIRMATION_BODY_ATR
        )

        weak_lower_wick = (
            data["lower_ratio"]
            <= 0.45
        )

        valid = (
            correct_direction
            and good_body
            and not_excessive
            and body_not_excessive
            and weak_lower_wick
        )

        if not valid:

            return {
                "valid": False,
                "reason":
                    "Confirmación PUT débil o movimiento excesivo",
                "range_atr": range_atr,
                "body_atr": body_atr
            }

        return {
            "valid": True,
            "reason":
                "Vela de confirmación PUT cerrada correctamente",
            "range_atr": range_atr,
            "body_atr": body_atr
        }

    return {
        "valid": False,
        "reason": "Dirección inválida"
    }


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def support_resistance_check(
    df,
    direction
):

    if len(df) < SR_LOOKBACK:

        return {
            "blocked": False,
            "reason": "Sin suficientes datos"
        }

    atr_series = calculate_atr(
        df
    )

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "blocked": False,
            "reason": "ATR inválido"
        }

    current_price = safe_float(
        df.iloc[-1]["close"]
    )

    recent = df.tail(
        SR_LOOKBACK
    )

    resistance = safe_float(
        recent["high"].max()
    )

    support = safe_float(
        recent["low"].min()
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

    # --------------------------------------------------------
    # CALL NO ENTRA EN RESISTENCIA
    # --------------------------------------------------------

    if direction == "bullish":

        if near_resistance:

            return {
                "blocked": True,
                "reason":
                    "Precio demasiado cerca de resistencia"
            }

    # --------------------------------------------------------
    # PUT NO ENTRA EN SOPORTE
    # --------------------------------------------------------

    if direction == "bearish":

        if near_support:

            return {
                "blocked": True,
                "reason":
                    "Precio demasiado cerca de soporte"
            }

    return {
        "blocked": False,
        "reason": "Ubicación válida"
    }


# ============================================================
# DETECTAR FINAL DE TENDENCIA
# ============================================================

def end_of_trend_check(
    df,
    direction
):

    if len(df) < 8:

        return True

    recent = df.tail(8)

    # --------------------------------------------------------
    # CALL
    # --------------------------------------------------------

    if direction == "bullish":

        last = candle_data(
            recent.iloc[-1]
        )

        previous = candle_data(
            recent.iloc[-2]
        )

        # Mecha superior excesiva
        if (
            last["upper_ratio"]
            > 0.55
        ):

            return True

        # Cuerpo demasiado pequeño
        if (
            last["body_ratio"]
            < 0.20
        ):

            return True

        # Dos velas con pérdida de fuerza
        if (
            previous["body_ratio"]
            < 0.25
            and
            last["body_ratio"]
            < 0.25
        ):

            return True

    # --------------------------------------------------------
    # PUT
    # --------------------------------------------------------

    if direction == "bearish":

        last = candle_data(
            recent.iloc[-1]
        )

        previous = candle_data(
            recent.iloc[-2]
        )

        if (
            last["lower_ratio"]
            > 0.55
        ):

            return True

        if (
            last["body_ratio"]
            < 0.20
        ):

            return True

        if (
            previous["body_ratio"]
            < 0.25
            and
            last["body_ratio"]
            < 0.25
        ):

            return True

    return False


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(df):

    # --------------------------------------------------------
    # RESPUESTA ESTÁNDAR
    # --------------------------------------------------------

    result = {
        "signal": None,
        "direction": "range",
        "reason": "Sin señal",
        "score": 0
    }

    # --------------------------------------------------------
    # PREPARAR
    # --------------------------------------------------------

    data = prepare_dataframe(
        df
    )

    if data is None:

        result["reason"] = (
            "Datos insuficientes"
        )

        return result

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    structure = analyze_structure(
        data
    )

    direction = structure[
        "direction"
    ]

    score = structure[
        "score"
    ]

    result["direction"] = direction

    result["score"] = score

    # --------------------------------------------------------
    # SIN TENDENCIA CLARA
    # --------------------------------------------------------

    if direction == "range":

        result["reason"] = (
            "No existe una tendencia clara"
        )

        return result

    # --------------------------------------------------------
    # SCORE MÍNIMO
    # --------------------------------------------------------

    if score < MIN_TREND_SCORE:

        result["reason"] = (
            "Tendencia insuficiente"
        )

        return result

    # --------------------------------------------------------
    # CONTINUIDAD
    # --------------------------------------------------------

    continuity = continuity_check(
        data,
        direction
    )

    if not continuity:

        result["reason"] = (
            "No existe continuidad estructural"
        )

        return result

    # --------------------------------------------------------
    # FINAL DE TENDENCIA
    # --------------------------------------------------------

    if end_of_trend_check(
        data,
        direction
    ):

        result["reason"] = (
            "Final de tendencia / pérdida de fuerza"
        )

        return result

    # --------------------------------------------------------
    # SOPORTE / RESISTENCIA
    # --------------------------------------------------------

    sr = support_resistance_check(
        data,
        direction
    )

    if sr["blocked"]:

        result["reason"] = (
            sr["reason"]
        )

        return result

    # --------------------------------------------------------
    # VELA DE CONFIRMACIÓN CERRADA
    # --------------------------------------------------------

    confirmation = (
        analyze_confirmation_candle(
            data,
            direction
        )
    )

    if not confirmation["valid"]:

        result["reason"] = (
            confirmation["reason"]
        )

        return result

    # --------------------------------------------------------
    # SEÑAL FINAL
    # --------------------------------------------------------

    if direction == "bullish":

        result["signal"] = "call"

        result["reason"] = (
            "CONTINUIDAD CALL CONFIRMADA | "
            "15 velas con estructura alcista | "
            "vela de confirmación cerrada | "
            "movimiento no excesivo | "
            "ubicación válida"
        )

        return result

    if direction == "bearish":

        result["signal"] = "put"

        result["reason"] = (
            "CONTINUIDAD PUT CONFIRMADA | "
            "15 velas con estructura bajista | "
            "vela de confirmación cerrada | "
            "movimiento no excesivo | "
            "ubicación válida"
        )

        return result

    return result
