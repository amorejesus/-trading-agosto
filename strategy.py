from __future__ import annotations

from typing import Any, Dict, Optional
import pandas as pd

TREND_LOOKBACK=15
STRUCTURE_LOOKBACK=20
CONTINUITY_LOOKBACK=6
EXHAUSTION_LOOKBACK=8
SR_LOOKBACK=20
ATR_PERIOD=14
IMPULSE_LOOKBACK=8
MAX_IMPULSE_AGE=4
MIN_IMPULSE_BODY_RATIO=0.45
MAX_IMPULSE_TOTAL_ATR=3.50
MIN_RECENT_STRUCTURE_SCORE=5
MAX_CONSECUTIVE_DIRECTION_CANDLES=5
BREAK_LOOKBACK=5
DOJI_BODY_RATIO=0.10
INDECISION_BODY_RATIO=0.25
WEAKNESS_BODY_RATIO=0.35
MIN_CONTINUITY_BODY_RATIO=0.40
STRONG_BODY_RATIO=0.55
FORCE_BODY_RATIO=0.65
MAX_COUNTER_WICK_RATIO=0.45
MAX_CONFIRMATION_RANGE_ATR=1.60
MAX_CONFIRMATION_BODY_ATR=1.20
SR_TOLERANCE_ATR=0.35
MAX_SCORE=100
MIN_STRUCTURE_SCORE=8
MIN_CONTINUITY_SCORE=5
MIN_FINAL_SCORE=82

def _to_float(value: Any)->Optional[float]:
    try:return float(value)
    except (TypeError,ValueError):return None

def _get_ohlc(candle:pd.Series)->Optional[tuple[float,float,float,float]]:
    if candle is None:return None
    o=_to_float(candle.get("open")); c=_to_float(candle.get("close"))
    h=_to_float(candle.get("high",candle.get("max"))); l=_to_float(candle.get("low",candle.get("min")))
    if None in(o,c,h,l) or h<l:return None
    return o,h,l,c

def safe_dataframe(df:Optional[pd.DataFrame])->pd.DataFrame:
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return pd.DataFrame()
    required={"open","close","high","low"}
    if not required.issubset(df.columns):return pd.DataFrame()
    r=df.copy()
    for x in required:r[x]=pd.to_numeric(r[x],errors="coerce")
    r.dropna(subset=list(required),inplace=True)
    if "from" in r.columns:
        r["from"]=pd.to_numeric(r["from"],errors="coerce"); r.dropna(subset=["from"],inplace=True)
        r["from"]=r["from"].astype("int64"); r.sort_values("from",inplace=True)
    r.reset_index(drop=True,inplace=True); return r

def calculate_atr(df:pd.DataFrame,period:int=ATR_PERIOD)->float:
    df=safe_dataframe(df)
    if len(df)<2:return 0.0
    pc=df["close"].shift(1)
    tr=pd.concat([df["high"]-df["low"],(df["high"]-pc).abs(),(df["low"]-pc).abs()],axis=1).max(axis=1)
    a=tr.rolling(window=min(period,len(df)),min_periods=2).mean().iloc[-1]
    return 0.0 if pd.isna(a) else float(a)

def get_candle_data(candle:pd.Series)->Optional[Dict[str,float]]:
    x=_get_ohlc(candle)
    if x is None:return None
    o,h,l,c=x; rg=h-l; body=abs(c-o)
    uw=max(0.0,h-max(o,c)); lw=max(0.0,min(o,c)-l)
    if rg<=0:
        return {"open":o,"close":c,"high":h,"low":l,"range":0.0,"body":0.0,"upper_wick":0.0,"lower_wick":0.0,"body_ratio":0.0,"upper_wick_ratio":0.0,"lower_wick_ratio":0.0,"close_position":0.5}
    return {"open":o,"close":c,"high":h,"low":l,"range":rg,"body":body,"upper_wick":uw,"lower_wick":lw,"body_ratio":body/rg,"upper_wick_ratio":uw/rg,"lower_wick_ratio":lw/rg,"close_position":(c-l)/rg}

