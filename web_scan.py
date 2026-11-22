"""Free/public web discovery adapters for Narrative OS.

Search results are *headline discovery*, never numerical releases. Dated market
observations are independently extracted from public price tables and official
Treasury feeds. Every input has a source and observation timestamp.
"""
from __future__ import annotations
import csv
import datetime as dt
import hashlib
import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UTC = dt.timezone.utc
GOOGLE_NEWS = 'https://news.google.com/rss/search?'
TREASURY_XML = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml'
STOOQ = 'https://stooq.com/q/d/l/?'
YAHOO = 'https://query1.finance.yahoo.com/v8/finance/chart/'
SEARCHES = [
    ('macro', 'US CPI jobs inflation Federal Reserve Treasury yields gold when:3d'),
    ('gold', 'gold XAUUSD dollar index real yields TIPS when:3d'),
    ('alternative', 'shipping insurance freight oil energy disruption inflation when:4d'),
]

def digest(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()[:24]
def utc_now(): return dt.datetime.now(UTC).isoformat().replace('+00:00','Z')
def to_iso(raw):
    try:
        dtval=parsedate_to_datetime(raw)
        return dtval.astimezone(UTC).isoformat().replace('+00:00','Z')
    except Exception: return None

def search_news(fetch, now=None, max_per_query=10):
    """Search Google News index via public RSS, retaining headline provenance.

    Entries are not verified economic releases and cannot be used as price quotes.
    """
    now=now or dt.datetime.now(UTC)
    items=[];errors={}
    for category,query in SEARCHES:
        url=GOOGLE_NEWS+urllib.parse.urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
        try:
            tree=ET.fromstring(fetch(url))
            for r in tree.findall('./channel/item')[:max_per_query]:
                title=(r.findtext('title') or '').strip()[:180]
                link=(r.findtext('link') or '').strip()
                timestamp=to_iso(r.findtext('pubDate') or '')
                source_node=r.find('source')
                publisher=(source_node.text or '').strip() if source_node is not None else ''
                if not title or not timestamp or not link:continue
                when=dt.datetime.fromisoformat(timestamp.replace('Z','+00:00'))
                if when>now+dt.timedelta(minutes=10) or when<now-dt.timedelta(days=6):continue
                # Google News RSS sometimes uses link redirects; do not pretend it is the publisher URL.
                key=digest(link+'\n'+title)
                items.append({'id':'web-news-'+key,'time':timestamp,'type':'news' if category!='alternative' else 'research',
                    'title':title,'detail':f'Search-discovered headline ({publisher or "publisher not specified"}). Not yet verified against the original report. Search terms: {query}.',
                    'source':link,'publisher':publisher,'discovery_query':query,'source_kind':'search_headline',
                    'retrieved_at':utc_now(),'market_verified':False})
        except Exception as ex:errors[category]=str(ex)[:140]
    return dedupe(items),errors

def dedupe(items):
    seen=set();result=[]
    for e in sorted(items,key=lambda r:r['time']):
        # Identical title+URL across multiple search queries is one discovered report.
        k=e['id']
        if k not in seen:seen.add(k);result.append(e)
    return result

def _price_rows(data):
    text=data.decode('utf-8-sig',errors='replace')
    rows=list(csv.DictReader(io.StringIO(text)))
    if not rows or not all(k in rows[0] for k in ('Date','Close')):
        raise ValueError('Price source unavailable or did not return a dated CSV')
    obs=[]
    for r in rows:
        try:
            day=dt.date.fromisoformat(r['Date'])
            v=float((r.get('Close') or '').replace(',',''))
            if 0<v<1_000_000:obs.append((day,v))
        except (TypeError,ValueError):pass
    if not obs:raise ValueError('No usable price observations')
    return sorted(set(obs))

def get_stooq_market(fetch, symbol, label, unit, proxy=False, now=None):
    """Stooq daily EOD series, never claim this is live or executable."""
    now=now or dt.datetime.now(UTC)
    query=urllib.parse.urlencode({'s':symbol,'i':'d','d1':(now-dt.timedelta(days=12)).strftime('%Y%m%d'),
                                  'd2':now.strftime('%Y%m%d')})
    url=STOOQ+query
    rows=_price_rows(fetch(url))
    last_date,last_val=rows[-1]
    prior=next((v for day,v in reversed(rows[:-1]) if day<last_date),None)
    move_pct=round(100*(last_val/prior-1),4) if prior else None
    return {'id':f'market-{symbol.lower().replace(".","-")}-{last_date.isoformat()}',
        'time':last_date.isoformat()+'T23:59:00Z','type':'market','title':label+' — daily close',
        'detail':f'{label} daily close: {last_val:,.4f} {unit} on {last_date.isoformat()}.'+
            (f' Change vs prior daily close: {move_pct:+.3f}%.' if move_pct is not None else '')+
            (' Futures proxy; NOT spot DXY.' if proxy else '')+
            ' End-of-day public snapshot, NOT a live executable quote.',
        'source':url,'source_kind':'public_daily_market','observation_date':last_date.isoformat(),
        'retrieved_at':utc_now(),'market_verified':True,'market_key':'dollar' if proxy else 'gold',
        'value':last_val,'previous':prior,'change_percent':move_pct,'unit':unit,'frequency':'daily',
        'proxy':proxy}

def get_yahoo_dollar(fetch, now=None):
    """Unlicensed Yahoo chart fallback; use for personal research only."""
    now=now or dt.datetime.now(UTC)
    url=YAHOO+urllib.parse.quote('DX-Y.NYB',safe='')+'?range=5d&interval=1d'
    raw=json.loads(fetch(url))
    chart=(raw.get('chart') or {}).get('result') or []
    if not chart:raise ValueError('Dollar index chart unavailable')
    obj=chart[0];times=obj.get('timestamp') or []
    close=(((obj.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
    rows=[]
    for timestamp,value in zip(times,close):
        if isinstance(value,(float,int)) and value>0:
            day=dt.datetime.fromtimestamp(timestamp,UTC).date();rows.append((day,float(value)))
    if not rows:raise ValueError('Dollar index chart contains no observations')
    day,value=rows[-1];prior=rows[-2][1] if len(rows)>1 else None
    return {'id':'market-dxy-'+day.isoformat(),'time':day.isoformat()+'T23:59:00Z',
        'type':'market','title':'US Dollar Index (DXY) — daily chart close',
        'detail':f'DXY chart close {value:.3f} points on {day.isoformat()}.'+
          (f' Change vs preceding close: {100*(value/prior-1):+.3f}%.' if prior else '')+
          ' Unofficial, potentially delayed data endpoint; do not use as a trading quote.',
        'source':url,'source_kind':'unofficial_market_snapshot','observation_date':day.isoformat(),
        'retrieved_at':utc_now(),'market_verified':True,'market_key':'dollar','value':value,
        'previous':prior,'change_percent':round(100*(value/prior-1),4) if prior else None,
        'unit':'index points','frequency':'daily','proxy':False}

def get_treasury_real(fetch, now=None):
    """Parse official daily TIPS real yield 10-year curve as Atom/OData XML."""
    now=now or dt.datetime.now(UTC)
    url=TREASURY_XML+'?'+urllib.parse.urlencode({'data':'daily_treasury_real_yield_curve',
                                            'field_tdr_date_value_month':now.strftime('%Y%m')})
    root=ET.fromstring(fetch(url))
    rows=[]
    for entry in root.iter():
        if entry.tag.rsplit('}',1)[-1]!='entry':continue
        props={el.tag.rsplit('}',1)[-1].upper():(el.text or '').strip() for el in entry.iter()}
        date=(props.get('NEW_DATE') or '')[:10]
        try:day=dt.date.fromisoformat(date)
        except ValueError:continue
        candidates=('TC_10YEAR','BC_10YEAR','10_YEAR','TEN_YEAR','TEN_YEAR_REAL')
        value=next((props[x] for x in candidates if props.get(x)),None)
        if not value:
            value=next((v for k,v in props.items() if '10YEAR' in k and not k.startswith('ID') and v),None)
        try:rows.append((day,float(value)))
        except (TypeError,ValueError):continue
    if not rows:raise ValueError('No 10-year real yield found in official Treasury feed')
    rows.sort();day,value=rows[-1]
    if day>now.date():raise ValueError('Treasury observation in the future')
    prior=rows[-2][1] if len(rows)>1 else None
    return {'id':'treasury-10y-real-'+day.isoformat(),'time':day.isoformat()+'T23:59:00Z','type':'market',
       'title':'10-year US TIPS real yield — official daily curve',
       'detail':f'Treasury 10-year par real yield {value:.3f}% on {day.isoformat()}.'+
           (f' Change vs preceding Treasury observation: {value-prior:+.3f} percentage points.' if prior is not None else '')+
           ' Published daily; this is NOT an intraday real-yield quote.',
       'source':url,'source_kind':'official_daily_treasury','observation_date':day.isoformat(),
       'retrieved_at':utc_now(),'market_verified':True,'market_key':'real_yield','value':value,
       'previous':prior,'change_percent':None,'change_pp':round(value-prior,4) if prior is not None else None,
       'unit':'% yield','frequency':'daily','proxy':False}

def search_custom(fetch,question,now=None):
    """One user-authored search; never treat discovered RSS titles as verified facts."""
    clean=' '.join(re.findall(r'[A-Za-z0-9\-.,]+',question))[:180].strip()
    if len(clean)<4:raise ValueError('Provide a more specific search question')
    now=now or dt.datetime.now(UTC)
    query=clean+' when:7d'
    url=GOOGLE_NEWS+urllib.parse.urlencode({'q':query,'hl':'en-US','gl':'US','ceid':'US:en'})
    results=[]
    root=ET.fromstring(fetch(url))
    for r in root.findall('./channel/item')[:14]:
        title=(r.findtext('title') or '').strip()[:180]
        link=(r.findtext('link') or '').strip()
        stamp=to_iso(r.findtext('pubDate') or '')
        source=r.find('source');publisher=(source.text or '').strip() if source is not None else ''
        if not title or not link or not stamp:continue
        date=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if date>now+dt.timedelta(minutes=10) or date<now-dt.timedelta(days=8):continue
        results.append({'id':'web-news-'+digest(link+'\n'+title),'time':stamp,
                        'type':'news','title':title,'detail':f'Web search headline published by {publisher or "unknown outlet"}; original article unverified.',
                        'source':link,'retrieved_at':utc_now(),'source_kind':'search_headline','discovery_query':query,
                        'market_verified':False})
    return dedupe(results)

def get_yahoo_gold_futures(fetch,now=None):
    """Fallback is GC=F gold futures, labelled as a proxy NOT spot XAUUSD."""
    now=now or dt.datetime.now(UTC)
    url=YAHOO+urllib.parse.quote('GC=F',safe='')+'?range=5d&interval=1d'
    raw=json.loads(fetch(url))
    chart=(raw.get('chart') or {}).get('result') or []
    if not chart:raise ValueError('Gold futures fallback chart unavailable')
    obj=chart[0]
    ts=obj.get('timestamp') or []
    closes=(((obj.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
    rows=[]
    for timestamp,value in zip(ts,closes):
        if isinstance(value,(float,int)) and value>0:
            rows.append((dt.datetime.fromtimestamp(timestamp,UTC).date(),float(value)))
    if not rows:raise ValueError('Gold futures chart has no dated close')
    day,value=rows[-1];prior=rows[-2][1] if len(rows)>1 else None
    return {'id':'market-goldfutures-'+day.isoformat(),'time':day.isoformat()+'T23:59:00Z',
        'type':'market','title':'Gold futures (GC=F) — NOT XAU/USD spot',
        'detail':f'Gold futures daily close {value:.2f} USD per troy oz on {day.isoformat()}.'+
          (f' Change vs prior close: {100*(value/prior-1):+.3f}%.' if prior else '')+
          ' This is a gold futures proxy, NOT XAU/USD spot. Unofficial chart endpoint; potentially delayed.',
        'source':url,'source_kind':'unofficial_market_snapshot','observation_date':day.isoformat(),
        'retrieved_at':utc_now(),'market_verified':True,'market_key':'gold','value':value,
        'previous':prior,'change_percent':round(100*(value/prior-1),4) if prior else None,
        'unit':'USD per troy oz','frequency':'daily','proxy':True}