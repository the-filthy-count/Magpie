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
    # No user/system config, hooks, executable expressions or external network
    # downloaders are accepted. Only sandboxed local FFmpeg helpers may execute.
    config.clear()
    settings = spec['settings']
    extractor = {
        'base-directory': str(root), 'archive': str(archive / 'archive.sqlite3'),
        'archive-event': ['file'], 'retries': settings['retries'],
        'timeout': settings['timeout'], 'proxy': None, 'proxy-env': False,
        'path-restrict': 'auto', 'path-remove': '\u0000',
        'cookies-update': False, **settings['advanced'],
    }
    if settings['filename']:
        extractor['filename'] = safe_template(settings['filename'])
    if settings['organisation'] == 'flat':
        extractor['directory'] = []
    elif settings['organisation'] == 'custom':
        extractor['directory'] = [safe_template(x) for x in settings['directory']]
    # Organised mode uses the extractor's native metadata-aware layout.
    # Native layouts avoid imposing absent creator/gallery metadata globally.
    if spec.get('cookie'):
        extractor['cookies'] = spec['cookie']
    config.set((), 'extractor', extractor)
    config.set((), 'downloader', {'http': {'rate': settings['rate_limit'] or None, 'progress': 0.5},
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
    install_path_boundary(root, settings['organisation'] == 'organised')
    guard_network()
    landlock([root, archive])
    validate_url(spec['url'])
    try:
        task = job.DownloadJob(spec['url'])
    except exception.NoExtractorError:
        # Prefix is internal only: the submitted URL was validated as HTTP(S).
        task = job.DownloadJob('ytdl:' + spec['url'])
    task.run()
    if task.status:
        emit(error=f'gallery-dl exited with status {task.status}. Check site support, cookies, rate limits and destination permissions.')
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
