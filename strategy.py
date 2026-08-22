from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1 - SOLO REVERSIÓN
# ============================================================
#
# OBJETIVO
# ------------------------------------------------------------
# Buscar únicamente posibles REVERSIÓNES de mercado.
#
# La estrategia NO opera continuidad.
#
# EJEMPLO:
#
# Tendencia alcista + agotamiento + rechazo superior
# + confirmación bajista
# = PUT en la siguiente vela.
#
# Tendencia bajista + agotamiento + rechazo inferior
# + confirmación alcista
# = CALL en la siguiente vela.
#
# IMPORTANTE
# ------------------------------------------------------------
# La vela de confirmación es la última vela M1 CERRADA.
#
# La estrategia genera la señal usando esa vela cerrada.
#
# La operación debe ejecutarse en N+1.
#
# Este archivo NO ejecuta operaciones. Solamente analiza
# y devuelve la señal.
# ============================================================


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

TREND_LOOKBACK = 15
STRUCTURE_LOOKBACK = 20
REVERSAL_LOOKBACK = 8
EXHAUSTION_LOOKBACK = 8
SR_LOOKBACK = 20
ATR_PERIOD = 14


# ============================================================
# RATIOS DE VELA
# ============================================================

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25

MIN_REVERSAL_BODY_RATIO = 0.40
STRONG_BODY_RATIO = 0.55
FORCE_BODY_RATIO = 0.65

# Mecha de rechazo en el extremo
MIN_REJECTION_WICK_RATIO = 0.35
STRONG_REJECTION_WICK_RATIO = 0.45

# Máximo permitido para evitar perseguir velas demasiado fuertes
MAX_CONFIRMATION_RANGE_ATR = 1.60
MAX_CONFIRMATION_BODY_ATR = 1.20

# Distancia para considerar precio cerca de soporte/resistencia
SR_TOLERANCE_ATR = 0.35


# ============================================================
# SCORES
# ============================================================

MAX_SCORE = 100

MIN_STRUCTURE_SCORE = 7
MIN_REVERSAL_SCORE = 6
MIN_FINAL_SCORE = 78


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_ohlc(
    candle: pd.Series,
) -> Optional[tuple[float, float, float, float]]:

    if candle is None:
        return None

    opening = _to_float(candle.get("open"))
    closing = _to_float(candle.get("close"))
    high = _to_float(candle.get("high", candle.get("max")))
    low = _to_float(candle.get("low", candle.get("min")))

    if None in (opening, closing, high, low):
        return None

    if high < low:
        return None

    return opening, high, low, closing


def safe_dataframe(
    df: Optional[pd.DataFrame],
) -> pd.DataFrame:

    if df is None:
        return pd.DataFrame()

    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    if len(df) == 0:
        return pd.DataFrame()

    required = {"open", "close", "high", "low"}

    if not required.issubset(df.columns):
        return pd.DataFrame()

    result = df.copy()

    for column in required:
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    result.dropna(
        subset=list(required),
        inplace=True,
    )

    if "from" in result.columns:
        result.sort_values(
            "from",
            inplace=True,
        )

    result.reset_index(
        drop=True,
        inplace=True,
    )

    return result


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    df: pd.DataFrame,
    period: int = ATR_PERIOD,
) -> float:

    df = safe_dataframe(df)

    if len(df) < 2:
        return 0.0

    work = df.copy()

    previous_close = work["close"].shift(1)

    tr1 = work["high"] - work["low"]
    tr2 = (work["high"] - previous_close).abs()
    tr3 = (work["low"] - previous_close).abs()

    true_range = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    atr_series = true_range.rolling(
        window=min(period, len(work)),
        min_periods=2,
    ).mean()

    atr = atr_series.iloc[-1]

    if pd.isna(atr):
        return 0.0

    return float(atr)


# ============================================================
# DATOS DE VELA
# ============================================================

