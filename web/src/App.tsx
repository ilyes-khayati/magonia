import { useEffect, useMemo, useRef, useState } from "react";
import {
  createArea,
  createWorkspace,
  deleteArea,
  earthEngineStatus,
  fetchCatalogue,
  listWorkspaces,
  openWorkspace,
  renameArea,
  updateWorkspace,
  type Area,
  type EarthEngineStatus,
  type Variable,
  type VariableKey,
  type WorkspaceSummary,
} from "./api";
import { readAreaFile } from "./areaFiles";
import DataPanel from "./components/DataPanel";
import EarthEngineSetup from "./components/EarthEngineSetup";
import MapView, { type Target, type Tool } from "./components/MapView";
import Results from "./components/Results";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import { DEFAULTS, readSettings, seriesKey, seriesOptions, type Settings } from "./settings";
import { applyTheme, areaColour, initialTheme, type Theme } from "./theme";
import { useSeries } from "./useSeries";

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
  const [catalogue, setCatalogue] = useState<Variable[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [wide, setWide] = useState(false);
  const [earthEngine, setEarthEngine] = useState<EarthEngineStatus | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [focus, setFocus] = useState(false);
  const saving = useRef<number | undefined>(undefined);

  useEffect(() => applyTheme(theme), [theme]);

  // Notices fade after a few seconds; errors stay until the next action
  useEffect(() => {
    if (!message || message.error) return;
    const timer = window.setTimeout(() => setMessage(null), 4000);
    return () => window.clearTimeout(timer);
  }, [message]);

  const fail = (error: unknown) =>
    setMessage({ text: error instanceof Error ? error.message : String(error), error: true });

  async function open(id: number) {
    const workspace = await openWorkspace(id);
    setWorkspaceId(id);
    setAreas(workspace.areas);
    setSettings(readSettings(workspace.settings));
    setHidden(new Set((workspace.settings.hidden as number[] | undefined) ?? []));
    remember(id);
    const box = bounds(workspace.areas.map((a) => a.geometry));
    if (box) setTarget({ key: Date.now(), bounds: box });
  }

  useEffect(() => {
    earthEngineStatus()
      .then((status) => {
        setEarthEngine(status);
        if (!status.connected) setSetupOpen(true);
      })
      .catch(() => undefined); // the message below already says the API is unreachable
    (async () => {
      setCatalogue(await fetchCatalogue());
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

  // Settings and hidden areas are saved with the workspace, half a second after the last change
  function save(nextSettings: Settings, nextHidden: Set<number>) {
    window.clearTimeout(saving.current);
    const id = workspaceId;
    if (id === null) return;
    saving.current = window.setTimeout(() => {
      updateWorkspace(id, { settings: { ...nextSettings, hidden: [...nextHidden] } }).catch(fail);
    }, 500);
  }

  function change(update: Partial<Settings>) {
    const next = { ...settings, ...update };
    setSettings(next);
    save(next, hidden);
  }

  function toggle(area: Area) {
    const next = new Set(hidden);
    if (next.has(area.id)) next.delete(area.id);
    else next.add(area.id);
    setHidden(next);
    save(settings, next);
  }

  const colours = useMemo(
    () => new Map(areas.map((area, index) => [area.id, areaColour(theme, index)])),
    [areas, theme],
  );
  const shown = useMemo(() => areas.filter((area) => !hidden.has(area.id)), [areas, hidden]);

  // One request per visible area and chosen variable
  const requests = useMemo(
    () =>
      // nothing is asked of Earth Engine until it is connected
      workspaceId === null || !earthEngine?.connected
        ? []
        : settings.variables.flatMap((variable) =>
            shown.map((area) => {
              const options = seriesOptions(settings, workspaceId, area.id, variable);
              return { key: seriesKey(options, area.geometry), options };
            }),
          ),
    [settings, workspaceId, shown, earthEngine],
  );
  const results = useSeries(requests);
  const states = requests.map((r) => results.get(r.key));
  const progress = {
    total: requests.length,
    done: states.filter((s) => s?.status === "done").length,
    failed: states.filter((s) => s?.status === "failed").length,
  };
  const entries = (variable: VariableKey) =>
    shown.map((area) => ({
      area,
      colour: colours.get(area.id)!,
      state: results.get(
        seriesKey(seriesOptions(settings, workspaceId!, area.id, variable), area.geometry),
      ),
    }));

  const hint =
    tool === "polygon"
      ? "Click to place points. Click the first point to close the area."
      : tool === "rectangle"
        ? "Click one corner, then the opposite corner."
        : null;

  return (
    <div className={`workbench${wide ? " wide" : ""}${focus ? " focus" : ""}`}>
      <Sidebar
        theme={theme}
        onTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        workspaces={workspaces}
        workspaceId={workspaceId}
        onOpen={(id) => open(id).catch(fail)}
        onNew={newWorkspace}
        earthEngine={earthEngine}
        onEarthEngine={() => setSetupOpen(true)}
      >
        <DataPanel catalogue={catalogue} settings={settings} onChange={change} progress={progress} />
      </Sidebar>

      <main className="map-area" aria-label="Map">
        <MapView
          areas={shown.map((area) => ({ id: area.id, geometry: area.geometry, colour: colours.get(area.id)! }))}
          tool={tool}
          target={target}
          onDrawn={drawn}
          focus={focus}
          onFocus={() => setFocus(!focus)}
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

      <Results
        catalogue={catalogue}
        settings={settings}
        onChange={change}
        areas={shown}
        entries={entries}
        wide={wide}
        onWide={() => setWide(!wide)}
      />

      {setupOpen && earthEngine && (
        <EarthEngineSetup
          status={earthEngine}
          onConnected={(status) => {
            setEarthEngine(status);
            setSetupOpen(false);
          }}
          onClose={earthEngine.connected ? () => setSetupOpen(false) : null}
        />
      )}
    </div>
  );
}
