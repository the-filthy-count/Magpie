<p align="center">
  <img src="brand/brand.webp" alt="Logo" width="500">
</p>

**Find it. Fetch it. File it.**

A self-hosted, single-container media downloader for your NAS. Paste a public gallery-dl-supported HTTP(S) link, pick a configured destination, and **Pluck**.

Python 3.12+, FastAPI, gallery-dl 1.32.16, yt-dlp 2026.8.19, FFmpeg, SQLite, React, TypeScript, Vite and Tailwind. No external database, cloud service or separate queue service. The interface and authenticated API share port **9080**.

## Deploy with Docker Compose

Use Docker Compose on a Linux server or a NAS with Docker support. You can create a Compose project through your platform's container manager or run the commands from a terminal. The published image targets Linux AMD64. The Dockerfile uses multi-architecture base images suitable for ARM64; ARM64 has not been tested.

**Host requirement:** Linux 5.13 or later with Landlock enabled and available through Docker's seccomp profile. Workers refuse to download if kernel-enforced filesystem confinement cannot be installed. Some NAS firmware kernels disable Landlock even on recent hardware; verify before deployment. Do not disable this boundary to make an unsupported NAS kernel work. An updated NAS kernel/firmware or a supported Linux VM is needed in that case.

1. Copy this project to a persistent shared folder, for example `/srv/magpie` (use a suitable path on your host).
2. Copy `.env.example` to `.env`. Set `PUID` and `PGID` to the NAS account that owns your download directories (`id` over SSH shows them). These are **image build arguments**, so rebuild after changing them.
3. Set `PICTURES_PATH`, `MODELS_PATH` and `OTHER_PATH` to existing absolute NAS paths. Set `MAGPIE_BIND_IP` to the NAS's LAN IP. Add that IP and your reverse proxy hostname to the comma-separated `MAGPIE_ALLOWED_HOSTS` list, keeping `127.0.0.1` for the health check. The default bind address is loopback.
4. Prepare the config directory and give only the container user write access. Also ensure the chosen NAS account can write the three bind mounts. Example for a fresh installation:

   ```sh
   mkdir -p config
   sudo chown 1000:1000 config  # use your PUID:PGID
   chmod 700 config
   docker compose up -d --build
   ```

   Create the download folders using your host's file manager or terminal and set their ownership/ACLs for that account. Magpie runs non-root and deliberately does not chown NAS media directories.
5. Read the one-time setup token with `docker compose exec magpie cat /config/setup-token`. Open `http://<NAS-IP>:9080`, enter that token, and create an administrator password of at least 12 characters. The token file is removed after successful setup. There is no default administrator password.
6. In **Destinations**, add `Pictures → /downloads/pictures`, `Models → /downloads/models` and `Other → /downloads/other`. A write probe reports actual mount accessibility. Select the default destination.
7. Paste a supported URL on **Downloads**, select its destination, and click **Pluck** (or press Enter).

The health check is `GET /api/health`. `docker compose ps` reports health. Check `docker compose logs --tail=100 magpie` for structured lifecycle logs. Do not forward port 9080 on your router. Tailscale and a local HTTPS reverse proxy work well for private access.

### Reverse proxy and HTTPS

Terminate HTTPS at your proxy and set `MAGPIE_SECURE_COOKIES=true`. Preserve the original `Host` and allow server-sent event connections without buffering. Magpie intentionally ignores forwarded client-IP headers; do not enable trust for arbitrary proxies. Login throttling therefore applies to the proxy address as a shared bucket. For nginx:

```nginx
location / {
    proxy_pass http://NAS_LAN_IP:9080;
    proxy_set_header Host $host;
    proxy_buffering off;
    proxy_read_timeout 120s;
}
```

Keep the upstream port private. Secure cookies require HTTPS in the browser. SameSite=Strict sessions, same-origin checks and a session-bound CSRF header protect writes. Direct HTTP LAN access uses HttpOnly SameSite cookies; set secure cookies when HTTPS is available.

### Changing mounts

Add a Docker bind mount and include its **container path** in `MAGPIE_DOWNLOAD_ROOTS` (colon separated), then recreate the container. In the UI, add a destination inside one of these roots. The web application cannot browse your host filesystem or add Docker mounts. Destination paths can be edited when no queued or downloading jobs use that destination. Select an existing writable folder under a permitted root. Changing the path starts a fresh archive for new jobs; old jobs retain their original path and archive for retries. No media is moved or deleted. Jobs snapshot the selected name/path, so later renaming does not reroute queued work. Active destinations cannot be removed. Removing destinations or clearing history never removes media or archives.

## How downloads work

