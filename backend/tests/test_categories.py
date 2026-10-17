import pytest

@pytest.mark.parametrize('label',['Pictures','pictures',' PICTURES '])
def test_submit_category_with_token(admin,destination,label):
    token=admin.post('/api/tokens',json={'name':'Category client'}).json()['token']
    admin.cookies.clear();admin.headers.pop('X-CSRF-Token')
    r=admin.post('/api/downloads',headers={'Authorization':'Bearer '+token},json={'url':'https://example.com/gallery','category':label})
    assert r.status_code==201,r.text
    assert r.json()['destination_id']==destination['id']
    assert r.json()['destination_path']==destination['path']

def test_invalid_or_ambiguous_category(admin,destination):
    for data in ({},{'category':' '},{'category':'Pictures','destination_id':destination['id']}):
        assert admin.post('/api/downloads',json={'url':'https://example.com/gallery',**data}).status_code==422
    for label in ('Missing','../../etc','/etc'):
        assert admin.post('/api/downloads',json={'url':'https://example.com/gallery','category':label}).status_code==404
    extra=admin.root/'other';extra.mkdir()
    assert admin.post('/api/destinations',json={'name':'PICTURES','path':str(extra)}).status_code==201
    assert admin.post('/api/downloads',json={'url':'https://example.com/gallery','category':'pictures'}).status_code==409
    assert admin.post('/api/downloads',json={'url':'https://example.com/gallery','destination_id':destination['id']}).status_code==201

def test_category_snapshot_and_duplicate_archive_destination(admin,destination):
    first=admin.post('/api/downloads',json={'url':'https://example.com/gallery','category':'Pictures'})
    assert first.status_code==201
    assert admin.post('/api/downloads',json={'url':'https://example.com/gallery','destination_id':destination['id']}).status_code==409
    admin.patch('/api/destinations/'+destination['id'],json={'name':'Renamed'})
    saved=admin.get('/api/downloads/'+first.json()['id']).json()
    assert saved['destination_name']=='Pictures' and saved['destination_path']==destination['path']