def analyze_structure(df:pd.DataFrame)->Dict[str,Any]:
    r={"direction":"NEUTRAL","score":0,"bullish_score":0,"bearish_score":0,"reason":"estructura insuficiente"}
    df=safe_dataframe(df)
    if len(df)<6:return r
    w=df.tail(TREND_LOOKBACK).reset_index(drop=True); h=w.high.tolist(); l=w.low.tolist(); c=w.close.tolist()
    hh=sum(h[i]>h[i-1] for i in range(1,len(h))); hl=sum(l[i]>l[i-1] for i in range(1,len(l)))
    lh=sum(h[i]<h[i-1] for i in range(1,len(h))); ll=sum(l[i]<l[i-1] for i in range(1,len(l)))
    bc=sum(c[i]>c[i-1] for i in range(1,len(c))); sc=sum(c[i]<c[i-1] for i in range(1,len(c)))
    bull=(3 if hh>=8 else 0)+(3 if hl>=8 else 0)+(2 if bc>=8 else 0)+(2 if c[-1]>c[0] else 0)
    bear=(3 if lh>=8 else 0)+(3 if ll>=8 else 0)+(2 if sc>=8 else 0)+(2 if c[-1]<c[0] else 0)
    r["bullish_score"],r["bearish_score"]=bull,bear
    if bull>=MIN_STRUCTURE_SCORE and bull>bear:r.update(direction="BULLISH",score=bull,reason="estructura alcista")
    elif bear>=MIN_STRUCTURE_SCORE and bear>bull:r.update(direction="BEARISH",score=bear,reason="estructura bajista")
    else:r.update(score=max(bull,bear),reason="estructura lateral o mezclada")
    return r

def recent_structure_quality(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"valid":False,"score":0,"reason":"estructura reciente insuficiente"}; df=safe_dataframe(df)
    if len(df)<BREAK_LOOKBACK+2:return r
    w=df.tail(BREAK_LOOKBACK).reset_index(drop=True); h=w.high.tolist(); l=w.low.tolist(); c=w.close.tolist(); s=0
    if direction=="BULLISH":
        if sum(h[i]>h[i-1] for i in range(1,len(h)))>=2:s+=3
        if sum(l[i]>l[i-1] for i in range(1,len(l)))>=2:s+=3
        if c[-1]>c[-2]:s+=2
    elif direction=="BEARISH":
        if sum(h[i]<h[i-1] for i in range(1,len(h)))>=2:s+=3
        if sum(l[i]<l[i-1] for i in range(1,len(l)))>=2:s+=3
        if c[-1]<c[-2]:s+=2
    r["score"]=s;r["valid"]=s>=MIN_RECENT_STRUCTURE_SCORE;r["reason"]=f"estructura reciente score={s}";return r

def analyze_impulse_start(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"valid":False,"score":0,"age":99,"extended":False,"reason":"sin impulso reciente"}; df=safe_dataframe(df)
    if len(df)<IMPULSE_LOOKBACK+2:return r
    w=df.tail(IMPULSE_LOOKBACK).reset_index(drop=True); atr=calculate_atr(df.iloc[:-1])
    if atr<=0:return r
    cs=[get_candle_data(w.iloc[i]) for i in range(len(w))]; cs=[x for x in cs if x is not None]
    if len(cs)<IMPULSE_LOOKBACK:return r
    start=None
    for i in range(1,len(cs)):
        x,p=cs[i],cs[i-1]; bull=x["close"]>x["open"]; bear=x["close"]<x["open"]; strong=x["body_ratio"]>=MIN_IMPULSE_BODY_RATIO
        if direction=="BULLISH" and bull and strong and x["close"]>p["high"]:start=i
        elif direction=="BEARISH" and bear and strong and x["close"]<p["low"]:start=i
    if start is None:r["reason"]="no existe ruptura reciente de impulso";return r
    age=len(cs)-1-start;r["age"]=age
    if age>MAX_IMPULSE_AGE:r["reason"]=f"impulso demasiado antiguo age={age}";return r
    ext=(max(x["high"] for x in cs[start:])-min(x["low"] for x in cs[start:]))/atr
    if ext>MAX_IMPULSE_TOTAL_ATR:r.update(extended=True,reason=f"impulso demasiado extendido {ext:.2f} ATR");return r
    recent=cs[start:]; directional=sum((x["close"]>x["open"]) if direction=="BULLISH" else (x["close"]<x["open"]) for x in recent); weak=sum(x["body_ratio"]<MIN_CONTINUITY_BODY_RATIO for x in recent)
    score=4+(5 if age<=1 else 4 if age<=2 else 2 if age<=3 else 0)
    if directional>=2:score+=3
    if weak<=1:score+=2
    if ext<=2.0:score+=3
    r["score"]=score;r["valid"]=score>=8 and age<=MAX_IMPULSE_AGE and not r["extended"]
    r["reason"]=f"inicio de impulso válido age={age} score={score}" if r["valid"] else f"impulso débil o avanzado age={age} score={score}"
    return r

