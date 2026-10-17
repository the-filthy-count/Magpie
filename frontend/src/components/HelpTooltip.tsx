import { useEffect, useId, useRef, useState, type ReactNode } from "react";
export default function HelpTooltip({ label, children, icon }: { label:string; children:ReactNode; icon:ReactNode }) {
  const [open,setOpen] = useState(false);
  const id=useId(), root=useRef<HTMLSpanElement>(null), button=useRef<HTMLButtonElement>(null);
  useEffect(()=>{
    function outside(e:PointerEvent) { if(!root.current?.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("pointerdown",outside);
    return ()=>document.removeEventListener("pointerdown",outside);
  },[]);
  return <span ref={root} className="help-tooltip" onMouseEnter={()=>setOpen(true)} onMouseLeave={()=>{if(document.activeElement!==button.current)setOpen(false);}}>
    <button ref={button} type="button" className="icon-button" aria-label={label} aria-describedby={open?id:undefined} onFocus={()=>setOpen(true)} onBlur={()=>setOpen(false)} onClick={()=>setOpen(true)} onKeyDown={e=>{if(e.key==="Escape"){setOpen(false);e.stopPropagation();}}}>{icon}</button>
    {open && <span id={id} role="tooltip" className="help-tooltip-content">{children}</span>}
  </span>;
}
