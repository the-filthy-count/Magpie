import { useState, useEffect } from "react";
import { ListRestart, Search, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { api, date, Job, Destination } from "../services/api";
type Notice = (message: string) => void;
import JobCard from "../components/JobCard";
import Empty from "../components/Empty";
export default function HistoryPage({
  jobs,
  destinations,
  action,
  notify,
  reload,
}: {
  jobs: Job[];
  destinations: Destination[];
  action: (p: string, m?: string) => Promise<void>;
  notify: Notice;
  reload: () => Promise<void>;
}) {
  const [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [site, setSite] = useState(""),
    [dest, setDest] = useState(""),
    [since, setSince] = useState(""),
    [until, setUntil] = useState(""),
    [results, setResults] = useState<Job[]>(jobs),
    [offset, setOffset] = useState(0),
    [hasMore, setHasMore] = useState(false);
  useEffect(() => {
    let valid = true;
    const timer = setTimeout(() => {
      const params = new URLSearchParams({
        q,
        status,
        website: site,
        destination_id: dest,
        since,
        until,
        limit: "100",
        offset: String(offset),
      });
      api<Job[]>("/downloads?" + params)
        .then((rows) => {
          if (valid) {
            setResults(rows);
            setHasMore(rows.length === 100);
          }
        })
        .catch((e) => notify(e.message));
    }, 200);
    return () => {
      valid = false;
      clearTimeout(timer);
    };
  }, [q, status, site, dest, since, until, offset, jobs, notify]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">THE THINGS YOU FOUND</div>
          <h1>
            A little collecting history<span>.</span>
          </h1>
          <p>
            Your downloads, past and present. Removing history keeps your files.
          </p>
        </div>
        <button
          className="secondary danger"
          onClick={async () => {
            if (
              confirm(
                "Clear all finished download history? Your media and archives will be kept.",
              )
            ) {
              await api("/downloads", "DELETE");
              reload();
              notify("History cleared. Your files are safe.");
            }
          }}
        >
          <Trash2 size={15} /> Clear history
        </button>
      </div>
      <div className="filter-bar">
        <div className="search-control">
          <Search size={16} />
          <input
            aria-label="Search by URL"
            placeholder="Search by URL…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
          />
        </div>
        <select
          aria-label="Filter status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All statuses</option>
          {[
            "queued",
            "downloading",
            "completed",
            "failed",
            "cancelled",
            "interrupted",
          ].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </select>
        <input
          aria-label="Website"
          placeholder="Website domain"
          list="websites"
          value={site}
          onChange={(e) => {
            setSite(e.target.value);
            setOffset(0);
          }}
        />
        <datalist id="websites">
          {[...new Set(jobs.map((j) => j.website))].map((x) => (
            <option key={x}>{x}</option>
          ))}
        </datalist>
        <select
          aria-label="Filter destination"
          value={dest}
          onChange={(e) => {
            setDest(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All destinations</option>
          {destinations.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <label>
          From{" "}
          <input
            type="date"
            value={since}
            onChange={(e) => {
              setSince(e.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          To{" "}
          <input
            type="date"
            value={until}
            onChange={(e) => {
              setUntil(e.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>
      <div className="section-heading">
        <h2>Downloads</h2>
        <span className="muted">{results.length} on this page</span>
      </div>
      <div className="job-list">
        {results.length ? (
          results.map((j) => <JobCard key={j.id} job={j} action={action} />)
        ) : (
          <Empty
            icon={<ListRestart />}
            title="Nothing here just yet"
            text="Try another filter, or pluck something new."
          />
        )}
      </div>
      <div className="pagination">
        <button
          className="icon-button" title="Previous page" aria-label="Previous page"
          disabled={!offset}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          <ChevronLeft size={18} />
        </button>
        <span>Page {offset / 100 + 1}</span>
        <button
          className="icon-button" title="Next page" aria-label="Next page"
          disabled={!hasMore}
          onClick={() => setOffset(offset + 100)}
        >
          <ChevronRight size={18} />
        </button>
      </div>
    </>
  );
}