def detect_late_trend(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"late":False,"penalty":0,"reason":"sin tendencia avanzada"};df=safe_dataframe(df)
    if len(df)<MAX_CONSECUTIVE_DIRECTION_CANDLES:return r
    n=0
    for _,x in df.tail(MAX_CONSECUTIVE_DIRECTION_CANDLES).iterrows():
        if direction=="BULLISH" and x.close>x.open:n+=1
        elif direction=="BEARISH" and x.close<x.open:n+=1
        else:break
    if n>=MAX_CONSECUTIVE_DIRECTION_CANDLES:r.update(late=True,penalty=12,reason=f"{n} velas consecutivas en la misma dirección")
    return r

def check_continuity(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"valid":False,"score":0,"reason":"sin continuidad"};df=safe_dataframe(df)
    if len(df)<CONTINUITY_LOOKBACK:r["reason"]="pocas velas para continuidad";return r
    w=df.tail(CONTINUITY_LOOKBACK).reset_index(drop=True);h=w.high.tolist();l=w.low.tolist();c=w.close.tolist();s=0
    if direction=="BULLISH":
        if sum(h[i]>=h[i-1] for i in range(1,len(h)))>=3:s+=3
        if sum(l[i]>=l[i-1] for i in range(1,len(l)))>=3:s+=3
        if c[-1]>=c[-2]:s+=2
    elif direction=="BEARISH":
        if sum(h[i]<=h[i-1] for i in range(1,len(h)))>=3:s+=3
        if sum(l[i]<=l[i-1] for i in range(1,len(l)))>=3:s+=3
        if c[-1]<=c[-2]:s+=2
    r["score"]=s;r["valid"]=s>=MIN_CONTINUITY_SCORE;r["reason"]=f"continuidad {'alcista' if direction=='BULLISH' else 'bajista'} score={s}";return r

def detect_end_of_trend(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"exhausted":False,"penalty":0,"reason":""};df=safe_dataframe(df)
    if len(df)<3:return r
    x,p=get_candle_data(df.iloc[-1]),get_candle_data(df.iloc[-2])
    if x is None or p is None:return r
    pen=0;reasons=[]
    if direction=="BULLISH":
        if x["upper_wick_ratio"]>=.50:pen+=8;reasons.append("rechazo superior")
        if x["body_ratio"]<.20:pen+=6;reasons.append("cuerpo muy débil")
        if x["close"]<p["low"]:pen+=10;reasons.append("pérdida de estructura")
    elif direction=="BEARISH":
        if x["lower_wick_ratio"]>=.50:pen+=8;reasons.append("rechazo inferior")
        if x["body_ratio"]<.20:pen+=6;reasons.append("cuerpo muy débil")
        if x["close"]>p["high"]:pen+=10;reasons.append("pérdida de estructura")
    r["penalty"]=pen;r["exhausted"]=pen>=10;r["reason"]=", ".join(reasons) if reasons else "sin agotamiento evidente";return r

def check_support_resistance(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"blocked":False,"penalty":0,"reason":"","support":None,"resistance":None};df=safe_dataframe(df)
    if len(df)<5:return r
    h=df.iloc[:-1].tail(SR_LOOKBACK);price=float(df.iloc[-1].close);atr=calculate_atr(h)
    if h.empty or atr<=0:return r
    support=float(h.low.min());resistance=float(h.high.max());r["support"]=support;r["resistance"]=resistance;t=atr*SR_TOLERANCE_ATR
    if direction=="BULLISH" and resistance-price<=t:r.update(blocked=True,penalty=12,reason="CALL cerca de resistencia")
    elif direction=="BEARISH" and price-support<=t:r.update(blocked=True,penalty=12,reason="PUT cerca de soporte")
    if not r["reason"]:r["reason"]="sin bloqueo S/R"
    return r

