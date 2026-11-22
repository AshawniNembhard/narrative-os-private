"""Regressions for on-demand interdisciplinary discovery, CSV gating, and held bias."""
from datetime import datetime,timezone
import app as server
import bias_engine
import research_cycle
from fastapi.testclient import TestClient


def sample_discovery(direction='Bearish'):
    return {
        'selected_keys':['oil','dxy','nominal'],
        'rationale':'Energy-and-currency basket captures competing propagation paths.',
        'hypothesis':'Cross-asset flows might affect gold despite a real-yield rise.',
        'novel_link':{
            'chain':'Marine insurance pricing could affect cargo choices and fuel costs, causing rate repricing while gold hedging changes.',
            'evidence_needed':'Insurance quotes and actual shipping diversions over the same dates.',
            'falsifier':'No diversion or delivered fuel price change.'},
        'theories':[
            {'title':'Insurance to fuel to real rates','direction':direction,
             'chain':'Marine insurers price an early threat, raising delivered energy costs and future policy rate expectations before gold adapts.',
             'falsifier':'Insurers do not reprice and delivered fuel costs do not change.',
             'external_evidence':'Dated insurance quotations and independent delivered-fuel bills.',
             'earliest_indicator':'Price of insurance quotes','horizon':'days-to-weeks'},
            {'title':'Gold as collateral under funding stress','direction':'Bullish',
             'chain':'Funding and collateral schedules redirect physical-gold demand through intermediaries before headline liquidity measures move.',
             'falsifier':'No documented collateral shortage or borrowing spread change.',
             'external_evidence':'Dated custody requirements, delivery volumes and basis transactions.',
             'earliest_indicator':'Collateral borrowing conditions','horizon':'weeks'},
        ],
        'leading_index':0,
        'leading_reason':'A hypothetical insurance repricing could precede observable commodity repricing.',
        'why_unconventional':'Links insurance microstructure, fuel logistics, monetary policy and gold.',
        'cannot_conclude':'No physical flows confirmed.'
    }


def test_discovery_validation_and_rankings():
    v=research_cycle.normalise_discovery(sample_discovery())
    assert len(v['theories'])==2
    assert v['leading_direction']=='Bearish'
    assert v['status']=='AI-proposed / unverified'
    r=research_cycle.initial_horse_race(v)
    assert r[0]['id']=='theory-1' and len(r)==2
    rev=research_cycle.revise_horse_race(v,{'theory_rankings':[
        {'id':'theory-2','status':'price-context supports','why_ranked':'Independent market responses deserve checking.'},
        {'id':'unknown','status':'proven','why_ranked':'invented'}]})
    assert [x['id'] for x in rev]==['theory-2','theory-1']
    assert rev[0]['status']=='price-context supports'
    assert all('probability' not in x for x in rev)


def test_research_cycle_seeds_ai_bias_without_marking_verified(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'studio.db')
    server.initialize()
    monkeypatch.setattr(server.cloud_ai,'configured',lambda: True)
    monkeypatch.setattr(server.cloud_ai,'infer_json',lambda *_: sample_discovery())
    with TestClient(server.app) as client:
        resp=client.post('/api/council/plan',json={'question':'Could insurance and collateral force counterintuitive gold behaviour?',
             'focus':'OANDA:XAUUSD','horizon':'swing','ai_refine':True,'discover_news':False})
        assert resp.status_code==200,resp.text
        result=resp.json()
        assert result['plan']['research_cycle']['leading_direction']=='Bearish'
        assert 'OANDA:WTICOUSD' in [x['symbol'] for x in result['plan']['requests']]
        bias=result['assessment']['fundamental_bias']
        assert bias['direction']=='Bearish'
        assert bias['basis']=='ai-hypothesis' and bias['state']=='provisional-ai'
        # No chart data: research still has a directional but explicitly unverified working state.
        run=client.post('/api/council/run',json={'ai_synthesis':False})
        assert run.status_code==200
        report=run.json()['report']
        assert report['status']=='incomplete-data'
        assert report['fundamental_bias']['direction']=='Bearish'
        assert len(report['theory_horse_race'])==2
        assert report['fundamental_bias']['state']=='provisional-held'
        # Repeating the exact same analysis cannot magically manufacture macro evidence.
        again=client.post('/api/council/run',json={'ai_synthesis':False}).json()['report']
        assert again['fundamental_bias']['new_evidence_count']==0


