import { useEffect, useMemo, useRef, useState } from "react";
import { useMatch, useNavigate } from "react-router";
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
  type Workspace,
  type WorkspaceSummary,
} from "./api";
import { addAnalysis, readAnalyses, variablesOf, type Analysis, type Kind } from "./analyses";
import { readAreaFile } from "./areaFiles";
import AnalysesPage from "./components/AnalysesPage";
import AssistantCard from "./components/AssistantCard";
import ChartsPage from "./components/ChartsPage";
import DataPanel from "./components/DataPanel";
import EarthEngineSetup from "./components/EarthEngineSetup";
import { CloseIcon, ExpandIcon } from "./components/Icons";
import MapView, { type Target, type Tool } from "./components/MapView";
import Rail from "./components/Rail";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import { PAGES, isPage, pagePath } from "./pages";
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
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [tool, setTool] = useState<Tool>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const [catalogue, setCatalogue] = useState<Variable[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [docked, setDocked] = useState(false);
  const [earthEngine, setEarthEngine] = useState<EarthEngineStatus | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [focus, setFocus] = useState(false);
  const saving = useRef<number | undefined>(undefined);

  // The address names the workspace and the page: /workspaces/<id>/<page>
  const navigate = useNavigate();
  const match = useMatch("/workspaces/:workspace/:page");
  const page = isPage(match?.params.page) ? match.params.page : "map";
  const routed = Number(match?.params.workspace) || null;

  useEffect(() => applyTheme(theme), [theme]);

  // Notices fade after a few seconds; errors stay until the next action
  useEffect(() => {
    if (!message || message.error) return;
    const timer = window.setTimeout(() => setMessage(null), 4000);
    return () => window.clearTimeout(timer);
  }, [message]);

  const fail = (error: unknown) =>
    setMessage({ text: error instanceof Error ? error.message : String(error), error: true });

  function show(id: number, workspace: Workspace) {
    setWorkspaceId(id);
    setAreas(workspace.areas);
    setSettings(readSettings(workspace.settings));
    setHidden(new Set((workspace.settings.hidden as number[] | undefined) ?? []));
    setAnalyses(readAnalyses(workspace.settings.analyses));
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
    })().catch(() =>
      setMessage({ text: "Could not reach the Magonia API. Is it running?", error: true }),
    );
  }, []);

  // Opening a workspace is a change of address; the address then decides what is open.
  // An unknown workspace in the address becomes the last one used, else the first; an unknown
  // page becomes the map.
  const valid = isPage(match?.params.page);
  useEffect(() => {
    if (!workspaces.length) return;
    const known = (id: number | null) => id !== null && workspaces.some((w) => w.id === id);
    if (!known(routed) || !valid) {
      const last = remembered();
      const id = known(routed) ? routed! : known(last) ? last! : workspaces[0].id;
      navigate(pagePath(id, page), { replace: true });
      return;
    }
    if (routed === workspaceId) return;
    let current = true; // a slower answer for a workspace left meanwhile is ignored
    openWorkspace(routed!)
      .then((workspace) => current && show(routed!, workspace))
      .catch(fail);
    return () => {
      current = false;
    };
  }, [routed, valid, page, workspaces, workspaceId, navigate]);

  async function newWorkspace() {
    try {
      const created = await createWorkspace(`Workspace ${workspaces.length + 1}`);
      setWorkspaces([created, ...workspaces]);
      navigate(pagePath(created.id, page));
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

  // Settings, hidden areas and analyses are saved with the workspace, half a second after the
  // last change
  function save(next: { settings?: Settings; hidden?: Set<number>; analyses?: Analysis[] }) {
    window.clearTimeout(saving.current);
    const id = workspaceId;
    if (id === null) return;
    const saved = {
      ...(next.settings ?? settings),
      hidden: [...(next.hidden ?? hidden)],
      analyses: next.analyses ?? analyses,
    };
    saving.current = window.setTimeout(() => {
      updateWorkspace(id, { settings: saved }).catch(fail);
    }, 500);
  }

  function change(update: Partial<Settings>) {
    const next = { ...settings, ...update };
    setSettings(next);
    save({ settings: next });
  }

  function toggle(area: Area) {
    const next = new Set(hidden);
    if (next.has(area.id)) next.delete(area.id);
    else next.add(area.id);
    setHidden(next);
    save({ hidden: next });
  }

  function changeAnalyses(next: Analysis[]) {
    setAnalyses(next);
    save({ analyses: next });
  }

  const colours = useMemo(
    () => new Map(areas.map((area, index) => [area.id, areaColour(theme, index)])),
    [areas, theme],
  );
  const shown = useMemo(() => areas.filter((area) => !hidden.has(area.id)), [areas, hidden]);

  // One request per visible area and variable, charted or needed by an analysis
  const needed = useMemo(
    () => [...new Set([...settings.variables, ...analyses.flatMap(variablesOf)])],
    [settings.variables, analyses],
  );
  const requests = useMemo(
    () =>
      // nothing is asked of Earth Engine until it is connected
      workspaceId === null || !earthEngine?.connected
        ? []
        : needed.flatMap((variable) =>
            shown.map((area) => {
              const options = seriesOptions(settings, workspaceId, area.id, variable);
              return { key: seriesKey(options, area.geometry), options };
            }),
          ),
    [settings, needed, workspaceId, shown, earthEngine],
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

  const label = PAGES.find((p) => p.key === page)!.label;

  return (
    <div className={`workbench page-${page}${focus && page === "map" ? " focus" : ""}${docked ? " docked" : ""}`}>
      <Rail page={page} workspaceId={workspaceId} docked={docked} onDock={() => setDocked(!docked)} />

      <Sidebar
        theme={theme}
        onTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        workspaces={workspaces}
        workspaceId={workspaceId}
        onOpen={(id) => navigate(pagePath(id, page))}
        onNew={newWorkspace}
        earthEngine={earthEngine}
        onEarthEngine={() => setSetupOpen(true)}
      >
        <DataPanel catalogue={catalogue} settings={settings} onChange={change} progress={progress} />
      </Sidebar>

      <main className="content" aria-label={label}>
        <div className="map-area" hidden={page !== "map"}>
          <MapView
            areas={shown.map((area) => ({ id: area.id, geometry: area.geometry, colour: colours.get(area.id)! }))}
            tool={tool}
            target={target}
            onDrawn={drawn}
            focus={focus}
            onFocus={() => setFocus(!focus)}
            visible={page === "map"}
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
        </div>

        {page === "charts" && (
          <ChartsPage catalogue={catalogue} settings={settings} onChange={change} areas={shown} entries={entries} />
        )}
        {page === "analyses" && (
          <AnalysesPage
            catalogue={catalogue}
            settings={settings}
            areas={shown}
            entries={entries}
            analyses={analyses}
            onAdd={(kind: Kind) => changeAnalyses(addAnalysis(analyses, kind, settings.variables))}
            onChange={(id, update) =>
              changeAnalyses(analyses.map((a) => (a.id === id ? ({ ...a, ...update } as Analysis) : a)))
            }
            onRemove={(id) => changeAnalyses(analyses.filter((a) => a.id !== id))}
          />
        )}

        {(hint || message) && (
          <p
            className={`floating message${message?.error && !hint ? " error" : ""}`}
            role={message?.error ? "alert" : "status"}
          >
            {hint ?? message?.text}
          </p>
        )}
      </main>

      {/* One assistant for every page, so a conversation carries on when the page changes:
          a full page of its own, or a panel beside the others */}
      <aside className="dock" aria-label="Magonia">
        <AssistantCard
          key={workspaceId}
          workspaceId={workspaceId}
          actions={
            page !== "assistant" && (
              <>
                <button
                  className="icon-button"
                  aria-label="Open Magonia on its own page"
                  title="Open Magonia on its own page"
                  onClick={() => workspaceId !== null && navigate(pagePath(workspaceId, "assistant"))}
                >
                  <ExpandIcon size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Close Magonia"
                  title="Close Magonia"
                  onClick={() => setDocked(false)}
                >
                  <CloseIcon size={14} />
                </button>
              </>
            )
          }
        />
      </aside>

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
