# App API

Create a named token under **Settings → API**. Copy it immediately: Magpie stores
only its SHA-256 hash. Tokens expire after 1–365 days (default 90), or never expire when you select
**Never expires** or send `"expires_days": null`. They persist across
restarts, and can be revoked individually. Changing the administrator password
revokes every app token and session. Limit: 20 active tokens.

Use HTTPS through your reverse proxy or your trusted private network. Never put
tokens in URLs, logs or client-side public code. Connect from your app's server;
cross-origin browser access is restricted. Cookie-based browser requests still
require CSRF protection; Bearer clients do not need a CSRF token.

Set `MAGPIE_URL` to your instance (e.g. `http://NAS-IP:9080`) and `MAGPIE_TOKEN`
to your app token in your integration's private environment.

```sh
# Get destination IDs
curl "$MAGPIE_URL/api/destinations" \
  -H "Authorization: Bearer $MAGPIE_TOKEN"

# Submit a gallery; response includes the job ID
curl "$MAGPIE_URL/api/downloads" \
  -H "Authorization: Bearer $MAGPIE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"url":"https://example.com/gallery","category":"Pictures"}'

# Poll at most once per second until completed, failed, cancelled or interrupted
curl "$MAGPIE_URL/api/downloads/JOB_ID" \
  -H "Authorization: Bearer $MAGPIE_TOKEN"

# Or stream live updates
curl -N "$MAGPIE_URL/api/events" \
  -H "Authorization: Bearer $MAGPIE_TOKEN"
```

`POST /api/downloads` returns 201 (accepted into the persistent queue), 409 for an
active duplicate, 400 for invalid/unsafe URLs, or 404 for a missing destination.
The queue continues independently of connected clients.

## Choose a destination by label

Send `"category": "Pictures"` to select the destination labelled **Pictures**.
Matching ignores case and surrounding whitespace. The label must identify exactly
one configured destination. Existing `"destination_id": "DESTINATION_ID"` requests
continue to work. Supply exactly one of `category` or `destination_id` (422 if both
or neither are supplied). Unknown categories return 404; ambiguous labels return
409. Unwritable destinations return 400. No paths or directories are created from
category text. The chosen destination is saved with the job, so later renaming the
label does not redirect queued jobs or change their archive.

## Progress

| Field | Meaning |
| --- | --- |
| `file_progress_percent` | Current-file percentage (0–100), rounded to two decimals; null without a valid measured total |
| `album_progress_percent` | Album percentage (0–100) by downloaded + skipped files; null without a valid known total |
| `status` | queued, downloading, completed, failed, cancelled, interrupted |
| `current_filename` | Current file, when available |
| `file_bytes`, `file_total` | Current file bytes and measured total; nullable |
| `speed` | Bytes per second, or null when unavailable |
| `bytes` | Cumulative transferred/finalized bytes for this attempt |
| `files`, `skipped` | Successfully downloaded and skipped files this attempt |
| `total_files` | Known gallery size; null when unknown (Bunkr albums supported) |

These explicit percentage fields appear in individual/list REST responses and SSE
updates. Album progress is file-count based, not byte-weighted across the album.
An unknown, zero or inconsistent total yields null; completion status never
fabricates a total. After a file finishes, its byte counters clear and its file
percentage becomes null until another measurable file starts.

Current file fraction: `file_bytes / file_total` only when the total is positive.
Gallery fraction: `(files + skipped) / total_files` only when the total is known
and at least the number handled. Never infer a percentage when totals are null.
Failures do not count as successful files. Retries reset attempt counters and
consult destination-specific archives to skip previously completed media.

SSE emits an initial `update`, then changed snapshots at most once per second:

```text
event: update
data: {"downloads":[{"id":"...","status":"downloading","files":6,"skipped":2,"total_files":20,"bytes":123456,"speed":1024,"current_filename":"image.jpg","file_bytes":50,"file_total":100,"file_progress_percent":50.0,"album_progress_percent":40.0,"error":null}]}
```

Snapshots include the latest 200 jobs, not the entire history. Poll a specific ID
for older jobs. Unchanged snapshots send heartbeat comments. An `expired` event
closes an expired/revoked connection. Reconnect after network failures; snapshots
contain current state, without event replay. Browser `EventSource` cannot attach
Bearer headers: use `fetch` streaming, an SSE library with headers, or polling.

## Permissions and control

Tokens may access:

- `GET /api/destinations`
- `POST /api/downloads`
- `GET /api/downloads` and `GET /api/downloads/{id}`
- `POST /api/downloads/{id}/cancel` and `POST /api/downloads/{id}/retry`
- `GET /api/events`, `/api/version`, `/api/openapi.json`

Tokens may see and control all instance downloads, including jobs from other
apps. They cannot change settings, access cookies, browse folders, manage tokens,
or delete history. Invalid/expired/revoked credentials return 401; actions outside
the token's permissions return 403. Errors use `{"error":{"code":"...","message":"..."}}`.

Token management is administrator-session-only: `GET /api/tokens`,
`POST /api/tokens` with `{"name":"My app","expires_days":90}`, and
`DELETE /api/tokens/{id}`. Create/delete requests require `X-CSRF-Token`.
Omitting `expires_days` keeps the default 90-day expiry; `null` means no expiry.
Non-expiring tokens still count toward the 20-active-token limit and can be revoked
manually or by changing the administrator password.
The authenticated OpenAPI schema documents request and response models.

## Custom filename fields

Optional `custom_fields` is an object containing up to 10 named text values.
`filename_position` is `"start"` (default) or `"end"`. Values are joined with
` - ` in the JSON order supplied; field names are descriptive labels, not part
of the resulting filename. The original/native filename and extension remain.
End-position values go before the extension. For example:

```sh
curl "$MAGPIE_URL/api/downloads" \
  -H "Authorization: Bearer $MAGPIE_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{
    "url": "https://example.com/gallery",
    "category": "Pictures",
    "custom_fields": {"creator": "Alice", "collection": "Nature"},
    "filename_position": "end"
  }'
```

`original.jpg` becomes `original - Alice - Nature.jpg`; choosing `"start"`
produces `Alice - Nature - original.jpg`. Flat-with-gallery-name mode combines
both, for example `Summer gallery - original - Alice - Nature.jpg`.

Names must start with a letter and contain at most 40 ASCII letters, numbers,
spaces, underscores or hyphens. Values must be non-empty strings of up to 100
characters. Values are literal, never executable templates or paths. Unsafe
filename characters are replaced, and long names shortened with a stable hash.
The selected destination remains the filesystem boundary.

Fields and position are returned in REST job responses and SSE updates, stored
in history and retained by retries/restarts. They do not override extractor
metadata, alter directory templates or change the archive identity. Sending the
same album to the same destination with different custom labels still skips
archived media; it does not create another copy or rename existing files.
