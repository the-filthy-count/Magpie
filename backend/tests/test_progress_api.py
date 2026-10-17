import asyncio
import json
import pytest
from app.core.progress import percentage

@pytest.mark.parametrize('done,total,expected',[(50,100,50.0),(0,100,0.0),(100,100,100.0),(1,3,33.33),(0,None,None),(None,100,None),(0,0,None),(101,100,None),(-1,10,None)])
def test_percentage_truthful(done,total,expected):
    assert percentage(done,total)==expected


def test_percentages_match_rest_and_live_events(admin,destination):
    token=admin.post('/api/tokens',json={'name':'Progress client'}).json()
    auth={'Authorization':'Bearer '+token['token']}
    job=admin.post('/api/downloads',headers=auth,json={'url':'https://example.com/gallery','category':'Pictures'}).json()
    assert job['file_progress_percent'] is None and job['album_progress_percent'] is None
    store=admin.app_ref.state.store
    store.execute("UPDATE jobs SET status='downloading',files=6,skipped=2,total_files=20,file_bytes=50,file_total=100 WHERE id=?",(job['id'],))
    for path in ('/api/downloads/'+job['id'],'/api/downloads'):
        data=admin.get(path,headers=auth).json()
        if isinstance(data,list):data=data[0]
        assert data['file_progress_percent']==50.0 and data['album_progress_percent']==40.0
    endpoint=next(r.endpoint for r in admin.app_ref.routes if getattr(r,'path',None)=='/api/events')
    class Request:
        async def is_disconnected(self):return False
    async def read():
        response=await endpoint(Request(),{'api_token':token['id']})
        event=await anext(response.body_iterator)
        row=json.loads(event.split('data: ')[1])['downloads'][0]
        assert row['file_progress_percent']==50.0 and row['album_progress_percent']==40.0
        await response.body_iterator.aclose()
    asyncio.run(read())
    store.execute('UPDATE jobs SET files=20,skipped=0,file_bytes=NULL,file_total=NULL WHERE id=?',(job['id'],))
    result=admin.get('/api/downloads/'+job['id'],headers=auth).json()
    assert result['file_progress_percent'] is None and result['album_progress_percent']==100.0


@pytest.mark.parametrize('files,skipped,file_bytes,file_total,expected',[(0,0,37,100,37.0),(0,0,3,10,30.0),(1,0,None,None,100.0),(0,1,None,None,100.0),(0,0,None,None,None)])
def test_single_file_rest_and_live_percentages(admin,destination,files,skipped,file_bytes,file_total,expected):
    token=admin.post('/api/tokens',json={'name':'Single-file client'}).json()
    auth={'Authorization':'Bearer '+token['token']}
    job=admin.post('/api/downloads',headers=auth,json={'url':'https://example.com/one.png','category':'Pictures'}).json()
    admin.app_ref.state.store.execute('UPDATE jobs SET total_files=1,files=?,skipped=?,file_bytes=?,file_total=? WHERE id=?',(files,skipped,file_bytes,file_total,job['id']))
    for path in ('/api/downloads/'+job['id'],'/api/downloads'):
        row=admin.get(path,headers=auth).json()
        if isinstance(row,list):row=row[0]
        assert row['file_progress_percent']==row['album_progress_percent']==expected
    endpoint=next(r.endpoint for r in admin.app_ref.routes if getattr(r,'path',None)=='/api/events')
    class Request:
        async def is_disconnected(self):return False
    async def read():
        response=await endpoint(Request(),{'api_token':token['id']})
        event=await anext(response.body_iterator)
        row=json.loads(event.split('data: ')[1])['downloads'][0]
        assert row['file_progress_percent']==row['album_progress_percent']==expected
        await response.body_iterator.aclose()
    asyncio.run(read())
