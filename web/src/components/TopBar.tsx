import { useEffect, useRef, useState } from "react";
import type { EarthEngineStatus, WorkspaceSummary } from "../api";
import type { Theme } from "../theme";
import { ChevronIcon, MoonIcon, PlusIcon, SparkIcon, SunIcon } from "./Icons";

type Props = {
  theme: Theme;
  onTheme: () => void;
  workspaces: WorkspaceSummary[];
  workspaceId: number | null;
  onOpen: (id: number) => void;
  onNew: () => void;
  onRename: (name: string) => void;
  earthEngine: EarthEngineStatus | null;
  onEarthEngine: () => void;
  magonia: { open: boolean; onToggle: () => void };
};

// The workspace is named once, like a file, and switched from its menu; the menu closes on a
// choice, Escape or a click elsewhere
function WorkspaceMenu(props: Pick<Props, "workspaces" | "workspaceId" | "onOpen" | "onNew" | "onRename">) {
  const { workspaces, workspaceId, onOpen, onNew, onRename } = props;
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = workspaces.find((w) => w.id === workspaceId);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) {
        setOpen(false);
        setRenaming(false);
      }
    };
    document.addEventListener("keydown", close);
    document.addEventListener("mousedown", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("mousedown", close);
    };
  }, [open]);

  const done = () => {
    setOpen(false);
    setRenaming(false);
  };

  return (
    <div className="workspace-menu" ref={box}>
      <button className="workspace-name" aria-expanded={open} onClick={() => setOpen(!open)} title="Workspaces">
        <span className="meta">Workspace</span>
        <strong>{current?.name ?? "…"}</strong>
        <ChevronIcon size={14} />
      </button>
      {open && (
        <div className="floating workspaces" role="group" aria-label="Workspaces">
          {renaming ? (
            <form
              className="rename"
              onSubmit={(e) => {
                e.preventDefault();
                const name = new FormData(e.currentTarget).get("name")?.toString().trim();
                if (name) onRename(name);
                done();
              }}
            >
              <label className="field">
                Name
                <input className="input" name="name" defaultValue={current?.name} autoFocus />
              </label>
              <button className="primary">Rename</button>
            </form>
          ) : (
            <>
              {workspaces.map((w) => (
                <button
                  key={w.id}
                  aria-current={w.id === workspaceId}
                  onClick={() => {
                    if (w.id !== workspaceId) onOpen(w.id);
                    done();
                  }}
                >
                  {w.name}
                </button>
              ))}
              <hr />
              <button onClick={() => setRenaming(true)}>Rename this workspace…</button>
              <button
                className="row"
                onClick={() => {
                  onNew();
                  done();
                }}
              >
                <PlusIcon size={14} />
                New workspace
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function TopBar(props: Props) {
  const { theme, onTheme, earthEngine, magonia } = props;
  return (
    <header className="topbar">
      <span className="brand-name">MAGONIA</span>
      <WorkspaceMenu {...props} />
      <span style={{ flex: 1 }} />
      <button className="engine-status" onClick={props.onEarthEngine}>
        <span className="dot" data-ok={earthEngine?.connected ?? false} />
        {earthEngine === null
          ? "Checking Earth Engine…"
          : earthEngine.connected
            ? `Earth Engine · ${earthEngine.project}`
            : "Earth Engine not connected"}
      </button>
      <button
        className="icon-button"
        aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
        onClick={onTheme}
      >
        {theme === "light" ? <MoonIcon size={16} /> : <SunIcon size={16} />}
      </button>
      <button
        className="magonia-toggle"
        aria-label="Magonia"
        aria-pressed={magonia.open}
        title={magonia.open ? "Close Magonia" : "Ask Magonia about your data"}
        onClick={magonia.onToggle}
      >
        <SparkIcon size={18} />
      </button>
    </header>
  );
}
