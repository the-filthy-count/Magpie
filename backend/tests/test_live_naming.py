import json
import subprocess
import sys
from pathlib import Path
import pytest
from app.database.store import DEFAULTS
from app.downloads.naming import write_control
from test_engine import SCRIPT,PNG


def test_api_amends_live_metadata_and_locks_publication(admin,destination):
    created=admin.post('/api/downloads',json={'url':'https://example.com/a.png','destination_id':destination['id'],'custom_fields':{'creator':'Alice','tag':'Old'}}).json()
    ident=created['id'];store=admin.app_ref.state.store
    store.execute("UPDATE jobs SET status='downloading' WHERE id=?",(ident,))
    token=admin.post('/api/tokens',json={'name':'Tag editor'}).json()['token']
    result=admin.patch('/api/downloads/'+ident,headers={'Authorization':'Bearer '+token},json={'custom_fields':{'creator':'Alice','tag':'New'},'filename_position':'end'})
    assert result.status_code==200,result.text
    assert result.json()['custom_fields']['tag']=='New'
    baseline=json.loads(store.one('SELECT filename_baseline FROM jobs WHERE id=?',(ident,))['filename_baseline'])
    assert baseline['custom_fields']['tag']=='Old'
    control=admin.config/'job-controls'/f'{ident}.json'
    assert json.loads(control.read_text())['filename_position']=='end'
    before=control.read_bytes()
    store.execute("UPDATE jobs SET phase='publishing' WHERE id=?",(ident,))
    assert admin.patch('/api/downloads/'+ident,json={'custom_fields':{}}).status_code==409
    assert control.read_bytes()==before
    store.execute("UPDATE jobs SET status='completed' WHERE id=?",(ident,))
    assert admin.patch('/api/downloads/'+ident,json={'filename_position':'start'}).status_code==409
    for body in ({},{'filename_position':'middle'},{'custom_fields':{'tag':''}},{'custom_fields':{'tag':'x'*101}}):
        assert admin.patch('/api/downloads/'+ident,json=body).status_code==422


def live_spec(tmp_path, staged):
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir();final=tmp_path/'final';final.mkdir()
    control=write_control(tmp_path,dict(id='job',custom_fields={'tag':'Old'},filename_position='start'))
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat','filename':'{filename}.{extension}'},payload=(PNG+b'\0'*300000).hex(),naming_control=control,filename_baseline=dict(custom_fields={'tag':'Old'},filename_position='start'),job_id='job')
    if staged:
        shared=tmp_path/'shared';shared.mkdir()
        spec.update(publish_destination=str(final),published_archive=str(shared))
    return spec,root,final


