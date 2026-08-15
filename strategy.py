from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import math

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURACIÓN
# ============================================================

MIN_BARS = 35

EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50

RSI_PERIOD = 14
ATR_PERIOD = 14

STRUCTURE_LOOKBACK = 6
SR_LOOKBACK = 20

# Tolerancia relativa al ATR para evitar entradas pegadas a extremos.
SR_ATR_MULTIPLIER = 0.35

# Evita operar con velas demasiado pequeñas.
MIN_BODY_ATR = 0.18

# Evita perseguir velas excesivamente extendidas.
MAX_BODY_ATR = 1.80

# RSI permitido para continuidad.
CALL_RSI_MIN = 48.0
CALL_RSI_MAX = 72.0
PUT_RSI_MIN = 28.0
PUT_RSI_MAX = 52.0


# ============================================================
# UTILIDADES
# ============================================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        if math.isfinite(x):
            return x
    except Exception:
        pass
    return default


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza columnas OHLC y orden temporal.
    No modifica el dataframe original.
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()

    out = df.copy()

    rename = {}
    if "max" in out.columns and "high" not in out.columns:
        rename["max"] = "high"
    if "min" in out.columns and "low" not in out.columns:
        rename["min"] = "low"
    rename.update({
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
    })
    out.rename(columns=rename, inplace=True)

    required = ["open", "high", "low", "close"]
    if any(c not in out.columns for c in required):
        return pd.DataFrame()

    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    if "from" in out.columns:
        out["from"] = pd.to_numeric(out["from"], errors="coerce")
        out.sort_values("from", inplace=True)

    out.dropna(subset=required, inplace=True)
    out.reset_index(drop=True, inplace=True)

    return out


# ============================================================
# INDICADORES
# ============================================================

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = _normalize(df)

    if out.empty:
        return out

    close = out["close"]
    high = out["high"]
    low = out["low"]

    out["ema9"] = close.ewm(span=EMA_FAST, adjust=False).mean()
    out["ema21"] = close.ewm(span=EMA_MID, adjust=False).mean()
    out["ema50"] = close.ewm(span=EMA_SLOW, adjust=False).mean()

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    out["tr"] = pd.concat(
        [tr1, tr2, tr3],
        axis=1,
    ).max(axis=1)

    out["atr"] = out["tr"].rolling(
        ATR_PERIOD,
        min_periods=ATR_PERIOD,
    ).mean()

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / RSI_PERIOD,
        adjust=False,
        min_periods=RSI_PERIOD,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))

    # Si no hubo pérdidas, RSI matemáticamente se aproxima a 100.
    out.loc[(avg_loss == 0) & (avg_gain > 0), "rsi"] = 100.0
    out.loc[(avg_gain == 0) & (avg_loss > 0), "rsi"] = 0.0

    return out


# ============================================================
# LECTURA DE VELA
# ============================================================

def candle_direction(candle: pd.Series) -> str:
    o = _safe_float(candle.get("open"))
    c = _safe_float(candle.get("close"))

    if c > o:
        return "bull"
    if c < o:
        return "bear"
    return "neutral"


def candle_metrics(candle: pd.Series) -> Dict[str, float]:
    o = _safe_float(candle.get("open"))
    h = _safe_float(candle.get("high"))
    l = _safe_float(candle.get("low"))
    c = _safe_float(candle.get("close"))

    rng = max(h - l, 0.0)
    body = abs(c - o)

    upper = max(h - max(o, c), 0.0)
    lower = max(min(o, c) - l, 0.0)

    return {
        "range": rng,
        "body": body,
        "upper_wick": upper,
        "lower_wick": lower,
        "body_ratio": body / rng if rng > 0 else 0.0,
    }


# ============================================================
# ESTRUCTURA
# ============================================================

