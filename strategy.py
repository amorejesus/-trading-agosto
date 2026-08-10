import pandas as pd
import numpy as np


# ============================================================
# CONFIGURACIÓN
# ============================================================

MAX_CANDLES = 60
MIN_CANDLES = 25

# Velas para estructura general
STRUCTURE_LOOKBACK = 30

# Velas para buscar zonas de soporte/resistencia
SR_LOOKBACK = 60

# Cantidad mínima de toques para considerar una zona importante
MIN_SR_TOUCHES = 2

# Distancia máxima entre niveles para agruparlos
# Se adapta también al ATR.
SR_CLUSTER_TOLERANCE = 0.00020

# Protección adicional alrededor de una zona
SR_PROTECTION_ATR = 0.45

# Cuántas velas recientes se usan para detectar rechazo
REJECTION_LOOKBACK = 6

# Cuántas velas para detectar pullback
PULLBACK_LOOKBACK = 6

# Cuántas velas para detectar debilidad
WEAKNESS_LOOKBACK = 5

# ============================================================
# UTILIDADES
# ============================================================


def safe_float(value, default=0.0):

    try:
        value = float(value)

        if np.isnan(value):
            return default

        if np.isinf(value):
            return default

        return value

    except Exception:
        return default


# ============================================================
# VALIDACIÓN
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
# PREPARAR DATA
# ============================================================


def prepare_dataframe(df):

    df = df.copy()

    required = [
        "open",
        "high",
        "low",
        "close"
    ]

    for column in required:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    df.dropna(
        subset=required,
        inplace=True
    )

    if "from" in df.columns:

        df["from"] = pd.to_numeric(
            df["from"],
            errors="coerce"
        )

        df.dropna(
            subset=["from"],
            inplace=True
        )

        df.sort_values(
            "from",
            inplace=True
        )

    df.reset_index(
        drop=True,
        inplace=True
    )

    # Nunca utilizar más de 60 velas
    if len(df) > MAX_CANDLES:

        df = df.tail(
            MAX_CANDLES
        ).reset_index(
            drop=True
        )

    return df


# ============================================================
# INDICADORES
# ============================================================


