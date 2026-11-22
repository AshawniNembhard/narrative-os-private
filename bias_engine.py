"""Sticky macro research bias with evidence hysteresis.

This is a *research state machine*, not a statistical probability model. It
separates a persistent macro thesis from fast tactical price responses. Every
transition is derived from dated source evidence; short-timeframe candles may
challenge a thesis but never switch an established fundamental bias alone.
"""
from __future__ import annotations
from datetime import datetime,timezone
from urllib.parse import urlsplit
import hashlib
import json
import math

UTC=timezone.utc
MIN_ADOPT=0.7
CHALLENGE_MIN=0.65
SWITCH_MIN=2.4
MAX_HISTORY=60


def _num(v,default=0.):
    try:
        val=float(v)
        return val if math.isfinite(val) else default
    except (ValueError,TypeError):return default


def _utc(s):
    try:
        v=datetime.fromisoformat(str(s).replace('Z','+00:00'))
        return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)
    except Exception:return None


def _event(e):
    """Return one directional event; never convert headlines to beliefs.

    Source reliability controls weight; a manual override remains labelled as
    user judgment and cannot alone trigger an automatic thesis reversal.
    """
    imp=e.get('impacts') or {}
    # The three narrative weights are effects on gold rather than narrative scores.
    # More rates pressure is a gold headwind; more haven/growth support is a tailwind.
    direction=_num(imp.get('haven'))+_num(imp.get('growth'))-_num(imp.get('rates'))
    if abs(direction)<0.01:return None
    typ=e.get('source_kind') or ''
    method=(e.get('score') or {}).get('method') or ''
    if str(e.get('id','')).startswith('demo-') or method=='demo':return None
    if typ in ('search_headline','official_release_headline','public_daily_market','unofficial_market_snapshot'):
        return None
    score=e.get('score') or {}
    rel=_num((score.get('reliability') or {}).get('value'),2)
    sig=_num((score.get('significance') or {}).get('value'),2)
    novelty=_num((score.get('novelty') or {}).get('value'),2)
    # Missing provenance is not high-quality evidence; scored numerical surprises
    # count more than unverified manually entered hypotheses.
    verified=(typ=='licensed_calendar_release' and e.get('actual') is not None and e.get('consensus') is not None)
    if typ=='official_daily_treasury':weight=.62
    elif verified:weight=1.05
    elif method=='manual':weight=.33
    elif method=='ai':weight=.42
    else:weight=.38
    weight*=max(.4,min(1.0,(rel+.5)/4.5))
    weight*=max(.6,min(1.0,(sig+.5)/4.5))
    weight*=.7 if novelty<=1 else 1.
    points=round(min(3.0,abs(direction)*weight),3)
    if points<.05:return None
    key=str(e.get('id') or e.get('source') or e.get('title') or '')
    if not key:return None
    tag=('verified release' if verified else 'official real-yield observation' if typ=='official_daily_treasury' else 'user judgment' if method=='manual' else 'unverified analysis')
    group=(e.get('type') or 'other').lower()
    if typ=='official_daily_treasury':group='rates-observation'
    if verified:group='structured-release'
    src=e.get('source') or e.get('source_url') or ''
    try:host=urlsplit(src).hostname or ''
    except Exception:host=''
    digest=hashlib.sha256(json.dumps({'id':key,'impacts':imp,'source_kind':typ,'score_method':method,'date':e.get('time')},sort_keys=True,default=str).encode()).hexdigest()[:16]
    return {'id':key,'revision':digest,'direction':'Bullish' if direction>0 else 'Bearish',
       'points':points,'quality':tag,'independent_group':group,
       'source_host':host,'title':str(e.get('title',''))[:140],
       'occurred':e.get('time'),'verified':verified}


def _price_state(assessment):
    """Observed market response is *diagnostic*, not fundamental validation."""
    # Interdisciplinary v0.5 already calculates noisy chart-side support points.
    p=assessment.get('price_support') or {}
    bulls=_num(p.get('Bullish'))
    bears=_num(p.get('Bearish'))
    difference=bulls-bears
    if difference>=1.5:direction='Bullish'
    elif difference<=-1.5:direction='Bearish'
    else:direction='Mixed'
    pb=_num(p.get('proxy_bullish'));ps=_num(p.get('proxy_bearish'))
    proxy_direction='Bullish' if pb-ps>=1.5 else 'Bearish' if ps-pb>=1.5 else 'Mixed'
    if int(p.get('proxy_count') or 0)<2 or assessment.get('status')!='ready-for-synthesis':proxy_direction='Mixed'
    return {'direction':direction,'proxy_direction':proxy_direction,'bullish_points':round(bulls,2),'bearish_points':round(bears,2),
            'description':'Cross-market and recent-price context only; can change faster than the macro thesis.'}


