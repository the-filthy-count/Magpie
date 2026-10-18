import json
import socket
import subprocess
import sys
import pytest
from app.downloads.routing import route_url
from app.database.store import DEFAULTS
from test_engine import SCRIPT,PNG


@pytest.mark.parametrize('url,engine,extractor',[
 ('https://bunkr.cx/a/FIXTURE','gallery-dl','bunkr'),
 ('https://bunkr.by/f/FIXTURE','gallery-dl','bunkr'),
 ('https://example.com/picture.jpg','gallery-dl','directlink'),
 ('https://www.youtube.com/watch?v=abcdefghijk','yt-dlp',None),
 ('https://example.com/not-a-known-site','yt-dlp',None),
])
def test_registry_routing_without_network(monkeypatch,url,engine,extractor):
    def forbidden(*a,**kw):raise AssertionError('Routing must not contact websites')
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    route=route_url(url)
    assert route['engine']==engine and route['engine_extractor']==extractor


@pytest.mark.parametrize('url,engine,extractor',[
 ('https://bunkr.cx/a/FIXTURE','gallery-dl','bunkr'),
 ('https://example.com/watch','yt-dlp',None),
])
def test_api_reports_preflight_route(admin,destination,url,engine,extractor):
    result=admin.post('/api/downloads',json={'url':url,'destination_id':destination['id']})
    assert result.status_code==201,result.text
    data=result.json()
    assert data['engine']==engine and data['engine_extractor']==extractor
    listed=admin.get('/api/downloads').json()[0]
    assert listed['engine']==engine
    assert admin.get('/api/downloads/'+data['id']).json()['engine']==engine


def test_native_failure_does_not_retry_with_other_engine(tmp_path):
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    script=SCRIPT.replace('response.status_code=200','response.status_code=403')
    spec=dict(url='https://93.184.216.34/file.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'retries':0},payload=PNG.hex())
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode!=0
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert [e['engine'] for e in events if 'engine' in e]==['gallery-dl']


def test_generic_probe_fails_clearly_when_page_has_no_media(tmp_path):
    from test_video import SCRIPT as video_script
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://93.184.216.34/watch',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'retries':0},fixtures={'/watch':b'<html><head><title>No media</title></head><body>Nothing here</body></html>'.hex()})
    result=subprocess.run([sys.executable,'-c',video_script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode!=0,result.stdout+result.stderr
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert any(e.get('engine')=='yt-dlp' and e.get('engine_extractor')=='Generic' for e in events)
    assert any('may be unsupported' in e.get('error','') for e in events)
    assert not list(root.rglob('*.mp4'))


def test_create_rejects_output_only_routing_and_staging_fields(admin,destination):
    result=admin.post('/api/downloads',json={'url':'https://example.com/watch','destination_id':destination['id'],'engine':'gallery-dl','staging_path':'/tmp'})
    assert result.status_code==422


def test_single_file_hint_does_not_apply_to_filester_folders():
    assert route_url('https://filester.me/d/FILE')['total_files']==1
    assert 'total_files' not in route_url('https://filester.me/f/FOLDER')


def test_filester_single_file_api_reports_matching_progress(admin,destination):
    result=admin.post('/api/downloads',json={'url':'https://filester.me/d/FILE','destination_id':destination['id']})
    assert result.status_code==201,result.text
    data=result.json();assert data['total_files']==1
    admin.app_ref.state.store.execute("UPDATE jobs SET status='downloading',file_bytes=69,file_total=100 WHERE id=?",(data['id'],))
    for response in [admin.get('/api/downloads/'+data['id']).json(),admin.get('/api/downloads').json()[0]]:
        assert response['files']==0
        assert response['file_progress_percent']==response['album_progress_percent']==69