def add_indicators(df):

    df = df.copy()

    # --------------------------------------------------------
    # RANGO
    # --------------------------------------------------------

    df["range"] = (
        df["high"] -
        df["low"]
    )

    df["range"] = df["range"].replace(
        0,
        np.nan
    )

    # --------------------------------------------------------
    # CUERPO
    # --------------------------------------------------------

    df["body"] = (
        df["close"] -
        df["open"]
    ).abs()

    # --------------------------------------------------------
    # DIRECCIÓN
    # --------------------------------------------------------

    df["direction"] = np.where(
        df["close"] > df["open"],
        1,
        np.where(
            df["close"] < df["open"],
            -1,
            0
        )
    )

    # --------------------------------------------------------
    # PROPORCIÓN DEL CUERPO
    # --------------------------------------------------------

    df["body_ratio"] = (
        df["body"] /
        df["range"]
    )

    df["body_ratio"] = (
        df["body_ratio"]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .fillna(0)
    )

    # --------------------------------------------------------
    # MECHAS
    # --------------------------------------------------------

    df["upper_wick"] = (
        df["high"] -
        df[["open", "close"]].max(axis=1)
    )

    df["lower_wick"] = (
        df[["open", "close"]].min(axis=1) -
        df["low"]
    )

    # --------------------------------------------------------
    # TRUE RANGE
    # --------------------------------------------------------

    previous_close = df["close"].shift(1)

    tr1 = (
        df["high"] -
        df["low"]
    )

    tr2 = (
        df["high"] -
        previous_close
    ).abs()

    tr3 = (
        df["low"] -
        previous_close
    ).abs()

    df["tr"] = pd.concat(
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

    df["atr"] = (
        df["tr"]
        .rolling(
            14,
            min_periods=5
        )
        .mean()
    )

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    df["ema9"] = (
        df["close"]
        .ewm(
            span=9,
            adjust=False
        )
        .mean()
    )

    df["ema21"] = (
        df["close"]
        .ewm(
            span=21,
            adjust=False
        )
        .mean()
    )

    df["ema50"] = (
        df["close"]
        .ewm(
            span=50,
            adjust=False
        )
        .mean()
    )

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
# DETECCIÓN DE ESTRUCTURA
# ============================================================


def detect_structure(df):

    if len(df) < 12:

        return {
            "structure": "range",
            "bullish": False,
            "bearish": False
        }

    data = df.tail(
        STRUCTURE_LOOKBACK
    )

    highs = data["high"].values
    lows = data["low"].values

    higher_highs = 0
    higher_lows = 0
    lower_highs = 0
    lower_lows = 0

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    for i in range(1, len(highs)):

        if highs[i] > highs[i - 1]:
            higher_highs += 1

        elif highs[i] < highs[i - 1]:
            lower_highs += 1

        if lows[i] > lows[i - 1]:
            higher_lows += 1

        elif lows[i] < lows[i - 1]:
            lower_lows += 1

    # --------------------------------------------------------
    # ESTRUCTURA RECIENTE
    # --------------------------------------------------------

    recent = data.tail(8)

    recent_hh = 0
    recent_hl = 0
    recent_lh = 0
    recent_ll = 0

    for i in range(1, len(recent)):

        if recent["high"].iloc[i] > recent["high"].iloc[i - 1]:
            recent_hh += 1

        elif recent["high"].iloc[i] < recent["high"].iloc[i - 1]:
            recent_lh += 1

        if recent["low"].iloc[i] > recent["low"].iloc[i - 1]:
            recent_hl += 1

        elif recent["low"].iloc[i] < recent["low"].iloc[i - 1]:
            recent_ll += 1

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    bullish = (
        higher_highs >= lower_highs
        and
        higher_lows >= lower_lows
        and
        recent_hh >= 3
        and
        recent_hl >= 3
    )

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    bearish = (
        lower_highs >= higher_highs
        and
        lower_lows >= higher_lows
        and
        recent_lh >= 3
        and
        recent_ll >= 3
    )

    if bullish and not bearish:

        return {
            "structure": "bullish",
            "bullish": True,
            "bearish": False
        }

    if bearish and not bullish:

        return {
            "structure": "bearish",
            "bullish": False,
            "bearish": True
        }

    return {
        "structure": "range",
        "bullish": False,
        "bearish": False
    }


# ============================================================
# TENDENCIA
# ============================================================


def detect_trend(df):

    if len(df) < 20:
        return "range"

    current = df.iloc[-1]

    ema9 = safe_float(current["ema9"])
    ema21 = safe_float(current["ema21"])
    ema50 = safe_float(current["ema50"])
    close = safe_float(current["close"])

    # --------------------------------------------------------
    # TENDENCIA ALCISTA
    # --------------------------------------------------------

    if (
        ema9 > ema21
        and
        ema21 > ema50
        and
        close > ema9
    ):

        return "bullish"

    # --------------------------------------------------------
    # TENDENCIA BAJISTA
    # --------------------------------------------------------

    if (
        ema9 < ema21
        and
        ema21 < ema50
        and
        close < ema9
    ):

        return "bearish"

    return "range"


# ============================================================
# FUERZA DE TENDENCIA
# ============================================================


def trend_strength(df, direction):

    if len(df) < 6:
        return 0

    data = df.tail(6)

    if direction == "bullish":

        return int(
            (data["direction"] == 1).sum()
        )

    if direction == "bearish":

        return int(
            (data["direction"] == -1).sum()
        )

    return 0


# ============================================================
# DETECTAR DEBILIDAD
# ============================================================


def detect_weakness(df, direction):

    if len(df) < WEAKNESS_LOOKBACK:

        return True

    data = df.tail(
        WEAKNESS_LOOKBACK
    )

    current = data.iloc[-1]

    # --------------------------------------------------------
    # CUERPO PEQUEÑO
    # --------------------------------------------------------

    body_ratio = safe_float(
        current["body_ratio"]
    )

    if body_ratio < 0.45:

        return True

    # --------------------------------------------------------
    # RANGO PEQUEÑO
    # --------------------------------------------------------

    previous_ranges = (
        data["range"]
        .iloc[:-1]
        .mean()
    )

    current_range = safe_float(
        current["range"]
    )

    if previous_ranges > 0:

        if current_range < (
            previous_ranges * 0.50
        ):

            return True

    # --------------------------------------------------------
    # VELAS CONTRARIAS
    # --------------------------------------------------------

    if direction == "bullish":

        opposite = (
            data["direction"] == -1
        ).sum()

    elif direction == "bearish":

        opposite = (
            data["direction"] == 1
        ).sum()

    else:

        return True

    if opposite >= 3:

        return True

    return False


# ============================================================
# RECHAZO
# ============================================================


def detect_rejection(df):

    if len(df) < REJECTION_LOOKBACK:

        return True

    data = df.tail(
        REJECTION_LOOKBACK
    )

    for _, candle in data.iterrows():

        candle_range = safe_float(
            candle["range"]
        )

        body = safe_float(
            candle["body"]
        )

        upper = safe_float(
            candle["upper_wick"]
        )

        lower = safe_float(
            candle["lower_wick"]
        )

        if candle_range <= 0:
            continue

        # ----------------------------------------------------
        # RECHAZO SUPERIOR
        # ----------------------------------------------------

        if (
            upper >= candle_range * 0.35
            and
            upper >= body * 1.5
        ):

            return True

        # ----------------------------------------------------
        # RECHAZO INFERIOR
        # ----------------------------------------------------

        if (
            lower >= candle_range * 0.35
            and
            lower >= body * 1.5
        ):

            return True

    return False


# ============================================================
# CREAR NIVELES DE SOPORTE / RESISTENCIA
#
# Aquí está la corrección principal.
#
# No usamos únicamente:
#
#     máximo de 60
#     mínimo de 60
#
# Buscamos múltiples reacciones agrupadas.
# ============================================================


def build_sr_levels(df):

    if len(df) < 15:

        return {
            "supports": [],
            "resistances": []
        }

    # --------------------------------------------------------
    # IMPORTANTE:
    # NO utilizar la vela actual para construir niveles.
    # --------------------------------------------------------

    data = df.tail(
        SR_LOOKBACK
    )

    if len(data) > 3:

        historical = data.iloc[:-1].copy()

    else:

        historical = data.copy()

    if len(historical) < 10:

        return {
            "supports": [],
            "resistances": []
        }

    atr = safe_float(
        df.iloc[-1]["atr"]
    )

    if atr <= 0:

        atr = safe_float(
            historical["range"].mean()
        )

    if atr <= 0:

        atr = SR_CLUSTER_TOLERANCE

    # --------------------------------------------------------
    # TOLERANCIA DE AGRUPACIÓN
    # --------------------------------------------------------

    cluster_tolerance = max(
        SR_CLUSTER_TOLERANCE,
        atr * 0.30
    )

    # --------------------------------------------------------
    # BUSCAR SWINGS
    # --------------------------------------------------------

    support_candidates = []
    resistance_candidates = []

    highs = historical["high"].values
    lows = historical["low"].values

    # Usamos ventanas de 5 velas
    for i in range(
        2,
        len(historical) - 2
    ):

        high_value = safe_float(
            highs[i]
        )

        low_value = safe_float(
            lows[i]
        )

        # ----------------------------------------------------
        # SWING HIGH
        # ----------------------------------------------------

        if (
            high_value >= highs[i - 1]
            and
            high_value >= highs[i - 2]
            and
            high_value >= highs[i + 1]
            and
            high_value >= highs[i + 2]
        ):

            resistance_candidates.append(
                high_value
            )

        # ----------------------------------------------------
        # SWING LOW
        # ----------------------------------------------------

        if (
            low_value <= lows[i - 1]
            and
            low_value <= lows[i - 2]
            and
            low_value <= lows[i + 1]
            and
            low_value <= lows[i + 2]
        ):

            support_candidates.append(
                low_value
            )

    # --------------------------------------------------------
    # AGRUPAR NIVELES
    # --------------------------------------------------------

    def cluster_levels(levels):

        if not levels:
            return []

        levels = sorted(levels)

        clusters = []

        current_cluster = [
            levels[0]
        ]

        for level in levels[1:]:

            cluster_mean = (
                sum(current_cluster)
                /
                len(current_cluster)
            )

            if abs(
                level - cluster_mean
            ) <= cluster_tolerance:

                current_cluster.append(
                    level
                )

            else:

                clusters.append(
                    current_cluster
                )

                current_cluster = [
                    level
                ]

        clusters.append(
            current_cluster
        )

        result = []

        for cluster in clusters:

            result.append(
                {
                    "level": (
                        sum(cluster)
                        /
                        len(cluster)
                    ),
                    "touches": len(cluster)
                }
            )

        return result

    supports = cluster_levels(
        support_candidates
    )

    resistances = cluster_levels(
        resistance_candidates
    )

    # --------------------------------------------------------
    # SOLO NIVELES CON AL MENOS 2 REACCIONES
    # --------------------------------------------------------

    supports = [
        level
        for level in supports
        if level["touches"] >= MIN_SR_TOUCHES
    ]

    resistances = [
        level
        for level in resistances
        if level["touches"] >= MIN_SR_TOUCHES
    ]

    return {
        "supports": supports,
        "resistances": resistances
    }


# ============================================================
# ZONA DE PROTECCIÓN S/R
# ============================================================


def get_sr_protection_distance(df):

    if len(df) == 0:
        return SR_CLUSTER_TOLERANCE

    atr = safe_float(
        df.iloc[-1]["atr"]
    )

    if atr <= 0:

        atr = safe_float(
            df["range"].tail(10).mean()
        )

    if atr <= 0:

        atr = SR_CLUSTER_TOLERANCE

    # --------------------------------------------------------
    # Zona de seguridad alrededor del nivel.
    # --------------------------------------------------------

    protection = max(
        SR_CLUSTER_TOLERANCE,
        atr * SR_PROTECTION_ATR
    )

    return protection


# ============================================================
# COMPROBAR SOPORTE
# ============================================================


def is_near_support(df):

    if len(df) < 15:

        return True

    levels = build_sr_levels(
        df
    )

    current_price = safe_float(
        df.iloc[-1]["close"]
    )

    protection = (
        get_sr_protection_distance(df)
    )

    for support in levels["supports"]:

        level = safe_float(
            support["level"]
        )

        # Precio por encima o prácticamente sobre soporte
        if abs(
            current_price - level
        ) <= protection:

            return True

    return False


# ============================================================
# COMPROBAR RESISTENCIA
# ============================================================


def is_near_resistance(df):

    if len(df) < 15:

        return True

    levels = build_sr_levels(
        df
    )

    current_price = safe_float(
        df.iloc[-1]["close"]
    )

    protection = (
        get_sr_protection_distance(df)
    )

    for resistance in levels["resistances"]:

        level = safe_float(
            resistance["level"]
        )

        if abs(
            current_price - level
        ) <= protection:

            return True

    return False


# ============================================================
# COMPROBACIÓN GENERAL S/R
# ============================================================


def check_support_resistance(df):

    """
    Devuelve:

        in_zone
        near_support
        near_resistance
        support_level
        resistance_level
    """

    if len(df) < 15:

        return {
            "in_zone": True,
            "near_support": True,
            "near_resistance": True,
            "support_level": None,
            "resistance_level": None
        }

    levels = build_sr_levels(
        df
    )

    current_price = safe_float(
        df.iloc[-1]["close"]
    )

    protection = (
        get_sr_protection_distance(df)
    )

    nearest_support = None
    nearest_resistance = None

    support_distance = float("inf")
    resistance_distance = float("inf")

    # --------------------------------------------------------
    # SOPORTES
    # --------------------------------------------------------

    for support in levels["supports"]:

        level = safe_float(
            support["level"]
        )

        distance = abs(
            current_price - level
        )

        if distance < support_distance:

            support_distance = distance
            nearest_support = level

    # --------------------------------------------------------
    # RESISTENCIAS
    # --------------------------------------------------------

    for resistance in levels["resistances"]:

        level = safe_float(
            resistance["level"]
        )

        distance = abs(
            current_price - level
        )

        if distance < resistance_distance:

            resistance_distance = distance
            nearest_resistance = level

    near_support = (
        nearest_support is not None
        and
        support_distance <= protection
    )

    near_resistance = (
        nearest_resistance is not None
        and
        resistance_distance <= protection
    )

    return {
        "in_zone": (
            near_support
            or
            near_resistance
        ),
        "near_support": near_support,
        "near_resistance": near_resistance,
        "support_level": nearest_support,
        "resistance_level": nearest_resistance
    }


# ============================================================
# PULLBACK
# ============================================================


def detect_pullback(df, direction):

    if len(df) < PULLBACK_LOOKBACK:

        return True

    data = df.tail(
        PULLBACK_LOOKBACK
    )

    current = data.iloc[-1]

    close = safe_float(
        current["close"]
    )

    ema9 = safe_float(
        current["ema9"]
    )

    ema21 = safe_float(
        current["ema21"]
    )

    atr = safe_float(
        current["atr"]
    )

    if atr <= 0:

        atr = safe_float(
            current["range"]
        )

    if atr <= 0:

        return True

    # --------------------------------------------------------
    # PULLBACK A EMA21
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            abs(close - ema21)
            <= atr * 0.40
            and
            close < ema9
        ):

            return True

    if direction == "bearish":

        if (
            abs(close - ema21)
            <= atr * 0.40
            and
            close > ema9
        ):

            return True

    # --------------------------------------------------------
    # RETROCESO DE ESTRUCTURA
    # --------------------------------------------------------

    previous = data.iloc[-2]

    if direction == "bullish":

        if (
            current["low"]
            <
            previous["low"]
        ):

            return True

    if direction == "bearish":

        if (
            current["high"]
            >
            previous["high"]
        ):

            return True

    return False


