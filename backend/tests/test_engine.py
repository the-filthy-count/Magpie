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
