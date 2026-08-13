from __future__ import annotations
from typing import Any, Dict, Optional
import math
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

MAX_CANDLES = 60

EMA_FAST = 9
EMA_SLOW = 21

ATR_PERIOD = 14

STRUCTURE_LOOKBACK = 8
SR_LOOKBACK = 20


# ============================================================
# FILTROS
# ============================================================

# Distancia mínima respecto a soporte/resistencia.
SR_ATR_DISTANCE = 0.45

# Detección de rechazo.
REJECTION_WICK_RATIO = 0.55

# Cuerpo mínimo respecto al ATR.
MIN_BODY_ATR = 0.22

# Mecha contraria máxima permitida.
MAX_COUNTER_WICK_ATR = 0.65

# Evita operar demasiado cerca del extremo
# de la tendencia.
END_TREND_DISTANCE_ATR = 0.75

EPS = 1e-12


# ============================================================
# RESULTADO VACÍO
# ============================================================

def _empty_result(
    reason: str = "Sin señal"
) -> Dict[str, Any]:

    return {
        "signal": None,
        "direction": "range",
        "reason": reason,
        "score": 0,
        "trend": "range",
        "continuity": False,
        "blocked": True,
        "zone": None,
    }


# ============================================================
# VALIDAR DATAFRAME
# ============================================================

def _validate_df(
    df: pd.DataFrame
) -> Optional[pd.DataFrame]:

    if (
        df is None
        or not isinstance(df, pd.DataFrame)
        or df.empty
    ):
        return None

    required = {
        "open",
        "high",
        "low",
        "close"
    }

    if not required.issubset(
        df.columns
    ):
        return None

    work = df.copy()

    # --------------------------------------------------------
    # CONVERTIR PRECIOS
    # --------------------------------------------------------

    for col in required:

        work[col] = pd.to_numeric(
            work[col],
            errors="coerce"
        )

    work.dropna(
        subset=list(required),
        inplace=True
    )

    # --------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------

    if "from" in work.columns:

        work["from"] = pd.to_numeric(
            work["from"],
            errors="coerce"
        )

        work.dropna(
            subset=["from"],
            inplace=True
        )

        work.sort_values(
            "from",
            inplace=True
        )

    # --------------------------------------------------------
    # MÁXIMO 60 VELAS
    # --------------------------------------------------------

    work.reset_index(
        drop=True,
        inplace=True
    )

    if len(work) > MAX_CANDLES:

        work = work.tail(
            MAX_CANDLES
        ).reset_index(
            drop=True
        )

    return work


# ============================================================
# ATR
# ============================================================

def _atr(
    df: pd.DataFrame,
    period: int = ATR_PERIOD
) -> float:

    previous_close = (
        df["close"].shift(1)
    )

    true_range = pd.concat(
        [
            df["high"] - df["low"],

            (
                df["high"]
                - previous_close
            ).abs(),

            (
                df["low"]
                - previous_close
            ).abs(),
        ],
        axis=1
    ).max(axis=1)

    value = (
        true_range.tail(
            period
        ).mean()
    )

    if (
        pd.isna(value)
        or value <= 0
    ):

        last_range = (
            df["high"].iloc[-1]
            - df["low"].iloc[-1]
        )

        return float(
            max(last_range, EPS)
        )

    return float(value)


# ============================================================
# EMA
# ============================================================

def _add_emas(
    df: pd.DataFrame
) -> pd.DataFrame:

    work = df.copy()

    work["ema_fast"] = (
        work["close"]
        .ewm(
            span=EMA_FAST,
            adjust=False
        )
        .mean()
    )

    work["ema_slow"] = (
        work["close"]
        .ewm(
            span=EMA_SLOW,
            adjust=False
        )
        .mean()
    )

    return work


# ============================================================
# ESTRUCTURA
# ============================================================

def _structure(
    df: pd.DataFrame
) -> str:

    """
    Determina estructura bullish, bearish o range.

    Usa las últimas velas disponibles,
    respetando el máximo de 60 velas.
    """

    if len(df) < (
        STRUCTURE_LOOKBACK + 1
    ):
        return "range"

    work = df.tail(
        STRUCTURE_LOOKBACK + 1
    )

    highs = work[
        "high"
    ].tolist()

    lows = work[
        "low"
    ].tolist()

    hh = 0
    hl = 0
    lh = 0
    ll = 0

    for i in range(
        1,
        len(work)
    ):

        # --------------------------------
        # MÁXIMOS
        # --------------------------------

        if highs[i] > highs[i - 1]:

            hh += 1

        elif highs[i] < highs[i - 1]:

            lh += 1

        # --------------------------------
        # MÍNIMOS
        # --------------------------------

        if lows[i] > lows[i - 1]:

            hl += 1

        elif lows[i] < lows[i - 1]:

            ll += 1

    bullish_points = (
        hh + hl
    )

    bearish_points = (
        lh + ll
    )

    if (
        bullish_points >= 10
        and bullish_points
        >= bearish_points + 3
    ):

        return "bullish"

    if (
        bearish_points >= 10
        and bearish_points
        >= bullish_points + 3
    ):

        return "bearish"

    return "range"