# ============================================================
# FINAL DE TENDENCIA
# ============================================================


def detect_end_of_trend(df, direction):

    if len(df) < 10:

        return True

    data = df.tail(10)

    current = data.iloc[-1]

    ema9 = safe_float(
        current["ema9"]
    )

    ema21 = safe_float(
        current["ema21"]
    )

    ema50 = safe_float(
        current["ema50"]
    )

    # --------------------------------------------------------
    # ESTRUCTURA EMA
    # --------------------------------------------------------

    if direction == "bullish":

        if not (
            ema9 > ema21 > ema50
        ):

            return True

    elif direction == "bearish":

        if not (
            ema9 < ema21 < ema50
        ):

            return True

    else:

        return True

    # --------------------------------------------------------
    # DEMASIADAS VELAS CONTRARIAS
    # --------------------------------------------------------

    if direction == "bullish":

        opposite = (
            data["direction"] == -1
        ).sum()

    else:

        opposite = (
            data["direction"] == 1
        ).sum()

    if opposite >= 4:

        return True

    # --------------------------------------------------------
    # PÉRDIDA DE SEPARACIÓN
    # --------------------------------------------------------

    gaps = (
        data["ema9"] -
        data["ema21"]
    ).abs()

    if len(gaps) >= 4:

        old_gap = safe_float(
            gaps.iloc[-4]
        )

        new_gap = safe_float(
            gaps.iloc[-1]
        )

        if (
            old_gap > 0
            and
            new_gap < old_gap * 0.45
        ):

            return True

    return False


