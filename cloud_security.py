"""Single-user cloud login gate for Narrative OS.

Cloud mode is explicitly enabled by CLOUD_MODE=1. All app and API routes,
including static assets and OAuth endpoints, are private except health/login.
A signed, expiring HttpOnly cookie is used over HTTPS; no credentials in URLs.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import html
import os
import secrets
import threading
import time
import urllib.parse
from collections import defaultdict
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

COOKIE='nos_session'
SESS_AGE=60*60*24*7
LOCK=threading.RLock()
ATTEMPTS=defaultdict(list)

def enabled():return os.getenv('CLOUD_MODE','0')=='1'

def secret_settings():
    pwd=os.getenv('APP_PASSWORD','')
    key=os.getenv('APP_SESSION_SECRET','')
    if len(pwd)<12 or len(key)<32:
        raise RuntimeError('Cloud deployment requires APP_PASSWORD (12+ chars) and APP_SESSION_SECRET (32+ chars)')
    return pwd,key.encode('utf-8')

def validate_config():
    if enabled():secret_settings()

def b64(data:bytes):return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')
def unb64(value:str):return base64.urlsafe_b64decode(value+'='*((-len(value))%4))

def password_marker(pwd,key):return hmac.new(key,b'password:'+pwd.encode(),hashlib.sha256).hexdigest()[:24]

def make_cookie(now=None):
    pwd,key=secret_settings()
    now=int(time.time() if now is None else now)
    data=f'{now+SESS_AGE}.{password_marker(pwd,key)}'.encode('ascii')
    sig=hmac.new(key,data,hashlib.sha256).digest()
    return b64(data)+'.'+b64(sig)

def valid_cookie(raw,now=None):
    if not raw or len(raw)>400:return False
    try:
        a,b=raw.split('.',1)
        data=unb64(a);provided=unb64(b)
        pwd,key=secret_settings()
        expected=hmac.new(key,data,hashlib.sha256).digest()
        exp,marker=data.decode('ascii').split('.',1)
        ts=int(time.time() if now is None else now)
        return (hmac.compare_digest(provided,expected) and
                hmac.compare_digest(marker,password_marker(pwd,key)) and ts<int(exp) and ts>=int(exp)-SESS_AGE)
    except (ValueError,UnicodeError,OverflowError,TypeError):return False

def same_origin(request:Request):
    origin=request.headers.get('origin','')
    if not origin:
        ref=request.headers.get('referer','')
        if ref:origin=urllib.parse.urlsplit(ref).scheme+'://'+urllib.parse.urlsplit(ref).netloc
    if not origin:return False
    try:
        url=urllib.parse.urlsplit(origin)
        hostname=(url.hostname or '').lower()
        target=request.headers.get('host','').split(':')[0].lower()
        # Allows the HTTPS browser origin to match Render's public hostname.
        # TestClient uses HTTP; public cloud never accepts plain HTTP origin.
        return bool(hostname) and hostname==target and url.scheme in ('https','http') and (url.scheme=='https' or target in ('localhost','127.0.0.1','testserver'))
    except ValueError:return False

HTML_HEAD='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#090e19"><title>Narrative OS · Private sign-in</title><style>
*{box-sizing:border-box}body{font:15px/1.55 -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;background:#090e19;color:#eaf2f9;min-height:100vh;margin:0;display:grid;place-items:center;padding:24px}main{background:#111b2d;border:1px solid #283b50;border-radius:18px;padding:30px;width:min(100%,420px);box-shadow:0 15px 45px #0005}h1{font-size:24px;margin:0 0 7px}p{color:#9aacc0;margin:0 0 24px}label{display:block;font-size:12px;font-weight:650;margin:16px 0 8px}input{display:block;width:100%;font-size:16px;padding:14px;color:#fff;background:#07111d;border:1px solid #54657e;border-radius:10px}button{margin-top:20px;display:block;width:100%;padding:14px;border-radius:10px;border:0;background:#66ddbb;color:#072920;font-weight:750;font-size:15px}small{display:block;color:#8094aa;margin-top:18px}.error{padding:12px;background:#43272c;color:#ffc1c6;border-radius:9px;margin-bottom:16px}</style></head><body><main><h1>NARRATIVE OS</h1><p>Private macro intelligence workspace. Sign in to continue.</p>'''

def login_page(error=False):
    msg='<div class="error" role="alert">Incorrect password or too many attempts. Try again later.</div>' if error else ''
    body=HTML_HEAD+msg+'''<form method="post" action="/login"><label for="password">Workspace password</label><input name="password" id="password" type="password" autocomplete="current-password" minlength="12" required autofocus><button type="submit">Unlock workspace</button></form><small>HTTPS protected · Single owner · Session expires in 7 days</small></main></body></html>'''
    return HTMLResponse(body,status_code=401 if error else 200,headers={'Cache-Control':'no-store'})

async def login_post(request:Request):
    # Origin and referer validation prevents a cross-site login form submission.
    if not same_origin(request):raise HTTPException(403,'Incorrect request origin')
    raw=await request.body()
    if len(raw)>8192:raise HTTPException(413,'Request too large')
    try:password=urllib.parse.parse_qs(raw.decode('utf-8'),keep_blank_values=True).get('password',[''])[0]
    except UnicodeError:password=''
    ip=request.client.host if request.client else 'unknown'
    now=time.time()
    with LOCK:
        prior=[x for x in ATTEMPTS[ip] if now-x<900]
        ATTEMPTS[ip]=prior
        limited=len(prior)>=6
    pwd,key=secret_settings()
    ok=(not limited and hmac.compare_digest(hashlib.sha256(password.encode('utf-8')).digest(),hashlib.sha256(pwd.encode('utf-8')).digest()))
    if not ok:
        with LOCK:ATTEMPTS[ip].append(now)
        return login_page(error=True)
    with LOCK:ATTEMPTS.pop(ip,None)
    response=RedirectResponse('/',status_code=303)
    response.set_cookie(COOKIE,make_cookie(now),max_age=SESS_AGE,secure=True,httponly=True,samesite='strict',path='/')
    response.headers['Cache-Control']='no-store'
    return response

async def logout_post(request:Request):
    response=RedirectResponse('/login',status_code=303)
    response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
    response.headers['Cache-Control']='no-store'
    return response

async def auth_gate(request:Request,call_next):
    if not enabled():return await call_next(request)
    path=request.url.path
    if path=='/health':return await call_next(request)
    if path=='/login' and request.method in ('GET','POST'):
        return await call_next(request)
    if not valid_cookie(request.cookies.get(COOKIE,'')):
        if path.startswith('/api/') or path.startswith('/auth/') or request.method!='GET':
            return PlainTextResponse('Authentication required',status_code=401,headers={'Cache-Control':'no-store'})
        return RedirectResponse('/login',status_code=303)
    if request.method not in ('GET','HEAD','OPTIONS') and not same_origin(request):
        return PlainTextResponse('Request origin blocked',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="frame-ancestors 'none'; object-src 'none'"
    response.headers['Cache-Control']='no-store'
    return response