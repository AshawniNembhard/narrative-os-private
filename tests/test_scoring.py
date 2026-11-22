"""Scoring safeguards: every discovered item receives a visible *explanation*.

Tests deliberately prevent unverified search-indexed headlines from causing
AI-derived directional narrative balances.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as module
import scoring
import chatgpt_auth

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'DB_PATH',tmp_path/'scores.db')
    monkeypatch.setenv('DISABLE_POLLING','1')
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    module.initialize()


def fake_headline(title='Gold rallies as inflation concerns grow'):
    return {'id':'web-news-test','time':'2026-11-16T08:00:00Z','type':'news','title':title,
            'detail':'Google News headline only, original article not reviewed.',
            'source_kind':'search_headline','source':'https://news.google.com/rss/articles/example',
            'publisher':'Unverified outlet'}


def test_headline_ratings_present_but_direction_stays_neutral():
    e=module.mk_web_event(fake_headline('Fed signals rate hike amid gold rally'))
    assert module.add_live(e)==1
    saved=TestClient(module.app).get('/api/bootstrap?mode=live').json()
    event=saved['events'][0]
    assert all(0<=event['score'][k]['value']<=5 for k in
            ('reliability','novelty','significance','unconventional'))
    assert event['score']['method']=='rules'
    assert event['impacts']=={'rates':0,'haven':0,'growth':0}
    assert saved['state']['totals']==event['impacts']
    assert 'headline' in event['score']['impact_reason'].lower()
    assert module.add_live(module.mk_web_event(fake_headline()))==0


def test_treasury_numeric_change_provisionally_scores_rates():
    e={'id':'treasury-10y-real-2026-11-16','time':'2026-11-16T23:59:00Z',
       'type':'market','title':'10-year TIPS real yield',
       'detail':'Treasury published daily 10 year real yield.',
       'source_kind':'official_daily_treasury','market_key':'real_yield',
       'observation_date':'2026-11-16','value':1.95,'previous':1.87,'change_pp':0.08}
    module.add_live(module.mk_web_event(e))
    r=TestClient(module.app).get('/api/bootstrap?mode=live').json()
    item=r['events'][0]
    assert item['score']['reliability']['value']==5
    assert item['impacts']=={'rates':1,'haven':0,'growth':0}
    assert r['state']['totals']['rates']==1


def test_repeat_headline_lower_novelty_even_different_url():
    first=fake_headline('Shipping insurance surges after tanker disruption in Middle East')
    second={**first,'id':'web-news-two','source':'https://news.google.com/rss/articles/second'}
    module.add_live(module.mk_web_event(first))
    module.add_live(module.mk_web_event(second))
    rows=TestClient(module.app).get('/api/bootstrap?mode=live').json()['events']
    assert [e['score']['novelty']['value'] for e in rows]==[4,1]
    assert rows[0]['score']['unconventional']['value']>=3
    assert rows[1]['impacts']=={'rates':0,'haven':0,'growth':0}


def test_release_surprise_is_structured_not_assumed_from_words():
    item={'id':'te-cpi-test','time':'2026-11-16T13:30:00Z','type':'macro',
          'title':'Core CPI YoY', 'detail':'Actual 3.4%; consensus 3.1%',
          'actual':'3.4%','consensus':'3.1%','source_kind':'licensed_calendar_release'}
    module.add_live(module.mk_web_event(item))
    live=TestClient(module.app).get('/api/bootstrap?mode=live').json()
    assert live['events'][0]['impacts']=={'rates':1,'haven':0,'growth':-1}
    assert live['events'][0]['score']['impact_confidence']=='moderate'


def test_ai_ratings_cannot_upgrade_unsupported_headlines():
    event=fake_headline()
    event.update(scoring.auto_score(event))
    ai={'reliability':{'value':5,'reason':'This headline sounds famous'},
        'novelty':{'value':4,'reason':'New words'},'significance':{'value':5,'reason':'Markets'},
        'unconventional':{'value':4,'reason':'May alter oil demand'},
        'impacts':{'rates':2,'haven':2,'growth':-2},'impact_reason':'Buy gold now'}
    amended=scoring.combine_ai(event,ai)
    assert amended['score']['method']=='ai'
    assert amended['score']['reliability']['value']==2
    assert amended['impacts']=={'rates':0,'haven':0,'growth':0}
    assert 'neutral' in amended['score']['impact_reason'].lower()


def test_optional_ai_updates_both_qualitative_and_numeric(monkeypatch):
    monkeypatch.setattr(chatgpt_auth,'status',lambda:{'sharing':True,'connected':True})
    captured={}
    def pretend_ai(instructions,payload):
        captured['instruction']=instructions
        assert payload['event']['source_kind']=='search_headline'
        d={k:'Measured hypothesis: '+k for k in
            ('retail','professional','unconventional','falsifier','horizon')}
        d.update({k:{'value':4,'reason':'Mock rating based on supplied metadata'} for k in
                  ('reliability','novelty','significance')})
        d['unconventional_score']={'value':5,'reason':'Shipping could matter'}
        d['impacts']={'rates':2,'haven':2,'growth':-2}
        d['impact_reason']='News appears to indicate risk'
        return d
    monkeypatch.setattr(chatgpt_auth,'infer_json',pretend_ai)
    module.add_live(module.mk_web_event(fake_headline()))
    c=TestClient(module.app)
    result=c.post('/api/ai/analyse',json={'id':'web-news-test'})
    assert result.status_code==200,result.text
    assert 'reliability' in captured['instruction']
    assert result.json()['score']['method']=='ai'
    assert result.json()['impacts']=={'rates':0,'haven':0,'growth':0}
    assert c.get('/api/bootstrap?mode=live').json()['events'][0]['score']['method']=='ai'


def test_manual_score_automatic_and_optional_override():
    c=TestClient(module.app)
    manual={'title':'Energy vessel premiums increase', 'detail':'Unverified insurance anecdote; possible effects on inflation',
            'category':'logistics'}
    first=c.post('/api/events',json=manual).json()
    assert first['score']['method']=='rules'
    assert first['impacts']=={'rates':0,'haven':0,'growth':0}
    assert first['score']['unconventional']['value']>=3
    second=c.post('/api/events',json={**manual,'impacts':{'rates':1,'haven':0,'growth':0}}).json()
    assert second['score']['method']=='manual'
    assert second['impacts']['rates']==1


def test_legacy_event_backfill_preserves_existing_impacts():
    event=module.mk_web_event(fake_headline('Inflation outlook changes'))
    event['impacts']={'rates':0,'haven':0,'growth':0}
    with module.conn() as c:module.save_event(c,event,'live')
    module.initialize()
    r=TestClient(module.app).get('/api/bootstrap?mode=live').json()
    assert r['events'][0]['score']['method']=='rules'