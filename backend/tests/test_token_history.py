import pytest
from app.downloads.queue import now


def auth(admin):
    token=admin.post('/api/tokens',json={'name':'History client'}).json()['token']
    admin.cookies.clear();admin.headers.pop('X-CSRF-Token')
    return {'Authorization':'Bearer '+token}


def job(admin,destination,headers,suffix,status):
    r=admin.post('/api/downloads',headers=headers,json={'url':'https://example.com/'+suffix,'category':'Pictures'})
    assert r.status_code==201,r.text
    ident=r.json()['id']
    admin.app_ref.state.store.execute('UPDATE jobs SET status=?,completed_at=? WHERE id=?',(status,now(),ident))
    return ident


@pytest.mark.parametrize('status',['completed','failed','cancelled','interrupted'])
def test_tokens_remove_finished_entries_only(admin,destination,status):
    headers=auth(admin)
    ident=job(admin,destination,headers,'finished',status)
    media=admin.root/'pictures'/'keep.jpg';media.write_bytes(b'media')
    archive=admin.config/'archives'/destination['id'];archive.mkdir(parents=True)
    (archive/'archive.sqlite3').write_bytes(b'archive')
    assert admin.delete('/api/downloads/'+ident,headers=headers).json()=={'ok':True}
    assert admin.get('/api/downloads/'+ident,headers=headers).status_code==404
    assert admin.delete('/api/downloads/'+ident,headers=headers).status_code==404
    assert media.read_bytes()==b'media' and (archive/'archive.sqlite3').read_bytes()==b'archive'


def test_bulk_history_keeps_active_jobs_and_restricts_other_deletes(admin,destination):
    headers=auth(admin)
    ids={s:job(admin,destination,headers,s,s) for s in ('queued','downloading','completed','failed','cancelled','interrupted')}
    for status in ('queued','downloading'):
        assert admin.delete('/api/downloads/'+ids[status],headers=headers).status_code==409
    assert admin.delete('/api/downloads',headers=headers).json()=={'ok':True}
    assert {r['id'] for r in admin.get('/api/downloads',headers=headers).json()}=={ids['queued'],ids['downloading']}
    for path in ('/api/destinations/'+destination['id'],'/api/tokens/anything','/api/cookies/anything','/api/auth/sessions'):
        assert admin.delete(path,headers=headers).status_code==403
    assert admin.delete('/api/downloads').status_code==401
    schema=admin.get('/api/openapi.json',headers=headers).json()
    assert {'AppToken':[]} in schema['paths']['/api/downloads/{ident}']['delete']['security']
    assert {'AppToken':[]} in schema['paths']['/api/downloads']['delete']['security']
