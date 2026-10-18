import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


async def terminate(process):
    if process.returncode is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        await asyncio.wait_for(process.wait(), 5)
    except asyncio.TimeoutError:
        os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
    except ProcessLookupError:
        await process.wait()


class Queue:
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.active = {}
        self.stopping = False
        self.task = None
        self.last_cleanup = 0
    async def start(self):
        self.store.execute("UPDATE jobs SET status='interrupted', completed_at=?, error='Application restarted during download', speed=NULL WHERE status='downloading'", (now(),))
        if self.store.get('settings').get('resume_interrupted'):
            self.store.execute("UPDATE jobs SET status='queued',started_at=NULL,completed_at=NULL,error=NULL,files=0,skipped=0,bytes=0,speed=NULL,current_filename=NULL,file_bytes=NULL,file_total=NULL,total_files=NULL,cancel_requested=0 WHERE status='interrupted'")
        self.task = asyncio.create_task(self.schedule())
    async def stop(self):
        self.stopping = True
        if self.task:
            await self.task
        await asyncio.gather(*list(self.active.values()), return_exceptions=True)
    async def schedule(self):
        while not self.stopping:
            settings = self.store.get('settings')
            if time.monotonic() - self.last_cleanup > 3600:
                self.last_cleanup = time.monotonic()
                if settings['retention_days']:
                    cutoff = (datetime.now(timezone.utc) - timedelta(days=settings['retention_days'])).isoformat()
                    self.store.execute("DELETE FROM jobs WHERE status NOT IN ('queued','downloading') AND completed_at < ?", (cutoff,))
                self.store.execute('DELETE FROM sessions WHERE expires < ?', (time.time(),))
            from app.downloads.options import schedule_allows
            while schedule_allows(settings) and len(self.active) < settings['concurrency'] and not self.stopping:
                # Atomic status transition protects claims. A process-wide lock in
                # main additionally prevents separate application schedulers.
                with self.store.db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row = db.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY seq LIMIT 1").fetchone()
                    if not row:
                        break
                    row = dict(row)
                    db.execute("UPDATE jobs SET status='downloading',phase='downloading',started_at=?,attempts=attempts+1,cancel_requested=0 WHERE id=?", (now(), row['id']))
                task = asyncio.create_task(self.execute(row, settings.copy()))
                self.active[row['id']] = task
                task.add_done_callback(lambda _, key=row['id']: self.active.pop(key, None))
            await asyncio.sleep(.2)
    async def execute(self, row, settings):
        process = None
        error = None
        try:
            from app.core.security import destination_path
            path = destination_path(row['destination_path'], self.config['roots'])
            archive = self.config['dir'] / 'archives' / (row.get('archive_id') or row['destination_id'])
            archive.mkdir(mode=0o700, parents=True, exist_ok=True)
            from app.downloads.staging import staging_location, prepare_staging
            staging = row.get('staging_path')
            if staging is None:
                staging = staging_location(path, row['id'], settings, self.config['roots']) if settings['publish_when_complete'] else ''
                self.store.execute('UPDATE jobs SET staging_path=? WHERE id=?', (staging, row['id']))
            published_archive = archive
            if staging:
                staging = prepare_staging(staging, path, self.config['roots'])
                archive = published_archive / 'jobs' / row['id']
                archive.mkdir(mode=0o700, parents=True, exist_ok=True)
            # Cookie selection is domain scoped, never gallery-dl category text supplied by a URL.
            cookies = self.store.all('SELECT * FROM cookies')
            cookie = next((str(self.config['dir'] / 'cookies' / (c['id'] + '.txt')) for c in cookies
                           if row['website'] == c['website'] or row['website'].endswith('.' + c['website'])), None)
            from app.downloads.options import effective_settings
            settings = effective_settings(settings, row['website'], row.get('organisation_override'))
            spec = dict(url=row['url'], destination_path=path, archive=str(archive), cookie=cookie, settings=settings, custom_fields=json.loads(row.get('custom_fields') or '{}'), filename_position=row.get('filename_position') or 'start')
            if staging:
                spec.update(destination_path=staging, publish_destination=path, published_archive=str(published_archive), job_id=row['id'])
            env = {k: v for k, v in os.environ.items() if k.upper() not in
                   ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','PYTHONPATH','PYTHONSTARTUP')}
            env['PYTHONDONTWRITEBYTECODE'] = '1'
            env['MAGPIE_PARENT_PID'] = str(os.getpid())
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'app.downloads.worker', stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True, env=env, limit=65536)
            process.stdin.write((json.dumps(spec) + '\n').encode())
            await process.stdin.drain()
            process.stdin.close()
            async def events():
                nonlocal error
                async for line in process.stdout:
                    try:
                        event = json.loads(line)
                        if 'error' in event:
                            error = str(event['error'])[:500]
                        allowed = {'files','skipped','bytes','speed','current_filename','file_bytes','file_total','total_files','phase','engine','engine_extractor'}
                        updates = {k: v for k, v in event.items() if k in allowed}
                        if updates:
                            self.store.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in updates) + ' WHERE id=?', (*updates.values(), row['id']))
                    except (ValueError, TypeError):
                        continue
            reader = asyncio.create_task(events())
            started = time.monotonic()
            try:
                while process.returncode is None:
                    state = self.store.one('SELECT cancel_requested FROM jobs WHERE id=?', (row['id'],))
                    if self.stopping or state['cancel_requested']:
                        await terminate(process)
                        break
                    if time.monotonic() - started > self.config['job_timeout']:
                        error = 'Maximum job duration reached; retry to resume using the archive'
                        await terminate(process)
                        break
                    await asyncio.sleep(.2)
                await process.wait()
                await reader
            finally:
                if not reader.done():
                    reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
            cancelled = self.store.one('SELECT cancel_requested FROM jobs WHERE id=?', (row['id'],))['cancel_requested']
            status = 'cancelled' if cancelled else 'interrupted' if self.stopping else 'failed' if process.returncode or error else 'completed'
            if status == 'completed' and staging:
                try:
                    Path(staging).rmdir()
                except OSError:
                    pass
        except Exception as exc:
            status = 'interrupted' if self.stopping else 'failed'
            error = f'Worker could not finish ({type(exc).__name__}); verify destination access and system configuration'
        finally:
            if process and process.returncode is None:
                await terminate(process)
        logging.getLogger('magpie.queue').info('download_finished id=%s status=%s', row['id'], status)
        self.store.execute('UPDATE jobs SET status=?,completed_at=?,error=?,speed=NULL WHERE id=?',
                           (status, now(), error, row['id']))