def detect_structure(
    df: pd.DataFrame,
    lookback: int = STRUCTURE_LOOKBACK,
) -> str:
    """
    Estructura simple de continuidad:
    bullish = máximos y mínimos crecientes
    bearish = máximos y mínimos decrecientes
    range   = estructura mixta/lateral
    """
    if df is None or len(df) < lookback:
        return "range"

    x = df.tail(lookback)

    highs = x["high"].to_numpy(dtype=float)
    lows = x["low"].to_numpy(dtype=float)

    hh = 0
    hl = 0
    lh = 0
    ll = 0

    for i in range(1, len(x)):
        if highs[i] > highs[i - 1]:
            hh += 1
        elif highs[i] < highs[i - 1]:
            lh += 1

        if lows[i] > lows[i - 1]:
            hl += 1
        elif lows[i] < lows[i - 1]:
            ll += 1

    if hh >= 3 and hl >= 3:
        return "bullish"

    if lh >= 3 and ll >= 3:
        return "bearish"

    return "range"


def structure_score(df: pd.DataFrame) -> int:
    """
    Puntaje de estructura 0-5.
    5 = estructura muy limpia.
    """
    if df is None or len(df) < STRUCTURE_LOOKBACK:
        return 0

    x = df.tail(STRUCTURE_LOOKBACK)

    highs = x["high"].to_numpy(dtype=float)
    lows = x["low"].to_numpy(dtype=float)

    bull = 0
    bear = 0

    for i in range(1, len(x)):
        if highs[i] > highs[i - 1] and lows[i] > lows[i - 1]:
            bull += 1
        if highs[i] < highs[i - 1] and lows[i] < lows[i - 1]:
            bear += 1

    return int(min(5, max(bull, bear)))


# ============================================================
# SOPORTE / RESISTENCIA
# ============================================================

def recent_levels(
    df: pd.DataFrame,
    lookback: int = SR_LOOKBACK,
) -> Tuple[float, float]:
    if df is None or df.empty:
        return 0.0, 0.0

    x = df.tail(lookback)

    support = _safe_float(x["low"].min())
    resistance = _safe_float(x["high"].max())

    return support, resistance


def is_near_sr(
    df: pd.DataFrame,
    tolerance: Optional[float] = None,
) -> bool:
    """
    True si el precio está demasiado cerca de un extremo reciente.
    Se utiliza para evitar operar en zonas de posible reversión.
    """
    if df is None or len(df) < 5:
        return True

    last = df.iloc[-1]
    close = _safe_float(last["close"])

    support, resistance = recent_levels(df)

    atr = _safe_float(last.get("atr"), 0.0)

    if tolerance is None:
        tolerance = atr * SR_ATR_MULTIPLIER

    if tolerance <= 0:
        # Fallback muy pequeño para OTC con pocos decimales.
        tolerance = max(abs(close) * 0.00015, 1e-8)

    near_support = abs(close - support) <= tolerance
    near_resistance = abs(resistance - close) <= tolerance

    return bool(near_support or near_resistance)


# ============================================================
# RUPTURA / FALSA RUPTURA
# ============================================================

def breakout_context(df: pd.DataFrame) -> Dict[str, bool]:
    """
    Detecta ruptura reciente y si la vela volvió dentro del rango.
    """
    result = {
        "bull_breakout": False,
        "bear_breakout": False,
        "false_bull_breakout": False,
        "false_bear_breakout": False,
    }

    if df is None or len(df) < 5:
        return result

    x = df.tail(5).copy()
    current = x.iloc[-1]

    previous_high = float(x.iloc[:-1]["high"].max())
    previous_low = float(x.iloc[:-1]["low"].min())

    h = _safe_float(current["high"])
    l = _safe_float(current["low"])
    c = _safe_float(current["close"])

    result["bull_breakout"] = c > previous_high
    result["bear_breakout"] = c < previous_low

    # Mecha fuera del rango pero cierre de vuelta dentro:
    result["false_bull_breakout"] = (
        h > previous_high and c <= previous_high
    )

    result["false_bear_breakout"] = (
        l < previous_low and c >= previous_low
    )

    return result


# ============================================================
# CONTINUIDAD
# ============================================================

