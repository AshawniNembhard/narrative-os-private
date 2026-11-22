"""OpenAI documented Sign in with ChatGPT (local open-source, OAuth PKCE).

No ChatGPT password or session cookies requested. Auth token storage is local,
owner-only and never exposed to browser code. External OAuth cannot be tested
without user approval and Internet access. Do not deploy as a multi-tenant app.
"""
from __future__ import annotations
import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any
import jwt

AUTH='https://auth.openai.com'
RESOURCE='https://api.openai.com/v1'
JWKS=AUTH+'/.well-known/jwks.json'
AUTHORIZE=AUTH+'/api/accounts/authorize'
TOKEN=AUTH+'/api/accounts/oauth/token'
LOCK=threading.RLock()
PENDING:dict[str,dict]={}
MODEL_CACHE:dict[str,Any]={}

def store_dir():return Path(os.getenv('NARRATIVE_AUTH_DIR',str(Path.home()/'.config'/'narrative-os')))
def path(name):return store_dir()/name

def atomic_write(file:Path,data:dict):
    file.parent.mkdir(parents=True,exist_ok=True)
    try:file.parent.chmod(0o700)
    except OSError:pass
    tmp=file.with_suffix(file.suffix+'.tmp')
    fd=os.open(tmp,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as out:json.dump(data,out)
        os.replace(tmp,file)
        try:file.chmod(0o600)
        except OSError:pass
    finally:
        if tmp.exists():tmp.unlink()

def read_record(name):
    try:return json.loads(path(name).read_text(encoding='utf-8'))
    except (OSError,ValueError):return None

def host_id():
    with LOCK:
        val=read_record('host.json')
        if val and str(val.get('id','')).startswith('urn:uuid:'):return val['id']
        val={'id':'urn:uuid:'+str(uuid.uuid4())}
        atomic_write(path('host.json'),val)
        return val['id']

def status():
    with LOCK:profile=read_record('chatgpt.json')
    if not profile:return {'connected':False,'sharing':False,'provider':'chatgpt','auto_ai_allowed':False}
    return {'connected':True,'sharing':'chatgpt.tokens.use.direct' in profile.get('scopes',[]),
            'email':profile.get('email'),'provider':'chatgpt','expires_at':profile.get('expires_at')}

def start(port=8000):
    with LOCK:
        for key,record in list(PENDING.items()):
            if time.time()-record['started']>600:PENDING.pop(key,None)
        profile=read_record('chatgpt.json')
        state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(64)
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        redirect=f'http://127.0.0.1:{int(port)}/auth/callback'
        client=(profile or {}).get('client_id') or 'dynamic_agent_client'
        info={'response_type':'code','client_id':client,'redirect_uri':redirect,
             'scope':'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct',
             'resource':RESOURCE,'state':state,'nonce':nonce,'code_challenge_method':'S256',
             'code_challenge':challenge,'ext_agent_host_id':host_id()}
        if client=='dynamic_agent_client':info['agent_name_hint']='Narrative OS'
        elif profile and profile.get('id_token'):info['id_token_hint']=profile['id_token']
        PENDING[state]={'started':time.time(),'verifier':verifier,'nonce':nonce,
                        'client_id':client,'redirect':redirect,'prior_subject':(profile or {}).get('subject')}
        return {'url':AUTHORIZE+'?'+urllib.parse.urlencode(info),'expires_in':600}

def post_form(url,data):
    body=urllib.parse.urlencode(data).encode()
    req=urllib.request.Request(url,body,headers={'Content-Type':'application/x-www-form-urlencoded',
                                                   'User-Agent':'NarrativeOS/0.2'},method='POST')
    with urllib.request.urlopen(req,timeout=22) as r:return json.load(r)

def signed_claims(id_token,client_id,nonce):
    jwk=jwt.PyJWKClient(JWKS,cache_jwk_set=True,lifespan=600)
    public=jwk.get_signing_key_from_jwt(id_token).key
    claims=jwt.decode(id_token,public,algorithms=['RS256'],audience=client_id,
                      issuer=AUTH,options={'require':['iss','sub','aud','exp','nonce']})
    if not secrets.compare_digest(str(claims.get('nonce','')),nonce):raise ValueError('OIDC nonce mismatch')
    return claims

def complete(state,code='',callback_client='',error=''):
    with LOCK:pending=PENDING.pop(state,None)
    if not pending or time.time()-pending['started']>600:raise ValueError('Sign-in attempt expired or state invalid')
    if error:raise ValueError('Sign-in was not approved')
    if not code:raise ValueError('Missing OAuth authorization code')
    original=pending['client_id']
    if original=='dynamic_agent_client':
        if not callback_client or callback_client=='dynamic_agent_client':raise ValueError('No issued client ID returned')
        client=callback_client
    else:
        if callback_client and callback_client!=original:raise ValueError('Client ID changed unexpectedly')
        client=original
    data=post_form(TOKEN,{'grant_type':'authorization_code','client_id':client,'code':code,
                           'code_verifier':pending['verifier'],'redirect_uri':pending['redirect'],
                           'resource':RESOURCE})
    claims=signed_claims(data['id_token'],client,pending['nonce'])
    if pending.get('prior_subject') and claims['sub']!=pending['prior_subject']:
        raise ValueError('Signed-in ChatGPT identity differs from saved account')
    scopes=str(data.get('scope','')).split()
    if not data.get('access_token') or not data.get('id_token'):raise ValueError('OpenAI did not return verifiable credentials')
    profile={'client_id':client,'subject':claims['sub'],'issuer':AUTH,'email':claims.get('email') or '',
          'scopes':scopes,'access_token':data['access_token'],'refresh_token':data.get('refresh_token'),
          'id_token':data['id_token'],'expires_at':time.time()+int(data.get('expires_in',3600)),
          'saved_at':time.time()}
    with LOCK:atomic_write(path('chatgpt.json'),profile)
    return status()

def disconnect():
    with LOCK:
        p=path('chatgpt.json')
        if p.exists():p.unlink()
        MODEL_CACHE.clear()
    return status()

def access_token():
    with LOCK:
        p=read_record('chatgpt.json')
        if not p:raise ValueError('Connect ChatGPT before enabling AI')
        if 'chatgpt.tokens.use.direct' not in p.get('scopes',[]):raise ValueError('Grant ChatGPT plan usage permission')
        if float(p.get('expires_at',0))>time.time()+90:return p['access_token']
        refresh=p.get('refresh_token')
        if not refresh:raise ValueError('Session expired; reconnect ChatGPT')
        data=post_form(TOKEN,{'grant_type':'refresh_token','refresh_token':refresh,
                              'client_id':p['client_id'],'resource':RESOURCE})
        if not data.get('access_token'):raise ValueError('OpenAI token refresh did not return access token')
        p['access_token']=data['access_token'];p['refresh_token']=data.get('refresh_token') or refresh
        p['expires_at']=time.time()+int(data.get('expires_in',3600));p['saved_at']=time.time()
        if 'scope' in data:p['scopes']=str(data['scope']).split()
        if 'id_token' in data:p['id_token']=data['id_token']
        atomic_write(path('chatgpt.json'),p)
        return p['access_token']

def get_json(url,token):
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/json',
                                           'User-Agent':'NarrativeOS/0.2'})
    with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)

