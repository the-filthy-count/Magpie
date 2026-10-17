# App API

Create a named token under **Settings → API**. Copy it immediately: Magpie stores
only its SHA-256 hash. Tokens expire after 1–365 days (default 90), persist across
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
  --data '{"url":"https://example.com/gallery","destination_id":"DESTINATION_ID"}'

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

## Progress

| Field | Meaning |
| --- | --- |
| `status` | queued, downloading, completed, failed, cancelled, interrupted |
| `current_filename` | Current file, when available |
| `file_bytes`, `file_total` | Current file bytes and measured total; nullable |
| `speed` | Bytes per second, or null when unavailable |
| `bytes` | Cumulative transferred/finalized bytes for this attempt |
| `files`, `skipped` | Successfully downloaded and skipped files this attempt |
| `total_files` | Known gallery size; null when unknown (Bunkr albums supported) |

Current file fraction: `file_bytes / file_total` only when the total is positive.
Gallery fraction: `(files + skipped) / total_files` only when the total is known
and at least the number handled. Never infer a percentage when totals are null.
Failures do not count as successful files. Retries reset attempt counters and
consult destination-specific archives to skip previously completed media.

SSE emits an initial `update`, then changed snapshots at most once per second:

```text
event: update
data: {"downloads":[{"id":"...","status":"downloading","files":6,"skipped":2,"total_files":20,"bytes":123456,"speed":1024,"current_filename":"image.jpg","file_bytes":50,"file_total":100,"error":null}]}
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
The authenticated OpenAPI schema documents request and response models.
