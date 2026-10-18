"""Exercise the real gallery-dl engine in a subprocess with controlled HTTP data.

Only HTTP transport is replaced. Extractor, downloader, file finalization, output
hooks, archive database and Linux write confinement are the production code.
"""
import base64
import json
import os
import sqlite3
import subprocess
import sys
from app.database.store import DEFAULTS

PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ioAAAAASUVORK5CYII=')
SCRIPT='''
import io,json,sys
import requests
from urllib3.response import HTTPResponse
from app.downloads.worker import run
spec=json.loads(sys.stdin.readline())
payload=bytes.fromhex(spec.pop('payload'))
def send(self,request,**kwargs):
    response=requests.Response()
    response.status_code=200
    response.url=request.url
    response.request=request
    response.headers={'Content-Type':'image/png','Content-Length':str(len(payload))}
    response.raw=HTTPResponse(body=io.BytesIO(payload),headers=response.headers,preload_content=False)
    return response
requests.adapters.HTTPAdapter.send=send
sys.exit(run(spec))
'''

def execute(spec):
    result=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    return [json.loads(line) for line in result.stdout.splitlines()]

def test_real_engine_and_archive_survive_process_restart(tmp_path):
    root=tmp_path/'downloads';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(root),archive=str(archive),settings=DEFAULTS.copy(),payload=PNG.hex())
    first=execute(spec)
    assert any(e.get('files')==1 for e in first)
    files=list(root.rglob('*.png'));assert len(files)==1
    assert files[0].read_bytes()==PNG
    db=archive/'archive.sqlite3';assert db.exists()
    with sqlite3.connect(db) as con:assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==1
    # Remove media to prove the second process consults persistent archive, not
    # just an existing output filename.
    files[0].unlink()
    second=execute(spec)
    assert any(e.get('skipped')==1 for e in second)
    assert not list(root.rglob('*.png'))
    other=tmp_path/'other';other.mkdir();otherarchive=tmp_path/'otherarchive';otherarchive.mkdir()
    third=execute({**spec,'destination_path':str(other),'archive':str(otherarchive)})
    assert any(e.get('files')==1 for e in third)

def test_failed_download_is_not_archived(tmp_path):
    root=tmp_path/'downloads';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    script=SCRIPT.replace('response.status_code=200','response.status_code=403')
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'retries':0},payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode!=0
    db=archive/'archive.sqlite3'
    with sqlite3.connect(db) as con:assert con.execute('SELECT COUNT(*) FROM archive').fetchone()[0]==0

def test_media_cannot_follow_symlink_into_archive(tmp_path):
    root=tmp_path/'downloads';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    (root/'escape.png').symlink_to(archive/'sensitive.png')
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat','filename':'escape.png'},payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode!=0
    assert not (archive/'sensitive.png').exists()


def test_bunkr_album_total_and_archived_files(tmp_path):
    # Controlled album metadata; real pinned Bunkr.items(), DownloadJob,
    # output hooks, downloader and archive handling are exercised.
    script = SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrAlbumExtractor
BunkrAlbumExtractor.fetch_album = lambda self, ident: ([
    {'file': 'https://93.184.216.34/first.png', 'name': 'first.png', 'id': 'first'},
    {'file': 'https://93.184.216.34/second.png', 'name': 'second.png', 'id': 'second'},
], {'album_id': ident, 'album_name': 'Fixture', 'count': 2})
sys.exit(run(spec))
''')
    root = tmp_path / 'downloads'; root.mkdir()
    archive = tmp_path / 'archive'; archive.mkdir()
    spec = dict(url='https://bunkr.cr/a/FIXTURE', destination_path=str(root), archive=str(archive), settings=DEFAULTS.copy(), payload=PNG.hex())
    for attempt in range(2):
        result = subprocess.run([sys.executable, '-c', script], input=json.dumps(spec)+'\n', capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        events = [json.loads(line) for line in result.stdout.splitlines()]
        assert any(e.get('total_files') == 2 for e in events)
        assert any(e.get('files' if attempt == 0 else 'skipped') == 2 for e in events)


def test_partial_file_survives_failure_and_resumes(tmp_path):
    root=tmp_path/'downloads';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    payload=PNG+b'\x00'*200000
    spec=dict(url='https://93.184.216.34/resume.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat','retries':0},payload=payload.hex())
    failing=SCRIPT.replace('def send(self,request,**kwargs):', '''
class Broken(io.BytesIO):
    def read(self, size=-1):
        if self.tell()>=65536:
            from urllib3.exceptions import ProtocolError
            raise ProtocolError('controlled interruption')
        return super().read(min(size if size>=0 else 32768,32768))
def send(self,request,**kwargs):''').replace('io.BytesIO(payload)','Broken(payload)')
    first=subprocess.run([sys.executable,'-c',failing],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert first.returncode!=0
    partial=list(root.glob('*.part'));assert len(partial)==1
    retained=partial[0].stat().st_size;assert 0<retained<len(payload)
    resume=SCRIPT.replace("    response.status_code=200",'''    offset=int(request.headers.get('Range','bytes=0-').split('=')[1].split('-')[0])
    print(json.dumps({'range_offset':offset}),flush=True)
    response.status_code=206 if offset else 200''').replace("    response.raw=HTTPResponse", "    if offset:\n        response.headers['Content-Range']=f'bytes {offset}-{len(payload)-1}/{len(payload)}'\n        response.headers['Content-Length']=str(len(payload)-offset)\n    response.raw=HTTPResponse").replace('io.BytesIO(payload)','io.BytesIO(payload[offset:])')
    second=subprocess.run([sys.executable,'-c',resume],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert second.returncode==0,second.stdout+second.stderr
    assert any(json.loads(line).get('range_offset')==retained for line in second.stdout.splitlines())
    completed=list(root.glob('*.png'));assert len(completed)==1
    assert completed[0].read_bytes()==payload
    assert not list(root.glob('*.part'))


def test_bunkr_file_link_reports_one_file(tmp_path):
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrMediaExtractor
BunkrMediaExtractor.fetch_album=lambda self,ident:([{'file':'https://93.184.216.34/one.png','name':'one.png','id':'one'}],{'album_id':'fixture','album_name':'Single fixture','count':1})
sys.exit(run(spec))
''')
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://bunkr.pk/f/FIXTURE',destination_path=str(root),archive=str(archive),settings=DEFAULTS.copy(),payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert any(e.get('total_files')==1 for e in events)
    assert any(e.get('files')==1 for e in events)


def test_filester_native_single_file_reports_total(tmp_path):
    # Real Filester.items() parses a controlled page and yields its one URL;
    # only the page/URL lookup and HTTP transport are replaced.
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from types import SimpleNamespace
from gallery_dl.extractor.filester import FilesterFileExtractor
page='<meta property="og:title" content="fixture.png"> >UUID</span><b>fixture</b> >Type</span><b>image/png</b> >Uploaded</span><b>2026-10-18T00:00:00Z</b> >Size</span><b>68</b> >SHA-256</span><b>fixture</b>'
FilesterFileExtractor.request=lambda self,*args,**kwargs:SimpleNamespace(text=page)
FilesterFileExtractor._download_url=lambda self,ident:'https://93.184.216.34/fixture.png'
sys.exit(run(spec))
''')
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://filester.me/d/FIXTURE',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat'},payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert any(e.get('total_files')==1 for e in events)
    assert any(e.get('files')==1 for e in events)
