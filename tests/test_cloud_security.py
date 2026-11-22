import os
import time
import pytest
from fastapi.testclient import TestClient
import cloud_security as cs

@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv('CLOUD_MODE','1')
    monkeypatch.setenv('APP_PASSWORD','A-Secure-Test-Password-123!')
    monkeypatch.setenv('APP_SESSION_SECRET','S'*60)
    cs.ATTEMPTS.clear()
    from app import app
    return TestClient(app, base_url='https://testserver')

def test_requires_secret_settings(monkeypatch):
    monkeypatch.setenv('CLOUD_MODE','1')
    monkeypatch.setenv('APP_PASSWORD','weak')
    monkeypatch.setenv('APP_SESSION_SECRET','short')
    with pytest.raises(RuntimeError):cs.validate_config()

def test_login_gate_and_health(cloud):
    assert cloud.get('/health').status_code==200
    assert cloud.get('/').status_code==200 # follows redirect to login
    assert 'Private sign-in' in cloud.get('/').text
    assert cloud.get('/api/bootstrap').status_code==401
    assert cloud.get('/static/index.html').url.path=='/login'
    assert cloud.post('/api/demo/reset',headers={'origin':'https://testserver'}).status_code==401

def test_login_and_cookie_scope(cloud):
    r=cloud.post('/login',data={'password':'A-Secure-Test-Password-123!'},headers={'Origin':'https://testserver'},follow_redirects=False)
    assert r.status_code==303
    cookie=r.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
    assert cloud.get('/api/bootstrap?mode=demo').status_code==200
    assert cloud.get('/').status_code==200
    assert cloud.post('/api/demo/reset',headers={'Origin':'https://evil.example'}).status_code==403
    assert cloud.post('/logout',headers={'Origin':'https://testserver'},follow_redirects=False).status_code==303
    assert cloud.get('/api/bootstrap').status_code==401

def test_login_bad_password_and_rate_limit(cloud):
    for i in range(6):
        r=cloud.post('/login',data={'password':'wrong-password'},headers={'Origin':'https://testserver'})
        assert r.status_code==401
    assert cloud.post('/login',data={'password':'A-Secure-Test-Password-123!'},headers={'Origin':'https://testserver'}).status_code==401

def test_session_expires_and_password_change(monkeypatch):
    monkeypatch.setenv('APP_PASSWORD','A-Secure-Test-Password-123!')
    monkeypatch.setenv('APP_SESSION_SECRET','S'*60)
    token=cs.make_cookie(now=1_800_000_000)
    assert cs.valid_cookie(token,now=1_800_000_001)
    assert not cs.valid_cookie(token,now=1_800_000_000+cs.SESS_AGE+1)
    monkeypatch.setenv('APP_PASSWORD','A-Different-Password-456!')
    assert not cs.valid_cookie(token,now=1_800_000_001)

def test_oauth_disabled_on_cloud(cloud):
    r=cloud.post('/login',data={'password':'A-Secure-Test-Password-123!'},headers={'Origin':'https://testserver'})
    assert r.status_code==200
    r=cloud.post('/api/auth/start',headers={'Origin':'https://testserver'})
    assert r.status_code==409

def test_cloud_ui_config(cloud):
    cloud.post('/login',data={'password':'A-Secure-Test-Password-123!'},headers={'Origin':'https://testserver'})
    data=cloud.get('/api/bootstrap').json()
    assert data['cloud_deployment'] is True
    assert data['auth']['api_key_configured'] is False
    assert cloud.post('/api/ai/automatic',headers={'Origin':'https://testserver'},json={'enabled':True}).status_code==409