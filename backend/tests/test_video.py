"""Real yt-dlp extraction/download/FFmpeg tests with controlled HTTP transport."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from app.database.store import DEFAULTS

SCRIPT = '''
import io,json,sys
from urllib.parse import urlsplit
import yt_dlp
from yt_dlp.networking.common import Response
from yt_dlp.extractor.common import InfoExtractor
from app.downloads.worker import run
spec=json.loads(sys.stdin.readline())
fixtures={k:bytes.fromhex(v) for k,v in spec.pop('fixtures').items()}
merge=spec.pop('merge',False)
def urlopen(self, request):
    url=request if isinstance(request,str) else request.url
    path=urlsplit(url).path
    payload=fixtures[path]
    kind='text/html' if path=='/watch' else 'video/mp4' if path.endswith('.mp4') else 'audio/mp4'
    return Response(io.BytesIO(payload),url,{'Content-Type':kind,'Content-Length':str(len(payload))})
yt_dlp.YoutubeDL.urlopen=urlopen
if merge:
    class MagpieFixtureIE(InfoExtractor):
        _VALID_URL=r'https://93\\.184\\.216\\.34/fixturevideo'
        def _real_extract(self,url):
            return {'id':'fixture','title':'Controlled video','formats':[
                {'format_id':'video','url':'https://93.184.216.34/video.mp4','ext':'mp4',
                 'vcodec':'mp4v','acodec':'none','width':16,'height':16},
                {'format_id':'audio','url':'https://93.184.216.34/audio.m4a','ext':'m4a',
                 'vcodec':'none','acodec':'aac','abr':32}]}
    original_classes=yt_dlp.extractor.gen_extractor_classes
    yt_dlp.extractor.gen_extractor_classes=lambda: [MagpieFixtureIE,*original_classes()]
    original_init=yt_dlp.YoutubeDL.__init__
    def init(self,*args,**kwargs):
        original_init(self,*args,**kwargs)
        self.add_info_extractor(MagpieFixtureIE())
    yt_dlp.YoutubeDL.__init__=init
sys.exit(run(spec))
'''

@pytest.fixture
def media(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg is required for video integration tests (included in Docker image)')
    video=tmp_path/'video.mp4';audio=tmp_path/'audio.m4a'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=16x16:r=1','-t','1','-an','-c:v','mpeg4',str(video)],check=True)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=1000:sample_rate=8000','-t','1','-vn','-c:a','aac',str(audio)],check=True)
    tools=Path('/usr/local/libexec/magpie')
    if not (tools/'ffmpeg').exists():
        tools=tmp_path/'tools';tools.mkdir()
        for name in ('ffmpeg','ffprobe'):
            script=tools/name
            script.write_text(f'#!{sys.executable}\nfrom app.downloads.media_tool import main\nmain()\n')
            script.chmod(0o755)
    return video,audio,tools


def execute(tmp_path,media,merge=False,settings=None):
    video,audio,tools=media
    root=tmp_path/'downloads';root.mkdir(exist_ok=True)
    archive=tmp_path/'archive';archive.mkdir(exist_ok=True)
    html=b'<html><head><title>Fixture</title></head><body><video src="https://93.184.216.34/video.mp4" controls></video></body></html>'
    spec=dict(url='https://93.184.216.34/'+('fixturevideo' if merge else 'watch'),
              destination_path=str(root),archive=str(archive),settings={**DEFAULTS,**(settings or {})},merge=merge,
              fixtures={'/watch':html.hex(),'/video.mp4':video.read_bytes().hex(),'/audio.m4a':audio.read_bytes().hex()})
    result=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,
                          env={**os.environ,'MAGPIE_FFMPEG_DIR':str(tools),
                               'PYTHONPATH':str(Path(__file__).resolve().parents[1])+os.pathsep+os.environ.get('PYTHONPATH','')},timeout=40)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    return root,[json.loads(line) for line in result.stdout.splitlines()]


def test_generic_video_fallback_and_archive(tmp_path,media):
    root,events=execute(tmp_path,media)
    assert any(e.get('engine')=='yt-dlp' and e.get('engine_extractor')=='Generic' for e in events)
    assert any(e.get('files')==1 for e in events)
    files=list(root.rglob('*.mp4'));assert len(files)==1
    assert files[0].stat().st_size>0
    files[0].unlink()
    _,second=execute(tmp_path,media)
    assert any(e.get('skipped')==1 for e in second)
    assert not list(root.rglob('*.mp4'))


def test_real_video_audio_merge(tmp_path,media):
    root,events=execute(tmp_path,media,merge=True)
    assert any(e.get('files')==1 for e in events)
    files=list(root.rglob('*.mp4'));assert len(files)==1
    result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(files[0])],capture_output=True,text=True,check=True)
    assert {s['codec_type'] for s in json.loads(result.stdout)['streams']}=={'audio','video'}


def test_video_flat_organisation(tmp_path,media):
    root,_=execute(tmp_path,media,settings={'organisation':'flat'})
    assert len(list(root.glob('*.mp4')))==1


def test_media_tool_network_and_read_boundaries(tmp_path):
    root=tmp_path/'allowed';root.mkdir()
    secret=tmp_path/'secret';secret.write_text('private')
    script='''
import sys,socket
from pathlib import Path
from app.downloads.media_tool import deny_network,restrict_files
root,secret=map(Path,sys.argv[1:])
restrict_files(root)
(root/'allowed').write_text('ok')
try:secret.read_text()
except PermissionError:pass
else:raise AssertionError('Read boundary escaped')
deny_network()
try:socket.socket()
except PermissionError:pass
else:raise AssertionError('Network sandbox escaped')
'''
    r=subprocess.run([sys.executable,'-c',script,str(root),str(secret)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr


def test_video_progress_uses_only_measured_values(tmp_path):
    script='''
import sys
from app.downloads.video import install_video_support
from gallery_dl.downloader.ytdl import YoutubeDLDownloader
class Events:
    def progress(self,*values):
        assert values==(None,10,None),values
install_video_support(sys.argv[1],{'retries':1,'timeout':10,'rate_limit':0},Events())
YoutubeDLDownloader._progress_hook(None,{'status':'downloading','downloaded_bytes':10,'total_bytes_estimate':999})
'''
    r=subprocess.run([sys.executable,'-c',script,str(tmp_path)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr

@pytest.mark.skipif(not Path('/usr/local/libexec/magpie-node-real').exists(),reason='Bundled Node runtime is tested in the production image')
def test_bundled_javascript_runtime_is_restricted(tmp_path):
    helper=Path('/usr/local/libexec/magpie/node')
    program="""
