import hashlib
import time
from app.main import create_app
from fastapi.testclient import TestClient

def issue(admin):
    r=admin.post('/api/tokens',json={'name':'Gallery app','expires_days':30})
    assert r.status_code==201,r.text
    return r.json()

def test_token_management_is_admin_only(client,admin):
    # client and admin share the fixture; drop cookies to test no session.
    client.cookies.clear()
    assert client.get('/api/tokens').status_code==401

def test_token_download_workflow_and_scope(admin,destination):
    token=issue(admin)
    auth={'Authorization':'Bearer '+token['token']}
    stored=admin.app_ref.state.store.one('SELECT * FROM api_tokens WHERE id=?',(token['id'],))
    assert stored['digest']==hashlib.sha256(token['token'].encode()).hexdigest()
    assert token['token'] not in admin.get('/api/tokens').text
    assert 'digest' not in admin.get('/api/tokens').text
    admin.cookies.clear(); admin.headers.pop('X-CSRF-Token')
    assert admin.get('/api/destinations',headers=auth).status_code==200
    job=admin.post('/api/downloads',headers=auth,json={'url':'https://example.com/gallery','destination_id':destination['id']})
    assert job.status_code==201,job.text
    ident=job.json()['id']
    admin.app_ref.state.store.execute('UPDATE jobs SET files=3,skipped=2,total_files=20,file_bytes=512,file_total=1024,speed=128 WHERE id=?',(ident,))
    progress=admin.get('/api/downloads/'+ident,headers=auth).json()
    assert [progress[k] for k in ('files','skipped','total_files','file_bytes','file_total','speed')]==[3,2,20,512,1024,128]
    assert admin.post('/api/downloads/'+ident+'/cancel',headers=auth).status_code==200
    assert admin.post('/api/downloads/'+ident+'/retry',headers=auth).status_code==200
    for path in ('/api/settings','/api/cookies','/api/tokens','/api/roots','/api/folders','/api/auth/sessions'):
        assert admin.get(path,headers=auth).status_code==403
    assert admin.post('/api/tokens',headers=auth,json={'name':'bad'}).status_code==403
    assert admin.delete('/api/downloads/'+ident,headers=auth).status_code==403
    assert admin.post('/api/downloads',headers=auth,json={'url':'http://127.0.0.1/file','destination_id':destination['id']}).status_code==400

def test_expiration_revocation_and_persistence(admin):
    token=issue(admin);auth={'Authorization':'Bearer '+token['token']}
    other=create_app(admin.config,[admin.root],start_queue=False)
    c=TestClient(other)
    assert c.get('/api/downloads',headers=auth).status_code==200
    c.close()
    assert admin.delete('/api/tokens/'+token['id']).status_code==200
    assert admin.get('/api/downloads',headers=auth).status_code==401
    token=issue(admin);auth={'Authorization':'Bearer '+token['token']}
    admin.app_ref.state.store.execute('UPDATE api_tokens SET expires_at=? WHERE id=?',(time.time()-1,token['id']))
    assert admin.get('/api/events',headers=auth).status_code==401
    assert admin.get('/api/downloads',headers={'Authorization':'Bearer invalid'}).status_code==401
    assert admin.post('/api/tokens',json={'name':'','expires_days':0}).status_code==422


def test_stream_reports_file_and_album_changes_and_revocation(admin,destination,monkeypatch):
    import asyncio
    import json
    token=issue(admin)
    job=admin.post('/api/downloads',json={'url':'https://example.com/stream','destination_id':destination['id']}).json()
    endpoint=next(r.endpoint for r in admin.app_ref.routes if getattr(r,'path',None)=='/api/events')
    class Request:
        async def is_disconnected(self): return False
    async def no_sleep(_): pass
    monkeypatch.setattr('app.main.asyncio.sleep',no_sleep)
    async def exercise():
        response=await endpoint(Request(),{'api_token':token['id']})
        first=await anext(response.body_iterator)
        assert 'event: update' in first
        admin.app_ref.state.store.execute('UPDATE jobs SET file_bytes=50,file_total=100,total_files=20 WHERE id=?',(job['id'],))
        changed=await anext(response.body_iterator)
        data=json.loads(changed.split('data: ')[1])['downloads'][0]
        assert data['file_bytes']==50 and data['total_files']==20
        assert token['token'] not in changed
        admin.app_ref.state.store.execute('DELETE FROM api_tokens WHERE id=?',(token['id'],))
        assert 'event: expired' in await anext(response.body_iterator)
        await response.body_iterator.aclose()
    asyncio.run(exercise())


def test_admin_csrf_and_password_change_revokes_tokens(admin):
    token=issue(admin)
    assert admin.post('/api/tokens',json={'name':'blocked'},headers={'X-CSRF-Token':''}).status_code==403
    assert admin.get('/api/openapi.json',headers={'Authorization':'Bearer '+token['token']}).json()['components']['securitySchemes']['AppToken']['scheme']=='bearer'
    assert admin.post('/api/auth/password',json={'current_password':'correct horse battery staple','password':'replacement password long enough'}).status_code==200
    assert admin.get('/api/downloads',headers={'Authorization':'Bearer '+token['token']}).status_code==401


def test_non_expiring_token_remains_valid_and_revocable(admin,monkeypatch):
    response=admin.post('/api/tokens',json={'name':'Permanent client','expires_days':None})
    assert response.status_code==201,response.text
    token=response.json()
    assert token['expires_at'] is None
    assert next(t for t in admin.get('/api/tokens').json() if t['id']==token['id'])['expires_at'] is None
    auth={'Authorization':'Bearer '+token['token']}
    future=time.time()+86400*365*20
    with monkeypatch.context() as patch:
        patch.setattr('app.main.time.time',lambda:future)
        assert admin.get('/api/downloads',headers=auth).status_code==200
    assert admin.delete('/api/tokens/'+token['id']).status_code==200
    assert admin.get('/api/downloads',headers=auth).status_code==401