def get_candle_data(
    candle: pd.Series,
) -> Optional[Dict[str, float]]:

    ohlc = _get_ohlc(candle)

    if ohlc is None:
        return None

    opening, high, low, closing = ohlc

    candle_range = high - low
    body = abs(closing - opening)

    upper_wick = max(
        0.0,
        high - max(opening, closing),
    )

    lower_wick = max(
        0.0,
        min(opening, closing) - low,
    )

    if candle_range <= 0:

        return {
            "open": opening,
            "close": closing,
            "high": high,
            "low": low,
            "range": 0.0,
            "body": 0.0,
            "upper_wick": 0.0,
            "lower_wick": 0.0,
            "body_ratio": 0.0,
            "upper_wick_ratio": 0.0,
            "lower_wick_ratio": 0.0,
            "close_position": 0.5,
        }

    return {
        "open": opening,
        "close": closing,
        "high": high,
        "low": low,
        "range": candle_range,
        "body": body,
        "upper_wick": upper_wick,
        "lower_wick": lower_wick,
        "body_ratio": body / candle_range,
        "upper_wick_ratio": upper_wick / candle_range,
        "lower_wick_ratio": lower_wick / candle_range,
        "close_position": (
            closing - low
        ) / candle_range,
    }


# ============================================================
# ANALIZAR ESTRUCTURA PREVIA
# ============================================================
#
# Esta función determina hacia dónde venía el mercado
# ANTES de la posible reversión.
# ============================================================

def analyze_structure(
    df: pd.DataFrame,
) -> Dict[str, Any]:

    result = {
        "direction": "NEUTRAL",
        "score": 0,
        "bullish_score": 0,
        "bearish_score": 0,
        "reason": "estructura insuficiente",
    }

    df = safe_dataframe(df)

    if len(df) < 6:
        return result

    work = df.tail(
        TREND_LOOKBACK
    ).reset_index(drop=True)

    highs = work["high"].tolist()
    lows = work["low"].tolist()
    closes = work["close"].tolist()

    higher_highs = sum(
        1
        for i in range(1, len(highs))
        if highs[i] > highs[i - 1]
    )

    higher_lows = sum(
        1
        for i in range(1, len(lows))
        if lows[i] > lows[i - 1]
    )

    lower_highs = sum(
        1
        for i in range(1, len(highs))
        if highs[i] < highs[i - 1]
    )

    lower_lows = sum(
        1
        for i in range(1, len(lows))
        if lows[i] < lows[i - 1]
    )

    bullish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] > closes[i - 1]
    )

    bearish_closes = sum(
        1
        for i in range(1, len(closes))
        if closes[i] < closes[i - 1]
    )

    bullish_score = 0
    bearish_score = 0

    if higher_highs >= 7:
        bullish_score += 3

    if higher_lows >= 7:
        bullish_score += 3

    if bullish_closes >= 7:
        bullish_score += 2

    if closes[-1] > closes[0]:
        bullish_score += 2

    if lower_highs >= 7:
        bearish_score += 3

    if lower_lows >= 7:
        bearish_score += 3

    if bearish_closes >= 7:
        bearish_score += 2

    if closes[-1] < closes[0]:
        bearish_score += 2

    result["bullish_score"] = bullish_score
    result["bearish_score"] = bearish_score

    if (
        bullish_score >= MIN_STRUCTURE_SCORE
        and bullish_score > bearish_score
    ):

        result["direction"] = "BULLISH"
        result["score"] = bullish_score
        result["reason"] = "tendencia previa alcista"

    elif (
        bearish_score >= MIN_STRUCTURE_SCORE
        and bearish_score > bullish_score
    ):

        result["direction"] = "BEARISH"
        result["score"] = bearish_score
        result["reason"] = "tendencia previa bajista"

    else:

        result["direction"] = "NEUTRAL"
        result["score"] = max(
            bullish_score,
            bearish_score,
        )
        result["reason"] = (
            "mercado lateral o estructura mezclada"
        )

    return result


# ============================================================
# DETECTAR EXTREMO DEL MERCADO
# ============================================================
#
# Para una reversión necesitamos que el precio esté cerca
# de un extremo:
#
# Tendencia alcista -> cerca de máximo/resistencia.
# Tendencia bajista -> cerca de mínimo/soporte.
# ============================================================