* SQLite stores FIFO queue claims, history, settings, destinations, cookie assignments and hashed sessions beneath `/config`.
* Default concurrency is 2, configurable from 1–5. Only one scheduler may use a config directory; do not run multiple Uvicorn workers/replicas.
* The worker runs the real gallery-dl `DownloadJob` in a dedicated process group, with an independent configuration and no shell. SIGTERM is followed by SIGKILL after five seconds when needed. `MAGPIE_JOB_TIMEOUT` bounds total job lifetime (default 24 hours), independently of per-request timeouts.
* Queued jobs resume automatically at startup. Jobs that were downloading become **Interrupted** and can be retried. Shutdown terminates workers and marks them Interrupted. Retry puts a job at the back of the FIFO and preserves the original destination.
* Archive SQLite files live under `/config/archives/<archive-id>/archive.sqlite3`. Each destination has a persistent archive; changing its path assigns a fresh archive for new jobs while old jobs retain their original one. Only gallery-dl's successful `file` event writes an archive record. Skipped existing files are not newly archived. Separate destinations have separate archives. Native existing-file checks also avoid duplicate output.
* File count and byte count are observed events, not estimates. The UI uses indeterminate overall progress because gallery-dl does not consistently know collection size. A percentage is shown only for a current file with a known total. Transfer speed is shown only when emitted by gallery-dl. Browser closure does not affect jobs.
* **Organised** preserves each gallery-dl extractor's native directory layout and original-quality preference. **Flat** removes directory levels. **Custom** accepts plain metadata fields as directory components, one per line. Native extractor filenames are used unless overridden. Missing metadata in custom templates depends on the source; choose fields present for that extractor. Expressions, path separators and traversal are rejected.
* **Video support is bundled:** gallery-dl delegates video extraction and native HTTP/HLS/DASH downloads to yt-dlp. If gallery-dl has no extractor for a submitted URL, Magpie retries it through gallery-dl's yt-dlp adapter. YouTube links and yt-dlp-supported video pages use the same Pluck workflow, destinations, cookies, queue, cancellation, progress and per-destination gallery-dl archives. A failed supported gallery-dl extractor is not blindly retried with another engine.
* **FFmpeg and FFprobe** merge separate audio/video streams and inspect local media. Native Python downloaders retrieve streams through Magpie's network checks. FFmpeg helpers inherit the filesystem boundary, receive an additional media-only write/read boundary, and are denied network sockets by seccomp. They cannot access `/config` credentials or fetch network playlists. External network downloaders and arbitrary command postprocessors remain disabled.
* **YouTube challenge support** includes the pinned official `yt-dlp-ejs` package and Node 24 runtime. Node runs with its permission model plus the same kernel network/filesystem restrictions; child processes, native addons and filesystem APIs are denied to challenge JavaScript. Remote component downloads are disabled. Login, geo-restrictions, unavailable videos and site changes may still require valid cookies or an engine update; Magpie does not bypass access restrictions. No separate website support list is maintained.

## Authentication and cookies

Upload UTF-8 **Netscape cookies.txt** files in Settings → Authentication. Assign a domain such as `example.com`; cookie domains must match that website or its subdomains. Do not paste cookie contents into configuration. Files are stored with mode 0600 under `/config/cookies`, and never returned by an API or included in logs. Uploading a domain again replaces its configured version. Active workers retain the immutable version they started with; deleting credentials waits for active jobs to finish. Only provide cookies for accounts and content you are authorised to access.

The password is scrypt-hashed with a random salt. Session bearer tokens are stored only as SHA-256 digests, expire after seven days, and are revocable. Password changes revoke all sessions. Ten login/setup attempts per client address per 15 minutes are allowed. No default password exists.

## Security boundaries

* URLs are validated at submission and retry. Only HTTP(S), default ports, public DNS addresses and credential-free URLs are accepted. The worker checks and pins the actual destination at every socket connection. This covers API requests, media URLs and redirect targets, and prevents a DNS change between initial validation and connection from reaching private addresses. Proxy environment variables are disabled in workers. Public websites hosted on nonstandard ports are intentionally unavailable.
* Every worker installs a Linux Landlock write allowlist covering only its selected media root and its own archive directory. Kernel checks enforce the boundary for symlinks, traversal, file creation, rename and (on Landlock ABI 3+) truncate. Validation also resolves destination paths against explicit permitted roots. Media cannot write into `/config` credentials, the application or another destination. Mount owners must be trusted; do not share write access to destination directories with hostile local processes.
* Arbitrary gallery-dl config is never accepted. Advanced JSON supports `sleep-request` (0–120), `sleep` (0–120) and `sleep-retries` (0–300) in seconds. Retry, timeout, rate, organisation and safe templates have dedicated fields. User-supplied commands, hooks, executable postprocessors, executable format strings, proxy overrides and file-path options are blocked. Only the bundled sandboxed FFmpeg/FFprobe and YouTube JavaScript wrappers may start as subprocesses; they remain in the job process group for cancellation.
* Non-root runtime, a read-only container filesystem, no capabilities, no-new-privileges, a process limit, bounded queue and memory limit are configured in Compose. No Docker socket or privileged mode is used.
* No remote favicon requests are made: neutral source icons avoid leaking browsing history and fetching untrusted website assets. Log messages from gallery-dl are classified rather than echoed, because upstream messages may embed secret URLs or credentials. History is intentionally visible to the authenticated administrator and stores original URLs. Protect and back up `/config` accordingly.

## Settings, retention and backup

