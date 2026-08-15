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
# CONFIGURACIÓN DE LECTURA INTRAVELA
# ============================================================

MIN_INTRABAR_SNAPSHOTS = 3

MIN_INTRABAR_SCORE = 3

PRESSURE_RATIO_MIN = 0.55

MAX_INTRABAR_CONTRADICTIONS = 3


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

    if df is None or len(df) < period:

        return pd.Series(
            index=df.index if df is not None else [],
            dtype=float
        )

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

    return true_range.rolling(
        period
    ).mean()


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

    candle_range = max(
        0.0,
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
# DIRECCIÓN DE VELA
# ============================================================

def candle_direction(candle):

    if candle["close"] > candle["open"]:
        return "bullish"

    if candle["close"] < candle["open"]:
        return "bearish"

    return "neutral"


# ============================================================
# ESTRUCTURA
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
            "price_change": 0.0
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

    first_close = closes[0]

    last_close = closes[-1]

    price_change = (
        last_close - first_close
    )

    bullish_score = 0

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

    if bullish_moves >= 3:
        bullish_score += 1

    bullish_candles = 0

    for _, candle in candles.iterrows():

        if (
            candle["close"]
            > candle["open"]
        ):

            bullish_candles += 1

    if bullish_candles >= 8:
        bullish_score += 1

    bearish_score = 0

    if bearish_lh >= 7:
        bearish_score += 1

    if bearish_ll >= 7:
        bearish_score += 1

    if price_change < 0:
        bearish_score += 1

    if bearish_moves >= 3:
        bearish_score += 1

    bearish_candles = 0

    for _, candle in candles.iterrows():

        if (
            candle["close"]
            < candle["open"]
        ):

            bearish_candles += 1

    if bearish_candles >= 8:
        bearish_score += 1

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

        return (
            higher_highs >= 3
            and
            higher_lows >= 3
            and
            closes[-1] > closes[0]
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

        return (
            lower_highs >= 3
            and
            lower_lows >= 3
            and
            closes[-1] < closes[0]
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

    if direction == "bearish":

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

    atr_series = calculate_atr(
        df
    )

    if atr_series.empty:
        return {
            "blocked": True,
            "reason": "ATR inválido"
        }

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

    if direction == "bullish":

        if near_resistance:

            return {
                "blocked": True,
                "reason":
                    "CALL bloqueado: zona de resistencia"
            }

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
# LECTURA DEL RECORRIDO INTRAVELA
# ============================================================

def analyze_intrabar_confirmation(
    confirmation_candle,
    snapshots,
    direction
):
    """
    Analiza TODO el recorrido registrado de la vela
    de confirmación.

    La vela se observa mientras está viva.

    snapshots contiene lecturas realizadas por bot.py.
    """

    result = {
        "valid": False,
        "score": 0,
        "reason": "Sin datos intravela",
        "bullish_pressure": 0,
        "bearish_pressure": 0,
        "contradictions": 0,
        "snapshots": 0
    }

    if confirmation_candle is None:
        return result

    if not snapshots:
        return result

    if len(snapshots) < MIN_INTRABAR_SNAPSHOTS:

        result["reason"] = (
            "Recorrido intravela insuficiente"
        )

        return result

    result["snapshots"] = len(
        snapshots
    )

    candle = get_candle_data(
        confirmation_candle
    )

    open_price = candle["open"]
    close_price = candle["close"]

    final_high = candle["high"]
    final_low = candle["low"]

    total_range = max(
        final_high - final_low,
        0.0
    )

    bullish_pressure = 0
    bearish_pressure = 0
    contradictions = 0

    previous_price = None
    previous_high = None
    previous_low = None

    for snapshot in snapshots:

        price = safe_float(
            snapshot.get("price")
        )

        high = safe_float(
            snapshot.get("high")
        )

        low = safe_float(
            snapshot.get("low")
        )

        if price <= 0:
            continue

        # ----------------------------------------------------
        # Movimiento respecto a apertura
        # ----------------------------------------------------

        if price > open_price:
            bullish_pressure += 1

        elif price < open_price:
            bearish_pressure += 1

        # ----------------------------------------------------
        # Movimiento secuencial
        # ----------------------------------------------------

        if previous_price is not None:

            if price > previous_price:
                bullish_pressure += 1

            elif price < previous_price:
                bearish_pressure += 1

        # ----------------------------------------------------
        # Expansión de máximo
        # ----------------------------------------------------

        if (
            previous_high is not None
            and
            high > previous_high
        ):

            bullish_pressure += 1

        # ----------------------------------------------------
        # Expansión de mínimo
        # ----------------------------------------------------

        if (
            previous_low is not None
            and
            low < previous_low
        ):

            bearish_pressure += 1

        previous_price = price
        previous_high = high
        previous_low = low

    # ========================================================
    # PRESIÓN FINAL
    # ========================================================

    if (
        bullish_pressure
        > bearish_pressure
    ):

        dominant_pressure = "bullish"

    elif (
        bearish_pressure
        > bullish_pressure
    ):

        dominant_pressure = "bearish"

    else:

        dominant_pressure = "neutral"

    result["bullish_pressure"] = (
        bullish_pressure
    )

    result["bearish_pressure"] = (
        bearish_pressure
    )

    # ========================================================
    # COMPARAR CON EL CIERRE
    # ========================================================

    final_direction = candle_direction(
        confirmation_candle
    )

    if (
        dominant_pressure != "neutral"
        and
        final_direction != "neutral"
        and
        dominant_pressure != final_direction
    ):

        contradictions += 1

    # ========================================================
    # DETECTAR RECHAZO FINAL
    # ========================================================

    rejection = False

    if direction == "bullish":

        if candle["upper_wick_ratio"] > 0.45:
            rejection = True

    elif direction == "bearish":

        if candle["lower_wick_ratio"] > 0.45:
            rejection = True

    # ========================================================
    # UBICACIÓN DEL CIERRE
    # ========================================================

    close_position = 0.5

    if total_range > 0:

        if direction == "bullish":

            close_position = (
                close_price
                - final_low
            ) / total_range

        elif direction == "bearish":

            close_position = (
                final_high
                - close_price
            ) / total_range

    # ========================================================
    # SCORE
    # ========================================================

    score = 0
    reasons = []

    # --------------------------------------------------------
    # 1. Dominio intravela
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            bullish_pressure
            > bearish_pressure
        ):

            score += 1
            reasons.append(
                "dominio comprador"
            )

        else:

            reasons.append(
                "sin dominio comprador"
            )

    elif direction == "bearish":

        if (
            bearish_pressure
            > bullish_pressure
        ):

            score += 1
            reasons.append(
                "dominio vendedor"
            )

        else:

            reasons.append(
                "sin dominio vendedor"
            )

    # --------------------------------------------------------
    # 2. Cierre compatible
    # --------------------------------------------------------

    if direction == "bullish":

        if close_price > open_price:

            score += 1
            reasons.append(
                "cierre alcista"
            )

        else:

            reasons.append(
                "cierre no alcista"
            )

    elif direction == "bearish":

        if close_price < open_price:

            score += 1
            reasons.append(
                "cierre bajista"
            )

        else:

            reasons.append(
                "cierre no bajista"
            )

    # --------------------------------------------------------
    # 3. Cierre en zona favorable
    # --------------------------------------------------------

    if close_position >= 0.65:

        score += 1
        reasons.append(
            "cierre favorable"
        )

    else:

        reasons.append(
            "cierre alejado del extremo"
        )

    # --------------------------------------------------------
    # 4. Sin contradicción importante
    # --------------------------------------------------------

    if contradictions <= MAX_INTRABAR_CONTRADICTIONS:

        score += 1

    else:

        reasons.append(
            "contradicción intravela"
        )

    # --------------------------------------------------------
    # 5. Sin rechazo
    # --------------------------------------------------------

    if not rejection:

        score += 1

    else:

        reasons.append(
            "rechazo final"
        )

    result["contradictions"] = contradictions
    result["score"] = score

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    if score < MIN_INTRABAR_SCORE:

        result["reason"] = (
            "Recorrido intravela insuficiente | "
            + " | ".join(reasons)
        )

        return result

    if rejection:

        result["reason"] = (
            "Rechazo al final de la vela"
        )

        return result

    if (
        direction == "bullish"
        and
        bullish_pressure <= bearish_pressure
    ):

        result["reason"] = (
            "Compradores no dominaron el recorrido"
        )

        return result

    if (
        direction == "bearish"
        and
        bearish_pressure <= bullish_pressure
    ):

        result["reason"] = (
            "Vendedores no dominaron el recorrido"
        )

        return result

    result["valid"] = True

    result["reason"] = (
        "Recorrido intravela confirmado | "
        + " | ".join(reasons)
    )

    return result


# ============================================================
# SCORE DE VELA DE CONFIRMACIÓN
# ============================================================

def confirmation_score(
    df,
    direction
):

    if len(df) < 2:

        return {
            "score": 0,
            "valid": False,
            "reason":
                "Sin vela de confirmación"
        }

    confirmation = df.iloc[-1]

    candle = get_candle_data(
        confirmation
    )

    atr_series = calculate_atr(
        df
    )

    if atr_series.empty:

        return {
            "score": 0,
            "valid": False,
            "reason": "ATR inválido"
        }

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

    if direction == "bullish":

        if candle["close"] > candle["open"]:

            score += 1

        else:

            reasons.append(
                "La vela no cerró alcista"
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
                "Cierre no suficientemente alto"
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
                "Movimiento excesivamente fuerte"
            )

    elif direction == "bearish":

        if candle["close"] < candle["open"]:

            score += 1

        else:

            reasons.append(
                "La vela no cerró bajista"
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
                "Cierre no suficientemente bajo"
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
                "Movimiento excesivamente fuerte"
            )

    else:

        return {
            "score": 0,
            "valid": False,
            "reason": "Dirección inválida"
        }

    valid = score >= 4

    reason = (
        " | ".join(reasons)
        if reasons
        else
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
# MOVIMIENTO DE CONFIRMACIÓN
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

    if atr_series.empty:

        return {
            "valid": False,
            "reason": "ATR inválido"
        }

    atr = safe_float(
        atr_series.iloc[-1]
    )

    if atr <= 0:

        return {
            "valid": False,
            "reason": "ATR inválido"
        }

    range_atr = (
        data["range"] / atr
    )

    body_atr = (
        data["body"] / atr
    )

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

    if direction == "bullish":

        if data["upper_wick_ratio"] > 0.45:

            return {
                "valid": False,
                "reason":
                    "La vela terminó con rechazo superior"
            }

    if direction == "bearish":

        if data["lower_wick_ratio"] > 0.45:

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

def analyze_market(
    df,
    intrabar_snapshots=None
):
    """
    Analiza exclusivamente velas cerradas.

    intrabar_snapshots:
        Recorrido de la vela de confirmación
        registrado por bot.py mientras estaba viva.
    """

    result = {

        "signal": None,

        "direction": "range",

        "reason": "Sin señal",

        "score": 0,

        "structure_score": 0,

        "confirmation_score": 0,

        "intrabar_score": 0,

        "final_score": 0
    }

    data = prepare_dataframe(
        df
    )

    if data is None:

        result["reason"] = (
            "Datos insuficientes"
        )

        return result

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

    result["score"] = structure_score

    if direction == "range":

        result["reason"] = (
            "No existe una tendencia clara"
        )

        return result

    if structure_score < MIN_STRUCTURE_SCORE:

        result["reason"] = (
            "Estructura insuficiente"
        )

        return result

    if not check_continuity(
        data,
        direction
    ):

        result["reason"] = (
            "No existe continuidad"
        )

        return result

    if detect_end_of_trend(
        data,
        direction
    ):

        result["reason"] = (
            "Posible final de tendencia o agotamiento"
        )

        return result

    sr = check_support_resistance(
        data,
        direction
    )

    if sr["blocked"]:

        result["reason"] = sr["reason"]

        return result

    movement = (
        analyze_confirmation_movement(
            data,
            direction
        )
    )

    if not movement["valid"]:

        result["reason"] = movement["reason"]

        return result

    # ========================================================
    # LECTURA INTRAVELA
    # ========================================================

    confirmation_candle = data.iloc[-1]

    intrabar = (
        analyze_intrabar_confirmation(
            confirmation_candle,
            intrabar_snapshots,
            direction
        )
    )

    result["intrabar_score"] = (
        intrabar["score"]
    )

    if not intrabar["valid"]:

        result["reason"] = (
            "Recorrido intravela no confirmado | "
            + intrabar["reason"]
        )

        return result

    # ========================================================
    # CONFIRMACIÓN FINAL
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

    if not confirmation["valid"]:

        result["reason"] = (
            "Vela de confirmación insuficiente | "
            + confirmation["reason"]
        )

        return result

    # ========================================================
    # SCORE FINAL
    #
    # Estructura       5
    # Confirmación     5
    # Intrabar         filtro adicional
    # ========================================================

    final_score = (
        structure_score
        + confirmation_score_value
    )

    result["final_score"] = final_score

    result["score"] = final_score

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
            "CONTINUIDAD CALL CONFIRMADA | "
            "Estructura "
            + str(structure_score)
            + "/5 | "
            "Confirmación "
            + str(confirmation_score_value)
            + "/5 | "
            "Intrabar "
            + str(intrabar["score"])
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            + intrabar["reason"]
        )

        return result

    # ========================================================
    # PUT
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
            "Intrabar "
            + str(intrabar["score"])
            + "/5 | "
            "FINAL "
            + str(final_score)
            + "/10 | "
            + intrabar["reason"]
        )

        return result

    return result


# ============================================================
# FIN strategy.py
# ============================================================