# ============================================================
# CONTINUIDAD ALCISTA
# ============================================================


def bullish_continuity(df):

    if len(df) < 10:

        return False

    data = df.tail(6)

    current = data.iloc[-1]

    # --------------------------------------------------------
    # VELA ALCISTA
    # --------------------------------------------------------

    if current["close"] <= current["open"]:

        return False

    # --------------------------------------------------------
    # CUERPO FUERTE
    # --------------------------------------------------------

    if safe_float(
        current["body_ratio"]
    ) < 0.50:

        return False

    # --------------------------------------------------------
    # CIERRE CERCA DEL MÁXIMO
    # --------------------------------------------------------

    candle_range = safe_float(
        current["range"]
    )

    if candle_range <= 0:

        return False

    close_position = (
        current["close"] -
        current["low"]
    ) / candle_range

    if close_position < 0.65:

        return False

    # --------------------------------------------------------
    # MÍNIMO DE VELAS ALCISTAS
    # --------------------------------------------------------

    bullish_count = (
        data["direction"] == 1
    ).sum()

    if bullish_count < 4:

        return False

    # --------------------------------------------------------
    # HACER NUEVO MÁXIMO
    # --------------------------------------------------------

    if (
        current["high"]
        <=
        data["high"].iloc[-2]
    ):

        return False

    # --------------------------------------------------------
    # NO DEBE DEJAR GRAN MECHA SUPERIOR
    # --------------------------------------------------------

    if (
        current["upper_wick"]
        >
        current["body"] * 0.80
    ):

        return False

    return True


