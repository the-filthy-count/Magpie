import DestinationPicker from "./DestinationPicker";
import { useState, useEffect } from "react";
import { ArrowDownToLine, ArrowUpRight, Folder, LoaderCircle, ShieldCheck, Link2, Clipboard } from "lucide-react";
import { api, Destination } from "../services/api";
export default function DownloadForm({
  destinations,
  onCreated,
  onManage,
}: {
  destinations: Destination[];
  onCreated: () => void;
  onManage: () => void;
}) {
  const [url, setUrl] = useState(""),
    [destination, setDestination] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (!destinations.some((d) => d.id === destination))
      setDestination(
        destinations.find((d) => d.is_default)?.id || destinations[0]?.id || "",
      );
  }, [destinations, destination]);
  return (
    <section className="download-panel">
      <div className="panel-top">
        <span>
          <span className="accent-icon">
            <Link2 size={17} />
          </span>{" "}
          A new find
        </span>
        <span>PASTE. PICK. PLUCK.</span>
      </div>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await api("/downloads", "POST", {
              url,
              destination_id: destination,
            });
            setUrl("");
            onCreated();
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="url-label" htmlFor="download-url">
          What caught your eye?
        </label>
        <div className="url-control">
          <Link2 size={21} />
          <input
            id="download-url"
            type="url"
            placeholder="Paste a link to an image, gallery, or profile…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            autoComplete="off"
          />
          <button
            className="paste-button icon-button" title="Paste URL" aria-label="Paste URL"
            type="button"
            onClick={async () => {
              try {
                setUrl(await navigator.clipboard.readText());
              } catch {
                setError(
                  "Use Ctrl+V or your device’s paste action in the URL field.",
                );
              }
            }}
          >
            <Clipboard size={18} />
          </button>
        </div>
        <div className="download-controls">
          <DestinationPicker destinations={destinations} value={destination} onChange={setDestination} />
          <span className="selected-path">
            {destinations.find((d) => d.id === destination)?.path || (
              <button type="button" className="text-button" onClick={onManage}>
                Add your first destination <ArrowUpRight size={13} />
              </button>
            )}
          </span>
          <button
            className="primary pluck"
            disabled={busy || !destination || !url}
          >
            {busy ? (
              <LoaderCircle className="spin" size={18} />
            ) : (
              <ArrowDownToLine size={18} />
            )}{" "}
            Pluck
          </button>
        </div>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
      </form>
      <div className="panel-note">
        <ShieldCheck size={13} /> Images, galleries, videos & more. Supported by
        gallery-dl. <span>Your files stay on your NAS.</span>
      </div>
    </section>
  );
}
