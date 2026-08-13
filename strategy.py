import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN
# ============================================================

MAX_CANDLES = 60

EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50

ATR_PERIOD = 14

# Porcentaje máximo de extensión respecto al rango reciente
MAX_EXTENSION = 0.78

# Proximidad a extremos recientes
SR_LOOKBACK = 60

# Número máximo de velas consecutivas fuertes antes de
# considerar que la tendencia puede estar demasiado extendida
MAX_CONSECUTIVE = 6


# ============================================================
# NORMALIZAR DATAFRAME
# ============================================================

def normalize_dataframe(df):
    """
    Normaliza las columnas recibidas desde IQ Option.
    """

    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return None

    if df.empty:
        return None

    data = df.copy()

    rename = {
        "max": "high",
        "min": "low"
    }

    data.rename(
        columns=rename,
        inplace=True
    )

    required = [
        "open",
        "close",
        "high",
        "low"
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

    if data.empty:
        return None

    if "from" in data.columns:

        data["from"] = pd.to_numeric(
            data["from"],
            errors="coerce"
        )

        data.sort_values(
            "from",
            inplace=True
        )

    data.reset_index(
        drop=True,
        inplace=True
    )

    # --------------------------------------------------------
    # MÁXIMO 60 VELAS
    # --------------------------------------------------------

    data = data.tail(
        MAX_CANDLES
    ).copy()

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
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    data["ema21"] = (
        data["close"]
        .ewm(
            span=EMA_MID,
            adjust=False
        )
        .mean()
    )

    data["ema50"] = (
        data["close"]
        .ewm(
            span=EMA_SLOW,
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

    # --------------------------------------------------------
    # CUERPO
    # --------------------------------------------------------

    data["body"] = (
        data["close"]
        - data["open"]
    ).abs()

    # --------------------------------------------------------
    # RANGO
    # --------------------------------------------------------

    data["range"] = (
        data["high"]
        - data["low"]
    )

    # --------------------------------------------------------
    # MECHAS
    # --------------------------------------------------------

    data["upper_wick"] = (
        data["high"]
        - data[
            ["open", "close"]
        ].max(axis=1)
    )

    data["lower_wick"] = (
        data[
            ["open", "close"]
        ].min(axis=1)
        - data["low"]
    )

    # --------------------------------------------------------
    # FUERZA DEL CUERPO
    # --------------------------------------------------------

    data["body_ratio"] = np.where(
        data["range"] > 0,
        data["body"] / data["range"],
        0
    )

    return data


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
# TENDENCIA
# ============================================================

def detect_trend(df):

    if len(df) < 50:
        return "range"

    last = df.iloc[-1]

    ema9 = last["ema9"]
    ema21 = last["ema21"]
    ema50 = last["ema50"]

    close = last["close"]

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if (
        close > ema9
        and ema9 > ema21
        and ema21 > ema50
    ):
        return "bullish"

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if (
        close < ema9
        and ema9 < ema21
        and ema21 < ema50
    ):
        return "bearish"

    return "range"


# ============================================================
# ESTRUCTURA
# ============================================================

def detect_structure(df):

    if len(df) < 10:
        return "range"

    recent = df.tail(10)

    highs = recent["high"].values
    lows = recent["low"].values

    bullish_points = 0
    bearish_points = 0

    for i in range(1, len(highs)):

        if highs[i] > highs[i - 1]:
            bullish_points += 1

        if lows[i] > lows[i - 1]:
            bullish_points += 1

        if highs[i] < highs[i - 1]:
            bearish_points += 1

        if lows[i] < lows[i - 1]:
            bearish_points += 1

    if bullish_points >= 10:
        return "bullish"

    if bearish_points >= 10:
        return "bearish"

    return "range"


# ============================================================
# FUERZA DE TENDENCIA
# ============================================================

def trend_strength(df, direction):

    recent = df.tail(8)

    if direction == "bullish":

        bullish = 0

        for _, candle in recent.iterrows():

            if candle["close"] > candle["open"]:
                bullish += 1

        return bullish / len(recent)

    if direction == "bearish":

        bearish = 0

        for _, candle in recent.iterrows():

            if candle["close"] < candle["open"]:
                bearish += 1

        return bearish / len(recent)

    return 0


# ============================================================
# DETECTAR DEBILIDAD
# ============================================================

def has_weakness(df, direction):

    if len(df) < 6:
        return True

    recent = df.tail(6)

    # --------------------------------------------------------
    # CUERPOS
    # --------------------------------------------------------

    bodies = recent["body"].values

    avg_body = np.mean(bodies)

    if avg_body <= 0:
        return True

    # --------------------------------------------------------
    # CUERPO DE LA ÚLTIMA VELA
    # --------------------------------------------------------

    last = recent.iloc[-1]

    # Una vela demasiado pequeña = pérdida de fuerza
    if last["body"] < avg_body * 0.45:
        return True

    # --------------------------------------------------------
    # MECHAS CONTRARIAS
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            last["upper_wick"]
            > last["body"] * 1.25
        ):
            return True

    if direction == "bearish":

        if (
            last["lower_wick"]
            > last["body"] * 1.25
        ):
            return True

    # --------------------------------------------------------
    # TRES VELAS DE PÉRDIDA
    # --------------------------------------------------------

    if direction == "bullish":

        last_three = recent.tail(3)

        if all(
            last_three["body"].iloc[i]
            < last_three["body"].iloc[i - 1]
            for i in range(1, 3)
        ):
            return True

    if direction == "bearish":

        last_three = recent.tail(3)

        if all(
            last_three["body"].iloc[i]
            < last_three["body"].iloc[i - 1]
            for i in range(1, 3)
        ):
            return True

    return False


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def is_end_of_trend(df, direction):

    if len(df) < 15:
        return True

    recent = df.tail(15)

    # --------------------------------------------------------
    # DEMASIADAS VELAS CONSECUTIVAS
    # --------------------------------------------------------

    consecutive = 0

    for _, candle in reversed(
        list(recent.iterrows())
    ):

        if direction == "bullish":

            if candle["close"] > candle["open"]:
                consecutive += 1
            else:
                break

        elif direction == "bearish":

            if candle["close"] < candle["open"]:
                consecutive += 1
            else:
                break

    if consecutive >= MAX_CONSECUTIVE:
        return True

    # --------------------------------------------------------
    # CUERPOS REDUCIÉNDOSE
    # --------------------------------------------------------

    last_five = recent.tail(5)

    bodies = last_five["body"].values

    decreasing = 0

    for i in range(1, len(bodies)):

        if bodies[i] < bodies[i - 1]:
            decreasing += 1

    if decreasing >= 3:
        return True

    # --------------------------------------------------------
    # DISTANCIA A EMA9
    # --------------------------------------------------------

    last = df.iloc[-1]

    atr = last["atr"]

    if pd.isna(atr) or atr <= 0:
        return True

    distance = abs(
        last["close"]
        - last["ema9"]
    )

    # Precio demasiado alejado de EMA9
    if distance > atr * 2.0:
        return True

    # --------------------------------------------------------
    # MECHA DE RECHAZO CONTRARIA
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            last["upper_wick"]
            > last["body"] * 1.5
        ):
            return True

    if direction == "bearish":

        if (
            last["lower_wick"]
            > last["body"] * 1.5
        ):
            return True

    return False


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def is_near_support_resistance(
    df,
    direction
):

    if len(df) < 20:
        return True

    current = df.iloc[-1]

    price = current["close"]

    # --------------------------------------------------------
    # RANGO DE LAS ÚLTIMAS 60
    # --------------------------------------------------------

    lookback = df.tail(
        SR_LOOKBACK
    )

    highest = lookback["high"].max()
    lowest = lookback["low"].min()

    total_range = (
        highest - lowest
    )

    if total_range <= 0:
        return True

    # --------------------------------------------------------
    # DISTANCIA NORMALIZADA
    # --------------------------------------------------------

    distance_high = (
        highest - price
    )

    distance_low = (
        price - lowest
    )

    # --------------------------------------------------------
    # NO COMPRAR CERCA DE RESISTENCIA
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            distance_high
            <= total_range * 0.15
        ):
            return True

    # --------------------------------------------------------
    # NO VENDER CERCA DE SOPORTE
    # --------------------------------------------------------

    if direction == "bearish":

        if (
            distance_low
            <= total_range * 0.15
        ):
            return True

    return False


