from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd


# ============================================================
# ESTRATEGIA 1M + MICROVELAS DE 5 SEGUNDOS
# ============================================================
#
# LOGICA ORIGINAL — NO SE CAMBIA
#
# CALL:
#
# 1. Primera 5s cierra POR ENCIMA de apertura 1M.
# 2. Después existe al menos una 5s que cierra
#    POR DEBAJO de apertura 1M.
# 3. La vela 1M termina VERDE.
# 4. Continuidad compradora.
# 5. Confirmaciones adicionales.
# 6. Se prepara CALL para N+1.
#
#
# PUT:
#
# 1. Primera 5s cierra POR DEBAJO de apertura 1M.
# 2. Después existe al menos una 5s que cierra
#    POR ENCIMA de apertura 1M.
# 3. La vela 1M termina ROJA.
# 4. Continuidad vendedora.
# 5. Confirmaciones adicionales.
# 6. Se prepara PUT para N+1.
#
#
# CONFIRMACIONES AÑADIDAS:
#
# - EMA
# - RSI
# - VOLUMEN
# - TENDENCIA
# - SCORE
# - MAYORÍA
#
#
# IMPORTANTE:
#
# Estas confirmaciones NO crean una señal.
#
# Primero debe cumplirse:
#
#       LOGICA ORIGINAL
#              +
#       CONTINUIDAD DOMINANTE
#
# Después se aplican las confirmaciones.
#
# ============================================================


# ============================================================
# CONFIGURACION DE CONFIRMACIONES
# ============================================================

EMA_FAST_PERIOD = 5
EMA_SLOW_PERIOD = 9

RSI_PERIOD = 7

MIN_SCORE = 4

# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


# ============================================================
# NORMALIZAR MICROVELAS 5S
# ============================================================

