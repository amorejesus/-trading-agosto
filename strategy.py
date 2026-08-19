from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


# ============================================================
# ESTRATEGIA M1
# ============================================================
#
# N inicia      -> recopilar datos de la M1
# N continúa    -> NO se genera señal
# N cierra      -> calcular toda la estructura de N
# decidir       -> CALL / PUT
# N+1           -> ejecutar la señal calculada
#
# La decisión usa exclusivamente OHLC de la M1 N ya cerrada.
# N+1 nunca participa en la decisión de N+1.
# No se utilizan 5S ni se exige ninguna cantidad de microvelas.
# ============================================================

DOJI_BODY_RATIO = 0.10
INDECISION_BODY_RATIO = 0.25
WEAKNESS_BODY_RATIO = 0.35
CONTINUITY_BODY_RATIO = 0.45
FORCE_BODY_RATIO = 0.60

# Confirmación de estructura para la entrada N+1.
# No cambia la dirección: solo permite operar cuando N es una
# vela de reanudación del movimiento después de un retroceso.
STRUCTURE_LOOKBACK = 6
IMPULSE_BODY_RATIO = 0.45
IMPULSE_CLOSE_CALL = 0.65
IMPULSE_CLOSE_PUT = 0.35


# ============================================================
# UTILIDADES
# ============================================================

def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_ohlc(candle: pd.Series) -> Optional[tuple[float, float, float, float]]:
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


# ============================================================
# ESTRUCTURA + RETROCESO + REANUDACIÓN
# ============================================================