# ============================================================
# EXTENSIÓN DEL MOVIMIENTO
# ============================================================

def is_overextended(df, direction):

    if len(df) < 20:
        return True

    recent = df.tail(20)

    highest = recent["high"].max()
    lowest = recent["low"].min()

    current = recent.iloc[-1]["close"]

    total_range = (
        highest - lowest
    )

    if total_range <= 0:
        return True

    if direction == "bullish":

        position = (
            current - lowest
        ) / total_range

        if position >= MAX_EXTENSION:
            return True

    if direction == "bearish":

        position = (
            highest - current
        ) / total_range

        if position >= MAX_EXTENSION:
            return True

    return False


# ============================================================
# RECHAZO
# ============================================================

def has_rejection(df, direction):

    if len(df) < 5:
        return True

    recent = df.tail(5)

    for _, candle in recent.iterrows():

        body = candle["body"]

        if body <= 0:
            continue

        if direction == "bullish":

            # Rechazo fuerte desde arriba
            if (
                candle["upper_wick"]
                > body * 1.8
            ):
                return True

        if direction == "bearish":

            # Rechazo fuerte desde abajo
            if (
                candle["lower_wick"]
                > body * 1.8
            ):
                return True

    return False


# ============================================================
# PULLBACK
# ============================================================

def is_pullback(df, direction):

    if len(df) < 6:
        return True

    recent = df.tail(6)

    last = recent.iloc[-1]

    if direction == "bullish":

        # Si la última vela es bajista,
        # no se considera continuidad limpia.
        if last["close"] < last["open"]:

            return True

        # Precio debajo de EMA9
        if last["close"] < last["ema9"]:

            return True

    if direction == "bearish":

        if last["close"] > last["open"]:

            return True

        if last["close"] > last["ema9"]:

            return True

    return False