def _continuity_call_checks(
    df: pd.DataFrame,
) -> Tuple[bool, int, list[str]]:
    last = df.iloc[-1]

    structure = detect_structure(df)
    s_score = structure_score(df)

    ema9 = _safe_float(last.get("ema9"))
    ema21 = _safe_float(last.get("ema21"))
    ema50 = _safe_float(last.get("ema50"))
    close = _safe_float(last.get("close"))
    rsi = _safe_float(last.get("rsi"), 50.0)
    atr = _safe_float(last.get("atr"))

    metrics = candle_metrics(last)
    direction = candle_direction(last)

    points = 0
    reasons: list[str] = []

    # 1. Estructura.
    if structure == "bullish":
        points += 2
        reasons.append("estructura alcista")
    else:
        reasons.append("estructura no alcista")

    # 2. Alineación de medias.
    if ema9 > ema21 > ema50 and close > ema9:
        points += 2
        reasons.append("EMA 9>21>50")
    else:
        reasons.append("EMA no alineada")

    # 3. Vela de confirmación.
    if direction == "bull":
        points += 1
        reasons.append("vela alcista")
    else:
        reasons.append("vela no alcista")

    # 4. RSI sano para continuidad.
    if CALL_RSI_MIN <= rsi <= CALL_RSI_MAX:
        points += 1
        reasons.append(f"RSI {rsi:.1f}")
    else:
        reasons.append(f"RSI fuera {rsi:.1f}")

    # 5. Cuerpo suficiente pero no exagerado.
    if atr > 0:
        body_atr = metrics["body"] / atr
        if MIN_BODY_ATR <= body_atr <= MAX_BODY_ATR:
            points += 1
            reasons.append("cuerpo válido")
        else:
            reasons.append("cuerpo extremo")
    else:
        reasons.append("ATR inválido")

    # 6. Estructura limpia.
    if s_score >= 4:
        points += 1
        reasons.append(f"estructura {s_score}/5")
    else:
        reasons.append(f"estructura {s_score}/5")

    # 7. No estar en reversión.
    if not is_near_sr(df):
        points += 1
        reasons.append("ubicación libre")
    else:
        reasons.append("cerca de S/R")

    # 8. Ruptura falsa = prohibido.
    br = breakout_context(df)
    if br["false_bull_breakout"]:
        points = 0
        reasons.append("falsa ruptura alcista")
    elif br["bull_breakout"]:
        # Una ruptura limpia puede continuar, pero no se sobrepremia.
        reasons.append("ruptura alcista")

    valid = (
        points >= 8
        and structure == "bullish"
        and ema9 > ema21 > ema50
        and close > ema9
        and direction == "bull"
        and CALL_RSI_MIN <= rsi <= CALL_RSI_MAX
        and not is_near_sr(df)
        and not br["false_bull_breakout"]
    )

    return valid, min(points, 10), reasons