def _independent(ledger):
    """Count meaningfully distinct event groups, not headline duplicates."""
    verified=[r for r in ledger if r.get('verified')]
    groups={r.get('independent_group') for r in ledger}
    # A single official Treasury observation must not be represented as a
    # separate physical-flow or policy event simply because its title differs.
    return (len(groups)>=2 and len(ledger)>=2 and bool(verified))


def evaluate(assessment,events,previous=None,now=None,focus='OANDA:XAUUSD',horizon='intraday'):
    """Evaluate one research horizon for a target instrument; gold mappings are gold-only."""
    now=now or datetime.now(UTC)
    prior=previous or {}
    direction=prior.get('direction') if prior.get('direction') in ('Bullish','Bearish') else 'Unestablished'
    prev_revision=dict(prior.get('processed') or {})
    ledger=list(prior.get('challenger_evidence') or [])
    base_evidence=list(prior.get('basis_evidence') or [])
    checked=[];new=[]
    max_age={'intraday':14,'swing':45,'macro':120}.get(horizon,14)
    gold_focus='XAUUSD' in focus.upper() or focus.upper().endswith(':GOLD')
    for e in sorted(events,key=lambda x: str(x.get('time',''))):
        # Event impacts in v0.5 are specifically calibrated as gold narratives;
        # do not transfer their sign to GBPJPY, equities, etc.
        if not gold_focus:continue
        record=_event(e)
        if not record:continue
        t=_utc(record.get('occurred'))
        if t and (now-t).total_seconds()>max_age*86400:continue
        checked.append(record)
        if prev_revision.get(record['id'])!=record['revision']:
            prev_revision[record['id']]=record['revision']
            new.append(record)
    # Prevent counting older events as fresh after reinstall or first upgrade.
    # On the first run use the evidence available at that time; later runs ingest
    # only previously unseen facts / changed assessments.
    pos=sum(r['points'] for r in checked if r['direction']=='Bullish')
    neg=sum(r['points'] for r in checked if r['direction']=='Bearish')
    price=_price_state(assessment)
    if not gold_focus:
        price['proxy_direction']='Mixed'  # gold-specific proxy signs must not be applied to other targets
    state='unestablished';reason='No sufficiently grounded directional macro evidence yet.'
    basis=prior.get('basis','not established') if direction!='Unestablished' else 'not established'
    switched=False;established=prior.get('established_at');last_switch=prior.get('last_change_at')
    lead_support=round(pos-neg,2)
    competing='Bearish' if direction=='Bullish' else 'Bullish'
    if direction=='Unestablished':
        if abs(lead_support)>=MIN_ADOPT:
            direction='Bullish' if lead_support>0 else 'Bearish'
            base_evidence=[r for r in checked if r['direction']==direction][-MAX_HISTORY:]
            ledger=[]
            established=now.isoformat();last_switch=established
            basis='macro-evidence'
            state='established' if any(r['verified'] for r in base_evidence) else 'provisional'
            reason=('Initial research bias from source-dated macro evidence.' if state=='established'
                    else 'Initial *provisional* thesis from unverified or low-weight evidence; corroboration required.')
        elif price['proxy_direction'] in ('Bullish','Bearish'):
            direction=price['proxy_direction']
            state='provisional'
            basis='cross-market-inference'
            established=now.isoformat();last_switch=established
            reason=('Directional *working hypothesis* inferred from at least two cross-market proxies, '
                    'not from the target candle alone. Its causal fundamental mechanism is unverified; '
                    'retain across price noise but seek macro evidence before calling it established.')
        else:
            reason=('Source evidence is insufficient to establish a macro thesis. '
                    'Market-price direction is shown separately and is not labelled fundamental.')
    else:
        # Only newly scored macro observations influence transitions; repeated
        # CSV runs or minute-price updates cannot manufacture confirmation.
        for r in new:
            if r['direction']!=direction:
                ledger=[x for x in ledger if x['id']!=r['id']]+[r]
            else:
                base_evidence=[x for x in base_evidence if x['id']!=r['id']]+[r]
                ledger=[x for x in ledger if x['id']!=r['id']]
        ledger=ledger[-MAX_HISTORY:];base_evidence=base_evidence[-MAX_HISTORY:]
        support=sum(x['points'] for x in ledger)
        verified_release=any(r['verified'] for r in ledger)
        qualifies=_independent(ledger)
        if basis in ('cross-market-inference','user-hypothesis') and abs(lead_support)>=MIN_ADOPT:
            macro_direction='Bullish' if lead_support>0 else 'Bearish'
            switched=macro_direction!=direction
            direction=macro_direction
            basis='macro-evidence'
            state='established' if any(r['verified'] for r in new if r['direction']==direction) else 'provisional'
            reason=('A source-dated macro observation now supersedes the earlier cross-market-only working case. '
                    'This is an initial thesis upgrade, not a reversal of established fundamental evidence.')
            base_evidence=[r for r in checked if r['direction']==direction][-MAX_HISTORY:]
            ledger=[]
            established=now.isoformat();last_switch=established
        elif support>=SWITCH_MIN and qualifies:
            previous_direction=direction
            direction='Bearish' if direction=='Bullish' else 'Bullish'
            switched=True
            basis='macro-evidence'
            state='switched'
            reason=f'Changed from {previous_direction} after independently grouped, source-dated opposing macro evidence; not on a minute-candle reversal.'
            base_evidence=ledger;ledger=[]
            established=now.isoformat();last_switch=established
        elif support>=CHALLENGE_MIN:
            state='challenged'
            reason=('Opposing macro evidence has emerged, but reversal requirements are unmet. '
                   'Maintain the previous bias while checking causal materiality and independent corroboration.')
        else:
            state='provisional-held' if basis=='cross-market-inference' else 'retained'
            reason=('The macro thesis is retained; no qualifying new opposing evidence has invalidated it. '
                    'Missing CSVs, fresh market volatility and repeated scans do not reset the bias.')
        if price['direction'] not in ('Mixed',direction):
            reason+=' Short-term market data diverges; flag this for investigation, not automatic switching.'
    # Age is a prompt to refresh the evidence, not permission to flip the sign.
    age_h=None
    if established and _utc(established):
        age_h=round((now-_utc(established)).total_seconds()/3600,1)
    review_after={'intraday':72,'swing':240,'macro':1080}.get(horizon,72)
    if state in ('retained','provisional-held') and age_h is not None and age_h>review_after and not new:
        state='review-due'
        reason+=' Bias age exceeds the research-horizon review interval; refresh upstream fundamental evidence.'
    challenge_points=round(sum(x['points'] for x in ledger),2)
    unmet=[]
    if direction!='Unestablished' and challenge_points:
        if challenge_points<SWITCH_MIN:unmet.append(f'Need at least {SWITCH_MIN:g} accumulated opposing macro-evidence points (currently {challenge_points:g}).')
        if not _independent(ledger):unmet.append('Need corroborating event groups including an independently sourced structured release; duplicate headlines do not count.')
    elif direction=='Unestablished':unmet=['Need meaningful source-dated directional macro evidence; price candles alone do not suffice.']
    history=list(prior.get('history') or [])[-29:]
    if direction!=prior.get('direction') or state in ('switched','established','provisional','challenged') or (not prior and new):
        history.append({'at':now.isoformat(),'direction':direction,'state':state,'reason':reason})
    return {
      'direction':direction,'state':state,'reason':reason,'basis':basis,
      'established_at':established,'last_change_at':last_switch,'reviewed_at':now.isoformat(),'age_hours':age_h,'review_after_hours':review_after,
      'price_context':price,'market_divergence':price['direction'] not in ('Mixed',direction) and direction!='Unestablished',
      'evidence_balance':{'bullish':round(pos,2),'bearish':round(neg,2),'net':lead_support},
      'switched':switched,'new_evidence_count':len(new),'new_directional_events':[r['title'] for r in new][-6:],
      'challenger_evidence':ledger,'basis_evidence':base_evidence,'challenger_points':challenge_points,
      'switch_requirements':unmet,'processed':prev_revision,'history':history[-30:],
      'policy':'Fundamental bias changes on meaningful new macro evidence, not minute-to-minute price fluctuations. No calibrated probabilities.',
      'thresholds':{'initial_min_net':MIN_ADOPT,'challenge_min':CHALLENGE_MIN,'switch_min':SWITCH_MIN},
    }