def run_live(spec, script, callback):
    process=subprocess.Popen([sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    process.stdin.write(json.dumps(spec)+'\n');process.stdin.close()
    events=[]
    try:
        for line in process.stdout:
            event=json.loads(line);events.append(event);callback(event)
        process.wait(timeout=20)
        assert process.returncode==0,'\n'.join(map(str,events))+process.stderr.read()
    finally:
        if process.poll() is None:process.kill();process.wait()
    return events


@pytest.mark.parametrize('staged',[False,True])
def test_edit_during_real_http_transfer_preserves_partial_path(tmp_path,staged):
    spec,root,final=live_spec(tmp_path,staged)
    script=SCRIPT.replace('def send(self,request,**kwargs):', '''
import time
class Slow(io.BytesIO):
    def read(self,size=-1):
        time.sleep(.03)
        return super().read(min(size if size>=0 else 32768,32768))
def send(self,request,**kwargs):''').replace('io.BytesIO(payload)','Slow(payload)')
    changed=[]
    def callback(event):
        if event.get('current_filename') and event.get('file_bytes') == 0 and not changed:
            import time
            for _ in range(100):
                partial=list(root.glob('*.part'))
                if partial and partial[0].stat().st_size > 0:break
                time.sleep(.01)
            assert len(partial)==1 and partial[0].stat().st_size > 0
            changed.append(partial[0])
            write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'))
            assert partial[0].exists()
        if event.get('phase')=='publishing':
            write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'),frozen=True)
    events=run_live(spec,script,callback)
    assert [e['current_filename'] for e in events if 'current_filename' in e][-1]=='fixture - New.png'
    assert changed
    output=final if staged else root
    assert (output/'fixture - New.png').read_bytes()==bytes.fromhex(spec['payload'])
    assert not list(output.glob('*Old*'))
    assert not list(root.glob('*.part'))


def test_staged_album_retags_earlier_completed_files_too(tmp_path):
    spec,root,final=live_spec(tmp_path,True);spec['url']='https://bunkr.cr/a/FIXTURE'
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrAlbumExtractor
BunkrAlbumExtractor.fetch_album=lambda self,ident:([
{'file':'https://93.184.216.34/first.png','name':'first.png','id':'first'},
{'file':'https://93.184.216.34/second.png','name':'second.png','id':'second'}],{'album_id':ident,'album_name':'Fixture','count':2})
sys.exit(run(spec))
''')
    def callback(event):
        if event.get('files')==1:
            assert (root/'Old - first.png').exists()
            write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'))
        if event.get('phase')=='publishing':
            write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'),frozen=True)
    run_live(spec,script,callback)
    assert sorted(p.name for p in final.glob('*.png'))==['first - New.png','second - New.png']
    assert not list(root.iterdir())


def test_queue_publication_handshake_uses_latest_metadata(tmp_path,monkeypatch):
    import asyncio
    from app.database.store import Store
    from app.downloads.queue import Queue,now
    root=tmp_path/'root';root.mkdir();stage=root/'.magpie-in-progress/job';stage.mkdir(parents=True)
    store=Store(tmp_path/'db.sqlite3')
    store.execute('INSERT INTO jobs(id,url,website,destination_id,destination_name,destination_path,created_at,staging_path,custom_fields) VALUES(?,?,?,?,?,?,?,?,?)',('job','https://93.184.216.34/fixture.png','93.184.216.34','dest','Pictures',str(root),now(),str(stage),json.dumps({'tag':'Old'})))
    original=asyncio.create_subprocess_exec
    controlled=SCRIPT.replace("spec=json.loads(sys.stdin.readline())",f"spec=json.loads(sys.stdin.readline())\nspec['payload']={PNG.hex()!r}").replace('sys.exit(run(spec))',"import time\ntime.sleep(.3)\nsys.exit(run(spec))")
    async def child(*args,**kwargs):
        return await original(sys.executable,'-c',controlled,**kwargs)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',child)
    async def scenario():
        queue=Queue(store,{'dir':tmp_path,'roots':[root],'job_timeout':60})
        await queue.start()
        try:
            for _ in range(100):
                if store.one('SELECT filename_baseline FROM jobs')['filename_baseline']:break
                await asyncio.sleep(.01)
            with store.db() as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE jobs SET custom_fields=?,filename_position=?',(json.dumps({'tag':'New'}),'end'))
                row=dict(db.execute('SELECT * FROM jobs').fetchone())
                write_control(tmp_path,row)
            for _ in range(500):
                if store.one('SELECT status FROM jobs')['status']=='completed':break
                await asyncio.sleep(.01)
            row=store.one('SELECT * FROM jobs');assert row['status']=='completed',row['error']
            assert any(p.name.endswith(' - New.png') for p in root.glob('**/*.png'))
        finally:await queue.stop()
    asyncio.run(scenario())


def test_retry_with_new_tag_resumes_original_partial_file(tmp_path):
    spec,root,final=live_spec(tmp_path,False)
    failing=SCRIPT.replace('def send(self,request,**kwargs):', '''
class Broken(io.BytesIO):
    def read(self,size=-1):
        if self.tell()>=65536:
            from urllib3.exceptions import ProtocolError
            raise ProtocolError('controlled interruption')
        return super().read(min(size if size>=0 else 32768,32768))
def send(self,request,**kwargs):''').replace('io.BytesIO(payload)','Broken(payload)')
    spec['settings']['retries']=0
    first=subprocess.run([sys.executable,'-c',failing],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert first.returncode!=0
    part=next(root.glob('*.part'));retained=part.stat().st_size;assert retained>0
    assert 'Old' in part.name
    write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'))
    resume=SCRIPT.replace('    response.status_code=200', '''    offset=int(request.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
    print(json.dumps({'range_offset':offset}),flush=True)
    response.status_code=206 if offset else 200''').replace('    response.raw=HTTPResponse', "    if offset:\n        response.headers['Content-Range']=f'bytes {offset}-{len(payload)-1}/{len(payload)}'\n        response.headers['Content-Length']=str(len(payload)-offset)\n    response.raw=HTTPResponse").replace('io.BytesIO(payload)','io.BytesIO(payload[offset:])')
    second=subprocess.run([sys.executable,'-c',resume],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert second.returncode==0,second.stdout+second.stderr
    assert any(json.loads(line).get('range_offset')==retained for line in second.stdout.splitlines())
    assert (root/'fixture - New.png').read_bytes()==bytes.fromhex(spec['payload'])
    assert not list(root.glob('*.part'))


def test_tag_collision_never_overwrites_and_retry_renames_without_download(tmp_path):
    spec,root,final=live_spec(tmp_path,False)
    write_control(tmp_path,dict(id='job',custom_fields={'tag':'New'},filename_position='end'))
    target=root/'fixture - New.png';target.write_bytes(b'existing data')
    first=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert first.returncode!=0
    assert target.read_bytes()==b'existing data'
    assert (root/'Old - fixture.png').read_bytes()==bytes.fromhex(spec['payload'])
    target.unlink()
    second=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert second.returncode==0,second.stdout+second.stderr
    assert any(json.loads(line).get('skipped')==1 for line in second.stdout.splitlines())
    assert target.read_bytes()==bytes.fromhex(spec['payload'])
    assert not (root/'Old - fixture.png').exists()
