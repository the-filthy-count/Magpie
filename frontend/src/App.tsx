import { useState, useEffect, useCallback } from "react";
import { ArrowDownToLine, ArrowUpRight, Check, CheckCheck, ChevronRight, Folder, ListRestart, LogOut, Menu, Settings2, ShieldCheck, X, Image, Sun, Moon } from "lucide-react";
import { api, setCsrf, bytes, Job, Destination } from "./services/api";

type Notice = (message: string) => void;
const active = (j: Job) => ["queued", "downloading"].includes(j.status);
import Login from "./components/Login";
import DownloadForm from "./components/DownloadForm";
import Stat from "./components/Stat";
import Empty from "./components/Empty";
import JobCard from "./components/JobCard";
import HistoryPage from "./pages/HistoryPage";
import Destinations from "./pages/Destinations";
import SettingsPage from "./pages/SettingsPage";
export { default as JobCard } from "./components/JobCard";
export default function App() {
  const [auth, setAuth] = useState<any>(null),
    [page, setPage] = useState("downloads"),
    [jobs, setJobs] = useState<Job[]>([]),
    [destinations, setDestinations] = useState<Destination[]>([]),
    [settings, setSettings] = useState<any>(null),
    [engine, setEngine] = useState<boolean|null>(null),
    [toast, setToast] = useState(""),
    [error, setError] = useState(""),
    [mobile, setMobile] = useState(false);
  const notify: Notice = useCallback((message) => {
    setToast(message);
    setTimeout(() => setToast(""), 4500);
  }, []);
  const reload = useCallback(async () => {
    try {
      const [j, d] = await Promise.all([
        api<Job[]>("/downloads?limit=500"),
        api<Destination[]>("/destinations"),
      ]);
      setJobs(j);
      setDestinations(d);
    } catch (e) {
      setError(String(e));
    }
  }, []);
  const loadSettings = useCallback(async () => {
    const s = await api("/settings");
    setSettings(s);
    document.documentElement.dataset.theme =
      s.theme === "system"
        ? matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark"
        : s.theme;
  }, []);
  useEffect(() => {
    api("/auth/status")
      .then((a) => {
        setAuth(a);
        setCsrf(a.csrf || "");
      })
      .catch((e) => setError(String(e)));
    const unauthorized = () => setAuth({ authenticated: false });
    window.addEventListener("magpie-unauthorized", unauthorized);
    return () =>
      window.removeEventListener("magpie-unauthorized", unauthorized);
  }, []);
  useEffect(() => {
    if (!auth?.authenticated) return;
    reload();
    loadSettings().catch((e) => setError(String(e)));
    const events = new EventSource("/api/events");
    events.addEventListener("update", reload);
    events.addEventListener("expired", () => setAuth({ authenticated: false }));
    const checkEngine = () => api('/system').then(s => setEngine(s.queue_running && s.landlock_abi > 0)).catch(() => setEngine(false));
    checkEngine();
    const enginePoll = setInterval(checkEngine, 15000);
    const poll = setInterval(reload, 15000);
    return () => {
      events.close();
      clearInterval(poll);
      clearInterval(enginePoll);
    };
  }, [auth, reload, loadSettings]);
  const action = async (path: string, method = "POST") => {
    try {
      await api(path, method);
      await reload();
    } catch (e) {
      notify((e as Error).message);
    }
  };
  if (!auth)
    return (
      <div className="loading">
        <img src="/logo.png" width="64" />
        <p>{error || "Waking up Magpie…"}</p>
      </div>
    );
  if (!auth.authenticated)
    return (
      <Login
        setup={auth.setup_required}
        onLogin={(a) => {
          setCsrf(a.csrf);
          setAuth(a);
        }}
      />
    );
  const working = jobs.filter(active),
    complete = jobs.filter((j) => j.status === "completed");
  return (
    <div className="app-shell">
      <aside className={mobile ? "sidebar open" : "sidebar"}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("downloads");
          }}
        >
          <img src="/logo.png" />
          <span>Magpie</span>
        </a>
        <div className="workspace-label">YOUR LITTLE COLLECTOR</div>
        <nav>
          {[
            ["downloads", "Downloads", ArrowDownToLine],
            ["history", "History", ListRestart],
            ["destinations", "Destinations", Folder],
            ["settings", "Settings", Settings2],
          ].map(([id, label, Icon]: any) => (
            <button
              key={id}
              className={page === id ? "nav-item selected" : "nav-item"}
              onClick={() => {
                setPage(id);
                setMobile(false);
              }}
            >
              <Icon size={19} />
              {label}
              {id === "downloads" && working.length > 0 && (
                <span className="nav-count">{working.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span className="status-dot" />
            Your nest. Your files.<small>Self-hosted & privately yours.</small>
          </div>
          <div className="sidebar-footer">
            <span>
              MAGPIE <small>v1.0.0</small>
            </span>
            <button
              title="Sign out"
              aria-label="Sign out"
              className="icon-button"
              onClick={async () => {
                await api("/auth/logout", "POST");
                setAuth({ authenticated: false });
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Open menu"
            onClick={() => setMobile(!mobile)}
          >
            <Menu />
          </button>
          <span>
            Workspace <ChevronRight size={14} />
            <b>{page.charAt(0).toUpperCase() + page.slice(1)}</b>
          </span>
          <div className="topbar-right">
            <span className="online">
              <span className={engine===false?"status-dot bad":"status-dot"} /> {engine===null?"Checking engine…":engine?"Engine online":"Engine unavailable"}
            </span>
            <button
              className="icon-button"
              aria-label="Toggle theme"
              onClick={async () => {
                try {
                  await api("/settings", "PATCH", {
                    theme: settings?.theme === "light" ? "dark" : "light",
                  });
                  await loadSettings();
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              {settings?.theme === "light" ? (
                <Moon size={17} />
              ) : (
                <Sun size={17} />
              )}
            </button>
            <span className="avatar">M</span>
          </div>
        </header>
        <div className="page-content">
          {page === "downloads" && (
            <>
              <div className="page-heading">
                <div>
                  <h1>
                    Find it. Fetch it. File it<span>.</span>
                  </h1>
                </div>
                <span className="subtle-badge">
                  <ShieldCheck size={14} /> Made for your NAS
                </span>
              </div>
              <DownloadForm
                destinations={destinations}
                onCreated={() => {
                  reload();
                  notify("Added to the queue. Magpie is on it.");
                }}
                onManage={() => setPage("destinations")}
              />
              <div className="stats-grid">
                <Stat
                  label="In the queue"
                  value={working.length}
                  icon={<ArrowDownToLine size={19} />}
                  foot={
                    working.length
                      ? "A little collecting in progress"
                      : "Ready for your next find"
                  }
                />
                <Stat
                  label="Plucked successfully"
                  value={complete.length}
                  icon={<CheckCheck size={19} />}
                  foot="Completed downloads in history"
                />
                <Stat
                  label="Files collected"
                  value={jobs
                    .reduce((sum, j) => sum + j.files, 0)
                    .toLocaleString()}
                  icon={<Image size={19} />}
                  foot={
                    bytes(jobs.reduce((sum, j) => sum + j.bytes, 0)) +
                    " downloaded"
                  }
                />
                <Stat
                  label="Destinations"
                  value={destinations.length}
                  icon={<Folder size={19} />}
                  foot="A place for every good find"
                />
              </div>
              <div className="section-heading">
                <h2>
                  Download queue <span>{working.length}</span>
                </h2>
                <span className="muted">
                  <span className="live-dot" /> Live updates
                </span>
              </div>
              <div className="job-list">
                {working.length ? (
                  working
                    .slice()
                    .reverse()
                    .map((j) => <JobCard key={j.id} job={j} action={action} />)
                ) : (
                  <Empty
                    icon={<ArrowDownToLine />}
                    title="Your queue is all clear"
                    text="Paste a link above. We'll take it from here."
                  />
                )}
              </div>
              <div className="section-heading recent-heading">
                <h2>Recent activity</h2>
                <button
                  className="icon-button" title="View history" aria-label="View history"
                  onClick={() => setPage("history")}
                >
                  <ListRestart size={18} />
                </button>
              </div>
              <div className="job-list">
                {jobs
                  .filter((j) => !active(j))
                  .slice(0, 4)
                  .map((j) => (
                    <JobCard key={j.id} job={j} action={action} />
                  ))}
                {!jobs.some((j) => !active(j)) && (
                  <div className="quiet-empty">
                    Your finds will land here after their journey.
                  </div>
                )}
              </div>
              <footer className="page-footer">
                <span>
                  <img src="/logo.png" /> A little less saving for later. A
                  little more keeping forever.
                </span>
                <span>
                  Powered by gallery-dl <ArrowUpRight size={12} />
                </span>
              </footer>
            </>
          )}
          {page === "history" && (
            <HistoryPage
              jobs={jobs}
              destinations={destinations}
              action={action}
              notify={notify}
              reload={reload}
            />
          )}
          {page === "destinations" && (
            <Destinations
              destinations={destinations}
              reload={reload}
              notify={notify}
            />
          )}
          {page === "settings" && settings && (
            <SettingsPage
              settings={settings}
              refresh={loadSettings}
              destinations={destinations}
              reload={reload}
              notify={notify}
            />
          )}
        </div>
      </main>
      {toast && (
        <div className="toast" role="status">
          <Check size={17} />
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {error && (
        <div className="toast error" role="alert">
          {error}
          <button onClick={() => setError("")}>Dismiss</button>
        </div>
      )}
    </div>
  );
}
