from pathlib import Path
from app.main import create_app

def test_auth_setup_csrf_and_logout(client):
    assert client.get('/api/downloads').status_code==401
    assert client.post('/api/auth/setup',json={'password':'a sufficiently long password'}).status_code==403
    r=client.post('/api/auth/setup',json={'password':'a sufficiently long password'},headers={'X-Setup-Token':client.setup_token})
    assert r.status_code==200
    assert not (client.config/'setup-token').exists()
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert client.patch('/api/settings',json={'concurrency':3}).status_code==403
    client.headers['X-CSRF-Token']=r.json()['csrf']
    assert client.patch('/api/settings',json={'concurrency':3}).status_code==200
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/settings').status_code==401

def test_rate_limits(client):
    for _ in range(10):client.post('/api/auth/login',json={'password':'wrong'})
    assert client.post('/api/auth/login',json={'password':'wrong'}).status_code==429

def test_cross_origin(admin):
    assert admin.patch('/api/settings',json={},headers={'origin':'https://evil.example'}).status_code==403

def test_password_and_sessions(admin):
    assert admin.post('/api/auth/password',json={'current_password':'wrong','password':'new long enough password'}).status_code==403
    assert admin.get('/api/auth/sessions').json()[0]['current']==1
    assert admin.post('/api/auth/password',json={'current_password':'correct horse battery staple','password':'new long enough password'}).status_code==200
    assert admin.get('/api/downloads').status_code==401
    assert admin.post('/api/auth/login',json={'password':'new long enough password'}).status_code==200

def test_destinations_and_jobs(admin,destination):
    assert destination['writable'] and destination['is_default']
    assert admin.post('/api/destinations',json={'name':'Bad','path':'/etc'}).status_code==400
    assert admin.post('/api/downloads',json={'url':'http://127.0.0.1','destination_id':destination['id']}).status_code==400
    assert admin.post('/api/downloads',json={'url':'https://example.com/gallery','destination_id':'missing'}).status_code==404
    r=admin.post('/api/downloads',json={'url':'https://example.com/gallery','destination_id':destination['id']})
    assert r.status_code==201,r.text
    job=r.json();ident=job['id'];assert job['status']=='queued'
    assert admin.delete('/api/destinations/'+destination['id']).status_code==409
    assert admin.delete('/api/downloads/'+ident).status_code==409
    assert admin.patch('/api/destinations/'+destination['id'],json={'name':'Renamed'}).status_code==200
    assert admin.get('/api/downloads/'+ident).json()['destination_name']=='Pictures'
    assert len(admin.get('/api/downloads?q=gallery&status=queued').json())==1
    assert admin.post('/api/downloads/'+ident+'/cancel').status_code==200
    assert admin.get('/api/downloads/'+ident).json()['status']=='cancelled'
    assert admin.post('/api/downloads/'+ident+'/retry').json()['status']=='queued'
    assert admin.post('/api/downloads/'+ident+'/retry').status_code==409
    admin.post('/api/downloads/'+ident+'/cancel')
    media=Path(destination['path'])/'keep.jpg';media.write_bytes(b'media')
    assert admin.delete('/api/downloads').status_code==200
    assert media.exists()
    assert admin.delete('/api/destinations/'+destination['id']).status_code==200
    assert media.exists()

def test_cookie_handling(admin):
    content=b'# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t2147483647\tsession\tTOP-SECRET\n'
    r=admin.post('/api/cookies',data={'website':'example.com'},files={'file':('cookies.txt',content,'text/plain')})
    assert r.status_code==201,r.text
    ident=r.json()['id'];target=admin.config/'cookies'/f'{ident}.txt'
    assert 'TOP-SECRET' not in r.text and 'TOP-SECRET' not in admin.get('/api/cookies').text
    assert target.stat().st_mode & 0o777==0o600
    assert admin.post('/api/cookies',data={'website':'other.com'},files={'file':('c.txt',content)}).status_code==400
    assert admin.post('/api/cookies',data={'website':'example.com'},files={'file':('c.txt',b'not cookies')}).status_code==400
    assert admin.delete('/api/cookies/'+ident).status_code==200
    assert not target.exists()

def test_settings_validate(admin):
    for body in ({'concurrency':6},{'advanced':{'exec':'touch /tmp/x'}},{'filename':'{x.__class__}'},{'directory':['../../etc']}):
        assert admin.patch('/api/settings',json=body).status_code in (400,422),body
    assert admin.patch('/api/settings',json={'advanced':{'sleep-request':1}}).status_code==200
    assert admin.get('/api/openapi.json').status_code==200
    assert admin.get('/api/health').json()=={'status':'ok'}
    assert admin.get('/api/not-real').status_code==404

def test_persistence(admin,destination):
    admin.patch('/api/settings',json={'concurrency':4})
    job=admin.post('/api/downloads',json={'url':'https://example.com/x','destination_id':destination['id']}).json()
    other=create_app(admin.config,[admin.root],start_queue=False)
    assert other.state.store.get('settings')['concurrency']==4
    assert other.state.store.one('SELECT id FROM jobs WHERE id=?',(job['id'],))
    assert other.state.store.one('SELECT id FROM destinations WHERE id=?',(destination['id'],))

def test_duplicate_active_download_rejected(admin,destination):
    body={'url':'https://example.com/gallery','destination_id':destination['id']}
    assert admin.post('/api/downloads',json=body).status_code==201
    assert admin.post('/api/downloads',json=body).status_code==409

def test_validation_errors_do_not_echo_secrets(admin):
    r=admin.patch('/api/settings',json={'advanced':{'cookies':'NEVER-ECHO-THIS'}})
    assert r.status_code==422
    assert 'NEVER-ECHO-THIS' not in r.text
    r=admin.post('/api/auth/password',json={'password':'NEVER-ECHO-THIS'})
    assert 'NEVER-ECHO-THIS' not in r.text
