"""Live filename labels without changing paths used by active transfers."""
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from app.downloads.options import custom_filename


def write_control(config_dir, row, frozen=False):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', row['id']):
        raise ValueError('Invalid job identifier')
    folder = Path(config_dir) / 'job-controls'
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = folder / (row['id'] + '.json')
    temporary = path.with_suffix('.tmp')
    fields = row['custom_fields']
    data = dict(custom_fields=json.loads(fields) if isinstance(fields, str) else fields,
                filename_position=row['filename_position'], frozen=frozen)
    temporary.write_text(json.dumps(data))
    temporary.chmod(0o600)
    temporary.replace(path)
    return str(path)


class LiveNaming:
    def __init__(self, root, archive, spec):
        self.root = Path(root)
        self.control = Path(spec['naming_control'])
        self.baseline = spec['filename_baseline']
        self.staged = bool(spec.get('publish_destination'))
        self.last_source = None
        self.db = sqlite3.connect(Path(archive) / ('names-' + spec['job_id'] + '.sqlite3'))
        self.db.execute('CREATE TABLE IF NOT EXISTS names (source TEXT PRIMARY KEY, native TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS pending (source TEXT PRIMARY KEY, native TEXT NOT NULL, target TEXT NOT NULL, archive_key TEXT)')
        self.archive = Path(archive) / 'archive.sqlite3'
        self.db.commit()

    def latest(self, freeze=False):
        deadline = time.monotonic() + 30
        while True:
            data = json.loads(self.control.read_text())
            if not freeze or data.get('frozen'):
                # Reuse the public API validation for this local control channel.
                from app.models.schemas import DownloadNamingPatch
                return DownloadNamingPatch.model_validate({k:data[k] for k in ('custom_fields','filename_position')}).model_dump()
            if time.monotonic() >= deadline:
                raise TimeoutError('Naming publication handshake timed out')
            time.sleep(.05)

    def remember(self, source, native):
        source = Path(source)
        if not source.resolve().is_relative_to(self.root):
            raise PermissionError('Filename map escaped destination')
        relative = str(source.relative_to(self.root))
        if source.is_file():
            self.last_source = Path(relative)
        self.db.execute('INSERT OR REPLACE INTO names VALUES (?,?)', (relative, native))
        self.db.commit()

    def install(self):
        from gallery_dl.path import PathFormat
        manager = self
        original_filename = PathFormat.build_filename
        original_finalize = PathFormat.finalize
        def filename(pathfmt, metadata):
            native = original_filename(pathfmt, metadata)
            result = pathfmt.clean_path(pathfmt.clean_segment(custom_filename(native, manager.baseline['custom_fields'], manager.baseline['filename_position'])))
            # Archive skips also format filenames, reconstructing mappings for
            # staged files created by an earlier version of the worker.
            if pathfmt.realdirectory and not result.endswith('.') and '%(' not in str(metadata.get('extension', '')):
                manager.remember(Path(pathfmt.realdirectory) / result, native)
            return result
        def finalize(pathfmt, *args, **kwargs):
            source = Path(pathfmt.realpath)
            metadata = {**pathfmt.kwdict, 'extension':source.suffix.lstrip('.')}
            native = original_filename(pathfmt, metadata)
            if not source.suffix and native.endswith('.') and not source.name.endswith('.'):
                native = native[:-1]
            manager.remember(source, native)
            result = original_finalize(pathfmt, *args, **kwargs)
            if source.is_file():
                manager.last_source = source.relative_to(manager.root)
            if not manager.staged and source.is_file():
                labels = manager.latest()
                target = source.with_name(pathfmt.clean_path(pathfmt.clean_segment(custom_filename(native, labels['custom_fields'], labels['filename_position']))))
                relative = str(source.relative_to(manager.root))
                manager.db.execute('INSERT OR REPLACE INTO pending VALUES (?,?,?,?)', (relative, native, str(target.relative_to(manager.root)), pathfmt.kwdict.get('_archive_key')))
                manager.db.commit()
                manager.move(source, target)
                manager.db.execute('DELETE FROM pending WHERE source=?', (relative,))
                manager.db.commit()
                # Keep the engine's success event and current filename accurate.
                pathfmt.filename = target.name
                pathfmt.realpath = str(target)
                pathfmt.path = pathfmt.directory + target.name
                manager.remember(target, native)
            return result
        PathFormat.build_filename = filename
        PathFormat.finalize = finalize

    def move(self, source, target):
        if source == target:
            return
        if source.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(self.root):
            raise PermissionError('Tag edit escaped destination')
        pairs = [(source, target)]
        sidecars = {'vtt','srt','ass','ssa','lrc','ttml','json3','srv1','srv2','srv3'}
        for item in source.parent.glob(source.stem + '.*'):
            if item.suffix.lstrip('.') in sidecars:
                pairs.append((item, target.with_name(target.stem + item.name[len(source.stem):])))
        # Retain all sources until every target is linked, so a collision or
        # interruption remains recoverable without downloading the media again.
        for old, new in pairs:
            if old.is_symlink() or new.is_symlink():
                raise PermissionError('Symlinks cannot be renamed')
            if new.exists():
                if not old.samefile(new):
                    raise FileExistsError('Tag filename collision')
            else:
                os.link(old, new, follow_symlinks=False)
        for old, _ in reversed(pairs):
            old.unlink()

    def finish_pending(self):
        if self.staged:
            return
        labels = self.latest()
        for source, native, previous, key in list(self.db.execute('SELECT source,native,target,archive_key FROM pending')):
            actual = self.root / source
            if not actual.exists():
                actual = self.root / previous
            if not actual.is_file() or actual.is_symlink() or not actual.resolve().is_relative_to(self.root):
                raise FileNotFoundError('Completed transfer awaiting naming recovery is missing')
            target = actual.with_name(custom_filename(native, labels['custom_fields'], labels['filename_position']))
            relative = str(actual.relative_to(self.root))
            self.db.execute('DELETE FROM pending WHERE source=?', (source,))
            self.db.execute('INSERT OR REPLACE INTO pending VALUES (?,?,?,?)', (relative, native, str(target.relative_to(self.root)), key))
            self.db.commit()
            self.move(actual, target)
            # The bytes were fully retrieved before the original rename failed.
            if key:
                with sqlite3.connect(self.archive) as archive:
                    archive.execute('INSERT OR IGNORE INTO archive(entry) VALUES (?)', (key,))
            self.db.execute('DELETE FROM pending WHERE source=?', (relative,))
            self.db.commit()
            self.remember(target, native)

    def mapper(self, labels):
        records = list(self.db.execute('SELECT source,native FROM names'))
        mapped = {}
        companions = []
        for source, native in records:
            relative = Path(source)
            name = custom_filename(native, labels['custom_fields'], labels['filename_position'])
            # Names came from gallery-dl's cleaned formatter; labels are already
            # sanitised by custom_filename. Publication rejects traversal too.
            mapped[source] = relative.with_name(name)
            companions.append((relative, mapped[source]))
        def target(relative):
            if str(relative) in mapped:
                return mapped[str(relative)]
            for source, renamed in sorted(companions, key=lambda pair:len(pair[0].stem), reverse=True):
                if relative.parent == source.parent and relative.name.startswith(source.stem + '.'):
                    return renamed.with_name(renamed.stem + relative.name[len(source.stem):])
            return relative
        return target