def _structure_confirmation(
    candle_1m: pd.Series,
    previous_m1: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """
    Busca únicamente este patrón en M1 cerradas:

        tendencia bajista -> retroceso alcista -> impulso bajista (N)
        tendencia alcista -> retroceso bajista -> impulso alcista (N)

    La vela N es la vela que acaba de cerrar. La función no mira N+1.
    Si no existe contexto suficiente, no inventa una estructura.
    """
    result = {
        "confirmed": False,
        "structure": "NONE",
        "pullback": False,
        "impulse": False,
        "reason": "sin estructura confirmada",
    }

    if previous_m1 is None or not isinstance(previous_m1, pd.DataFrame) or previous_m1.empty:
        result["reason"] = "sin historial M1 suficiente para estructura"
        return result

    cols = {str(c).lower(): c for c in previous_m1.columns}
    required = ("open", "high", "low", "close")
    if any(c not in cols for c in required):
        result["reason"] = "historial M1 sin OHLC completo"
        return result

    rows = previous_m1.copy()
    try:
        if "from" in cols:
            rows = rows.sort_values(cols["from"])
    except Exception:
        pass

    # Si el historial incluye N, eliminarla por timestamp para que
    # la estructura use exclusivamente velas anteriores a N.
    current_ts = None
    try:
        current_ts = int(float(candle_1m.get("from")))
    except Exception:
        pass

    if current_ts is not None and "from" in cols:
        try:
            rows = rows[rows[cols["from"]].astype(float).astype(int) != current_ts]
        except Exception:
            pass

    rows = rows.tail(STRUCTURE_LOOKBACK)
    if len(rows) < 3:
        result["reason"] = "menos de 3 M1 anteriores"
        return result

    def vals(row):
        return (
            _to_float(row.get(cols["open"])),
            _to_float(row.get(cols["high"])),
            _to_float(row.get(cols["low"])),
            _to_float(row.get(cols["close"])),
        )

    parsed = [vals(row) for _, row in rows.iterrows()]
    parsed = [x for x in parsed if None not in x and x[1] >= x[2]]
    if len(parsed) < 3:
        result["reason"] = "historial M1 inválido"
        return result

    # Las dos últimas velas previas forman la tendencia y la última
    # debe ser el retroceso contra esa tendencia.
    a, b, pull = parsed[-3], parsed[-2], parsed[-1]
    ao, ah, al, ac = a
    bo, bh, bl, bc = b
    po, ph, pl, pc = pull

    co = _to_float(candle_1m.get("open"))
    ch = _to_float(candle_1m.get("high"))
    cl = _to_float(candle_1m.get("low"))
    cc = _to_float(candle_1m.get("close"))
    if None in (co, ch, cl, cc) or ch < cl:
        result["reason"] = "M1 N inválida"
        return result

    n_range = ch - cl
    n_body = abs(cc - co)
    if n_range <= 0:
        return result
    n_body_ratio = n_body / n_range
    n_position = (cc - cl) / n_range

    bearish_structure = (
        ac < ao and bc < bo
        and bc < ac
        and pc > po
    )
    bullish_structure = (
        ac > ao and bc > bo
        and bc > ac
        and pc < po
    )

    if bearish_structure:
        # El cierre de N debe romper el mínimo del retroceso y quedar
        # en la parte baja del rango: eso define la reanudación bajista.
        impulse = (
            cc < pl
            and cc < co
            and n_body_ratio >= IMPULSE_BODY_RATIO
            and n_position <= IMPULSE_CLOSE_PUT
        )
        result.update({
            "structure": "BEARISH",
            "pullback": True,
            "impulse": bool(impulse),
        })
        if impulse:
            result["confirmed"] = True
            result["reason"] = "estructura bajista + retroceso alcista + nuevo impulso bajista"
        else:
            result["reason"] = "estructura bajista y retroceso, pero N no confirma nuevo impulso"
        return result

    if bullish_structure:
        impulse = (
            cc > ph
            and cc > co
            and n_body_ratio >= IMPULSE_BODY_RATIO
            and n_position >= IMPULSE_CLOSE_CALL
        )
        result.update({
            "structure": "BULLISH",
            "pullback": True,
            "impulse": bool(impulse),
        })
        if impulse:
            result["confirmed"] = True
            result["reason"] = "estructura alcista + retroceso bajista + nuevo impulso alcista"
        else:
            result["reason"] = "estructura alcista y retroceso, pero N no confirma nuevo impulso"
        return result

    result["reason"] = "no hay tendencia + retroceso claramente definido"
    return result


# ============================================================
# ANALISIS DE LA M1 CERRADA
# ============================================================

def analyze_minute(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Analiza únicamente la vela M1 N después de su cierre."""

    result: Dict[str, Any] = {
        "signal": None,
        "valid": False,
        "reason": "sin señal",
        "minute_timestamp": None,
        "minute_open": None,
        "minute_close": None,
        "high": None,
        "low": None,
        "range": 0.0,
        "body": 0.0,
        "body_ratio": 0.0,
        "upper_wick": 0.0,
        "lower_wick": 0.0,
        "close_position": None,
        "direction": "NEUTRAL",
        "state": "INDECISION",
        "fuerza": False,
        "continuidad": False,
        "reversion": False,
        "indecision": False,
        "debilidad": False,
        "doji": False,
        "quality_checks": {},
        "structure_confirmed": False,
        "structure": "NONE",
        "pullback": False,
        "impulse": False,
        "structure_reason": "sin estructura confirmada",
    }

    ohlc = _get_ohlc(candle_1m)
    if ohlc is None:
        result["reason"] = "OHLC de M1 inválido"
        return result

    opening, high, low, closing = ohlc

    result["minute_open"] = opening
    result["minute_close"] = closing
    result["high"] = high
    result["low"] = low

    if "from" in candle_1m.index:
        try:
            result["minute_timestamp"] = int(float(candle_1m["from"]))
        except (TypeError, ValueError):
            pass

    candle_range = high - low
    body = abs(closing - opening)
    upper_wick = max(0.0, high - max(opening, closing))
    lower_wick = max(0.0, min(opening, closing) - low)

    result["range"] = candle_range
    result["body"] = body
    result["upper_wick"] = upper_wick
    result["lower_wick"] = lower_wick

    if candle_range <= 0:
        result["direction"] = "NEUTRAL"
        result["state"] = "DOJI"
        result["doji"] = True
        result["indecision"] = True
        result["reason"] = "sin señal: M1 sin rango"
        return result

    body_ratio = body / candle_range
    close_position = (closing - low) / candle_range

    result["body_ratio"] = body_ratio
    result["close_position"] = close_position

    if closing > opening:
        direction = "BULLISH"
    elif closing < opening:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    result["direction"] = direction

    # --------------------------------------------------------
    # ESTADOS DE LA M1 YA CERRADA
    # --------------------------------------------------------

    doji = body_ratio <= DOJI_BODY_RATIO
    indecision = body_ratio <= INDECISION_BODY_RATIO

    fuerza = (
        body_ratio >= FORCE_BODY_RATIO
        and (
            close_position >= 0.75
            or close_position <= 0.25
        )
    )

    continuidad = (
        body_ratio >= CONTINUITY_BODY_RATIO
        and (
            (direction == "BULLISH" and close_position >= 0.65)
            or (direction == "BEARISH" and close_position <= 0.35)
        )
    )

    reversion = (
        (direction == "BULLISH" and lower_wick > body * 1.5 and close_position >= 0.50)
        or (direction == "BEARISH" and upper_wick > body * 1.5 and close_position <= 0.50)
    )

    debilidad = (
        not doji
        and body_ratio < WEAKNESS_BODY_RATIO
        and max(upper_wick, lower_wick) > body
    )

    result["fuerza"] = fuerza
    result["continuidad"] = continuidad
    result["reversion"] = reversion
    result["indecision"] = indecision
    result["debilidad"] = debilidad
    result["doji"] = doji

    if doji:
        state = "DOJI"
    elif fuerza:
        state = "FUERZA"
    elif reversion:
        state = "REVERSIÓN"
    elif continuidad:
        state = "CONTINUIDAD"
    elif debilidad:
        state = "DEBILIDAD"
    elif indecision:
        state = "INDECISIÓN"
    else:
        state = "MOVIMIENTO"

    result["state"] = state

    # --------------------------------------------------------
    # CONFIRMACIÓN DEL MEJOR PUNTO DE ENTRADA
    # --------------------------------------------------------
    # N debe ser la vela de reanudación después de un retroceso.
    # Esto solo filtra la señal; no usa ningún dato de N+1.
    structure = _structure_confirmation(candle_1m, previous_m1)
    result["structure_confirmed"] = structure["confirmed"]
    result["structure"] = structure["structure"]
    result["pullback"] = structure["pullback"]
    result["impulse"] = structure["impulse"]
    result["structure_reason"] = structure["reason"]

    # --------------------------------------------------------
    # DECISION FINAL: SOLO CON N CERRADA
    # --------------------------------------------------------

    if doji or direction == "NEUTRAL":
        result["reason"] = "sin señal: M1 neutral/doji"
        return result

    if direction == "BULLISH":
        if not structure["confirmed"] or structure["structure"] != "BULLISH":
            result["reason"] = "sin señal: falta reanudación alcista después del retroceso"
            return result
        result["signal"] = "call"
        result["valid"] = True
        result["reason"] = f"CALL confirmada al cierre de N: {state} + nuevo impulso alcista"
        return result

    if not structure["confirmed"] or structure["structure"] != "BEARISH":
        result["reason"] = "sin señal: falta reanudación bajista después del retroceso"
        return result

    result["signal"] = "put"
    result["valid"] = True
    result["reason"] = f"PUT confirmada al cierre de N: {state} + nuevo impulso bajista"
    return result


def check_pattern(candles_5s=None):
    """Compatibilidad con verificadores antiguos.

    La estrategia actual NO utiliza velas de 5 segundos para decidir.
    Las decisiones se realizan exclusivamente con la M1 ya cerrada
    mediante analyze_market().
    """
    return None


def build_n1_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Compatibilidad con versiones anteriores de bot.py.

    Usa exactamente el mismo análisis de la M1 cerrada.
    No añade ninguna lógica ni utiliza 5 segundos para decidir.
    """
    return analyze_market(candle_1m, candles_5s, previous_m1)


# ============================================================
# API PRINCIPAL
# ============================================================

def analyze_market(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    return analyze_minute(candle_1m, candles_5s, previous_m1)


def get_m1_direction(candle_1m=None):
    """Compatibilidad con versiones anteriores de bot.py.

    La dirección se obtiene únicamente de una M1 ya cerrada.
    No analiza ni utiliza velas de 5 segundos.
    Devuelve BULLISH, BEARISH o NEUTRAL.
    """
    if candle_1m is None:
        return None

    # Permite recibir una sola fila de pandas o un diccionario.
    try:
        if hasattr(candle_1m, "columns") and hasattr(candle_1m, "iloc"):
            if len(candle_1m) == 0:
                return None
            candle_1m = candle_1m.iloc[-1]
    except Exception:
        return None

    try:
        opening = _to_float(candle_1m.get("open"))
        closing = _to_float(candle_1m.get("close"))
    except AttributeError:
        return None

    if opening is None or closing is None:
        return None

    if closing > opening:
        return "BULLISH"
    if closing < opening:
        return "BEARISH"
    return "NEUTRAL"


def get_signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    return analyze_market(candle_1m, candles_5s, previous_m1).get("signal")


def signal(
    candle_1m: pd.Series,
    candles_5s: Optional[pd.DataFrame] = None,
    previous_m1: Optional[pd.DataFrame] = None,
) -> Optional[str]:
    return get_signal(candle_1m, candles_5s, previous_m1)


if __name__ == "__main__":
    print("strategy.py cargado correctamente.")
    print("Estrategia: M1 completa -> cierre -> decisión -> N+1")
