from __future__ import annotations
import logging,os,threading,time
from typing import Any,Dict,Optional
import pandas as pd,requests
from iqoptionapi.stable_api import IQ_Option
from strategy import analyze_market

def _disabled_digital_open(self,*args:Any,**kwargs:Any)->None:return None
try:IQ_Option._IQ_Option__get_digital_open=_disabled_digital_open
except Exception:pass

IQ_EMAIL=os.getenv("IQ_EMAIL");IQ_PASSWORD=os.getenv("IQ_PASSWORD")
TELEGRAM_TOKEN=os.getenv("TELEGRAM_TOKEN");TELEGRAM_CHAT_ID=os.getenv("TELEGRAM_CHAT_ID")
PAIRS=[];MARKET_REFRESH_INTERVAL=30.0;LAST_MARKET_REFRESH=0.0
TIMEFRAME=60;CANDLE_COUNT=60;AMOUNT=30;EXPIRATION=1
POLL_INTERVAL=.05;TELEGRAM_POLL_INTERVAL=1.0;TELEGRAM_HTTP_TIMEOUT=5.0
RAILWAY_HEARTBEAT_INTERVAL=15.0;LAST_HEARTBEAT=0.0
BOT_RUNNING=False;IQ:Optional[IQ_Option]=None;LAST_UPDATE_ID:Optional[int]=None
LAST_PROCESSED_MINUTE:Dict[str,int]={};LAST_LIVE_M1:Dict[str,Dict[str,Any]]={}
LAST_CLOSED_M1:Dict[str,Dict[str,Any]]={};PENDING_ENTRY:Dict[str,Dict[str,Any]]={}
LAST_TRADE_CANDLE:Dict[str,int]={};STREAMS_STARTED=False

logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s")
logger=logging.getLogger(__name__)

def telegram_send(message:str)->bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT_ID,"text":message},timeout=TELEGRAM_HTTP_TIMEOUT)
        return r.status_code==200
    except Exception as exc:logger.warning("Telegram no disponible: %s",exc);return False

def telegram_worker()->None:
    global LAST_UPDATE_ID,BOT_RUNNING
    if not TELEGRAM_TOKEN:return
    logger.info("Telegram worker iniciado. /start /stop /status disponibles.")
    while True:
        try:
            p={"timeout":1}
            if LAST_UPDATE_ID is not None:p["offset"]=LAST_UPDATE_ID+1
            r=requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",params=p,timeout=TELEGRAM_HTTP_TIMEOUT)
            if r.status_code!=200:time.sleep(TELEGRAM_POLL_INTERVAL);continue
            data=r.json()
            if not data.get("ok"):time.sleep(TELEGRAM_POLL_INTERVAL);continue
            for u in data.get("result",[]):
                LAST_UPDATE_ID=u.get("update_id");m=u.get("message",{})
                text=str(m.get("text","")).strip().lower();chat=str(m.get("chat",{}).get("id",""))
                if chat!=str(TELEGRAM_CHAT_ID):continue
                if text=="/start":
                    BOT_RUNNING=True
                    telegram_send("🟢 BOT ACTIVADO\n\nEstrategia M1 completa.\nN cerrada → análisis → CALL/PUT → N+1.\nMercado: OTC disponible para expiración 1 minuto.")
                    logger.info("BOT ACTIVADO POR TELEGRAM")
                elif text=="/stop":
                    BOT_RUNNING=False
                    telegram_send("🔴 BOT DETENIDO\n\nNo se abrirán nuevas operaciones.")
                    logger.info("BOT DETENIDO POR TELEGRAM")
                elif text=="/status":
                    telegram_send(("📊 ESTADO\n\n"+f"Estado: {'🟢 ACTIVO' if BOT_RUNNING else '🔴 DETENIDO'}\n"
                                   "Estrategia: M1 completa\nEntrada: N+1\nMercado: OTC 1M\nTipo: BINARIA\n"
                                   f"Importe: ${AMOUNT}\nOTC disponibles: {len(PAIRS)}\nPendientes: {len(PENDING_ENTRY)}"))
        except Exception as exc:logger.warning("Telegram worker: %s",exc)
        time.sleep(TELEGRAM_POLL_INTERVAL)

def get_server_timestamp()->Optional[int]:
    if IQ is None:return None
    try:
        x=IQ.get_server_timestamp();return None if x is None else int(float(x))
    except Exception as exc:logger.warning("Error timestamp servidor: %s",exc);return None