def check_reversal_zone(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "",
        "support": None,
        "resistance": None,
        "atr": 0.0,
    }

    df = safe_dataframe(df)

    if len(df) < 6:
        result["reason"] = "historial insuficiente para zona"
        return result

    historical = df.iloc[:-1].tail(
        SR_LOOKBACK
    )

    if len(historical) < 3:
        result["reason"] = "poco historial para zona"
        return result

    last = get_candle_data(
        df.iloc[-1]
    )

    if last is None:
        result["reason"] = "vela actual inválida"
        return result

    atr = calculate_atr(
        historical
    )

    if atr <= 0:
        result["reason"] = "ATR inválido"
        return result

    support = float(
        historical["low"].min()
    )

    resistance = float(
        historical["high"].max()
    )

    tolerance = atr * SR_TOLERANCE_ATR

    result["support"] = support
    result["resistance"] = resistance
    result["atr"] = atr

    score = 0

    if direction == "BULLISH":

        # Para buscar PUT queremos que el precio esté arriba.
        distance_to_resistance = (
            resistance - last["high"]
        )

        if distance_to_resistance <= tolerance:
            score += 6

        if last["high"] >= resistance:
            score += 2

        if score >= 6:
            result["valid"] = True
            result["score"] = score
            result["reason"] = (
                "precio en zona alta para posible reversión PUT"
            )
            return result

        result["reason"] = (
            "precio no está suficientemente alto para reversión"
        )
        return result

    if direction == "BEARISH":

        # Para buscar CALL queremos que el precio esté abajo.
        distance_to_support = (
            last["low"] - support
        )

        if distance_to_support <= tolerance:
            score += 6

        if last["low"] <= support:
            score += 2

        if score >= 6:
            result["valid"] = True
            result["score"] = score
            result["reason"] = (
                "precio en zona baja para posible reversión CALL"
            )
            return result

        result["reason"] = (
            "precio no está suficientemente bajo para reversión"
        )
        return result

    result["reason"] = "dirección neutral"

    return result


# ============================================================
# DETECTAR AGOTAMIENTO
# ============================================================
#
# BULLISH agotado:
# - rechazo superior
# - cuerpo débil
# - pérdida de fuerza
#
# BEARISH agotado:
# - rechazo inferior
# - cuerpo débil
# - pérdida de fuerza
# ============================================================