def _continuity_put_checks(
    df: pd.DataFrame,
) -> Tuple[bool, int, list[str]]:
    last = df.iloc[-1]

    structure = detect_structure(df)
    s_score = structure_score(df)

    ema9 = _safe_float(last.get("ema9"))
    ema21 = _safe_float(last.get("ema21"))
    ema50 = _safe_float(last.get("ema50"))
    close = _safe_float(last.get("close"))
    rsi = _safe_float(last.get("rsi"), 50.0)
    atr = _safe_float(last.get("atr"))

    metrics = candle_metrics(last)
    direction = candle_direction(last)

    points = 0
    reasons: list[str] = []

    if structure == "bearish":
        points += 2
        reasons.append("estructura bajista")
    else:
        reasons.append("estructura no bajista")

    if ema9 < ema21 < ema50 and close < ema9:
        points += 2
        reasons.append("EMA 9<21<50")
    else:
        reasons.append("EMA no alineada")

    if direction == "bear":
        points += 1
        reasons.append("vela bajista")
    else:
        reasons.append("vela no bajista")

    if PUT_RSI_MIN <= rsi <= PUT_RSI_MAX:
        points += 1
        reasons.append(f"RSI {rsi:.1f}")
    else:
        reasons.append(f"RSI fuera {rsi:.1f}")

    if atr > 0:
        body_atr = metrics["body"] / atr
        if MIN_BODY_ATR <= body_atr <= MAX_BODY_ATR:
            points += 1
            reasons.append("cuerpo válido")
        else:
            reasons.append("cuerpo extremo")
    else:
        reasons.append("ATR inválido")

    if s_score >= 4:
        points += 1
        reasons.append(f"estructura {s_score}/5")
    else:
        reasons.append(f"estructura {s_score}/5")

    if not is_near_sr(df):
        points += 1
        reasons.append("ubicación libre")
    else:
        reasons.append("cerca de S/R")

    br = breakout_context(df)
    if br["false_bear_breakout"]:
        points = 0
        reasons.append("falsa ruptura bajista")
    elif br["bear_breakout"]:
        reasons.append("ruptura bajista")

    valid = (
        points >= 8
        and structure == "bearish"
        and ema9 < ema21 < ema50
        and close < ema9
        and direction == "bear"
        and PUT_RSI_MIN <= rsi <= PUT_RSI_MAX
        and not is_near_sr(df)
        and not br["false_bear_breakout"]
    )

    return valid, min(points, 10), reasons


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(df: pd.DataFrame) -> Dict[str, Any]:
    """
    API utilizada directamente por bot.py.

    Retorna:
        {
            "signal": "call" | "put" | None,
            "score": 0..10,
            "reason": str,
            "structure": str,
            "structure_score": int,
            "candle": "bull" | "bear" | "neutral",
            "rsi": float,
            "atr": float,
        }
    """
    neutral: Dict[str, Any] = {
        "signal": None,
        "score": 0,
        "reason": "sin señal",
        "structure": "range",
        "structure_score": 0,
        "candle": "neutral",
        "rsi": 0.0,
        "atr": 0.0,
    }

    clean = _normalize(df)

    if len(clean) < MIN_BARS:
        neutral["reason"] = (
            f"faltan velas: {len(clean)}/{MIN_BARS}"
        )
        return neutral

    data = add_indicators(clean)

    if data.empty or len(data) < MIN_BARS:
        neutral["reason"] = "indicadores insuficientes"
        return neutral

    # Se requiere ATR y RSI válidos en la vela de confirmación.
    last = data.iloc[-1]

    atr = _safe_float(last.get("atr"))
    rsi = _safe_float(last.get("rsi"), 50.0)

    if atr <= 0 or not math.isfinite(atr):
        neutral["reason"] = "ATR no disponible"
        return neutral

    if not math.isfinite(rsi):
        neutral["reason"] = "RSI no disponible"
        return neutral

    structure = detect_structure(data)
    s_score = structure_score(data)
    candle = candle_direction(last)

    call_ok, call_score, call_reasons = _continuity_call_checks(data)
    put_ok, put_score, put_reasons = _continuity_put_checks(data)

    # Si ambas direcciones aparecen, el mercado está ambiguo.
    if call_ok and put_ok:
        return {
            **neutral,
            "reason": "señales contradictorias",
            "structure": structure,
            "structure_score": s_score,
            "candle": candle,
            "rsi": rsi,
            "atr": atr,
        }

    if call_ok:
        return {
            "signal": "call",
            "score": call_score,
            "reason": "CALL continuidad | " + ", ".join(call_reasons),
            "structure": structure,
            "structure_score": s_score,
            "candle": candle,
            "rsi": rsi,
            "atr": atr,
        }

    if put_ok:
        return {
            "signal": "put",
            "score": put_score,
            "reason": "PUT continuidad | " + ", ".join(put_reasons),
            "structure": structure,
            "structure_score": s_score,
            "candle": candle,
            "rsi": rsi,
            "atr": atr,
        }

    # Razón útil para los logs.
    best_score = max(call_score, put_score)
    best_side = "CALL" if call_score >= put_score else "PUT"
    best_reasons = (
        call_reasons if call_score >= put_score else put_reasons
    )

    return {
        **neutral,
        "score": best_score,
        "reason": (
            f"sin confirmación {best_side} | "
            + ", ".join(best_reasons)
        ),
        "structure": structure,
        "structure_score": s_score,
        "candle": candle,
        "rsi": rsi,
        "atr": atr,
    }


# ============================================================
# COMPATIBILIDAD / PRUEBA RÁPIDA
# ============================================================

def get_signal(df: pd.DataFrame) -> Optional[str]:
    """
    Alias sencillo para versiones anteriores del bot.
    """
    return analyze_market(df).get("signal")


def signal(df: pd.DataFrame) -> Optional[str]:
    """
    Alias adicional de compatibilidad.
    """
    return get_signal(df)


if __name__ == "__main__":
    print("strategy.py cargado correctamente.")
    print("API principal: analyze_market(df)")
