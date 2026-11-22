import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as module

@pytest.fixture(autouse=True)
def temp_database(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'DB_PATH',tmp_path/'test.sqlite3')
    module.initialize()

@pytest.fixture
def client():
    return TestClient(module.app)

def test_demo_progression_and_replay_state(client):
    a=client.get('/api/bootstrap?mode=demo').json()
    assert len(a['events'])==3
    assert a['state']['totals']=={'rates':3,'haven':3,'growth':-1}
    r=client.post('/api/demo/next').json()
    assert r['added']=='demo-4'
    b=client.get('/api/bootstrap?mode=demo').json()
    assert len(b['events'])==4
    assert b['state']['totals']=={'rates':1,'haven':4,'growth':-1}
    assert client.post('/api/demo/reset').status_code==200
    assert len(client.get('/api/bootstrap?mode=demo').json()['events'])==3

def test_manual_evidence_in_live_overlay(client):
    data={'title':'Freight route marine insurance rises','detail':'Source reported shipping costs up; economic impact unverified.',
          'category':'logistics','impacts':{'rates':0,'haven':2,'growth':-1}}
    r=client.post('/api/events',json=data)
    assert r.status_code==200,r.text
    assert r.json()['retail'].startswith('This logistics')
    research=client.get('/api/bootstrap?mode=manual').json()
    live=client.get('/api/bootstrap?mode=live').json()
    assert len(research['events'])==1
    assert live['events'][0]['id']==research['events'][0]['id']
    assert live['state']['totals']=={'rates':0,'haven':2,'growth':-1}

def test_bad_urls_and_invalid_requests(client):
    bad=client.post('/api/events',json={'title':'Event name','detail':'Long description here','source_url':'javascript:alert(1)'})
    assert bad.status_code==400
    assert client.get('/api/bootstrap?mode=other').status_code==422

@pytest.mark.parametrize('actual,forecast,name,result',[
    ('3.4%','3.1%','Core CPI YoY',{'rates':1,'growth':-1}),
    ('175K','200K','Non Farm Payrolls',{'rates':-1,'growth':1}),
    ('5.2%','4.9%','Unemployment Rate',{'growth':1,'rates':-1}),
    ('1.8%','1.8%','Core CPI',{}),
    ('3.2%','130K','Core CPI',{}),
    ('tbc','3.1%','Core CPI',{}),
    ('150K','140K','Coal output',{}),
])
def test_macro_rules(actual,forecast,name,result):
    impacts,_=module.provisional_release_assessment(name,actual,forecast)
    assert impacts==result

def test_optional_ai_unconfigured(client,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    assert client.post('/api/ai/analyse',json={'id':'demo-1'}).status_code==409