# ============================================================
# CONTINUIDAD BAJISTA
# ============================================================


def bearish_continuity(df):

    if len(df) < 10:

        return False

    data = df.tail(6)

    current = data.iloc[-1]

    # --------------------------------------------------------
    # VELA BAJISTA
    # --------------------------------------------------------

    if current["close"] >= current["open"]:

        return False

    # --------------------------------------------------------
    # CUERPO FUERTE
    # --------------------------------------------------------

    if safe_float(
        current["body_ratio"]
    ) < 0.50:

        return False

    # --------------------------------------------------------
    # CIERRE CERCA DEL MÍNIMO
    # --------------------------------------------------------

    candle_range = safe_float(
        current["range"]
    )

    if candle_range <= 0:

        return False

    close_position = (
        current["high"] -
        current["close"]
    ) / candle_range

    if close_position < 0.65:

        return False

    # --------------------------------------------------------
    # MÍNIMO DE VELAS BAJISTAS
    # --------------------------------------------------------

    bearish_count = (
        data["direction"] == -1
    ).sum()

    if bearish_count < 4:

        return False

    # --------------------------------------------------------
    # HACER NUEVO MÍNIMO
    # --------------------------------------------------------

    if (
        current["low"]
        >=
        data["low"].iloc[-2]
    ):

        return False

    # --------------------------------------------------------
    # NO DEBE DEJAR GRAN MECHA INFERIOR
    # --------------------------------------------------------

    if (
        current["lower_wick"]
        >
        current["body"] * 0.80
    ):

        return False

    return True