def _normalize_5s(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename = {}

    if "max" in out.columns and "high" not in out.columns:
        rename["max"] = "high"

    if "min" in out.columns and "low" not in out.columns:
        rename["min"] = "low"

    if "Open" in out.columns and "open" not in out.columns:
        rename["Open"] = "open"

    if "High" in out.columns and "high" not in out.columns:
        rename["High"] = "high"

    if "Low" in out.columns and "low" not in out.columns:
        rename["Low"] = "low"

    if "Close" in out.columns and "close" not in out.columns:
        rename["Close"] = "close"

    if "Volume" in out.columns and "volume" not in out.columns:
        rename["Volume"] = "volume"

    if rename:
        out.rename(
            columns=rename,
            inplace=True,
        )

    if "open" not in out.columns:
        return pd.DataFrame()

    if "close" not in out.columns:
        return pd.DataFrame()

    out["open"] = pd.to_numeric(
        out["open"],
        errors="coerce",
    )

    out["close"] = pd.to_numeric(
        out["close"],
        errors="coerce",
    )

    if "high" in out.columns:

        out["high"] = pd.to_numeric(
            out["high"],
            errors="coerce",
        )

    if "low" in out.columns:

        out["low"] = pd.to_numeric(
            out["low"],
            errors="coerce",
        )

    if "volume" in out.columns:

        out["volume"] = pd.to_numeric(
            out["volume"],
            errors="coerce",
        )

    if "from" in out.columns:

        out["from"] = pd.to_numeric(
            out["from"],
            errors="coerce",
        )

        out.dropna(
            subset=["from"],
            inplace=True,
        )

        out.sort_values(
            "from",
            inplace=True,
        )

    out.dropna(
        subset=["open", "close"],
        inplace=True,
    )

    out.reset_index(
        drop=True,
        inplace=True,
    )

    return out


# ============================================================
# VALIDAR SECUENCIA 5S
# ============================================================

def _validate_5s_sequence(
    micro: pd.DataFrame,
) -> bool:

    if micro.empty:
        return False

    if "from" not in micro.columns:
        return True

    if len(micro) < 2:
        return False

    timestamps = (
        micro["from"]
        .astype(float)
        .tolist()
    )

    for i in range(1, len(timestamps)):

        difference = (
            timestamps[i]
            - timestamps[i - 1]
        )

        if difference != 5:
            return False

    return True


# ============================================================
# FILTRAR MICROVELAS DEL MINUTO
# ============================================================

def _get_minute_micro_candles(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> pd.DataFrame:

    micro = _normalize_5s(
        candles_5s
    )

    if micro.empty:
        return pd.DataFrame()

    minute_timestamp = None

    if candle_1m is not None:

        try:

            if "from" in candle_1m.index:

                minute_timestamp = int(
                    float(
                        candle_1m["from"]
                    )
                )

        except (TypeError, ValueError):

            minute_timestamp = None

    if (
        minute_timestamp is not None
        and "from" in micro.columns
    ):

        start_time = minute_timestamp

        end_time = (
            minute_timestamp + 60
        )

        micro = micro[
            (micro["from"] >= start_time)
            &
            (micro["from"] < end_time)
        ].copy()

        micro.sort_values(
            "from",
            inplace=True,
        )

        micro.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        micro.reset_index(
            drop=True,
            inplace=True,
        )

    return micro


# ============================================================
# CONTINUIDAD COMPRADORA
# ============================================================

def _buyer_continuity_confirmed(
    micro: pd.DataFrame,
    opening: float,
) -> bool:

    if micro.empty:
        return False

    pullback_indexes = []

    for i in range(1, len(micro)):

        close_value = _to_float(
            micro.iloc[i]["close"]
        )

        if close_value is None:
            continue

        if close_value < opening:

            pullback_indexes.append(i)

    if not pullback_indexes:
        return False

    last_pullback = (
        pullback_indexes[-1]
    )

    if last_pullback >= len(micro) - 1:
        return False

    continuation = micro.iloc[
        last_pullback + 1:
    ].copy()

    if continuation.empty:
        return False

    recovered = False

    for _, candle in continuation.iterrows():

        close_value = _to_float(
            candle["close"]
        )

        if close_value is None:
            continue

        if close_value > opening:

            recovered = True
            break

    if not recovered:
        return False

    last_close = _to_float(
        continuation.iloc[-1]["close"]
    )

    if last_close is None:
        return False

    if last_close <= opening:
        return False

    if len(continuation) >= 2:

        previous_close = _to_float(
            continuation.iloc[-2]["close"]
        )

        current_close = _to_float(
            continuation.iloc[-1]["close"]
        )

        if (
            previous_close is None
            or current_close is None
        ):
            return False

        if current_close <= previous_close:
            return False

    return True


# ============================================================
# CONTINUIDAD VENDEDORA
# ============================================================

def _seller_continuity_confirmed(
    micro: pd.DataFrame,
    opening: float,
) -> bool:

    if micro.empty:
        return False

    pullback_indexes = []

    for i in range(1, len(micro)):

        close_value = _to_float(
            micro.iloc[i]["close"]
        )

        if close_value is None:
            continue

        if close_value > opening:

            pullback_indexes.append(i)

    if not pullback_indexes:
        return False

    last_pullback = (
        pullback_indexes[-1]
    )

    if last_pullback >= len(micro) - 1:
        return False

    continuation = micro.iloc[
        last_pullback + 1:
    ].copy()

    if continuation.empty:
        return False

    recovered = False

    for _, candle in continuation.iterrows():

        close_value = _to_float(
            candle["close"]
        )

        if close_value is None:
            continue

        if close_value < opening:

            recovered = True
            break

    if not recovered:
        return False

    last_close = _to_float(
        continuation.iloc[-1]["close"]
    )

    if last_close is None:
        return False

    if last_close >= opening:
        return False

    if len(continuation) >= 2:

        previous_close = _to_float(
            continuation.iloc[-2]["close"]
        )

        current_close = _to_float(
            continuation.iloc[-1]["close"]
        )

        if (
            previous_close is None
            or current_close is None
        ):
            return False

        if current_close >= previous_close:
            return False

    return True


# ============================================================
# EMA
# ============================================================

def _calculate_ema(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "ema_fast": None,
        "ema_slow": None,
        "ema_bullish": False,
        "ema_bearish": False,
    }

    if "close" not in micro.columns:
        return result

    if len(micro) < EMA_SLOW_PERIOD:
        return result

    closes = pd.to_numeric(
        micro["close"],
        errors="coerce",
    )

    if closes.isna().any():
        return result

    ema_fast = closes.ewm(
        span=EMA_FAST_PERIOD,
        adjust=False,
    ).mean()

    ema_slow = closes.ewm(
        span=EMA_SLOW_PERIOD,
        adjust=False,
    ).mean()

    fast = _to_float(
        ema_fast.iloc[-1]
    )

    slow = _to_float(
        ema_slow.iloc[-1]
    )

    last_close = _to_float(
        closes.iloc[-1]
    )

    if (
        fast is None
        or slow is None
        or last_close is None
    ):
        return result

    result["ema_fast"] = fast
    result["ema_slow"] = slow

    result["ema_bullish"] = (
        fast > slow
        and last_close > fast
    )

    result["ema_bearish"] = (
        fast < slow
        and last_close < fast
    )

    return result


# ============================================================
# RSI
# ============================================================

def _calculate_rsi(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "rsi": None,
        "rsi_bullish": False,
        "rsi_bearish": False,
    }

    if "close" not in micro.columns:
        return result

    if len(micro) < RSI_PERIOD + 1:
        return result

    closes = pd.to_numeric(
        micro["close"],
        errors="coerce",
    )

    if closes.isna().any():
        return result

    delta = closes.diff()

    gains = delta.clip(
        lower=0
    )

    losses = (
        -delta.clip(
            upper=0
        )
    )

    average_gain = gains.rolling(
        RSI_PERIOD
    ).mean()

    average_loss = losses.rolling(
        RSI_PERIOD
    ).mean()

    gain = _to_float(
        average_gain.iloc[-1]
    )

    loss = _to_float(
        average_loss.iloc[-1]
    )

    if gain is None or loss is None:
        return result

    if loss == 0:

        rsi = 100.0

    else:

        relative_strength = (
            gain / loss
        )

        rsi = (
            100
            -
            (
                100
                /
                (
                    1
                    +
                    relative_strength
                )
            )
        )

    result["rsi"] = rsi

    # --------------------------------------------------------
    # Confirmación compradora
    # --------------------------------------------------------

    result["rsi_bullish"] = (
        50 < rsi < 70
    )

    # --------------------------------------------------------
    # Confirmación vendedora
    # --------------------------------------------------------

    result["rsi_bearish"] = (
        30 < rsi < 50
    )

    return result


# ============================================================
# VOLUMEN
# ============================================================

def _volume_confirmation(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "volume_available": False,
        "volume_bullish": False,
        "volume_bearish": False,
        "volume_current": None,
        "volume_average": None,
    }

    if "volume" not in micro.columns:
        return result

    if len(micro) < 3:
        return result

    volumes = pd.to_numeric(
        micro["volume"],
        errors="coerce",
    )

    if volumes.isna().all():
        return result

    volumes = volumes.dropna()

    if len(volumes) < 3:
        return result

    current_volume = _to_float(
        volumes.iloc[-1]
    )

    previous_volumes = volumes.iloc[
        :-1
    ]

    average_volume = _to_float(
        previous_volumes.mean()
    )

    if (
        current_volume is None
        or average_volume is None
    ):
        return result

    result["volume_available"] = True

    result[
        "volume_current"
    ] = current_volume

    result[
        "volume_average"
    ] = average_volume

    # --------------------------------------------------------
    # El volumen debe superar el promedio.
    # --------------------------------------------------------

    if current_volume <= average_volume:
        return result

    # --------------------------------------------------------
    # Determinar dominio por última microvela.
    # --------------------------------------------------------

    last = micro.iloc[-1]

    last_open = _to_float(
        last["open"]
    )

    last_close = _to_float(
        last["close"]
    )

    if (
        last_open is None
        or last_close is None
    ):
        return result

    if last_close > last_open:

        result[
            "volume_bullish"
        ] = True

    elif last_close < last_open:

        result[
            "volume_bearish"
        ] = True

    return result


# ============================================================
# TENDENCIA
# ============================================================

def _trend_confirmation(
    micro: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "trend": "neutral",
        "trend_bullish": False,
        "trend_bearish": False,
    }

    if len(micro) < 3:
        return result

    closes = pd.to_numeric(
        micro["close"],
        errors="coerce",
    )

    if closes.isna().any():
        return result

    first = _to_float(
        closes.iloc[-3]
    )

    second = _to_float(
        closes.iloc[-2]
    )

    third = _to_float(
        closes.iloc[-1]
    )

    if (
        first is None
        or second is None
        or third is None
    ):
        return result

    # --------------------------------------------------------
    # Tendencia compradora
    # --------------------------------------------------------

    if (
        third > second
        and second > first
    ):

        result[
            "trend"
        ] = "bullish"

        result[
            "trend_bullish"
        ] = True

        return result

    # --------------------------------------------------------
    # Tendencia vendedora
    # --------------------------------------------------------

    if (
        third < second
        and second < first
    ):

        result[
            "trend"
        ] = "bearish"

        result[
            "trend_bearish"
        ] = True

        return result

    return result


# ============================================================
# CONFIRMACIONES + SCORE + MAYORIA
# ============================================================

def _additional_confirmations(
    micro: pd.DataFrame,
    signal: str,
) -> Dict[str, Any]:

    ema = _calculate_ema(
        micro
    )

    rsi = _calculate_rsi(
        micro
    )

    volume = _volume_confirmation(
        micro
    )

    trend = _trend_confirmation(
        micro
    )

    confirmations = []

    # ========================================================
    # EMA
    # ========================================================

    if signal == "call":

        ema_ok = bool(
            ema["ema_bullish"]
        )

    else:

        ema_ok = bool(
            ema["ema_bearish"]
        )

    confirmations.append(
        ema_ok
    )

    # ========================================================
    # RSI
    # ========================================================

    if signal == "call":

        rsi_ok = bool(
            rsi["rsi_bullish"]
        )

    else:

        rsi_ok = bool(
            rsi["rsi_bearish"]
        )

    confirmations.append(
        rsi_ok
    )

    # ========================================================
    # VOLUMEN
    # ========================================================

    if signal == "call":

        volume_ok = bool(
            volume["volume_bullish"]
        )

    else:

        volume_ok = bool(
            volume["volume_bearish"]
        )

    confirmations.append(
        volume_ok
    )

    # ========================================================
    # TENDENCIA
    # ========================================================

    if signal == "call":

        trend_ok = bool(
            trend["trend_bullish"]
        )

    else:

        trend_ok = bool(
            trend["trend_bearish"]
        )

    confirmations.append(
        trend_ok
    )

    # ========================================================
    # SCORE
    # ========================================================

    score = sum(
        1
        for confirmation
        in confirmations
        if confirmation
    )

    total_filters = len(
        confirmations
    )

    # ========================================================
    # MAYORIA
    # ========================================================

    majority = (
        score
        >
        total_filters / 2
    )

    # ========================================================
    # CONFIRMACION FINAL
    # ========================================================

    confirmed = (
        score >= MIN_SCORE
        and majority
    )

    return {

        "ema_fast": ema[
            "ema_fast"
        ],

        "ema_slow": ema[
            "ema_slow"
        ],

        "ema_confirmed": ema_ok,

        "rsi": rsi[
            "rsi"
        ],

        "rsi_confirmed": rsi_ok,

        "volume_current": volume[
            "volume_current"
        ],

        "volume_average": volume[
            "volume_average"
        ],

        "volume_confirmed": volume_ok,

        "trend": trend[
            "trend"
        ],

        "trend_confirmed": trend_ok,

        "score": score,

        "score_total": total_filters,

        "majority": majority,

        "confirmed": confirmed,
    }


# ============================================================
# ANALIZAR UNA VELA DE 1 MINUTO
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {

        "signal": None,

        "valid": False,

        "reason": "sin señal",

        "minute_timestamp": None,

        "minute_open": None,

        "minute_close": None,

        "first_5s_open": None,

        "first_5s_close": None,

        "pullback_count": 0,

        "continuity_confirmed": False,

        "ema_fast": None,

        "ema_slow": None,

        "ema_confirmed": False,

        "rsi": None,

        "rsi_confirmed": False,

        "volume_current": None,

        "volume_average": None,

        "volume_confirmed": False,

        "trend": "neutral",

        "trend_confirmed": False,

        "score": 0,

        "score_total": 4,

        "majority": False,

        "confirmations_confirmed": False,
    }

    # ========================================================
    # VALIDAR VELA 1M
    # ========================================================

    if candle_1m is None:

        result["reason"] = (
            "vela de 1 minuto no disponible"
        )

        return result

    opening = _to_float(
        candle_1m.get("open")
    )

    closing = _to_float(
        candle_1m.get("close")
    )

    if opening is None:

        result["reason"] = (
            "apertura 1M inválida"
        )

        return result

    if closing is None:

        result["reason"] = (
            "cierre 1M inválido"
        )

        return result

    result["minute_open"] = opening
    result["minute_close"] = closing

    # ========================================================
    # TIMESTAMP
    # ========================================================

    if "from" in candle_1m.index:

        try:

            result["minute_timestamp"] = int(
                float(
                    candle_1m["from"]
                )
            )

        except (TypeError, ValueError):

            result[
                "minute_timestamp"
            ] = None

    # ========================================================
    # MICROVELAS
    # ========================================================

    micro = _get_minute_micro_candles(
        candle_1m,
        candles_5s,
    )

    if micro.empty:

        result["reason"] = (
            "no hay microvelas 5s"
        )

        return result

    # ========================================================
    # SECUENCIA
    # ========================================================

    if not _validate_5s_sequence(
        micro
    ):

        result["reason"] = (
            "secuencia 5s inválida: "
            "hay huecos o timestamps incorrectos"
        )

        return result

    if len(micro) < 2:

        result["reason"] = (
            "faltan microvelas 5s"
        )

        return result

    # ========================================================
    # PRIMERA 5S
    # ========================================================

    first_5s = micro.iloc[0]

    first_open = _to_float(
        first_5s["open"]
    )

    first_close = _to_float(
        first_5s["close"]
    )

    if first_open is None:

        result["reason"] = (
            "apertura primera 5s inválida"
        )

        return result

    if first_close is None:

        result["reason"] = (
            "cierre primera 5s inválido"
        )

        return result

    result["first_5s_open"] = first_open
    result["first_5s_close"] = first_close

    # ========================================================
    # CALL
    # ========================================================

    if first_close > opening:

        rest = micro.iloc[1:]

        pullback_mask = (
            rest["close"] < opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # ----------------------------------------------------
        # LOGICA ORIGINAL
        # ----------------------------------------------------

        if pullback_count <= 0:

            result["reason"] = (
                "CALL no válida: "
                "no hubo retroceso"
            )

            return result

        if closing <= opening:

            result["reason"] = (
                "CALL no válida: "
                "vela 1M no cerró verde"
            )

            return result

        # ----------------------------------------------------
        # CONTINUIDAD COMPRADORA
        # ----------------------------------------------------

        continuity = (
            _buyer_continuity_confirmed(
                micro,
                opening,
            )
        )

        if not continuity:

            result["reason"] = (
                "CALL bloqueada: "
                "no hubo continuidad compradora"
            )

            return result

        result[
            "continuity_confirmed"
        ] = True

        # ----------------------------------------------------
        # CONFIRMACIONES ADICIONALES
        # ----------------------------------------------------

        confirmations = (
            _additional_confirmations(
                micro,
                "call",
            )
        )

        result.update(
            confirmations
        )

        if not confirmations[
            "confirmed"
        ]:

            result["reason"] = (
                "CALL bloqueada: "
                "confirmaciones insuficientes | "
                f"score="
                f"{confirmations['score']}/"
                f"{confirmations['score_total']}"
            )

            return result

        # ----------------------------------------------------
        # CALL FINAL
        # ----------------------------------------------------

        result["signal"] = "call"

        result["valid"] = True

        result[
            "confirmations_confirmed"
        ] = True

        result["reason"] = (
            "CALL confirmada: "
            "patrón original + "
            "continuidad compradora + "
            "EMA + RSI + volumen + "
            "tendencia + mayoría"
        )

        return result

    # ========================================================
    # PUT
    # ========================================================

    if first_close < opening:

        rest = micro.iloc[1:]

        pullback_mask = (
            rest["close"] > opening
        )

        pullback_count = int(
            pullback_mask.sum()
        )

        result["pullback_count"] = (
            pullback_count
        )

        # ----------------------------------------------------
        # LOGICA ORIGINAL
        # ----------------------------------------------------

        if pullback_count <= 0:

            result["reason"] = (
                "PUT no válida: "
                "no hubo retroceso"
            )

            return result

        if closing >= opening:

            result["reason"] = (
                "PUT no válida: "
                "vela 1M no cerró roja"
            )

            return result

        # ----------------------------------------------------
        # CONTINUIDAD VENDEDORA
        # ----------------------------------------------------

        continuity = (
            _seller_continuity_confirmed(
                micro,
                opening,
            )
        )

        if not continuity:

            result["reason"] = (
                "PUT bloqueada: "
                "no hubo continuidad vendedora"
            )

            return result

        result[
            "continuity_confirmed"
        ] = True

        # ----------------------------------------------------
        # CONFIRMACIONES ADICIONALES
        # ----------------------------------------------------

        confirmations = (
            _additional_confirmations(
                micro,
                "put",
            )
        )

        result.update(
            confirmations
        )

        if not confirmations[
            "confirmed"
        ]:

            result["reason"] = (
                "PUT bloqueada: "
                "confirmaciones insuficientes | "
                f"score="
                f"{confirmations['score']}/"
                f"{confirmations['score_total']}"
            )

            return result

        # ----------------------------------------------------
        # PUT FINAL
        # ----------------------------------------------------

        result["signal"] = "put"

        result["valid"] = True

        result[
            "confirmations_confirmed"
        ] = True

        result["reason"] = (
            "PUT confirmada: "
            "patrón original + "
            "continuidad vendedora + "
            "EMA + RSI + volumen + "
            "tendencia + mayoría"
        )

        return result

    # ========================================================
    # NEUTRAL
    # ========================================================

    result["reason"] = (
        "primera 5s cerró exactamente "
        "en la apertura 1M"
    )

    return result


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Dict[str, Any]:

    return analyze_minute(
        candle_1m,
        candles_5s,
    )


# ============================================================
# API SIMPLE
# ============================================================

def get_signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Optional[str]:

    result = analyze_market(
        candle_1m,
        candles_5s,
    )

    return result.get(
        "signal"
    )


# ============================================================
# COMPATIBILIDAD
# ============================================================

def signal(
    candle_1m: pd.Series,
    candles_5s: pd.DataFrame,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
    )


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    print(
        "strategy.py cargado correctamente."
    )

    print(
        "Estrategia: 1M + microvelas 5S"
    )

    print(
        "Logica original conservada."
    )

    print(
        "Continuidad dominante activa."
    )

    print(
        "EMA + RSI + volumen + tendencia"
    )

    print(
        "Score + mayoría activos."
        )
