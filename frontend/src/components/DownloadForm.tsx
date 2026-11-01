import HelpTooltip from "./HelpTooltip";
import DestinationPicker from "./DestinationPicker";
import { useState, useEffect } from "react";
import { ArrowDownToLine, ArrowUpRight, Folder, LoaderCircle, ShieldCheck, Link2, Clipboard, Info } from "lucide-react";
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
    [tag, setTag] = useState(""),
    [position, setPosition] = useState<"start" | "end">("start"),
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
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            await api("/downloads", "POST", {
              url,
              destination_id: destination,
              ...(tag.trim() ? { custom_fields: { tag: tag.trim() }, filename_position: position } : {}),
            });
            setUrl("");
            setTag("");
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
          <div className="filename-tag-controls">
            <div className="filename-tag-field">
              <div className="filename-tag-label"><label htmlFor="download-tag">Tag <span>(optional)</span></label><HelpTooltip label="About filename tags" icon={<Info size={14}/>}>Add this tag to every filename in the download. Prefix: tag - filename.ext. Suffix: filename - tag.ext. The extension is preserved; unsafe filename characters are sanitised.</HelpTooltip></div>
              <input id="download-tag" value={tag} onChange={e => setTag(e.target.value)} placeholder="Add a filename tag…" maxLength={100} disabled={busy} autoComplete="off" />
            </div>
            <label className="filename-tag-position" htmlFor="download-tag-position">Position<select id="download-tag-position" value={position} onChange={e => setPosition(e.target.value as "start" | "end")} disabled={busy}><option value="start">Prefix</option><option value="end">Suffix</option></select></label>
          </div>
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
