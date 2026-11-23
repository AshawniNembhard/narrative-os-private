"""Out-of-sample windows auditor; no AI can grade itself."""
from datetime import datetime,timedelta,timezone,date
from zoneinfo import ZoneInfo
import io,math,csv,json,sqlite3
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app as server
import window_forecasts as w

UTC=timezone.utc
FIXED=datetime(2026,11,23,0,15,tzinfo=UTC)

def forecast_for(slot,direction='Bullish',now=FIXED):
    return w.lock_payload(slot,{'window_id':slot['id'],'direction':direction,
       'rationale':'Shipping risk or dollar liquidity makes this window potentially directional.',
       'catalyst':'Marine insurance notices','invalidation':'No price reaction','leading_theory':'Freight'},
       now,'OANDA:XAUUSD',{'source':'local test'})

def candles_for(slot,moves=(100.0,100.5),interval='1h',end_lag_minutes=10):
    start=w.parse_instant(slot['opens_at']);end=w.parse_instant(slot['closes_at']);step=w.BAR_SECONDS[interval]
    n=int((end-start).total_seconds()/step)
    data=[]
    for i in range(n):
        p=moves[0]+(moves[1]-moves[0])*i/n
        q=moves[0]+(moves[1]-moves[0])*(i+1)/n
        data.append({'time':w.iso(start+timedelta(seconds=step*i)),
                     'open':p,'close':q,'high':max(p,q)+1,'low':min(p,q)-1})
    return {'symbol':'OANDA:XAUUSD','interval':interval,'candles':data,
            'uploaded_at':w.iso(end+timedelta(minutes=end_lag_minutes)),'sha256':'a'*64,'filename':'gold.csv'}

def test_four_exact_trading_windows_and_dst():
    fri=w.day_slots('2026-03-27');mon=w.day_slots('2026-03-30')
    assert [x['local_start'] for x in mon]==['01:00','04:00','07:00','13:00']
    assert [x['local_end'] for x in mon]==['03:00','06:00','09:00','15:00']
    assert fri[2]['opens_at']=='2026-03-27T07:00:00Z'
    assert mon[2]['opens_at']=='2026-03-30T06:00:00Z'
    assert w.day_slots('2026-10-23')[2]['opens_at']=='2026-10-23T06:00:00Z'
    assert w.day_slots('2026-10-26')[2]['opens_at']=='2026-10-26T07:00:00Z'
    with pytest.raises(ValueError):w.day_slots('2026-11-22')

def test_lock_only_future_windows_and_reject_time_crossing():
    slots=w.day_slots('2026-11-23')
    now=datetime(2026,11,23,4,30,tzinfo=UTC)
    assert [x['id'] for x in w.prepared_slots('2026-11-23',now)]==[3,4]
    with pytest.raises(ValueError,match='began'):
        w.lock_forecasts(sqlite3.connect(':memory:'),'2026-11-23','OANDA:XAUUSD',
                         [slots[1]],[{}],{},now)
    with pytest.raises(ValueError):w.validate_date('2026-11-22',now)

def test_ai_batch_normalisation_requires_all_windows_and_valid_directions():
    slots=w.day_slots('2026-11-23')[:2]
    def p(n,di):return {'window_id':n,'direction':di,
        'rationale':'A sufficiently long speculative rationale for this exact two-hour window',
        'catalyst':'Insurance premium','invalidation':'Price action breaks hypothesis'}
    assert w.normalize_batch({'forecasts':[p(1,'Bullish'),p(2,'Bearish')]},slots)[1]['direction']=='Bearish'
    with pytest.raises(ValueError):w.normalize_batch({'forecasts':[p(1,'Bullish')]},slots)
    with pytest.raises(ValueError):w.normalize_batch({'forecasts':[p(1,'Rise'),p(2,'Flat')]},slots)

@pytest.mark.parametrize('direction,close,expected',[
    ('Bullish',101,'Win'),('Bullish',99,'Loss'),('Bearish',99,'Win'),('Bearish',101,'Loss'),
    ('Bullish',100.05,'Neutral'),('Flat',100.05,'Win'),('Flat',101,'Loss'),('Abstain',101,'Abstained')])
def test_deterministic_scores(direction,close,expected):
    slot=w.day_slots('2026-11-23')[0]
    f=forecast_for(slot,direction)
    chart=candles_for(slot,(100,close))
    result=w.assess_price(f,chart,w.parse_instant(slot['closes_at'])+timedelta(hours=1))
    assert result['grade']==expected
    assert result['source_sha256']=='a'*64
    assert result['candle_interval']=='1h'
    assert result['catalyst_result'].startswith('Not graded')