Settings include destination default, parallelism, theme (dark/light/system), retention, retries, timeouts, bytes-per-second rate limit, organisation, templates and safe advanced timing options. New engine settings apply when a worker starts. Automatic retention runs hourly and removes terminal job history older than the configured days. Set days to 0 to retain forever. Files, archives and cookies are unaffected.

Stop Magpie before backing up `/config` to capture a consistent SQLite database plus archives and credentials. Back up your media mounts separately. Restore `/config` and the same mount paths/ownership, then start the container. An archive intentionally still suppresses a previously downloaded file if that file is manually deleted; remove the destination's archive offline only when you deliberately want to redownload its complete archive history.

If you lose the administrator password, stop Magpie, back up `/config`, and use a trusted local SQLite client to delete the `password` key in `kv` and all rows in `sessions`. Restart to generate a new one-time setup token. Anyone with write access to `/config` controls the application.

## API

Protected, Pydantic-validated JSON REST endpoints use the same administrator session as the UI. Retrieve `/api/auth/status` for the session CSRF token. Send `X-CSRF-Token` on writes. Authenticate via `POST /api/auth/login` with `{"password":"…"}` and retain the returned session cookie. Setup additionally requires `X-Setup-Token`.

| Endpoint | Purpose |
| --- | --- |
| `GET/POST /api/downloads` | Filter/list jobs, enqueue a URL with `destination_id` |
| `GET/DELETE /api/downloads/{id}` | Details / remove terminal history |
| `POST /api/downloads/{id}/cancel` | Cancel queued/running job |
| `POST /api/downloads/{id}/retry` | Retry failed/cancelled/interrupted job |
| `DELETE /api/downloads` | Clear terminal history, preserve media |
| `GET/POST /api/destinations` | List/add configured destinations |
| `PATCH/DELETE /api/destinations/{id}` | Rename/change default/remove unused destination |
| `GET/PATCH /api/settings` | Read/validate settings |
| `GET /api/events` | Authenticated SSE invalidations; fetch current records on update |
| `GET /api/health` | Public minimal health probe |
| `GET /api/version` | Installed app/engine versions |
| `GET /api/system` | Scheduler/worker status and sanitised recent errors |
| `GET/POST /api/cookies` | List cookie metadata / multipart domain + file upload |
| `DELETE /api/cookies/{id}` | Delete configured cookie file |
| `GET/DELETE /api/auth/sessions` | List sessions / revoke others |
| `POST /api/auth/password` | Change password, revoke sessions |
| `GET /api/openapi.json` | Authenticated complete OpenAPI schema |

Filters: `status`, `website`, `destination_id`, `q` (URL substring), `since`, `until` (ISO dates), `limit` (1–500), `offset`. Errors have `{"error":{"code":"…","message":"…"}}`. Cookies and passwords are omitted from error payloads.

## Development and tests

Use Linux with Landlock enabled. From `backend`:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest -q
MAGPIE_CONFIG=/tmp/magpie-dev MAGPIE_DOWNLOAD_ROOTS=/absolute/dev/downloads python -m app
```

For the full video runtime, use the Docker image (it installs FFmpeg, Node and trusted wrapper scripts). Host-only video merge tests need FFmpeg on PATH and create disposable wrappers. Create the download root first. From `frontend`, run `npm ci`, `npm test`, `npm run build`, or `npm run dev` (Vite proxies `/api` to port 9080). For a same-origin local production run, copy `frontend/dist` into `backend/static` or set `MAGPIE_STATIC` to its absolute path.

Tests cover URL/DNS/network rejection, kernel write boundaries, symlink/traversal attempts, authentication, CSRF, login limits, destinations, job creation/cancel/retry, settings, cookies, persistence, FIFO, bounded parallelism and process-group termination. The deterministic real-engine integration replaces **only HTTP transport**, then exercises gallery-dl's actual extractor, downloader, output events, file finalization and persistent archive across subprocess restarts. Additional video tests exercise real yt-dlp generic extraction, native downloads, archive reuse, flat organisation, real FFmpeg audio/video merging, accurate progress, helper filesystem/network confinement and restricted JavaScript execution. No uncontrolled external site is required by the automated suite.

See `VALIDATION.md` for checks actually performed in this build, including the separate public-network container smoke test and limitations.

## Brand and license

The application uses the supplied Magpie illustration, Bird identity font and six-colour palette; see `assets/branding/README.md`. SVG files losslessly embed the supplied raster illustration rather than pretending it is vector artwork. Original Magpie code is GPL-2.0-only, compatible with its gallery-dl integration. The complete license is in `COPYING`. Supplied brand assets retain their original ownership/licensing.

## App integrations

Create scoped Bearer tokens under **Settings → API** to submit galleries and monitor individual file and album progress. See [the app API guide](docs/API.md) for curl examples, live events and permissions.

## Download preferences

Settings → Download engine includes flat layouts with gallery-title filenames, video quality/format, playlist handling, media filters, file/size limits, subtitles, daily hours, automatic interrupted-job recovery and website defaults. Destinations can override organisation. See [Download settings](docs/DOWNLOAD_SETTINGS.md) for precedence, examples and engine limitations.