# ============================================================
# CONTINUIDAD
# ============================================================

def is_continuation(df, direction):

    if len(df) < 8:
        return False

    recent = df.tail(8)

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        bullish_count = sum(
            1
            for _, candle
            in recent.iterrows()
            if candle["close"]
            > candle["open"]
        )

        if bullish_count < 5:
            return False

        last = recent.iloc[-1]

        if last["close"] <= last["ema9"]:
            return False

        if last["ema9"] <= last["ema21"]:
            return False

        # Máximos y mínimos recientes
        highs = recent["high"].values
        lows = recent["low"].values

        higher_highs = sum(
            highs[i] > highs[i - 1]
            for i in range(1, len(highs))
        )

        higher_lows = sum(
            lows[i] > lows[i - 1]
            for i in range(1, len(lows))
        )

        if higher_highs < 4:
            return False

        if higher_lows < 4:
            return False

        return True

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    if direction == "bearish":

        bearish_count = sum(
            1
            for _, candle
            in recent.iterrows()
            if candle["close"]
            < candle["open"]
        )

        if bearish_count < 5:
            return False

        last = recent.iloc[-1]

        if last["close"] >= last["ema9"]:
            return False

        if last["ema9"] >= last["ema21"]:
            return False

        highs = recent["high"].values
        lows = recent["low"].values

        lower_highs = sum(
            highs[i] < highs[i - 1]
            for i in range(1, len(highs))
        )

        lower_lows = sum(
            lows[i] < lows[i - 1]
            for i in range(1, len(lows))
        )

        if lower_highs < 4:
            return False

        if lower_lows < 4:
            return False

        return True

    return False