def models():
    token=access_token();now=time.time()
    if MODEL_CACHE.get('expires',0)>now:return MODEL_CACHE['list']
    result=get_json(RESOURCE+'/models',token)
    names=result.get('models') or result.get('data') or []
    parsed=[{'slug':m.get('slug') or m.get('id'),'name':m.get('display_name') or m.get('slug') or m.get('id')}
            for m in names if m.get('visibility','list')=='list' and (m.get('slug') or m.get('id'))]
    MODEL_CACHE.update({'list':parsed,'expires':now+600})
    return parsed

def response_text(token,model,input_text,instructions):
    """Complies with plan-usage streaming contract: store=false, stream=true."""
    request={'model':model,'input':[{'role':'user','content':input_text}],
             'instructions':instructions,'store':False,'stream':True}
    req=urllib.request.Request(RESOURCE+'/responses',data=json.dumps(request).encode(),
       headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Accept':'text/event-stream'},method='POST')
    out=[];completed=False
    with urllib.request.urlopen(req,timeout=90) as r:
        for raw in r:
            line=raw.decode('utf-8',errors='replace').strip()
            if not line.startswith('data:'):continue
            data=line[5:].strip()
            if data=='[DONE]':continue
            try:event=json.loads(data)
            except ValueError:continue
            typ=event.get('type')
            if typ=='response.output_text.delta':out.append(event.get('delta',''))
            elif typ=='response.failed':raise ValueError(str(event.get('response',{}).get('error','AI stream failed'))[:200])
            elif typ=='response.incomplete':raise ValueError('AI stream incomplete')
            elif typ=='response.completed':completed=True
    if not completed:raise ValueError('AI response stream ended without completion')
    return ''.join(out)

def infer_json(instructions,payload):
    model=os.getenv('SIWC_MODEL') or next((m['slug'] for m in models()),None)
    if not model:raise ValueError('No models available through connected ChatGPT plan')
    text=response_text(access_token(),model,json.dumps(payload,ensure_ascii=False),instructions)
    # Model should return raw JSON; remove harmless markdown fencing if present.
    text=text.strip()
    if text.startswith('```'):
        text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    return json.loads(text)