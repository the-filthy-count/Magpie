import json
import sqlite3
import subprocess
import sys
from app.database.store import DEFAULTS
from app.downloads.routing import route_url
from test_engine import SCRIPT,PNG


def test_pixeldrain_restriction_explained_and_staging_recovers(tmp_path):
    stage=tmp_path/'stage';stage.mkdir();final=tmp_path/'final';final.mkdir()
    shared=tmp_path/'archive';shared.mkdir();private=shared/'jobs/job';private.mkdir(parents=True)
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.pixeldrain import PixeldrainAlbumExtractor
restricted=spec.pop('restricted')
def request_json(self,url):
    files=[{'id':'first','name':'first.png','date_upload':'2026-10-19T00:00:00Z'},
           {'id':'second','name':'second.png','date_upload':'2026-10-19T00:00:00Z'}]
    if restricted:
        files[1].update(availability='file_rate_limited_captcha_required',availability_message='PRIVATE filename, token=secret https://example.com/private')
    return {'id':'fixture','title':'Fixture album','date_created':'2026-10-19T00:00:00Z','file_count':2,'files':files}
PixeldrainAlbumExtractor.request_json=request_json
sys.exit(run(spec))
''')
    spec=dict(url='https://pixeldrain.com/l/fixture',destination_path=str(stage),publish_destination=str(final),published_archive=str(shared),job_id='job',archive=str(private),settings={**DEFAULTS,'organisation':'flat'},payload=PNG.hex(),restricted=True)
    def attempt():
        return subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    first=attempt();assert first.returncode!=0
    events=[json.loads(line) for line in first.stdout.splitlines()]
    assert any(e.get('total_files')==2 for e in events)
    assert any(e.get('files')==1 for e in events)
    error=next(e['error'] for e in events if 'error' in e)
    assert 'requires a CAPTCHA for 1 file(s)' in error
    assert 'Completed files remain in In Progress' in error
    assert 'token=secret' not in first.stdout and 'PRIVATE' not in first.stdout
    assert len(list(stage.glob('*.png')))==1 and not list(final.iterdir())
    spec['restricted']=False
    second=attempt();assert second.returncode==0,second.stdout+second.stderr
    events=[json.loads(line) for line in second.stdout.splitlines()]
    assert any(e.get('skipped')==1 for e in events)
    assert any(e.get('files')==1 for e in events)
    assert len(list(final.glob('*.png')))==2
    with sqlite3.connect(shared/'archive.sqlite3') as con:
        assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==2


def test_pixeldrain_singleton_hint_is_not_applied_to_album():
    assert route_url('https://pixeldrain.com/u/fixture')['total_files']==1
    assert 'total_files' not in route_url('https://pixeldrain.com/l/fixture')