def test_research_cycle_does_not_overwrite_existing_held_bias(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'held.db')
    server.initialize()
    monkeypatch.setattr(server.cloud_ai,'configured',lambda: True)
    monkeypatch.setattr(server.cloud_ai,'infer_json',lambda *_: sample_discovery('Bearish'))
    with TestClient(server.app) as client:
        client.post('/api/council/plan',json={'question':'Does insurance market stress create a gold impact?',
            'ai_refine':False,'discover_news':False})
        adopted=client.post('/api/council/bias/adopt',json={'direction':'Bullish',
            'rationale':'User scenario: physical gold replacement demand dominates funding costs.'})
        assert adopted.status_code==200
        resp=client.post('/api/council/plan',json={'question':'What if insurance links favor bearish gold outcomes instead?',
            'ai_refine':True,'discover_news':False})
        assert resp.status_code==200,resp.text
        data=resp.json()
        assert data['plan']['research_cycle']['leading_direction']=='Bearish'
        assert data['assessment']['fundamental_bias']['direction']=='Bullish'
        assert data['assessment']['fundamental_bias']['basis']=='user-hypothesis'


def test_targeted_news_is_metadata_only_and_nonfatal(tmp_path,monkeypatch):
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'scan.db')
    server.initialize()
    monkeypatch.setattr(server,'search_on_demand',lambda *_: {'new':1,'results':[{'title':'Marine cargo risk commentary',
        'url':'https://example.org/report', 'time':'2026-11-21T12:00:00Z', 'source_kind':'search_headline'}]})
    with TestClient(server.app) as client:
        p=client.post('/api/council/plan',json={'question':'Can an insurance shock affect gold and US Treasury yields?',
            'discover_news':True,'ai_refine':False})
        assert p.status_code==200,p.text
        d=p.json()['plan']['discovery_scan']
        assert d['status']=='scanned' and d['sources'][0]['quality'].startswith('headline-only')
        r=client.post('/api/council/run',json={'refresh_evidence':True,'ai_synthesis':False})
        assert r.status_code==200
        assert r.json()['report']['discovery_scan']['status']=='scanned'


def test_source_capture_rejects_unsafe_links_and_duplicates():
    x=research_cycle.capture_headlines([
        {'title':'Same headline','url':'javascript:alert(1)'},
        {'title':'Same headline','url':'https://example.org/copy'},
        {'title':'Other headline','url':'https://example.org/a','time':'2026-11-22'},
    ])
    assert len(x)==2 and x[0]['url']==''


def test_ai_synthesis_can_rerank_rivals_without_switching_held_bias(tmp_path,monkeypatch):
    from datetime import timedelta
    import csv,io
    monkeypatch.setattr(server,'DB_PATH',tmp_path/'synthesis.db')
    server.initialize()
    monkeypatch.setattr(server.cloud_ai,'configured',lambda: True)
    def infer(system,payload):
        if 'theory_rankings' in system:
            return {'synthesis':'Price co-moves but insurance documentation remains absent.',
                'leading_scenario':'Bullish gold under collateral scarcity remains speculative.',
                'causal_chains':['Funding conditions to collateral demand to price'],
                'counterarguments':['Short-rate pressure could dominate'],
                'missing_evidence':['Dated bullion deliveries'],
                'invalidations':['No documented shortfall'],
                'uncertainty':'No observed physical flows.',
                'theory_rankings':[{'id':'theory-2','status':'price-context supports',
                    'why_ranked':'Observed risk proxies warrant checking collateral prices.'},
                  {'id':'theory-1','status':'price-context challenges',
                    'why_ranked':'Energy and dollar signals conflict with the timing.'}]}
        return sample_discovery('Bearish')
    monkeypatch.setattr(server.cloud_ai,'infer_json',infer)
    with TestClient(server.app) as client:
        resp=client.post('/api/council/plan',json={'question':'Could insurance and collateral effects offset gold rates?',
            'focus':'OANDA:XAUUSD','horizon':'intraday','ai_refine':True})
        assert resp.status_code==200,resp.text
        plan=resp.json()['plan']
        now=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
        for req in plan['requests']:
            if req['priority']!='required':continue
            out=io.StringIO();w=csv.writer(out);w.writerow(['time','open','high','low','close'])
            for i in range(101):
                price=100+i*0.15
                w.writerow([(now-timedelta(hours=101-i)).isoformat(),price,price+1,price-1,price])
            r=client.post('/api/chart/import',params={'symbol':req['symbol'],'interval':req['interval']},
                content=out.getvalue().encode(),headers={'Content-Type':'text/csv','X-Filename':'chart.csv'})
            assert r.status_code==200,r.text
        run=client.post('/api/council/run',json={'ai_synthesis':True})
        assert run.status_code==200,run.text
        result=run.json()['report']
        assert result['status']=='ready-for-synthesis',result['blocking']
        assert result['theory_horse_race'][0]['id']=='theory-2'
        assert result['fundamental_bias']['direction']=='Bearish'
        assert result['fundamental_bias']['basis']=='ai-hypothesis'