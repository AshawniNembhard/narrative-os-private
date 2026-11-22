"""Integration tests for the two-stage manual market-data workflow."""
from datetime import datetime,timedelta,timezone
import csv,io,math
from fastapi.testclient import TestClient
import app as server


def data_csv(symbol, start, n=100):
    out=io.StringIO();w=csv.writer(out);w.writerow(['time','open','high','low','close'])
    for i in range(n):
        x=100.0+0.1*i+0.4*math.sin(i/5)
        w.writerow([(start+timedelta(hours=i)).isoformat(),x,x+1,x-1,x])
    return out.getvalue().encode()

def test_plan_upload_complete_and_rerun(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'test.db')
    server.initialize()
    with TestClient(server.app) as client:
        response=client.post('/api/council/plan',json={'question':'How do freight insurance and oil shocks reach gold via rates?', 'ai_refine':False})
        assert response.status_code==200,response.text
        plan=response.json()['plan']
        assert 'freight' in [m['id'] for m in plan['mechanisms']]
        assert len(plan['requests'])>=3
        not_ready=client.post('/api/council/run',json={'ai_synthesis':False})
        assert not_ready.status_code==200
        assert not_ready.json()['report']['status']=='incomplete-data'
        today=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
        start=today-timedelta(hours=100)
        for req in plan['requests']:
            if req['priority']!='required':continue
            response=client.post('/api/chart/import',params={'symbol':req['symbol'],'interval':req['interval']},
                     content=data_csv(req['symbol'],start),headers={'Content-Type':'text/csv','X-Filename':'chart.csv'})
            assert response.status_code==200,response.text
        response=client.get('/api/council/current')
        assert response.status_code==200
        assert response.json()['assessment']['status']=='ready-for-synthesis'
        run=client.post('/api/council/run',json={'ai_synthesis':False})
        assert run.status_code==200,run.text
        result=run.json()['report']
        assert result['status']=='ready-for-synthesis'
        assert len(result['tested_pairs'])>=2
        assert not result.get('ai_synthesis')
        assert client.get('/api/council/current').json()['last_run']['run_id']==result['run_id']