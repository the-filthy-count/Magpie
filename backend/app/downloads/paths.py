"""Small pinned-version adapter around gallery-dl's native path formatter."""
from pathlib import Path
import sys


def install_path_boundary(root, organised=False):
    from gallery_dl.path import PathFormat
    root = Path(root).resolve(strict=True)
    def check(value):
        if value and not Path(value).resolve().is_relative_to(root):
            raise PermissionError('Media path escaped the selected destination')
    # Kernel confinement is the final write boundary. These checks additionally
    # separate media paths from the separately writable native archive directory.
    for name in ('set_directory', 'build_path'):
        original = getattr(PathFormat, name)
        def wrapped(self, *args, _original=original, **kwargs):
            result = _original(self, *args, **kwargs)
            for attr in ('realdirectory', 'realpath', 'temppath'):
                check(getattr(self, attr, ''))
            return result
        setattr(PathFormat, name, wrapped)
    for name in ('open', 'finalize'):
        original = getattr(PathFormat, name)
        def wrapped(self, *args, _original=original, **kwargs):
            for attr in ('realdirectory', 'realpath', 'temppath'):
                check(getattr(self, attr, ''))
            return _original(self, *args, **kwargs)
        setattr(PathFormat, name, wrapped)
    if organised:
        original_directory = PathFormat.build_directory
        def directory(self, *args, **kwargs):
            return [segment for segment in original_directory(self, *args, **kwargs)
                    if segment.strip().lower() not in ('none', 'unknown', 'null')]
        PathFormat.build_directory = directory
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.posix_spawn'):
            from app.downloads.video import media_tool_directory
            executable, argv = args[:2]
            allowed = {str(media_tool_directory() / name) for name in ('ffmpeg', 'ffprobe', 'node')}
            if (isinstance(executable, str) and executable in allowed and
                    isinstance(argv, (list, tuple)) and argv and argv[0] == executable):
                return
            raise PermissionError('Only sandboxed bundled media wrappers may run in download workers')
        if event in ('os.system', 'os.exec'):
            raise PermissionError('External commands are disabled in download workers')
    sys.addaudithook(audit)
