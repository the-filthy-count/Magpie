import { useState } from "react";
import { Info, Plus, Trash2 } from "lucide-react";
import HelpTooltip from "./HelpTooltip";
export default function DownloadPreferences({draft,update}:{draft:any;update:(key:string,value:any)=>void}) {
  const [extensions,setExtensions]=useState((draft.extensions||[]).join(', '));
  const [languages,setLanguages]=useState((draft.subtitle_languages||['en']).join(', '));
  const field=(key:string,label:string,options:[string,string][]) => <label>{label}<select value={draft[key]} onChange={e=>update(key,e.target.value)}>{options.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></label>;
  const rules=draft.site_rules||[];
  const setRule=(index:number,key:string,value:any)=>update('site_rules',rules.map((r:any,i:number)=>i===index?{...r,[key]:value}:r));
  return <details className="download-preferences wide" open>
    <summary>More download options</summary>
    <div className="preference-heading"><h3>Media and video</h3><HelpTooltip label="Video and file filtering information" icon={<Info size={18}/>}>
      Quality, format and subtitle preferences apply to yt-dlp video downloads. MP4 is preferred when offered, without transcoding. Filters use extractor metadata; unknown extensions are excluded when filtering. Gallery title prefixes fall back to native filenames when no gallery title exists.
    </HelpTooltip></div>
    <div className="form-grid">
      {field('video_quality','Maximum video quality',[['best','Best available'],['1080','1080p'],['720','720p'],['480','480p']])}
      {field('video_format','Preferred video format',[['best','Best available'],['mp4','Prefer MP4']])}
      {field('playlist','Video playlists',[['all','Entire playlist'],['single','First / single video only']])}
      {field('media_filter','Files to download',[['all','All supported media'],['images','Images only'],['videos','Videos only'],['extensions','Selected extensions']])}
      {draft.media_filter==='extensions' && <label className="wide">Extensions (comma separated)<input value={extensions} placeholder="jpg, png, webp, mp4" onChange={e=>{setExtensions(e.target.value);update('extensions',e.target.value.split(',').map(x=>x.trim().toLowerCase().replace(/^\./,'')).filter(Boolean));}} /></label>}
      <label>Maximum new files per job<input type="number" min={0} max={100000} value={draft.max_files||0} onChange={e=>update('max_files',Number(e.target.value))}/><small>0 means unlimited. Archived skips do not count.</small></label>
      <label>Maximum file size (MiB)<input type="number" min={0} max={953674} value={(draft.max_file_size||0)/1048576} onChange={e=>update('max_file_size',Math.round(Number(e.target.value)*1048576))}/><small>0 means unlimited. Oversized partial files are not finalised or archived.</small></label>
      {field('subtitles','Video subtitles',[['off','Off'],['manual','Published subtitles'],['automatic','Published and automatic subtitles']])}
      {draft.subtitles!=='off' && <label>Subtitle languages<input value={languages} placeholder="en, en-US" onChange={e=>{setLanguages(e.target.value);update('subtitle_languages',e.target.value.split(',').map(x=>x.trim()).filter(Boolean));}}/><small>Language codes; only available tracks are downloaded.</small></label>}
    </div>
    <div className="preference-heading"><h3>Scheduling and recovery</h3><HelpTooltip label="Scheduling and recovery information" icon={<Info size={18}/>}>The daily window uses the container timezone (TZ). Jobs already running finish normally. Equal start/end means all day. Recovery retries interrupted jobs on startup and uses persistent archives and partial files where supported.</HelpTooltip></div>
    <div className="form-grid">
      <label className="preference-check"><input type="checkbox" checked={!!draft.schedule_enabled} onChange={e=>update('schedule_enabled',e.target.checked)}/>Use daily download hours</label>
      <label className="preference-check"><input type="checkbox" checked={!!draft.resume_interrupted} onChange={e=>update('resume_interrupted',e.target.checked)}/>Automatically retry interrupted jobs after restart</label>
      {draft.schedule_enabled && <><label>Start time<input type="time" required value={draft.schedule_start} onChange={e=>update('schedule_start',e.target.value)}/></label><label>End time<input type="time" required value={draft.schedule_end} onChange={e=>update('schedule_end',e.target.value)}/></label></>}
    </div>
    <details className="site-preferences"><summary>Advanced · website defaults</summary>
      <p>Overrides apply to the hostname and its subdomains; the most specific rule wins. Destination organisation takes priority. Custom organisation uses the shared directory template.</p>
      {rules.map((rule:any,index:number)=><div key={index} className="site-rule"><div className="form-grid">
        <label>Website hostname<input required value={rule.website} placeholder="bunkr.cr" maxLength={253} onChange={e=>setRule(index,'website',e.target.value)}/></label>
        <label>Organisation<select value={rule.organisation||''} onChange={e=>setRule(index,'organisation',e.target.value||null)}><option value="">Use global default</option><option value="organised">Organised</option><option value="flat">Flat</option><option value="flat_gallery">Flat with gallery name</option><option value="custom">Custom</option></select></label>
        <label>Request delay (seconds)<input type="number" min={0} max={120} step="0.1" value={rule.sleep_request??''} placeholder="Use global default" onChange={e=>setRule(index,'sleep_request',e.target.value===''?null:Number(e.target.value))}/></label>
        <label>Retry attempts<input type="number" min={0} max={20} value={rule.retries??''} placeholder="Use global default" onChange={e=>setRule(index,'retries',e.target.value===''?null:Number(e.target.value))}/></label>
        <label>Timeout (seconds)<input type="number" min={5} max={300} value={rule.timeout??''} placeholder="Use global default" onChange={e=>setRule(index,'timeout',e.target.value===''?null:Number(e.target.value))}/></label>
        <label>Rate limit (bytes / second)<input type="number" min={0} max={1000000000} value={rule.rate_limit??''} placeholder="Use global default" onChange={e=>setRule(index,'rate_limit',e.target.value===''?null:Number(e.target.value))}/></label>
        <label className="wide">Filename template override<input value={rule.filename??''} placeholder="Use global default" onChange={e=>setRule(index,'filename',e.target.value||null)}/></label>
      </div><button type="button" className="icon-button" title="Remove website default" aria-label={`Remove website default ${index+1}`} onClick={()=>update('site_rules',rules.filter((_:any,i:number)=>i!==index))}><Trash2 size={18}/></button></div>)}
      <button type="button" className="secondary" disabled={rules.length>=50} onClick={()=>update('site_rules',[...rules,{website:''}])}><Plus size={17}/>Add website default</button>
    </details>
  </details>;
}
