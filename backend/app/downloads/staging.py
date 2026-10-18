"""Persistent per-job staging and non-overwriting publication on Linux.

Publication keeps source files until the destination archive has committed. A
retry can therefore finish an interrupted publication without redownloading.
"""
import errno
import hashlib
import os
import re
import sqlite3
from pathlib import Path
from app.core.security import destination_path


def staging_location(destination, ident, settings, roots):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', ident):
        raise ValueError('Invalid staging job identifier')
    destination = Path(destination_path(destination, roots))
    configured = settings.get('in_progress_path')
    if configured:
        base = Path(destination_path(configured, roots))
    else:
        base = destination / '.magpie-in-progress'
    if destination.is_relative_to(base.resolve()):
        raise ValueError('In Progress must not contain the final destination')
    return str(base / ident)


def prepare_staging(value, destination, roots):
    path = Path(value)
    # Revalidate snapshots, including every existing symlink component.
    resolved = path.resolve()
    if not path.is_absolute() or '..' in path.parts or resolved != path or not any(resolved.is_relative_to(r) for r in roots):
        raise ValueError('Staging path is outside its permitted root or contains symlinks')
    if Path(destination).is_relative_to(resolved.parent):
        raise ValueError('Staging cannot contain the final destination')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return destination_path(str(path), roots)


def merge_archive(source, target):
    """Union the pinned gallery-dl native archive without replacing other jobs."""
    if not source.exists():
        return
    with sqlite3.connect(source, timeout=60) as src:
        if not src.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='archive'").fetchone():
            return
        with sqlite3.connect(target, timeout=60) as dst:
            dst.execute('CREATE TABLE IF NOT EXISTS archive (entry TEXT PRIMARY KEY) WITHOUT ROWID')
            dst.executemany('INSERT OR IGNORE INTO archive(entry) VALUES (?)', src.execute('SELECT entry FROM archive'))


def _directory(root_fd, parts):
    fd = os.dup(root_fd)
    try:
        for part in parts:
            if part in ('', '.', '..') or '/' in part:
                raise ValueError('Invalid publication path')
            try:
                os.mkdir(part, mode=0o755, dir_fd=fd)
            except FileExistsError:
                pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _digest(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    result = hashlib.sha256()
    while block := os.read(fd, 1024 * 1024):
        result.update(block)
    return result.digest()


def _matches(source_fd, name, directory_fd):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    except FileNotFoundError:
        return False
    try:
        import stat
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise FileExistsError('Publication target is not a regular file')
        if os.fstat(source_fd).st_size != os.fstat(fd).st_size or _digest(source_fd) != _digest(fd):
            raise FileExistsError('A different file already exists at the destination; it was not overwritten')
        return True
    finally:
        os.close(fd)


def publish_files(source, destination, ident):
    source, destination = Path(source), Path(destination)
    # Validate the full inventory before exposing any files. Directory traversal
    # uses no-follow directory descriptors to prevent symlink replacement races.
    inventory = []
    for current, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            if (Path(current) / name).is_symlink():
                raise PermissionError('Symlinks cannot be published')
        for name in files:
            relative = (Path(current) / name).relative_to(source)
            if name.endswith(('.part', '.ytdl')) or name.startswith('.magpie-transfer-') or '.magpie-in-progress' in relative.parts:
                raise ValueError('Unfinished temporary files remain; retry before publishing')
            inventory.append(relative)
    root_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    stage_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for relative in inventory:
            src_dir = _directory(stage_fd, relative.parts[:-1])
            dst_dir = _directory(root_fd, relative.parts[:-1])
            src_fd = None
            temporary = '.magpie-transfer-' + ident
            try:
                src_fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src_dir)
                import stat
                if not stat.S_ISREG(os.fstat(src_fd).st_mode):
                    raise PermissionError('Only regular files can be published')
                if _matches(src_fd, relative.name, dst_dir):
                    continue
                try:
                    # Same filesystem: publish atomically without copying or overwriting.
                    os.link(relative.name, relative.name, src_dir_fd=src_dir, dst_dir_fd=dst_dir, follow_symlinks=False)
                except OSError as exc:
                    if exc.errno == errno.EEXIST:
                        if not _matches(src_fd, relative.name, dst_dir):
                            raise
                    elif exc.errno == errno.EXDEV:
                        # Other filesystem: copy to a hidden temporary file, sync,
                        # then link its complete contents into place atomically.
                        try:
                            os.unlink(temporary, dir_fd=dst_dir)
                        except FileNotFoundError:
                            pass
                        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dst_dir)
                        try:
                            os.lseek(src_fd, 0, os.SEEK_SET)
                            with os.fdopen(out, 'wb') as stream:
                                while block := os.read(src_fd, 1024 * 1024):
                                    stream.write(block)
                                stream.flush()
                                os.fsync(stream.fileno())
                            try:
                                os.link(temporary, relative.name, src_dir_fd=dst_dir, dst_dir_fd=dst_dir, follow_symlinks=False)
                            except FileExistsError:
                                if not _matches(src_fd, relative.name, dst_dir):
                                    raise
                        finally:
                            os.unlink(temporary, dir_fd=dst_dir)
                    else:
                        raise
                os.fsync(dst_dir)
            finally:
                if src_fd is not None:
                    os.close(src_fd)
                os.close(src_dir)
                os.close(dst_dir)
    finally:
        os.close(stage_fd)
        os.close(root_fd)