def adopt_user_thesis(assessment,events,previous,direction,rationale,now=None,focus='OANDA:XAUUSD',horizon='intraday'):
    """Explicit research hypothesis set by user, with traceable manual provenance."""
    if direction not in ('Bullish','Bearish'):raise ValueError('Choose Bullish or Bearish')
    if not isinstance(rationale,str) or not 12<=len(rationale.strip())<=500:
        raise ValueError('Give a 12–500 character rationale for the working thesis')
    now=now or datetime.now(UTC)
    base=evaluate(assessment,events,previous,now,focus=focus,horizon=horizon)
    old=previous or {}
    old_dir=old.get('direction','Unestablished')
    base.update({'direction':direction,'state':'provisional-user','basis':'user-hypothesis',
                 'reason':'User-seeded, unverified hypothesis: '+rationale.strip(),
                 'established_at':now.isoformat(),'last_change_at':now.isoformat(),
                 'challenger_evidence':[],'challenger_points':0.,
                 'basis_evidence':[],'manual_rationale':rationale.strip(),
                 'switched':old_dir!=direction})
    base['switch_requirements']=['User-seeded hypothesis; requires source-dated macro evidence for promotion or a justified reversal.']
    base['history']=(list(old.get('history') or [])+[{'at':now.isoformat(),'direction':direction,
      'state':'provisional-user','reason':'Explicit user adoption: '+rationale.strip()}])[-30:]
    return base