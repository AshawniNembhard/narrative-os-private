import os
import sys
import datetime as dt
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as module
import web_scan
import chatgpt_auth

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'DB_PATH',tmp_path/'db.sqlite')
    monkeypatch.setenv('NARRATIVE_AUTH_DIR',str(tmp_path/'credentials'))
    monkeypatch.setenv('DISABLE_POLLING','1')
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('ENABLE_REMOTE_MARKET','1')
    # Freeze clock for historical, deliberately dated fixture data.
    original_news,original_custom=web_scan.search_news,web_scan.search_custom
    original_price,original_treasury=web_scan.get_stooq_market,web_scan.get_treasury_real
    def fixed(fn):
        def wrap(*args,**kwargs):
            kwargs.setdefault('now',NOW)
            return fn(*args,**kwargs)
        return wrap
    monkeypatch.setattr(web_scan,'search_news',fixed(original_news))
    monkeypatch.setattr(web_scan,'search_custom',fixed(original_custom))
    monkeypatch.setattr(web_scan,'get_stooq_market',fixed(original_price))
    monkeypatch.setattr(web_scan,'get_treasury_real',fixed(original_treasury))
    module.initialize()

NOW=dt.datetime(2026,11,16,12,tzinfo=dt.timezone.utc)
RSS=b'''<?xml version="1.0"?><rss><channel><item><title>New inflation forecast - Example</title><link>https://news.google.com/rss/articles/abc</link><pubDate>Fri, 13 Nov 2026 09:00:00 GMT</pubDate><source url="https://example.com">Example</source></item></channel></rss>'''
REAL=b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"><entry><content><m:properties><d:NEW_DATE>2026-11-12T00:00:00</d:NEW_DATE><d:TC_10YEAR>1.90</d:TC_10YEAR></m:properties></content></entry><entry><content><m:properties><d:NEW_DATE>2026-11-13T00:00:00</d:NEW_DATE><d:TC_10YEAR>1.98</d:TC_10YEAR></m:properties></content></entry></feed>'''
GOLD=b'Date,Open,High,Low,Close,Volume\n2026-11-12,4100,4200,4000,4150,\n2026-11-13,4150,4300,4100,4250,\n'
DOLLAR=b'Date,Open,High,Low,Close,Volume\n2026-11-12,100,101,99,100.2,\n2026-11-13,100,102,99,101.3,\n'

def fake_fetch(url):
    if 'news.google.com' in url:return RSS
    if 'daily_treasury_real_yield_curve' in url:return REAL
    if 'stooq.com' in url:return GOLD if 'xauusd' in url else DOLLAR
    if 'bls.gov' in url:return b'<rss><channel></channel></rss>'
    raise RuntimeError('Unknown URL '+url)

def test_public_scanner_parsing():
    headlines,errors=web_scan.search_news(fake_fetch,now=NOW)
    assert len(headlines)==1 and not errors
    assert headlines[0]['market_verified'] is False
    assert headlines[0]['time']=='2026-11-13T09:00:00Z'
    assert headlines[0]['source'].startswith('https://news.google.com')
    gold=web_scan.get_stooq_market(fake_fetch,'xauusd','Gold','USD',now=NOW)
    assert gold['value']==4250
    assert gold['change_percent']==round(100*(4250/4150-1),4)
    assert 'NOT a live' in gold['detail']
    dollar=web_scan.get_stooq_market(fake_fetch,'dx.f','Dollar futures','points',proxy=True,now=NOW)
    assert dollar['proxy'] and dollar['value']==101.3
    tips=web_scan.get_treasury_real(fake_fetch,now=NOW)
    assert tips['value']==1.98 and tips['observation_date']=='2026-11-13'
    assert tips['change_pp']==0.08

