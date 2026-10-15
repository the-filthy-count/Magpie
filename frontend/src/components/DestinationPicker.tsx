import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Folder, Image, Box, Star, Video, Film, Music, Headphones, Camera, Heart } from "lucide-react";
import { Destination } from "../services/api";
const icons: Record<string, typeof Folder> = { folder:Folder, image:Image, box:Box, star:Star, video:Video, film:Film, music:Music, headphones:Headphones, camera:Camera, heart:Heart };
export default function DestinationPicker({ destinations, value, onChange }: { destinations:Destination[]; value:string; onChange:(id:string)=>void }) {
  const [open,setOpen] = useState(false), [index,setIndex] = useState(0);
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const selected = destinations.find(d => d.id === value);
  const Icon = icons[selected?.icon || "folder"] || Folder;
  const available = destinations.map((d,i) => d.writable ? i : -1).filter(i => i >= 0);
  useEffect(() => {
    function outside(e:PointerEvent) { if (!root.current?.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("pointerdown",outside);
    return () => document.removeEventListener("pointerdown",outside);
  },[]);
  useEffect(() => { if (open) document.getElementById(`destination-option-${index}`)?.scrollIntoView({block:"nearest"}); },[index,open]);
  function show() { setIndex(Math.max(0,destinations.findIndex(d => d.id === value && d.writable))); setOpen(true); }
  function choose(i:number) { if (destinations[i]?.writable) { onChange(destinations[i].id); setOpen(false); trigger.current?.focus(); } }
  return <div className="destination-picker" ref={root} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false); }}>
    <button ref={trigger} type="button" className="destination-trigger" role="combobox" aria-label="Save to" aria-haspopup="listbox" aria-expanded={open} aria-controls="destination-options" aria-activedescendant={open ? `destination-option-${index}` : undefined}
      onClick={() => open ? setOpen(false) : show()}
      onKeyDown={e => {
        if (["ArrowDown","ArrowUp","Home","End"].includes(e.key)) {
          e.preventDefault();
          if (!open) { show(); return; }
          const pos = available.indexOf(index);
          const next = e.key === "Home" ? 0 : e.key === "End" ? available.length-1 : (pos + (e.key === "ArrowDown" ? 1 : -1) + available.length) % available.length;
          if (available[next] !== undefined) setIndex(available[next]);
        } else if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
        else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open ? choose(index) : show(); }
        else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
          const match = available.find(i => destinations[i].name.toLowerCase().startsWith(e.key.toLowerCase()));
          if (match !== undefined) { e.preventDefault(); setIndex(match); setOpen(true); }
        }
      }}>
      <Icon size={20} aria-hidden="true" /><span><small>SAVE TO</small><strong>{selected?.name || "Choose a destination"}</strong></span><ChevronDown className={open ? "picker-chevron open" : "picker-chevron"} size={17} aria-hidden="true" />
    </button>
    {open && <div id="destination-options" role="listbox" aria-label="Download destinations" className="destination-options">
      {!destinations.length && <p>No destinations configured.</p>}
      {destinations.map((d,i) => { const ItemIcon = icons[d.icon] || Folder; return <button key={d.id} id={`destination-option-${i}`} type="button" role="option" tabIndex={-1} aria-selected={d.id === value} aria-disabled={!d.writable} className={"destination-option " + (i === index ? "focused" : "")} onPointerDown={e => e.preventDefault()} onMouseEnter={() => { if(d.writable) setIndex(i); }} onClick={() => choose(i)}>
        <ItemIcon size={19} aria-hidden="true" /><span><strong>{d.name}</strong><small>{d.writable ? d.path : "Not writable · check mount permissions"}</small></span>{d.id === value && <Check size={17} aria-hidden="true" />}
      </button>; })}
    </div>}
  </div>;
}