const fs = require('fs');
const cp = require('child_process');
for (const action of [() => fs.readFileSync('/etc/passwd'), () => cp.execFileSync('/usr/bin/true')]) {
  let blocked=false;
  try { action(); } catch { blocked=true; }
  if (!blocked) process.exit(1);
}
console.log('sandboxed');
"""
    result=subprocess.run([str(helper),'-'],input=program,capture_output=True,text=True,
                          env={**os.environ,'MAGPIE_MEDIA_ROOT':str(tmp_path)},timeout=15)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='sandboxed'


def test_video_quality_subtitles_and_mp4_preference(tmp_path,media,monkeypatch):
    # Real yt-dlp format selection and subtitle writes with controlled transport.
    global SCRIPT
    script=SCRIPT.replace("merge=spec.pop('merge',False)", "merge=spec.pop('merge',False)\nfixtures['/sub.vtt']=b'WEBVTT\\n\\n00:00.000 --> 00:00.800\\nFixture caption\\n'\nfixtures['/low.mp4']=fixtures['/video.mp4']")
    script=script.replace('    payload=fixtures[path]', "    print(json.dumps({'transport_path':path}),flush=True)\n    payload=fixtures[path]")
    script=script.replace("'formats':[", "'subtitles':{'en':[{'ext':'vtt','url':'https://93.184.216.34/sub.vtt'}]},'formats':[")
    script=script.replace("'height':16},", "'height':1080},\n                {'format_id':'low','url':'https://93.184.216.34/low.mp4','ext':'mp4','vcodec':'mp4v','acodec':'none','width':16,'height':720},")
    monkeypatch.setitem(globals(),'SCRIPT',script)
    root,events=execute(tmp_path,media,merge=True,settings={'video_quality':'720','video_format':'mp4','subtitles':'manual','subtitle_languages':['en'],'organisation':'flat'})
    requested=[e['transport_path'] for e in events if 'transport_path' in e]
    assert '/low.mp4' in requested and '/video.mp4' not in requested
    subtitles=list(root.glob('*.vtt'));assert subtitles
    assert 'Fixture caption' in subtitles[0].read_text()
    assert len(list(root.glob('*.mp4')))==1


@pytest.mark.parametrize('mode,count',[('single',1),('all',2)])
def test_real_video_playlist_selection(tmp_path,media,monkeypatch,mode,count):
    script=SCRIPT.replace("            return {'id':'fixture'", "            data={'id':'fixture'")
    script=script.replace('    original_classes=yt_dlp.extractor.gen_extractor_classes', "            return {'_type':'playlist','id':'album','title':'Playlist','entries':[dict(data,id='one',title='One'),dict(data,id='two',title='Two')]}\n    original_classes=yt_dlp.extractor.gen_extractor_classes")
    monkeypatch.setitem(globals(),'SCRIPT',script)
    root,events=execute(tmp_path,media,merge=True,settings={'playlist':mode,'organisation':'flat'})
    assert len(list(root.glob('*.mp4')))==count
    assert any(e.get('files')==count for e in events)


@pytest.mark.parametrize('position',['start','end'])
def test_real_video_custom_fields(tmp_path,media,monkeypatch,position):
    script=SCRIPT.replace('sys.exit(run(spec))',f"spec['custom_fields']={{'creator':'Alice','tag':'Nature'}}\nspec['filename_position']={position!r}\nsys.exit(run(spec))")
    monkeypatch.setitem(globals(),'SCRIPT',script)
    root,events=execute(tmp_path,media,merge=True,settings={'organisation':'flat'})
    files=list(root.glob('*.mp4'));assert len(files)==1
    if position=='start':assert files[0].name.startswith('Alice - Nature - ')
    else:assert files[0].name.endswith(' - Alice - Nature.mp4')
    assert any(e.get('files')==1 for e in events)


def test_merged_video_publishes_from_staging(tmp_path,media,monkeypatch):
    original_script=SCRIPT
    final=tmp_path/'published';final.mkdir()
    shared=tmp_path/'shared';shared.mkdir()
    # Inject staging publication into the same real yt-dlp and FFmpeg fixture.
    staged=original_script.replace("sys.exit(run(spec))",f"spec.update(publish_destination={str(final)!r},published_archive={str(shared)!r},job_id='video-job')\nsys.exit(run(spec))")
    monkeypatch.setitem(globals(),'SCRIPT',staged)
    root,events=execute(tmp_path,media,merge=True,settings={'organisation':'flat'})
    assert not list(root.iterdir())
    files=list(final.glob('*.mp4'));assert len(files)==1
    result=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(files[0])],capture_output=True,text=True,check=True)
    assert {s['codec_type'] for s in json.loads(result.stdout)['streams']}=={'audio','video'}
    assert any(e.get('phase')=='publishing' for e in events)
