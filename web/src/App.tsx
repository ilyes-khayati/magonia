import { useEffect, useMemo, useState } from "react";
import {
  createArea,
  createWorkspace,
  deleteArea,
  listWorkspaces,
  openWorkspace,
  renameArea,
  type Area,
  type WorkspaceSummary,
} from "./api";
import { readAreaFile } from "./areaFiles";
import MapView, { type Target, type Tool } from "./components/MapView";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import { applyTheme, areaColour, initialTheme, type Theme } from "./theme";

type Message = { text: string; error?: boolean } | null;

const LAST_WORKSPACE = "magonia-workspace";

function remember(id: number) {
  try {
    localStorage.setItem(LAST_WORKSPACE, String(id));
  } catch {
    // not remembered; the first workspace opens next time
  }
}

function remembered(): number | null {
  try {
    return Number(localStorage.getItem(LAST_WORKSPACE)) || null;
  } catch {
    return null;
  }
}

// The box around some geometries, for fitting the map to them
function bounds(geometries: GeoJSON.Geometry[]): [[number, number], [number, number]] | null {
  const points = geometries.flatMap((g) =>
    g.type === "Polygon" ? g.coordinates.flat() : g.type === "MultiPolygon" ? g.coordinates.flat(2) : [],
  );
  if (!points.length) return null;
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [
    [Math.min(...xs), Math.min(...ys)],
    [Math.max(...xs), Math.max(...ys)],
  ];
}

export default function App() {
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [workspaceId, setWorkspaceId] = useState<number | null>(null);
  const [areas, setAreas] = useState<Area[]>([]);
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [tool, setTool] = useState<Tool>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => applyTheme(theme), [theme]);

  const fail = (error: unknown) =>
    setMessage({ text: error instanceof Error ? error.message : String(error), error: true });

  async function open(id: number) {
    const workspace = await openWorkspace(id);
    setWorkspaceId(id);
    setAreas(workspace.areas);
    setHidden(new Set());
    remember(id);
    const box = bounds(workspace.areas.map((a) => a.geometry));
    if (box) setTarget({ key: Date.now(), bounds: box });
  }

  useEffect(() => {
    (async () => {
      let found = await listWorkspaces();
      if (!found.length) found = [await createWorkspace("My workspace")];
      setWorkspaces(found);
      const last = remembered();
      await open(found.some((w) => w.id === last) ? last! : found[0].id);
    })().catch(() =>
      setMessage({ text: "Could not reach the Magonia API. Is it running?", error: true }),
    );
  }, []);

  async function newWorkspace() {
    try {
      const created = await createWorkspace(`Workspace ${workspaces.length + 1}`);
      setWorkspaces([created, ...workspaces]);
      await open(created.id);
    } catch (error) {
      fail(error);
    }
  }

  function freeName(base: string, taken: string[]) {
    if (!taken.includes(base)) return base;
    let n = 2;
    while (taken.includes(`${base} ${n}`)) n += 1;
    return `${base} ${n}`;
  }

  async function addArea(geometry: GeoJSON.Geometry, wanted?: string, existing = areas) {
    const name = freeName(wanted ?? `Area ${existing.length + 1}`, existing.map((a) => a.name));
    const area = await createArea(workspaceId!, name, geometry);
    return [...existing, area];
  }

  async function drawn(geometry: GeoJSON.Polygon) {
    setTool(null);
    try {
      setAreas(await addArea(geometry));
      setMessage(null);
    } catch (error) {
      fail(error);
    }
  }

  async function upload(file: File) {
    try {
      const shapes = await readAreaFile(file);
      let next = areas;
      for (const shape of shapes) next = await addArea(shape.geometry, shape.name, next);
      setAreas(next);
      const box = bounds(shapes.map((s) => s.geometry));
      if (box) setTarget({ key: Date.now(), bounds: box });
      setMessage({ text: `Added ${shapes.length} ${shapes.length === 1 ? "area" : "areas"} from ${file.name}.` });
    } catch (error) {
      fail(error);
    }
  }

  async function rename(area: Area, name: string) {
    try {
      const renamed = await renameArea(area.id, name);
      setAreas(areas.map((a) => (a.id === area.id ? renamed : a)));
    } catch (error) {
      fail(error);
    }
  }

  async function remove(area: Area) {
    try {
      await deleteArea(area.id);
      setAreas(areas.filter((a) => a.id !== area.id));
    } catch (error) {
      fail(error);
    }
  }

  function toggle(area: Area) {
    const next = new Set(hidden);
    if (next.has(area.id)) next.delete(area.id);
    else next.add(area.id);
    setHidden(next);
  }

  const colours = useMemo(
    () => new Map(areas.map((area, index) => [area.id, areaColour(theme, index)])),
    [areas, theme],
  );
  const shown = areas.filter((area) => !hidden.has(area.id));

  const hint =
    tool === "polygon"
      ? "Click to place points. Click the first point to close the area."
      : tool === "rectangle"
        ? "Click one corner, then the opposite corner."
        : null;

  return (
    <div className="workbench">
      <Sidebar
        theme={theme}
        onTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        workspaces={workspaces}
        workspaceId={workspaceId}
        onOpen={(id) => open(id).catch(fail)}
        onNew={newWorkspace}
      />

      <main className="map-area" aria-label="Map">
        <MapView
          areas={shown.map((area) => ({ id: area.id, geometry: area.geometry, colour: colours.get(area.id)! }))}
          tool={tool}
          target={target}
          onDrawn={drawn}
        />
        <Toolbar
          tool={tool}
          onTool={setTool}
          onUpload={upload}
          onGo={(center) => setTarget({ key: Date.now(), center })}
          areas={areas}
          colours={colours}
          hidden={hidden}
          onToggle={toggle}
          onRename={rename}
          onDelete={remove}
        />
        {(hint || message) && (
          <p
            className={`floating message${message?.error && !hint ? " error" : ""}`}
            role={message?.error ? "alert" : "status"}
          >
            {hint ?? message?.text}
          </p>
        )}
      </main>

      <aside className="results" aria-label="Results">
        <h2 style={{ margin: 0, fontSize: 15 }}>Results</h2>
        <p className="placeholder">
          {areas.length
            ? "Choose variables on the left to see them here."
            : "Draw or upload an area to begin."}
        </p>
      </aside>
    </div>
  );
}
