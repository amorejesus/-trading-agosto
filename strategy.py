import time
import math
import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN
# ============================================================

LOOKBACK_TREND = 15

ATR_PERIOD = 14

EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 50

SR_LOOKBACK = 20

# Cuánto debe acercarse el precio a máximo/mínimo
# reciente para considerarlo zona peligrosa.
SR_ATR_MULTIPLIER = 0.35

# Máximo porcentaje del ATR que puede medir
# una vela de confirmación.
#
# Si supera este valor, se considera movimiento
# demasiado fuerte y no se entra.
MAX_CONFIRMATION_ATR = 1.35

# Una vela extremadamente pequeña tampoco
# sirve como confirmación.
MIN_BODY_ATR = 0.08

# Porcentaje mínimo del cuerpo respecto al rango.
MIN_BODY_RATIO = 0.25

# Número mínimo de relaciones estructurales
# necesarias para considerar tendencia clara.
MIN_STRUCTURE_POINTS = 3

# Permite que haya retrocesos normales.
MAX_COUNTER_CANDLES = 4


# ============================================================
# UTILIDADES
# ============================================================

def safe_float(value, default=0.0):

    try:

        value = float(value)

        if not math.isfinite(value):
            return default

        return value

    except Exception:

        return default


# ============================================================
# VALIDAR DATAFRAME
# ============================================================

def validate_dataframe(df):

    if df is None:
        return False

    if not isinstance(df, pd.DataFrame):
        return False

    if df.empty:
        return False

    required = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        if column not in df.columns:
            return False

    return True


# ============================================================
# NORMALIZAR DATAFRAME
# ============================================================

