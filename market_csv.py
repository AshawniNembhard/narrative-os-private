"""Validated user-uploaded OHLC CSV snapshots. No scraping or live market connection.

Designed for TradingView's chart CSV with time, open, high, low, close and
optional Volume / indicator columns. Snapshots are local user-provided data;
they are not verified executable or real-time market prices.
"""
from __future__ import annotations
import csv
import datetime as dt
import io
import math
import re
from hashlib import sha256

UTC=dt.timezone.utc
MAX_BYTES=8_000_000
MAX_BARS=20_000
REQUIRED=('time','open','high','low','close')
SYMBOL_RE=re.compile(r'^[A-Za-z0-9_.:/!+\-]{2,55}$')
INTERVALS={'1m','3m','5m','10m','15m','30m','45m','1h','2h','3h','4h','6h','12h','1D','2D','3D','1W','1M'}

class CSVValidationError(ValueError):
    pass

def parse_time(raw):
    raw=(raw or '').strip()
    if not raw:raise CSVValidationError('A time value is missing.')
    try:
        n=float(raw)
        if not math.isfinite(n):raise ValueError()
        if abs(n)>1e11:n/=1000  # TradingView exports Unix seconds; allow milliseconds too
        return dt.datetime.fromtimestamp(n,UTC).isoformat().replace('+00:00','Z')
    except (ValueError,OverflowError,OSError):pass
    try:
        parsed=dt.datetime.fromisoformat(raw.replace('Z','+00:00'))
        if not parsed.tzinfo: parsed=parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).isoformat().replace('+00:00','Z')
    except ValueError as e:raise CSVValidationError(f'Invalid candle time {raw[:35]!r}.') from e

def num(value, field, row):
    try:
        n=float(str(value or '').strip().replace(',',''))
        if not math.isfinite(n):raise ValueError()
        return n
    except ValueError as ex:raise CSVValidationError(f'Row {row}: {field} must be a finite number.') from ex

def read_ohlcv_csv(raw:bytes, symbol:str, interval:str, filename:str='chart.csv'):
    if not raw or len(raw)>MAX_BYTES:raise CSVValidationError('CSV must be nonempty and smaller than 8 MB.')
    symbol=symbol.strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):raise CSVValidationError('Provide a ticker such as OANDA:XAUUSD or TVC:DXY.')
    if interval not in INTERVALS:raise CSVValidationError('Select a supported chart timeframe.')
    try:csv_text=raw.decode('utf-8-sig')
    except UnicodeDecodeError as e:raise CSVValidationError('CSV must be UTF-8 encoded.') from e
    # Chart exports can contain a leading sep=, hint from spreadsheet tools.
    if csv_text.startswith('sep=,\n'):csv_text=csv_text[6:]
    reader=csv.DictReader(io.StringIO(csv_text, newline=''))
    if not reader.fieldnames:raise CSVValidationError('CSV has no header.')
    names={name.strip().lower():name for name in reader.fieldnames if name}
    time_name=next((names[x] for x in ('time','timestamp','date','datetime') if x in names),None)
    missing=[x for x in REQUIRED if (time_name is None if x=='time' else x not in names)]
    if missing:raise CSVValidationError('Missing required CSV columns: '+', '.join(missing))
    out={}; rowcount=0
    extras=[name for name in reader.fieldnames if name and name not in [time_name,*[names[k] for k in REQUIRED if k!='time']]]
    vol_name=next((x for x in extras if x.strip().lower() in ('volume','volume sma')),None)
    used_indicators=[x for x in extras if x!=vol_name][:12]
    last_indicators={}
    for row in reader:
        rowcount+=1
        if rowcount>MAX_BARS:raise CSVValidationError('Maximum 20,000 rows per CSV; export a shorter chart window.')
        if not any(str(v or '').strip() for v in row.values()):continue
        t=parse_time(row.get(time_name))
        o,h,l,c=[num(row.get(names[k]),k,rowcount+1) for k in ('open','high','low','close')]
        eps=max(abs(o),abs(c),abs(h),abs(l),1)*1e-9
        if h+eps<max(o,c,l) or l-eps>min(o,c,h) or h+eps<l:
            raise CSVValidationError(f'Row {rowcount+1}: inconsistent OHLC high/low values.')
        candle={'time':t,'open':o,'high':h,'low':l,'close':c}
        if vol_name and row.get(vol_name) not in (None,''):
            v=num(row.get(vol_name),'volume',rowcount+1)
            if v<0:raise CSVValidationError(f'Row {rowcount+1}: volume cannot be negative.')
            candle['volume']=v
        extras_on_row={}
        for k in used_indicators:
            value=row.get(k)
            if value not in ('',None):
                try:
                    f=float(value)
                    if math.isfinite(f):extras_on_row[k]=f
                except ValueError:pass
        if extras_on_row:candle['indicators']=extras_on_row
        out[t]=candle
    candles=[out[k] for k in sorted(out)]
    if len(candles)<2:raise CSVValidationError('At least two distinct timestamped candles are needed.')
    first,last=candles[0],candles[-1]
    def pct(a,b):return round((b/a-1)*100,5) if a else None
    window=candles[-20:]
    previous=candles[-2]
    last_indicators=last.get('indicators',{})
    return {'symbol':symbol,'interval':interval,'filename':re.sub(r'[^a-zA-Z0-9_.-]','_',filename)[:110],
        'sha256':sha256(raw).hexdigest(),'bars':len(candles),'duplicates_removed':rowcount-len(candles),
        'first_time':first['time'],'last_time':last['time'],'latest_open':last['open'],
        'latest_high':last['high'],'latest_low':last['low'],'latest_close':last['close'],
        'prior_close':previous['close'],'one_bar_percent':pct(previous['close'],last['close']),
        'twenty_bar_percent':pct(window[0]['close'],last['close']),
        'sample_percent':pct(first['close'],last['close']),
        'twenty_bar_low':min(x['low'] for x in window),
        'twenty_bar_high':max(x['high'] for x in window),
        'indicators':last_indicators,'candles':candles,
        'cautions':['Latest candle may still be forming.','Prices are user-uploaded, not verified live quotes.',
                    'Naive date/time strings are interpreted as UTC. Check your export time zone.']}

def public_view(record,chart_limit=180):
    value={k:v for k,v in record.items() if k!='candles'}
    value['chart']=[{'time':b['time'],'close':b['close'],'high':b['high'],'low':b['low']} for b in record.get('candles',[])[-chart_limit:]]
    return value