# ============================================================
# SCORE DE CONTINUIDAD
# ============================================================

def continuity_score(
    df,
    direction
):

    score = 0

    # --------------------------------------------------------
    # TENDENCIA
    # --------------------------------------------------------

    trend = detect_trend(df)

    if (
        direction == "bullish"
        and trend == "bullish"
    ):
        score += 2

    elif (
        direction == "bearish"
        and trend == "bearish"
    ):
        score += 2

    else:
        return 0

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    structure = detect_structure(df)

    if structure == direction:
        score += 2

    # --------------------------------------------------------
    # FUERZA
    # --------------------------------------------------------

    strength = trend_strength(
        df,
        direction
    )

    if strength >= 0.625:
        score += 1

    if strength >= 0.75:
        score += 1

    # --------------------------------------------------------
    # CONTINUIDAD
    # --------------------------------------------------------

    if is_continuation(
        df,
        direction
    ):
        score += 2

    return score


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(df):

    """
    FUNCIÓN PRINCIPAL.

    Devuelve SIEMPRE:

    {
        "signal": "call" / "put" / None,
        "direction": "bullish" / "bearish" / "range",
        "reason": "...",
        "score": int
    }
    """

    # --------------------------------------------------------
    # VALORES POR DEFECTO
    # --------------------------------------------------------

    result = {
        "signal": None,
        "direction": "range",
        "reason": "Sin datos suficientes",
        "score": 0
    }

    # --------------------------------------------------------
    # NORMALIZAR
    # --------------------------------------------------------

    data = normalize_dataframe(df)

    if data is None:

        result["reason"] = (
            "Datos inválidos"
        )

        return result

    # --------------------------------------------------------
    # NECESITAMOS 50+ PARA EMA50
    # --------------------------------------------------------

    if len(data) < 50:

        result["reason"] = (
            f"Esperando estructura: "
            f"{len(data)}/50 velas"
        )

        return result

    # --------------------------------------------------------
    # INDICADORES
    # --------------------------------------------------------

    data = add_indicators(
        data
    )

    # --------------------------------------------------------
    # ÚLTIMA VELA
    # --------------------------------------------------------

    last = data.iloc[-1]

    if (
        pd.isna(last["ema50"])
        or pd.isna(last["atr"])
    ):

        result["reason"] = (
            "Indicadores incompletos"
        )

        return result

    # --------------------------------------------------------
    # TENDENCIA
    # --------------------------------------------------------

    trend = detect_trend(
        data
    )

    result["direction"] = trend

    if trend == "range":

        result["reason"] = (
            "No existe tendencia clara"
        )

        return result

    # ========================================================
    # DETERMINAR DIRECCIÓN
    # ========================================================

    if trend == "bullish":

        direction = "bullish"
        signal = "call"

    elif trend == "bearish":

        direction = "bearish"
        signal = "put"

    else:

        result["reason"] = (
            "Mercado sin dirección"
        )

        return result

    # ========================================================
    # FILTRO 1 — FINAL DE TENDENCIA
    # ========================================================

    if is_end_of_trend(
        data,
        direction
    ):

        result["reason"] = (
            "Final de tendencia / "
            "movimiento demasiado extendido"
        )

        return result

    # ========================================================
    # FILTRO 2 — DEBILIDAD
    # ========================================================

    if has_weakness(
        data,
        direction
    ):

        result["reason"] = (
            "Debilidad detectada"
        )

        return result

    # ========================================================
    # FILTRO 3 — RECHAZO
    # ========================================================

    if has_rejection(
        data,
        direction
    ):

        result["reason"] = (
            "Zona de rechazo detectada"
        )

        return result

    # ========================================================
    # FILTRO 4 — SOPORTE / RESISTENCIA
    # ========================================================

    if is_near_support_resistance(
        data,
        direction
    ):

        if direction == "bullish":

            result["reason"] = (
                "Precio cerca de resistencia"
            )

        else:

            result["reason"] = (
                "Precio cerca de soporte"
            )

        return result

    # ========================================================
    # FILTRO 5 — EXTENSIÓN
    # ========================================================

    if is_overextended(
        data,
        direction
    ):

        result["reason"] = (
            "Precio demasiado extendido"
        )

        return result

    # ========================================================
    # FILTRO 6 — PULLBACK
    # ========================================================

    if is_pullback(
        data,
        direction
    ):

        result["reason"] = (
            "Pullback detectado"
        )

        return result

    # ========================================================
    # FILTRO 7 — CONTINUIDAD
    # ========================================================

    if not is_continuation(
        data,
        direction
    ):

        result["reason"] = (
            "No existe continuidad limpia"
        )

        return result

    # ========================================================
    # SCORE
    # ========================================================

    score = continuity_score(
        data,
        direction
    )

    result["score"] = score

    # ========================================================
    # SCORE MÍNIMO
    # ========================================================

    if score < 7:

        result["reason"] = (
            f"Continuidad insuficiente "
            f"(score {score}/8)"
        )

        return result

    # ========================================================
    # CONFIRMACIÓN DE ÚLTIMA VELA
    # ========================================================

    candle = candle_direction(
        last
    )

    if direction == "bullish":

        if candle != "bull":

            result["reason"] = (
                "Última vela no confirma CALL"
            )

            return result

    if direction == "bearish":

        if candle != "bear":

            result["reason"] = (
                "Última vela no confirma PUT"
            )

            return result

    # ========================================================
    # SEÑAL CONFIRMADA
    # ========================================================

    result["signal"] = signal

    result["reason"] = (
        "CONTINUIDAD CONFIRMADA | "
        f"tendencia={trend} | "
        f"estructura={detect_structure(data)} | "
        f"score={score}/8"
    )

    return result