def refresh_1m_otc_pairs(force:bool=False)->list[str]:
    global PAIRS,LAST_MARKET_REFRESH,STREAMS_STARTED
    if IQ is None:return list(PAIRS)
    now=time.monotonic()
    if not force and PAIRS and now-LAST_MARKET_REFRESH<MARKET_REFRESH_INTERVAL:return list(PAIRS)
    try:
        op=IQ.get_all_open_time() or {};turbo=op.get("turbo",{}) or {};found=[]
        for pair,data in turbo.items():
            name=str(pair).upper()
            if name.endswith("-OTC") and isinstance(data,dict) and data.get("open") is True:found.append(name)
        found=sorted(set(found))
        if set(found)!=set(PAIRS):
            logger.info("OTC 1M ACTUALIZADOS | %s pares | %s",len(found),", ".join(found) if found else "ninguno")
            PAIRS=found;STREAMS_STARTED=False
        else:PAIRS=found
        LAST_MARKET_REFRESH=now;return list(PAIRS)
    except Exception as exc:logger.warning("Error descubriendo OTC 1M: %s",exc);return list(PAIRS)

def connect_iq()->bool:
    global IQ,STREAMS_STARTED
    if not IQ_EMAIL or not IQ_PASSWORD:raise ValueError("Faltan IQ_EMAIL o IQ_PASSWORD")
    logger.info("Conectando a IQ Option...")
    IQ=IQ_Option(IQ_EMAIL,IQ_PASSWORD);ok,reason=IQ.connect()
    if not ok:raise ConnectionError(f"No se pudo conectar: {reason}")
    logger.info("IQ Option conectado.");STREAMS_STARTED=False;refresh_1m_otc_pairs(True);start_realtime_streams();return True

def ensure_connection()->bool:
    global STREAMS_STARTED
    try:
        if IQ is None:return connect_iq()
        if IQ.check_connect():
            if not STREAMS_STARTED:refresh_1m_otc_pairs(True);start_realtime_streams()
            return True
        logger.warning("Conexión IQ perdida. Reconectando...")
        ok,reason=IQ.connect()
        if not ok:logger.error("Reconexión fallida: %s",reason);return False
        STREAMS_STARTED=False;refresh_1m_otc_pairs(True);start_realtime_streams();logger.info("IQ Option reconectado.");return True
    except Exception as exc:logger.error("Error conexión IQ: %s",exc);return False

def start_realtime_streams()->None:
    global STREAMS_STARTED
    if IQ is None or STREAMS_STARTED:return
    if not PAIRS:logger.warning("No hay OTC 1M disponibles para iniciar streams.");return
    n=0
    for pair in PAIRS:
        try:IQ.start_candles_stream(pair,TIMEFRAME,CANDLE_COUNT);n+=1
        except Exception as exc:logger.error("%s | error stream M1: %s",pair,exc)
    STREAMS_STARTED=n>0;logger.info("STREAMS M1 | iniciados=%s/%s",n,len(PAIRS))

def realtime_dataframe(pair:str,timeframe:int)->Optional[pd.DataFrame]:
    if IQ is None:return None
    try:
        candles=IQ.get_realtime_candles(pair,timeframe)
        if not candles:return None
        rows=[]
        for ts,c in candles.items():
            try:
                rows.append({"from":int(float(ts)),"open":float(c["open"]),"close":float(c["close"]),
                             "high":float(c.get("max",c.get("high"))),"low":float(c.get("min",c.get("low"))),
                             "volume":float(c.get("volume",0))})
            except Exception:continue
        if not rows:return None
        df=pd.DataFrame(rows);df.dropna(subset=["from","open","close","high","low"],inplace=True)
        df["from"]=df["from"].astype(int);df.sort_values("from",inplace=True);df.drop_duplicates("from",keep="last",inplace=True);df.reset_index(drop=True,inplace=True);return df
    except Exception as exc:logger.warning("%s | realtime %ss error: %s",pair,timeframe,exc);return None

def get_1m_realtime(pair:str)->Optional[pd.DataFrame]:return realtime_dataframe(pair,TIMEFRAME)
def get_intrabar_1m(pair:str)->Optional[pd.DataFrame]:return realtime_dataframe(pair,60)
def get_live_1m(df:pd.DataFrame)->Optional[pd.Series]:return None if df is None or df.empty else df.iloc[-1]
def get_closed_1m(df:pd.DataFrame,expected_timestamp:Optional[int]=None)->Optional[pd.Series]:
    if df is None or df.empty or "from" not in df.columns:return None
    if expected_timestamp is not None:
        x=df[df["from"].astype(int)==int(expected_timestamp)];return x.iloc[-1] if not x.empty else None
    return df.iloc[-2] if len(df)>=2 else None