# ============================================================
# SCORE DE ESTRUCTURA
# ============================================================


def structure_score(df, direction):

    if len(df) < 15:

        return 0

    data = df.tail(12)

    score = 0

    current = data.iloc[-1]

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            current["ema9"]
            >
            current["ema21"]
            >
            current["ema50"]
        ):

            score += 1

    elif direction == "bearish":

        if (
            current["ema9"]
            <
            current["ema21"]
            <
            current["ema50"]
        ):

            score += 1

    # --------------------------------------------------------
    # ESTRUCTURA
    # --------------------------------------------------------

    if direction == "bullish":

        hh = 0
        hl = 0

        for i in range(1, len(data)):

            if (
                data["high"].iloc[i]
                >
                data["high"].iloc[i - 1]
            ):

                hh += 1

            if (
                data["low"].iloc[i]
                >
                data["low"].iloc[i - 1]
            ):

                hl += 1

        if hh >= 6:
            score += 1

        if hl >= 6:
            score += 1

    elif direction == "bearish":

        lh = 0
        ll = 0

        for i in range(1, len(data)):

            if (
                data["high"].iloc[i]
                <
                data["high"].iloc[i - 1]
            ):

                lh += 1

            if (
                data["low"].iloc[i]
                <
                data["low"].iloc[i - 1]
            ):

                ll += 1

        if lh >= 6:
            score += 1

        if ll >= 6:
            score += 1

    # --------------------------------------------------------
    # VELAS
    # --------------------------------------------------------

    if direction == "bullish":

        count = (
            data["direction"] == 1
        ).sum()

    else:

        count = (
            data["direction"] == -1
        ).sum()

    if count >= 7:

        score += 1

    return score


