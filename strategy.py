# ============================================================
# STRATEGY.PY
# IQ OPTION
# M1 + EXACTAMENTE 12 VELAS DE 5 SEGUNDOS
# ============================================================

from typing import Optional, List, Dict, Any


# ============================================================
# CONFIGURACIÓN
# ============================================================

CANDLES_PER_M1 = 12


# ============================================================
# COLOR DE VELA
# ============================================================

def get_candle_color(candle: Dict[str, Any]) -> str:
    """
    Determina el color de una vela usando exclusivamente:

        close > open  -> verde
        close < open  -> rojo
        close == open -> doji
    """

    open_price = float(candle["open"])
    close_price = float(candle["close"])

    if close_price > open_price:
        return "verde"

    if close_price < open_price:
        return "rojo"

    return "doji"


# ============================================================
# CUERPO DE VELA
# ============================================================

def candle_body(candle: Dict[str, Any]) -> float:
    """
    Devuelve:

        close - open
    """

    return (
        float(candle["close"])
        - float(candle["open"])
    )


# ============================================================
# CHECK PATTERN
# ============================================================

def check_pattern(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    FUNCIÓN PRINCIPAL UTILIZADA POR BOT.PY.

    Recibe EXACTAMENTE las 12 velas de 5 segundos
    correspondientes a una M1 cerrada.

    Devuelve:

        "call"
        "put"
        None

    No obtiene datos de IQ Option.
    No abre operaciones.
    No modifica las velas.

    Toda la decisión se realiza aquí.
    """

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if candles_5s is None:
        return None

    if not isinstance(candles_5s, list):
        return None

    if len(candles_5s) != CANDLES_PER_M1:
        print(
            f"[STRATEGY] Se esperaban "
            f"{CANDLES_PER_M1} velas y llegaron "
            f"{len(candles_5s)}."
        )

        return None

    # --------------------------------------------------------
    # VALIDAR DATOS
    # --------------------------------------------------------

    for candle in candles_5s:

        if not isinstance(candle, dict):
            return None

        if "open" not in candle:
            return None

        if "close" not in candle:
            return None

        try:
            float(candle["open"])
            float(candle["close"])

        except Exception:
            return None

    # ========================================================
    # 1. SUMA DE CUERPOS ALCISTAS / BAJISTAS
    # ========================================================

    buy_score = 0.0
    sell_score = 0.0

    for candle in candles_5s:

        body = candle_body(candle)

        if body > 0:
            buy_score += body

        elif body < 0:
            sell_score += abs(body)

    # ========================================================
    # 2. DOMINANCIA
    # ========================================================

    total_score = (
        buy_score
        + sell_score
    )

    if total_score <= 0:
        return None

    dominance = (
        abs(
            buy_score
            - sell_score
        )
        / total_score
    )

    # Mínimo 25 %
    if dominance < 0.25:
        return None

    # ========================================================
    # 3. EFICIENCIA
    # ========================================================

    net_move = abs(
        candle_body(candles_5s[-1])
    )

    total_body = 0.0

    for candle in candles_5s:

        total_body += abs(
            candle_body(candle)
        )

    if total_body <= 0:
        return None

    # Movimiento total de la M1
    m1_move = abs(
        float(candles_5s[-1]["close"])
        - float(candles_5s[0]["open"])
    )

    efficiency = (
        m1_move
        / total_body
    )

    # Mínimo 45 %
    if efficiency < 0.45:
        return None

    # ========================================================
    # 4. CONTROL FINAL
    #    ÚLTIMAS 3 VELAS DE 5S
    # ========================================================

    final_net = 0.0

    for candle in candles_5s[-3:]:

        final_net += candle_body(
            candle
        )

    # ========================================================
    # 5. DECISIÓN
    # ========================================================

    if final_net > 0:

        return "call"

    if final_net < 0:

        return "put"

    return None


# ============================================================
# ALIAS DE COMPATIBILIDAD
# ============================================================

def get_strategy_analysis(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Alias de compatibilidad.

    Utiliza exactamente la misma lógica
    de check_pattern().
    """

    return check_pattern(
        candles_5s
    )


# ============================================================
# DIRECCIÓN M1
# ============================================================

def get_m1_direction(
    candles_5s: List[Dict[str, Any]]
) -> Optional[str]:
    """
    Devuelve la dirección de la M1 usando
    la apertura de la primera vela y el cierre
    de la última.

        cierre > apertura -> call
        cierre < apertura -> put
        igual -> None
    """

    if candles_5s is None:
        return None

    if len(candles_5s) != CANDLES_PER_M1:
        return None

    try:

        m1_open = float(
            candles_5s[0]["open"]
        )

        m1_close = float(
            candles_5s[-1]["close"]
        )

    except Exception:

        return None

    if m1_close > m1_open:
        return "call"

    if m1_close < m1_open:
        return "put"

    return None