# ============================================================
# TENDENCIA
# ============================================================

def _trend(
    df: pd.DataFrame
) -> str:

    if len(df) < (
        EMA_SLOW + 5
    ):

        return "range"

    work = _add_emas(
        df
    )

    fast = float(
        work[
            "ema_fast"
        ].iloc[-1]
    )

    slow = float(
        work[
            "ema_slow"
        ].iloc[-1]
    )

    lookback = min(
        4,
        len(work) - 1
    )

    fast_previous = float(
        work[
            "ema_fast"
        ].iloc[
            -1 - lookback
        ]
    )

    slow_previous = float(
        work[
            "ema_slow"
        ].iloc[
            -1 - lookback
        ]
    )

    structure = _structure(
        work
    )

    bullish = (
        fast > slow
        and fast >= fast_previous
        and slow >= slow_previous
        and structure == "bullish"
    )

    bearish = (
        fast < slow
        and fast <= fast_previous
        and slow <= slow_previous
        and structure == "bearish"
    )

    if bullish:

        return "bullish"

    if bearish:

        return "bearish"

    return "range"


# ============================================================
# MÉTRICAS DE VELA
# ============================================================

def _candle_metrics(
    candle: pd.Series
) -> Dict[str, float]:

    open_price = float(
        candle["open"]
    )

    high = float(
        candle["high"]
    )

    low = float(
        candle["low"]
    )

    close = float(
        candle["close"]
    )

    body = abs(
        close - open_price
    )

    candle_range = max(
        high - low,
        EPS
    )

    upper_wick = max(
        high
        - max(
            open_price,
            close
        ),
        0.0
    )

    lower_wick = max(
        min(
            open_price,
            close
        )
        - low,
        0.0
    )

    return {
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "body": body,
        "range": candle_range,
        "upper": upper_wick,
        "lower": lower_wick,
    }


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def _near_sr(
    history: pd.DataFrame,
    price: float,
    atr: float
) -> tuple[
    bool,
    Optional[str],
    Optional[float]
]:

    """
    Bloqueo absoluto cerca de soporte/resistencia.

    IMPORTANTE:
    history NO incluye la vela viva.
    """

    if len(history) < 5:

        return (
            True,
            "insuficiente_historial",
            None
        )

    work = history.tail(
        SR_LOOKBACK
    )

    recent_high = float(
        work["high"].max()
    )

    recent_low = float(
        work["low"].min()
    )

    tolerance = max(
        atr * SR_ATR_DISTANCE,
        EPS
    )

    distance_high = abs(
        price - recent_high
    )

    distance_low = abs(
        price - recent_low
    )

    # --------------------------------------------------------
    # RESISTENCIA
    # --------------------------------------------------------

    if (
        distance_high
        <= tolerance
    ):

        return (
            True,
            "resistencia",
            recent_high
        )

    # --------------------------------------------------------
    # SOPORTE
    # --------------------------------------------------------

    if (
        distance_low
        <= tolerance
    ):

        return (
            True,
            "soporte",
            recent_low
        )

    return (
        False,
        None,
        None
    )


# ============================================================
# RECHAZO
# ============================================================

def _rejection(
    candle: Dict[str, float],
    direction: str
) -> bool:

    body = candle[
        "body"
    ]

    candle_range = candle[
        "range"
    ]

    # --------------------------------------------------------
    # TENDENCIA ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        # Mecha superior dominante.
        if (
            candle["upper"]
            / candle_range
            >= REJECTION_WICK_RATIO
        ):

            return True

        # Rechazo inferior excesivo.
        if (
            candle["lower"]
            > body * 2.8
            and
            candle["lower"]
            / candle_range
            > 0.45
        ):

            return True

    # --------------------------------------------------------
    # TENDENCIA BAJISTA
    # --------------------------------------------------------

    else:

        # Mecha inferior dominante.
        if (
            candle["lower"]
            / candle_range
            >= REJECTION_WICK_RATIO
        ):

            return True

        # Rechazo superior excesivo.
        if (
            candle["upper"]
            > body * 2.8
            and
            candle["upper"]
            / candle_range
            > 0.45
        ):

            return True

    return False


# ============================================================
# DEBILIDAD
# ============================================================

