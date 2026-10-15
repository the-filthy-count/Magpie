"""Pinned yt-dlp adapter for gallery-dl, with fixed safe runtime options."""
import os
from pathlib import Path


def media_tool_directory():
    return Path(os.environ.get('MAGPIE_FFMPEG_DIR', '/usr/local/libexec/magpie')).resolve()


def install_video_support(root, settings, events):
    import yt_dlp
    from gallery_dl.downloader.ytdl import YoutubeDLDownloader
    original = yt_dlp.YoutubeDL
    root = Path(root).resolve(strict=True)
    os.environ['MAGPIE_MEDIA_ROOT'] = str(root)

    def check_path(filename):
        if filename and filename != '-' and not Path(filename).resolve().is_relative_to(root):
            raise PermissionError('Video path escaped the selected destination')
        if filename == '-':
            raise PermissionError('Video stdout output is disabled')
        return filename

    class ConfinedYoutubeDL(original):
        def __init__(self, params=None, *args, **kwargs):
            params = dict(params or {})
            # Override even options supplied by an extractor: network access must
            # stay in guarded Python downloaders, never native external helpers.
            params.update({
                'proxy': '', 'cachedir': False, 'cookiefile': None,
                'cookiesfrombrowser': None, 'usenetrc': False,
                'quiet': True, 'no_warnings': True, 'noprogress': True,
                'paths': {'home': str(root), 'temp': str(root)},
                'ffmpeg_location': str(media_tool_directory()),
                'external_downloader': {'default': 'native'},
                'hls_prefer_native': True, 'concurrent_fragment_downloads': 1,
                'retries': settings['retries'], 'fragment_retries': settings['retries'],
                'extractor_retries': settings['retries'], 'socket_timeout': settings['timeout'],
                'ratelimit': settings['rate_limit'] or None,
                'js_runtimes': {'node': {'path': str(media_tool_directory() / 'node')}},
                'remote_components': set(),
                'postprocessors': [], 'exec_cmd': None,
            })
            super().__init__(params, *args, **kwargs)

        def prepare_filename(self, *args, **kwargs):
            return check_path(super().prepare_filename(*args, **kwargs))

        def process_info(self, info):
            for key in ('filepath', '_filename'):
                if info.get(key):
                    check_path(info[key])
            return super().process_info(info)

    yt_dlp.YoutubeDL = ConfinedYoutubeDL

    def progress(self, info):
        # gallery-dl's default adapter uses estimated totals and substitutes 0
        # for absent speed. Forward only actual measurements instead.
        if info.get('status') == 'downloading':
            events.progress(info.get('total_bytes'), info.get('downloaded_bytes', 0), info.get('speed'))
    YoutubeDLDownloader._progress_hook = progress
