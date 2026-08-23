from __future__ import annotations

import csv
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_market


# ============================================================
# PAPER TRADING / BACKTEST
# ============================================================
#
# IMPORTANTE
# ------------------------------------------------------------
# Este archivo NO utiliza IQ.buy().
#
# La estrategia utilizada es la de strategy.py:
#
#     analyze_market()
#
# El sistema:
#
# 1. Analiza los mercados.
# 2. Detecta una señal CALL / PUT.
# 3. Registra la entrada hipotética en N+1.
# 4. Espera 1 minuto.
# 5. Compara entrada vs precio de expiración.
# 6. Determina WIN / LOSS / DRAW.
# 7. Guarda todas las operaciones en CSV.
#
# MODOS:
#
# PAPER_LIVE = True
#     Observa el mercado real pero NO opera.
#
# PAPER_LIVE = False
#     Permite utilizar datos históricos para backtest.
#
# ============================================================


# ============================================================
# CONFIGURACIÓN IQ OPTION
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

TIMEFRAME = 60

CANDLE_COUNT = 120

EXPIRATION = 1

AMOUNT = 100


# ============================================================
# PAPER TRADING
# ============================================================

PAPER_LIVE = True

# Solo registrar la mejor señal de cada minuto.
ONE_SIGNAL_PER_MINUTE = True

# Score mínimo compatible con tu bot.
MIN_MARKET_SCORE = 82

# Cantidad máxima de mercados mostrados en ranking.
TOP_MARKETS_TO_LOG = 10


# ============================================================
# VELOCIDAD
# ============================================================

POLL_INTERVAL = 0.20

ASSET_REFRESH_INTERVAL = 60


# ============================================================
# ARCHIVOS
# ============================================================

TRADES_FILE = "paper_trades.csv"

SUMMARY_FILE = "paper_summary.csv"


# ============================================================
# TELEGRAM OPCIONAL
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TELEGRAM_HTTP_TIMEOUT = 3.0


# ============================================================
# ESTADO
# ============================================================

IQ: Optional[IQ_Option] = None

BOT_RUNNING = True

AVAILABLE_OTC_PAIRS: List[str] = []

LAST_ASSET_REFRESH = 0.0

STREAMS_STARTED_FOR: Dict[str, bool] = {}

LAST_ANALYZED_MINUTE: Optional[int] = None

PENDING_PAPER_TRADES: List[
    Dict[str, Any]
] = []

TRADE_HISTORY: List[
    Dict[str, Any]
] = []


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

logger = logging.getLogger(__name__)


# ============================================================
# TELEGRAM
# ============================================================

def telegram_send(
    message: str,
) -> bool:

    if (
        not TELEGRAM_TOKEN
        or not TELEGRAM_CHAT_ID
    ):
        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    try:

        response = requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=TELEGRAM_HTTP_TIMEOUT,
        )

        return response.status_code == 200

    except Exception:

        return False


# ============================================================
# CONEXIÓN
# ============================================================

def connect_iq() -> bool:

    global IQ

    if not IQ_EMAIL:
        raise ValueError(
            "Falta IQ_EMAIL"
        )

    if not IQ_PASSWORD:
        raise ValueError(
            "Falta IQ_PASSWORD"
        )

    logger.info(
        "Conectando a IQ Option..."
    )

    IQ = IQ_Option(
        IQ_EMAIL,
        IQ_PASSWORD,
    )

    connected, reason = IQ.connect()

    if not connected:

        raise ConnectionError(
            f"No se pudo conectar: {reason}"
        )

    logger.info(
        "IQ Option conectado."
    )

    refresh_otc_assets(
        force=True
    )

    return True


def ensure_connection() -> bool:

    global IQ

    try:

        if IQ is None:
            return connect_iq()

        if IQ.check_connect():
            return True

        logger.warning(
            "Conexión perdida. Reconectando..."
        )

        connected, reason = IQ.connect()

        if not connected:

            logger.error(
                "Reconexión fallida: %s",
                reason,
            )

            return False

        refresh_otc_assets(
            force=True
        )

        return True

    except Exception as exc:

        logger.error(
            "Error conexión IQ: %s",
            exc,
        )

        return False


# ============================================================
# TIMESTAMP SERVIDOR
# ============================================================

