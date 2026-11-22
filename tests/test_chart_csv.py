"""User-supplied TradingView-style CSV: local import and research integration."""
from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as module
import market_csv

@pytest.fixture(autouse=True)
def temp_database(monkeypatch,tmp_path):
    monkeypatch.setattr(module,'DB_PATH',tmp_path/'narrative.db')
    monkeypatch.setenv('DISABLE_POLLING','1')
    monkeypatch.delenv('ENABLE_REMOTE_MARKET',raising=False)
    module.initialize()

@pytest.fixture
def client():return TestClient(module.app)

def file_data(end=1700000900):
    return ("time,open,high,low,close,Volume,My RSI\n"
            "1700000000,1990,2010,1980,2000,100,51\n"
            f"{end},2000,2030,1995,2020,140,56\n").encode()

def test_parse_tradingview_unix_csv_indicators():
    data=market_csv.read_ohlcv_csv(file_data(),'OANDA:XAUUSD','15m')
    assert data['bars']==2
    assert data['latest_close']==2020
    assert data['one_bar_percent']==1
    assert data['indicators']['My RSI']==56
    assert data['last_time'].endswith('Z')
    assert len(market_csv.public_view(data)['chart'])==2

def test_upload_csv_persists_with_no_market_data_api(client):
    resp=client.post('/api/chart/import?symbol=OANDA:XAUUSD&interval=15m',content=file_data(),
                     headers={'Content-Type':'text/csv','X-Filename':'OANDA_XAUUSD.csv'})
    assert resp.status_code==200,resp.text
    data=resp.json()
    assert data['one_bar_percent']==1
    assert data['bars']==2
    page=client.get('/api/bootstrap?mode=live').json()
    assert page['chart_imports'][0]['symbol']=='OANDA:XAUUSD'
    assert page['market']['gold']['value']==2020
    assert page['market']['gold']['manual_csv'] is True
    assert page['state']['totals']=={'rates':0,'haven':0,'growth':0}
    assert page['events']==[]
    assert len(module.chart_context_for_ai())==1
    assert 'chart' not in module.chart_context_for_ai()[0]

def test_repeated_exact_file_and_older_file_rejected(client):
    url='/api/chart/import?symbol=OANDA:XAUUSD&interval=15m'
    a=client.post(url,content=file_data())
    assert a.status_code==200
    assert client.post(url,content=file_data()).status_code==409
    assert client.post(url,content=file_data(1699999999)).status_code in (409,422)

def test_other_ticker_does_not_disguise_nominal_yield_as_real(client):
    c=client.post('/api/chart/import?symbol=TVC:US10Y&interval=15m',content=file_data())
    assert c.status_code==200
    assert 'real_yield' not in client.get('/api/bootstrap?mode=live').json()['market']
    assert client.get('/api/bootstrap?mode=live').json()['chart_imports'][0]['symbol']=='TVC:US10Y'

def test_bad_ohlc_and_missing_headers_rejected(client):
    url='/api/chart/import?symbol=OANDA:XAUUSD&interval=15m'
    assert client.post(url,content=b'time,open,high,low,close\n1700000000,1,1,1,1\n1700000900,2,1,2,2\n').status_code==422
    assert client.post(url,content=b'time,close\n1700000000,2000\n1700000900,2002\n').status_code==422
    assert client.post(url,content=b'').status_code==422


def test_newer_chart_replaces_snapshots_and_dedupes(client):
    url='/api/chart/import?symbol=OANDA:XAUUSD&interval=15m'
    assert client.post(url,content=file_data()).status_code==200
    for n in [1700001800,1700002700,1700003600]:
        assert client.post(url,content=file_data(n)).status_code==200
    rows=client.get('/api/chart/imports').json()['charts']
    assert len(rows)==1 and rows[0]['last_time']==market_csv.parse_time('1700003600')
    with module.conn() as c:assert c.execute('select count(*) from chart_imports').fetchone()[0]==3


def test_daily_web_scan_skips_market_calls_by_default(monkeypatch):
    # This test requires no network. A failed news scan must not call prices.
    monkeypatch.setattr(module,'refresh_bls',lambda:{'new':0})
    monkeypatch.setattr(module.web_scan,'search_news',lambda fetch:([],{}))
    monkeypatch.setattr(module.web_scan,'get_stooq_market',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('no remote price API')))
    monkeypatch.setattr(module.web_scan,'get_treasury_real',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('no real-yield request')))
    results=module.refresh_free_web()
    assert set(results)=={'bls','web_news'}