import { useCallback, useEffect, useRef, useState } from "react";
import { deletedWorkspaces, type WorkspaceSummary } from "../api";
import { PlusIcon } from "./Icons";

type Props = {
  workspaces: WorkspaceSummary[];
  workspaceId: number | null;
  onOpen: (id: number) => void;
  onNew: () => void;
  onRename: (name: string) => void;
  onDelete: (id: number) => void; // to Recently deleted, with an Undo
  onRestore: (id: number) => void;
  onForget: (id: number) => Promise<void>; // deleted forever, from Recently deleted
};

// Closes a floating menu on Escape or a click outside its box
function useDismiss(open: boolean, box: React.RefObject<HTMLDivElement | null>, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) close();
    };
    document.addEventListener("keydown", away);
    document.addEventListener("mousedown", away);
    return () => {
      document.removeEventListener("keydown", away);
      document.removeEventListener("mousedown", away);
    };
  }, [open, box, close]);
}

// "Jendouba orchard" → "JO", "Workspace 4" → "W4"
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "·";
  return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}

// "3 days ago", for when something was deleted
function ago(stamp: string): string {
  const days = Math.floor((Date.now() - Date.parse(stamp)) / 86_400_000);
  return days <= 0 ? "today" : days === 1 ? "yesterday" : `${days} days ago`;
}

// Workspaces deleted in the last 30 days: each can be restored, or deleted for good. Only the
// last is asked twice, since it cannot be undone.
function RecentlyDeleted(props: { onRestore: (id: number) => void; onForget: (id: number) => Promise<void>; onBack: () => void }) {
  const { onRestore, onForget, onBack } = props;
  const [deleted, setDeleted] = useState<WorkspaceSummary[] | null>(null);
  const [confirming, setConfirming] = useState<number | null>(null);
  useEffect(() => {
    deletedWorkspaces()
      .then(setDeleted)
      .catch(() => setDeleted([]));
  }, []);
  return (
    <div className="recently-deleted">
      <button className="row" onClick={onBack}>
        ‹ Recently deleted
      </button>
      <p className="meta">Kept for 30 days, then deleted for good.</p>
      {deleted === null ? (
        <p className="meta">Loading…</p>
      ) : !deleted.length ? (
        <p className="meta">Nothing deleted.</p>
      ) : (
        <ul>
          {deleted.map((w) => (
            <li key={w.id}>
              <span>
                {w.name}
                <span className="meta"> · deleted {ago(w.deleted!)}</span>
              </span>
              <span className="row">
                <button className="link" onClick={() => onRestore(w.id)}>
                  Restore
                </button>
                <button
                  className={confirming === w.id ? "link danger" : "link"}
                  onClick={() =>
                    confirming === w.id
                      ? onForget(w.id).then(() => setDeleted(deleted.filter((x) => x.id !== w.id)))
                      : setConfirming(w.id)
                  }
                  onBlur={() => setConfirming(null)}
                >
                  {confirming === w.id ? "Delete forever?" : "Delete forever"}
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// The workspace is named once, like a file, and switched from its menu; the menu closes on a
// choice, Escape or a click elsewhere
export function WorkspaceMenu(props: Props) {
  const { workspaces, workspaceId, onOpen, onNew, onRename, onDelete, onRestore, onForget } = props;
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [trash, setTrash] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = workspaces.find((w) => w.id === workspaceId);

  const done = useCallback(() => {
    setOpen(false);
    setRenaming(false);
    setTrash(false);
  }, []);
  useDismiss(open, box, done);

  return (
    <div className="workspace-menu" ref={box}>
      <button
        className="workspace-badge"
        aria-expanded={open}
        aria-label={`Workspace: ${current?.name ?? "…"}`}
        title={`${current?.name ?? ""} · switch, rename or add a workspace`}
        onClick={() => (open ? done() : setOpen(true))}
      >
        {initials(current?.name ?? "")}
      </button>
      {open && (
        <div className="floating workspaces rail-pop" role="group" aria-label="Workspaces">
          {!trash && !renaming && <p className="pop-title">Workspaces</p>}
          {trash ? (
            <RecentlyDeleted
              onBack={() => setTrash(false)}
              onForget={onForget}
              onRestore={(id) => {
                onRestore(id);
                done();
              }}
            />
          ) : renaming ? (
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
                onClick={() => {
                  if (workspaceId !== null) onDelete(workspaceId);
                  done();
                }}
              >
                Delete this workspace
              </button>
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
              <hr />
              <button className="meta-button" onClick={() => setTrash(true)}>
                Recently deleted…
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