def test_web_scan_api_source_status_and_dedupe(monkeypatch):
    monkeypatch.setattr(module,'fetch',fake_fetch)
    c=TestClient(module.app)
    r=c.post('/api/live/refresh')
    assert r.status_code==200,r.text
    data=r.json()
    assert data['gold']['new']==1 and data['dollar']['new']==1
    assert data['real_yield']['new']==1 and data['web_news']['new']==1
    assert c.post('/api/live/refresh').json()['gold']['new']==0
    status=c.get('/api/status').json()
    assert all(x['enabled'] for x in status['feeds'] if x['key']!='openai')
    live=c.get('/api/bootstrap?mode=live').json()
    assert len(live['events'])==4
    assert live['market']['gold']['value']==4250
    assert live['market']['real_yield']['value']==1.98

def test_custom_query_search_and_no_account_ai(monkeypatch):
    monkeypatch.setattr(module,'fetch',fake_fetch)
    c=TestClient(module.app)
    r=c.post('/api/live/search',json={'question':'gold and real yields'})
    assert r.status_code==200
    assert r.json()['new']==1
    r=c.post('/api/ai/research',json={'question':'gold and real yields'})
    assert r.status_code==409

def test_oauth_start_and_callback_guardrails(monkeypatch,tmp_path):
    start=chatgpt_auth.start(8000)
    from urllib.parse import urlsplit,parse_qs
    query=parse_qs(urlsplit(start['url']).query)
    assert query['client_id']==['dynamic_agent_client']
    assert query['code_challenge_method']==['S256']
    assert query['redirect_uri']==['http://127.0.0.1:8000/auth/callback']
    assert 'access_token' not in start
    with pytest.raises(ValueError,match='state'):
        chatgpt_auth.complete('wrong-state','CODE','oaiapp_test')
    with pytest.raises(ValueError,match='not approved'):
        chatgpt_auth.complete(query['state'][0],'','','access_denied')
    assert not chatgpt_auth.status()['connected']

def test_no_ai_background_without_permission(monkeypatch):
    monkeypatch.setattr(chatgpt_auth,'status',lambda:{'sharing':True,'connected':True})
    c=TestClient(module.app)
    assert c.get('/api/auth/status').json()['automatic_ai'] is False
    assert module.auto_analyse()['disabled']
    response=c.post('/api/ai/automatic',json={'enabled':True})
    assert response.status_code==200 and response.json()['automatic_ai']
    assert c.post('/api/ai/automatic',json={'enabled':False}).json()['automatic_ai'] is False

def test_parse_guard_when_source_is_html_or_missing_value():
    with pytest.raises(ValueError,match='dated CSV'):web_scan._price_rows(b'<html>rate limited</html>')
    with pytest.raises(ValueError,match='10-year'):web_scan.get_treasury_real(lambda url:b'<feed/>',now=NOW)

def test_custom_research_returns_separate_views_with_mock_ai(monkeypatch):
    monkeypatch.setattr(module,'fetch',fake_fetch)
    monkeypatch.setattr(chatgpt_auth,'status',lambda:{'sharing':True,'connected':True})
    observed={}
    def pretend_ai(instructions,payload):
        observed['question']=payload['question']
        observed['sources']=payload['search_headlines']
        observed['market']=payload['market_observations']
        return {x:f'Grounded hypothesis: {x}' for x in
                ('answer','retail','professional','unconventional','contradictions','next_checks','uncertainty')}
    monkeypatch.setattr(chatgpt_auth,'infer_json',pretend_ai)
    c=TestClient(module.app)
    c.post('/api/live/refresh')
    response=c.post('/api/ai/research',json={'question':'Does a rise in real yields challenge gold?'})
    assert response.status_code==200,response.text
    assert observed['question'].startswith('Does a rise')
    assert observed['sources'][0]['source_kind']=='search_headline'
    assert set(m['market_key'] for m in observed['market'])=={'gold','dollar','real_yield'}
    assert len(response.json()['analysis'])==7
    assert not any('access_token' in x for x in response.json())