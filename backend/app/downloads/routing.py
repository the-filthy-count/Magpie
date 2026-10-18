"""Network-free routing using the installed gallery-dl extractor registry."""
import threading

_classes = None
_lock = threading.Lock()


def route_url(url):
    global _classes
    # Match classes without instantiating extractors: constructors may access
    # configuration or credentials. The registry is loaded once under a lock.
    with _lock:
        if _classes is None:
            from gallery_dl import extractor
            classes = extractor.extractors()
            _classes = sorted(classes, key=lambda cls: cls.category == 'directlink')
        classes = _classes
    for cls in classes:
        if not cls.category.startswith('ytdl') and cls.pattern.match(url):
            return {'engine': 'gallery-dl', 'engine_extractor': cls.category}
    # yt-dlp's generic extractor matches any HTTP URL. Its match alone is not
    # proof of support; actual extraction stays in the confined queue worker.
    return {'engine': 'yt-dlp', 'engine_extractor': None}
