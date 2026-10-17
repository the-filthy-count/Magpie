import HelpTooltip from "../components/HelpTooltip";
import { useState, useEffect } from "react";
import { Folder, Plus, ShieldCheck, Trash2, Image, Box, Star, Video, Film, Music, Headphones, Camera, Heart, Pencil, Save, X } from "lucide-react";
import { api, Destination } from "../services/api";
type Notice = (message: string) => void;
const icons: Record<string, typeof Folder> = {
  folder: Folder,
  image: Image,
  box: Box,
  star: Star,
  video: Video,
  film: Film,
  music: Music,
  headphones: Headphones,
  camera: Camera,
  heart: Heart,
};
import PathPicker from "../components/PathPicker";
import Empty from "../components/Empty";
export default function Destinations({
  destinations,
  reload,
  notify,
}: {
  destinations: Destination[];
  reload: () => Promise<void>;
  notify: Notice;
}) {
  const [adding, setAdding] = useState(false),
    [name, setName] = useState(""),
    [path, setPath] = useState(""),
    [description, setDescription] = useState(""),
    [icon, setIcon] = useState("folder"),
    [editing, setEditing] = useState(""),
    [error, setError] = useState(""),
    [roots, setRoots] = useState<string[]>([]);
  useEffect(() => {
    api("/roots")
      .then((r) => setRoots(r.roots))
      .catch((e) => notify(e.message));
  }, [notify]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">EVERY FIND HAS A HOME</div>
          <h1>
            Your destinations<span>.</span>
          </h1>
          <p>Choose where your finds land. Files stay yours, always.</p>
        </div>
        <div className="heading-actions">
          <HelpTooltip label="Destination storage information" icon={<ShieldCheck size={19} />}>
            Destinations point to your NAS bind mounts. Removing a destination never deletes downloaded media.
          </HelpTooltip>
        <button
          className="icon-button" title="Add destination" aria-label="Add destination"
          onClick={() => {
            setAdding(!adding);
            setEditing("");
            setName("");
            setPath("");
            setDescription("");
            setError("");
          }}
        >
          <Plus size={18} />
        </button>
        </div>
      </div>
      {adding && (
        <section className="settings-card">
          <h2>{editing ? "Edit destination" : "A new place to keep things"}</h2>
          <form
            className="settings-form"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api(
                  "/destinations" + (editing ? "/" + editing : ""),
                  editing ? "PATCH" : "POST",
                  editing
                    ? { name, description, icon }
                    : { name, path, description, icon },
                );
                setAdding(false);
                reload();
                notify("Destination saved");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <div className="form-grid">
              <label>
                Name
                <input
                  value={name}
                  required
                  maxLength={60}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Pictures"
                />
              </label>
              <label>
                Icon
                <select value={icon} onChange={(e) => setIcon(e.target.value)}>
                  {Object.keys(icons).map((i) => (
                    <option key={i}>{i}</option>
                  ))}
                </select>
              </label>
              <div className="wide">
                <label htmlFor="destination-path">Container path</label>
                <PathPicker value={path} onChange={setPath} disabled={!!editing} />
                <small>
                  Permitted roots: {roots.join(", ")}. Add bind mounts in Docker
                  Compose before adding a destination.
                </small>
              </div>
              <label className="wide">
                Description
                <input
                  value={description}
                  maxLength={250}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="A home for your visual inspiration"
                />
              </label>
            </div>
            {error && <p className="form-error">{error}</p>}
            <div className="button-row">
              <button className="icon-button" title="Save destination" aria-label="Save destination"><Save size={18} /></button>
              <button
                type="button"
                className="icon-button" title="Cancel" aria-label="Cancel"
                onClick={() => setAdding(false)}
              >
                <X size={18} />
              </button>
            </div>
          </form>
        </section>
      )}
      <div className="destinations-grid">
        {destinations.map((d) => {
          const Icon = icons[d.icon] || Folder;
          return (
            <section className="destination-card" key={d.id}>
              <div className="destination-card-top">
                <span className="destination-art">
                  <Icon size={26} />
                </span>
                {d.is_default && <span className="subtle-badge">Default</span>}
              </div>
              <h2>{d.name}</h2>
              <code>{d.path}</code>
              <p>{d.description || "Ready for your next collection."}</p>
              <div className="destination-state">
                <span className={"status-dot " + (!d.writable ? "bad" : "")} />
                {d.writable
                  ? "Accessible & writable"
                  : "Not writable — check mount permissions"}
              </div>
              <div className="button-row">
                {!d.is_default && (
                  <button
                    className="icon-button" title="Set default destination" aria-label="Set default destination"
                    onClick={async () => {
                      try {
                        await api("/destinations/" + d.id, "PATCH", {
                          is_default: true,
                        });
                        reload();
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }}
                  >
                    <Star size={18} />
                  </button>
                )}
                <button
                  className="icon-button" title={"Edit " + d.name} aria-label={"Edit " + d.name}
                  onClick={() => {
                    setEditing(d.id);
                    setName(d.name);
                    setPath(d.path);
                    setDescription(d.description);
                    setIcon(d.icon);
                    setAdding(true);
                    setError("");
                  }}
                >
                  <Pencil size={18} />
                </button>
                <button
                  className="icon-button delete-destination"
                  title="Remove destination"
                  aria-label={"Remove " + d.name}
                  onClick={async () => {
                    if (
                      confirm(
                        "Remove " + d.name + "? Downloaded files will be kept.",
                      )
                    ) {
                      try {
                        await api("/destinations/" + d.id, "DELETE");
                        reload();
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </section>
          );
        })}
      </div>
      {!destinations.length && !adding && (
        <Empty
          icon={<Folder />}
          title="Give your finds a home"
          text="Add a mounted directory to get started."
        />
      )}

    </>
  );
}
