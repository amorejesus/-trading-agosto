import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN DE ESTRATEGIA
# ============================================================

MAX_CANDLES = 60

EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50

ATR_PERIOD = 14

# Distancia mínima para considerar que existe separación
# entre las medias y evitar mercado débil/lateral.
MIN_TREND_SEPARATION_ATR = 0.15

# Evita operar demasiado cerca de máximos/mínimos recientes.
SR_LOOKBACK = 20

# Distancia aproximada de seguridad respecto a soporte/resistencia.
SR_ATR_DISTANCE = 0.35

# Rechazo
WICK_BODY_RATIO = 1.5

# Evita entrar cuando la tendencia ya está demasiado extendida.
MAX_EXTENSION_ATR = 2.5


# ============================================================
# INDICADORES
# ============================================================

def add_indicators(df):
    """
    Agrega indicadores necesarios para analizar continuidad.
    """

    df = df.copy()

    if len(df) == 0:
        return df

    df["ema9"] = df["close"].ewm(
        span=EMA_FAST,
        adjust=False
    ).mean()

    df["ema21"] = df["close"].ewm(
        span=EMA_MID,
        adjust=False
    ).mean()

    df["ema50"] = df["close"].ewm(
        span=EMA_SLOW,
        adjust=False
    ).mean()

    # True Range
    previous_close = df["close"].shift(1)

    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - previous_close).abs()
    tr3 = (df["low"] - previous_close).abs()

    df["tr"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr"] = df["tr"].rolling(
        ATR_PERIOD
    ).mean()

    return df


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
# ESTRUCTURA DE MERCADO
# ============================================================

def detect_structure(df):

    if len(df) < 10:
        return "unknown"

    data = df.tail(min(MAX_CANDLES, len(df)))

    highs = data["high"].values
    lows = data["low"].values

    hh = 0
    hl = 0
    lh = 0
    ll = 0

    for i in range(1, len(highs)):

        if highs[i] > highs[i - 1]:
            hh += 1

        if lows[i] > lows[i - 1]:
            hl += 1

        if highs[i] < highs[i - 1]:
            lh += 1

        if lows[i] < lows[i - 1]:
            ll += 1

    bullish_score = hh + hl
    bearish_score = lh + ll

    if bullish_score > bearish_score:
        return "bullish"

    if bearish_score > bullish_score:
        return "bearish"

    return "range"


# ============================================================
# TENDENCIA
# ============================================================

def detect_trend(df):

    if len(df) < EMA_SLOW + 5:
        return "unknown"

    row = df.iloc[-1]

    ema9 = row["ema9"]
    ema21 = row["ema21"]
    ema50 = row["ema50"]

    if pd.isna(ema50):
        return "unknown"

    # Tendencia alcista limpia
    if (
        ema9 > ema21
        and ema21 > ema50
        and row["close"] > ema9
    ):
        return "bullish"

    # Tendencia bajista limpia
    if (
        ema9 < ema21
        and ema21 < ema50
        and row["close"] < ema9
    ):
        return "bearish"

    return "range"


# ============================================================
# FUERZA DE TENDENCIA
# ============================================================

def trend_strength(df):

    if len(df) < EMA_SLOW + 5:
        return "weak"

    row = df.iloc[-1]

    atr = row["atr"]

    if pd.isna(atr) or atr <= 0:
        return "weak"

    separation = abs(row["ema9"] - row["ema21"])

    separation_atr = separation / atr

    if separation_atr < MIN_TREND_SEPARATION_ATR:
        return "weak"

    # Comprobar pendiente de EMA21
    ema21_now = df["ema21"].iloc[-1]
    ema21_previous = df["ema21"].iloc[-5]

    slope = ema21_now - ema21_previous

    if abs(slope) < atr * 0.05:
        return "weak"

    return "strong"


# ============================================================
# RECHAZO
# ============================================================