def confirmation_score(df:pd.DataFrame,direction:str)->Dict[str,Any]:
    r={"score":0,"valid":False,"reason":"","range_atr":0.0,"body_atr":0.0};df=safe_dataframe(df)
    if len(df)<2:r["reason"]="pocas velas para confirmación";return r
    x=get_candle_data(df.iloc[-1])
    if x is None:r["reason"]="vela inválida";return r
    atr=calculate_atr(df.iloc[:-1]);atr=atr if atr>0 else x["range"]
    if atr<=0:r["reason"]="ATR inválido";return r
    r["range_atr"]=x["range"]/atr;r["body_atr"]=x["body"]/atr;s=0;reasons=[]
    if direction=="BULLISH":
        if x["close"]>x["open"]:s+=5
        if x["body_ratio"]>=MIN_CONTINUITY_BODY_RATIO:s+=5
        if x["close_position"]>=.65:s+=4
        if x["upper_wick_ratio"]<=MAX_COUNTER_WICK_RATIO:s+=3
    elif direction=="BEARISH":
        if x["close"]<x["open"]:s+=5
        if x["body_ratio"]>=MIN_CONTINUITY_BODY_RATIO:s+=5
        if x["close_position"]<=.35:s+=4
        if x["lower_wick_ratio"]<=MAX_COUNTER_WICK_RATIO:s+=3
    if r["range_atr"]>MAX_CONFIRMATION_RANGE_ATR:reasons.append("movimiento demasiado extendido");s-=8
    if r["body_atr"]>MAX_CONFIRMATION_BODY_ATR:reasons.append("cuerpo demasiado extendido");s-=6
    if x["body_ratio"]<=INDECISION_BODY_RATIO:reasons.append("vela indecisa");s-=8
    r["score"]=max(0,s);r["valid"]=r["score"]>=12 and not reasons;r["reason"]=", ".join(reasons) if reasons else f"confirmación score={r['score']}";return r

def analyze_live_candle(candle_1m:pd.Series)->Dict[str,Any]:
    r={"direction":"NEUTRAL","state":"INDEFINITION","score":0};x=get_candle_data(candle_1m)
    if x is None:return r
    r.update(x);d="BULLISH" if x["close"]>x["open"] else "BEARISH" if x["close"]<x["open"] else "NEUTRAL";r["direction"]=d;s=0
    if d=="BULLISH":
        if x["body_ratio"]>=.40:s+=5
        if x["close_position"]>=.65:s+=5
        if x["upper_wick_ratio"]<=.30:s+=3
    elif d=="BEARISH":
        if x["body_ratio"]>=.40:s+=5
        if x["close_position"]<=.35:s+=5
        if x["lower_wick_ratio"]<=.30:s+=3
    r["state"]="DOJI" if x["body_ratio"]<=DOJI_BODY_RATIO else "INDECISION" if x["body_ratio"]<=INDECISION_BODY_RATIO else "LIVE_CONTINUITY" if s>=10 else "MOVEMENT";r["score"]=s;return r

