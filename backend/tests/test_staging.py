import errno
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest
from app.database.store import DEFAULTS
from app.downloads.staging import staging_location, prepare_staging, publish_files
from test_engine import PNG, SCRIPT


def test_paths_are_confined_and_snapshots_stay_separate(tmp_path):
    destination=tmp_path/'pictures';destination.mkdir()
    settings={**DEFAULTS,'in_progress_path':''}
    location=staging_location(str(destination),'job1',settings,[tmp_path])
    assert location==str(destination/'.magpie-in-progress/job1')
    assert prepare_staging(location,str(destination),[tmp_path])==location
    external=tmp_path/'external';external.mkdir()
    with pytest.raises(ValueError):prepare_staging(str(external/'job'),str(destination),[destination])
    (destination/'escape').symlink_to(external,target_is_directory=True)
    with pytest.raises(ValueError):prepare_staging(str(destination/'escape/job'),str(destination),[tmp_path])
    with pytest.raises(ValueError):staging_location(str(destination),'../bad',settings,[tmp_path])
    with pytest.raises(ValueError):staging_location(str(destination),'job',{**settings,'in_progress_path':str(tmp_path)},[tmp_path])


def test_publication_retry_conflicts_and_symlinks(tmp_path):
    source=tmp_path/'stage';source.mkdir();destination=tmp_path/'final';destination.mkdir()
    (source/'a.jpg').write_bytes(b'a');(source/'b.jpg').write_bytes(b'b')
    (destination/'b.jpg').write_bytes(b'conflict')
    with pytest.raises(FileExistsError):publish_files(source,destination,'job')
    assert (source/'a.jpg').exists() and (source/'b.jpg').exists()
    assert (destination/'b.jpg').read_bytes()==b'conflict'
    (destination/'b.jpg').unlink()
    publish_files(source,destination,'job')
    assert (destination/'a.jpg').read_bytes()==b'a'
    assert (destination/'b.jpg').read_bytes()==b'b'
    # Same contents can be published again after a crash without overwriting.
    publish_files(source,destination,'job')
    (source/'unfinished.jpg.part').write_bytes(b'x')
    with pytest.raises(ValueError):publish_files(source,destination,'job')
    (source/'unfinished.jpg.part').unlink()
    other=tmp_path/'other';other.mkdir();(source/'escape').symlink_to(other,target_is_directory=True)
    with pytest.raises(PermissionError):publish_files(source,destination,'job')


def test_cross_filesystem_copy_is_complete_and_retryable(tmp_path,monkeypatch):
    source=tmp_path/'stage';source.mkdir();destination=tmp_path/'final';destination.mkdir()
    payload=b'media'*100000;(source/'video.mp4').write_bytes(payload)
    original=os.link
    def cross_device(src,dst,**kwargs):
        if not str(src).startswith('.magpie-transfer-'):
            assert not (destination/dst).exists()
            raise OSError(errno.EXDEV,'controlled separate filesystem')
        assert (destination/src).read_bytes()==payload
        return original(src,dst,**kwargs)
    monkeypatch.setattr(os,'link',cross_device)
    publish_files(source,destination,'job')
    assert (destination/'video.mp4').read_bytes()==payload
    assert (source/'video.mp4').read_bytes()==payload
    assert not list(destination.glob('.magpie-transfer-*'))


