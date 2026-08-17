# bot.py
# ============================================================
# IQ OPTION BOT
# ============================================================
#
# REGLA PRINCIPAL:
#
#   N = vela M1 que se está formando
#   N cierra en :00
#        ↓
#   ANALIZAR N COMPLETA
#        ↓
#   Fuerza
#   Continuidad
#   Reversión
#   Indecisión
#   Debilidad
#   Doji
#   Dirección
#   Cuerpo
#   Mechas
#   Posición del cierre
#        ↓
#   DECIDIR CALL / PUT
#        ↓
#   N+1 = EJECUCIÓN
#
# IMPORTANTE:
#   - NO decide en el segundo 20.
#   - NO decide en el segundo 30.
#   - NO decide antes del cierre.
#   - NO usa datos parciales de N.
#   - NO usa datos de N+1 para decidir N+1.
#   - NO usa velas de 5 segundos.
#   - NO usa patrones de 6 o 12 velas de 5s.
#   - Si no existe una señal válida, NO OPERA.
#
# ============================================================

import os
import time
import requests

from iqoptionapi.stable_api import IQ_Option

from strategy import (
    build_n1_signal,
    format_analysis,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

PAIRS = [
    "EURUSD-OTC",
    "EURJPY-OTC",
    "EURGBP-OTC",
    "GBPUSD-OTC",
]

AMOUNT = 32
EXPIRATION = 1

TIMEFRAME = 60

EMAIL = os.getenv("IQ_EMAIL")
PASSWORD = os.getenv("IQ_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


# ============================================================
# VARIABLES DE CONTROL
# ============================================================

iq = None

# Última vela M1 cerrada procesada por cada par.
last_processed_candle = {}

# Evita ejecutar dos veces el mismo par en la misma vela N+1.
last_trade_candle = {}

# Guarda la conexión.
connected = False


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """
    Envía mensaje a Telegram si las variables están configuradas.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        url = (
            "https://api.telegram.org/bot"
            f"{TELEGRAM_TOKEN}/sendMessage"
        )

        requests.post(
            url,
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
            },
            timeout=10,
        )

    except Exception as e:
        print(f"[TELEGRAM] Error: {e}")


# ============================================================
# CONEXIÓN IQ OPTION
# ============================================================

def connect_iq():
    """
    Conecta y mantiene una instancia global de IQ Option.
    """

    global iq
    global connected

    if not EMAIL:
        print("[ERROR] Falta IQ_EMAIL.")
        return False

    if not PASSWORD:
        print("[ERROR] Falta IQ_PASSWORD.")
        return False

    try:
        print("[IQ] Conectando...")

        iq = IQ_Option(
            EMAIL,
            PASSWORD
        )

        check, reason = iq.connect()

        if not check:
            connected = False

            print(
                f"[IQ] Error de conexión: {reason}"
            )

            return False

        connected = True

        print("[IQ] Conectado correctamente.")

        try:
            iq.change_balance("PRACTICE")
            print("[IQ] Cuenta PRACTICE seleccionada.")
        except Exception as e:
            print(
                f"[IQ] No se pudo cambiar a PRACTICE: {e}"
            )

        return True

    except Exception as e:
        connected = False

        print(
            f"[IQ] Excepción conectando: {e}"
        )

        return False


# ============================================================
# COMPROBAR CONEXIÓN
# ============================================================

def ensure_connection():
    """
    Comprueba la conexión y reconecta si es necesario.
    """

    global connected

    try:
        if iq is not None and iq.check_connect():
            connected = True
            return True
    except Exception:
        pass

    connected = False

    print("[IQ] Conexión perdida. Reconectando...")

    return connect_iq()


# ============================================================
# TIEMPO DEL SERVIDOR
# ============================================================

def get_server_time():
    """
    Obtiene el tiempo del servidor IQ Option.

    Si no está disponible, usa time.time().
    """

    try:
        if iq is not None:
            server_time = iq.get_server_timestamp()

            if server_time:
                return float(server_time)

    except Exception:
        pass

    return time.time()


# ============================================================
# INICIO DE VELA M1
# ============================================================

def current_minute_start(timestamp):
    """
    Devuelve el inicio del minuto correspondiente.
    """

    return int(timestamp // 60) * 60


# ============================================================
# OBTENER VELA M1 CERRADA
# ============================================================

def get_closed_m1_candles(pair):
    """
    Obtiene las últimas velas M1 y selecciona únicamente
    las velas que ya están COMPLETAMENTE CERRADAS.

    Devuelve:

        current_closed
        previous_closed

    donde:

        current_closed  = N
        previous_closed = N-1

    La vela actual que todavía se está formando jamás
    se entrega como vela cerrada.
    """

    try:
        now = get_server_time()

        current_minute = current_minute_start(now)

        candles = iq.get_candles(
            pair,
            TIMEFRAME,
            4,
            now,
        )

        if not candles:
            print(
                f"[{pair}] API no devolvió velas M1."
            )

            return None, None

        closed = []

        for candle in candles:

            if not isinstance(candle, dict):
                continue

            candle_time = candle.get("from")

            if candle_time is None:
                continue

            candle_time = int(candle_time)

            # ------------------------------------------------
            # Solo velas cuyo inicio está antes del minuto
            # actual. La vela del minuto actual todavía está
            # abierta y NO se analiza.
            # ------------------------------------------------
            if candle_time < current_minute:
                closed.append(candle)

        if len(closed) < 2:
            print(
                f"[{pair}] Esperando 2 velas M1 cerradas..."
            )

            return None, None

        closed.sort(
            key=lambda x: int(x.get("from", 0))
        )

        current_closed = closed[-1]
        previous_closed = closed[-2]

        return (
            current_closed,
            previous_closed,
        )

    except Exception as e:

        print(
            f"[{pair}] Error obteniendo M1: {e}"
        )

        return None, None


# ============================================================
# VALIDAR QUE LA VELA REALMENTE CERRÓ
# ============================================================

def candle_is_closed(candle):
    """
    Comprueba que la vela haya terminado completamente.
    """

    if not candle:
        return False

    try:
        now = get_server_time()

        candle_from = int(
            candle.get("from")
        )

        candle_end = candle_from + TIMEFRAME

        return now >= candle_end

    except Exception:
        return False


# ============================================================
# EJECUCIÓN DE OPERACIÓN
# ============================================================

def execute_trade(pair, signal):
    """
    Ejecuta la operación para N+1.

    CALL -> call
    PUT  -> put

    EXPIRACIÓN = 1 minuto
    IMPORTE = 30
    """

    if signal not in ("CALL", "PUT"):
        return False, None

    if not ensure_connection():
        return False, None

    action = (
        "call"
        if signal == "CALL"
        else "put"
    )

    try:

        print(
            f"[{pair}] EJECUTANDO {signal} "
            f"N+1 | IMPORTE={AMOUNT} | "
            f"EXPIRACION={EXPIRATION}M"
        )

        check, order_id = iq.buy(
            AMOUNT,
            action,
            pair,
            EXPIRATION,
        )

        if check:

            print(
                f"[{pair}] OPERACIÓN EJECUTADA "
                f"ID={order_id}"
            )

            send_telegram(
                f"🎯 ENTRADA N+1\n"
                f"{pair} → {signal}\n"
                f"💰 Importe: {AMOUNT}\n"
                f"⏱ Expiración: {EXPIRATION} minuto"
            )

            return True, order_id

        print(
            f"[{pair}] ERROR AL EJECUTAR: "
            f"{order_id}"
        )

        return False, order_id

    except Exception as e:

        print(
            f"[{pair}] Excepción ejecutando: {e}"
        )

        return False, None


# ============================================================
# PROCESAR UNA VELA M1
# ============================================================

def process_closed_candle(
    pair,
    closed_candle,
    previous_candle,
):
    """
    Procesa una única vela M1 ya cerrada.

    AQUÍ ESTÁ LA REGLA CRÍTICA:

        N CIERRA
           ↓
        ANALIZAR N
           ↓
        SEÑAL PARA N+1
           ↓
        EJECUTAR N+1

    Nunca procesa una vela antes de cerrar.
    """

    if not candle_is_closed(closed_candle):

        print(
            f"[{pair}] Vela todavía no cerrada."
        )

        return

    candle_id = int(
        closed_candle.get("from")
    )

    # --------------------------------------------------------
    # Evitar analizar nuevamente la misma vela.
    # --------------------------------------------------------
    if last_processed_candle.get(pair) == candle_id:

        return

    # --------------------------------------------------------
    # MARCAR COMO PROCESADA ANTES DEL ANÁLISIS.
    # --------------------------------------------------------
    last_processed_candle[pair] = candle_id

    print()
    print("=" * 60)
    print(
        f"[{pair}] VELA M1 CERRADA"
    )
    print(
        f"[{pair}] N = {candle_id}"
    )
    print(
        f"[{pair}] AHORA SE ANALIZA N "
        f"PARA DECIDIR N+1"
    )
    print("=" * 60)

    # ========================================================
    # ANÁLISIS
    # ========================================================

    try:

        result = build_n1_signal(
            closed_candle,
            previous_candle,
        )

    except Exception as e:

        print(
            f"[{pair}] ERROR EN STRATEGY: {e}"
        )

        return

    # ========================================================
    # MOSTRAR TODAS LAS CONFIRMACIONES
    # ========================================================

    print(
        format_analysis(result)
    )

    signal = result.get(
        "signal_n1"
    )

    # ========================================================
    # SIN SEÑAL = NO OPERAR
    # ========================================================

    if signal not in ("CALL", "PUT"):

        print(
            f"[{pair}] ⚪ SIN SEÑAL "
            f"VALIDA PARA N+1"
        )

        send_telegram(
            f"⚪ {pair}\n"
            f"Sin señal válida para N+1.\n"
            f"No se ejecuta operación."
        )

        return

    # ========================================================
    # IDENTIFICADOR DE N+1
    # ========================================================

    next_candle_id = candle_id + TIMEFRAME

    # --------------------------------------------------------
    # Evitar doble operación sobre la misma N+1.
    # --------------------------------------------------------
    if last_trade_candle.get(pair) == next_candle_id:

        print(
            f"[{pair}] N+1 ya fue operada."
        )

        return

    # ========================================================
    # SEÑAL CONFIRMADA
    # ========================================================

    print()
    print("=" * 60)
    print(
        f"🎯 SEÑAL CONFIRMADA PARA N+1"
    )
    print(
        f"{pair} → {signal}"
    )
    print(
        f"N cerrada     : {candle_id}"
    )
    print(
        f"N+1 apertura  : {next_candle_id}"
    )
    print("=" * 60)

    send_telegram(
        f"🎯 SEÑAL CONFIRMADA N+1\n"
        f"{pair} → {signal}\n"
        f"N cerrada correctamente."
    )

    # ========================================================
    # ESPERAR LA APERTURA EXACTA DE N+1
    # ========================================================
    #
    # La decisión ya está tomada.
    #
    # No volvemos a analizar el precio.
    # No cambiamos CALL por PUT.
    # No miramos la vela N+1.
    #
    # Solo esperamos hasta el comienzo de N+1.
    # ========================================================

    wait_until = next_candle_id

    print(
        f"[{pair}] Esperando apertura de N+1..."
    )

    while True:

        now = get_server_time()

        remaining = wait_until - now

        if remaining <= 0:
            break

        # ----------------------------------------------------
        # Espera corta para intentar ejecutar lo más cerca
        # posible de la apertura.
        # ----------------------------------------------------
        if remaining > 0.20:
            time.sleep(
                min(
                    remaining - 0.10,
                    0.10,
                )
            )
        else:
            time.sleep(0.01)

    # ========================================================
    # APERTURA N+1
    # ========================================================

    print(
        f"[{pair}] 🚀 APERTURA N+1"
    )

    print(
        f"[{pair}] Ejecutando "
        f"{signal}..."
    )

    success, order_id = execute_trade(
        pair,
        signal,
    )

    if success:

        last_trade_candle[pair] = (
            next_candle_id
        )

        print(
            f"[{pair}] ✅ OPERACIÓN "
            f"ENVIADA EN N+1"
        )

    else:

        print(
            f"[{pair}] ❌ NO SE PUDO "
            f"EJECUTAR LA OPERACIÓN"
        )


# ============================================================
# LOOP PRINCIPAL
# ============================================================

def main():

    print()
    print("=" * 60)
    print("        IQ OPTION M1 SNIPER BOT")
    print("=" * 60)
    print()
    print("Pares OTC:")
    print(" - EURUSD-OTC")
    print(" - EURJPY-OTC")
    print(" - EURGBP-OTC")
    print(" - GBPUSD-OTC")
    print()
    print("Importe     :", AMOUNT)
    print("Expiración  :", EXPIRATION, "minuto")
    print("Timeframe   :", "M1")
    print()
    print(
        "REGLA: ANALIZAR SOLO AL CIERRE DE M1"
    )
    print(
        "ENTRADA: APERTURA DE N+1"
    )
    print("=" * 60)
    print()

    # ========================================================
    # CONECTAR
    # ========================================================

    while not connect_iq():

        print(
            "[IQ] Reintentando conexión "
            "en 5 segundos..."
        )

        time.sleep(5)

    # ========================================================
    # LOOP
    # ========================================================

    while True:

        try:

            if not ensure_connection():

                time.sleep(2)
                continue

            # ------------------------------------------------
            # Procesar todos los pares.
            # ------------------------------------------------

            for pair in PAIRS:

                try:

                    current_closed, previous_closed = (
                        get_closed_m1_candles(pair)
                    )

                    if (
                        current_closed is None
                        or previous_closed is None
                    ):
                        continue

                    process_closed_candle(
                        pair,
                        current_closed,
                        previous_closed,
                    )

                except Exception as e:

                    print(
                        f"[{pair}] ERROR "
                        f"PROCESANDO PAR: {e}"
                    )

            # ------------------------------------------------
            # Pequeña espera para no saturar API.
            # ------------------------------------------------

            time.sleep(0.15)

        except KeyboardInterrupt:

            print()
            print(
                "[BOT] Detenido manualmente."
            )

            break

        except Exception as e:

            print(
                f"[BOT] Error general: {e}"
            )

            time.sleep(2)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
