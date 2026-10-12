import type { WorkspaceSummary } from "../api";
import type { Theme } from "../theme";
import { MoonIcon, PlusIcon, SunIcon } from "./Icons";

type Props = {
  theme: Theme;
  onTheme: () => void;
  workspaces: WorkspaceSummary[];
  workspaceId: number | null;
  onOpen: (id: number) => void;
  onNew: () => void;
  children?: React.ReactNode;
};

export default function Sidebar({ theme, onTheme, workspaces, workspaceId, onOpen, onNew, children }: Props) {
  return (
    <aside className="sidebar" aria-label="Data">
      <div className="brand">
        <span>MAGONIA</span>
        <button
          className="icon-button"
          aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
          onClick={onTheme}
        >
          {theme === "light" ? <MoonIcon size={16} /> : <SunIcon size={16} />}
        </button>
      </div>

      <div className="section">
        <label className="label" htmlFor="workspace">
          Workspace
        </label>
        <div className="row">
          <select
            id="workspace"
            className="select"
            style={{ flex: 1 }}
            value={workspaceId ?? ""}
            onChange={(e) => onOpen(Number(e.target.value))}
          >
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
          <button className="icon-button" aria-label="New workspace" title="New workspace" onClick={onNew}>
            <PlusIcon size={16} />
          </button>
        </div>
      </div>

      {children}
    </aside>
  );
}
