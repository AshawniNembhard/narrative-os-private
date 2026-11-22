from datetime import datetime,timezone
from fastapi.testclient import TestClient
import app as server

NOW=datetime.now(timezone.utc).isoformat()

def verified_event(id,impacts):
    return {'id':id,'time':NOW,'type':'macro','title':id,'detail':'Test-only hypothetical structured release',
        'source_kind':'licensed_calendar_release','source':'https://example.org/releases/'+id,
        'actual':'3.7','consensus':'3.2','impacts':impacts,
        'score':{'method':'rules','significance':{'value':4},'novelty':{'value':4},'reliability':{'value':4}}}

def test_api_keeps_persistent_macro_bias_when_chart_upload_missing(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'council.db')
    server.initialize()
    with TestClient(server.app) as client:
        p=client.post('/api/council/plan',json={'question':'Does gold respond to an inflation surprise in real yields?','horizon':'intraday'})
        assert p.status_code==200,p.text
        evt=verified_event('official-test-1',{'rates':-2,'growth':1,'haven':0})
        with server.DB_LOCK,server.conn() as c:server.save_event(c,evt,'live')
        a=client.post('/api/council/run',json={'ai_synthesis':False})
        assert a.status_code==200,a.text
        b=a.json()['report']['fundamental_bias']
        assert b['direction']=='Bullish' and b['state']=='established' and b['basis']=='macro-evidence'
        assert a.json()['report']['status']=='incomplete-data'
        repeat=client.post('/api/council/run',json={'ai_synthesis':False})
        rb=repeat.json()['report']['fundamental_bias']
        assert rb['direction']=='Bullish' and rb['state']=='retained'
        assert rb['new_evidence_count']==0
        # Fresh GET reflects committed state, but does not count another update.
        current=client.get('/api/council/current').json()
        assert current['last_run']['fundamental_bias']['direction']=='Bullish'
        assert current['assessment']['fundamental_bias']['direction']=='Bullish'
        assert current['assessment']['leading_observation'].startswith('Fundamental research bias: Bullish')

def test_user_adopted_provisional_thesis_is_audited_and_durable(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'seed.db')
    server.initialize()
    with TestClient(server.app) as client:
        client.post('/api/council/plan',json={'question':'Could physical gold refinancing create a supply shortage for lenders?'})
        adopted=client.post('/api/council/bias/adopt',json={'direction':'Bearish',
             'rationale':'Hypothetical gold lending relief could create incremental supply pressure.'})
        assert adopted.status_code==200,adopted.text
        state=adopted.json()['assessment']['fundamental_bias']
        assert state['direction']=='Bearish' and state['basis']=='user-hypothesis'
        assert state['state']=='provisional-user'
        assert state['history'][-1]['state']=='provisional-user'
        rerun=client.post('/api/council/run',json={'ai_synthesis':False})
        assert rerun.status_code==200,rerun.text
        saved=rerun.json()['report']['fundamental_bias']
        assert saved['direction']=='Bearish' and saved['basis']=='user-hypothesis'
        assert saved['state']=='retained'