import { useEffect, useRef, useState } from "react";
import { Folder, ArrowUp, X } from "lucide-react";
import { api } from "../services/api";
type Listing = { path: string; parent: string | null; folders: string[]; truncated: boolean };
export default function PathPicker({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const request = useRef(0);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      api<Listing>("/folders?suggest=true&path=" + encodeURIComponent(value))
        .then(data => { if (active) setSuggestions(data.folders); })
        .catch(() => { if (active) setSuggestions([]); });
    }, 200);
    return () => { active = false; clearTimeout(timer); };
  }, [value]);
  async function browse(path: string) {
    const id = ++request.current;
    setError(""); setLoading(true);
    try {
      const data = await api<Listing>("/folders?path=" + encodeURIComponent(path));
      if (id === request.current) setListing(data);
    } catch (e) { if (id === request.current) setError((e as Error).message); }
    finally { if (id === request.current) setLoading(false); }
  }
  return <div className="path-picker">
    <div className="path-input-row">
      <input id="destination-path" value={value} onChange={e => onChange(e.target.value)} required disabled={disabled} list="destination-paths" autoComplete="off" placeholder="/downloads/pictures" />
      <datalist id="destination-paths">{suggestions.map(path => <option key={path} value={path} />)}</datalist>
      <button type="button" className="icon-button" title="Browse folders" aria-label="Browse folders" disabled={disabled} onClick={() => { setListing(null); dialog.current?.showModal(); browse(""); }}><Folder size={18} /></button>
    </div>
    <dialog ref={dialog} className="folder-dialog" aria-labelledby="folder-dialog-title">
      <div className="folder-dialog-heading"><h2 id="folder-dialog-title">Choose a folder</h2><button type="button" className="icon-button" aria-label="Close folder picker" onClick={() => dialog.current?.close()}><X size={18} /></button></div>
      <p>Browse your permitted download roots.</p>
      <code>{listing?.path || "Download roots"}</code>
      <div className="folder-list" aria-busy={loading}>
        {loading ? <p role="status">Loading folders…</p> : <>
          {listing?.parent !== null && listing && <button type="button" className="secondary" onClick={() => browse(listing.parent || "")}><ArrowUp size={17} /> Up one level</button>}
          {listing?.folders.map(path => <button type="button" className="secondary folder-entry" key={path} onClick={() => browse(path)}><Folder size={18} /><span>{listing.path ? path.split("/").pop() : path}</span></button>)}
          {listing && !listing.folders.length && <p>No subfolders in this directory.</p>}
          {listing?.truncated && <p>Showing the first 200 folders. Type a path to narrow the suggestions.</p>}
        </>}
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <div className="button-row"><button type="button" className="primary" disabled={loading || !listing?.path || !!error} onClick={() => { if (listing?.path) onChange(listing.path); dialog.current?.close(); }}>Use this folder</button><button type="button" className="secondary" onClick={() => dialog.current?.close()}>Cancel</button></div>
    </dialog>
  </div>;
}
