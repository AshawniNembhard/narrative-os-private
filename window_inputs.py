"""Narrative OS v0.9: dynamic, catalogue-validated inputs for four-window forecasts.

Only on-demand, user-uploaded market snapshots are accepted.  Missing and stale
market data are never silently represented as fresh observations.  Selection of
research inputs is distinct from immutable prediction and price-outcome auditing.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

UTC=timezone.utc
FOCUS='OANDA:XAUUSD'
INTRADAY=('5m','15m','1m','30m','1h','4h')
ALLOWED=set(INTRADAY)|{'1D'}
MAX_REQUESTS=7


def _string(v,n=280):
    return str(v or '').strip()[:n] if isinstance(v,str) else ''


def fallback(focus=FOCUS):
    return {'source':'default-context','reason':'No active, matching Research Studio basket. Create a research cycle or ask AI to select market inputs.',
            'source_plan_id':None,'requests':[
                {'key':'focus','symbol':focus,'name':'Gold spot','interval':'1h','priority':'required','reason':'Forecast outcome and spot-price context'},
                {'key':'dxy','symbol':'TVC:DXY','name':'US dollar index','interval':'1h','priority':'required','reason':'USD translation and funding context'},
                {'key':'futures','symbol':'COMEX:GC1!','name':'Gold futures','interval':'1h','priority':'optional','reason':'Spot–futures comparison; roll dates matter'},
                {'key':'real','symbol':'FRED:DFII10','name':'US 10-year real yield','interval':'1D','priority':'context','reason':'Daily macro background only; not an intraday yield measurement'}]}


def from_studio(plan, catalog, focus=FOCUS):
    if not plan or plan.get('focus')!=focus or not isinstance(plan.get('requests'),list):return fallback(focus)
    allowed={(v[0],k) for k,v in catalog.items()}
    req=[];used=set()
    for item in plan['requests']:
        if not isinstance(item,dict):continue
        symbol=_string(item.get('symbol'),55)
        key=_string(item.get('key'),35)
        iv=_string(item.get('interval'),5)
        if (symbol,key) not in allowed and not (symbol==focus and key=='focus'):continue
        if (symbol,iv) in used or iv not in ALLOWED:continue
        priority=item.get('priority') if item.get('priority') in ('required','optional','context') else 'optional'
        req.append({'key':key,'symbol':symbol,'name':_string(item.get('name'),90),
                    'interval':iv,'priority':priority,'reason':_string(item.get('reason'),260)})
        used.add((symbol,iv))
        if len(req)>=MAX_REQUESTS:break
    if not req or req[0]['symbol']!=focus:return fallback(focus)
    if sum(r['priority']=='required' for r in req)<2:return fallback(focus)
    return {'source':'research-studio','reason':_string(plan.get('why_these_tickers'),600) or 'AI-selected Research Studio ticker basket',
            'source_plan_id':plan.get('id'),'requests':req}


def from_ai(answer, catalog, source_plan_id=None, focus=FOCUS):
    """Validate all AI-selected keys and intervals. Reject freeform tickers entirely."""
    if not isinstance(answer,dict) or not isinstance(answer.get('requests'),list):
        raise ValueError('AI did not return a request list')
    selected=answer['requests']
    focal_interval=answer.get('focus_interval')
    if focal_interval not in INTRADAY:
        focal_interval=next((x.get('interval') for x in selected if isinstance(x,dict)
              and x.get('priority')=='required' and x.get('key') not in ('real','tips5','breakeven')
              and x.get('interval') in INTRADAY),'1h')
    seen={focus};out=[{'key':'focus','symbol':focus,'name':'Gold spot','interval':focal_interval,
        'priority':'required','reason':'Target asset and opening/closing-price context'}]
    for candidate in selected:
        if not isinstance(candidate,dict):continue
        k=_string(candidate.get('key'),40)
        if k not in catalog:continue
        symbol,name,default_reason=catalog[k]
        if symbol in seen:continue
        iv=_string(candidate.get('interval'),5)
        if k in ('real','tips5','breakeven'):iv='1D'
        elif iv not in ALLOWED:iv='1h'
        priority=candidate.get('priority') if candidate.get('priority') in ('required','optional','context') else 'optional'
        if priority=='required' and iv!=focal_interval:
            priority='context'  # No mixed-timeframe paired returns. Other resolutions remain contextual.
        out.append({'key':k,'symbol':symbol,'name':name,'interval':iv,'priority':priority,
                    'reason':_string(candidate.get('reason'),260) or default_reason})
        seen.add(symbol)
        if len(out)>=MAX_REQUESTS:break
    if len(out)<2 or sum(x['priority']=='required' for x in out)<2:
        raise ValueError('AI must request at least one valid same-timeframe required corroborating instrument')
    return {'source':'window-ai-refreshed','source_plan_id':source_plan_id,
            'reason':_string(answer.get('reason'),650) or 'AI-nominated ticker basket, not verified market evidence',
            'requests':out,'additional_evidence':_string(answer.get('additional_evidence'),500)}


def status_for(requests,charts,now=None):
    now=now or datetime.now(UTC)
    catalog={(c.get('symbol'),c.get('interval')):c for c in charts}
    result=[]
    for r in requests:
        view=catalog.get((r['symbol'],r['interval']))
        info={**r,'status':'missing','last_time':None,'bars':None,'uploaded_at':None,'snapshot':None}
        if view:
            raw=view.get('last_time')
            try:
                last=datetime.fromisoformat(str(raw).replace('Z','+00:00'))
                if last.tzinfo is None:raise ValueError('missing timezone')
                age=now-last.astimezone(UTC)
                sufficient=int(view.get('bars') or 0)>=20
                # Comparisons need recent candles, and 1D macro observations can have a release lag.
                stale=age>timedelta(days=14 if r['interval']=='1D' else 3) or age<timedelta(hours=-1)
                info['status']='insufficient' if not sufficient else 'stale' if stale else 'ready'
            except (TypeError,ValueError,OverflowError):info['status']='invalid-time'
            info.update({'last_time':raw,'bars':view.get('bars'),'uploaded_at':view.get('uploaded_at'),
                         'snapshot':{k:view.get(k) for k in ('symbol','interval','last_time','uploaded_at','bars',
                           'latest_close','one_bar_percent','twenty_bar_percent','cautions')}})
        result.append(info)
    needed=[r for r in result if r['priority']=='required']
    counts={k:sum(r['status']==k for r in result) for k in ('ready','missing','stale','insufficient','invalid-time')}
    return {'requests':result,'summary':{**counts,'required_total':len(needed),
      'required_ready':sum(r['status']=='ready' for r in needed),
      'required_not_ready':sum(r['status']!='ready' for r in needed)},
      'data_policy':'Exact ticker/timeframe match; >=20 bars; intraday last bar <=3 days old, daily <=14 days. Status describes uploaded data, not verification.'}