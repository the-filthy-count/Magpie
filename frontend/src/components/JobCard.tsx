import { useState } from "react";
import { ArrowDownToLine, Check, ChevronRight, Clock3, Folder, LoaderCircle, RefreshCw, Trash2, X, Link2 } from "lucide-react";
import { bytes, date, Job, Destination } from "../services/api";
const active = (j: Job) => ["queued", "downloading"].includes(j.status);
export default function JobCard({
  job: j,
  action,
}: {
  job: Job;
  action: (p: string, m?: string) => Promise<void>;
}) {
  const [details, setDetails] = useState(false);
  const pct =
    j.file_total && j.file_bytes != null
      ? Math.min(100, (j.file_bytes / j.file_total) * 100)
      : null;
  const handled = j.files + j.skipped;
  const albumPct = j.total_files && j.total_files >= handled
    ? (handled / j.total_files) * 100 : null;
  return (
    <article className={"job-card " + j.status}>
      <div className={"site-icon " + (j.status === "completed" ? "done" : "")}>
        {j.status === "downloading" ? (
          <ArrowDownToLine size={21} />
        ) : j.status === "completed" ? (
          <Check size={21} />
        ) : j.status === "queued" ? (
          <Clock3 size={21} />
        ) : (
          <Link2 size={21} />
        )}
      </div>
      <div className="job-body">
        <div className="job-top">
          <strong>{j.website}</strong>
          <span className={"status-pill " + j.status}>
            {j.status === "downloading" && (
              <LoaderCircle className="spin" size={11} />
            )}{" "}
            {j.status.charAt(0).toUpperCase() + j.status.slice(1)}
          </span>
        </div>
        <div className="job-url" title={j.url}>
          {j.url}
        </div>
        <div className="job-meta">
          <span>
            <Folder size={12} />
            {j.destination_name}
          </span>
          <span>
            {j.files} {j.files === 1 ? "file" : "files"}
            {j.skipped ? ` · ${j.skipped} skipped` : ""}
          </span>
          <span>
            {bytes(j.bytes)}
            {j.speed != null ? " · " + bytes(j.speed) + "/s" : ""}
          </span>
          {!active(j) && (
            <span className="job-time">{date(j.completed_at)}</span>
          )}
        </div>
        {j.status === "downloading" && (
          <>
            <div
              className={"progress " + (pct === null ? "indeterminate" : "")}
            >
              {pct !== null ? (
                <progress
                  max={100}
                  value={pct}
                  aria-label="Current file progress"
                />
              ) : (
                <div />
              )}
            </div>
            <small className="current-file">
              {j.current_filename || "Finding media…"}
              {pct !== null && <span>Current file · {pct.toFixed(0)}%</span>}
            </small>
            <div className={"progress album-progress " + (albumPct === null ? "indeterminate" : "")}>
              {albumPct !== null ? <progress max={100} value={albumPct} aria-label="Album progress" /> : <div />}
            </div>
            <small className="current-file album-caption">
              <span>{albumPct !== null ? `Album · ${handled} of ${j.total_files} files` : `Overall · ${handled} files handled · total unknown`}{j.skipped ? ` · ${j.skipped} skipped` : ""}</span>
              {albumPct !== null && <span>{albumPct.toFixed(0)}%</span>}
            </small>
          </>
        )}
      </div>
      <div className="job-actions">
        {active(j) ? (
          <button
            title="Cancel download"
            aria-label="Cancel download"
            className="icon-button"
            onClick={() => action("/downloads/" + j.id + "/cancel")}
          >
            <X size={16} />
          </button>
        ) : ["failed", "cancelled", "interrupted"].includes(j.status) ? (
          <button
            className="icon-button"
            title="Retry download"
            aria-label="Retry download"
            onClick={() => action("/downloads/" + j.id + "/retry")}
          >
            <RefreshCw size={16} />
          </button>
        ) : null}
        <button
          className="icon-button"
          title="View details"
          aria-label="View details"
          onClick={() => setDetails(!details)}
        >
          <ChevronRight size={17} className={details ? "rotated" : ""} />
        </button>
        {!active(j) && (
          <button
            className="icon-button"
            title="Remove from history"
            aria-label="Remove from history"
            onClick={() => action("/downloads/" + j.id, "DELETE")}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
      {details && (
        <div className="job-details">
          <dl>
            <dt>Original URL</dt>
            <dd>{j.url}</dd>
            <dt>Destination</dt>
            <dd>{j.destination_path}</dd>
            <dt>Queued</dt>
            <dd>{date(j.created_at)}</dd>
            <dt>Started</dt>
            <dd>{date(j.started_at)}</dd>
            <dt>Completed</dt>
            <dd>{date(j.completed_at)}</dd>
            <dt>Attempts</dt>
            <dd>{j.attempts}</dd>
          </dl>
          {j.error && <p className="form-error">{j.error}</p>}
        </div>
      )}
    </article>
  );
}