def has_rejection(candle):

    body = abs(
        candle["close"] - candle["open"]
    )

    if body <= 0:
        body = 0.00000001

    upper_wick = (
        candle["high"]
        - max(candle["open"], candle["close"])
    )

    lower_wick = (
        min(candle["open"], candle["close"])
        - candle["low"]
    )

    # Rechazo superior
    if upper_wick > body * WICK_BODY_RATIO:
        return True

    # Rechazo inferior
    if lower_wick > body * WICK_BODY_RATIO:
        return True

    return False


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def near_support_resistance(df):

    if len(df) < SR_LOOKBACK + 2:
        return True

    row = df.iloc[-1]

    close = row["close"]
    atr = row["atr"]

    if pd.isna(atr) or atr <= 0:
        return True

    historical = df.iloc[-SR_LOOKBACK - 1:-1]

    resistance = historical["high"].max()
    support = historical["low"].min()

    distance_resistance = abs(
        resistance - close
    )

    distance_support = abs(
        close - support
    )

    max_distance = atr * SR_ATR_DISTANCE

    if distance_resistance <= max_distance:
        return True

    if distance_support <= max_distance:
        return True

    return False


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def trend_is_ending(df, direction):

    if len(df) < 10:
        return True

    recent = df.tail(5)

    if direction == "bullish":

        # Si empiezan a aparecer cierres por debajo
        # de EMA9, la continuidad pierde calidad.
        below = (
            recent["close"] < recent["ema9"]
        ).sum()

        if below >= 2:
            return True

        # EMA9 dejando de subir.
        if (
            recent["ema9"].iloc[-1]
            <= recent["ema9"].iloc[-3]
        ):
            return True

    elif direction == "bearish":

        above = (
            recent["close"] > recent["ema9"]
        ).sum()

        if above >= 2:
            return True

        if (
            recent["ema9"].iloc[-1]
            >= recent["ema9"].iloc[-3]
        ):
            return True

    return False


# ============================================================
# DEBILIDAD
# ============================================================

def has_weakness(df, direction):

    if len(df) < 6:
        return True

    recent = df.tail(5)

    bodies = (
        recent["close"]
        - recent["open"]
    ).abs()

    atr = recent["atr"].iloc[-1]

    if pd.isna(atr) or atr <= 0:
        return True

    average_body = bodies.mean()

    # Velas demasiado pequeñas
    if average_body < atr * 0.20:
        return True

    if direction == "bullish":

        bullish_count = (
            recent["close"] > recent["open"]
        ).sum()

        if bullish_count < 3:
            return True

    elif direction == "bearish":

        bearish_count = (
            recent["close"] < recent["open"]
        ).sum()

        if bearish_count < 3:
            return True

    return False


# ============================================================
# PULLBACK
# ============================================================

def is_pullback(df, direction):

    if len(df) < 6:
        return True

    last = df.iloc[-1]

    if direction == "bullish":

        # Si el precio está regresando hacia EMA21,
        # no queremos entrar.
        distance = abs(
            last["close"] - last["ema21"]
        )

        atr = last["atr"]

        if distance < atr * 0.25:
            return True

        # Últimas velas deben mantener máximos/mínimos
        if (
            df["high"].iloc[-1]
            < df["high"].iloc[-2]
        ):
            return True

    elif direction == "bearish":

        distance = abs(
            last["close"] - last["ema21"]
        )

        atr = last["atr"]

        if distance < atr * 0.25:
            return True

        if (
            df["low"].iloc[-1]
            > df["low"].iloc[-2]
        ):
            return True

    return False


# ============================================================
# EXTENSIÓN EXCESIVA
# ============================================================

def trend_overextended(df, direction):

    if len(df) < EMA_SLOW + 2:
        return True

    row = df.iloc[-1]

    atr = row["atr"]

    if pd.isna(atr) or atr <= 0:
        return True

    if direction == "bullish":

        extension = (
            row["close"] - row["ema21"]
        ) / atr

        if extension > MAX_EXTENSION_ATR:
            return True

    elif direction == "bearish":

        extension = (
            row["ema21"] - row["close"]
        ) / atr

        if extension > MAX_EXTENSION_ATR:
            return True

    return False


