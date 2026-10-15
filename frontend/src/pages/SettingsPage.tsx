import { useState, useEffect } from "react";
import { Check, Plus, RefreshCw, ShieldCheck, Trash2, Activity, ExternalLink } from "lucide-react";
import { api, bytes, date, Job, Destination } from "../services/api";
type Notice = (message: string) => void;
const active = (j: Job) => ["queued", "downloading"].includes(j.status);
export default function SettingsPage({
  settings,
  refresh,
  destinations,
  reload,
  notify,
}: {
  settings: any;
  refresh: () => Promise<void>;
  destinations: Destination[];
  reload: () => Promise<void>;
  notify: Notice;
}) {
  const [draft, setDraft] = useState(settings),
    [advanced, setAdvanced] = useState(
      JSON.stringify(settings.advanced, null, 2),
    ),
    [directory, setDirectory] = useState(settings.directory.join("\n")),
    [tab, setTab] = useState("general"),
    [system, setSystem] = useState<any>(null),
    [cookies, setCookies] = useState<any[]>([]),
    [sessions, setSessions] = useState<any[]>([]),
    [domain, setDomain] = useState(""),
    [file, setFile] = useState<File | null>(null),
    [error, setError] = useState(""),
    [password, setPassword] = useState(""),
    [current, setCurrent] = useState("");
  const load = () => {
    api("/system")
      .then(setSystem)
      .catch((e) => notify(e.message));
    api("/cookies")
      .then(setCookies)
      .catch((e) => notify(e.message));
    api("/auth/sessions")
      .then(setSessions)
      .catch((e) => notify(e.message));
  };
  useEffect(load, [notify]);
  const update = (key: string, value: any) =>
    setDraft({ ...draft, [key]: value });
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">JUST THE WAY YOU LIKE IT</div>
          <h1>
            Make yourself at home<span>.</span>
          </h1>
          <p>A few thoughtful settings for your little collector.</p>
        </div>
        <span className="subtle-badge">
          Magpie v{system?.magpie || "1.0.0"}
        </span>
      </div>
      <div className="settings-tabs">
        {["general", "engine", "authentication", "system"].map((t) => (
          <button
            key={t}
            className={tab === t ? "active" : ""}
            onClick={() => {
              setTab(t);
              setError("");
            }}
          >
            {t === "engine"
              ? "Download engine"
              : t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {(tab === "general" || tab === "engine") && (
        <form
          className="settings-card settings-form"
          onSubmit={async (e) => {
            e.preventDefault();
            setError("");
            try {
              await api("/settings", "PATCH", {
                ...draft,
                advanced: JSON.parse(advanced),
                directory: directory
                  .split("\n")
                  .map((s: string) => s.trim())
                  .filter(Boolean),
              });
              await refresh();
              notify("Settings saved");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          <h2>{tab === "general" ? "The essentials" : "Under the feathers"}</h2>
          <p className="muted">
            {tab === "general"
              ? "Small preferences. A smoother workflow."
              : `Powered by gallery-dl ${system?.gallery_dl || "…"}. Video downloads also use yt-dlp. Settings apply to the next job.`}
          </p>
          <div className="form-grid">
            {tab === "general" ? (
              <>
                <label>
                  Default destination
                  <select
                    value={destinations.find((d) => d.is_default)?.id || ""}
                    onChange={async (e) => {
                      try {
                        await api("/destinations/" + e.target.value, "PATCH", {
                          is_default: true,
                        });
                        reload();
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }}
                  >
                    <option value="" disabled>
                      No destination configured
                    </option>
                    {destinations.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Concurrent downloads
                  <input
                    type="number"
                    min="1"
                    max="5"
                    value={draft.concurrency}
                    onChange={(e) =>
                      update("concurrency", Number(e.target.value))
                    }
                  />
                  <small>One to five downloads at a time.</small>
                </label>
                <label>
                  Interface theme
                  <select
                    value={draft.theme}
                    onChange={(e) => update("theme", e.target.value)}
                  >
                    {["dark", "light", "system"].map((v) => (
                      <option key={v}>{v}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Keep history for (days)
                  <input
                    type="number"
                    min="0"
                    max="3650"
                    value={draft.retention_days}
                    onChange={(e) =>
                      update("retention_days", Number(e.target.value))
                    }
                  />
                  <small>
                    Set to 0 to keep forever. Media and archives are kept.
                  </small>
                </label>
              </>
            ) : (
              <>
                <label>
                  Retry attempts
                  <input
                    type="number"
                    min="0"
                    max="20"
                    value={draft.retries}
                    onChange={(e) => update("retries", Number(e.target.value))}
                  />
                </label>
                <label>
                  Request timeout (seconds)
                  <input
                    type="number"
                    min="5"
                    max="300"
                    value={draft.timeout}
                    onChange={(e) => update("timeout", Number(e.target.value))}
                  />
                </label>
                <label>
                  Rate limit (bytes / second)
                  <input
                    type="number"
                    min="0"
                    max="1000000000"
                    value={draft.rate_limit}
                    onChange={(e) =>
                      update("rate_limit", Number(e.target.value))
                    }
                  />
                  <small>0 uses the available connection speed.</small>
                </label>
                <label>
                  Download organisation
                  <select
                    value={draft.organisation}
                    onChange={(e) => update("organisation", e.target.value)}
                  >
                    <option value="organised">
                      Organised · native website layout
                    </option>
                    <option value="flat">Flat · destination folder</option>
                    <option value="custom">Custom · your templates</option>
                  </select>
                </label>
                <label className="wide">
                  Filename template
                  <input
                    placeholder="Use gallery-dl's native filename"
                    value={draft.filename}
                    onChange={(e) => update("filename", e.target.value)}
                  />
                  <small>
                    Plain metadata fields, for example{" "}
                    {"{filename}.{extension}"}. Leave empty for native naming.
                  </small>
                </label>
                {draft.organisation === "custom" && (
                  <label className="wide">
                    Directory components · one per line
                    <textarea
                      value={directory}
                      onChange={(e) => setDirectory(e.target.value)}
                      placeholder={"{category}\n{user}"}
                    />
                    <small>
                      Each line is one folder. Choose fields supported by the
                      source extractor.
                    </small>
                  </label>
                )}
                <label className="wide">
                  Advanced configuration (JSON)
                  <textarea
                    value={advanced}
                    onChange={(e) => setAdvanced(e.target.value)}
                    spellCheck={false}
                  />
                  <small>
                    Supported keys: sleep-request (0–120), sleep (0–120),
                    sleep-retries (0–300), in seconds. Command execution and
                    external paths are blocked.
                  </small>
                </label>
              </>
            )}
          </div>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary">
            <Check size={16} /> Save changes
          </button>
        </form>
      )}
      {tab === "authentication" && (
        <>
          <section className="settings-card">
            <h2>Website cookies</h2>
            <p className="muted">
              Upload a Netscape cookie file for a website you can access.
              Contents stay private.
            </p>
            <form
              className="settings-form"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!file) return;
                setError("");
                const body = new FormData();
                body.append("website", domain);
                body.append("file", file);
                try {
                  await api("/cookies", "POST", body);
                  setDomain("");
                  setFile(null);
                  load();
                  notify("Cookie file saved securely");
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <div className="form-grid">
                <label>
                  Website domain
                  <input
                    placeholder="example.com"
                    value={domain}
                    required
                    onChange={(e) => setDomain(e.target.value)}
                  />
                </label>
                <label>
                  Netscape cookie file
                  <input
                    type="file"
                    accept=".txt"
                    required
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                  />
                </label>
              </div>
              <button className="secondary">
                <Plus size={15} /> Upload or replace
              </button>
            </form>
            {cookies.map((c) => (
              <div className="cookie-row" key={c.id}>
                <ShieldCheck size={18} />
                <div>
                  <strong>{c.website}</strong>
                  <small>Configured · {date(c.updated_at)}</small>
                </div>
                <button
                  className="icon-button"
                  aria-label={"Delete cookies for " + c.website}
                  onClick={async () => {
                    try {
                      await api("/cookies/" + c.id, "DELETE");
                      load();
                    } catch (e) {
                      notify((e as Error).message);
                    }
                  }}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </section>
          <section className="settings-card">
            <h2>Administrator password</h2>
            <form
              className="settings-form"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await api("/auth/password", "POST", {
                    current_password: current,
                    password,
                  });
                  location.reload();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              <div className="form-grid">
                <label>
                  Current password
                  <input
                    type="password"
                    required
                    autoComplete="current-password"
                    value={current}
                    onChange={(e) => setCurrent(e.target.value)}
                  />
                </label>
                <label>
                  New password
                  <input
                    type="password"
                    required
                    minLength={12}
                    maxLength={256}
                    autoComplete="new-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>
              </div>
              <button className="secondary">Change password & sign out</button>
            </form>
          </section>
          <section className="settings-card">
            <h2>Sessions</h2>
            <p className="muted">
              {sessions.length} active session{sessions.length === 1 ? "" : "s"}
              . Sessions expire after seven days.
            </p>
            {sessions.map((s, i) => (
              <div className="cookie-row" key={i}>
                <ShieldCheck size={17} />
                <span>
                  {s.current ? "This session" : "Other session"} ·{" "}
                  {date(s.created_at)}
                </span>
              </div>
            ))}
            <button
              className="secondary"
              onClick={async () => {
                await api("/auth/sessions", "DELETE");
                load();
                notify("Other sessions signed out");
              }}
            >
              Sign out other sessions
            </button>
          </section>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </>
      )}
      {tab === "system" && (
        <>
          <section className="settings-card">
            <h2>
              <Activity size={19} /> System status
            </h2>
            <dl className="system-list">
              <dt>Application</dt>
              <dd>Magpie {system?.magpie}</dd>
              <dt>Download engine</dt>
              <dd>gallery-dl {system?.gallery_dl}</dd>
              <dt>Video engine</dt>
              <dd>yt-dlp {system?.yt_dlp || "…"}</dd>
              <dt>YouTube JavaScript</dt>
              <dd>{system?.video_javascript ? "Sandboxed Node runtime" : "Unavailable"}</dd>
              <dt>Video processing</dt>
              <dd>{system?.ffmpeg ? "FFmpeg & FFprobe · local files only" : "Unavailable"}</dd>
              <dt>Filesystem sandbox</dt>
              <dd>{system?.landlock_abi ? `Landlock ABI ${system.landlock_abi}` : "Unavailable — downloads blocked"}</dd>
              <dt>Database health</dt>
              <dd className="healthy">{system?.health}</dd>
              <dt>Queue scheduler</dt>
              <dd>{system?.queue_running ? "Running" : "Stopped"}</dd>
              <dt>Active workers</dt>
              <dd>{system?.active_workers}</dd>
            </dl>
            <button className="secondary" onClick={load}>
              <RefreshCw size={14} /> Refresh status
            </button>
          </section>
          <section className="settings-card">
            <h2>Recent errors & application logs</h2>
            <p className="muted">{system?.logs}</p>
            {system?.recent_errors?.length ? (
              system.recent_errors.map((e: any) => (
                <div className="error-row" key={e.id}>
                  <strong>{e.website}</strong>
                  <p>{e.error}</p>
                  <small>{date(e.completed_at)}</small>
                </div>
              ))
            ) : (
              <p className="healthy">All quiet. No recent errors.</p>
            )}
            <a
              className="text-button"
              href="/api/openapi.json"
              target="_blank"
              rel="noreferrer"
            >
              REST API schema <ExternalLink size={14} />
            </a>
          </section>
        </>
      )}
    </>
  );
}
