import asyncio
import fcntl
import hashlib
import http.cookiejar
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import gallery_dl.version
import yt_dlp.version
from app.downloads.video import media_tool_directory
from fastapi import FastAPI, Request, HTTPException, Depends, UploadFile, File, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from app.core.security import destination_path, hash_password, verify_password, validate_url
from app.database.store import Store
from app.downloads.queue import Queue, now
from app.models.schemas import (Credentials, Login, PasswordChange, DownloadCreate,
                               DestinationCreate, DestinationPatch, Settings, JobView, DestinationView,
                               ApiTokenCreate, ApiTokenView, ApiTokenIssued)

VERSION = '1.0.0'
TERMINAL = ('completed', 'failed', 'cancelled', 'interrupted')
logger = logging.getLogger('magpie')


def create_app(config_dir=None, roots=None, start_queue=True):
    config = {'dir': Path(config_dir or os.environ.get('MAGPIE_CONFIG', '/config')).resolve(),
              'roots': [Path(p).resolve() for p in (roots or os.environ.get('MAGPIE_DOWNLOAD_ROOTS', '/downloads').split(':'))],
              'secure': os.environ.get('MAGPIE_SECURE_COOKIES', 'false').lower() == 'true',
              'job_timeout': int(os.environ.get('MAGPIE_JOB_TIMEOUT', '86400'))}
    directory = config['dir']
    os.umask(0o077)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('cookies', 'archives'):
        (directory / name).mkdir(exist_ok=True, mode=0o700)
    store = Store(directory / 'magpie.sqlite3')
    setup_path = directory / 'setup-token'
    if not store.get('password') and not setup_path.exists():
        setup_path.write_text(secrets.token_urlsafe(24))
        setup_path.chmod(0o600)
    queue = Queue(store, config)
    attempts = defaultdict(deque)
    @asynccontextmanager
    async def lifespan(app):
        lock = open(directory / 'scheduler.lock', 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise RuntimeError('Only one Magpie application process may use this /config')
        try:
            if start_queue:
                await queue.start()
            yield
        finally:
            if start_queue:
                await queue.stop()
            lock.close()
    app = FastAPI(title='Magpie', version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store, app.state.queue, app.state.config = store, queue, config
    hosts = os.environ.get('MAGPIE_ALLOWED_HOSTS', '*').split(',')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    @app.middleware('http')
    async def security_headers(request, call_next):
        # Browser writes require a same-origin request, including login/setup.
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if origin and urlsplit(origin).netloc != request.headers.get('host'):
                return JSONResponse({'error': {'code': 'origin', 'message': 'Cross-origin request blocked'}}, 403)
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return JSONResponse({'error': {'code': 'origin', 'message': 'Cross-site request blocked'}}, 403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control'] = 'no-store'
        return response
    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse({'error': {'code': str(exc.status_code), 'message': exc.detail}}, exc.status_code)
    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's raw errors include input values; never echo credentials.
        messages = [f'{".".join(map(str, e["loc"][1:]))}: {e["msg"]}' for e in exc.errors()]
        return JSONResponse({'error': {'code': 'validation', 'message': '; '.join(messages)}}, 422)
    @app.exception_handler(ValueError)
    async def value_error(request, exc):
        return JSONResponse({'error': {'code': 'validation', 'message': str(exc)}}, 400)
    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(request, exc):
        return JSONResponse({'error': {'code': 'conflict', 'message': 'An entry with that path or website already exists'}}, 409)
    def auth(request: Request):
        authorization = request.headers.get('authorization')
        if authorization:
            scheme, _, credential = authorization.partition(' ')
            if scheme.lower() != 'bearer' or not credential or len(credential) > 256:
                raise HTTPException(401, 'A valid Bearer API token is required')
            digest = hashlib.sha256(credential.encode()).hexdigest()
            token_row = store.one('SELECT * FROM api_tokens WHERE digest=? AND expires_at>?', (digest, time.time()))
            if not token_row:
                raise HTTPException(401, 'API token is invalid, expired or revoked')
            path, method = request.url.path, request.method
            allowed = (method == 'GET' and (path in ('/api/destinations', '/api/downloads', '/api/events', '/api/version', '/api/openapi.json') or re.fullmatch(r'/api/downloads/[a-f0-9]{32}', path))) or (method == 'POST' and (path == '/api/downloads' or re.fullmatch(r'/api/downloads/[a-f0-9]{32}/(cancel|retry)', path)))
            if not allowed:
                raise HTTPException(403, 'API tokens can only submit, monitor, cancel or retry downloads and read destinations')
            return {'api_token': token_row['id'], 'token': digest}
        token = request.cookies.get('magpie_session', '')
        hashed = hashlib.sha256(token.encode()).hexdigest()
        session = store.one('SELECT * FROM sessions WHERE token=? AND expires>?', (hashed, time.time()))
        if not session:
            raise HTTPException(401, 'Sign in to Magpie')
        if request.method not in ('GET', 'HEAD') and not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
            raise HTTPException(403, 'Session security token missing; refresh and try again')
        return session
    @app.get('/api/tokens', response_model=list[ApiTokenView], dependencies=[Depends(auth)])
    def list_tokens():
        return store.all('SELECT id,name,created_at,expires_at FROM api_tokens ORDER BY created_at DESC')
    @app.post('/api/tokens', response_model=ApiTokenIssued, status_code=201, dependencies=[Depends(auth)])
    def create_token(body: ApiTokenCreate):
        name = body.name.strip()
        if not name:
            raise HTTPException(400, 'Token name cannot be blank')
        ident, secret = uuid.uuid4().hex, 'magpie_' + secrets.token_urlsafe(32)
        created, expires = now(), time.time() + body.expires_days * 86400
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM api_tokens WHERE expires_at>?', (time.time(),)).fetchone()[0] >= 20:
                raise HTTPException(409, 'Revoke an active token before creating another (limit 20)')
            db.execute('INSERT INTO api_tokens VALUES (?,?,?,?,?)', (ident, name, hashlib.sha256(secret.encode()).hexdigest(), created, expires))
        return {'id': ident, 'name': name, 'created_at': created, 'expires_at': expires, 'token': secret}
    @app.delete('/api/tokens/{ident}', dependencies=[Depends(auth)])
    def revoke_token(ident: str):
        if not store.execute('DELETE FROM api_tokens WHERE id=?', (ident,)):
            raise HTTPException(404, 'API token not found')
        return {'ok': True}
    def throttle(request):
        ip = request.client.host if request.client else 'unknown'
        bucket = attempts[ip]
        while bucket and bucket[0] < time.monotonic() - 900:
            bucket.popleft()
        if len(bucket) >= 10:
            raise HTTPException(429, 'Too many attempts. Try again in 15 minutes')
        bucket.append(time.monotonic())
        if len(attempts) > 10000:
            attempts.clear()
    def session_response():
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        store.execute('INSERT INTO sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), csrf, time.time()+86400*7, now()))
        response = JSONResponse({'authenticated': True, 'csrf': csrf})
        response.set_cookie('magpie_session', token, max_age=86400*7, httponly=True, secure=config['secure'], samesite='strict', path='/')
        return response
    @app.get('/api/auth/status')
    def auth_status(request: Request):
        try:
            session = auth(request)
            return {'authenticated': True, 'setup_required': False, 'csrf': session['csrf']}
        except HTTPException:
            return {'authenticated': False, 'setup_required': not bool(store.get('password'))}
    @app.post('/api/auth/setup')
    def setup(body: Credentials, request: Request):
        throttle(request)
        # Atomic transaction prevents simultaneous initial administrator creation.
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM kv WHERE key='password'").fetchone():
                raise HTTPException(409, 'Administrator already configured')
            if not setup_path.exists() or not secrets.compare_digest(request.headers.get('x-setup-token', ''), setup_path.read_text().strip()):
                raise HTTPException(403, 'Enter the setup token from /config/setup-token')
            db.execute('INSERT INTO kv VALUES (?,?)', ('password', json.dumps(hash_password(body.password))))
        setup_path.unlink(missing_ok=True)
        return session_response()
    @app.post('/api/auth/login')
    def login(body: Login, request: Request):
        throttle(request)
        if not verify_password(body.password, store.get('password', '')):
            raise HTTPException(401, 'Incorrect password')
        return session_response()
    @app.post('/api/auth/logout')
    def logout(session=Depends(auth)):
        store.execute('DELETE FROM sessions WHERE token=?', (session['token'],))
        response = JSONResponse({'ok': True})
        response.delete_cookie('magpie_session')
        return response
    @app.post('/api/auth/password')
    def password(body: PasswordChange, session=Depends(auth)):
        if not verify_password(body.current_password, store.get('password')):
            raise HTTPException(403, 'Current password is incorrect')
        store.set('password', hash_password(body.password))
        store.execute('DELETE FROM sessions')
        store.execute('DELETE FROM api_tokens')
        return {'ok': True}
    @app.get('/api/auth/sessions')
    def sessions(session=Depends(auth)):
        return store.all('SELECT created_at,expires,token=? AS current FROM sessions WHERE expires>?', (session['token'], time.time()))
    @app.delete('/api/auth/sessions')
    def revoke(session=Depends(auth)):
        store.execute('DELETE FROM sessions WHERE token != ?', (session['token'],))
        return {'ok': True}
    def destination(row):
        if not row:
            raise HTTPException(404, 'Destination not found')
        result = dict(row)
        try:
            path = destination_path(row['path'], config['roots'])
            result['accessible'] = os.access(path, os.R_OK | os.X_OK)
            # An actual create/write/delete probe catches read-only bind mounts and ACLs.
            with tempfile.NamedTemporaryFile(dir=path, prefix='.magpie-check-') as probe:
                probe.write(b'magpie')
                probe.flush()
            result['writable'] = True
        except (OSError, ValueError):
            result['accessible'] = result['writable'] = False
        return result
    @app.get('/api/destinations', response_model=list[DestinationView], dependencies=[Depends(auth)])
    def destinations():
        return [destination(row) for row in store.all('SELECT * FROM destinations ORDER BY is_default DESC,name')]
    @app.get('/api/roots', dependencies=[Depends(auth)])
    def permitted_roots():
        return {'roots': [str(p) for p in config['roots']]}
    @app.get('/api/folders', dependencies=[Depends(auth)])
    def folders(path: str = '', suggest: bool = False):
        # Only explicitly mounted roots and real child directories are exposed.
        if len(path) > 4096 or '..' in Path(path).parts:
            raise HTTPException(400, 'Invalid folder path')
        roots = config['roots']
        prefix = ''
        if suggest and path and not path.endswith('/'):
            prefix = Path(path).name.casefold()
            parent = str(Path(path).parent)
            if not any(Path(parent).is_relative_to(r) for r in roots):
                return {'path': '', 'parent': None, 'folders': [str(r) for r in roots if str(r).casefold().startswith(path.casefold())], 'truncated': False}
            path = parent
        if not path:
            return {'path': '', 'parent': None, 'folders': [str(r) for r in roots], 'truncated': False}
        try:
            current = Path(destination_path(path, roots))
            result = []
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.casefold().startswith(prefix) and entry.is_dir(follow_symlinks=False):
                        # Revalidate resolved children; never follow directory symlinks.
                        child = destination_path(str(current / entry.name), roots)
                        result.append(child)
                        if len(result) > 200:
                            break
            parent = str(current.parent) if any(current.parent.is_relative_to(r) for r in roots) else ''
            return {'path': str(current), 'parent': parent, 'folders': sorted(result[:200], key=str.casefold), 'truncated': len(result) > 200}
        except (OSError, ValueError):
            raise HTTPException(400, 'Folder is unavailable or outside permitted download roots')
    @app.post('/api/destinations', response_model=DestinationView, status_code=201, dependencies=[Depends(auth)])
    def add_destination(body: DestinationCreate):
        path = destination_path(body.path, config['roots'])
        ident = uuid.uuid4().hex
        with store.db() as db:
            default = body.is_default or not db.execute('SELECT 1 FROM destinations').fetchone()
            if default:
                db.execute('UPDATE destinations SET is_default=0')
            db.execute('INSERT INTO destinations VALUES (?,?,?,?,?,?)', (ident, body.name.strip(), path, body.description, body.icon, int(default)))
        return destination(store.one('SELECT * FROM destinations WHERE id=?', (ident,)))
    @app.patch('/api/destinations/{ident}', response_model=DestinationView, dependencies=[Depends(auth)])
    def edit_destination(ident: str, body: DestinationPatch):
        destination(store.one('SELECT * FROM destinations WHERE id=?', (ident,)))
        changes = body.model_dump(exclude_none=True)
        with store.db() as db:
            if changes.get('is_default'):
                db.execute('UPDATE destinations SET is_default=0')
            elif changes.get('is_default') is False:
                raise HTTPException(400, 'Choose another default destination instead')
            if changes:
                db.execute('UPDATE destinations SET '+','.join(k+'=?' for k in changes)+' WHERE id=?', (*changes.values(), ident))
        return destination(store.one('SELECT * FROM destinations WHERE id=?', (ident,)))
    @app.delete('/api/destinations/{ident}', dependencies=[Depends(auth)])
    def delete_destination(ident: str):
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE destination_id=? AND status IN ('queued','downloading')", (ident,)).fetchone():
                raise HTTPException(409, 'This destination has active jobs')
            db.execute('DELETE FROM destinations WHERE id=?', (ident,))
            if not db.execute('SELECT 1 FROM destinations WHERE is_default=1').fetchone():
                db.execute('UPDATE destinations SET is_default=1 WHERE id=(SELECT id FROM destinations ORDER BY name LIMIT 1)')
        return {'ok': True}
    def get_job(ident):
        row = store.one('SELECT * FROM jobs WHERE id=?', (ident,))
        if not row:
            raise HTTPException(404, 'Download not found')
        return row
    @app.post('/api/downloads', response_model=JobView, status_code=201, dependencies=[Depends(auth)])
    def create_download(body: DownloadCreate):
        validate_url(body.url)
        ident = uuid.uuid4().hex
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM destinations WHERE id=?', (body.destination_id,)).fetchone()
            dest = destination(dict(row) if row else None)
            if not dest['writable']:
                raise HTTPException(400, 'Destination is not writable')
            if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','downloading')").fetchone()[0] >= 1000:
                raise HTTPException(429, 'Queue is full')
            if db.execute("SELECT 1 FROM jobs WHERE url=? AND destination_id=? AND status IN ('queued','downloading')", (body.url, dest['id'])).fetchone():
                raise HTTPException(409, 'This URL is already queued for that destination')
            db.execute('INSERT INTO jobs (id,url,website,destination_id,destination_name,destination_path,created_at) VALUES (?,?,?,?,?,?,?)',
                       (ident, body.url, urlsplit(body.url).hostname.lower(), dest['id'], dest['name'], dest['path'], now()))
        return get_job(ident)
    @app.get('/api/downloads', response_model=list[JobView], dependencies=[Depends(auth)])
    def downloads(status: str = '', website: str = '', destination_id: str = '', q: str = '', since: str = '', until: str = '', limit: int = 200, offset: int = 0):
        clauses, args = [], []
        for column, value in [('status', status), ('website', website), ('destination_id', destination_id)]:
            if value:
                clauses.append(column+'=?'); args.append(value)
        if q:
            clauses.append('instr(lower(url),lower(?))>0'); args.append(q)
        if since:
            clauses.append('created_at>=?'); args.append(since)
        if until:
            clauses.append('created_at<=?'); args.append(until+'T23:59:59.999999+00:00')
        return store.all('SELECT * FROM jobs' + (' WHERE '+' AND '.join(clauses) if clauses else '')+' ORDER BY seq DESC LIMIT ? OFFSET ?', (*args, max(1,min(limit,500)), max(0,offset)))
    @app.delete('/api/downloads', dependencies=[Depends(auth)])
    def clear_history():
        store.execute("DELETE FROM jobs WHERE status NOT IN ('queued','downloading')")
        return {'ok': True}
    @app.get('/api/downloads/{ident}', response_model=JobView, dependencies=[Depends(auth)])
    def job_details(ident: str):
        return get_job(ident)
    @app.post('/api/downloads/{ident}/cancel', dependencies=[Depends(auth)])
    def cancel(ident: str):
        get_job(ident)
        with store.db() as db:
            db.execute("UPDATE jobs SET status='cancelled',completed_at=? WHERE id=? AND status='queued'", (now(),ident))
            db.execute("UPDATE jobs SET cancel_requested=1 WHERE id=? AND status='downloading'", (ident,))
        return {'ok': True}
    @app.post('/api/downloads/{ident}/retry', response_model=JobView, dependencies=[Depends(auth)])
    def retry(ident: str):
        row = get_job(ident)
        # URL DNS and original filesystem snapshot are revalidated at retry and execution.
        validate_url(row['url'])
        destination_path(row['destination_path'], config['roots'])
        changed = store.execute("UPDATE jobs SET status='queued',created_at=?,started_at=NULL,completed_at=NULL,error=NULL,files=0,skipped=0,bytes=0,speed=NULL,current_filename=NULL,file_bytes=NULL,file_total=NULL,total_files=NULL,cancel_requested=0,seq=(SELECT COALESCE(MAX(seq),0)+1 FROM jobs) WHERE id=? AND status IN ('failed','cancelled','interrupted')", (now(),ident))
        if not changed:
            raise HTTPException(409, 'Only failed, cancelled or interrupted jobs may be retried')
        return get_job(ident)
    @app.delete('/api/downloads/{ident}', dependencies=[Depends(auth)])
    def remove(ident: str):
        row = get_job(ident)
        changed = store.execute("DELETE FROM jobs WHERE id=? AND status NOT IN ('queued','downloading')", (ident,))
        if not changed:
            raise HTTPException(409, 'Cancel the download before removing it')
        return {'ok': True}
    @app.get('/api/settings', response_model=Settings, dependencies=[Depends(auth)])
    def settings():
        return store.get('settings')
    @app.patch('/api/settings', response_model=Settings, dependencies=[Depends(auth)])
    def update_settings(body: dict):
        updated = Settings.model_validate({**store.get('settings'), **body})
        store.set('settings', updated.model_dump())
        return updated
    @app.get('/api/cookies', dependencies=[Depends(auth)])
    def cookies():
        return store.all('SELECT * FROM cookies ORDER BY website')
    @app.post('/api/cookies', status_code=201, dependencies=[Depends(auth)])
    async def upload_cookie(website: str = Form(...), file: UploadFile = File(...)):
        website = website.strip().lower()
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', website) or '.' not in website:
            raise HTTPException(400, 'Use a website domain such as example.com')
        data = await file.read(1024*1024+1)
        await file.close()
        if len(data) > 1024*1024:
            raise HTTPException(413, 'Cookie file exceeds 1 MiB')
        ident = uuid.uuid4().hex
        target = directory / 'cookies' / (ident+'.txt')
        try:
            data.decode('utf-8')
            target.write_bytes(data)
            target.chmod(0o600)
            jar = http.cookiejar.MozillaCookieJar(str(target))
            jar.load(ignore_discard=True, ignore_expires=True)
            if not list(jar) or any(not (c.domain.lstrip('.') == website or c.domain.lstrip('.').endswith('.'+website)) for c in jar):
                raise ValueError('Cookie domains must match the assigned website')
        except Exception:
            target.unlink(missing_ok=True)
            raise HTTPException(400, 'Invalid Netscape cookie file or mismatched cookie domains')
        with store.db() as db:
            old = db.execute('SELECT id FROM cookies WHERE website=?', (website,)).fetchone()
            db.execute('INSERT OR REPLACE INTO cookies VALUES (?,?,?)', (ident,website,now()))
        # Old immutable versions are kept while workers may hold them open.
        # They contain credentials, so delete them once no active job exists.
        if old and not queue.active:
            (directory / 'cookies' / (old['id']+'.txt')).unlink(missing_ok=True)
        return {'id': ident, 'website': website, 'updated_at': now()}
    @app.delete('/api/cookies/{ident}', dependencies=[Depends(auth)])
    def delete_cookie(ident: str):
        row = store.one('SELECT id FROM cookies WHERE id=?', (ident,))
        if not row:
            raise HTTPException(404, 'Cookie file not found')
        if queue.active:
            raise HTTPException(409, 'Wait for active downloads before deleting credentials')
        store.execute('DELETE FROM cookies WHERE id=?', (ident,))
        (directory / 'cookies' / (row['id']+'.txt')).unlink(missing_ok=True)
        return {'ok': True}
    @app.get('/api/health')
    def health():
        store.one('SELECT 1')
        return {'status': 'ok'}
    @app.get('/api/version', dependencies=[Depends(auth)])
    def version():
        return {'magpie': VERSION, 'gallery_dl': gallery_dl.version.__version__,
                'yt_dlp': yt_dlp.version.__version__,
                'video_javascript': (media_tool_directory() / 'node').is_file(),
                'ffmpeg': all((media_tool_directory() / name).is_file() for name in ('ffmpeg', 'ffprobe'))}
    @app.get('/api/system', dependencies=[Depends(auth)])
    def system():
        import ctypes
        abi = ctypes.CDLL(None).syscall(444, 0, 0, 1)
        return {**version(), 'health': 'ok', 'landlock_abi': max(0, abi), 'active_workers': len(queue.active),
                'queue_running': queue.task is not None and not queue.task.done(),
                'recent_errors': store.all("SELECT id,website,error,completed_at FROM jobs WHERE error IS NOT NULL ORDER BY seq DESC LIMIT 30"),
                'logs': 'Sanitised job errors appear below. Structured request-free lifecycle logs are written to container stdout.'}
    @app.get('/api/events')
    async def events(request: Request, session=Depends(auth)):
        async def stream():
            previous = None
            while not await request.is_disconnected():
                valid = (store.one('SELECT 1 FROM api_tokens WHERE id=? AND expires_at>?', (session['api_token'], time.time())) if 'api_token' in session else store.one('SELECT 1 FROM sessions WHERE token=? AND expires>?', (session['token'], time.time())))
                if not valid:
                    yield 'event: expired\ndata: {}\n\n'
                    break
                current = {'downloads': store.all('SELECT id,status,files,skipped,total_files,bytes,speed,current_filename,file_bytes,file_total,error FROM jobs ORDER BY seq DESC LIMIT 200')}
                encoded = json.dumps(current)
                if encoded != previous:
                    yield 'event: update\ndata: ' + encoded + '\n\n'
                    previous = encoded
                else:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering':'no'})
    @app.get('/api/openapi.json', dependencies=[Depends(auth)])
    def openapi():
        schema = app.openapi()
        schemes = schema.setdefault('components', {}).setdefault('securitySchemes', {})
        schemes['AppToken'] = {'type': 'http', 'scheme': 'bearer', 'description': 'Create a scoped app token in Settings → API.'}
        schemes['AdminSession'] = {'type': 'apiKey', 'in': 'cookie', 'name': 'magpie_session', 'description': 'Mutations also require X-CSRF-Token.'}
        for path, methods in schema['paths'].items():
            app_access = path in ('/api/destinations', '/api/events', '/api/version', '/api/openapi.json') or path.startswith('/api/downloads')
            for method, operation in methods.items():
                if method not in ('get', 'post', 'patch', 'delete') or not isinstance(operation, dict):
                    continue
                if path in ('/api/health', '/api/auth/setup', '/api/auth/login', '/api/auth/status'):
                    continue
                allowed = app_access and (method == 'get' or (method == 'post' and (path == '/api/downloads' or path.endswith(('/cancel', '/retry')))))
                operation['security'] = [{'AdminSession': []}] + ([{'AppToken': []}] if allowed else [])
        return schema
    # SPA fallback must not hide unknown API endpoints.
    static = Path(os.environ.get('MAGPIE_STATIC', str(Path(__file__).resolve().parents[2] / 'static')))
    if (static / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=static / 'assets'), name='assets')
    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str):
        if path.startswith('api/'):
            raise HTTPException(404, 'Endpoint not found')
        if path in ('logo.svg','favicon.svg','logo.png','bird.ttf') and (static/path).is_file():
            return FileResponse(static/path)
        if (static/'index.html').is_file():
            return FileResponse(static/'index.html')
        raise HTTPException(503, 'Frontend build missing; build the Docker image or run Vite for development')
    return app
