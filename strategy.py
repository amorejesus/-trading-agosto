import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN DE ESTRATEGIA
# ============================================================

MIN_M1_CANDLES = 30
MIN_M5_CANDLES = 20

# Mínimo de calidad para permitir entrada
MIN_SCORE = 6

# Cantidad de velas usadas para estructura
STRUCTURE_LOOKBACK = 8

# Pullback de 2 a 4 velas
PULLBACK_MIN = 2
PULLBACK_MAX = 4

# Distancia mínima de soporte/resistencia
SR_LOOKBACK = 20

# No entrar demasiado cerca de una zona
SR_MIN_DISTANCE_ATR = 0.60

# Evitar velas anormalmente grandes
MAX_CANDLE_ATR = 2.20

# ATR
ATR_PERIOD = 14


# ============================================================
# UTILIDADES
# ============================================================

def normalize_dataframe(df):

    if df is None:
        return None

    if not isinstance(df, pd.DataFrame):
        return None

    if len(df) == 0:
        return None

    df = df.copy()

    required = [
        "open",
        "close",
        "max",
        "min"
    ]

    for col in required:

        if col not in df.columns:
            return None

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(
        subset=required
    ).reset_index(drop=True)

    return df


# ============================================================
# ATR
# ============================================================

def add_atr(df, period=ATR_PERIOD):

    df = df.copy()

    previous_close = df["close"].shift(1)

    tr1 = (
        df["max"] -
        df["min"]
    )

    tr2 = (
        df["max"] -
        previous_close
    ).abs()

    tr3 = (
        df["min"] -
        previous_close
    ).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1
    ).max(axis=1)

    df["atr"] = (
        true_range
        .rolling(period)
        .mean()
    )

    return df


# ============================================================
# EMA
# ============================================================

