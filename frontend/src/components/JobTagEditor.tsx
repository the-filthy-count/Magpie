import { useEffect, useRef, useState } from 'react';
import { Info, X, Check, LoaderCircle } from 'lucide-react';
import { api, Job } from '../services/api';
import HelpTooltip from './HelpTooltip';
export default function JobTagEditor({job,onClose,onSaved}:{job:Job;onClose:()=>void;onSaved:()=>void}) {
 const dialog=useRef<HTMLDialogElement>(null);
 const [tag,setTag]=useState(job.custom_fields?.tag||'');
 const [position,setPosition]=useState<'start'|'end'>(job.filename_position||'start');
 const [busy,setBusy]=useState(false),[error,setError]=useState('');
 useEffect(()=>{dialog.current?.showModal();},[]);
 return <dialog ref={dialog} className="folder-dialog tag-dialog" aria-labelledby={`tag-title-${job.id}`} onCancel={e=>{e.preventDefault();if(!busy)onClose();}}>
  <div className="folder-dialog-heading"><h2 id={`tag-title-${job.id}`}>Edit filename tag</h2><HelpTooltip label="How live tag changes work" icon={<Info size={17}/>}>Temporary filenames stay unchanged during transfer. With In Progress storage, changes apply to the whole job when published. In immediate-save mode, changes apply to the current and remaining files; files already saved keep their names. Other fields supplied through the API are preserved.</HelpTooltip><button type="button" className="icon-button" aria-label="Close tag editor" disabled={busy} onClick={onClose}><X size={17}/></button></div>
  <form onSubmit={async e=>{
   e.preventDefault();if(busy)return;setBusy(true);setError('');
   const fields={...(job.custom_fields||{})};if(tag.trim())fields.tag=tag.trim();else delete fields.tag;
   try {await api(`/downloads/${job.id}`,'PATCH',{custom_fields:fields,filename_position:position});onSaved();onClose();}
   catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }}>
   <label htmlFor={`job-tag-${job.id}`}>Tag (optional)</label><input id={`job-tag-${job.id}`} value={tag} onChange={e=>setTag(e.target.value)} maxLength={100} disabled={busy} placeholder="Add a filename tag…" autoComplete="off"/>
   <label htmlFor={`job-tag-position-${job.id}`}>Position</label><select id={`job-tag-position-${job.id}`} value={position} onChange={e=>setPosition(e.target.value as 'start'|'end')} disabled={busy}><option value="start">Prefix</option><option value="end">Suffix</option></select>
   {error&&<p className="form-error" role="alert">{error}</p>}
   <div className="button-row"><button className="primary" disabled={busy}>{busy?<LoaderCircle className="spin" size={17}/>:<Check size={17}/>}Save tag</button><button type="button" className="secondary" onClick={onClose} disabled={busy}>Cancel</button></div>
  </form>
 </dialog>;
}