def test_no_future_data_no_partial_candles_no_wrong_symbol():
    slot=w.day_slots('2026-11-23')[0];f=forecast_for(slot)
    end=w.parse_instant(slot['closes_at'])
    chart=candles_for(slot)
    assert w.assess_price(f,chart,end)['status']=='awaiting-close'
    chart['uploaded_at']=w.iso(end-timedelta(minutes=1))
    assert w.assess_price(f,chart,end+timedelta(hours=1))['status']=='missing-data'
    chart=candles_for(slot);chart['candles']=chart['candles'][:1]
    assert w.assess_price(f,chart,end+timedelta(hours=1))['status']=='missing-data'
    chart=candles_for(slot);chart['symbol']='COMEX:GC1!'
    assert w.assess_price(f,chart,end+timedelta(hours=1))['status']=='missing-data'
    f['published_at']=w.iso(end)
    assert w.assess_price(f,candles_for(slot),end+timedelta(hours=1))['status']=='invalid'

def test_append_only_forecasts_and_first_audit_never_overwritten():
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;w.init_db(c)
    slot=w.day_slots('2026-11-23')[0]
    f=w.lock_forecasts(c,'2026-11-23','OANDA:XAUUSD',[slot],
           [{'window_id':1,'direction':'Bullish','rationale':'Many signs of risk aversion in the gold market',
             'catalyst':'shipping','invalidation':'No quoted spread change'}],{},FIXED)[0]
    c.commit()
    assert f['digest_sha256']
    with pytest.raises(sqlite3.IntegrityError):
        w.lock_forecasts(c,'2026-11-23','OANDA:XAUUSD',[slot],
          [{'window_id':1,'direction':'Bearish'}],{},FIXED)
    with pytest.raises(sqlite3.IntegrityError):
        c.execute('UPDATE window_forecasts SET published=? WHERE id=?',('2030',f['id']))
    chart=candles_for(slot,(100,101))
    end=w.parse_instant(slot['closes_at'])+timedelta(hours=1)
    result=w.audit_pending(c,[f],[chart],end)
    assert result[0]['grade']=='Win'
    assert not w.audit_pending(c,[f],[candles_for(slot,(100,99))],end)
    assert w.latest_audits(c,[f])[f['id']]['grade']=='Win'
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM window_audits')

def test_dashboard_has_missed_window_not_fabricated_history():
    now=datetime(2026,11,23,4,30,tzinfo=UTC)
    board=w.window_summary([],{},'2026-11-23',now)
    assert board['summary']['directional_accuracy_percent'] is None
    assert board['windows'][0]['state'].startswith('Missed')
    assert board['windows'][2]['state'].startswith('Upcoming')

def test_forecast_endpoint_and_paid_scheduler_off_by_default(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'empty.db')
    monkeypatch.setenv('DISABLE_POLLING','1')
    monkeypatch.setenv('OPENAI_API_KEY','test-placeholder-not-real')
    server.initialize()
    nextday=w.london_today()+timedelta(days=1)
    while nextday.weekday()>=5:nextday+=timedelta(days=1)
    def fake_ai(system,payload):
        return {'forecasts':[{'window_id':x['window_id'],'direction':'Bullish' if x['window_id']%2 else 'Bearish',
             'rationale':'Possible shipping pressure and a serious opposing macro narrative',
             'invalidation':'Unexpected rise in US yields','catalyst':'Shipping premium',
             'leading_theory':'Freight','alternative':'Dollar liquidity'} for x in payload['windows_to_forecast']]}
    monkeypatch.setattr(server.cloud_ai,'infer_json',fake_ai)
    monkeypatch.setattr(server.cloud_ai,'configured',lambda:True)
    with TestClient(server.app) as client:
        board=client.get('/api/windows',params={'date':nextday.isoformat()}).json()
        assert board['auto_enabled'] is False
        assert len(board['windows'])==4
        r=client.post('/api/windows/forecast',json={'date':nextday.isoformat()})
        assert r.status_code==200,r.text
        assert r.json()['count']==4
        assert client.post('/api/windows/forecast',json={'date':nextday.isoformat()}).status_code==409
        board=client.get('/api/windows',params={'date':nextday.isoformat()}).json()
        assert board['summary']['locked']==4
        assert board['windows'][0]['forecast']['forecast']['direction']=='Bullish'
        assert board['windows'][1]['forecast']['forecast']['direction']=='Bearish'
        perf=client.get('/api/windows/performance').json()
        assert perf['total']['locked']==4
        assert perf['total']['win_rate'] is None
        assert client.post('/api/windows/auto',json={'enabled':False}).status_code==200