def get_server_timestamp() -> Optional[int]:

    if IQ is None:
        return None

    try:

        timestamp = (
            IQ.get_server_timestamp()
        )

        if timestamp is None:
            return None

        return int(
            float(timestamp)
        )

    except Exception:

        return None


# ============================================================
# DESCUBRIR OTC
# ============================================================

def is_asset_usable(
    active: Dict[str, Any],
) -> bool:

    if not isinstance(
        active,
        dict,
    ):
        return False

    if not bool(
        active.get(
            "enabled",
            False,
        )
    ):
        return False

    if bool(
        active.get(
            "is_suspended",
            False,
        )
    ):
        return False

    return True


def extract_symbol(
    active: Dict[str, Any],
) -> Optional[str]:

    try:

        raw_name = str(
            active.get(
                "name",
                "",
            )
        )

        if not raw_name:
            return None

        if "." in raw_name:

            return raw_name.split(
                ".",
                1,
            )[1]

        return raw_name

    except Exception:

        return None


def discover_otc_assets() -> List[str]:

    if IQ is None:
        return []

    found = set()

    try:

        init_data = (
            IQ.get_all_init_v2()
        )

        if not isinstance(
            init_data,
            dict,
        ):
            return []

        for option_type in (
            "binary",
            "turbo",
        ):

            option_data = (
                init_data.get(
                    option_type,
                    {},
                )
            )

            if not isinstance(
                option_data,
                dict,
            ):
                continue

            actives = (
                option_data.get(
                    "actives",
                    {},
                )
            )

            if not isinstance(
                actives,
                dict,
            ):
                continue

            for active in actives.values():

                if not is_asset_usable(
                    active
                ):
                    continue

                symbol = extract_symbol(
                    active
                )

                if not symbol:
                    continue

                if (
                    "-OTC"
                    not in symbol.upper()
                ):
                    continue

                found.add(
                    symbol
                )

    except Exception as exc:

        logger.warning(
            "Error descubriendo OTC: %s",
            exc,
        )

    return sorted(found)


def refresh_otc_assets(
    force: bool = False,
) -> None:

    global AVAILABLE_OTC_PAIRS
    global LAST_ASSET_REFRESH

    now = time.time()

    if (
        not force
        and now - LAST_ASSET_REFRESH
        < ASSET_REFRESH_INTERVAL
    ):
        return

    pairs = discover_otc_assets()

    if pairs:

        AVAILABLE_OTC_PAIRS = pairs

        logger.info(
            "OTC disponibles: %s",
            len(
                AVAILABLE_OTC_PAIRS
            ),
        )

    LAST_ASSET_REFRESH = now


# ============================================================
# STREAM
# ============================================================

def ensure_pair_stream(
    pair: str,
) -> bool:

    if IQ is None:
        return False

    if STREAMS_STARTED_FOR.get(
        pair,
        False,
    ):
        return True

    try:

        IQ.start_candles_stream(
            pair,
            TIMEFRAME,
            CANDLE_COUNT,
        )

        STREAMS_STARTED_FOR[pair] = True

        logger.info(
            "%s | stream iniciado",
            pair,
        )

        return True

    except Exception as exc:

        logger.warning(
            "%s | stream error: %s",
            pair,
            exc,
        )

        return False


# ============================================================
# DATAFRAME REALTIME
# ============================================================