def railway_heartbeat(force:bool=False)->None:
    global LAST_HEARTBEAT
    now=time.monotonic()
    if not force and now-LAST_HEARTBEAT<RAILWAY_HEARTBEAT_INTERVAL:return
    LAST_HEARTBEAT=now
    logger.info("HEARTBEAT | running=%s | iq=%s | streams=%s | otc=%s | pendientes=%s | server_ts=%s",
                BOT_RUNNING,IQ is not None,STREAMS_STARTED,len(PAIRS),len(PENDING_ENTRY),get_server_timestamp())

def log_pair_analysis(pair:str,result:Dict[str,Any],ts:int)->None:
    logger.info("ANALISIS | %s | N=%s | dir=%s | signal=%s | valid=%s | score=%s | stage=%s | state=%s | motivo=%s",
                pair,ts,result.get("direction"),result.get("signal"),result.get("valid"),result.get("score"),
                result.get("diagnostic_stage"),result.get("state"),result.get("reason",""))

def create_pending_signal(pair:str,result:Dict[str,Any])->None:
    signal=result.get("signal")
    if signal not in("call","put"):return
    ts=result.get("minute_timestamp")
    if ts is None:return
    ts=int(ts);n1=ts+TIMEFRAME
    if pair in PENDING_ENTRY and int(PENDING_ENTRY[pair]["minute_timestamp"])==ts:return
    PENDING_ENTRY[pair]={"signal":signal,"minute_timestamp":ts,"next_timestamp":n1,
                         "minute_open":result.get("minute_open"),"minute_close":result.get("minute_close"),
                         "reason":result.get("reason",""),"score":result.get("score",0),"created_at":time.time()}
    logger.info("SEÑAL PENDIENTE | %s | %s | score=%s | N=%s | N+1=%s",pair,signal.upper(),result.get("score"),ts,n1)

def buy_binary(pair:str,signal:str)->tuple[bool,Optional[Any],Any]:
    if IQ is None:return False,None,"IQ=None"
    try:
        x=IQ.buy(AMOUNT,pair,signal,EXPIRATION)
        if isinstance(x,tuple):
            if len(x)>=2:return bool(x[0]),x[1],x
            if len(x)==1:return bool(x[0]),None,x
        if x is True:return True,None,x
        return False,None,x
    except Exception as exc:logger.exception("%s | error buy binary: %s",pair,exc);return False,None,str(exc)

