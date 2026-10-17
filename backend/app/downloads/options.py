"""Typed user preferences translated to the pinned download engines."""
from datetime import datetime
import re
import hashlib
from app.database.store import DEFAULTS

IMAGES=frozenset('jpg jpeg png gif webp avif bmp tif tiff heic heif jxl svg'.split())
VIDEOS=frozenset('mp4 webm mkv mov avi m4v mpeg mpg flv ts ogv gifv'.split())

def effective_settings(settings, website, organisation=None):
    result={**DEFAULTS, **settings}
    result['advanced']=dict(result['advanced'])
    matches=[r for r in result['site_rules'] if website==r['website'] or website.endswith('.'+r['website'])]
    if matches:
        rule=max(matches,key=lambda r:len(r['website']))
        result.update({k:v for k,v in rule.items() if k not in ('website','sleep_request') and v is not None})
        if rule.get('sleep_request') is not None:
            result['advanced']['sleep-request']=rule['sleep_request']
    if organisation and organisation!='inherit':result['organisation']=organisation
    return result

def schedule_allows(settings, local=None):
    if not settings.get('schedule_enabled'):return True
    clock=(local or datetime.now()).strftime('%H:%M')
    start,end=settings['schedule_start'],settings['schedule_end']
    return True if start==end else start<=clock<end if start<end else clock>=start or clock<end

def gallery_name(metadata):
    for key in ('album_name','gallery_name','gallery_title','album_title','playlist_title','_magpie_gallery'):
        value=metadata.get(key)
        if isinstance(value,str) and value.strip() and value.strip().lower() not in ('none','unknown','null'):
            return value.strip()
    return ''

def install_gallery_prefix():
    from gallery_dl.path import PathFormat
    original=PathFormat.build_filename
    def filename(self, metadata):
        native=original(self,metadata)
        title=gallery_name(metadata)
        if not title:return native
        title=re.sub(r'[\x00-\x1f\x7f/\\]+','_',title).strip(' .')[:100]
        combined=self.clean_path(self.clean_segment(title+' - '+native)) if title else native
        if len(combined.encode('utf-8')) > 240:
            from pathlib import Path
            suffix=Path(native).suffix[:20]
            digest=hashlib.sha256(combined.encode()).hexdigest()[:12]
            combined=combined.encode()[:195].decode('utf-8','ignore').rstrip(' .')+'-'+digest+suffix
        return combined
    PathFormat.build_filename=filename

def accepts_file(settings, metadata):
    mode=settings.get('media_filter','all')
    if mode=='all':return True
    video=metadata.get('_ytdl_info_dict')
    ext=str(metadata.get('extension') or (video or {}).get('ext') or '').lower()
    if mode=='images':return not video and ext in IMAGES
    if mode=='videos':return bool(video) or ext in VIDEOS
    return ext in settings['extensions']

def video_options(settings):
    height=settings.get('video_quality','best')
    bound='' if height=='best' else f'[height<={height}]'
    best=f'bestvideo*{bound}+bestaudio/best{bound}'
    if settings.get('video_format')=='mp4':
        best=f'bestvideo*[ext=mp4]{bound}+bestaudio[ext=m4a]/best[ext=mp4]{bound}/'+best
    subs=settings.get('subtitles','off')
    return dict(format=best, noplaylist=settings.get('playlist','all')=='single',
                max_filesize=settings.get('max_file_size') or None,
                max_downloads=settings.get('max_files') or None,
                playlistend=1 if settings.get('playlist')=='single' else None,
                writesubtitles=subs!='off', writeautomaticsub=subs=='automatic',
                subtitleslangs=settings.get('subtitle_languages',['en']), subtitlesformat='vtt/best',
                sleep_interval_requests=settings.get('advanced',{}).get('sleep-request') or None,
                continuedl=True, nopart=False)


def custom_filename(native, fields, position):
    """Literal labels only: never expose custom values as template expressions."""
    values=[]
    for value in fields.values():
        value=re.sub(r'[\x00-\x1f\x7f/\\:<>"|?*]+','_',value).strip(' .')
        if value:values.append(value)
    if not values:return native
    from pathlib import Path
    labels=' - '.join(values)
    # gallery-dl uses a trailing dot while yt-dlp fills the extension.
    suffix='.' if native.endswith('.') else Path(native).suffix
    if position=='end':
        stem=native[:-len(suffix)] if suffix else native
        combined=stem+' - '+labels+suffix
    else:
        combined=labels+' - '+native
    if len(combined.encode())>240:
        digest=hashlib.sha256(combined.encode()).hexdigest()[:12]
        combined=combined.encode()[:195].decode('utf-8','ignore').rstrip(' .')+'-'+digest+suffix[:20]
    return combined


def install_custom_fields(fields, position):
    if not fields:return
    from gallery_dl.path import PathFormat
    original=PathFormat.build_filename
    def filename(self,metadata):
        native=original(self,metadata)
        return self.clean_path(self.clean_segment(custom_filename(native,fields,position)))
    PathFormat.build_filename=filename
