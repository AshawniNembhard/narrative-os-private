"""Narrative OS v0.8: fixed-window forecast lock and deterministic outcome adjudication.

The AI produces a thesis; only this module computes the observed outcome. Market
snapshots are explicitly labelled as user CSVs until an independent licensed feed
is integrated. No retrofit scoring of historical, un-locked predictions.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
import json
import math

UTC=timezone.utc
LONDON=ZoneInfo('Europe/London')
WINDOWS=((1,'01:00','03:00','Asia'),(2,'04:00','06:00','Asia transition'),
         (3,'07:00','09:00','London'),(4,'13:00','15:00','US session'))
DIRECTIONS={'Bullish','Bearish','Flat','Abstain'}
BAR_SECONDS={'1m':60,'3m':180,'5m':300,'10m':600,'15m':900,'30m':1800,'1h':3600}
PREFERRED=('5m','15m','1m','3m','10m','30m','1h')
NOISE_BPS=10.0  # predeclared fixed +/-0.10% neutral band for every 2-hour window
DELAY=timedelta(minutes=5)


def iso(t):
    return t.astimezone(UTC).isoformat().replace('+00:00','Z')


def parse_instant(t):
    if isinstance(t,datetime):
        if t.tzinfo is None:raise ValueError('Timezone-aware datetime required')
        return t.astimezone(UTC)
    d=datetime.fromisoformat(str(t).replace('Z','+00:00'))
    if not d.tzinfo:raise ValueError('Timestamp must include a timezone')
    return d.astimezone(UTC)


def london_today(now=None):
    return (now or datetime.now(UTC)).astimezone(LONDON).date()


def day_slots(day):
    day=date.fromisoformat(day) if isinstance(day,str) else day
    if day.weekday()>=5:raise ValueError('Choose a Monday–Friday trading date.')
    return [{'id':n,'label':label,'opens_at':iso(datetime.combine(day,time.fromisoformat(start),LONDON)),
             'closes_at':iso(datetime.combine(day,time.fromisoformat(end),LONDON)),
             'local_start':start,'local_end':end,'trading_date':day.isoformat(),
             'tz':'Europe/London'} for n,start,end,label in WINDOWS]


def validate_date(day,now=None):
    today=london_today(now)
    target=date.fromisoformat(day) if day else today
    if target<today:raise ValueError('Past dates cannot be used to create new forecasts.')
    if (target-today).days>7:raise ValueError('Forecast up to seven days ahead.')
    return target


def validate_display_date(day, now=None):
    today=london_today(now)
    target=date.fromisoformat(day) if day else today
    if day is None:
        while target.weekday()>=5:target+=timedelta(days=1)
    if target.weekday()>=5:raise ValueError('Choose a weekday date.')
    if (today-target).days>365 or (target-today).days>7:
        raise ValueError('Review at most one year ago or forecast up to seven days ahead.')
    return target


def prepared_slots(day, now=None, existing=()):
    now=now or datetime.now(UTC)
    claimed={x['window_id'] for x in existing}
    return [w for w in day_slots(day) if w['id'] not in claimed and now<parse_instant(w['opens_at'])]


def normalize_prediction(p,slot):
    if not isinstance(p,dict):raise ValueError('Each window forecast must be an object')
    direction=p.get('direction')
    if direction not in DIRECTIONS:raise ValueError('Unrecognized forecast direction')
    def clean(k,limit=500):
        value=p.get(k,'')
        return value.strip()[:limit] if isinstance(value,str) else ''
    reason=clean('rationale',800)
    if len(reason)<18:raise ValueError('Every forecast needs a meaningful rationale')
    if direction!='Abstain' and len(clean('invalidation'))<8:
        raise ValueError('Every directional forecast requires an invalidation')
    return {'window_id':slot['id'],'direction':direction,'rationale':reason,
            'catalyst':clean('catalyst',500),'invalidation':clean('invalidation',500),
            'leading_theory':clean('leading_theory',160),
            'alternative':clean('alternative',350),'conviction':clean('conviction',80) or 'Uncalibrated'}


def normalize_batch(response, slots):
    if not isinstance(response,dict) or not isinstance(response.get('forecasts'),list):
        raise ValueError('AI must return forecasts array')
    by_id={}
    for r in response['forecasts']:
        if not isinstance(r,dict):continue
        try:i=int(r.get('window_id'))
        except (TypeError,ValueError):continue
        if i in by_id:raise ValueError('Duplicate forecast window from AI')
        by_id[i]=r
    wanted={s['id'] for s in slots}
    if set(by_id)!=wanted:raise ValueError('AI must forecast each eligible window exactly once')
    return [normalize_prediction(by_id[s['id']],s) for s in slots]


def lock_payload(slot,prediction,published,focus,context):
    """Content digest is a tamper-evidence aid, not a blockchain or external notarisation."""
    snapshot={'id':f"{focus}:{slot['trading_date']}:{slot['id']}",'instrument':focus,
              'trading_date':slot['trading_date'],'window_id':slot['id'],'label':slot['label'],
              'opens_at':slot['opens_at'],'closes_at':slot['closes_at'],
              'local_start':slot['local_start'],'local_end':slot['local_end'],
              'published_at':iso(published),'noise_bps':NOISE_BPS,
              'forecast':prediction,'context':context,'audit_rule':'2h open-to-close; >10bps directional move; flat within 10bps',
              'origin':'AI research, not a trade signal','market_source':'User-supplied TradingView CSV; not independently verified'}
    snapshot['digest_sha256']=sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return snapshot


def init_db(c):
    c.execute('CREATE TABLE IF NOT EXISTS window_forecasts ('
      'id TEXT PRIMARY KEY, trading_date TEXT NOT NULL, window_id INTEGER NOT NULL, '
      'instrument TEXT NOT NULL, published TEXT NOT NULL, opens TEXT NOT NULL, closes TEXT NOT NULL, '
      'payload TEXT NOT NULL, UNIQUE(trading_date,window_id,instrument))')
    c.execute('CREATE INDEX IF NOT EXISTS idx_windows_date ON window_forecasts(trading_date,window_id)')
    c.execute('CREATE TABLE IF NOT EXISTS window_audits ('
      'id INTEGER PRIMARY KEY AUTOINCREMENT, forecast_id TEXT NOT NULL, audited TEXT NOT NULL, '
      'source_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(forecast_id,source_hash))')
    c.execute('CREATE INDEX IF NOT EXISTS idx_window_audit_id ON window_audits(forecast_id,id)')
    c.execute('CREATE TABLE IF NOT EXISTS window_auto_attempts (trading_date TEXT PRIMARY KEY, attempted_at TEXT NOT NULL, result TEXT NOT NULL)')
    # App-level append-only logs. A privileged DB owner can still change SQLite data.
    for table in ('window_forecasts','window_audits'):
        c.execute(f"CREATE TRIGGER IF NOT EXISTS block_{table}_update BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only audit ledger'); END")
        c.execute(f"CREATE TRIGGER IF NOT EXISTS block_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'Append-only audit ledger'); END")


def rows_for_day(c,day,focus='OANDA:XAUUSD'):
    rows=c.execute('SELECT payload FROM window_forecasts WHERE trading_date=? AND instrument=? ORDER BY window_id',(str(day),focus)).fetchall()
    return [json.loads(r['payload']) for r in rows]


def lock_forecasts(c,day,focus,slots,predictions,context,now=None):
    now=now or datetime.now(UTC)
    # Reject entire batch if even one window began while an AI call was in flight.
    if any(now>=parse_instant(s['opens_at']) for s in slots):
        raise ValueError('A window began during generation. Re-run for remaining future windows; never backdate.')
    if len(slots)!=len(predictions):raise ValueError('Forecast batch incomplete')
    locked=[]
    for slot,pred in zip(slots,predictions):
        f=lock_payload(slot,pred,now,focus,context)
        c.execute('INSERT INTO window_forecasts(id,trading_date,window_id,instrument,published,opens,closes,payload) '
                  'VALUES (?,?,?,?,?,?,?,?)',(f['id'],f['trading_date'],f['window_id'],focus,
                   f['published_at'],f['opens_at'],f['closes_at'],json.dumps(f,ensure_ascii=False)))
        locked.append(f)
    return locked


def assess_price(forecast,chart,now=None):
    """Pure deterministic audit. No AI, news or council bias is involved."""
    now=now or datetime.now(UTC)
    start=parse_instant(forecast['opens_at']);end=parse_instant(forecast['closes_at'])
    if parse_instant(forecast['published_at'])>=start:
        return {'status':'invalid','reason':'Forecast was not locked before the window began.'}
    if now<end+DELAY:
        return {'status':'awaiting-close','reason':'Window not completed plus five-minute settlement buffer.'}
    if chart.get('symbol')!=forecast['instrument']:
        return {'status':'missing-data','reason':'Wrong instrument: requires same XAU/USD price series.'}
    interval=chart.get('interval');step=BAR_SECONDS.get(interval)
    if not step:return {'status':'missing-data','reason':'Use a 1m, 3m, 5m, 10m, 15m, 30m or 1h TradingView chart.'}
    uploaded=parse_instant(chart.get('uploaded_at'))
    if uploaded<end+DELAY:
        return {'status':'missing-data','reason':'Upload a CSV exported after the window closed, not an earlier partial candle.'}
    bar_map={parse_instant(b['time']):b for b in chart.get('candles',[])}
    final_start=end-timedelta(seconds=step)
    first=bar_map.get(start);last=bar_map.get(final_start)
    if not first or not last:
        return {'status':'missing-data','reason':'CSV does not contain both exact window boundary candles.'}
    expected=int((end-start).total_seconds()/step)
    if any(start+timedelta(seconds=step*i) not in bar_map for i in range(expected)):
        return {'status':'missing-data','reason':f'CSV is missing candles inside the two-hour window ({expected} expected).'}
    opening=float(first['open']);closing=float(last['close'])
    if not (math.isfinite(opening) and math.isfinite(closing) and opening>0 and closing>0):
        return {'status':'missing-data','reason':'Bad or nonpositive price values.'}
    percent=(closing/opening-1)*100
    basis_points=percent*100
    direction=forecast['forecast']['direction']
    threshold=float(forecast['noise_bps'])
    outcome='Neutral' if abs(basis_points)<=threshold else 'Bullish' if basis_points>0 else 'Bearish'
    if direction=='Abstain':grade='Abstained'
    elif direction=='Flat':grade='Win' if outcome=='Neutral' else 'Loss'
    elif outcome=='Neutral':grade='Neutral'
    else:grade='Win' if outcome==direction else 'Loss'
    return {'status':'scored','grade':grade,'observed_direction':outcome,
            'predicted_direction':direction,'return_percent':round(percent,5),
            'return_bps':round(basis_points,3),'open_price':opening,'close_price':closing,
            'candle_interval':interval,'bars_tested':expected,
            'source':'User-supplied TradingView CSV — independently computed, not independently verified prices',
            'source_file':chart.get('filename'),'source_sha256':chart.get('sha256'),
            'uploaded_at':chart.get('uploaded_at'),'window_start':forecast['opens_at'],
            'window_end':forecast['closes_at'],'auditor':'deterministic-v0.8',
            'rule':'Fixed two-hour window; 10bps dead zone; no retroactive thresholds',
            'catalyst_result':'Not graded; documentary source evidence requires a separate dated audit'}


def audit_pending(c,forecasts,chart_records,now=None):
    """Append first valid audit only. Later snapshots can be kept as corrections
    but do not silently replace a recorded result."""
    now=now or datetime.now(UTC)
    finished=[]
    for f in forecasts:
        if parse_instant(f['closes_at'])+DELAY>now:continue
        if c.execute('SELECT 1 FROM window_audits WHERE forecast_id=? LIMIT 1',(f['id'],)).fetchone():continue
        matches=[]
        for chart in chart_records:
            if chart.get('symbol')!=f['instrument']:continue
            result=assess_price(f,chart,now)
            if result.get('status')=='scored':matches.append((PREFERRED.index(chart['interval']) if chart['interval'] in PREFERRED else 100,result))
        if not matches:continue
        matches.sort(key=lambda x:x[0]);audit=matches[0][1]
        source_hash=sha256(json.dumps({'forecast':f['digest_sha256'],'feed':audit['source_sha256'],
            'interval':audit['candle_interval'],'date':f['trading_date']},sort_keys=True).encode()).hexdigest()
        audit['forecast_id']=f['id'];audit['judged_at']=iso(now);audit['source_hash']=source_hash
        c.execute('INSERT OR IGNORE INTO window_audits(forecast_id,audited,source_hash,payload) VALUES(?,?,?,?)',
                  (f['id'],audit['judged_at'],source_hash,json.dumps(audit,ensure_ascii=False)))
        finished.append(audit)
    return finished


def latest_audits(c,forecasts):
    audits={}
    for f in forecasts:
        row=c.execute('SELECT payload FROM window_audits WHERE forecast_id=? ORDER BY id ASC LIMIT 1',(f['id'],)).fetchone()
        if row:audits[f['id']]=json.loads(row['payload'])
    return audits


def window_summary(forecasts,audits,day=None,now=None,focus='OANDA:XAUUSD'):
    now=now or datetime.now(UTC)
    if day is None:day=london_today(now)
    slots=day_slots(day);by_id={f['window_id']:f for f in forecasts}
    listed=[]
    for slot in slots:
        f=by_id.get(slot['id']);audit=audits.get(f['id']) if f else None
        if audit:state=audit.get('grade','Scored')
        elif f:state='Awaiting close' if now<parse_instant(slot['closes_at'])+DELAY else 'Awaiting price CSV'
        else:state='Upcoming — not locked' if now<parse_instant(slot['opens_at']) else 'Missed — no pre-window forecast'
        listed.append({**slot,'state':state,'forecast':f,'audit':audit})
    graded=list(audits.values())
    grades=[a['grade'] for a in graded]
    counts={k:grades.count(k) for k in ('Win','Loss','Neutral','Abstained')}
    directional=[a for a in graded if a.get('predicted_direction') in ('Bullish','Bearish')]
    scored=[a for a in directional if a['grade'] in ('Win','Loss')]
    directional_wins=sum(a['grade']=='Win' for a in scored)
    return {'trading_date':str(day),'timezone':'Europe/London','focus':focus,'held_macro_bias':'Independent from these four window forecasts',
            'noise_bps':NOISE_BPS,'windows':listed,'summary':{'locked':len(forecasts),
            'wins':counts['Win'],'losses':counts['Loss'],'neutral':counts['Neutral'],
            'abstentions':counts['Abstained'],'directional_accuracy_percent':round(100*directional_wins/len(scored),1) if scored else None,
            'scored_denominator':len(scored)},'server_time_utc':iso(now),'auto_market_feed':False,
            'data_notice':'Results are rule-based, but source prices are user CSV uploads; no verified automated market feed is connected.'}