# ============================================================
# ANALYZE MARKET
# ============================================================


def analyze_market(df):

    """
    FUNCIÓN PRINCIPAL PARA BOT.PY

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

    La estrategia NO ejecuta operaciones.
    """

    # ========================================================
    # VALIDAR
    # ========================================================

    if not validate_dataframe(df):

        return {
            "signal": None,
            "direction": "range",
            "reason": "DataFrame inválido",
            "score": 0
        }

    # ========================================================
    # PREPARAR
    # ========================================================

    df = prepare_dataframe(
        df
    )

    if len(df) < MIN_CANDLES:

        return {
            "signal": None,
            "direction": "range",
            "reason": "Velas insuficientes",
            "score": 0
        }

    # ========================================================
    # INDICADORES
    # ========================================================

    df = add_indicators(
        df
    )

    # ========================================================
    # ========================================================
    # PRIMER FILTRO: UBICACIÓN
    #
    # LA UBICACIÓN ES MÁS IMPORTANTE QUE EL MOMENTUM.
    #
    # Si estamos en soporte/resistencia:
    #
    #       NO SE SIGUE ANALIZANDO.
    #
    # ========================================================
    # ========================================================

    sr = check_support_resistance(
        df
    )

    if sr["in_zone"]:

        if (
            sr["near_support"]
            and
            sr["near_resistance"]
        ):

            reason = (
                "Precio dentro de zona "
                "de soporte/resistencia"
            )

        elif sr["near_support"]:

            reason = (
                "PRECIO EN SOPORTE - "
                "OPERACIÓN BLOQUEADA"
            )

        else:

            reason = (
                "PRECIO EN RESISTENCIA - "
                "OPERACIÓN BLOQUEADA"
            )

        return {
            "signal": None,
            "direction": "range",
            "reason": reason,
            "score": 0,
            "support_level": sr["support_level"],
            "resistance_level": sr["resistance_level"]
        }

    # ========================================================
    # ESTRUCTURA
    # ========================================================

    structure = detect_structure(
        df
    )

    structure_direction = (
        structure["structure"]
    )

    # ========================================================
    # TENDENCIA
    # ========================================================

    trend = detect_trend(
        df
    )

    if trend not in (
        "bullish",
        "bearish"
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": "No existe tendencia clara",
            "score": 0
        }

    # ========================================================
    # ESTRUCTURA DEBE COINCIDIR
    # ========================================================

    if structure_direction != trend:

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
    # FUERZA
    # ========================================================

    strength = trend_strength(
        df,
        trend
    )

    if strength < 4:

        return {
            "signal": None,
            "direction": trend,
            "reason": "Tendencia insuficientemente fuerte",
            "score": strength
        }

    # ========================================================
    # RECHAZO
    # ========================================================

    if detect_rejection(df):

        return {
            "signal": None,
            "direction": trend,
            "reason": "Rechazo detectado",
            "score": 0
        }

    # ========================================================
    # PULLBACK
    # ========================================================

    if detect_pullback(
        df,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": "Pullback detectado",
            "score": 0
        }

    # ========================================================
    # DEBILIDAD
    # ========================================================

    if detect_weakness(
        df,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": "Debilidad detectada",
            "score": 0
        }

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    if detect_end_of_trend(
        df,
        trend
    ):

        return {
            "signal": None,
            "direction": trend,
            "reason": "Final de tendencia detectado",
            "score": 0
        }

    # ========================================================
    # SCORE
    # ========================================================

    score = structure_score(
        df,
        trend
    )

    # Solo estructura fuerte
    if score < 4:

        return {
            "signal": None,
            "direction": trend,
            "reason": (
                "Score de continuidad insuficiente"
            ),
            "score": score
        }

    # ========================================================
    # CONTINUIDAD ALCISTA
    # ========================================================

    if trend == "bullish":

        if not bullish_continuity(df):

            return {
                "signal": None,
                "direction": "bullish",
                "reason": (
                    "No existe continuidad alcista válida"
                ),
                "score": score
            }

        # ----------------------------------------------------
        # SEGUNDA PROTECCIÓN S/R
        # ----------------------------------------------------

        sr_final = check_support_resistance(
            df
        )

        if sr_final["near_resistance"]:

            return {
                "signal": None,
                "direction": "bullish",
                "reason": (
                    "CALL bloqueado: "
                    "cerca de resistencia"
                ),
                "score": score,
                "resistance_level": (
                    sr_final["resistance_level"]
                )
            }

        return {
            "signal": "call",
            "direction": "bullish",
            "reason": (
                "CONTINUIDAD ALCISTA "
                "CONFIRMADA - ZONA LIBRE"
            ),
            "score": score,
            "support_level": (
                sr_final["support_level"]
            ),
            "resistance_level": (
                sr_final["resistance_level"]
            )
        }

    # ========================================================
    # CONTINUIDAD BAJISTA
    # ========================================================

    if trend == "bearish":

        if not bearish_continuity(df):

            return {
                "signal": None,
                "direction": "bearish",
                "reason": (
                    "No existe continuidad bajista válida"
                ),
                "score": score
            }

        # ----------------------------------------------------
        # SEGUNDA PROTECCIÓN S/R
        # ----------------------------------------------------

        sr_final = check_support_resistance(
            df
        )

        if sr_final["near_support"]:

            return {
                "signal": None,
                "direction": "bearish",
                "reason": (
                    "PUT bloqueado: "
                    "cerca de soporte"
                ),
                "score": score,
                "support_level": (
                    sr_final["support_level"]
                )
            }

        return {
            "signal": "put",
            "direction": "bearish",
            "reason": (
                "CONTINUIDAD BAJISTA "
                "CONFIRMADA - ZONA LIBRE"
            ),
            "score": score,
            "support_level": (
                sr_final["support_level"]
            ),
            "resistance_level": (
                sr_final["resistance_level"]
            )
        }

    # ========================================================
    # SIN OPERACIÓN
    # ========================================================

    return {
        "signal": None,
        "direction": trend,
        "reason": "Sin continuidad",
        "score": score
    }