def execute_pending(pair:str)->bool:
    p=PENDING_ENTRY.get(pair)
    if p is None:return False
    st=get_server_timestamp()
    if st is None:return False
    st=int(st);n=int(p["minute_timestamp"]);n1=int(p["next_timestamp"]);cur=(st//TIMEFRAME)*TIMEFRAME
    if cur<n1:return False
    if cur>n1:
        logger.info("%s | SEÑAL CANCELADA | N+1 terminó | N=%s | N+1=%s",pair,n,n1);PENDING_ENTRY.pop(pair,None);return False
    if LAST_TRADE_CANDLE.get(pair)==n1:PENDING_ENTRY.pop(pair,None);return False
    sig=p["signal"]
    logger.info("%s | EJECUTANDO N+1 | %s | N=%s | N+1=%s | score=%s",pair,sig.upper(),n,n1,p.get("score"))
    ok,order,raw=buy_binary(pair,sig)
    if not ok:
        logger.warning("%s | BUY RECHAZADO/NO EJECUTADO | %s | N=%s | N+1=%s | %s",pair,sig.upper(),n,n1,raw);return False
    LAST_TRADE_CANDLE[pair]=n1;PENDING_ENTRY.pop(pair,None)
    telegram_send("✅ OPERACIÓN ABIERTA\n\n"+f"Par: {pair}\nDirección: {sig.upper()}\nTimestamp N: {n}\nApertura N: {p['minute_open']}\nCierre N: {p['minute_close']}\nTimestamp N+1: {n1}\n💵 Importe: ${AMOUNT}\n⏱ Expiración: 1 minuto\n🆔 ID: {order}")
    logger.info("%s | OPERACIÓN ABIERTA | %s | ID=%s | N=%s | N+1=%s",pair,sig.upper(),order,n,n1);return True

def process_pair(pair:str)->Optional[Dict[str,Any]]:
    if pair in PENDING_ENTRY:execute_pending(pair);return None
    st=get_server_timestamp()
    if st is None:logger.warning("%s | sin timestamp de servidor",pair);return None
    current=(int(st)//TIMEFRAME)*TIMEFRAME;closed=current-TIMEFRAME
    df=get_1m_realtime(pair)
    if df is None or df.empty:logger.warning("%s | SIN DATOS M1 | esperando stream",pair);return None
    live=get_live_1m(df)
    if live is not None:
        try:
            if int(float(live["from"]))==current:LAST_LIVE_M1[pair]=live.to_dict()
        except Exception:pass
    candle=get_closed_1m(df,closed)
    if candle is None:
        cache=LAST_CLOSED_M1.get(pair)
        if cache is not None:
            try:
                if int(float(cache["from"]))==closed:candle=pd.Series(cache)
            except Exception:pass
    if candle is None:
        logger.warning("%s | N CERRADA NO DISPONIBLE | esperado=%s | velas=%s",pair,closed,len(df));return None
    try:ts=int(float(candle["from"]))
    except Exception:logger.warning("%s | timestamp N inválido",pair);return None
    if ts!=closed:return None
    if LAST_PROCESSED_MINUTE.get(pair)==closed:return None
    hist=get_intrabar_1m(pair)
    if hist is not None and not hist.empty:hist=hist[hist["from"].astype(int)<closed].copy()
    result=analyze_market(pd.Series(candle),None,hist)
    result.update(minute_timestamp=closed,minute_open=float(candle["open"]),minute_close=float(candle["close"]),pair=pair)
    LAST_PROCESSED_MINUTE[pair]=closed;LAST_CLOSED_M1[pair]=pd.Series(candle).to_dict()
    log_pair_analysis(pair,result,closed);return result

def analyze_all_pairs()->None:
    if not BOT_RUNNING:railway_heartbeat();return
    refresh_1m_otc_pairs()
    if not PAIRS:logger.warning("ANALISIS | NO HAY OTC 1M DISPONIBLES");railway_heartbeat();return
    if not STREAMS_STARTED:start_realtime_streams()
    if PENDING_ENTRY:
        for pair in list(PENDING_ENTRY):execute_pending(pair)
        railway_heartbeat();return
    candidates=[];analyzed=0
    for pair in list(PAIRS):
        if not BOT_RUNNING:return
        try:
            r=process_pair(pair)
            if r is None:continue
            analyzed+=1
            if r.get("valid") is True and r.get("signal") in("call","put"):candidates.append(r)
        except Exception:logger.exception("%s | ERROR PROCESANDO PAR",pair)
    if candidates:
        best=max(candidates,key=lambda x:float(x.get("score",0)))
        logger.info("CANDIDATOS VÁLIDOS | total=%s | mejor=%s | %s | score=%s",len(candidates),best.get("pair"),str(best.get("signal")).upper(),best.get("score"))
        for x in sorted(candidates,key=lambda x:float(x.get("score",0)),reverse=True):
            logger.info("CANDIDATO | %s | %s | score=%s | %s",x.get("pair"),str(x.get("signal")).upper(),x.get("score"),x.get("reason",""))
        create_pending_signal(str(best.get("pair")),best)
    else:logger.info("CICLO COMPLETO | pares=%s | analizados_nuevos=%s | sin señal válida en este cierre",len(PAIRS),analyzed)
    railway_heartbeat()

def main()->None:
    logger.info("==========================================")
    logger.info("BOT IQ OPTION BINARIAS OTC")
    logger.info("ESTRATEGIA M1 COMPLETA -> N CERRADA -> N+1")
    logger.info("EXPIRACIÓN 1 MINUTO | OTC DINÁMICO | AMOUNT=$%s",AMOUNT)
    logger.info("==========================================")
    required={"IQ_EMAIL":IQ_EMAIL,"IQ_PASSWORD":IQ_PASSWORD,"TELEGRAM_TOKEN":TELEGRAM_TOKEN,"TELEGRAM_CHAT_ID":TELEGRAM_CHAT_ID}
    missing=[k for k,v in required.items() if not v]
    if missing:logger.error("Faltan variables: %s",", ".join(missing));return
    threading.Thread(target=telegram_worker,name="telegram-worker",daemon=True).start()
    try:connect_iq()
    except Exception as exc:
        logger.exception("No se pudo conectar a IQ Option.")
        telegram_send("❌ ERROR IQ OPTION\n\n"+f"{exc}\n\nTelegram continúa activo: usa /status o /stop.")
    railway_heartbeat(True)
    while True:
        try:
            if not BOT_RUNNING:railway_heartbeat();time.sleep(.20);continue
            if not ensure_connection():logger.warning("LOOP | IQ no disponible; reintentando...");time.sleep(1);continue
            analyze_all_pairs();time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            BOT_RUNNING=False;telegram_send("🔴 BOT DETENIDO MANUALMENTE");logger.info("Bot detenido.");break
        except Exception:logger.exception("ERROR PRINCIPAL");time.sleep(.5)

if __name__=="__main__":main()

