import asyncio
import json
from datetime import datetime
import pytest
from app.models.schemas import Settings
from app.database.store import Store, DEFAULTS
from app.downloads.options import effective_settings,schedule_allows,accepts_file,video_options
from app.downloads.queue import Queue
from test_engine import SCRIPT,PNG
import subprocess
import sys


def test_precedence_validation_and_snapshot(admin,destination):
    prefs={'organisation':'flat_gallery','video_quality':'1080','video_format':'mp4','playlist':'single',
           'media_filter':'images','max_files':5,'max_file_size':1048576,'subtitles':'automatic','subtitle_languages':['en'],
           'resume_interrupted':True,'schedule_enabled':True,'schedule_start':'22:00','schedule_end':'06:00',
           'site_rules':[{'website':'example.com','organisation':'organised','sleep_request':2,'retries':1}]}
    r=admin.patch('/api/settings',json=prefs);assert r.status_code==200,r.text
    assert admin.get('/api/settings').json()['video_quality']=='1080'
    d=admin.patch('/api/destinations/'+destination['id'],json={'organisation':'flat_gallery'}).json()
    assert d['organisation']=='flat_gallery'
    job=admin.post('/api/downloads',json={'url':'https://example.com/a','category':'Pictures'}).json()
    admin.patch('/api/destinations/'+destination['id'],json={'organisation':'organised'})
    row=admin.app_ref.state.store.one('SELECT * FROM jobs WHERE id=?',(job['id'],))
    assert row['organisation_override']=='flat_gallery'
    resolved=effective_settings(admin.app_ref.state.store.get('settings'),'sub.example.com',row['organisation_override'])
    assert resolved['organisation']=='flat_gallery' and resolved['advanced']['sleep-request']==2
    assert resolved['retries']==1
    for changes in ({'schedule_start':'25:00'},{'max_files':-1},{'subtitle_languages':['../../etc']},
                    {'media_filter':'extensions','extensions':[]},{'site_rules':[{'website':'https://evil.test/'}]},
                    {'site_rules':[{'website':'example.com','filename':'../../{filename}'}]}):
        assert admin.patch('/api/settings',json=changes).status_code in (400,422),changes


def test_schedule_and_filters():
    s={**DEFAULTS,'schedule_enabled':True,'schedule_start':'22:00','schedule_end':'06:00'}
    assert schedule_allows(s,datetime(2026,10,17,23))
    assert schedule_allows(s,datetime(2026,10,17,5))
    assert not schedule_allows(s,datetime(2026,10,17,12))
    assert not schedule_allows(s,datetime(2026,10,17,6))
    s.update(schedule_start='08:00',schedule_end='17:00')
    assert schedule_allows(s,datetime(2026,10,17,9))
    assert not schedule_allows(s,datetime(2026,10,17,23))
    assert accepts_file({'media_filter':'images'},{'extension':'png'})
    assert not accepts_file({'media_filter':'images'},{'extension':None,'_ytdl_info_dict':{'id':'1'}})
    assert accepts_file({'media_filter':'videos'},{'_ytdl_info_dict':{'id':'1'}})
    assert accepts_file({'media_filter':'extensions','extensions':['webp']},{'extension':'webp'})
    assert not accepts_file({'media_filter':'extensions','extensions':['webp']},{'extension':None})
    options=video_options({'video_quality':'720','video_format':'mp4','subtitles':'automatic','subtitle_languages':['en'],'playlist':'single'})
    assert '[height<=720]' in options['format'] and '[ext=mp4]' in options['format']
    assert options['writeautomaticsub'] and options['writesubtitles'] and options['noplaylist']
    assert options['continuedl'] and not options['nopart']


def test_recovery_and_scheduled_queue(tmp_path):
    async def exercise():
        store=Store(tmp_path/'db');s=store.get('settings');s.update(resume_interrupted=True,schedule_enabled=True)
        # A denied clock is injected; no worker starts outside the daily window.
        store.set('settings',s)
        from test_queue import insert
        insert(store,'resume','downloading')
        q=Queue(store,{'dir':tmp_path});started=[]
        async def execute(row,settings):
            started.append(row['id']);store.execute("UPDATE jobs SET status='completed' WHERE id=?",(row['id'],))
        q.execute=execute
        import app.downloads.options as opts
        original=opts.schedule_allows;opts.schedule_allows=lambda _:False
        try:
            await q.start();await asyncio.sleep(.25)
            assert store.one('SELECT status FROM jobs')['status']=='queued' and not started
            opts.schedule_allows=lambda _:True
            await asyncio.sleep(.3)
            assert started==['resume']
        finally:
            opts.schedule_allows=original;await q.stop()
    asyncio.run(exercise())


def test_flat_gallery_prefix_and_file_limit_real_engine(tmp_path):
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrAlbumExtractor
BunkrAlbumExtractor.fetch_album = lambda self, ident: ([
 {'file':'https://93.184.216.34/first.png','name':'first.png','id':'first'},
 {'file':'https://93.184.216.34/second.png','name':'second.png','id':'second'},
], {'album_id':ident,'album_name':'A / special gallery','count':2})
sys.exit(run(spec))
''')
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://bunkr.cr/a/FIXTURE',destination_path=str(root),archive=str(archive),
              settings={**DEFAULTS,'organisation':'flat_gallery','max_files':1},payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    files=list(root.glob('*.png'));assert len(files)==1
    assert files[0].name.startswith('A _ special gallery - ')
    assert files[0].read_bytes()==PNG
    assert not list(root.rglob('*.part'))
    # A second attempt skips the archived first file and collects the next one.
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert len(list(root.glob('*.png')))==2


def test_file_size_limit_does_not_archive(tmp_path):
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://93.184.216.34/large.png',destination_path=str(root),archive=str(archive),
              settings={**DEFAULTS,'organisation':'flat','max_file_size':10,'retries':0},payload=PNG.hex())
    subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert not list(root.glob('*.png'))
    import sqlite3
    with sqlite3.connect(archive/'archive.sqlite3') as con:assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==0


def test_filtered_media_is_not_archived(tmp_path):
    from test_engine import execute
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://93.184.216.34/image.png',destination_path=str(root),archive=str(archive),
              settings={**DEFAULTS,'organisation':'flat','media_filter':'videos'},payload=PNG.hex())
    events=execute(spec)
    assert not any(e.get('files') for e in events)
    assert not list(root.glob('*.png'))
    events=execute({**spec,'settings':{**spec['settings'],'media_filter':'images'}})
    assert any(e.get('files')==1 for e in events)


def test_existing_config_gets_new_defaults(tmp_path):
    import sqlite3
    with sqlite3.connect(tmp_path/'old.sqlite3') as con:
        con.executescript("CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE destinations(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT UNIQUE NOT NULL,description TEXT NOT NULL,icon TEXT NOT NULL,is_default INTEGER NOT NULL);")
        con.execute('INSERT INTO kv VALUES (?,?)',('settings',json.dumps({'concurrency':1,'organisation':'flat'})))
        con.execute('INSERT INTO destinations VALUES (?,?,?,?,?,?)',('old','Existing','/downloads','','folder',1))
    store=Store(tmp_path/'old.sqlite3')
    assert store.get('settings')['concurrency']==1
    assert store.get('settings')['organisation']=='flat'
    assert store.get('settings')['video_quality']=='best'
    assert store.one('SELECT * FROM destinations')['organisation']=='inherit'