def analyze_market(candle_1m:Optional[pd.Series]=None,candles_5s=None,previous_m1:Optional[pd.DataFrame]=None)->Dict[str,Any]:
    r={"signal":None,"valid":False,"score":0,"direction":"NEUTRAL","state":"NO_SIGNAL","reason":"sin análisis","minute_timestamp":None,"minute_open":None,"minute_close":None,"structure":{},"recent_structure":{},"impulse":{},"late_trend":{},"continuity":{},"confirmation":{},"exhaustion":{},"support_resistance":{},"diagnostic_stage":"START"}
    if candle_1m is None:r.update(reason="vela M1 no disponible",diagnostic_stage="NO_CANDLE");return r
    cur=get_candle_data(candle_1m)
    if cur is None:r.update(reason="OHLC inválido",diagnostic_stage="INVALID_OHLC");return r
    if "from" in candle_1m.index:
        try:r["minute_timestamp"]=int(float(candle_1m["from"]))
        except Exception:pass
    r["minute_open"],r["minute_close"]=cur["open"],cur["close"]
    h=safe_dataframe(previous_m1)
    if h.empty:h=pd.DataFrame([dict(candle_1m)])
    if "from" not in h.columns or r["minute_timestamp"] is None or r["minute_timestamp"] not in h["from"].values:
        h=pd.concat([h,pd.DataFrame([dict(candle_1m)])],ignore_index=True)
    h=safe_dataframe(h)
    if len(h)<6:r.update(reason=f"historial insuficiente ({len(h)}/6)",diagnostic_stage="INSUFFICIENT_HISTORY");return r
    st=analyze_structure(h.iloc[:-1]);r["structure"]=st;r["direction"]=st["direction"]
    if st["direction"]=="NEUTRAL":r.update(reason="mercado sin estructura clara",state="RANGE",diagnostic_stage="STRUCTURE");return r
    rs=recent_structure_quality(h.iloc[:-1],st["direction"]);r["recent_structure"]=rs
    if not rs["valid"]:r.update(reason="estructura reciente débil",state="WEAK_RECENT_STRUCTURE",diagnostic_stage="RECENT_STRUCTURE");return r
    imp=analyze_impulse_start(h.iloc[:-1],st["direction"]);r["impulse"]=imp
    if not imp["valid"]:r.update(reason=imp["reason"],state="NO_EARLY_IMPULSE",diagnostic_stage="IMPULSE");return r
    late=detect_late_trend(h.iloc[:-1],st["direction"]);r["late_trend"]=late
    if late["late"]:r.update(reason=late["reason"],state="LATE_TREND",diagnostic_stage="LATE_TREND");return r
    cont=check_continuity(h.iloc[:-1],st["direction"]);conf=confirmation_score(h,st["direction"]);ex=detect_end_of_trend(h,st["direction"]);sr=check_support_resistance(h,st["direction"])
    r["continuity"],r["confirmation"],r["exhaustion"],r["support_resistance"]=cont,conf,ex,sr
    score=max(0,min(MAX_SCORE,min(30,st["score"]*3)+min(25,cont["score"]*3)+min(30,conf["score"]*2)-ex["penalty"]-sr["penalty"]));r["score"]=score
    if not cont["valid"]:r.update(reason="sin continuidad suficiente",state="NO_CONTINUITY",diagnostic_stage="CONTINUITY");return r
    if ex["exhausted"]:r.update(reason=f"tendencia agotada: {ex['reason']}",state="EXHAUSTION",diagnostic_stage="EXHAUSTION");return r
    if sr["blocked"]:r.update(reason=sr["reason"],state="SUPPORT_RESISTANCE",diagnostic_stage="SUPPORT_RESISTANCE");return r
    if not conf["valid"]:r.update(reason=f"confirmación débil: {conf['reason']}",state="WEAK_CONFIRMATION",diagnostic_stage="CONFIRMATION");return r
    if score<MIN_FINAL_SCORE:r.update(reason=f"calidad insuficiente score={score}",state="LOW_SCORE",diagnostic_stage="FINAL_SCORE");return r
    r["signal"]="call" if st["direction"]=="BULLISH" else "put";r["valid"]=True;r["state"]="BULLISH_CONTINUITY" if r["signal"]=="call" else "BEARISH_CONTINUITY";r["reason"]=f"{'CALL' if r['signal']=='call' else 'PUT'} continuidad {'alcista' if r['signal']=='call' else 'bajista'} e inicio de impulso score={score}";r["diagnostic_stage"]="SIGNAL";return r

def analyze_minute(candle_1m,candles_5s=None,previous_m1=None):return analyze_market(candle_1m,candles_5s,previous_m1)
def build_n1_signal(candle_1m,candles_5s=None,previous_m1=None):return analyze_market(candle_1m,candles_5s,previous_m1)
def get_signal(candle_1m,candles_5s=None,previous_m1=None):return analyze_market(candle_1m,candles_5s,previous_m1).get("signal")
def signal(candle_1m,candles_5s=None,previous_m1=None):return get_signal(candle_1m,candles_5s,previous_m1)
def get_m1_direction(candle_1m=None):
    if candle_1m is None:return None
    try:
        if hasattr(candle_1m,"iloc") and hasattr(candle_1m,"columns"):
            if len(candle_1m)==0:return None
            candle_1m=candle_1m.iloc[-1]
        o=float(candle_1m.get("open"));c=float(candle_1m.get("close"))
    except Exception:return None
    return "BULLISH" if c>o else "BEARISH" if c<o else "NEUTRAL"
def check_pattern(candles_5s=None):return None

if __name__=="__main__":
    print("strategy.py cargado correctamente.")
    print("Estrategia: MULTI MARKET CONTINUITY | M1 -> N cerrada -> N+1")