def normalize_dataframe(df):

    if not validate_dataframe(df):
        return None

    data = df.copy()

    required = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        data[column] = pd.to_numeric(
            data[column],
            errors="coerce"
        )

    data.dropna(
        subset=required,
        inplace=True
    )

    if "from" in data.columns:

        data["from"] = pd.to_numeric(
            data["from"],
            errors="coerce"
        )

        data.dropna(
            subset=["from"],
            inplace=True
        )

        data.sort_values(
            "from",
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
    # EMA 9
    # --------------------------------------------------------

    data["ema9"] = (
        data["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # EMA 21
    # --------------------------------------------------------

    data["ema21"] = (
        data["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # EMA 50
    # --------------------------------------------------------

    data["ema50"] = (
        data["close"]
        .ewm(
            span=EMA_TREND,
            adjust=False
        )
        .mean()
    )

    # --------------------------------------------------------
    # TRUE RANGE
    # --------------------------------------------------------

    previous_close = (
        data["close"]
        .shift(1)
    )

    tr1 = (
        data["high"]
        - data["low"]
    )

    tr2 = (
        data["high"]
        - previous_close
    ).abs()

    tr3 = (
        data["low"]
        - previous_close
    ).abs()

    data["tr"] = pd.concat(
        [
            tr1,
            tr2,
            tr3
        ],
        axis=1
    ).max(axis=1)

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    data["atr"] = (
        data["tr"]
        .rolling(
            ATR_PERIOD
        )
        .mean()
    )

    return data


# ============================================================
# DETECTAR SI LA ÚLTIMA VELA ESTÁ CERRADA
# ============================================================

def get_closed_dataframe(df):

    data = df.copy()

    if (
        "from" not in data.columns
        or len(data) < 2
    ):

        return data.iloc[:-1].copy()

    now = time.time()

    last_timestamp = safe_float(
        data.iloc[-1]["from"],
        0
    )

    # --------------------------------------------------------
    # Si la última vela todavía está viva,
    # NO se utiliza para confirmar.
    # --------------------------------------------------------

    if (
        last_timestamp > 0
        and now < last_timestamp + 60
    ):

        return data.iloc[:-1].copy()

    return data.copy()


# ============================================================
# DIRECCIÓN DE VELA
# ============================================================

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
# INFORMACIÓN DE VELA
# ============================================================

def candle_info(candle):

    open_price = safe_float(
        candle["open"]
    )

    close_price = safe_float(
        candle["close"]
    )

    high = safe_float(
        candle["high"]
    )

    low = safe_float(
        candle["low"]
    )

    body = abs(
        close_price - open_price
    )

    range_size = max(
        high - low,
        0
    )

    upper_wick = max(
        high - max(
            open_price,
            close_price
        ),
        0
    )

    lower_wick = max(
        min(
            open_price,
            close_price
        ) - low,
        0
    )

    return {
        "direction": candle_direction(candle),
        "body": body,
        "range": range_size,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick
    }


# ============================================================
# PIVOTES
# ============================================================

def find_pivots(df, window=2):

    highs = []
    lows = []

    if len(df) < (
        window * 2 + 1
    ):

        return highs, lows

    for i in range(
        window,
        len(df) - window
    ):

        current_high = safe_float(
            df.iloc[i]["high"]
        )

        current_low = safe_float(
            df.iloc[i]["low"]
        )

        left_highs = [
            safe_float(
                df.iloc[j]["high"]
            )
            for j in range(
                i - window,
                i
            )
        ]

        right_highs = [
            safe_float(
                df.iloc[j]["high"]
            )
            for j in range(
                i + 1,
                i + window + 1
            )
        ]

        left_lows = [
            safe_float(
                df.iloc[j]["low"]
            )
            for j in range(
                i - window,
                i
            )
        ]

        right_lows = [
            safe_float(
                df.iloc[j]["low"]
            )
            for j in range(
                i + 1,
                i + window + 1
            )
        ]

        if (
            current_high >= max(left_highs)
            and current_high >= max(right_highs)
        ):

            highs.append(
                (
                    i,
                    current_high
                )
            )

        if (
            current_low <= min(left_lows)
            and current_low <= min(right_lows)
        ):

            lows.append(
                (
                    i,
                    current_low
                )
            )

    return highs, lows


# ============================================================
# ESTRUCTURA ALCISTA
# ============================================================

def bullish_structure(df):

    highs, lows = find_pivots(
        df,
        window=2
    )

    hh_count = 0
    hl_count = 0

    # --------------------------------------------------------
    # MÁXIMOS CRECIENTES
    # --------------------------------------------------------

    if len(highs) >= 2:

        for i in range(
            1,
            len(highs)
        ):

            previous = highs[i - 1][1]
            current = highs[i][1]

            if current > previous:
                hh_count += 1

    # --------------------------------------------------------
    # MÍNIMOS CRECIENTES
    # --------------------------------------------------------

    if len(lows) >= 2:

        for i in range(
            1,
            len(lows)
        ):

            previous = lows[i - 1][1]
            current = lows[i][1]

            if current > previous:
                hl_count += 1

    score = (
        hh_count
        + hl_count
    )

    bullish = (
        hh_count >= 1
        and hl_count >= 1
        and score >= MIN_STRUCTURE_POINTS
    )

    return {
        "bullish": bullish,
        "hh": hh_count,
        "hl": hl_count,
        "score": score,
        "highs": highs,
        "lows": lows
    }


# ============================================================
# ESTRUCTURA BAJISTA
# ============================================================

def bearish_structure(df):

    highs, lows = find_pivots(
        df,
        window=2
    )

    lh_count = 0
    ll_count = 0

    # --------------------------------------------------------
    # MÁXIMOS DECRECIENTES
    # --------------------------------------------------------

    if len(highs) >= 2:

        for i in range(
            1,
            len(highs)
        ):

            previous = highs[i - 1][1]
            current = highs[i][1]

            if current < previous:
                lh_count += 1

    # --------------------------------------------------------
    # MÍNIMOS DECRECIENTES
    # --------------------------------------------------------

    if len(lows) >= 2:

        for i in range(
            1,
            len(lows)
        ):

            previous = lows[i - 1][1]
            current = lows[i][1]

            if current < previous:
                ll_count += 1

    score = (
        lh_count
        + ll_count
    )

    bearish = (
        lh_count >= 1
        and ll_count >= 1
        and score >= MIN_STRUCTURE_POINTS
    )

    return {
        "bearish": bearish,
        "lh": lh_count,
        "ll": ll_count,
        "score": score,
        "highs": highs,
        "lows": lows
    }


# ============================================================
# DETECTAR ESTRUCTURA PRINCIPAL
# ============================================================

def detect_structure(df):

    if len(df) < 8:

        return {
            "direction": "range",
            "score": 0,
            "reason": "Pocas velas"
        }

    bullish = bullish_structure(
        df
    )

    bearish = bearish_structure(
        df
    )

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if (
        bullish["bullish"]
        and bullish["score"]
        > bearish["score"]
    ):

        return {
            "direction": "bullish",
            "score": bullish["score"],
            "hh": bullish["hh"],
            "hl": bullish["hl"],
            "lh": bearish["lh"],
            "ll": bearish["ll"],
            "reason": (
                "HH/HL detectados"
            )
        }

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if (
        bearish["bearish"]
        and bearish["score"]
        > bullish["score"]
    ):

        return {
            "direction": "bearish",
            "score": bearish["score"],
            "hh": bullish["hh"],
            "hl": bullish["hl"],
            "lh": bearish["lh"],
            "ll": bearish["ll"],
            "reason": (
                "LH/LL detectados"
            )
        }

    return {
        "direction": "range",
        "score": max(
            bullish["score"],
            bearish["score"]
        ),
        "hh": bullish["hh"],
        "hl": bullish["hl"],
        "lh": bearish["lh"],
        "ll": bearish["ll"],
        "reason": (
            "Estructura insuficiente"
        )
    }


# ============================================================
# CONTAR RETROCESOS
# ============================================================

def count_counter_candles(
    df,
    direction
):

    count = 0

    recent = df.tail(
        6
    )

    for _, candle in recent.iterrows():

        candle_dir = candle_direction(
            candle
        )

        if direction == "bullish":

            if candle_dir == "bear":
                count += 1

        elif direction == "bearish":

            if candle_dir == "bull":
                count += 1

    return count


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def is_end_of_trend(
    df,
    direction
):

    if len(df) < 6:
        return False

    recent = df.tail(
        5
    )

    directions = [
        candle_direction(
            row
        )
        for _, row in recent.iterrows()
    ]

    counter = 0

    if direction == "bullish":

        for d in directions:

            if d == "bear":
                counter += 1

    elif direction == "bearish":

        for d in directions:

            if d == "bull":
                counter += 1

    # --------------------------------------------------------
    # Varias velas consecutivas contra tendencia
    # pueden indicar pérdida de continuidad.
    # --------------------------------------------------------

    if counter >= 3:

        return True

    return False


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def get_support_resistance(
    df,
    lookback=SR_LOOKBACK
):

    recent = df.tail(
        lookback
    )

    support = safe_float(
        recent["low"].min()
    )

    resistance = safe_float(
        recent["high"].max()
    )

    return support, resistance


# ============================================================
# CERCA DE SOPORTE / RESISTENCIA
# ============================================================

def is_near_sr(
    df,
    price=None
):

    if len(df) < 5:
        return False, None

    if price is None:

        price = safe_float(
            df.iloc[-1]["close"]
        )

    support, resistance = (
        get_support_resistance(df)
    )

    atr = safe_float(
        df.iloc[-1].get(
            "atr",
            0
        )
    )

    if atr <= 0:

        ranges = (
            df["high"]
            - df["low"]
        )

        atr = safe_float(
            ranges.tail(
                ATR_PERIOD
            ).mean()
        )

    if atr <= 0:
        return False, None

    tolerance = (
        atr
        * SR_ATR_MULTIPLIER
    )

    distance_support = abs(
        price - support
    )

    distance_resistance = abs(
        resistance - price
    )

    if (
        distance_resistance
        <= tolerance
    ):

        return True, "resistance"

    if (
        distance_support
        <= tolerance
    ):

        return True, "support"

    return False, None


# ============================================================
# FILTRO DE EMA
# ============================================================

def ema_trend_filter(
    df,
    direction
):

    if len(df) < EMA_TREND:

        return False

    row = df.iloc[-1]

    close = safe_float(
        row["close"]
    )

    ema9 = safe_float(
        row["ema9"]
    )

    ema21 = safe_float(
        row["ema21"]
    )

    ema50 = safe_float(
        row["ema50"]
    )

    if direction == "bullish":

        return (
            close > ema21
            and ema9 >= ema21
            and ema21 >= ema50
        )

    if direction == "bearish":

        return (
            close < ema21
            and ema9 <= ema21
            and ema21 <= ema50
        )

    return False


# ============================================================
# ANALIZAR MOVIMIENTO COMPLETO DE LA VELA
# ============================================================

def analyze_confirmation_candle(
    candle,
    atr,
    direction
):

    info = candle_info(
        candle
    )

    body = info["body"]
    range_size = info["range"]

    if atr <= 0:

        return {
            "valid": False,
            "reason": "ATR inválido"
        }

    # --------------------------------------------------------
    # MOVIMIENTO DEMASIADO FUERTE
    # --------------------------------------------------------

    if (
        range_size
        > atr * MAX_CONFIRMATION_ATR
    ):

        return {
            "valid": False,
            "reason": (
                "Movimiento demasiado fuerte"
            )
        }

    # --------------------------------------------------------
    # VELA DEMASIADO PEQUEÑA
    # --------------------------------------------------------

    if (
        body
        < atr * MIN_BODY_ATR
    ):

        return {
            "valid": False,
            "reason": (
                "Cuerpo demasiado pequeño"
            )
        }

    # --------------------------------------------------------
    # CUERPO / RANGO
    # --------------------------------------------------------

    if range_size <= 0:

        return {
            "valid": False,
            "reason": "Rango inválido"
        }

    body_ratio = (
        body
        / range_size
    )

    if body_ratio < MIN_BODY_RATIO:

        return {
            "valid": False,
            "reason": (
                "Demasiada indecisión"
            )
        }

    candle_dir = info[
        "direction"
    ]

    # --------------------------------------------------------
    # CONFIRMACIÓN ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        if candle_dir != "bull":

            return {
                "valid": False,
                "reason": (
                    "La confirmación no cerró alcista"
                )
            }

        # Rechazo superior excesivo
        if (
            info["upper_wick"]
            > body * 1.5
        ):

            return {
                "valid": False,
                "reason": (
                    "Rechazo superior"
                )
            }

        return {
            "valid": True,
            "reason": (
                "Confirmación CALL válida"
            )
        }

    # --------------------------------------------------------
    # CONFIRMACIÓN BAJISTA
    # --------------------------------------------------------

    if direction == "bearish":

        if candle_dir != "bear":

            return {
                "valid": False,
                "reason": (
                    "La confirmación no cerró bajista"
                )
            }

        # Rechazo inferior excesivo
        if (
            info["lower_wick"]
            > body * 1.5
        ):

            return {
                "valid": False,
                "reason": (
                    "Rechazo inferior"
                )
            }

        return {
            "valid": True,
            "reason": (
                "Confirmación PUT válida"
            )
        }

    return {
        "valid": False,
        "reason": "Sin dirección"
    }


# ============================================================
# COMPROBAR CONTINUIDAD DE ESTRUCTURA
# ============================================================

def continuity_confirmed(
    df,
    direction
):

    if len(df) < 6:
        return False, "Pocas velas"

    recent = df.tail(
        5
    )

    if direction == "bullish":

        highs = (
            recent["high"]
            .astype(float)
            .tolist()
        )

        lows = (
            recent["low"]
            .astype(float)
            .tolist()
        )

        higher_highs = 0
        higher_lows = 0

        for i in range(
            1,
            len(highs)
        ):

            if highs[i] > highs[i - 1]:
                higher_highs += 1

            if lows[i] > lows[i - 1]:
                higher_lows += 1

        if (
            higher_highs >= 2
            and higher_lows >= 2
        ):

            return (
                True,
                "Continuidad alcista"
            )

    if direction == "bearish":

        highs = (
            recent["high"]
            .astype(float)
            .tolist()
        )

        lows = (
            recent["low"]
            .astype(float)
            .tolist()
        )

        lower_highs = 0
        lower_lows = 0

        for i in range(
            1,
            len(highs)
        ):

            if highs[i] < highs[i - 1]:
                lower_highs += 1

            if lows[i] < lows[i - 1]:
                lower_lows += 1

        if (
            lower_highs >= 2
            and lower_lows >= 2
        ):

            return (
                True,
                "Continuidad bajista"
            )

    return (
        False,
        "Continuidad insuficiente"
    )


# ============================================================
# FUERZA DE LA ÚLTIMA VELA
# ============================================================

def movement_strength(
    candle,
    atr
):

    info = candle_info(
        candle
    )

    if atr <= 0:

        return 0.0

    return (
        info["range"]
        / atr
    )


# ============================================================
# SCORE
# ============================================================

def calculate_score(
    structure,
    direction,
    ema_ok,
    continuity_ok,
    confirmation_ok,
    sr_blocked,
    end_trend
):

    score = 0

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    if direction == "bullish":

        score += min(
            structure.get(
                "hh",
                0
            ) * 1.5,
            3
        )

        score += min(
            structure.get(
                "hl",
                0
            ) * 1.5,
            3
        )

    elif direction == "bearish":

        score += min(
            structure.get(
                "lh",
                0
            ) * 1.5,
            3
        )

        score += min(
            structure.get(
                "ll",
                0
            ) * 1.5,
            3
        )

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    if ema_ok:
        score += 2

    if continuity_ok:
        score += 2

    if confirmation_ok:
        score += 2

    if sr_blocked:
        score -= 5

    if end_trend:
        score -= 5

    return round(
        score,
        2
    )


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def analyze_market(df):

    # ========================================================
    # RESULTADO BASE
    # ========================================================

    result = {
        "signal": None,
        "direction": "range",
        "score": 0,
        "reason": "Sin análisis",
        "trend": "range",
        "structure_score": 0,
        "confirmation": False,
        "near_sr": False,
        "sr_zone": None,
        "end_of_trend": False,
        "execution_ready": False
    }

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    if not validate_dataframe(df):

        result["reason"] = (
            "DataFrame inválido"
        )

        return result

    # ========================================================
    # NORMALIZAR
    # ========================================================

    data = normalize_dataframe(
        df
    )

    if data is None:

        result["reason"] = (
            "No se pudo normalizar"
        )

        return result

    # ========================================================
    # NECESITAMOS HISTORIAL
    # ========================================================

    if len(data) < 30:

        result["reason"] = (
            "Historial insuficiente"
        )

        return result

    # ========================================================
    # INDICADORES
    # ========================================================

    data = add_indicators(
        data
    )

    # ========================================================
    # SOLO VELAS CERRADAS
    #
    # La vela que todavía está transcurriendo
    # NO puede ser vela de confirmación.
    # ========================================================

    closed = get_closed_dataframe(
        data
    )

    if len(closed) < 20:

        result["reason"] = (
            "Esperando cierre de vela"
        )

        return result

    # ========================================================
    # ÚLTIMAS 15 VELAS PARA ESTRUCTURA
    # ========================================================

    trend_df = closed.tail(
        LOOKBACK_TREND
    ).copy()

    # ========================================================
    # ESTRUCTURA
    # ========================================================

    structure = detect_structure(
        trend_df
    )

    direction = structure[
        "direction"
    ]

    result[
        "direction"
    ] = direction

    result[
        "trend"
    ] = direction

    result[
        "structure_score"
    ] = structure.get(
        "score",
        0
    )

    # ========================================================
    # NO HAY TENDENCIA
    # ========================================================

    if direction not in (
        "bullish",
        "bearish"
    ):

        result["reason"] = (
            "No existe una tendencia clara"
        )

        return result

    # ========================================================
    # RETROCESOS
    # ========================================================

    counter_candles = (
        count_counter_candles(
            trend_df,
            direction
        )
    )

    if (
        counter_candles
        > MAX_COUNTER_CANDLES
    ):

        result["reason"] = (
            "Demasiado retroceso "
            "contra la tendencia"
        )

        return result

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    end_trend = (
        is_end_of_trend(
            closed,
            direction
        )
    )

    result[
        "end_of_trend"
    ] = end_trend

    if end_trend:

        result["reason"] = (
            "Posible final de tendencia"
        )

        return result

    # ========================================================
    # EMA
    # ========================================================

    ema_ok = (
        ema_trend_filter(
            closed,
            direction
        )
    )

    if not ema_ok:

        result["reason"] = (
            "EMA no confirma tendencia"
        )

        return result

    # ========================================================
    # CONTINUIDAD
    # ========================================================

    continuity_ok, continuity_reason = (
        continuity_confirmed(
            trend_df,
            direction
        )
    )

    if not continuity_ok:

        result["reason"] = (
            continuity_reason
        )

        return result

    # ========================================================
    # VELA DE CONFIRMACIÓN
    #
    # Esta es la ÚLTIMA VELA CERRADA.
    # Se estudia TODO su movimiento:
    #
    # OPEN
    # HIGH
    # LOW
    # CLOSE
    # CUERPO
    # MECHAS
    # RANGO
    # ATR
    # ========================================================

    confirmation_candle = (
        closed.iloc[-1]
    )

    atr = safe_float(
        confirmation_candle.get(
            "atr",
            0
        )
    )

    confirmation = (
        analyze_confirmation_candle(
            confirmation_candle,
            atr,
            direction
        )
    )

    confirmation_ok = (
        confirmation["valid"]
    )

    result[
        "confirmation"
    ] = confirmation_ok

    if not confirmation_ok:

        result["reason"] = (
            confirmation["reason"]
        )

        return result

    # ========================================================
    # FUERZA DEL MOVIMIENTO
    # ========================================================

    strength = (
        movement_strength(
            confirmation_candle,
            atr
        )
    )

    # ========================================================
    # EVITAR MOVIMIENTO DEMASIADO FUERTE
    # ========================================================

    if (
        strength
        > MAX_CONFIRMATION_ATR
    ):

        result["reason"] = (
            "Vela de confirmación "
            "demasiado fuerte"
        )

        return result

    # ========================================================
    # SOPORTE / RESISTENCIA
    #
    # IMPORTANTE:
    # NO operar justo delante de una zona.
    # ========================================================

    price = safe_float(
        confirmation_candle[
            "close"
        ]
    )

    near_sr, sr_zone = (
        is_near_sr(
            closed,
            price
        )
    )

    result[
        "near_sr"
    ] = near_sr

    result[
        "sr_zone"
    ] = sr_zone

    if near_sr:

        result["reason"] = (
            "PRECIO EN "
            + str(sr_zone).upper()
            + " - OPERACIÓN BLOQUEADA"
        )

        return result

    # ========================================================
    # SCORE FINAL
    # ========================================================

    score = calculate_score(
        structure,
        direction,
        ema_ok,
        continuity_ok,
        confirmation_ok,
        near_sr,
        end_trend
    )

    result[
        "score"
    ] = score

    # ========================================================
    # SCORE MÍNIMO
    # ========================================================

    if score < 6:

        result["reason"] = (
            "Score insuficiente"
        )

        return result

    # ========================================================
    # SEÑAL FINAL
    # ========================================================

    if direction == "bullish":

        result["signal"] = "call"

        result["reason"] = (
            "CONTINUIDAD CALL CONFIRMADA"
        )

    elif direction == "bearish":

        result["signal"] = "put"

        result["reason"] = (
            "CONTINUIDAD PUT CONFIRMADA"
        )

    # ========================================================
    # LISTA PARA LA SIGUIENTE VELA
    # ========================================================

    result[
        "execution_ready"
    ] = True

    return result


# ============================================================
# FUNCIÓN DE DEBUG
# ============================================================

def debug_market(df):

    result = analyze_market(
        df
    )

    print(
        "========================================"
    )

    print(
        "ESTRATEGIA"
    )

    print(
        "========================================"
    )

    print(
        "Dirección:",
        result.get(
            "direction"
        )
    )

    print(
        "Tendencia:",
        result.get(
            "trend"
        )
    )

    print(
        "Score estructura:",
        result.get(
            "structure_score"
        )
    )

    print(
        "Score final:",
        result.get(
            "score"
        )
    )

    print(
        "Confirmación:",
        result.get(
            "confirmation"
        )
    )

    print(
        "Zona S/R:",
        result.get(
            "sr_zone"
        )
    )

    print(
        "Final tendencia:",
        result.get(
            "end_of_trend"
        )
    )

    print(
        "Execution ready:",
        result.get(
            "execution_ready"
        )
    )

    print(
        "SEÑAL:",
        result.get(
            "signal"
        )
    )

    print(
        "RAZÓN:",
        result.get(
            "reason"
        )
    )

    print(
        "========================================"
    )

    return result