# ============================================================
# FUNCIÓN SIMPLE PARA BOT.PY
# ============================================================


def get_signal(df):

    result = analyze_market(
        df
    )

    return result.get(
        "signal"
    )


# ============================================================
# INFORMACIÓN DE LA ESTRATEGIA
# ============================================================


def strategy_info():

    return {
        "timeframe": "1m",
        "max_candles": MAX_CANDLES,
        "strategy": "continuidad",
        "trend_filter": True,
        "support_filter": True,
        "resistance_filter": True,
        "rejection_filter": True,
        "pullback_filter": True,
        "weakness_filter": True,
        "end_of_trend_filter": True
    }


# ============================================================
# PRUEBA
# ============================================================


if __name__ == "__main__":

    print("=" * 60)
    print("STRATEGY.PY CARGADO CORRECTAMENTE")
    print("=" * 60)

    print(
        "Estrategia: CONTINUIDAD"
    )

    print(
        "Timeframe: 1 MINUTO"
    )

    print(
        "Máximo de velas:",
        MAX_CANDLES
    )

    print(
        "Soporte: BLOQUEADO"
    )

    print(
        "Resistencia: BLOQUEADO"
    )

    print(
        "Rechazo: BLOQUEADO"
    )

    print(
        "Pullback: BLOQUEADO"
    )

    print(
        "Debilidad: BLOQUEADO"
    )

    print(
        "Final de tendencia: BLOQUEADO"
    )

    print(
        "Función:",
        "analyze_market(df)"
    )

    print("=" * 60)