def add_ema(df):

    df = df.copy()

    df["ema9"] = (
        df["close"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["ema20"] = (
        df["close"]
        .ewm(
            span=20,
            adjust=False
        )
        .mean()
    )

    return df


# ============================================================
# TENDENCIA M5
# ============================================================

def trend_m5(df):

    df = normalize_dataframe(df)

    if df is None:
        return None

    if len(df) < MIN_M5_CANDLES:
        return None

    df = add_ema(df)

    recent = df.iloc[
        -STRUCTURE_LOOKBACK:
    ]

    highs = recent["max"].values
    lows = recent["min"].values

    rising_highs = sum(
        highs[i] > highs[i - 1]
        for i in range(1, len(highs))
    )

    rising_lows = sum(
        lows[i] > lows[i - 1]
        for i in range(1, len(lows))
    )

    falling_highs = sum(
        highs[i] < highs[i - 1]
        for i in range(1, len(highs))
    )

    falling_lows = sum(
        lows[i] < lows[i - 1]
        for i in range(1, len(lows))
    )

    # Estructura alcista
    if (
        rising_highs >= 4
        and
        rising_lows >= 4
        and
        recent["close"].iloc[-1]
        >= recent["ema20"].iloc[-1]
    ):
        return "up"

    # Estructura bajista
    if (
        falling_highs >= 4
        and
        falling_lows >= 4
        and
        recent["close"].iloc[-1]
        <= recent["ema20"].iloc[-1]
    ):
        return "down"

    # Tendencia más flexible mediante EMA
    if (
        recent["ema9"].iloc[-1]
        >
        recent["ema20"].iloc[-1]
        and
        recent["close"].iloc[-1]
        >
        recent["ema20"].iloc[-1]
    ):
        return "up"

    if (
        recent["ema9"].iloc[-1]
        <
        recent["ema20"].iloc[-1]
        and
        recent["close"].iloc[-1]
        <
        recent["ema20"].iloc[-1]
    ):
        return "down"

    return None


# ============================================================
# FUERZA DE TENDENCIA M5
# ============================================================

def trend_strength_m5(df, trend):

    if trend not in ("up", "down"):
        return 0

    df = normalize_dataframe(df)

    if df is None:
        return 0

    df = add_ema(df)

    last = df.iloc[-1]

    score = 0

    if trend == "up":

        if last["close"] > last["ema20"]:
            score += 1

        if last["ema9"] > last["ema20"]:
            score += 1

        if df["close"].iloc[-3:].mean() > last["ema20"]:
            score += 1

    elif trend == "down":

        if last["close"] < last["ema20"]:
            score += 1

        if last["ema9"] < last["ema20"]:
            score += 1

        if df["close"].iloc[-3:].mean() < last["ema20"]:
            score += 1

    return score


# ============================================================
# DETECTAR PULLBACK
# ============================================================

def detect_pullback(df, trend):

    df = normalize_dataframe(df)

    if df is None:
        return False, 0

    if len(df) < 10:
        return False, 0

    # No usamos la última vela porque puede estar abierta.
    data = df.iloc[:-1].copy()

    if trend == "up":

        count = 0

        for i in range(
            1,
            min(
                PULLBACK_MAX + 1,
                len(data)
            )
        ):

            candle = data.iloc[-i]

            if candle["close"] < candle["open"]:
                count += 1
            else:
                break

        if (
            PULLBACK_MIN
            <= count
            <= PULLBACK_MAX
        ):
            return True, count

    if trend == "down":

        count = 0

        for i in range(
            1,
            min(
                PULLBACK_MAX + 1,
                len(data)
            )
        ):

            candle = data.iloc[-i]

            if candle["close"] > candle["open"]:
                count += 1
            else:
                break

        if (
            PULLBACK_MIN
            <= count
            <= PULLBACK_MAX
        ):
            return True, count

    return False, 0


# ============================================================
# MICROESTRUCTURA M1
# ============================================================

def candle_strength(candle, trend):

    candle_range = (
        candle["max"] -
        candle["min"]
    )

    if candle_range <= 0:
        return 0

    body = abs(
        candle["close"] -
        candle["open"]
    )

    body_ratio = (
        body /
        candle_range
    )

    upper_wick = (
        candle["max"] -
        max(
            candle["open"],
            candle["close"]
        )
    )

    lower_wick = (
        min(
            candle["open"],
            candle["close"]
        ) -
        candle["min"]
    )

    score = 0

    # Fuerza del cuerpo
    if body_ratio >= 0.60:
        score += 2

    elif body_ratio >= 0.50:
        score += 1

    # Dirección
    if trend == "up":

        if candle["close"] > candle["open"]:
            score += 2

        if upper_wick < body * 0.60:
            score += 1

    elif trend == "down":

        if candle["close"] < candle["open"]:
            score += 2

        if lower_wick < body * 0.60:
            score += 1

    return score


# ============================================================
# CONFIRMACIÓN M1
# ============================================================

def m1_confirmation(df, trend):

    df = normalize_dataframe(df)

    if df is None:
        return False, 0

    if len(df) < MIN_M1_CANDLES:
        return False, 0

    df = add_atr(df)
    df = add_ema(df)

    # La última vela puede estar abierta.
    # Trabajamos con la última cerrada.
    last = df.iloc[-2]

    previous = df.iloc[-3]

    score = 0

    # --------------------------------------------------------
    # Dirección de la vela
    # --------------------------------------------------------

    if trend == "up":

        if last["close"] > last["open"]:
            score += 2

        if last["close"] > previous["close"]:
            score += 1

    elif trend == "down":

        if last["close"] < last["open"]:
            score += 2

        if last["close"] < previous["close"]:
            score += 1

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    if trend == "up":

        if last["close"] > last["ema9"]:
            score += 1

    elif trend == "down":

        if last["close"] < last["ema9"]:
            score += 1

    # --------------------------------------------------------
    # Fuerza de vela
    # --------------------------------------------------------

    score += candle_strength(
        last,
        trend
    )

    return score >= 4, score


# ============================================================
# EVITAR LATERAL
# ============================================================

def is_lateral(df):

    df = normalize_dataframe(df)

    if df is None:
        return True

    if len(df) < 15:
        return True

    recent = df.iloc[-12:]

    total_range = (
        recent["max"].max()
        -
        recent["min"].min()
    )

    average_range = (
        recent["max"]
        -
        recent["min"]
    ).mean()

    if average_range <= 0:
        return True

    ratio = (
        total_range /
        average_range
    )

    return ratio < 3.0


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def get_support_resistance(df):

    df = normalize_dataframe(df)

    if df is None:
        return None, None

    if len(df) < SR_LOOKBACK:
        return None, None

    recent = df.iloc[
        -SR_LOOKBACK:
    ]

    support = recent["min"].min()

    resistance = recent["max"].max()

    return support, resistance


# ============================================================
# PROTECCIÓN CONTRA ENTRADA CERCA DE S/R
# ============================================================

def too_close_to_zone(
    df,
    trend
):

    df = normalize_dataframe(df)

    if df is None:
        return True

    df = add_atr(df)

    last = df.iloc[-2]

    atr = last["atr"]

    if pd.isna(atr) or atr <= 0:
        return True

    support, resistance = (
        get_support_resistance(df)
    )

    if support is None:
        return False

    price = last["close"]

    min_distance = (
        atr *
        SR_MIN_DISTANCE_ATR
    )

    if trend == "up":

        distance_resistance = (
            resistance -
            price
        )

        if distance_resistance < min_distance:
            return True

    elif trend == "down":

        distance_support = (
            price -
            support
        )

        if distance_support < min_distance:
            return True

    return False


# ============================================================
# EVITAR VELA EXAGERADAMENTE GRANDE
# ============================================================

def abnormal_candle(df):

    df = normalize_dataframe(df)

    if df is None:
        return True

    df = add_atr(df)

    last = df.iloc[-2]

    candle_range = (
        last["max"] -
        last["min"]
    )

    atr = last["atr"]

    if pd.isna(atr) or atr <= 0:
        return True

    return (
        candle_range >
        atr * MAX_CANDLE_ATR
    )


# ============================================================
# SCORE DE CALIDAD
# ============================================================

def calculate_score(
    df_m1,
    df_m5,
    trend
):

    score = 0

    # --------------------------------------------------------
    # Tendencia M5
    # --------------------------------------------------------

    strength = trend_strength_m5(
        df_m5,
        trend
    )

    score += strength

    # --------------------------------------------------------
    # Pullback
    # --------------------------------------------------------

    pullback, count = (
        detect_pullback(
            df_m1,
            trend
        )
    )

    if pullback:
        score += 2

    # --------------------------------------------------------
    # M1
    # --------------------------------------------------------

    confirmation, m1_score = (
        m1_confirmation(
            df_m1,
            trend
        )
    )

    score += min(
        m1_score,
        4
    )

    # --------------------------------------------------------
    # Zona S/R
    # --------------------------------------------------------

    if not too_close_to_zone(
        df_m1,
        trend
    ):
        score += 1

    return score


# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================

def analyze_candle(
    df_m1,
    df_m5
):

    df_m1 = normalize_dataframe(
        df_m1
    )

    df_m5 = normalize_dataframe(
        df_m5
    )

    if df_m1 is None:
        return None, None

    if df_m5 is None:
        return None, None

    if len(df_m1) < MIN_M1_CANDLES:
        return None, None

    if len(df_m5) < MIN_M5_CANDLES:
        return None, None

    # ========================================================
    # TENDENCIA M5
    # ========================================================

    trend = trend_m5(
        df_m5
    )

    if trend is None:

        print(
            "⛔ M5 sin tendencia clara"
        )

        return None, None

    print(
        f"📈 Tendencia M5: {trend.upper()}"
    )

    # ========================================================
    # LATERAL
    # ========================================================

    if is_lateral(df_m5):

        print(
            "⛔ M5 lateral"
        )

        return None, trend

    # ========================================================
    # VELA ANORMAL
    # ========================================================

    if abnormal_candle(df_m1):

        print(
            "⛔ M1: vela demasiado grande"
        )

        return None, trend

    # ========================================================
    # ZONA S/R
    # ========================================================

    if too_close_to_zone(
        df_m1,
        trend
    ):

        print(
            "⛔ Precio demasiado cerca "
            "de soporte/resistencia"
        )

        return None, trend

    # ========================================================
    # PULLBACK
    # ========================================================

    pullback, count = (
        detect_pullback(
            df_m1,
            trend
        )
    )

    if pullback:

        print(
            f"🔄 Pullback detectado: "
            f"{count} velas"
        )

    # No obligamos a que siempre exista
    # un pullback perfecto para evitar
    # bloquear excesivamente el bot.

    # ========================================================
    # CONFIRMACIÓN M1
    # ========================================================

    confirmation, m1_score = (
        m1_confirmation(
            df_m1,
            trend
        )
    )

    if not confirmation:

        print(
            f"⛔ M1 sin fuerza suficiente "
            f"(score={m1_score})"
        )

        return None, trend

    # ========================================================
    # SCORE
    # ========================================================

    score = calculate_score(
        df_m1,
        df_m5,
        trend
    )

    print(
        f"📊 Score: {score}/{MIN_SCORE}"
    )

    if score < MIN_SCORE:

        print(
            "⛔ Score insuficiente"
        )

        return None, trend

    # ========================================================
    # ÚLTIMA VELA CERRADA
    # ========================================================

    last = df_m1.iloc[-2]

    previous = df_m1.iloc[-3]

    # ========================================================
    # CALL
    # ========================================================

    if trend == "up":

        if (
            last["close"] >
            last["open"]
            and
            last["close"] >
            previous["close"]
        ):

            print(
                "🟢 CONTINUIDAD + FUERZA"
            )

            print(
                "🎯 SEÑAL CALL"
            )

            return "call", trend

    # ========================================================
    # PUT
    # ========================================================

    if trend == "down":

        if (
            last["close"] <
            last["open"]
            and
            last["close"] <
            previous["close"]
        ):

            print(
                "🔴 CONTINUIDAD + FUERZA"
            )

            print(
                "🎯 SEÑAL PUT"
            )

            return "put", trend

    print(
        "⛔ No se confirmó continuidad"
    )

    return None, trend
