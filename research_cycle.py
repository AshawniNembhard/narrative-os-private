"""Bounded, evidence-labelled AI discovery for an on-demand interdisciplinary research cycle.

AI-selected narratives are hypotheses, not observations or calibrated odds.
Only clean, validated content is persisted. News search results are metadata, not
full-text evidence; market data enters separately via the manual CSV path.
"""
from __future__ import annotations

from urllib.parse import urlsplit

DIRECTIONS={'Bullish','Bearish','Two-sided'}


def _text(value,limit=600):
    return str(value or '').strip()[:limit] if isinstance(value,str) else ''


def capture_headlines(rows):
    """Retain short, dated source metadata without marking a story verified."""
    seen=set();out=[]
    for row in rows or []:
        if not isinstance(row,dict):continue
        title=_text(row.get('title'),170)
        url=_text(row.get('url') or row.get('source') or row.get('link'),700)
        if not title or title.lower() in seen:continue
        seen.add(title.lower())
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.netloc:url=''
        out.append({'title':title,'url':url,'time':_text(row.get('time'),50),
                    'publisher':_text(row.get('publisher') or row.get('source_name') or '',90),
                    'quality':'headline-only; unverified'})
        if len(out)>=12:break
    return out


def normalise_discovery(answer):
    """Reject malformed claims rather than presenting an AI paragraph as validation."""
    if not isinstance(answer,dict):raise ValueError('Discovery output must be an object')
    source=answer.get('theories')
    if not isinstance(source,list):raise ValueError('Discovery needs competing theories')
    theories=[];titles=set()
    for item in source[:8]:
        if not isinstance(item,dict):continue
        title=_text(item.get('title'),110)
        direction=item.get('direction')
        chain=_text(item.get('chain'),900)
        falsifier=_text(item.get('falsifier'),600)
        external=_text(item.get('external_evidence'),600)
        if not title or len(chain)<24 or len(falsifier)<12 or len(external)<12 or direction not in DIRECTIONS:
            continue
        if title.lower() in titles:continue
        titles.add(title.lower())
        theories.append({'id':f'theory-{len(theories)+1}', 'title':title,
          'direction':direction,'chain':chain,'falsifier':falsifier,
          'external_evidence':external,'earliest_indicator':_text(item.get('earliest_indicator'),350),
          'horizon':_text(item.get('horizon'),90), 'status':'AI-proposed / unverified'})
        if len(theories)>=4:break
    if len(theories)<2:raise ValueError('Discovery needs at least two testable competing theories')
    leader=answer.get('leading_index',0)
    if type(leader)!=int or not 0<=leader<len(theories):leader=0
    preferred=theories[leader]
    return {'status':'AI-proposed / unverified', 'theories':theories,
        'leading_id':preferred['id'],'leading_direction':preferred['direction'],
        'leading_title':preferred['title'],
        'leading_reason':_text(answer.get('leading_reason'),700) or 'Provisional priority proposed by AI, not independently established.',
        'selection_basis':'Unverified causal prioritisation; not a measured probability, a trade instruction or proof of external flows.',
        'why_unconventional':_text(answer.get('why_unconventional'),700),
        'cannot_conclude':_text(answer.get('cannot_conclude'),600) or 'Headlines and charts alone cannot prove transactions, delivery shortfalls or institutional positioning.'}


def no_ai_discovery():
    return {'status':'Rule-based planning; no AI theory discovery', 'theories':[],
            'leading_id':None,'leading_direction':'Unestablished',
            'leading_title':'Not established', 'leading_reason':'Enable AI discovery to nominate a working theory.',
            'selection_basis':'No directional thesis inferred from unverified headlines.'}


def initial_horse_race(discovery):
    """Priority order is editorial research triage, never a numeric probability."""
    theories=discovery.get('theories') or []
    leading=discovery.get('leading_id')
    sorted_items=sorted(theories,key=lambda t: t.get('id')!=leading)
    return [{'id':t['id'],'title':t['title'],'direction':t['direction'],
             'rank':ix+1,'status':'unverified / awaiting market and external checks',
             'why_ranked':'Initial AI research priority; not validated against market CSVs.'}
            for ix,t in enumerate(sorted_items)]


def revise_horse_race(discovery, ai_response):
    """Allow re-ordering candidate explanations, but only from valid known IDs.

    No probability, proof or alleged flow quantity is inferred from AI text.
    """
    baseline=initial_horse_race(discovery)
    if not baseline or not isinstance(ai_response,dict):return baseline
    proposals=ai_response.get('theory_rankings')
    if not isinstance(proposals,list):return baseline
    allowed={x['id']:x for x in baseline}
    ranked=[];seen=set()
    for entry in proposals:
        if not isinstance(entry,dict):continue
        id=entry.get('id')
        if id not in allowed or id in seen:continue
        seen.add(id)
        state=entry.get('status')
        if state not in ('price-context supports', 'price-context challenges', 'unverified / awaiting external checks'):
            state='unverified / awaiting external checks'
        ranked.append({**allowed[id],
            'status':state,
            'why_ranked':_text(entry.get('why_ranked'),500) or allowed[id]['why_ranked']})
    ranked.extend(x for x in baseline if x['id'] not in seen)
    for i,item in enumerate(ranked):item['rank']=i+1
    return ranked