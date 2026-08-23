from __future__ import annotations

import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from iqoptionapi.stable_api import IQ_Option

from strategy import (
    analyze_live_candle,
    analyze_market,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

IQ_EMAIL = os.getenv("IQ_EMAIL")
IQ_PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# TEMPORALIDADES
# ============================================================

TIMEFRAME = 60
CANDLE_COUNT = 62


# ============================================================
# MODO
# ============================================================
#
# Este archivo funciona como SCANNER / GENERADOR / EJECUTOR
# DE SEÑALES.
#
# La estrategia analiza cada mercado.
#
# Cuando una vela N cierra:
#
#   N cierra
#      ↓
#   analizar todos los OTC
#      ↓
#   obtener señales válidas
#      ↓
#   esperar/estar en N+1
#      ↓
#   ejecutar TODAS las señales válidas
#
# La estrategia continúa estando en strategy.py.
#
# ============================================================

EXPIRATION = 1

# Importe de cada operación.
AMOUNT = 35


# ============================================================
# SCANNER
# ============================================================

# Número de workers concurrentes.
#
# No conviene poner un número exageradamente alto porque
# todos los workers utilizan la misma conexión IQ.
#
MAX_WORKERS = 8

# Score mínimo para considerar candidato.
MIN_MARKET_SCORE = 82

# Número de mercados mostrados en ranking.
TOP_MARKETS_TO_LOG = 10

# Actualización de activos.
ASSET_REFRESH_INTERVAL = 60


# ============================================================
# RELOJ
# ============================================================

POLL_INTERVAL = 0.05


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_POLL_INTERVAL = 1.0
TELEGRAM_HTTP_TIMEOUT = 3.0


# ============================================================
# ESTADO GLOBAL
# ============================================================

BOT_RUNNING = False

IQ: Optional[IQ_Option] = None

LAST_UPDATE_ID: Optional[int] = None

AVAILABLE_OTC_PAIRS: List[str] = []

LAST_ASSET_REFRESH = 0.0

STREAMS_STARTED_FOR: Dict[str, bool] = {}

LIVE_M1_STATE: Dict[
    str,
    Dict[str, Any],
] = {}

LAST_PROCESSED_MINUTE: Optional[int] = None

LAST_SIGNAL: Optional[Dict[str, Any]] = None

# ============================================================
# CONTROL DE OPERACIONES
# ============================================================
#
# Guarda la última vela N ejecutada por cada par.
#
# Esto evita que un mismo mercado ejecute dos veces
# la misma señal si process_market_cycle() vuelve a entrar
# durante el mismo minuto.
#
LAST_EXECUTED_SIGNAL: Dict[str, int] = {}

# Evita ejecuciones simultáneas desde distintos hilos.
TRADE_LOCK = threading.Lock()


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

    except Exception as exc:

        logger.warning(
            "Telegram no disponible: %s",
            exc,
        )

        return False


# ============================================================
# TELEGRAM WORKER
# ============================================================

def telegram_worker() -> None:

    global LAST_UPDATE_ID
    global BOT_RUNNING

    if not TELEGRAM_TOKEN:
        return

    logger.info(
        "Telegram worker iniciado."
    )

    while True:

        try:

            url = (
                "https://api.telegram.org/"
                f"bot{TELEGRAM_TOKEN}/getUpdates"
            )

            params: Dict[str, Any] = {
                "timeout": 0,
            }

            if LAST_UPDATE_ID is not None:

                params["offset"] = (
                    LAST_UPDATE_ID + 1
                )

            response = requests.get(
                url,
                params=params,
                timeout=TELEGRAM_HTTP_TIMEOUT,
            )

            if response.status_code != 200:

                time.sleep(
                    TELEGRAM_POLL_INTERVAL
                )

                continue

            data = response.json()

            if not data.get("ok"):

                time.sleep(
                    TELEGRAM_POLL_INTERVAL
                )

                continue

            for update in data.get(
                "result",
                [],
            ):

                LAST_UPDATE_ID = (
                    update.get("update_id")
                )

                message = update.get(
                    "message",
                    {},
                )

                text = str(
                    message.get(
                        "text",
                        "",
                    )
                ).strip().lower()

                chat_id = str(
                    message.get(
                        "chat",
                        {},
                    ).get(
                        "id",
                        "",
                    )
                )

                if (
                    chat_id
                    != str(TELEGRAM_CHAT_ID)
                ):
                    continue

                if text == "/start":

                    BOT_RUNNING = True

                    telegram_send(
                        "🟢 SCANNER ACTIVADO\n\n"
                        "MODO MULTI-OTC\n"
                        "Analizando todos los OTC disponibles.\n"
                        "Todas las señales válidas serán ejecutadas "
                        "en N+1."
                    )

                elif text == "/stop":

                    BOT_RUNNING = False

                    telegram_send(
                        "🔴 SCANNER DETENIDO\n\n"
                        "No se generarán nuevas señales "
                        "ni nuevas operaciones."
                    )

                elif text == "/status":

                    status = (
                        "🟢 ACTIVO"
                        if BOT_RUNNING
                        else "🔴 DETENIDO"
                    )

                    signal_text = (
                        "Sí"
                        if LAST_SIGNAL
                        else "No"
                    )

                    telegram_send(
                        "📊 ESTADO\n\n"
                        f"Estado: {status}\n"
                        "Modo: MULTI-OTC\n"
                        f"OTC disponibles: "
                        f"{len(AVAILABLE_OTC_PAIRS)}\n"
                        f"Expiración: "
                        f"{EXPIRATION} minuto\n"
                        f"Importe: "
                        f"{AMOUNT}\n"
                        f"Última señal: "
                        f"{signal_text}"
                    )

        except Exception as exc:

            logger.warning(
                "Telegram worker: %s",
                exc,
            )

        time.sleep(
            TELEGRAM_POLL_INTERVAL
        )


# ============================================================
# TIMESTAMP
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

    except Exception as exc:

        logger.warning(
            "Error timestamp servidor: %s",
            exc,
        )

        return None


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

    telegram_send(
        "🟢 IQ OPTION CONECTADO\n\n"
        "Scanner MULTI-OTC listo."
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

        telegram_send(
            "🟢 IQ OPTION RECONECTADO"
        )

        return True

    except Exception as exc:

        logger.error(
            "Error conexión IQ: %s",
            exc,
        )

        return False


# ============================================================
# ACTIVOS
# ============================================================

def is_asset_usable(
    active: Dict[str, Any],
) -> bool:

    try:

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

    except Exception:

        return False


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

                found.add(symbol)

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

        previous = set(
            AVAILABLE_OTC_PAIRS
        )

        current = set(pairs)

        added = current - previous
        removed = previous - current

        AVAILABLE_OTC_PAIRS = pairs

        if added:

            logger.info(
                "OTC añadidos: %s",
                ", ".join(
                    sorted(added)
                ),
            )

        if removed:

            logger.info(
                "OTC eliminados: %s",
                ", ".join(
                    sorted(removed)
                ),
            )

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
            "%s | stream M1 iniciado",
            pair,
        )

        return True

    except Exception as exc:

        logger.warning(
            "%s | error stream: %s",
            pair,
            exc,
        )

        return False


def initialize_all_streams() -> None:

    """
    Inicializa todos los streams antes de comenzar
    el escaneo.

    Esto evita intentar crear streams repetidamente
    durante cada ciclo.
    """

    if IQ is None:
        return

    pairs = list(
        AVAILABLE_OTC_PAIRS
    )

    logger.info(
        "Inicializando %s streams M1...",
        len(pairs),
    )

    for pair in pairs:

        if not BOT_RUNNING:
            return

        ensure_pair_stream(
            pair
        )

    logger.info(
        "Streams inicializados: %s",
        len(STREAMS_STARTED_FOR),
    )


# ============================================================
# DATAFRAME
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

        df = pd.DataFrame(
            rows
        )

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
            "%s | realtime error: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# VELA LIVE
# ============================================================

def monitor_live_market(
    pair: str,
    df: pd.DataFrame,
    server_ts: int,
) -> Optional[Dict[str, Any]]:

    if df is None or len(df) == 0:
        return None

    try:

        live = df.iloc[-1]

        live_ts = int(
            live["from"]
        )

        current_minute = (
            int(server_ts)
            // TIMEFRAME
        ) * TIMEFRAME

        if live_ts != current_minute:
            return None

        live_analysis = (
            analyze_live_candle(
                live
            )
        )

        elapsed = int(
            server_ts - live_ts
        )

        previous = LIVE_M1_STATE.get(
            pair
        )

        if (
            previous is None
            or previous.get(
                "timestamp"
            ) != live_ts
        ):

            LIVE_M1_STATE[pair] = {
                "timestamp": live_ts,
                "last_second": elapsed,
                "analysis": live_analysis,
            }

        else:

            previous[
                "last_second"
            ] = elapsed

            previous[
                "analysis"
            ] = live_analysis

        return live_analysis

    except Exception:

        logger.exception(
            "%s | error monitoreo live",
            pair,
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
# ANALIZAR PAR
# ============================================================

def analyze_pair_closed(
    pair: str,
    df: pd.DataFrame,
    closed_candle: pd.Series,
) -> Dict[str, Any]:

    closed_ts = int(
        closed_candle["from"]
    )

    history = df[
        df["from"] <= closed_ts
    ].copy()

    result = analyze_market(
        closed_candle,
        previous_m1=history,
    )

    result["pair"] = pair
    result["minute_timestamp"] = closed_ts

    return result


# ============================================================
# WORKER DE UN SOLO PAR
# ============================================================

def scan_single_pair(
    pair: str,
    server_ts: int,
) -> Optional[Dict[str, Any]]:

    """
    Analiza un único mercado.

    Esta función es independiente para poder ejecutarse
    mediante ThreadPoolExecutor.
    """

    try:

        if not ensure_pair_stream(
            pair
        ):
            return None

        df = realtime_dataframe(
            pair
        )

        if df is None:
            return None

        if len(df) < 10:
            return None

        # Analizar vela viva.
        monitor_live_market(
            pair,
            df,
            server_ts,
        )

        # Buscar última vela cerrada.
        closed_candle = (
            get_closed_candle(
                df,
                server_ts,
            )
        )

        if closed_candle is None:
            return None

        result = analyze_pair_closed(
            pair,
            df,
            closed_candle,
        )

        return result

    except Exception as exc:

        logger.warning(
            "%s | scanner error: %s",
            pair,
            exc,
        )

        return None


# ============================================================
# ANALIZAR TODOS LOS MERCADOS EN PARALELO
# ============================================================

def analyze_all_markets(
    server_ts: int,
) -> List[Dict[str, Any]]:

    """
    Antes:
        PAR 1 → PAR 2 → PAR 3 → PAR 4...

    Ahora:
        PAR 1 ─┐
        PAR 2 ─┤
        PAR 3 ─┤
        PAR 4 ─┤
        PAR 5 ─┤
        ...    ┘
                 ↓
            análisis paralelo

    La estrategia continúa siendo exactamente
    strategy.analyze_market().
    """

    if not AVAILABLE_OTC_PAIRS:
        return []

    pairs = list(
        AVAILABLE_OTC_PAIRS
    )

    results: List[
        Dict[str, Any]
    ] = []

    worker_count = min(
        MAX_WORKERS,
        len(pairs),
    )

    if worker_count <= 0:
        return results

    started = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:

        futures = {
            executor.submit(
                scan_single_pair,
                pair,
                server_ts,
            ): pair
            for pair in pairs
        }

        for future in as_completed(
            futures
        ):

            pair = futures[
                future
            ]

            try:

                result = (
                    future.result()
                )

                if result is not None:

                    results.append(
                        result
                    )

            except Exception as exc:

                logger.warning(
                    "%s | worker error: %s",
                    pair,
                    exc,
                )

    elapsed = (
        time.perf_counter()
        - started
    )

    logger.info(
        "SCAN | %s mercados | "
        "%s resultados | %.3fs",
        len(pairs),
        len(results),
        elapsed,
    )

    return results


# ============================================================
# RANKING
# ============================================================

def select_best_market(
    results: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    valid_results = []

    for result in results:

        if not result.get(
            "valid"
        ):
            continue

        if result.get(
            "signal"
        ) not in (
            "call",
            "put",
        ):
            continue

        score = int(
            result.get(
                "score",
                0,
            )
        )

        if score < MIN_MARKET_SCORE:
            continue

        valid_results.append(
            result
        )

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
                    "structure",
                    {},
                ).get(
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


# ============================================================
# RANKING COMPLETO
# ============================================================

def log_market_ranking(
    results: List[Dict[str, Any]],
) -> None:

    ranking = sorted(
        results,
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
        ),
        reverse=True,
    )

    logger.info(
        "================ RANKING ================"
    )

    for index, result in enumerate(
        ranking[
            :TOP_MARKETS_TO_LOG
        ],
        start=1,
    ):

        logger.info(
            "#%s | %s | score=%s | "
            "direction=%s | signal=%s | "
            "state=%s",
            index,
            result.get("pair"),
            result.get("score"),
            result.get("direction"),
            result.get("signal"),
            result.get("state"),
        )

    logger.info(
        "=========================================="
    )


# ============================================================
# CREAR SEÑAL
# ============================================================

def create_signal(
    result: Dict[str, Any],
) -> Dict[str, Any]:

    signal = {
        "pair": result.get(
            "pair"
        ),
        "signal": result.get(
            "signal"
        ),
        "score": result.get(
            "score",
            0,
        ),
        "direction": result.get(
            "direction"
        ),
        "state": result.get(
            "state"
        ),
        "minute_timestamp": result.get(
            "minute_timestamp"
        ),
        "minute_open": result.get(
            "minute_open"
        ),
        "minute_close": result.get(
            "minute_close"
        ),
        "structure": result.get(
            "structure",
            {},
        ),
        "recent_structure": result.get(
            "recent_structure",
            {},
        ),
        "impulse": result.get(
            "impulse",
            {},
        ),
        "late_trend": result.get(
            "late_trend",
            {},
        ),
        "continuity": result.get(
            "continuity",
            {},
        ),
        "confirmation": result.get(
            "confirmation",
            {},
        ),
        "exhaustion": result.get(
            "exhaustion",
            {},
        ),
        "support_resistance": result.get(
            "support_resistance",
            {},
        ),
        "reason": result.get(
            "reason",
            "",
        ),
        "created_at": time.time(),
    }

    return signal


# ============================================================
# MOSTRAR MEJOR MERCADO
# ============================================================

def publish_best_market(
    result: Dict[str, Any],
) -> None:

    global LAST_SIGNAL

    signal = create_signal(
        result
    )

    LAST_SIGNAL = signal

    pair = signal["pair"]

    direction = (
        "CALL 🟢"
        if signal["signal"] == "call"
        else "PUT 🔴"
    )

    structure = signal[
        "structure"
    ]

    continuity = signal[
        "continuity"
    ]

    confirmation = signal[
        "confirmation"
    ]

    exhaustion = signal[
        "exhaustion"
    ]

    sr = signal[
        "support_resistance"
    ]

    logger.info(
        "🏆 MEJOR MERCADO | %s | %s | "
        "score=%s",
        pair,
        direction,
        signal["score"],
    )

    telegram_send(
        "🏆 MEJOR MERCADO\n\n"
        f"Par: {pair}\n"
        f"Dirección: {direction}\n"
        f"Score: {signal['score']}/100\n\n"
        "ESTRUCTURA\n"
        f"{structure.get('reason')}\n"
        f"Score: {structure.get('score')}\n\n"
        "CONTINUIDAD\n"
        f"{continuity.get('reason')}\n\n"
        "CONFIRMACIÓN\n"
        f"{confirmation.get('reason')}\n\n"
        "AGOTAMIENTO\n"
        f"{exhaustion.get('reason')}\n\n"
        "SOPORTE / RESISTENCIA\n"
        f"{sr.get('reason')}\n\n"
        "🎯 SEÑAL N+1\n"
        f"{signal['signal'].upper()}\n"
        f"Timestamp N: "
        f"{signal['minute_timestamp']}\n"
        f"Expiración: "
        f"{EXPIRATION} minuto"
    )


# ============================================================
# EJECUTAR UNA OPERACIÓN
# ============================================================

def execute_signal(
    signal: Dict[str, Any],
    server_ts: int,
) -> bool:

    if IQ is None:
        return False

    pair = signal.get(
        "pair"
    )

    action = signal.get(
        "signal"
    )

    minute_timestamp = signal.get(
        "minute_timestamp"
    )

    if not pair:
        return False

    if action not in (
        "call",
        "put",
    ):
        return False

    if minute_timestamp is None:
        return False

    try:

        minute_timestamp = int(
            minute_timestamp
        )

    except Exception:

        return False

    current_minute = (
        int(server_ts)
        // TIMEFRAME
    ) * TIMEFRAME

    expected_entry_minute = (
        minute_timestamp
        + TIMEFRAME
    )

    # ========================================================
    # LA SEÑAL DE N SE EJECUTA ÚNICAMENTE EN N+1
    # ========================================================

    if current_minute != expected_entry_minute:

        logger.info(
            "%s | señal descartada | "
            "entrada fuera de N+1 | "
            "N=%s | actual=%s | esperado=%s",
            pair,
            minute_timestamp,
            current_minute,
            expected_entry_minute,
        )

        return False

    # ========================================================
    # EVITAR DUPLICADOS
    # ========================================================

    with TRADE_LOCK:

        last_executed = (
            LAST_EXECUTED_SIGNAL.get(
                pair
            )
        )

        if last_executed == minute_timestamp:

            logger.info(
                "%s | señal N=%s ya ejecutada",
                pair,
                minute_timestamp,
            )

            return False

        try:

            logger.info(
                "🎯 EJECUTANDO | %s | %s | "
                "N=%s | entrada=N+1 | "
                "amount=%s | expiration=%s",
                pair,
                action.upper(),
                minute_timestamp,
                AMOUNT,
                EXPIRATION,
            )

            success, order_id = IQ.buy(
                AMOUNT,
                pair,
                action,
                EXPIRATION,
            )

            if not success:

                logger.error(
                    "%s | ERROR IQ.buy() | "
                    "action=%s | order_id=%s",
                    pair,
                    action,
                    order_id,
                )

                telegram_send(
                    "❌ ERROR EJECUTANDO\n\n"
                    f"Par: {pair}\n"
                    f"Dirección: {action.upper()}\n"
                    f"Importe: {AMOUNT}\n"
                    f"N: {minute_timestamp}\n"
                    f"Respuesta: {order_id}"
                )

                return False

            # =================================================
            # MARCAR COMO EJECUTADA SOLAMENTE SI IQ.buy()
            # CONFIRMÓ LA OPERACIÓN.
            # =================================================

            LAST_EXECUTED_SIGNAL[
                pair
            ] = minute_timestamp

            logger.info(
                "✅ OPERACIÓN EJECUTADA | "
                "%s | %s | "
                "amount=%s | expiration=%s | "
                "order_id=%s",
                pair,
                action.upper(),
                AMOUNT,
                EXPIRATION,
                order_id,
            )

            telegram_send(
                "🚀 OPERACIÓN EJECUTADA\n\n"
                f"Par: {pair}\n"
                f"Dirección: {action.upper()}\n"
                f"Importe: {AMOUNT}\n"
                f"Expiración: {EXPIRATION} minuto\n"
                f"Timestamp N: {minute_timestamp}\n"
                "Entrada: N+1\n"
                f"Order ID: {order_id}"
            )

            return True

        except Exception as exc:

            logger.exception(
                "%s | excepción ejecutando operación",
                pair,
            )

            telegram_send(
                "❌ EXCEPCIÓN EJECUTANDO\n\n"
                f"Par: {pair}\n"
                f"Dirección: {action.upper()}\n"
                f"Error: {exc}"
            )

            return False


# ============================================================
# EJECUTAR TODAS LAS SEÑALES VÁLIDAS
# ============================================================

def execute_all_valid_signals(
    results: List[Dict[str, Any]],
    server_ts: int,
) -> int:

    executable = []

    for result in results:

        # ----------------------------------------------------
        # LA ESTRATEGIA DEBE HABER VALIDADO LA OPERACIÓN
        # ----------------------------------------------------

        if not result.get(
            "valid"
        ):
            continue

        # ----------------------------------------------------
        # SOLO CALL / PUT
        # ----------------------------------------------------

        if result.get(
            "signal"
        ) not in (
            "call",
            "put",
        ):
            continue

        # ----------------------------------------------------
        # SCORE MÍNIMO
        # ----------------------------------------------------

        score = int(
            result.get(
                "score",
                0,
            )
        )

        if score < MIN_MARKET_SCORE:
            continue

        executable.append(
            result
        )

    if not executable:

        logger.info(
            "EXECUTION | no hay operaciones válidas."
        )

        return 0

    # ========================================================
    # ORDENAR POR SCORE
    # ========================================================

    executable.sort(
        key=lambda item: int(
            item.get(
                "score",
                0,
            )
        ),
        reverse=True,
    )

    logger.info(
        "🎯 OPERACIONES CANDIDATAS: %s",
        len(executable),
    )

    for result in executable:

        logger.info(
            "📌 CANDIDATA | %s | %s | score=%s | "
            "timestamp=%s",
            result.get(
                "pair"
            ),
            str(
                result.get(
                    "signal"
                )
            ).upper(),
            result.get(
                "score"
            ),
            result.get(
                "minute_timestamp"
            ),
        )

    # ========================================================
    # EJECUTAR TODAS
    # ========================================================

    executed = 0

    for result in executable:

        signal = create_signal(
            result
        )

        if execute_signal(
            signal,
            server_ts,
        ):

            executed += 1

    logger.info(
        "EXECUTION | %s/%s operaciones ejecutadas.",
        executed,
        len(executable),
    )

    return executed


# ============================================================
# CICLO M1
# ============================================================

def process_market_cycle() -> None:

    global LAST_PROCESSED_MINUTE
    global LAST_SIGNAL

    server_ts = (
        get_server_timestamp()
    )

    if server_ts is None:
        return

    current_minute = (
        server_ts // TIMEFRAME
    ) * TIMEFRAME

    closed_minute = (
        current_minute
        - TIMEFRAME
    )

    if (
        LAST_PROCESSED_MINUTE
        == closed_minute
    ):
        return

    refresh_otc_assets()

    # Si aparecen nuevos pares,
    # se intenta iniciar su stream.
    initialize_all_streams()

    results = analyze_all_markets(
        server_ts
    )

    if not results:
        return

    LAST_PROCESSED_MINUTE = (
        closed_minute
    )

    log_market_ranking(
        results
    )

    # ========================================================
    # BUSCAR TODAS LAS SEÑALES VÁLIDAS
    # ========================================================

    valid_signals = []

    for result in results:

        if not result.get(
            "valid"
        ):
            continue

        if result.get(
            "signal"
        ) not in (
            "call",
            "put",
        ):
            continue

        score = int(
            result.get(
                "score",
                0,
            )
        )

        if score < MIN_MARKET_SCORE:
            continue

        valid_signals.append(
            result
        )

    # ========================================================
    # SIN SEÑALES
    # ========================================================

    if not valid_signals:

        LAST_SIGNAL = None

        logger.info(
            "NO SIGNAL | ningún mercado "
            "alcanzó score=%s",
            MIN_MARKET_SCORE,
        )

        telegram_send(
            "🔎 MULTI-OTC\n\n"
            f"Mercados analizados: "
            f"{len(results)}\n\n"
            "🚫 SIN SEÑAL\n"
            "Ningún mercado alcanzó "
            f"{MIN_MARKET_SCORE}/100."
        )

        return

    # ========================================================
    # ORDENAR SEÑALES
    # ========================================================

    valid_signals.sort(
        key=lambda item: (
            int(
                item.get(
                    "score",
                    0,
                )
            ),
            int(
                item.get(
                    "structure",
                    {},
                ).get(
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

    logger.info(
        "🎯 SEÑALES VÁLIDAS: %s",
        len(valid_signals),
    )

    # ========================================================
    # MOSTRAR TODAS LAS SEÑALES
    # ========================================================

    for index, result in enumerate(
        valid_signals,
        start=1,
    ):

        logger.info(
            "SIGNAL #%s | %s | %s | "
            "score=%s | N=%s",
            index,
            result.get(
                "pair"
            ),
            str(
                result.get(
                    "signal"
                )
            ).upper(),
            result.get(
                "score"
            ),
            result.get(
                "minute_timestamp"
            ),
        )

    # ========================================================
    # GUARDAR LA MEJOR PARA /STATUS
    # ========================================================

    publish_best_market(
        valid_signals[0]
    )

    # ========================================================
    # EJECUTAR TODAS LAS OPERACIONES
    # ========================================================

    executed = execute_all_valid_signals(
        valid_signals,
        server_ts,
    )

    logger.info(
        "🏁 CICLO COMPLETADO | "
        "mercados=%s | "
        "señales=%s | "
        "ejecutadas=%s",
        len(results),
        len(valid_signals),
        executed,
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    global BOT_RUNNING

    logger.info(
        "======================================"
    )

    logger.info(
        "MARKET SCANNER IQ OPTION"
    )

    logger.info(
        "ESTRATEGIA: strategy.py"
    )

    logger.info(
        "MODO: MULTI-OTC"
    )

    logger.info(
        "ANÁLISIS: PARALELO"
    )

    logger.info(
        "EJECUCIÓN: TODAS LAS SEÑALES VÁLIDAS"
    )

    logger.info(
        "WORKERS: %s",
        MAX_WORKERS,
    )

    logger.info(
        "TIMEFRAME: 1 MINUTO"
    )

    logger.info(
        "AMOUNT: %s",
        AMOUNT,
    )

    logger.info(
        "EXPIRATION: %s MINUTO",
        EXPIRATION,
    )

    logger.info(
        "MIN SCORE: %s",
        MIN_MARKET_SCORE,
    )

    logger.info(
        "======================================"
    )

    required = {
        "IQ_EMAIL": IQ_EMAIL,
        "IQ_PASSWORD": IQ_PASSWORD,
        "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
        "TELEGRAM_CHAT_ID": (
            TELEGRAM_CHAT_ID
        ),
    }

    missing = [
        key
        for key, value
        in required.items()
        if not value
    ]

    if missing:

        logger.error(
            "Faltan variables: %s",
            ", ".join(missing),
        )

        return

    try:

        connect_iq()

    except Exception as exc:

        logger.exception(
            "No se pudo conectar."
        )

        telegram_send(
            "❌ ERROR IQ OPTION\n\n"
            f"{exc}"
        )

        return

    telegram_thread = (
        threading.Thread(
            target=telegram_worker,
            daemon=True,
        )
    )

    telegram_thread.start()

    BOT_RUNNING = True

    initialize_all_streams()

    telegram_send(
        "🤖 MARKET SCANNER LISTO\n\n"
        "MULTI-OTC\n\n"
        "🔎 Descubre OTC disponibles\n"
        "⚡ Analiza mercados en paralelo\n"
        "👁 Monitorea M1 en vivo\n"
        "📊 Analiza vela cerrada\n"
        "🏆 Compara todos los mercados\n"
        "🎯 Ejecuta TODAS las señales válidas\n\n"
        "La decisión de entrada sigue "
        "siendo producida por strategy.py.\n"
        f"Score mínimo: {MIN_MARKET_SCORE}/100\n"
        f"Importe: {AMOUNT}\n"
        f"Expiración: {EXPIRATION} minuto\n"
        "Entrada: N+1"
    )

    while True:

        try:

            if not BOT_RUNNING:

                time.sleep(
                    0.20
                )

                continue

            if not ensure_connection():

                time.sleep(
                    1
                )

                continue

            process_market_cycle()

            time.sleep(
                POLL_INTERVAL
            )

        except KeyboardInterrupt:

            BOT_RUNNING = False

            telegram_send(
                "🔴 SCANNER DETENIDO"
            )

            logger.info(
                "Scanner detenido."
            )

            break

        except Exception:

            logger.exception(
                "Error principal"
            )

            time.sleep(
                0.5
            )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()
