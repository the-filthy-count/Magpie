import { useEffect, useState } from "react";
import { Clipboard, KeyRound, Trash2, X } from "lucide-react";
import { api } from "../services/api";
type Token = { id:string; name:string; created_at:string; expires_at:number | null };
export default function ApiSettings({notify}:{notify:(message:string)=>void}) {
  const [tokens,setTokens] = useState<Token[]>([]), [name,setName] = useState(""), [days,setDays] = useState(90), [neverExpires,setNeverExpires] = useState(false), [secret,setSecret] = useState(""), [busy,setBusy] = useState(false), [error,setError] = useState("");
  const load = () => api<Token[]>("/tokens").then(setTokens);
  useEffect(() => { load().catch(e=>setError(e.message)); },[]);
  return <>
    <section className="settings-card">
      <h2><KeyRound size={20} /> App connections</h2>
      <p>Give each app its own API token. Apps can submit galleries, read destinations and download progress, and cancel or retry jobs. Tokens can view and control all instance downloads. They cannot change settings, manage cookies or delete history. Changing the administrator password revokes all tokens.</p>
      <form className="settings-form" onSubmit={async e=>{
        e.preventDefault(); setBusy(true); setError(""); setSecret("");
        try { const data = await api<Token & {token:string}>("/tokens","POST",{name,expires_days:neverExpires ? null : days}); setSecret(data.token); setName(""); await load(); }
        catch(e) { setError((e as Error).message); } finally { setBusy(false); }
      }}>
        <div className="form-grid"><label>App name<input required maxLength={60} value={name} onChange={e=>setName(e.target.value)} placeholder="My gallery app" /></label><label>Expires in (days)<input type="number" disabled={neverExpires} min={1} max={365} required={!neverExpires} value={days} onChange={e=>setDays(Number(e.target.value))} /></label></div>
        <label className="never-expire-option"><input type="checkbox" checked={neverExpires} onChange={e=>setNeverExpires(e.target.checked)} /> Never expires</label>
        <button className="primary" disabled={busy || !name.trim()}><KeyRound size={17} /> Create token</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {secret && <div className="issued-token"><p>Copy this token now. It is shown only once. Treat it like a password.</p><input aria-label="New API token" value={secret} readOnly autoComplete="off" spellCheck={false} /><div className="button-row"><button type="button" className="icon-button" title="Copy API token" aria-label="Copy API token" onClick={async()=>{try {await navigator.clipboard.writeText(secret); notify("API token copied");}catch {setError("Select and copy the token manually.");}}}><Clipboard size={18}/></button><button type="button" className="icon-button" title="Hide API token" aria-label="Hide API token" onClick={()=>setSecret("")}><X size={18}/></button></div></div>}
      <div className="api-token-list">{tokens.map(token=><div className="cookie-row" key={token.id}><KeyRound size={18}/><div><strong>{token.name}</strong><small>{token.expires_at === null ? "Never expires" : `Expires ${new Date(token.expires_at*1000).toLocaleString()}${token.expires_at*1000 < Date.now() ? " · Expired" : ""}`}</small></div><button className="icon-button" title={"Revoke " + token.name} aria-label={"Revoke " + token.name} onClick={async()=>{try {await api("/tokens/"+token.id,"DELETE");setSecret("");await load();notify("API token revoked");}catch(e){setError((e as Error).message);}}}><Trash2 size={18}/></button></div>)}{!tokens.length && <p>No API tokens yet.</p>}</div>
    </section>
    <section className="settings-card api-guide"><h2>Connect an app</h2><p>Base URL: <code>{window.location.origin}/api</code>. Send <code>Authorization: Bearer YOUR_TOKEN</code> with every request. Use HTTPS through your reverse proxy or a trusted private network.</p>
      <ol><li><code>GET /api/destinations</code> returns destination labels and IDs.</li><li><code>POST /api/downloads</code> with the JSON below queues a gallery by destination label and returns its job ID.</li><li><code>GET /api/downloads/&#123;id&#125;</code> returns status and progress. Poll once per second, or stream <code>GET /api/events</code> with the same Authorization header.</li></ol>
      <pre>{JSON.stringify({url:"https://example.com/gallery",category:"Pictures"},null,2)}</pre>
      <p>Send <code>category</code> with a destination label (case-insensitive), or <code>destination_id</code>, but not both. Unknown labels return 404; duplicate labels return 409. Labels select configured destinations, never arbitrary paths.</p>
      <p>Optional filename labels: send <code>custom_fields</code> as a named object of text values, plus <code>filename_position</code> set to <code>start</code> or <code>end</code>. Values are joined in the order supplied; end labels appear before the extension. Values are retained in history and API responses.</p>
      <p>Current file percentage: <code>file_progress_percent</code>. Album percentage: <code>album_progress_percent</code>. These range from 0–100, or null when unknown. File progress uses bytes; album progress counts downloaded and skipped files. Current file: <code>current_filename</code>, <code>file_bytes</code>, <code>file_total</code>, <code>speed</code>. Gallery: <code>files</code>, <code>skipped</code>, <code>total_files</code>. Totals are null when unknown; Bunkr album totals are supported. Overall progress is (files + skipped) / total_files.</p>
      <p>Live events: <code>update</code> contains a <code>downloads</code> array with the latest 200 jobs and their progress; <code>expired</code> closes the connection when the token expires or is revoked. Fetch any older job by ID. Browser EventSource cannot attach Bearer headers; use a streaming HTTP client or fetch.</p>
      <p><code>POST /api/downloads/&#123;id&#125;/cancel</code> and <code>POST /api/downloads/&#123;id&#125;/retry</code> control a job. Authenticated API schema: <code>GET /api/openapi.json</code>. Browser cross-origin access is restricted; connect from your app’s server.</p>
    </section>
  </>;
}