def _weakness(
    live: Dict[str, float],
    previous: Dict[str, float],
    direction: str,
    atr: float
) -> bool:

    # --------------------------------------------------------
    # CUERPO MUY PEQUEÑO
    # --------------------------------------------------------

    if (
        live["body"]
        < atr * MIN_BODY_ATR
    ):

        return True

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        # No está haciendo continuidad.
        if (
            live["close"]
            <= previous["close"]
        ):

            return True

        # Mecha contraria demasiado grande.
        if (
            live["upper"]
            > atr * MAX_COUNTER_WICK_ATR
        ):

            return True

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    else:

        if (
            live["close"]
            >= previous["close"]
        ):

            return True

        if (
            live["lower"]
            > atr * MAX_COUNTER_WICK_ATR
        ):

            return True

    return False


# ============================================================
# PULLBACK
# ============================================================

def _pullback(
    live: Dict[str, float],
    previous: Dict[str, float],
    direction: str,
    atr: float
) -> bool:

    """
    Bloquea una vela que esté funcionando
    como retroceso contra la tendencia.
    """

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        if (
            live["open"]
            <
            previous["close"]
            - 0.20 * atr
        ):

            return True

        if (
            live["close"]
            <= live["open"]
        ):

            return True

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    else:

        if (
            live["open"]
            >
            previous["close"]
            + 0.20 * atr
        ):

            return True

        if (
            live["close"]
            >= live["open"]
        ):

            return True

    return False


# ============================================================
# FINAL DE TENDENCIA
# ============================================================

def _end_of_trend(
    history: pd.DataFrame,
    live: Dict[str, float],
    direction: str,
    atr: float
) -> bool:

    """
    Evita operar demasiado cerca
    del extremo de la estructura.
    """

    if history.empty:

        return True

    work = history.tail(
        SR_LOOKBACK
    )

    recent_high = float(
        work["high"].max()
    )

    recent_low = float(
        work["low"].min()
    )

    price = live[
        "close"
    ]

    # --------------------------------------------------------
    # ALCISTA
    # --------------------------------------------------------

    if direction == "bullish":

        distance_to_high = (
            recent_high
            - price
        )

        if (
            distance_to_high
            <= atr
            * END_TREND_DISTANCE_ATR
        ):

            return True

    # --------------------------------------------------------
    # BAJISTA
    # --------------------------------------------------------

    else:

        distance_to_low = (
            price
            - recent_low
        )

        if (
            distance_to_low
            <= atr
            * END_TREND_DISTANCE_ATR
        ):

            return True

    return False


# ============================================================
# ANALIZAR MERCADO
# ============================================================

