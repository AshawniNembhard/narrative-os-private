"""Explainable, deliberately conservative assessments for Narrative OS.

0-5 dimension scores are editorial research triage, NOT calibrated probabilities,
measured predictive accuracy, or a market trading signal. Headline-search items
never produce a directional narrative update without underlying verified data.
"""
from __future__ import annotations
import datetime as dt
import re
from difflib import SequenceMatcher

NARRATIVE_IDS = ('rates', 'haven', 'growth')
TOPIC_PATTERN = re.compile(r'\b(cpi|pce|ppi|payroll|unemployment|jobs|employment|inflation|federal reserve|\bfed\b|fomc|central bank|real yields?|tips|treasury|dxy|dollar|xau|gold|interest rates?|interest-rate|shipping|marine insurance|tanker|freight|energy|oil|geopolitic|conflict|sanction|ceasefire|recession|etf|bond auction)\b', re.I)
ALT_PATTERN = re.compile(r'\b(freight|shipping|tanker|marine|insurance|port congestion|refinery|weather|grid|energy|temporary hiring|temporary worker|hours worked|supply chain|crop|auction|central bank|physical gold|etf|term premium|logistics)\b', re.I)
STOP = set('the and for from with amid into could would over under after before that this news latest us uss market markets gold today'.split())

def clamp(n, a=0, b=5):
    try: return max(a, min(b, int(n)))
    except (TypeError, ValueError): return a

def _title_tokens(title):
    return set(w for w in re.findall(r'[a-z]{3,}', title.lower()) if w not in STOP)

def similar_titles(title_a, title_b):
    a,b=_title_tokens(title_a),_title_tokens(title_b)
    if not a or not b:return False
    jaccard=len(a & b)/len(a | b)
    return jaccard>=.72 or SequenceMatcher(None,' '.join(sorted(a)),' '.join(sorted(b))).ratio()>=.89

def auto_score(event, previous=(), surprise=None):
    """Score a new item from provenance and *verified fields*, never a directional guess.

    surprise: optional pre-existing deterministic actual-vs-consensus assessment.
    Scores: reliability, novelty, significance, unconventional relevance, 0..5.
    Narrative impacts: -2..+2, but neutral for headline-only observations.
    """
    typ=event.get('type') or 'news'
    kind=event.get('source_kind') or ''
    title=event.get('title') or ''
    detail=event.get('detail') or ''
    body=title+' '+detail if kind!='search_headline' else title
    impacts={key:0 for key in NARRATIVE_IDS}
    measured=bool(event.get('market_key')) and event.get('value') is not None
    official_real=kind=='official_daily_treasury' and measured
    headline_only=kind=='search_headline' or (typ=='news' and not event.get('actual'))
    if official_real:
        rel=5; rel_note='Official US Treasury daily numeric observation; not an intraday quote.'
    elif kind=='public_daily_market' and measured:
        rel=3; rel_note='Source-dated public daily price series; availability and accuracy are not independently audited.'
    elif kind=='unofficial_market_snapshot' and measured:
        rel=2; rel_note='Unofficial daily market-data fallback; delayed or proxy measurements may differ from spot.'
    elif kind=='official_release_headline' or str(event.get('id','')).startswith('bls-'):
        rel=4; rel_note='Official release-announcement provenance, but numerical surprise is not extracted.'
    elif kind=='licensed_calendar_release' and event.get('actual'):
        rel=4; rel_note='Structured calendar values; check units, methodology, revisions and vendor accuracy.'
    elif headline_only:
        rel=2; rel_note='Search-indexed headline only. Underlying reporting and factual claim have not been verified.'
    elif typ=='research' and not event.get('source'):
        rel=1; rel_note='User-entered research without a linked, verified primary source.'
    else:
        rel=2; rel_note='Source or interpretation has not been independently corroborated.'

    duplicate=any(similar_titles(title,p.get('title','')) for p in previous if p.get('id')!=event.get('id'))
    novelty=1 if duplicate else 4
    novelty_note=('A closely related headline is already recorded; little new information is established.' if duplicate
                  else 'No closely matching previously stored headline; this does not prove the underlying fact is new.')
    if measured:
        novelty=3 if not duplicate else 1
        novelty_note=('A distinct dated measurement is available; importance depends on its change and context.' if not duplicate else novelty_note)
    if TOPIC_PATTERN.search(title):
        sig=4 if any(x in title.lower() for x in ('cpi','fomc','nonfarm','payroll','real yield','fed ', 'federal reserve','gold','dollar index','treasury')) else 3
        sig_note='Direct macro or cross-market relevance to gold; not a quantified price effect.'
    elif typ in ('market','macro'):
        sig=3;sig_note='Potential macro context; direct gold impact is not established.'
    elif typ=='logistics':
        sig=3;sig_note='Plausible upstream supply or inflation channel, requiring magnitude and timing checks.'
    else:
        sig=1;sig_note='No clearly identified near-term gold transmission mechanism in the supplied information.'
    alt_match=bool(ALT_PATTERN.search(body))
    alt=4 if alt_match and typ!='market' else 2 if alt_match else 1
    alt_note=('A plausible cross-disciplinary link warrants investigation; not a verified leading indicator.' if alt_match
              else 'No specific unusual causal mechanism can be inferred from the available facts.')
    impact_note='Directional narrative evidence not established. A headline or price alone cannot demonstrate causation.'
    impact_confidence='low'
    surprises=surprise or {}
    if (event.get('actual') and event.get('consensus') and surprises
            and kind!='search_headline'):
        impacts={k:clamp(surprises.get(k,0),-2,2) for k in NARRATIVE_IDS}
        impact_note='Explicit actual-versus-consensus surprise supports provisional rate/growth scenarios; market confirmation is still needed.'
        impact_confidence='moderate'
    elif official_real:
        # Measured yield change is observable, but does not identify what caused it.
        pp=event.get('change_pp')
        if isinstance(pp,(int,float)) and abs(pp)>=.05:
            impacts['rates']=1 if pp>0 else -1
            impact_note=('10-year published real yield increased' if pp>0 else '10-year published real yield decreased')+' by at least 0.05 percentage points; a limited rates-pressure cross-check, not a Fed-policy or gold-direction claim.'
            impact_confidence='moderate'
        else:
            impact_note='Real-yield change is absent or too small for the conservative ±0.05 percentage-point rule.'
    elif headline_only:
        impact_note='Headline-only discovery cannot establish a verified numerical surprise or causal gold impact; all narrative impacts stay at zero.'

    limitations='Rule-based triage, not a predictive model. Source content and competing explanations may be missing.'
    if event.get('mode')=='demo' or str(event.get('id','')).startswith('demo-'):
        impacts={k:clamp((event.get('impacts') or {}).get(k,0),-2,2) for k in NARRATIVE_IDS}
        impact_note='Fictional teaching scenario with authored impacts; not inferred from live data.'
        rel=0;rel_note='Simulation. This is not sourced real-world evidence.'
        limitations='Simulation only; no market facts, forecast power or verified source reliability.'
        method='demo'
    else:method='rules'
    return {
       'impacts':impacts,
       'score':{
           'method':method,
           'scored_at':dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z'),
           'reliability':{'value':rel,'reason':rel_note},
           'novelty':{'value':novelty,'reason':novelty_note},
           'significance':{'value':sig,'reason':sig_note},
           'unconventional':{'value':alt,'reason':alt_note},
           'impact_reason':impact_note,
           'impact_confidence':impact_confidence,
           'limitations':limitations,
       }
    }

