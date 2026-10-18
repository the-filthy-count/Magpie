"""One isolated gallery-dl process per job. JSON events only on stdout."""
import json
import logging
import os
import sys
import time
from pathlib import Path
from app.core.security import guard_network, landlock, safe_template, validate_url


def emit(**event):
    print(json.dumps(event), flush=True)


def run(spec):
    from gallery_dl import config, job, output, exception
    root = Path(spec['destination_path']).resolve(strict=True)
    archive = Path(spec['archive']).resolve(strict=True)
    publish_destination = Path(spec['publish_destination']).resolve(strict=True) if spec.get('publish_destination') else None
    if publish_destination:
        from app.downloads.staging import merge_archive
        merge_archive(Path(spec['published_archive']) / 'archive.sqlite3', archive / 'archive.sqlite3')
    # No user/system config, hooks, executable expressions or external network
    # downloaders are accepted. Only sandboxed local FFmpeg helpers may execute.
    config.clear()
    from app.database.store import DEFAULTS
    settings = {**DEFAULTS, **spec['settings']}
    from app.downloads.options import accepts_file, gallery_name, install_gallery_prefix
    extractor = {
        'base-directory': str(root), 'archive': str(archive / 'archive.sqlite3'),
        'archive-event': ['file'], 'retries': settings['retries'],
        'timeout': settings['timeout'], 'proxy': None, 'proxy-env': False,
        'path-restrict': 'auto', 'path-remove': '\u0000',
        'cookies-update': False, **settings['advanced'],
    }
    if settings['filename']:
        extractor['filename'] = safe_template(settings['filename'])
    if settings['organisation'] in ('flat','flat_gallery'):
        extractor['directory'] = []
    elif settings['organisation'] == 'custom':
        extractor['directory'] = [safe_template(x) for x in settings['directory']]
    if settings['organisation']=='flat_gallery':
        install_gallery_prefix()
    from app.downloads.options import install_custom_fields
    install_custom_fields(spec.get('custom_fields', {}), spec.get('filename_position', 'start'))
    # Organised mode uses the extractor's native metadata-aware layout.
    # Native layouts avoid imposing absent creator/gallery metadata globally.
    if spec.get('cookie'):
        extractor['cookies'] = spec['cookie']
    config.set((), 'extractor', extractor)
    config.set((), 'downloader', {'http': {'rate': settings['rate_limit'] or None, 'progress': 0.5, 'part': True, 'filesize-max': settings['max_file_size'] or None},
                                'ytdl': {'enabled': True, 'module': 'yt_dlp', 'progress': 0.5}})
    config.set(('cache',), 'file', str(archive / 'cache.sqlite3'))
    completed_bytes = 0
    current_bytes = 0
    files = skipped = 0
    last = 0.0
    class Events(output.NullOutput):
        def start(self, path):
            nonlocal current_bytes
            current_bytes = 0
            emit(current_filename=Path(path).name, file_bytes=0, file_total=None, speed=None)
        def progress(self, total, downloaded, speed):
            nonlocal last, current_bytes
            if settings['max_file_size'] and (downloaded > settings['max_file_size'] or (total and total > settings['max_file_size'])):
                raise exception.StopDownload()
            current_bytes = downloaded
            now = time.monotonic()
            if now - last >= .5:
                last = now
                emit(bytes=completed_bytes + downloaded, file_bytes=downloaded, file_total=total, speed=speed)
        def success(self, path):
            nonlocal completed_bytes, files, current_bytes
            # File size after finalization is authoritative, including resume.
            completed_bytes += Path(path).stat().st_size
            current_bytes = 0
            files += 1
            emit(files=files, bytes=completed_bytes, current_filename=Path(path).name,
                 file_bytes=None, file_total=None, speed=None)
        def skip(self, path):
            nonlocal skipped
            skipped += 1
            emit(skipped=skipped)
    events = Events()
    from app.downloads.video import install_video_support
    install_video_support(root, settings, events)
    config.set(('extractor', 'ytdl'), 'module', 'yt_dlp')
    output.select = lambda: events
    class SanitizedLog(logging.Handler):
        def emit(self, record):
            # Do not forward extractor messages: URLs/tokens/cookies may be embedded.
            if record.levelno >= logging.WARNING:
                emit(message=f'{record.name.split(".")[0]}: {record.levelname.lower()}; see job outcome')
    logging.basicConfig(handlers=[SanitizedLog()], level=logging.WARNING, force=True)
    from app.downloads.paths import install_path_boundary
    install_path_boundary(root, settings['organisation'] == 'organised', settings['max_file_size'])
    guard_network()
    landlock([root, archive] + ([publish_destination, Path(spec['published_archive'])] if publish_destination else []))
    validate_url(spec['url'])
    videos_seen = 0
    class AlbumDownloadJob(job.DownloadJob):
        def handle_url(self, url, metadata):
            nonlocal videos_seen
            if settings['max_files'] and files >= settings['max_files']:
                raise exception.StopExtraction()
            if metadata.get('_ytdl_info_dict') is not None:
                if settings['playlist']=='single' and videos_seen:
                    raise exception.StopExtraction()
                videos_seen += 1
            if not accepts_file(settings, metadata):
                return
            title=gallery_name(metadata) or getattr(self,'_magpie_gallery','')
            if title:metadata['_magpie_gallery']=title
            return super().handle_url(url, metadata)

        def handle_directory(self, metadata):
            self._magpie_gallery=gallery_name(metadata)
            if not self._magpie_gallery and self.extractor.subcategory in ('album','gallery'):
                title=metadata.get('title')
                if isinstance(title,str) and title.strip().lower() not in ('none','unknown','null'):
                    self._magpie_gallery=title.strip()
            # In the pinned Bunkr album extractor, Directory.count is the
            # album total. Other extractors may use count for individual posts.
            if self.extractor.category == 'bunkr' and self.extractor.subcategory in ('album','media','direct-link'):
                count = metadata.get('count')
                if type(count) is int and count > 0:
                    emit(total_files=count)
            return super().handle_directory(metadata)
    from app.downloads.routing import route_url
    routing = route_url(spec['url'])
    engine = routing['engine']
    if engine == 'gallery-dl':
        try:
            task = AlbumDownloadJob(spec['url'])
        except exception.NoExtractorError:
            engine = 'yt-dlp'
            task = AlbumDownloadJob('ytdl:' + spec['url'])
    else:
        # Internal prefix only; validate_url above still guards the real URL.
        task = AlbumDownloadJob('ytdl:' + spec['url'])
    emit(engine=engine, engine_extractor=getattr(task.extractor, 'ytdl_ie_key', None) if engine == 'yt-dlp' else task.extractor.category)
    if task.extractor.category=='directlink':
        emit(total_files=1)
    task.run()
    if task.status:
        if engine == 'yt-dlp':
            emit(error='yt-dlp could not download media from this URL. The page may be unsupported or require cookies; check site availability and authentication.')
        else:
            emit(error=f'gallery-dl exited with status {task.status}. Check site support, cookies, rate limits and destination permissions.')
    if not task.status and publish_destination:
        emit(phase='publishing', speed=None)
        from app.downloads.staging import publish_files, merge_archive
        try:
            publish_files(root, publish_destination, spec['job_id'])
        except FileExistsError:
            emit(error='Publication found a conflicting destination filename. Existing files were not overwritten; staged files are retained for retry.')
            return 1
        merge_archive(archive / 'archive.sqlite3', Path(spec['published_archive']) / 'archive.sqlite3')
        # Sources are retained until every file is published and the shared archive commits.
        import shutil
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    return task.status


if __name__ == '__main__':
    os.umask(0o077)
    # A killed scheduler must not leave an orphaned downloader behind.
    import ctypes
    import signal
    parent = int(os.environ.get('MAGPIE_PARENT_PID', str(os.getppid())))
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) or os.getppid() != parent:
        sys.exit(1)
    try:
        sys.exit(run(json.loads(sys.stdin.readline())))
    except Exception as exc:
        # Errors are classified without emitting arbitrary exception payloads.
        if isinstance(exc, RuntimeError) and str(exc).startswith('Linux Landlock'):
            emit(error=str(exc))
        else:
            emit(error=f'Download stopped ({type(exc).__name__}). Check the URL, authentication and filesystem permissions.')
        sys.exit(1)
