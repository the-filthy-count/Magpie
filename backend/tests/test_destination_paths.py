import pytest


def test_path_edit_keeps_history_and_archive_snapshot(admin,destination):
    first=admin.post('/api/downloads',json={'url':'https://example.com/first','destination_id':destination['id']}).json()
    admin.post('/api/downloads/'+first['id']+'/cancel')
    old=admin.app_ref.state.store.one('SELECT * FROM jobs WHERE id=?',(first['id'],))
    assert old['archive_id']==destination['id']
    original=admin.root/'pictures'/'keep.jpg';original.write_bytes(b'keep')
    archive=admin.config/'archives'/destination['id'];archive.mkdir(parents=True)
    (archive/'archive.sqlite3').write_bytes(b'preserved archive')
    target=admin.root/'new';target.mkdir()
    r=admin.patch('/api/destinations/'+destination['id'],json={'path':str(target)})
    assert r.status_code==200,r.text
    assert r.json()['path']==str(target) and 'archive_id' not in r.json()
    newdest=admin.app_ref.state.store.one('SELECT * FROM destinations WHERE id=?',(destination['id'],))
    assert newdest['archive_id']!=destination['id']
    second=admin.post('/api/downloads',json={'url':'https://example.com/second','category':'Pictures'}).json()
    new=admin.app_ref.state.store.one('SELECT * FROM jobs WHERE id=?',(second['id'],))
    assert new['destination_path']==str(target) and new['archive_id']==newdest['archive_id']
    retried=admin.post('/api/downloads/'+first['id']+'/retry').json()
    assert retried['destination_path']==destination['path']
    assert admin.app_ref.state.store.one('SELECT * FROM jobs WHERE id=?',(first['id'],))['archive_id']==destination['id']
    assert original.read_bytes()==b'keep'
    assert (archive/'archive.sqlite3').read_bytes()==b'preserved archive'


@pytest.mark.parametrize('status',['queued','downloading'])
def test_active_jobs_block_path_changes(admin,destination,status):
    job=admin.post('/api/downloads',json={'url':'https://example.com/gallery','destination_id':destination['id']}).json()
    admin.app_ref.state.store.execute('UPDATE jobs SET status=? WHERE id=?',(status,job['id']))
    target=admin.root/'new';target.mkdir()
    assert admin.patch('/api/destinations/'+destination['id'],json={'path':str(target)}).status_code==409
    assert admin.patch('/api/destinations/'+destination['id'],json={'name':'Renamed','path':destination['path']}).status_code==200


def test_changed_path_boundaries_and_existing_destinations(admin,destination,tmp_path):
    outside=tmp_path/'outside';outside.mkdir()
    (admin.root/'escape').symlink_to(outside,target_is_directory=True)
    for path in (str(outside),str(admin.root/'escape'),str(admin.root/'../outside'),str(admin.root/'missing')):
        assert admin.patch('/api/destinations/'+destination['id'],json={'path':path}).status_code in (400,404)
    other=admin.root/'other';other.mkdir()
    admin.post('/api/destinations',json={'name':'Other','path':str(other)})
    assert admin.patch('/api/destinations/'+destination['id'],json={'path':str(other)}).status_code==409
    assert admin.get('/api/destinations').json()[0]['path']==destination['path']
