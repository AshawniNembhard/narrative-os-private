"""Bias persistence / hysteresis tests: no live data or AI connection."""
from datetime import datetime,timedelta,timezone
import bias_engine as b

NOW=datetime.now(timezone.utc).replace(microsecond=0)

def ts(delta=0):return (NOW+timedelta(hours=delta)).isoformat()

def report(bull=2.,bear=0.,proxy_bull=2.,proxy_bear=0.,proxy_count=2,ready=True):
    return {'status':'ready-for-synthesis' if ready else 'incomplete-data',
        'price_support':{'Bullish':bull,'Bearish':bear,'proxy_bullish':proxy_bull,
            'proxy_bearish':proxy_bear,'proxy_count':proxy_count}}

def official(id, direction='Bullish',type='licensed_calendar_release', hours=0):
    impacts={'rates':-2,'haven':1,'growth':0} if direction=='Bullish' else {'rates':2,'haven':-1,'growth':-1}
    return {'id':id,'type':'macro','time':ts(hours),'title':'Economic release '+id,
       'source_kind':type,'actual':3.5,'consensus':3.0,'impacts':impacts,
       'score':{'method':'rules','reliability':{'value':4},'significance':{'value':4},'novelty':{'value':4}}}

def treasury(id='real',direction='Bearish'):
    return {'id':id,'type':'market','time':ts(), 'title':'Real yields measured '+id,
       'source_kind':'official_daily_treasury',
       'impacts':{'rates':1 if direction=='Bearish' else -1},
       'score':{'method':'rules','reliability':{'value':5},'significance':{'value':4},'novelty':{'value':4}}}

def test_no_default_flat_or_unverified_macro_from_target_candles():
    first=b.evaluate(report(bull=4.,proxy_bull=0.,proxy_count=0),[],now=NOW)
    assert first['direction']=='Unestablished'
    assert first['price_context']['direction']=='Bullish'
    assert 'price candles alone' in ' '.join(first['switch_requirements'])

def test_provisional_crossmarket_bias_held_despite_one_minute_reversal():
    first=b.evaluate(report(),[],now=NOW)
    assert first['direction']=='Bullish' and first['basis']=='cross-market-inference'
    opposite=report(bull=0.,bear=5.,proxy_bull=0.,proxy_bear=3.)
    second=b.evaluate(opposite,[],first,now=NOW+timedelta(minutes=2))
    assert second['direction']=='Bullish'
    assert second['market_divergence']
    assert second['state']=='provisional-held'


def test_verified_macro_thesis_held_challenged_then_switched():
    e1=official('initial','Bullish')
    first=b.evaluate(report(),[e1],now=NOW)
    assert first['basis']=='macro-evidence' and first['direction']=='Bullish'
    assert first['state']=='established'
    # Bearish price by itself is not a regime change.
    second=b.evaluate(report(bull=0.,bear=4.,proxy_bull=0.,proxy_bear=3.),[e1],first,now=NOW+timedelta(minutes=1))
    assert second['direction']=='Bullish' and second['state']=='retained'
    # One powerful *new* release does not automatically overturn a thesis.
    e2=official('challenger','Bearish')
    challenged=b.evaluate(report(),[e1,e2],second,now=NOW+timedelta(minutes=2))
    assert challenged['direction']=='Bullish' and challenged['state']=='challenged'
    assert challenged['challenger_points']>2
    repeat=b.evaluate(report(),[e1,e2],challenged,now=NOW+timedelta(minutes=3))
    assert repeat['direction']=='Bullish' and repeat['new_evidence_count']==0
    # Independent *real-yield* evidence is new support for the challenger.
    e3=treasury()
    switched=b.evaluate(report(),[e1,e2,e3],repeat,now=NOW+timedelta(minutes=4))
    assert switched['direction']=='Bearish' and switched['state']=='switched'
    assert switched['switched'] is True
    again=b.evaluate(report(),[e1,e2,e3],switched,now=NOW+timedelta(minutes=5))
    assert again['direction']=='Bearish' and again['new_evidence_count']==0


def test_macro_evidence_supersedes_provisional_price_case():
    first=b.evaluate(report(),[],now=NOW)
    new=b.evaluate(report(),[official('first','Bearish')],first,now=NOW+timedelta(minutes=1))
    assert new['direction']=='Bearish'
    assert new['basis']=='macro-evidence'
    assert new['switched'] is True


def test_no_price_or_event_translated_into_other_ticker_gold_bias():
    first=b.evaluate(report(),[official('first','Bullish')],focus='OANDA:GBPJPY',now=NOW)
    assert first['direction']=='Unestablished'


def test_missing_csv_doesnt_erase_established_macro_bias():
    first=b.evaluate(report(),[official('first','Bullish')],now=NOW)
    second=b.evaluate(report(ready=False),[official('first','Bullish')],first,now=NOW+timedelta(minutes=3))
    assert second['direction']=='Bullish' and second['state']=='retained'


def test_bias_age_becomes_review_due_without_direction_switch():
    e=official('first','Bullish')
    first=b.evaluate(report(),[e],now=NOW)
    later=b.evaluate(report(),[e],first,now=NOW+timedelta(days=4))
    assert later['direction']=='Bullish' and later['state']=='review-due'
    assert 'refresh' in later['reason']


def test_old_evidence_cannot_set_fresh_bias():
    old=official('old','Bullish',hours=-24*50)
    first=b.evaluate(report(bull=0,bear=0,proxy_bull=0,proxy_bear=0,proxy_count=0),[old],now=NOW)
    assert first['direction']=='Unestablished'


def test_headline_impacts_cannot_open_or_flip_bias():
    headline=official('unverified','Bullish',type='search_headline')
    first=b.evaluate(report(bull=0,bear=0,proxy_bull=0,proxy_bear=0,proxy_count=0),[headline],now=NOW)
    assert first['direction']=='Unestablished'