# ============================================================
# CONTINUIDAD
# ============================================================

def continuity_confirmation(df, direction):

    if len(df) < 5:
        return False

    recent = df.tail(4)

    if direction == "bullish":

        bullish = (
            recent["close"] > recent["open"]
        ).sum()

        higher_high = (
            recent["high"].iloc[-1]
            > recent["high"].iloc[-2]
        )

        higher_low = (
            recent["low"].iloc[-1]
            >= recent["low"].iloc[-2]
        )

        return (
            bullish >= 2
            and higher_high
            and higher_low
        )

    if direction == "bearish":

        bearish = (
            recent["close"] < recent["open"]
        ).sum()

        lower_high = (
            recent["high"].iloc[-1]
            <= recent["high"].iloc[-2]
        )

        lower_low = (
            recent["low"].iloc[-1]
            < recent["low"].iloc[-2]
        )

        return (
            bearish >= 2
            and lower_high
            and lower_low
        )

    return False


# ============================================================
# ANÁLISIS PRINCIPAL
# ============================================================

def analyze_market(df):

    """
    Devuelve:

        {
            "signal": "call",
            "direction": "bullish",
            "reason": "...",
            "score": 5
        }

    o:

        {
            "signal": None,
            ...
        }
    """

    if df is None or len(df) < 60:
        return {
            "signal": None,
            "direction": "unknown",
            "reason": "No hay suficientes velas",
            "score": 0
        }

    # Máximo 60 velas
    df = df.tail(MAX_CANDLES).copy()

    df = add_indicators(df)

    trend = detect_trend(df)

    if trend not in ("bullish", "bearish"):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Sin tendencia limpia",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 1 - FUERZA
    # --------------------------------------------------------

    if trend_strength(df) != "strong":
        return {
            "signal": None,
            "direction": trend,
            "reason": "Tendencia débil",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 2 - ESTRUCTURA
    # --------------------------------------------------------

    structure = detect_structure(df)

    if structure != trend:
        return {
            "signal": None,
            "direction": trend,
            "reason": "Estructura no confirma tendencia",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 3 - RECHAZO
    # --------------------------------------------------------

    last_candle = df.iloc[-1]

    if has_rejection(last_candle):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Zona/vela de rechazo",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 4 - SOPORTE / RESISTENCIA
    # --------------------------------------------------------

    if near_support_resistance(df):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Cerca de soporte/resistencia",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 5 - FINAL DE TENDENCIA
    # --------------------------------------------------------

    if trend_is_ending(df, trend):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Posible final de tendencia",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 6 - DEBILIDAD
    # --------------------------------------------------------

    if has_weakness(df, trend):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Debilidad",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 7 - PULLBACK
    # --------------------------------------------------------

    if is_pullback(df, trend):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Pullback",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 8 - EXTENSIÓN
    # --------------------------------------------------------

    if trend_overextended(df, trend):
        return {
            "signal": None,
            "direction": trend,
            "reason": "Tendencia demasiado extendida",
            "score": 0
        }

    # --------------------------------------------------------
    # FILTRO 9 - CONTINUIDAD
    # --------------------------------------------------------

    if not continuity_confirmation(df, trend):
        return {
            "signal": None,
            "direction": trend,
            "reason": "No hay continuidad suficiente",
            "score": 0
        }

    # --------------------------------------------------------
    # SEÑAL FINAL
    # --------------------------------------------------------

    if trend == "bullish":

        return {
            "signal": "call",
            "direction": "bullish",
            "reason": "Continuidad alcista confirmada",
            "score": 5
        }

    if trend == "bearish":

        return {
            "signal": "put",
            "direction": "bearish",
            "reason": "Continuidad bajista confirmada",
            "score": 5
        }

    return {
        "signal": None,
        "direction": trend,
        "reason": "Sin señal",
        "score": 0
        }