def realtime_dataframe(
    pair: str,
) -> Optional[pd.DataFrame]:

    if IQ is None:
        return None

    try:

        candles = (
            IQ.get_realtime_candles(
                pair,
                TIMEFRAME,
            )
        )

        if not candles:
            return None

        rows = []

        for timestamp, candle in candles.items():

            try:

                rows.append(
                    {
                        "from": int(
                            float(timestamp)
                        ),
                        "open": float(
                            candle["open"]
                        ),
                        "close": float(
                            candle["close"]
                        ),
                        "high": float(
                            candle.get(
                                "max",
                                candle.get(
                                    "high"
                                ),
                            )
                        ),
                        "low": float(
                            candle.get(
                                "min",
                                candle.get(
                                    "low"
                                ),
                            )
                        ),
                        "volume": float(
                            candle.get(
                                "volume",
                                0,
                            )
                        ),
                    }
                )

            except Exception:
                continue

        if not rows:
            return None

        df = pd.DataFrame(rows)

        df.sort_values(
            "from",
            inplace=True,
        )

        df.drop_duplicates(
            subset=["from"],
            keep="last",
            inplace=True,
        )

        df.reset_index(
            drop=True,
            inplace=True,
        )

        return df.tail(
            CANDLE_COUNT
        ).copy()

    except Exception as exc:

        logger.warning(
            "%s | dataframe error: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# VELA CERRADA
# ============================================================

def get_closed_candle(
    df: pd.DataFrame,
    server_ts: int,
) -> Optional[pd.Series]:

    if df is None or len(df) < 2:
        return None

    current_minute = (
        int(server_ts)
        // TIMEFRAME
    ) * TIMEFRAME

    candidates = df[
        df["from"] < current_minute
    ]

    if len(candidates) == 0:
        return None

    return candidates.iloc[-1]


# ============================================================
# PRECIO DE ENTRADA
# ============================================================

def get_next_candle(
    df: pd.DataFrame,
    closed_timestamp: int,
) -> Optional[pd.Series]:

    if df is None or len(df) == 0:
        return None

    next_timestamp = (
        closed_timestamp
        + TIMEFRAME
    )

    rows = df[
        df["from"]
        >= next_timestamp
    ]

    if len(rows) == 0:
        return None

    return rows.iloc[0]


# ============================================================
# PRECIO DE EXPIRACIÓN
# ============================================================

def get_expiration_candle(
    df: pd.DataFrame,
    entry_timestamp: int,
) -> Optional[pd.Series]:

    if df is None:
        return None

    expiration_timestamp = (
        entry_timestamp
        + TIMEFRAME
    )

    rows = df[
        df["from"]
        >= expiration_timestamp
    ]

    if len(rows) == 0:
        return None

    return rows.iloc[0]


# ============================================================
# RESULTADO DE OPERACIÓN
# ============================================================

def calculate_result(
    signal: str,
    entry_price: float,
    expiration_price: float,
) -> str:

    if signal == "call":

        if expiration_price > entry_price:
            return "WIN"

        if expiration_price < entry_price:
            return "LOSS"

        return "DRAW"

    if signal == "put":

        if expiration_price < entry_price:
            return "WIN"

        if expiration_price > entry_price:
            return "LOSS"

        return "DRAW"

    return "INVALID"


# ============================================================
# CREAR PAPER TRADE
# ============================================================

def create_paper_trade(
    result: Dict[str, Any],
    df: pd.DataFrame,
) -> Optional[Dict[str, Any]]:

    pair = result.get("pair")

    signal = result.get(
        "signal"
    )

    if signal not in (
        "call",
        "put",
    ):
        return None

    closed_timestamp = int(
        result[
            "minute_timestamp"
        ]
    )

    next_timestamp = (
        closed_timestamp
        + TIMEFRAME
    )

    entry_candle = get_next_candle(
        df,
        closed_timestamp,
    )

    if entry_candle is None:

        logger.info(
            "%s | N+1 todavía no disponible",
            pair,
        )

        return None

    entry_price = float(
        entry_candle["open"]
    )

    expiration_timestamp = (
        next_timestamp
        + TIMEFRAME
    )

    trade = {
        "id": len(TRADE_HISTORY)
        + len(PENDING_PAPER_TRADES)
        + 1,

        "pair": pair,

        "signal": signal,

        "score": int(
            result.get(
                "score",
                0,
            )
        ),

        "direction": result.get(
            "direction"
        ),

        "signal_timestamp": closed_timestamp,

        "entry_timestamp": next_timestamp,

        "expiration_timestamp":
            expiration_timestamp,

        "entry_price": entry_price,

        "expiration_price": None,

        "result": "PENDING",

        "profit": None,

        "reason": result.get(
            "reason",
            "",
        ),

        "structure_score": int(
            result.get(
                "structure",
                {},
            ).get(
                "score",
                0,
            )
        ),

        "continuity_score": int(
            result.get(
                "continuity",
                {},
            ).get(
                "score",
                0,
            )
        ),

        "confirmation_score": int(
            result.get(
                "confirmation",
                {},
            ).get(
                "score",
                0,
            )
        ),

        "created_at": datetime.now().isoformat(),
    }

    return trade


# ============================================================
# RESOLVER PAPER TRADE
# ============================================================

def resolve_paper_trade(
    trade: Dict[str, Any],
    df: pd.DataFrame,
    server_ts: int,
) -> bool:

    expiration_timestamp = int(
        trade[
            "expiration_timestamp"
        ]
    )

    if server_ts < expiration_timestamp:
        return False

    rows = df[
        df["from"]
        >= expiration_timestamp
    ]

    if len(rows) == 0:
        return False

    expiration_candle = (
        rows.iloc[0]
    )

    expiration_price = float(
        expiration_candle["open"]
    )

    entry_price = float(
        trade["entry_price"]
    )

    signal = trade["signal"]

    outcome = calculate_result(
        signal,
        entry_price,
        expiration_price,
    )

    trade[
        "expiration_price"
    ] = expiration_price

    trade[
        "result"
    ] = outcome

    if outcome == "WIN":

        trade["profit"] = float(
            AMOUNT * 0.80
        )

    elif outcome == "LOSS":

        trade["profit"] = float(
            -AMOUNT
        )

    else:

        trade["profit"] = 0.0

    TRADE_HISTORY.append(
        trade.copy()
    )

    save_trade(
        trade
    )

    logger.info(
        "PAPER RESULT | %s | %s | "
        "entrada=%.6f | expiración=%.6f | "
        "%s | profit=%.2f",
        trade["pair"],
        signal.upper(),
        entry_price,
        expiration_price,
        outcome,
        trade["profit"],
    )

    return True


# ============================================================
# GUARDAR OPERACIÓN
# ============================================================

def save_trade(
    trade: Dict[str, Any],
) -> None:

    exists = os.path.exists(
        TRADES_FILE
    )

    fieldnames = [
        "id",
        "pair",
        "signal",
        "score",
        "direction",
        "signal_timestamp",
        "entry_timestamp",
        "expiration_timestamp",
        "entry_price",
        "expiration_price",
        "result",
        "profit",
        "reason",
        "structure_score",
        "continuity_score",
        "confirmation_score",
        "created_at",
    ]

    try:

        with open(
            TRADES_FILE,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fieldnames,
            )

            if not exists:
                writer.writeheader()

            writer.writerow(
                {
                    key: trade.get(
                        key
                    )
                    for key in fieldnames
                }
            )

    except Exception as exc:

        logger.error(
            "Error guardando trade: %s",
            exc,
        )


# ============================================================
# RANKING
# ============================================================

def select_best_market(
    results: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    valid_results = [
        result
        for result in results
        if result.get("valid")
        and result.get("signal")
        in ("call", "put")
        and int(
            result.get(
                "score",
                0,
            )
        ) >= MIN_MARKET_SCORE
    ]

    if not valid_results:
        return None

    valid_results.sort(
        key=lambda item: (
            int(
                item.get(
                    "score",
                    0,
                )
            ),

            int(
                item.get(
                    "continuity",
                    {},
                ).get(
                    "score",
                    0,
                )
            ),

            int(
                item.get(
                    "confirmation",
                    {},
                ).get(
                    "score",
                    0,
                )
            ),
        ),
        reverse=True,
    )

    return valid_results[0]


def log_market_ranking(
    results: List[Dict[str, Any]],
) -> None:

    ranking = sorted(
        results,
        key=lambda item: int(
            item.get(
                "score",
                0,
            )
        ),
        reverse=True,
    )

    logger.info(
        "================ RANKING ================"
    )

    for result in ranking[
        :TOP_MARKETS_TO_LOG
    ]:

        logger.info(
            "RANK | %s | score=%s | "
            "signal=%s | direction=%s | %s",
            result.get("pair"),
            result.get("score"),
            result.get("signal"),
            result.get("direction"),
            result.get("reason"),
        )


# ============================================================
# ANALIZAR TODOS LOS MERCADOS
# ============================================================

def analyze_all_markets(
    server_ts: int,
) -> List[
    Dict[str, Any]
]:

    results = []

    for pair in AVAILABLE_OTC_PAIRS:

        try:

            if not ensure_pair_stream(
                pair
            ):
                continue

            df = realtime_dataframe(
                pair
            )

            if df is None:
                continue

            if len(df) < 10:
                continue

            closed = get_closed_candle(
                df,
                server_ts,
            )

            if closed is None:
                continue

            closed_ts = int(
                closed["from"]
            )

            history = df[
                df["from"]
                <= closed_ts
            ].copy()

            result = analyze_market(
                closed,
                previous_m1=history,
            )

            result[
                "pair"
            ] = pair

            result[
                "minute_timestamp"
            ] = closed_ts

            results.append(
                result
            )

        except Exception:

            logger.exception(
                "%s | error análisis",
                pair,
            )

    return results


# ============================================================
# PROCESAR SEÑAL
# ============================================================

def process_signal(
    result: Dict[str, Any],
    server_ts: int,
) -> None:

    if not result.get(
        "valid"
    ):
        return

    if result.get(
        "signal"
    ) not in (
        "call",
        "put",
    ):
        return

    pair = result.get(
        "pair"
    )

    if not pair:
        return

    if int(
        result.get(
            "score",
            0,
        )
    ) < MIN_MARKET_SCORE:
        return

    # --------------------------------------------------------
    # EVITAR DUPLICADOS
    # --------------------------------------------------------

    signal_timestamp = int(
        result[
            "minute_timestamp"
        ]
    )

    for trade in PENDING_PAPER_TRADES:

        if (
            trade.get("pair")
            == pair
            and trade.get(
                "signal_timestamp"
            )
            == signal_timestamp
        ):
            return

    for trade in TRADE_HISTORY:

        if (
            trade.get("pair")
            == pair
            and trade.get(
                "signal_timestamp"
            )
            == signal_timestamp
        ):
            return

    # --------------------------------------------------------
    # OBTENER DATA
    # --------------------------------------------------------

    df = realtime_dataframe(
        pair
    )

    if df is None:
        return

    trade = create_paper_trade(
        result,
        df,
    )

    if trade is None:
        return

    PENDING_PAPER_TRADES.append(
        trade
    )

    direction = (
        "CALL 🟢"
        if trade["signal"]
        == "call"
        else "PUT 🔴"
    )

    logger.info(
        "PAPER ENTRY | %s | %s | "
        "score=%s | entrada=%.6f",
        pair,
        direction,
        trade["score"],
        trade["entry_price"],
    )

    telegram_send(
        "📝 PAPER TRADE\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n"
        f"Score: {trade['score']}/100\n\n"
        f"Entrada N+1: "
        f"{trade['entry_price']}\n"
        f"Expiración: "
        f"{trade['expiration_timestamp']}\n\n"
        "⚠️ NO SE EJECUTÓ DINERO REAL"
    )


# ============================================================
# RESOLVER TODAS LAS OPERACIONES
# ============================================================

def resolve_pending_trades(
    server_ts: int,
) -> None:

    if not PENDING_PAPER_TRADES:
        return

    remaining = []

    for trade in PENDING_PAPER_TRADES:

        try:

            pair = trade[
                "pair"
            ]

            df = realtime_dataframe(
                pair
            )

            if df is None:

                remaining.append(
                    trade
                )

                continue

            resolved = (
                resolve_paper_trade(
                    trade,
                    df,
                    server_ts,
                )
            )

            if not resolved:

                remaining.append(
                    trade
                )

        except Exception:

            logger.exception(
                "%s | error resolviendo paper trade",
                trade.get(
                    "pair"
                ),
            )

            remaining.append(
                trade
            )

    PENDING_PAPER_TRADES.clear()

    PENDING_PAPER_TRADES.extend(
        remaining
    )


# ============================================================
# ESTADÍSTICAS
# ============================================================

def calculate_statistics() -> Dict[str, Any]:

    total = len(
        TRADE_HISTORY
    )

    wins = sum(
        1
        for trade in TRADE_HISTORY
        if trade.get(
            "result"
        ) == "WIN"
    )

    losses = sum(
        1
        for trade in TRADE_HISTORY
        if trade.get(
            "result"
        ) == "LOSS"
    )

    draws = sum(
        1
        for trade in TRADE_HISTORY
        if trade.get(
            "result"
        ) == "DRAW"
    )

    profit = sum(
        float(
            trade.get(
                "profit",
                0.0,
            )
            or 0.0
        )
        for trade in TRADE_HISTORY
    )

    decided = (
        wins
        + losses
    )

    win_rate = (
        wins / decided * 100
        if decided > 0
        else 0.0
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": win_rate,
        "profit": profit,
    }


# ============================================================
# ESTADÍSTICAS POR PAR
# ============================================================

def statistics_by_pair() -> pd.DataFrame:

    if not TRADE_HISTORY:

        return pd.DataFrame()

    rows = []

    pairs = sorted(
        set(
            trade["pair"]
            for trade in TRADE_HISTORY
        )
    )

    for pair in pairs:

        trades = [
            trade
            for trade in TRADE_HISTORY
            if trade["pair"] == pair
        ]

        wins = sum(
            trade["result"] == "WIN"
            for trade in trades
        )

        losses = sum(
            trade["result"] == "LOSS"
            for trade in trades
        )

        draws = sum(
            trade["result"] == "DRAW"
            for trade in trades
        )

        decided = (
            wins + losses
        )

        win_rate = (
            wins / decided * 100
            if decided > 0
            else 0.0
        )

        profit = sum(
            float(
                trade.get(
                    "profit",
                    0,
                )
                or 0
            )
            for trade in trades
        )

        rows.append(
            {
                "pair": pair,
                "trades": len(trades),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": round(
                    win_rate,
                    2,
                ),
                "profit": round(
                    profit,
                    2,
                ),
            }
        )

    return pd.DataFrame(
        rows
    ).sort_values(
        "win_rate",
        ascending=False,
    )


# ============================================================
# ESTADÍSTICAS POR SEÑAL
# ============================================================

def statistics_by_signal() -> pd.DataFrame:

    if not TRADE_HISTORY:

        return pd.DataFrame()

    rows = []

    for signal in (
        "call",
        "put",
    ):

        trades = [
            trade
            for trade in TRADE_HISTORY
            if trade["signal"]
            == signal
        ]

        wins = sum(
            trade["result"] == "WIN"
            for trade in trades
        )

        losses = sum(
            trade["result"] == "LOSS"
            for trade in trades
        )

        draws = sum(
            trade["result"] == "DRAW"
            for trade in trades
        )

        decided = (
            wins + losses
        )

        win_rate = (
            wins / decided * 100
            if decided > 0
            else 0.0
        )

        profit = sum(
            float(
                trade.get(
                    "profit",
                    0,
                )
                or 0
            )
            for trade in trades
        )

        rows.append(
            {
                "signal": signal,
                "trades": len(trades),
                "wins": wins,
                "losses": losses,
                "draws": draws,
                "win_rate": round(
                    win_rate,
                    2,
                ),
                "profit": round(
                    profit,
                    2,
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# GUARDAR RESUMEN
# ============================================================

def save_summary() -> None:

    stats = calculate_statistics()

    summary = pd.DataFrame(
        [
            stats
        ]
    )

    summary[
        "generated_at"
    ] = datetime.now().isoformat()

    try:

        summary.to_csv(
            SUMMARY_FILE,
            index=False,
        )

    except Exception as exc:

        logger.error(
            "Error guardando resumen: %s",
            exc,
        )


# ============================================================
# MOSTRAR ESTADÍSTICAS
# ============================================================

def print_statistics() -> None:

    stats = calculate_statistics()

    logger.info(
        "======================================"
    )

    logger.info(
        "PAPER TRADING STATISTICS"
    )

    logger.info(
        "Operaciones: %s",
        stats["total"],
    )

    logger.info(
        "WIN: %s",
        stats["wins"],
    )

    logger.info(
        "LOSS: %s",
        stats["losses"],
    )

    logger.info(
        "DRAW: %s",
        stats["draws"],
    )

    logger.info(
        "WIN RATE: %.2f%%",
        stats["win_rate"],
    )

    logger.info(
        "P/L: %.2f",
        stats["profit"],
    )

    logger.info(
        "======================================"
    )


# ============================================================
# PROCESAR CICLO
# ============================================================

def process_cycle() -> None:

    global LAST_ANALYZED_MINUTE

    server_ts = (
        get_server_timestamp()
    )

    if server_ts is None:
        return

    # --------------------------------------------------------
    # RESOLVER OPERACIONES ANTERIORES
    # --------------------------------------------------------

    resolve_pending_trades(
        server_ts
    )

    # --------------------------------------------------------
    # ACTUALIZAR MERCADOS
    # --------------------------------------------------------

    refresh_otc_assets()

    if not AVAILABLE_OTC_PAIRS:
        return

    current_minute = (
        server_ts // TIMEFRAME
    ) * TIMEFRAME

    closed_minute = (
        current_minute
        - TIMEFRAME
    )

    # --------------------------------------------------------
    # SOLO ANALIZAR UNA VEZ CADA MINUTO
    # --------------------------------------------------------

    if (
        LAST_ANALYZED_MINUTE
        == closed_minute
    ):
        return

    results = analyze_all_markets(
        server_ts
    )

    if not results:
        return

    LAST_ANALYZED_MINUTE = (
        closed_minute
    )

    log_market_ranking(
        results
    )

    best = select_best_market(
        results
    )

    if best is None:

        logger.info(
            "NO PAPER TRADE | "
            "ningún mercado alcanzó %s",
            MIN_MARKET_SCORE,
        )

        return

    # --------------------------------------------------------
    # CREAR PAPER TRADE
    # --------------------------------------------------------

    process_signal(
        best,
        server_ts,
    )

    # --------------------------------------------------------
    # ESTADÍSTICAS
    # --------------------------------------------------------

    if len(
        TRADE_HISTORY
    ) % 5 == 0:

        print_statistics()

        save_summary()


# ============================================================
# CARGAR HISTORIAL CSV
# ============================================================

def load_previous_results() -> None:

    global TRADE_HISTORY

    if not os.path.exists(
        TRADES_FILE
    ):
        return

    try:

        df = pd.read_csv(
            TRADES_FILE
        )

        if df.empty:
            return

        TRADE_HISTORY = (
            df.to_dict(
                orient="records"
            )
        )

        logger.info(
            "Historial cargado: %s operaciones",
            len(
                TRADE_HISTORY
            ),
        )

    except Exception as exc:

        logger.warning(
            "No se pudo cargar historial: %s",
            exc,
        )


# ============================================================
# RESUMEN FINAL
# ============================================================

def final_report() -> None:

    print_statistics()

    by_pair = (
        statistics_by_pair()
    )

    if not by_pair.empty:

        logger.info(
            "========= RESULTADOS POR PAR ========="
        )

        for _, row in by_pair.iterrows():

            logger.info(
                "%s | trades=%s | "
                "winrate=%.2f%% | "
                "profit=%.2f",
                row["pair"],
                row["trades"],
                row["win_rate"],
                row["profit"],
            )

    by_signal = (
        statistics_by_signal()
    )

    if not by_signal.empty:

        logger.info(
            "========= RESULTADOS CALL / PUT ========="
        )

        for _, row in by_signal.iterrows():

            logger.info(
                "%s | trades=%s | "
                "winrate=%.2f%% | "
                "profit=%.2f",
                row["signal"].upper(),
                row["trades"],
                row["win_rate"],
                row["profit"],
            )

    save_summary()


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    logger.info(
        "======================================"
    )

    logger.info(
        "PAPER TRADING M1"
    )

    logger.info(
        "NO SE EJECUTAN OPERACIONES REALES"
    )

    logger.info(
        "ESTRATEGIA: strategy.py"
    )

    logger.info(
        "TIMEFRAME: 1 MINUTO"
    )

    logger.info(
        "EXPIRATION: 1 MINUTO"
    )

    logger.info(
        "MIN SCORE: %s",
        MIN_MARKET_SCORE,
    )

    logger.info(
        "CSV: %s",
        TRADES_FILE,
    )

    logger.info(
        "======================================"
    )

    load_previous_results()

    try:

        connect_iq()

    except Exception as exc:

        logger.exception(
            "No se pudo conectar a IQ Option."
        )

        return

    telegram_send(
        "📝 PAPER TRADING ACTIVADO\n\n"
        "⚠️ NO SE EJECUTAN OPERACIONES REALES\n\n"
        "La estrategia analizará los OTC "
        "y registrará qué habría ocurrido "
        "con cada señal N+1.\n\n"
        "⏱ Expiración: 1 minuto"
    )

    try:

        while BOT_RUNNING:

            try:

                if not ensure_connection():

                    time.sleep(1)

                    continue

                process_cycle()

                time.sleep(
                    POLL_INTERVAL
                )

            except KeyboardInterrupt:

                break

            except Exception:

                logger.exception(
                    "Error en ciclo paper trading"
                )

                time.sleep(
                    1
                )

    finally:

        final_report()

        telegram_send(
            "📊 PAPER TRADING FINALIZADO\n\n"
            f"Operaciones: "
            f"{len(TRADE_HISTORY)}\n"
            f"Revisa: {TRADES_FILE}\n"
            f"Resumen: {SUMMARY_FILE}"
        )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
