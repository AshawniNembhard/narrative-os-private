"""No network, broker, login, or live data required for these tests."""
import csv
import io
import math
from datetime import datetime,timedelta,timezone
import pytest
import interdisciplinary as mod
import market_csv

NOW=datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)

def chart(symbol, interval='1h', n=120, offset=0, drift=.002, start=None):
    start=start or NOW-timedelta(hours=n+offset)
    rows=[]
    for k in range(n):
        v=100*math.exp((k*drift)+0.006*math.sin(k/7))
        timestamp=start+timedelta(hours=k+offset)
        rows.append([timestamp.isoformat(),v,v*1.002,v*.998,v])
    buffer=io.StringIO();w=csv.writer(buffer);w.writerow(['time','open','high','low','close']);w.writerows(rows)
    return market_csv.read_ohlcv_csv(buffer.getvalue().encode(),symbol,interval)

def test_freight_selects_oil_and_dollar():
    p=mod.plan('Can rising marine insurance and shipping disruption change oil inflation pressure and gold?',horizon='intraday')
    syms=[r['symbol'] for r in p['requests']]
    assert 'OANDA:XAUUSD' in syms and 'OANDA:WTICOUSD' in syms and 'TVC:DXY' in syms
    assert any('premiums' in r['needed'] for r in p['external_checks'])
    assert len(syms)<=7

def test_gold_physical_requires_external_evidence():
    p=mod.plan('Could a bullion collateral and refinery gold shortage force external purchases of metal?')
    assert any('fine-troy-ounce' in x['needed'].lower() for x in p['external_checks'])
    assert 'COMEX:GC1!' in [r['symbol'] for r in p['requests']]

def test_no_data_is_incomplete_and_no_fabricated_prediction():
    p=mod.plan('Could freight inflation disrupt gold expectations?')
    a=mod.analyse(p,[],now=NOW)
    assert a['status']=='incomplete-data' and a['blocking']
    assert a['leading_observation'].startswith('Undetermined')

def test_market_data_complete_only_with_overlapping_required_bars():
    p=mod.plan('Can shipping insurance change rates and gold via oil?',horizon='intraday')
    required=[r for r in p['requests'] if r['priority']=='required']
    charts=[chart(r['symbol'],r['interval']) for r in required]
    a=mod.analyse(p,charts,now=NOW)
    assert a['status']=='ready-for-synthesis',a['blocking']
    assert len([x for x in a['tested_pairs'] if x.get('status')=='observed'])>=2
    assert all(x['sample']>=30 for x in a['tested_pairs'] if x.get('status')=='observed')
    assert 'not causal proof' in ' '.join(a['limitations'])

def test_missing_overlap_blocks_completed_analysis():
    p=mod.plan('Can shipping insurance change rates and gold via oil?',horizon='intraday')
    required=[r for r in p['requests'] if r['priority']=='required']
    charts=[chart(required[0]['symbol'],required[0]['interval'])]
    charts += [chart(r['symbol'],r['interval'],start=NOW-timedelta(hours=290)) for r in required[1:]]
    a=mod.analyse(p,charts,now=NOW)
    assert a['status']=='incomplete-data'
    assert any('overlapping' in b or 'stale' in b for b in a['blocking'])

def test_ai_refinement_rejects_unknown_assets():
    p=mod.plan('Does shipping freight inflation cause gold market changes?')
    pp=mod.refine_plan(p,{'selected_keys':['oil','dxy','invented_thing'],'rationale':'Oil and FX pathways'})
    assert all(x['key']!='invented_thing' for x in pp['requests'])
    assert pp['method'].startswith('AI-guided')
    with pytest.raises(ValueError):mod.refine_plan(p,{'selected_keys':['unknown']})

@pytest.mark.parametrize('question', ['', 'short', '  '])
def test_bad_questions_rejected(question):
    with pytest.raises(ValueError):mod.plan(question)