def detect_end_of_trend(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "exhausted": False,
        "penalty": 0,
        "score": 0,
        "reason": "",
    }

    df = safe_dataframe(df)

    if len(df) < 3:
        result["reason"] = "pocas velas para agotamiento"
        return result

    work = df.tail(
        EXHAUSTION_LOOKBACK
    ).reset_index(drop=True)

    last = get_candle_data(
        work.iloc[-1]
    )

    previous = get_candle_data(
        work.iloc[-2]
    )

    if last is None or previous is None:
        result["reason"] = "velas inválidas"
        return result

    score = 0
    reasons = []

    if direction == "BULLISH":

        # Rechazo superior
        if (
            last["upper_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 5
            reasons.append("rechazo superior")

        # Vela con cuerpo pequeño después del impulso
        if (
            last["body_ratio"]
            <= INDECISION_BODY_RATIO
        ):
            score += 3
            reasons.append("indecisión en máximos")

        # Pérdida de fuerza frente a la vela anterior
        if (
            last["body"]
            < previous["body"]
            and previous["close"] > previous["open"]
        ):
            score += 2
            reasons.append("pérdida de fuerza alcista")

        # Cierre bajista
        if last["close"] < last["open"]:
            score += 3
            reasons.append("presión bajista")

        # Rompe el mínimo de la vela anterior
        if last["close"] < previous["low"]:
            score += 4
            reasons.append("ruptura bajista de estructura corta")

    elif direction == "BEARISH":

        # Rechazo inferior
        if (
            last["lower_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 5
            reasons.append("rechazo inferior")

        # Indecisión en mínimos
        if (
            last["body_ratio"]
            <= INDECISION_BODY_RATIO
        ):
            score += 3
            reasons.append("indecisión en mínimos")

        # Pérdida de fuerza bajista
        if (
            last["body"]
            < previous["body"]
            and previous["close"] < previous["open"]
        ):
            score += 2
            reasons.append("pérdida de fuerza bajista")

        # Cierre alcista
        if last["close"] > last["open"]:
            score += 3
            reasons.append("presión alcista")

        # Rompe el máximo de la vela anterior
        if last["close"] > previous["high"]:
            score += 4
            reasons.append("ruptura alcista de estructura corta")

    result["score"] = score

    # 5 puntos ya indican una posible pérdida clara de fuerza.
    result["exhausted"] = score >= 5

    result["penalty"] = 0

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else "sin agotamiento suficiente"
    )

    return result


# ============================================================
# CONFIRMACIÓN DE REVERSIÓN
# ============================================================
#
# Tendencia previa BULLISH:
# buscamos confirmación BEARISH para PUT.
#
# Tendencia previa BEARISH:
# buscamos confirmación BULLISH para CALL.
# ============================================================

def confirmation_score(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "score": 0,
        "valid": False,
        "reason": "",
        "range_atr": 0.0,
        "body_atr": 0.0,
        "reversal_direction": "NEUTRAL",
    }

    df = safe_dataframe(df)

    if len(df) < 3:
        result["reason"] = (
            "pocas velas para confirmación"
        )
        return result

    candle = get_candle_data(
        df.iloc[-1]
    )

    previous = get_candle_data(
        df.iloc[-2]
    )

    if candle is None or previous is None:
        result["reason"] = "vela inválida"
        return result

    atr = calculate_atr(
        df.iloc[:-1]
    )

    if atr <= 0:
        atr = candle["range"]

    if atr <= 0:
        result["reason"] = "ATR inválido"
        return result

    range_atr = candle["range"] / atr
    body_atr = candle["body"] / atr

    result["range_atr"] = range_atr
    result["body_atr"] = body_atr

    score = 0
    reasons = []

    # --------------------------------------------------------
    # REVERSIÓN BAJISTA
    # Tendencia previa alcista -> PUT
    # --------------------------------------------------------

    if direction == "BULLISH":

        result["reversal_direction"] = "BEARISH"

        # La confirmación debe cerrar bajista.
        if candle["close"] < candle["open"]:
            score += 5

        # Cuerpo suficiente.
        if (
            candle["body_ratio"]
            >= MIN_REVERSAL_BODY_RATIO
        ):
            score += 4

        # Cierre cerca del mínimo.
        if candle["close_position"] <= 0.35:
            score += 4

        # Rechazo superior.
        if (
            candle["upper_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 4

        # Debilidad respecto al máximo anterior.
        if candle["high"] >= previous["high"]:
            score += 2

        # Confirmación más fuerte si rompe el mínimo previo.
        if candle["close"] < previous["low"]:
            score += 5

        # No queremos cierre alcista.
        if candle["close"] >= candle["open"]:
            reasons.append("confirmación no bajista")

    # --------------------------------------------------------
    # REVERSIÓN ALCISTA
    # Tendencia previa bajista -> CALL
    # --------------------------------------------------------

    elif direction == "BEARISH":

        result["reversal_direction"] = "BULLISH"

        # La confirmación debe cerrar alcista.
        if candle["close"] > candle["open"]:
            score += 5

        # Cuerpo suficiente.
        if (
            candle["body_ratio"]
            >= MIN_REVERSAL_BODY_RATIO
        ):
            score += 4

        # Cierre cerca del máximo.
        if candle["close_position"] >= 0.65:
            score += 4

        # Rechazo inferior.
        if (
            candle["lower_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 4

        # Barrida o test del mínimo.
        if candle["low"] <= previous["low"]:
            score += 2

        # Confirmación fuerte si rompe máximo previo.
        if candle["close"] > previous["high"]:
            score += 5

        # No queremos cierre bajista.
        if candle["close"] <= candle["open"]:
            reasons.append("confirmación no alcista")

    else:
        result["reason"] = "dirección previa neutral"
        return result

    # --------------------------------------------------------
    # FILTROS DE MOVIMIENTO
    # --------------------------------------------------------

    if range_atr > MAX_CONFIRMATION_RANGE_ATR:
        score -= 6
        reasons.append("movimiento demasiado extendido")

    if body_atr > MAX_CONFIRMATION_BODY_ATR:
        score -= 5
        reasons.append("cuerpo demasiado extendido")

    if candle["body_ratio"] <= INDECISION_BODY_RATIO:
        score -= 8
        reasons.append("vela indecisa")

    result["score"] = max(0, score)

    result["valid"] = (
        result["score"] >= 13
        and not reasons
    )

    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else f"confirmación reversión score={result['score']}"
    )

    return result


# ============================================================
# VALIDAR REVERSIÓN COMPLETA
# ============================================================

def check_reversal(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    result = {
        "valid": False,
        "score": 0,
        "reason": "sin reversión",
    }

    df = safe_dataframe(df)

    if len(df) < 4:
        result["reason"] = "pocas velas para reversión"
        return result

    work = df.tail(
        REVERSAL_LOOKBACK
    ).reset_index(drop=True)

    last = get_candle_data(
        work.iloc[-1]
    )

    previous = get_candle_data(
        work.iloc[-2]
    )

    if last is None or previous is None:
        result["reason"] = "velas inválidas"
        return result

    score = 0
    reasons = []

    if direction == "BULLISH":

        # Buscamos giro hacia abajo.

        if last["close"] < last["open"]:
            score += 3

        if (
            last["close_position"]
            <= 0.35
        ):
            score += 2

        if (
            last["upper_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 2

        if last["close"] < previous["low"]:
            score += 3

        if score >= MIN_REVERSAL_SCORE:
            result["valid"] = True
            result["score"] = score
            result["reason"] = (
                "reversión bajista confirmada"
            )
            return result

        reasons.append("reversión bajista insuficiente")

    elif direction == "BEARISH":

        # Buscamos giro hacia arriba.

        if last["close"] > last["open"]:
            score += 3

        if (
            last["close_position"]
            >= 0.65
        ):
            score += 2

        if (
            last["lower_wick_ratio"]
            >= MIN_REJECTION_WICK_RATIO
        ):
            score += 2

        if last["close"] > previous["high"]:
            score += 3

        if score >= MIN_REVERSAL_SCORE:
            result["valid"] = True
            result["score"] = score
            result["reason"] = (
                "reversión alcista confirmada"
            )
            return result

        reasons.append("reversión alcista insuficiente")

    result["score"] = score
    result["reason"] = (
        ", ".join(reasons)
        if reasons
        else "sin reversión"
    )

    return result


# ============================================================
# COMPATIBILIDAD SOPORTE / RESISTENCIA
# ============================================================
#
# En estrategia de reversión S/R no es necesariamente bloqueo.
#
# De hecho:
# - resistencia ayuda a buscar PUT
# - soporte ayuda a buscar CALL
#
# ============================================================

def check_support_resistance(
    df: pd.DataFrame,
    direction: str,
) -> Dict[str, Any]:

    zone = check_reversal_zone(
        df,
        direction,
    )

    return {
        "blocked": False,
        "penalty": 0,
        "reason": zone.get(
            "reason",
            "",
        ),
        "support": zone.get(
            "support",
        ),
        "resistance": zone.get(
            "resistance",
        ),
        "valid_reversal_zone": zone.get(
            "valid",
            False,
        ),
        "score": zone.get(
            "score",
            0,
        ),
    }


# ============================================================
# ANÁLISIS DE VELA EN VIVO
# ============================================================

def analyze_live_candle(
    candle_1m: pd.Series,
) -> Dict[str, Any]:

    result = {
        "direction": "NEUTRAL",
        "state": "INDEFINITION",
        "score": 0,
        "open": None,
        "close": None,
        "high": None,
        "low": None,
        "range": 0.0,
        "body": 0.0,
        "body_ratio": 0.0,
        "upper_wick": 0.0,
        "lower_wick": 0.0,
        "close_position": 0.5,
    }

    data = get_candle_data(
        candle_1m
    )

    if data is None:
        return result

    result.update(data)

    if data["close"] > data["open"]:
        direction = "BULLISH"

    elif data["close"] < data["open"]:
        direction = "BEARISH"

    else:
        direction = "NEUTRAL"

    result["direction"] = direction

    score = 0

    # Posible rechazo bajista.
    if (
        data["upper_wick_ratio"]
        >= MIN_REJECTION_WICK_RATIO
    ):
        score += 4

    # Posible rechazo alcista.
    if (
        data["lower_wick_ratio"]
        >= MIN_REJECTION_WICK_RATIO
    ):
        score += 4

    # Cuerpo significativo.
    if (
        data["body_ratio"]
        >= MIN_REVERSAL_BODY_RATIO
    ):
        score += 3

    if data["body_ratio"] <= DOJI_BODY_RATIO:

        result["state"] = "DOJI"

    elif data["body_ratio"] <= INDECISION_BODY_RATIO:

        result["state"] = "INDECISION"

    elif (
        data["upper_wick_ratio"]
        >= STRONG_REJECTION_WICK_RATIO
    ):

        result["state"] = "UPPER_REJECTION"

    elif (
        data["lower_wick_ratio"]
        >= STRONG_REJECTION_WICK_RATIO
    ):

        result["state"] = "LOWER_REJECTION"

    else:

        result["state"] = "MOVEMENT"

    result["score"] = score

    return result


# ============================================================
# ANÁLISIS PRINCIPAL DE MERCADO
# ============================================================
#
# FLUJO:
#
# 1. Detectar tendencia previa.
# 2. Verificar que el precio esté en un extremo.
# 3. Buscar agotamiento.
# 4. Buscar reversión real.
# 5. Confirmar la vela contraria.
# 6. Generar señal para N+1.
# ============================================================

def analyze_market(
    candle_1m: Optional[pd.Series] = None,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "score": 0,
        "direction": "NEUTRAL",
        "state": "NO_SIGNAL",
        "reason": "sin análisis",
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "structure": {},
        "continuity": {},
        "confirmation": {},
        "exhaustion": {},
        "support_resistance": {},
        "reversal": {},
        "reversal_zone": {},
    }

    if candle_1m is None:

        result["reason"] = "vela M1 no disponible"

        return result

    current = get_candle_data(
        candle_1m
    )

    if current is None:

        result["reason"] = "OHLC inválido"

        return result

    if "from" in candle_1m.index:

        try:

            result["minute_timestamp"] = int(
                float(
                    candle_1m["from"]
                )
            )

        except Exception:
            pass

    result["minute_open"] = current["open"]
    result["minute_close"] = current["close"]

    # --------------------------------------------------------
    # CONSTRUIR HISTORIAL
    # --------------------------------------------------------

    historical = safe_dataframe(
        previous_m1
    )

    if len(historical) == 0:

        historical = pd.DataFrame(
            [dict(candle_1m)]
        )

    # Agregar la vela de confirmación si aún no está.
    if len(historical) > 0:

        should_append = True

        if (
            "from" in historical.columns
            and result["minute_timestamp"] is not None
        ):

            timestamps = pd.to_numeric(
                historical["from"],
                errors="coerce",
            )

            if (
                result["minute_timestamp"]
                in timestamps.values
            ):
                should_append = False

        if should_append:

            historical = pd.concat(
                [
                    historical,
                    pd.DataFrame(
                        [dict(candle_1m)]
                    ),
                ],
                ignore_index=True,
            )

    historical = safe_dataframe(
        historical
    )

    if len(historical) < 8:

        result["reason"] = "historial insuficiente"

        return result

    # --------------------------------------------------------
    # LA ÚLTIMA VELA ES LA CONFIRMACIÓN.
    #
    # Para detectar la tendencia previa usamos las velas
    # anteriores, para no dejar que la vela de reversión
    # cambie artificialmente la tendencia.
    # --------------------------------------------------------

    trend_history = historical.iloc[:-1]

    if len(trend_history) < 6:

        result["reason"] = (
            "historial previo insuficiente"
        )

        return result

    structure = analyze_structure(
        trend_history
    )

    previous_direction = structure["direction"]

    result["structure"] = structure
    result["direction"] = previous_direction

    # --------------------------------------------------------
    # NO OPERAR MERCADO LATERAL
    # --------------------------------------------------------

    if previous_direction == "NEUTRAL":

        result["state"] = "RANGE"

        result["reason"] = (
            "no hay tendencia previa clara para revertir"
        )

        return result

    # --------------------------------------------------------
    # ZONA DE REVERSIÓN
    # --------------------------------------------------------

    reversal_zone = check_reversal_zone(
        historical,
        previous_direction,
    )

    result["reversal_zone"] = reversal_zone

    result["support_resistance"] = {
        "blocked": False,
        "penalty": 0,
        "reason": reversal_zone["reason"],
        "support": reversal_zone["support"],
        "resistance": reversal_zone["resistance"],
        "valid_reversal_zone": reversal_zone["valid"],
        "score": reversal_zone["score"],
    }

    if not reversal_zone["valid"]:

        result["state"] = "NO_REVERSAL_ZONE"

        result["reason"] = (
            reversal_zone["reason"]
        )

        return result

    # --------------------------------------------------------
    # AGOTAMIENTO
    # --------------------------------------------------------

    exhaustion = detect_end_of_trend(
        historical,
        previous_direction,
    )

    result["exhaustion"] = exhaustion

    if not exhaustion["exhausted"]:

        result["state"] = "NO_EXHAUSTION"

        result["reason"] = (
            f"tendencia todavía sin agotamiento: "
            f"{exhaustion['reason']}"
        )

        return result

    # --------------------------------------------------------
    # REVERSIÓN
    # --------------------------------------------------------

    reversal = check_reversal(
        historical,
        previous_direction,
    )

    result["reversal"] = reversal

    # Compatibilidad con el bot anterior.
    result["continuity"] = {
        "valid": reversal["valid"],
        "score": reversal["score"],
        "reason": reversal["reason"],
    }

    if not reversal["valid"]:

        result["state"] = "NO_REVERSAL"

        result["reason"] = reversal["reason"]

        return result

    # --------------------------------------------------------
    # CONFIRMACIÓN
    # --------------------------------------------------------

    confirmation = confirmation_score(
        historical,
        previous_direction,
    )

    result["confirmation"] = confirmation

    if not confirmation["valid"]:

        result["state"] = "WEAK_CONFIRMATION"

        result["reason"] = (
            f"confirmación de reversión débil: "
            f"{confirmation['reason']}"
        )

        return result

    # --------------------------------------------------------
    # SCORE FINAL
    # --------------------------------------------------------

    score = 0

    # Tendencia previa.
    score += min(
        25,
        structure["score"] * 2.5,
    )

    # Zona extrema.
    score += min(
        20,
        reversal_zone["score"] * 2.5,
    )

    # Agotamiento.
    score += min(
        20,
        exhaustion["score"] * 2.5,
    )

    # Reversión.
    score += min(
        20,
        reversal["score"] * 2.5,
    )

    # Confirmación.
    score += min(
        25,
        confirmation["score"] * 1.5,
    )

    score = max(
        0,
        min(
            MAX_SCORE,
            int(score),
        ),
    )

    result["score"] = score

    if score < MIN_FINAL_SCORE:

        result["state"] = "LOW_SCORE"

        result["reason"] = (
            f"reversión detectada pero calidad insuficiente "
            f"score={score}"
        )

        return result

    # --------------------------------------------------------
    # SEÑAL FINAL - INVERSIÓN DE LA TENDENCIA PREVIA
    # --------------------------------------------------------

    # Tendencia previa alcista -> buscamos reversión bajista.
    if previous_direction == "BULLISH":

        result["signal"] = "put"
        result["valid"] = True
        result["state"] = "BEARISH_REVERSAL"

        result["reason"] = (
            f"PUT reversión bajista confirmada "
            f"score={score}"
        )

        return result

    # Tendencia previa bajista -> buscamos reversión alcista.
    if previous_direction == "BEARISH":

        result["signal"] = "call"
        result["valid"] = True
        result["state"] = "BULLISH_REVERSAL"

        result["reason"] = (
            f"CALL reversión alcista confirmada "
            f"score={score}"
        )

        return result

    return result


# ============================================================
# COMPATIBILIDAD CON BOT.PY
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )


def build_n1_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    )


def get_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return analyze_market(
        candle_1m,
        candles_5s,
        previous_m1,
    ).get("signal")


def signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:

    return get_signal(
        candle_1m,
        candles_5s,
        previous_m1,
    )


# ============================================================
# DIRECCIÓN DE VELA M1
# ============================================================

def get_m1_direction(
    candle_1m=None,
):

    if candle_1m is None:
        return None

    try:

        if (
            hasattr(candle_1m, "iloc")
            and hasattr(candle_1m, "columns")
        ):

            if len(candle_1m) == 0:
                return None

            candle_1m = candle_1m.iloc[-1]

        opening = float(
            candle_1m.get("open")
        )

        closing = float(
            candle_1m.get("close")
        )

    except Exception:

        return None

    if closing > opening:
        return "BULLISH"

    if closing < opening:
        return "BEARISH"

    return "NEUTRAL"


# ============================================================
# COMPATIBILIDAD
# ============================================================

def check_pattern(
    candles_5s=None,
):

    return None


# ============================================================
# EJECUCIÓN DIRECTA
# ============================================================

if __name__ == "__main__":

    print("strategy.py cargado correctamente.")
    print("Estrategia: SOLO REVERSIÓN M1")
    print(
        "BULLISH agotado -> posible PUT"
    )
    print(
        "BEARISH agotado -> posible CALL"
    )
    print(
        "La señal se genera con vela cerrada y se ejecuta en N+1."
    )
