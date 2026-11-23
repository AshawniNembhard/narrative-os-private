"""Dynamic research inputs: catalogue safety, persistence, evidence availability and forecast locks."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
import app as server
import window_inputs as wi
import interdisciplinary
import window_forecasts as wf
UTC=timezone.utc
NOW=datetime(2026,11,23,9,0,tzinfo=UTC)

def chart(symbol,interval,last=None,bars=120):
    return {'symbol':symbol,'interval':interval,'last_time':(last or NOW-timedelta(hours=2)).isoformat(),
            'bars':bars,'latest_close':123,'one_bar_percent':.4,'twenty_bar_percent':1.5,'uploaded_at':NOW.isoformat()}

def test_validates_ai_request_catalog_and_daily_yields():
    o=wi.from_ai({'reason':'Energy disruptions affect dollar and gold markets','requests':[
        {'key':'oil','interval':'5m','priority':'required','reason':'Energy repricing as freight shifts'},
        {'key':'breakeven','interval':'5m','priority':'required','reason':'Rates context is only daily'},
        {'key':'NOT-A-TICKER','interval':'1h','priority':'required'},
        {'key':'dxy','interval':'5m','priority':'optional'}
    ]},interdisciplinary.CATALOG,'p1')
    assert [r['symbol'] for r in o['requests']]==['OANDA:XAUUSD','OANDA:WTICOUSD','FRED:T5YIE','TVC:DXY']
    assert o['requests'][2]['interval']=='1D'
    assert o['requests'][2]['priority']=='context'
    assert o['source_plan_id']=='p1'
    assert sum(x['priority']=='required' for x in o['requests'])==2

def test_rejects_hallucinated_or_empty_basket():
    with pytest.raises(ValueError):wi.from_ai({'requests':[{'key':'HACK:USD','priority':'required'}]},interdisciplinary.CATALOG)
    with pytest.raises(ValueError):wi.from_ai({'requests':[{'key':'real','priority':'required'}]},interdisciplinary.CATALOG)
    with pytest.raises(ValueError):wi.from_ai({'requests':[]},interdisciplinary.CATALOG)

def test_from_research_studio_dynamic_tickers_not_fixed_four():
    plan={'id':'plan-new','focus':wi.FOCUS,'why_these_tickers':'Oil rate pressure hypothesis',
          'requests':[{'key':'focus','symbol':wi.FOCUS,'interval':'1h','priority':'required','name':'Gold'},
             {'key':'brent','symbol':'ICEEUR:BRN1!','interval':'1h','priority':'required','name':'Brent'},
             {'key':'yen','symbol':'OANDA:USDJPY','interval':'1h','priority':'optional','name':'USDJPY'}]}
    out=wi.from_studio(plan,interdisciplinary.CATALOG)
    assert out['source']=='research-studio'
    assert [x['symbol'] for x in out['requests']]==[wi.FOCUS,'ICEEUR:BRN1!','OANDA:USDJPY']
    assert 'TVC:DXY' not in [x['symbol'] for x in out['requests']]
    assert wi.from_studio({**plan,'focus':'OANDA:GBPJPY'},interdisciplinary.CATALOG)['source']=='default-context'

def test_readiness_exact_timeframes_and_staleness():
    req=[{'symbol':wi.FOCUS,'interval':'1h','priority':'required'},
         {'symbol':'TVC:DXY','interval':'5m','priority':'required'},
         {'symbol':'COMEX:GC1!','interval':'1D','priority':'context'}]
    charts=[chart(wi.FOCUS,'1h'),chart('TVC:DXY','1h'),chart('COMEX:GC1!','1D',NOW-timedelta(days=18))]
    s=wi.status_for(req,charts,NOW)
    assert [x['status'] for x in s['requests']]==['ready','missing','stale']
    assert s['summary']['required_ready']==1 and s['summary']['required_not_ready']==1
    charts.append(chart('TVC:DXY','5m',bars=5))
    assert wi.status_for(req,charts,NOW)['requests'][1]['status']=='insufficient'
    charts[-1]['bars']=60
    assert wi.status_for(req,charts,NOW)['requests'][1]['status']=='ready'

def test_existing_plan_selects_requested_brent_and_is_in_ai_context(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'v09.db')
    monkeypatch.setenv('DISABLE_POLLING','1')
    monkeypatch.setenv('OPENAI_API_KEY','fake-not-real')
    server.initialize()
    plan={'id':'dynamic-1','focus':wi.FOCUS,'question':'How might energy shipping disruptions affect gold and Brent?',
          'horizon':'intraday','requests':[
             {'key':'focus','symbol':wi.FOCUS,'name':'Gold','interval':'1h','priority':'required','reason':'Spot'},
             {'key':'brent','symbol':'ICEEUR:BRN1!','name':'Brent','interval':'1h','priority':'required','reason':'Energy'}],
          'research_cycle':{'leading_title':'Freight insurance and gold','leading_direction':'Bullish'}}
    plan={**interdisciplinary.plan(plan['question'],wi.FOCUS,'intraday'),**plan}
    with server.conn() as c:
        c.execute('INSERT INTO council_plans(id,created,payload) VALUES (?,?,?)',
                  (plan['id'],NOW.isoformat(),json.dumps(plan)))
    got=[]
    def ai(system,payload):
        got.append(payload)
        if 'catalog' in payload:
            return {'reason':'Oil and yen','requests':[{'key':'oil','priority':'required','interval':'5m'},
                                                       {'key':'yen','priority':'optional','interval':'5m'}]}
        return {'forecasts':[{'window_id':x['window_id'],'direction':'Abstain',
                             'rationale':'Insufficient fresh evidence for this two-hour window',
                             'invalidation':'Unexpected gold trend','leading_theory':'Freight risk'}
                            for x in payload['windows_to_forecast']]}
    monkeypatch.setattr(server.cloud_ai,'infer_json',ai)
    monkeypatch.setattr(server.cloud_ai,'configured',lambda:True)
    with TestClient(server.app) as client:
        before=client.get('/api/windows/requirements').json()
        assert [x['symbol'] for x in before['requests']]==[wi.FOCUS,'ICEEUR:BRN1!']
        after=client.post('/api/windows/requirements/refresh').json()
        assert [x['symbol'] for x in after['requests']]==[wi.FOCUS,'OANDA:WTICOUSD','OANDA:USDJPY']
        # New research plan must supersede an older on-demand refresh.
        newplan={**plan,'id':'dynamic-2','requests':[plan['requests'][0],
          {'key':'vix','symbol':'CBOE:VIX','name':'VIX','interval':'1h','priority':'required','reason':'Haven demand'}]}
        with server.conn() as c:
            c.execute('INSERT INTO council_plans(id,created,payload) VALUES (?,?,?)',
                      (newplan['id'],(NOW+timedelta(hours=1)).isoformat(),json.dumps(newplan)))
        fresh=client.get('/api/windows/requirements').json()
        assert [x['symbol'] for x in fresh['requests']]==[wi.FOCUS,'CBOE:VIX']
        # Restore for the forecast: our AI-refreshed plan must be preserved when matching plan is current.
        with server.conn() as c:
            c.execute('DELETE FROM council_plans WHERE id=?',(newplan['id'],))
        day=(wf.london_today()+timedelta(days=1))
        while day.weekday()>=5:day+=timedelta(days=1)
        no=client.post('/api/windows/forecast',json={'date':day.isoformat()})
        assert no.status_code==409
        yes=client.post('/api/windows/forecast',json={'date':day.isoformat(),'allow_partial':True})
        assert yes.status_code==200,yes.text
        assert yes.json()['count']==4
        c=got[-1]['research_context']
        assert c['ticker_selection_source']=='window-ai-refreshed'
        assert [x['symbol'] for x in c['requested_inputs']]==[wi.FOCUS,'OANDA:WTICOUSD','OANDA:USDJPY']
        assert 'TVC:DXY' not in [x['symbol'] for x in c['requested_inputs']]
        locked=yes.json()['locked'][0]
        assert locked['context']['partial_data_acknowledged']
        assert locked['context']['ticker_selection_source']=='window-ai-refreshed'
        assert locked['context']['required_coverage_at_lock']['required_not_ready']>0