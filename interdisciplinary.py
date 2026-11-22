"""On-demand, evidence-first, multi-instrument research.

The planner nominates testable chart combinations. User uploads CSVs, then
analyzes aligned returns; this never scrapes TradingView or infers causation
from a correlation. Trading plans are user-guided research artifacts, not orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import math
import re
import statistics

UTC=timezone.utc

CATALOG={
 'gold':('OANDA:XAUUSD','Gold spot','Outcome asset and benchmark'),
 'dxy':('TVC:DXY','US dollar index','FX translation and dollar-funding channel'),
 'real':('FRED:DFII10','10-year US TIPS real yield','Daily real-yield level; not a live intraday proxy'),
 'nominal':('TVC:US10Y','10-year US Treasury yield','Intraday nominal-yield proxy, NOT a real yield'),
 'oil':('OANDA:WTICOUSD','WTI crude oil','Energy inflation and supply-disruption transmission'),
 'equities':('SP:SPX','S&P 500 index','Broad risk appetite and growth-sentiment proxy'),
 'copper':('COMEX:HG1!','Copper futures (continuous)','Industrial demand / global growth proxy; rollover caution'),
 'etf':('AMEX:GLD','Gold ETF market price','Exchange-traded gold price proxy; NOT ETF creations or flows'),
 'futures':('COMEX:GC1!','Gold futures (continuous)','Gold futures-versus-spot relationship; rollover caution'),
 'credit':('AMEX:HYG','High-yield bond ETF price','Risk/credit proxy; NOT an actual credit-spread series'),
 'gbpjpy':('OANDA:GBPJPY','GBP/JPY','FX cross-asset response for sterling and yen'),
}
MECHANISMS={
 'freight':{'name':'Shipping/insurance → energy → inflation/rates → gold','words':r'freight|marine|shipping|insur|suez|red sea|tanker|port|cargo|strait|shipping route|logistic',
            'assets':['oil','dxy','nominal'],'evidence':'Dated freight/insurance premiums and actual cargo flow or route disruption evidence',
            'falsifier':'Shipping disruption does not affect delivered energy prices or policy expectations'},
 'rates':{'name':'Rate repricing → real yields/dollar → gold','words':r'fed|fomc|cpi|inflation|yield|rates?|treasur|bond|auction|duration|tips|dollar|dxy|powell',
          'assets':['dxy','nominal','real'],'evidence':'Actual-versus-consensus macro releases and rate/real-yield repricing',
          'falsifier':'Gold moves persistently against the proposed yield/dollar transmission without corroborating demand'},
 'growth':{'name':'Labour/industry → growth outlook → policy/risk appetite → gold','words':r'labou?r|jobs|employment|payroll|recession|growth|manufactur|industrial|hiring|consumer|gdp|copper',
           'assets':['copper','equities','dxy'],'evidence':'Dated labour/industry releases and revisions compared with consensus',
           'falsifier':'Industrial and labour indicators fail to confirm the proposed slowdown'},
 'safehaven':{'name':'Geopolitical stress → risk hedging / USD → gold','words':r'geopolit|war|conflict|militar|sanction|safe.haven|risk.off|invasion|escalat|de.escalat',
              'assets':['equities','dxy','oil'],'evidence':'Verified escalation/de-escalation events and observed risk-hedging demand',
              'falsifier':'Risk hedging and commodity channels both fail to confirm the proposed impact'},
 'physical':{'name':'Delivery/collateral bottlenecks → replacement gold demand → spot/futures','words':r'gold shortage|gold surplus|bullion|refiner|lease|collateral|vault|delivery|bullion.premium|gold.premium|physical.premium|physical.gold|forward|prepay|gold lending|settlement',
             'assets':['futures','etf','dxy'],'evidence':'Fine-troy-ounce quantities, binding delivery/collateral obligations and net external gold purchases/sales',
             'falsifier':'Alleged shortage/surplus fails to produce binding funding gaps or external flows net of offsets'},
 'funding':{'name':'Credit/liquidity strain → funding / forced selling → gold','words':r'liquidit|credit|margin|repo|funding|bank|swap|haircut|spread|leverage',
            'assets':['credit','dxy','nominal'],'evidence':'Funding spreads, margin/collateral changes and forced-transaction evidence',
            'falsifier':'No measurable change in funding costs, margins or risk-asset repricing'},
 'flows':{'name':'Reserve diversification / ETF positioning → gold resilience','words':r'etf|central.bank|reserve|positioning|gold.flow|inflow|outflow|investment.demand',
          'assets':['etf','dxy','real'],'evidence':'Published ETF creation/redemption or holding flows, reserve transactions and reporting timestamps',
          'falsifier':'Recorded flows do not support hypothesised net physical or investment demand'},
}
PRIORITY=('physical','freight','funding','rates','growth','safehaven','flows')

def _interval(horizon):
    return {'intraday':'1h','swing':'4h','macro':'1D'}[horizon]

def plan(question,focus='OANDA:XAUUSD',horizon='intraday',headlines=None):
    if not isinstance(question,str) or len(question.strip())<12 or len(question)>1200:
        raise ValueError('Describe the research question in 12–1200 characters.')
    focus=focus.strip().upper()
    if not re.fullmatch(r'[A-Z0-9_.:/!+\-]{2,55}',focus):raise ValueError('Invalid focal ticker.')
    if horizon not in ('intraday','swing','macro'):raise ValueError('Unknown analysis horizon.')
    core=question.lower()
    evidence_text=' '.join((x.get('title','')+' '+x.get('detail','')[:250]) for x in (headlines or [])[:25]).lower()
    scored=[]
    for key,mech in MECHANISMS.items():
        q_hits=len(re.findall(mech['words'],core,re.IGNORECASE))
        ev_hits=min(3,len(re.findall(mech['words'],evidence_text,re.IGNORECASE)))
        scored.append((3*q_hits+ev_hits,key))
    scored.sort(key=lambda x:(-x[0],PRIORITY.index(x[1])))
    selected=[k for v,k in scored if v>0][:3]
    if not selected:selected=['rates','flows']
    if len(selected)==1:
        selected.append('rates' if selected[0]!='rates' else 'flows')
    main_interval=_interval(horizon)
    assets=[{'key':'focus','symbol':focus,'name':'Primary instrument','interval':main_interval,
             'priority':'required','reason':'Target of the conditional prediction','data_class':'observed_chart'}]
    taken={focus}
    # Give priority to macro-price comparison, not dozens of arbitrary symbols.
    votes={}
    for rank,k in enumerate(selected):
        for ix,key in enumerate(MECHANISMS[k]['assets']):
            votes[key]=votes.get(key,0)+4-rank-ix*.45
    if 'dxy' not in votes:votes['dxy']=1
    sorted_assets=sorted(votes,key=lambda x:-votes[x])
    for key in sorted_assets:
        symbol,name,role=CATALOG[key]
        if symbol in taken:continue
        if len(assets)>=7:break
        # Daily series are contextual for intraday/swing; cannot calculate
        # same-clock returns against 1h/4h candles.
        series_interval='1D' if key=='real' else main_interval
        tier='context' if key=='real' and main_interval!='1D' else ('required' if len([a for a in assets if a['priority']=='required'])<4 else 'optional')
        assets.append({'key':key,'symbol':symbol,'name':name,'interval':series_interval,
                       'priority':tier,'reason':role,'data_class':'observed_chart'})
        taken.add(symbol)
    if len([x for x in assets if x['priority']=='required'])<2:
        raise ValueError('No valid comparison tickers selected.')
    mechanisms=[{'id':k,**MECHANISMS[k]} for k in selected]
    # Non-chart evidence cannot be fabricated by correlations or ETFs.
    return {'question':question.strip(),'focus':focus,'horizon':horizon,'main_interval':main_interval,
      'method':'rule-based research planner','mechanisms':mechanisms,'requests':assets,
      'external_checks':[{'domain':m['name'],'needed':m['evidence'],'falsifier':m['falsifier']} for m in mechanisms],
      'why_these_tickers':'Requests are tailored to the stated thesis and recent headline keywords; prices test reactions, not causality.',
      'caveat':'Not a price target, trade recommendation or calibrated probability. Manual CSVs may be stale or incomplete.'}

def _date(s):return datetime.fromisoformat(s.replace('Z','+00:00')).astimezone(UTC)
def _ret_map(chart):
    bars=chart.get('candles') or []
    out={}
    symbol=str(chart.get('symbol','')).upper()
    yield_series=any(s in symbol for s in ('DFII10','US10Y','US02Y','US05Y','US30Y'))
    for left,right in zip(bars,bars[1:]):
        if right['time']<=left['time']:continue
        if yield_series:
            out[right['time']]=right['close']-left['close']  # percentage-point changes, not yield returns
        elif left['close']>0 and right['close']>0:
            out[right['time']]=math.log(right['close']/left['close'])
    return out

def correlate(a,b):
    if len(a)<20 or len(b)<20:return None
    ma,mb=statistics.mean(a),statistics.mean(b)
    dev_a=[v-ma for v in a];dev_b=[v-mb for v in b]
    da=sum(v*v for v in dev_a);db=sum(v*v for v in dev_b)
    if da<=0 or db<=0:return None
    return round(sum(x*y for x,y in zip(dev_a,dev_b))/math.sqrt(da*db),3)

def pair_test(focus,comparison):
    a,b=_ret_map(focus),_ret_map(comparison)
    times=sorted(set(a)&set(b));na=len(times)
    if na<20:return {'sample':na,'status':'insufficient-overlap','message':'Need ≥20 matching closed-candle timestamps; check both CSV date ranges and timeframes.'}
    x=[a[t] for t in times];y=[b[t] for t in times]
    if na<30:return {'sample':na,'status':'thin-overlap','correlation':correlate(x,y),'message':'Limited aligned sample; interpret cautiously.'}
    corr=correlate(x,y)
    # Lagging y by one matching bar can indicate a possible lead; no predictive claim.
    lead1=correlate(y[:-1],x[1:])
    return {'sample':na,'status':'observed','correlation':corr,
            'other_asset_prior_bar_vs_focus_next_bar':lead1,
            'first_overlap':times[0],'last_overlap':times[-1],
            'message':'Descriptive aligned changes (log returns for price series; percentage-point changes for yields). Apparent lag may reflect common shocks, multiple testing or mismatched information timing.'}

def analyse(plan_record,charts,news_events=None,now=None):
    now=now or datetime.now(UTC)
    matches={(c['symbol'].upper(),c['interval']):c for c in charts}
    requested=plan_record['requests']; requests=[]; metrics=[]; blocking=[]
    chart_by_symbol={}
    for req in requested:
        found=matches.get((req['symbol'],req['interval']))
        item={k:req[k] for k in ('symbol','name','interval','priority','reason')}
        if found:
            last=_date(found['last_time'])
            age_hours=(now-last).total_seconds()/3600
            max_h=360 if req['interval'] in ('1D','1W','1M') else 96
            item.update(status='ready' if age_hours>=0 and age_hours<=max_h else 'stale',
                        last_candle=found['last_time'],uploaded_at=found.get('uploaded_at'),
                        bar_count=found['bars'],age_hours=round(age_hours,1))
            chart_by_symbol[req['symbol']]=found
        else:item['status']='missing'
        requests.append(item)
        if item['status']!='ready' and req['priority']=='required':blocking.append(item['symbol']+': '+item['status'])
    base=chart_by_symbol.get(plan_record['focus'])
    cross_metrics=[]
    if base:
        for req in requested:
            if req['symbol']==plan_record['focus']:continue
            other=chart_by_symbol.get(req['symbol'])
            if not other:continue
            if other['interval']!=base['interval']:
                cross_metrics.append({'symbol':req['symbol'],'status':'different-timeframe',
                    'message':'Context only; do not correlate different timeframe candles without resampling.'});continue
            pair=pair_test(base,other)
            cross_metrics.append({'symbol':req['symbol'],**pair})
            if req['priority']=='required' and pair['status']=='insufficient-overlap':
                blocking.append(req['symbol']+': fewer than 20 overlapping returns with '+plan_record['focus'])
    if not base:
        blocking.append('Primary instrument not imported')
    follow_up=[]
    dxy=chart_by_symbol.get('TVC:DXY')
    if base and dxy and base.get('twenty_bar_percent') is not None and dxy.get('twenty_bar_percent') is not None:
        if float(base['twenty_bar_percent'])*float(dxy['twenty_bar_percent'])>0 and abs(float(base['twenty_bar_percent']))>.1 and abs(float(dxy['twenty_bar_percent']))>.1:
            if 'FRED:DFII10' not in [x['symbol'] for x in requested]:
                follow_up.append({'symbol':'FRED:DFII10','interval':'1D','purpose':'Primary instrument and the dollar moved together; investigate real-yield context (not proof of flows).','priority':'optional-follow-up'})
    # Provisional *explanatory* horse race, not a trained probability model.
    # Use only uploaded, fresh and compatible chart data. The rules are intentionally
    # low-weight because macro price responses often invert between regimes.
    bullish=0.0;bearish=0.0;proxy_bullish=0.0;proxy_bearish=0.0;proxy_count=0;signals=[]
    is_gold=('XAUUSD' in plan_record['focus'] or plan_record['focus'].endswith(':GOLD'))
    if base and base.get('twenty_bar_percent') is not None:
        delta=float(base['twenty_bar_percent'])
        signals.append('Primary instrument 20-bar return: '+f'{delta:+.2f}%')
        if delta>=.3:bullish+=1
        if delta<=-.3:bearish+=1
    ready={r['symbol'] for r in requests if r['status']=='ready'}
    if is_gold and dxy and 'TVC:DXY' in ready and dxy.get('twenty_bar_percent') is not None:
        delta=float(dxy['twenty_bar_percent'])
        signals.append('Dollar-index 20-bar return: '+f'{delta:+.2f}%'+ ' (usual inverse-gold channel; regime-dependent)')
        if delta<=-.15:
            bullish+=1;proxy_bullish+=1;proxy_count+=1
        elif delta>=.15:
            bearish+=1;proxy_bearish+=1;proxy_count+=1
    if is_gold:
        for symbol,threshold,weight in (('TVC:US10Y',.035,1.0),('FRED:DFII10',.05,.5)):
            c=chart_by_symbol.get(symbol)
            if not c or symbol not in ready or len(c.get('candles') or [])<20:continue
            pp=float(c['candles'][-1]['close'])-float(c['candles'][-20]['close'])
            label='10Y nominal Treasury yield' if symbol=='TVC:US10Y' else '10Y real Treasury yield (daily context)'
            signals.append(label+' 20-bar change: '+f'{pp:+.3f}'+' percentage points')
            if pp>=threshold:
                bearish+=weight;proxy_bearish+=weight;proxy_count+=1
            elif pp<=-threshold:
                bullish+=weight;proxy_bullish+=weight;proxy_count+=1
    for row in cross_metrics:
        if row.get('status') not in ('observed','thin-overlap'):continue
        if row.get('correlation') is not None:
            signals.append(row['symbol']+': aligned changes correlation '+str(row['correlation'])+' over '+str(row['sample'])+' observations (descriptive only)')
    status='ready-for-synthesis' if not blocking else 'incomplete-data'
    if bullish>bearish+.5 and bullish>=1.5:leader='Bullish (price context only)'
    elif bearish>bullish+.5 and bearish>=1.5:leader='Bearish (price context only)'
    else:leader='Mixed price context — macro bias not determined'
    ranking=sorted([
        {'case':'Bullish','qualitative_support_points':bullish},
        {'case':'Bearish','qualitative_support_points':bearish},
        {'case':'Flat / awaiting catalyst','qualitative_support_points':max(.5,1.5-abs(bullish-bearish)/2)}
    ],key=lambda x: (-x['qualitative_support_points'],0 if x['case']==leader else 1))
    if status!='ready-for-synthesis':ranking=[];leader='Insufficient market data — retain any prior macro bias'
    events=news_events or []
    evidence=[{'title':x.get('title','')[:160],'occurred':x.get('time',''),
               'url':x.get('source','') or x.get('source_url',''),
               'assessment':(x.get('score') or {}).get('method','unreviewed')}
               for x in events[-12:]]
    # Potential relationship is not claimed to be proven by a pair test.
    scenarios=[
        {'case':'Bullish','trigger':'Gold holds gains while dollar and relevant yield pressures ease, or a verified independent demand catalyst dominates.',
         'invalidation':'Gold loses the relevant reaction levels and supportive flows/data fail to appear.'},
        {'case':'Bearish','trigger':'Gold weakens while USD/rates reprice higher, or independent selling/surplus evidence is verified.',
         'invalidation':'Gold remains resilient and the claimed selling/rate-transmission channel is contradicted.'},
        {'case':'Neutral / awaiting material catalyst','trigger':'Divergent asset responses, stale inputs or no verified real-world transmission mechanism.',
         'invalidation':'New verified evidence produces consistent, timely cross-asset confirmation.'}]
    return {'status':status,'blocking':blocking,'requests':requests,'tested_pairs':cross_metrics,
            'observed_signals':signals,'leading_observation':('Provisional leader: '+leader+'; mechanisms unverified') if status=='ready-for-synthesis' else 'Undetermined — required data incomplete',
            'scenario_ranking':ranking,'price_support':{'Bullish':bullish,'Bearish':bearish,'proxy_bullish':proxy_bullish,'proxy_bearish':proxy_bearish,'proxy_count':proxy_count},'ranking_method':'Market observations are short-term context; the persistent fundamental bias is maintained separately from price fluctuations. No calibrated probabilities.',
            'scenarios':scenarios,'follow_up_requests':follow_up,'mechanisms':plan_record['mechanisms'],'external_checks':plan_record['external_checks'],
            'news_evidence':evidence,'analysed_at':now.isoformat().replace('+00:00','Z'),
            'method':'deterministic alignment + conditional framework; no AI synthesis performed',
            'limitations':['Correlation and one-bar lead/lag are not causal proof or validated forecasts.',
                'Current price is user supplied and may include an unfinished final candle.',
                'Source headlines and ETF prices cannot verify physical flows or transaction quantities.',
                'Directional scenarios are hypotheses, not calibrated probabilities or live trading signals.']}

def refine_plan(base, ai_selection):
    """AI can nominate extra/alternative permitted instruments, never arbitrary symbols.
    Always keep the target and at least two corroborating required series.
    """
    if not isinstance(ai_selection,dict):raise ValueError('AI did not return an object')
    keys=ai_selection.get('selected_keys')
    if not isinstance(keys,list):raise ValueError('AI did not return selected_keys')
    clean=[]
    for k in keys:
        if isinstance(k,str) and k in CATALOG and k not in clean:clean.append(k)
    if len(clean)<2:raise ValueError('AI selected too few supported instruments')
    req=[base['requests'][0]]
    main_interval=base['main_interval']
    for k in clean[:6]:
        symbol,name,reason=CATALOG[k]
        if symbol==base['focus']:continue
        iv='1D' if k=='real' else main_interval
        req.append({'key':k,'symbol':symbol,'name':name,'interval':iv,
                    'priority':'context' if iv!=main_interval else 'required' if len([r for r in req if r['priority']=='required'])<4 else 'optional',
                    'reason':reason,'data_class':'observed_chart'})
    if len([r for r in req if r['priority']=='required'])<2:
        raise ValueError('AI produced no same-timeframe comparison')
    allowed={m['id']:m for m in base['mechanisms']}
    plan={**base,'requests':req,'method':'AI-guided market request (validated catalog)',
          'why_these_tickers':str(ai_selection.get('rationale') or base['why_these_tickers'])[:1000]}
    if isinstance(ai_selection.get('hypothesis'),str):plan['initial_hypothesis']=ai_selection['hypothesis'][:900]
    novel=ai_selection.get('novel_link')
    if isinstance(novel,dict) and all(isinstance(novel.get(k),str) and 12<=len(novel[k])<=700 for k in ('chain','evidence_needed','falsifier')):
        proposed={'id':'ai-hypothesis','name':novel['chain'][:250],
                  'evidence':novel['evidence_needed'][:500],'falsifier':novel['falsifier'][:500],
                  'origin':'AI-proposed, unverified causal hypothesis'}
        plan['mechanisms'].append(proposed)
        plan['external_checks'].append({'domain':proposed['name'],'needed':proposed['evidence'],
                  'falsifier':proposed['falsifier'],'origin':proposed['origin']})
    return plan