def analyze_market(
    df: pd.DataFrame
) -> Dict[str, Any]:

    """
    Analiza como máximo las últimas 60 velas de 1 minuto.

    df.iloc[-1]
        = vela viva.

    df.iloc[-2]
        = vela anterior.

    IMPORTANTE:
    Esta función NO ejecuta operaciones.
    """

    # --------------------------------------------------------
    # VALIDAR
    # --------------------------------------------------------

    work = _validate_df(
        df
    )

    if (
        work is None
        or len(work)
        < max(
            EMA_SLOW + 5,
            30
        )
    ):

        return _empty_result(
            "Historial insuficiente"
        )

    # --------------------------------------------------------
    # EMA
    # --------------------------------------------------------

    work = _add_emas(
        work
    )

    # --------------------------------------------------------
    # VELA VIVA
    # --------------------------------------------------------

    live = work.iloc[-1]

    # --------------------------------------------------------
    # VELA ANTERIOR
    # --------------------------------------------------------

    previous = work.iloc[-2]

    # --------------------------------------------------------
    # HISTORIAL CERRADO
    # --------------------------------------------------------

    history = work.iloc[:-1]

    if len(history) < 25:

        return _empty_result(
            "Historial cerrado insuficiente"
        )

    # --------------------------------------------------------
    # ATR
    # --------------------------------------------------------

    atr = _atr(
        history
    )

    # --------------------------------------------------------
    # TENDENCIA
    # --------------------------------------------------------

    direction = _trend(
        history
    )

    # ========================================================
    # RESULTADO BASE
    # ========================================================

    result: Dict[str, Any] = {

        "signal": None,

        "direction":
            direction,

        "trend":
            direction,

        "reason":
            "",

        "score":
            0,

        "continuity":
            False,

        "blocked":
            True,

        "zone":
            None,

        "atr":
            atr,

        "candle_timestamp":
            (
                int(
                    live["from"]
                )
                if (
                    "from"
                    in work.columns
                    and
                    not pd.isna(
                        live["from"]
                    )
                )
                else None
            ),
    }

    # ========================================================
    # SIN TENDENCIA
    # ========================================================

    if direction not in (
        "bullish",
        "bearish"
    ):

        result[
            "reason"
        ] = (
            "No existe tendencia clara"
        )

        return result

    # ========================================================
    # MÉTRICAS
    # ========================================================

    live_candle = _candle_metrics(
        live
    )

    previous_candle = _candle_metrics(
        previous
    )

    # ========================================================
    # SOPORTE / RESISTENCIA
    # ========================================================

    blocked, zone, level = _near_sr(
        history,
        live_candle["close"],
        atr
    )

    if blocked:

        result[
            "reason"
        ] = (
            f"Precio en {zone}"
        )

        result[
            "zone"
        ] = zone

        result[
            "level"
        ] = level

        return result

    # ========================================================
    # RECHAZO
    # ========================================================

    if _rejection(
        live_candle,
        direction
    ):

        result[
            "reason"
        ] = (
            "Rechazo detectado"
        )

        return result

    # ========================================================
    # PULLBACK
    # ========================================================

    if _pullback(
        live_candle,
        previous_candle,
        direction,
        atr
    ):

        result[
            "reason"
        ] = (
            "Pullback detectado"
        )

        return result

    # ========================================================
    # DEBILIDAD
    # ========================================================

    if _weakness(
        live_candle,
        previous_candle,
        direction,
        atr
    ):

        result[
            "reason"
        ] = (
            "Debilidad detectada"
        )

        return result

    # ========================================================
    # FINAL DE TENDENCIA
    # ========================================================

    if _end_of_trend(
        history,
        live_candle,
        direction,
        atr
    ):

        result[
            "reason"
        ] = (
            "Final/extensión de tendencia"
        )

        return result

    # ========================================================
    # IMPORTANTE
    # ========================================================
    #
    # Inicializamos signal ANTES de utilizarla.
    #
    # Esto evita:
    #
    # name 'signal' is not defined
    #
    # ========================================================

    signal = None

    valid = False

    # ========================================================
    # CONTINUIDAD ALCISTA
    # ========================================================

    if direction == "bullish":

        valid = (
            live_candle["close"]
            >
            live_candle["open"]

            and

            live_candle["close"]
            >
            previous_candle["close"]

            and

            live_candle["body"]
            >=
            atr * MIN_BODY_ATR

            and

            live_candle["close"]
            >=
            (
                live_candle["low"]
                +
                live_candle["range"]
                * 0.55
            )
        )

        if valid:

            signal = "call"

    # ========================================================
    # CONTINUIDAD BAJISTA
    # ========================================================

    elif direction == "bearish":

        valid = (
            live_candle["close"]
            <
            live_candle["open"]

            and

            live_candle["close"]
            <
            previous_candle["close"]

            and

            live_candle["body"]
            >=
            atr * MIN_BODY_ATR

            and

            live_candle["close"]
            <=
            (
                live_candle["high"]
                -
                live_candle["range"]
                * 0.55
            )
        )

        if valid:

            signal = "put"

    # ========================================================
    # NO HAY CONTINUIDAD
    # ========================================================

    if signal is None:

        result[
            "reason"
        ] = (
            "Continuidad no confirmada"
        )

        return result

    # ========================================================
    # CONTINUIDAD CONFIRMADA
    # ========================================================

    result.update({

        "signal":
            signal,

        "reason":
            "Continuidad confirmada",

        "score":
            5,

        "continuity":
            True,

        "blocked":
            False,

        "zone":
            "continuidad",

        "signal_price":
            live_candle["close"],

        "candle_open":
            live_candle["open"],

        "candle_close":
            live_candle["close"],
    })

    return result


# ============================================================
# COMPATIBILIDAD
# ============================================================

def candle_direction(
    candle: pd.Series
) -> str:

    if (
        float(candle["close"])
        >
        float(candle["open"])
    ):

        return "bull"

    if (
        float(candle["close"])
        <
        float(candle["open"])
    ):

        return "bear"

    return "neutral"


# ============================================================
# DETECTAR ESTRUCTURA
# ============================================================

def detect_structure(
    df: pd.DataFrame
) -> str:

    work = _validate_df(
        df
    )

    if work is None:

        return "range"

    return _structure(
        work.tail(
            MAX_CANDLES
        )
    )


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def is_near_sr(
    df: pd.DataFrame,
    tolerance: float = 0.0003
) -> bool:

    work = _validate_df(
        df
    )

    if (
        work is None
        or len(work) < 5
    ):

        return True

    price = float(
        work[
            "close"
        ].iloc[-1]
    )

    high = float(
        work[
            "high"
        ].tail(
            SR_LOOKBACK
        ).max()
    )

    low = float(
        work[
            "low"
        ].tail(
            SR_LOOKBACK
        ).min()
    )

    return (
        abs(
            price - high
        )
        <= tolerance

        or

        abs(
            price - low
        )
        <= tolerance
    )