def test_real_album_stays_staged_until_retry_completes(tmp_path):
    stage=tmp_path/'stage';stage.mkdir();destination=tmp_path/'final';destination.mkdir()
    archive=tmp_path/'archive';archive.mkdir();job_archive=archive/'jobs/job';job_archive.mkdir(parents=True)
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrAlbumExtractor
BunkrAlbumExtractor.fetch_album=lambda self,ident:([
 {'file':'https://93.184.216.34/first.png','name':'first.png','id':'first'},
 {'file':'https://93.184.216.34/second.png','name':'second.png','id':'second'},
],{'album_id':ident,'album_name':'Fixture','count':2})
sys.exit(run(spec))
''')
    failing=script.replace('response.status_code=200', "response.status_code=403 if request.url.endswith('second.png') else 200")
    spec=dict(url='https://bunkr.cr/a/FIXTURE',destination_path=str(stage),publish_destination=str(destination),published_archive=str(archive),job_id='job',archive=str(job_archive),settings={**DEFAULTS,'retries':0,'organisation':'flat'},payload=PNG.hex())
    def attempt(code):
        return subprocess.run([sys.executable,'-c',code],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    first=attempt(failing)
    assert first.returncode!=0,first.stdout+first.stderr
    assert (stage/'first.png').read_bytes()==PNG
    assert not list(destination.iterdir())
    assert not (archive/'archive.sqlite3').exists()
    with sqlite3.connect(job_archive/'archive.sqlite3') as con:
        assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==1
    second=attempt(script)
    assert second.returncode==0,second.stdout+second.stderr
    events=[json.loads(line) for line in second.stdout.splitlines()]
    assert any(e.get('skipped')==1 for e in events)
    assert any(e.get('files')==1 for e in events)
    assert any(e.get('phase')=='publishing' for e in events)
    assert (destination/'first.png').read_bytes()==PNG and (destination/'second.png').read_bytes()==PNG
    assert not list(stage.iterdir())
    with sqlite3.connect(archive/'archive.sqlite3') as con:
        assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==2
    # A separate job now consults the published archive and downloads nothing.
    new_stage=tmp_path/'next-stage';new_stage.mkdir()
    new_private=archive/'jobs/next-job';new_private.mkdir()
    spec.update(destination_path=str(new_stage),archive=str(new_private),job_id='next-job')
    third=attempt(script)
    assert third.returncode==0,third.stdout+third.stderr
    assert any(json.loads(line).get('skipped')==2 for line in third.stdout.splitlines())
    assert not list(new_stage.iterdir())


def test_settings_validate_and_jobs_snapshot_staging(admin,destination):
    stage=admin.root/'in-progress';stage.mkdir()
    r=admin.patch('/api/settings',json={'in_progress_path':str(stage),'publish_when_complete':True})
    assert r.status_code==200,r.text
    job=admin.post('/api/downloads',json={'url':'https://example.com/one.jpg','destination_id':destination['id']})
    assert job.status_code==201,job.text
    old=job.json()['staging_path'];assert old==str(stage/job.json()['id'])
    assert admin.patch('/api/settings',json={'in_progress_path':''}).status_code==200
    assert admin.get('/api/downloads/'+job.json()['id']).json()['staging_path']==old
    assert admin.patch('/api/settings',json={'in_progress_path':str(admin.root)}).status_code==400
    assert admin.patch('/api/settings',json={'in_progress_path':'/tmp'}).status_code==400
    assert admin.patch('/api/settings',json={'in_progress_path':str(admin.root/'missing')}).status_code==400
    assert admin.patch('/api/settings',json={'publish_when_complete':False}).status_code==200
    direct=admin.post('/api/downloads',json={'url':'https://example.com/two.jpg','destination_id':destination['id']})
    assert direct.json()['staging_path']==''


def test_real_engine_publication_across_filesystems(tmp_path):
    import tempfile
    if not Path('/dev/shm').is_dir() or not os.access('/dev/shm',os.W_OK):
        pytest.skip('Writable separate tmpfs is needed for this integration test')
    with tempfile.TemporaryDirectory(prefix='magpie-staging-',dir='/dev/shm') as folder:
        stage=Path(folder);destination=tmp_path/'final';destination.mkdir()
        if stage.stat().st_dev==destination.stat().st_dev:
            pytest.skip('Test needs separate filesystems')
        archive=tmp_path/'archive';archive.mkdir();job_archive=archive/'jobs/job';job_archive.mkdir(parents=True)
        spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(stage),publish_destination=str(destination),published_archive=str(archive),job_id='job',archive=str(job_archive),settings={**DEFAULTS,'organisation':'flat'},payload=PNG.hex())
        result=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
        assert result.returncode==0,result.stdout+result.stderr
        assert len(list(destination.glob('*.png')))==1
        assert next(destination.glob('*.png')).read_bytes()==PNG
        assert not list(stage.iterdir())


def test_final_destination_cannot_use_staging(admin,destination):
    stage=admin.root/'in-progress';stage.mkdir()
    assert admin.patch('/api/settings',json={'in_progress_path':str(stage)}).status_code==200
    assert admin.post('/api/destinations',json={'name':'Bad','path':str(stage)}).status_code==400
    assert admin.patch('/api/destinations/'+destination['id'],json={'path':str(stage)}).status_code==400


def test_real_publication_failure_keeps_archive_private_for_retry(tmp_path):
    stage=tmp_path/'stage';stage.mkdir();destination=tmp_path/'final';destination.mkdir()
    archive=tmp_path/'archive';archive.mkdir();private=archive/'jobs/job';private.mkdir(parents=True)
    target=destination/'fixture.png';target.write_bytes(b'existing file')
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(stage),publish_destination=str(destination),published_archive=str(archive),job_id='job',archive=str(private),settings={**DEFAULTS,'organisation':'flat','filename':'{filename}.{extension}'},payload=PNG.hex())
    def attempt():
        return subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    first=attempt();assert first.returncode!=0
    assert 'conflicting destination filename' in first.stdout
    assert target.read_bytes()==b'existing file'
    assert (stage/'fixture.png').read_bytes()==PNG
    assert not (archive/'archive.sqlite3').exists()
    target.unlink()
    second=attempt();assert second.returncode==0,second.stdout+second.stderr
    assert any(json.loads(line).get('skipped')==1 for line in second.stdout.splitlines())
    assert target.read_bytes()==PNG


def test_cancellation_retains_staging_snapshot(tmp_path,monkeypatch):
    import asyncio
    from app.database.store import Store
    from app.downloads.queue import Queue,now
    original=asyncio.create_subprocess_exec
    async def controlled(*args,**kwargs):
        code="import sys,json,time;from pathlib import Path;s=json.loads(sys.stdin.readline());p=Path(s['destination_path']);(p/'finished.jpg').write_bytes(b'finished');(p/'unfinished.jpg.part').write_bytes(b'partial');print(json.dumps({'files':1}),flush=True);time.sleep(60)"
        return await original(sys.executable,'-c',code,**kwargs)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',controlled)
    async def scenario():
        final=tmp_path/'final';final.mkdir();stage=tmp_path/'in-progress';stage.mkdir()
        store=Store(tmp_path/'db.sqlite3')
        prefs={**DEFAULTS,'in_progress_path':str(stage)};store.set('settings',prefs)
        snapshot=str(stage/'job')
        store.execute('INSERT INTO jobs(id,url,website,destination_id,destination_name,destination_path,created_at,staging_path) VALUES(?,?,?,?,?,?,?,?)',('job','https://example.com','example.com','dest','Pictures',str(final),now(),snapshot))
        queue=Queue(store,{'dir':tmp_path,'roots':[tmp_path],'job_timeout':60})
        await queue.start()
        try:
            for _ in range(100):
                if store.one("SELECT files FROM jobs WHERE id='job'")['files']:break
                await asyncio.sleep(.02)
            assert (Path(snapshot)/'finished.jpg').exists()
            store.execute("UPDATE jobs SET cancel_requested=1 WHERE id='job'")
            for _ in range(100):
                if store.one("SELECT status FROM jobs WHERE id='job'")['status']=='cancelled':break
                await asyncio.sleep(.02)
            assert store.one("SELECT status FROM jobs WHERE id='job'")['status']=='cancelled'
            assert (Path(snapshot)/'unfinished.jpg.part').exists()
            assert not list(final.iterdir())
        finally:
            await queue.stop()
    asyncio.run(scenario())