def combine_ai(event, ai):
    """Parse optional AI assessment. Never let AI upgrade headline-only to verified.

    All AI data are advisory. A verified input source is not independently
    validated just because an AI model emits a high numeric score.
    """
    if not isinstance(ai,dict):raise ValueError('AI scoring result must be an object')
    existing=event.get('score') or auto_score(event)['score']
    score={**existing, 'method':'ai'}
    for field in ('reliability','novelty','significance','unconventional'):
        obj=ai.get(field)
        if not isinstance(obj,dict) or not isinstance(obj.get('value'),(int,float)) or not isinstance(obj.get('reason'),str):
            raise ValueError('AI score missing '+field)
        value=clamp(obj['value'])
        if field=='reliability':
            # Source provenance is not something the language model can verify from metadata.
            value=min(value,existing['reliability']['value'])
        score[field]={'value':value,'reason':obj['reason'][:450]}
    if not isinstance(ai.get('impact_reason'),str):raise ValueError('AI score missing impact_reason')
    if not isinstance(ai.get('impacts'),dict):raise ValueError('AI score missing impacts')
    impacts={k:clamp(ai['impacts'].get(k,0),-2,2) for k in NARRATIVE_IDS}
    kind=event.get('source_kind','')
    if kind in ('search_headline','official_release_headline') or (event.get('type')=='news' and not event.get('actual')):
        impacts={k:0 for k in NARRATIVE_IDS}
        score['impact_reason']='AI commentary only; headline not independently verified. '+ai['impact_reason'][:300]+' Directional scoring held neutral.'
        score['impact_confidence']='low'
    elif kind in ('public_daily_market','unofficial_market_snapshot'):
        # Price observations alone are insufficient to infer a causal macro story.
        impacts={k:0 for k in NARRATIVE_IDS}
        score['impact_reason']='Daily market price alone does not verify cause. '+ai['impact_reason'][:300]
        score['impact_confidence']='low'
    elif kind=='official_daily_treasury':
        impacts={k:clamp(impacts[k],-1,1) if k=='rates' else 0 for k in NARRATIVE_IDS}
        score['impact_reason']='Daily real-yield data; impact capped to a rates-context hypothesis. '+ai['impact_reason'][:300]
        score['impact_confidence']='moderate'
    else:
        impacts={k:clamp(v,-1,1) for k,v in impacts.items()}
        score['impact_reason']=ai['impact_reason'][:450]
        score['impact_confidence']='low' if not event.get('actual') else 'moderate'
    score['limitations']='AI assessment using supplied source metadata and observations only; not independently verified or statistically calibrated.'
    score['scored_at']=dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
    return {'score':score,'impacts':impacts}