# ============================================================
# FUNCIÓN AUXILIAR PARA DEBUG
# ============================================================

def get_market_state(df):

    """
    Devuelve información detallada de la situación
    actual sin ejecutar ninguna operación.
    """

    data = normalize_dataframe(
        df
    )

    if data is None:
        return {
            "valid": False
        }

    if len(data) < 50:
        return {
            "valid": False,
            "candles": len(data)
        }

    data = add_indicators(
        data
    )

    trend = detect_trend(
        data
    )

    if trend == "bullish":
        direction = "bullish"
        signal = "call"

    elif trend == "bearish":
        direction = "bearish"
        signal = "put"

    else:
        direction = "range"
        signal = None

    return {
        "valid": True,
        "candles": len(data),
        "trend": trend,
        "direction": direction,
        "signal": signal,
        "structure": detect_structure(data),
        "strength": trend_strength(
            data,
            direction
        ) if direction != "range" else 0,
        "weakness": has_weakness(
            data,
            direction
        ) if direction != "range" else True,
        "rejection": has_rejection(
            data,
            direction
        ) if direction != "range" else True,
        "support_resistance": (
            is_near_support_resistance(
                data,
                direction
            )
            if direction != "range"
            else True
        ),
        "overextended": (
            is_overextended(
                data,
                direction
            )
            if direction != "range"
            else True
        ),
        "end_of_trend": (
            is_end_of_trend(
                data,
                direction
            )
            if direction != "range"
            else True
        ),
        "pullback": (
            is_pullback(
                data,
                direction
            )
            if direction != "range"
            else True
        ),
        "continuation": (
            is_continuation(
                data,
                direction
            )
            if direction != "range"
            else False
        )
    }
