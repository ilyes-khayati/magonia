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
  type Proposal,
  type Variable,
  type VariableKey,
  type Workspace,
  type WorkspaceSummary,
} from "./api";
import { addAnalysis, needsOf, readAnalyses, type Analysis, type Kind, type Models, type Need } from "./analyses";
import { describeDisplay } from "./display";
import { MODEL_NAMES, newExperiment, PAPER, readExperiments, type Experiment } from "./experiments";
import { readAreaFile } from "./areaFiles";
import AnalysesPage from "./components/AnalysesPage";
import AssistantCard from "./components/AssistantCard";
import DataPage from "./components/DataPage";
import DataPanel from "./components/DataPanel";
import EarthEngineSetup from "./components/EarthEngineSetup";
import { CloseIcon, ExpandIcon, ShrinkIcon } from "./components/Icons";
import MapView, { type Target, type Tool } from "./components/MapView";
import ModelPage from "./components/ModelPage";
import Rail from "./components/Rail";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import TopBar from "./components/TopBar";
import { PAGES, isPage, pagePath, type Page } from "./pages";
import { DEFAULTS, readSettings, seriesKey, seriesOptions, variableTitle, type Settings } from "./settings";
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

// Whether Magonia's panel is open, and how wide, are this browser's own conveniences
const PANEL = "magonia-panel";
const PANEL_WIDTH = { min: 320, initial: 420 };

function panelSaved(): { open: boolean; width: number } {
  try {
    const saved = JSON.parse(localStorage.getItem(PANEL) ?? "{}");
    return { open: saved.open === true, width: Number(saved.width) || PANEL_WIDTH.initial };
  } catch {
    return { open: false, width: PANEL_WIDTH.initial };
  }
}

function panelRemember(panel: { open: boolean; width: number }) {
  try {
    localStorage.setItem(PANEL, JSON.stringify(panel));
  } catch {
    // not remembered; the panel starts closed next time
  }
}

const panelClamp = (width: number) =>
  Math.round(Math.min(Math.max(width, PANEL_WIDTH.min), window.innerWidth * 0.7));

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
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [experimentsShown, setExperimentsShown] = useState<number[]>([]);
  const [tool, setTool] = useState<Tool>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const [catalogue, setCatalogue] = useState<Variable[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [panel, setPanel] = useState(panelSaved);
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
  useEffect(() => panelRemember(panel), [panel]);

  const docked = panel.open && page !== "assistant";
  const setDocked = (open: boolean) => setPanel((p) => ({ ...p, open }));

  // Magonia opens full size from its panel, and goes back to the page it came from
  const lastPage = useRef<Page>("map");
  useEffect(() => {
    if (page !== "assistant") lastPage.current = page;
  }, [page]);
  function magoniaSmaller() {
    setDocked(true);
    if (workspaceId !== null) navigate(pagePath(workspaceId, lastPage.current));
  }

  // Magonia's panel is widened by dragging its edge, or with the arrow keys on it
  function resize(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    const move = (m: PointerEvent) =>
      setPanel((p) => ({ ...p, width: panelClamp(window.innerWidth - m.clientX) }));
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
  }

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
    // forecast cards from before the Model page become experiments
    const saved = Array.isArray(workspace.settings.analyses) ? (workspace.settings.analyses as { kind?: string }[]) : [];
    setExperiments(readExperiments(workspace.settings.experiments, saved.filter((a): a is Models => a.kind === "models")));
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

  async function renameWorkspace(name: string) {
    if (workspaceId === null) return;
    try {
      await updateWorkspace(workspaceId, { name });
      setWorkspaces(workspaces.map((w) => (w.id === workspaceId ? { ...w, name } : w)));
    } catch (error) {
      fail(error);
    }
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
  function save(next: { settings?: Settings; hidden?: Set<number>; analyses?: Analysis[]; experiments?: Experiment[] }) {
    window.clearTimeout(saving.current);
    const id = workspaceId;
    if (id === null) return;
    const saved = {
      ...(next.settings ?? settings),
      hidden: [...(next.hidden ?? hidden)],
      analyses: next.analyses ?? analyses,
      experiments: next.experiments ?? experiments,
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

  function changeExperiments(next: Experiment[]) {
    setExperiments(next);
    save({ experiments: next });
  }

  // What Magonia proposed, added because the researcher clicked (AI-07): its card, and the
  // period if one was asked for
  function adopt(p: Proposal) {
    if (workspaceId === null) return;
    const nextSettings = p.period
      ? { ...settings, start: p.period.start ?? settings.start, end: p.period.end ?? settings.end }
      : settings;
    setSettings(nextSettings);
    const visible = areas.filter((a) => !hidden.has(a.id));
    const areaId = (p.area ? areas.find((a) => a.name === p.area)?.id : undefined) ?? visible[0]?.id ?? null;
    if (p.kind === "experiment") {
      const recipe = {
        ...structuredClone(PAPER),
        area: areaId,
        response: p.variable ?? "ndvi",
        drivers: p.drivers ?? PAPER.drivers,
        models: p.models ?? [...MODEL_NAMES],
        test_years: p.test_years ?? 3,
      };
      const e = newExperiment(experiments, areaId, recipe);
      const next = [...experiments, { ...e, name: p.title, ran: structuredClone(recipe) }];
      setExperiments(next);
      save({ settings: nextSettings, experiments: next });
      navigate(pagePath(workspaceId, "model"));
      return;
    }
    const added = addAnalysis(analyses, p.kind, settings.variables);
    const last = added[added.length - 1];
    const v = p.variable ?? "ndvi";
    const shaped: Analysis =
      last.kind === "correlation"
        ? { ...last, response: v, driver: p.driver ?? last.driver }
        : last.kind === "lags"
          ? { ...last, response: v, drivers: p.drivers ?? last.drivers, ...(p.area ? { area: areaId ?? undefined } : {}) }
          : last.kind === "decomposition" || last.kind === "trend"
            ? { ...last, variable: v }
            : last;
    const next = [...added.slice(0, -1), shaped];
    setAnalyses(next);
    save({ settings: nextSettings, analyses: next });
    navigate(pagePath(workspaceId, "analyses"));
  }

  const colours = useMemo(
    () => new Map(areas.map((area, index) => [area.id, areaColour(theme, index)])),
    [areas, theme],
  );
  const shown = useMemo(() => areas.filter((area) => !hidden.has(area.id)), [areas, hidden]);

  // A series as the charts show it, or at the product's own time step for an analysis
  // that needs it (a decomposition)
  const optionsFor = (areaId: number, variable: VariableKey, native = false) => {
    const options = seriesOptions(settings, workspaceId!, areaId, variable);
    return native ? { ...options, resolution: "native" as const } : options;
  };

  // One request per visible area and series, charted or needed by an analysis
  const needed = useMemo(() => {
    const forecast = experiments.flatMap((e) =>
      [e.recipe, e.ran].flatMap((r) => (r ? [r.response, ...r.drivers] : [])).map((variable) => ({ variable, native: false })),
    );
    const all: Need[] = [
      ...settings.variables.map((variable) => ({ variable, native: false })),
      ...analyses.flatMap(needsOf),
      ...forecast,
    ];
    return all.filter((n, i) => all.findIndex((m) => m.variable === n.variable && m.native === n.native) === i);
  }, [settings.variables, analyses, experiments]);
  const requests = useMemo(
    () =>
      // nothing is asked of Earth Engine until it is connected
      workspaceId === null || !earthEngine?.connected
        ? []
        : needed.flatMap(({ variable, native }) =>
            shown.map((area) => {
              const options = seriesOptions(settings, workspaceId, area.id, variable);
              const wanted = native ? { ...options, resolution: "native" as const } : options;
              return { key: seriesKey(wanted, area.geometry), options: wanted };
            }),
          ),
    [settings, needed, workspaceId, shown, earthEngine],
  );
  const results = useSeries(requests);

  // What is open, sent with each question so that Magonia can discuss it
  const view = useMemo(
    () => ({
      page,
      charts: settings.variables,
      resolution: settings.resolution,
      // experiments are read as forecasts of the area they ran on
      analyses: [
        ...analyses,
        // on the Model page, only the experiments on screen, so that runs are not mixed up
        ...experiments
          .filter((e) => page !== "model" || experimentsShown.includes(e.id))
          .flatMap((e) => (e.ran ? [{ kind: "models", name: e.name, ...e.ran, area: e.ran.area ?? shown[0]?.id ?? null }] : [])),
      ],
      series: requests.map((r) => r.options),
      display: describeDisplay(settings.display),
    }),
    [page, settings.variables, settings.resolution, settings.display, analyses, experiments, experimentsShown, shown, requests],
  );
  const states = requests.map((r) => results.get(r.key));
  const progress = {
    total: requests.length,
    done: states.filter((s) => s?.status === "done").length,
    failed: states.filter((s) => s?.status === "failed").length,
  };
  const entries = (variable: VariableKey, native = false) =>
    shown.map((area) => ({
      area,
      colour: colours.get(area.id)!,
      state: results.get(seriesKey(optionsFor(area.id, variable, native), area.geometry)),
    }));

  const hint =
    tool === "polygon"
      ? "Click to place points. Click the first point to close the area."
      : tool === "rectangle"
        ? "Click one corner, then the opposite corner."
        : null;

  const label = PAGES.find((p) => p.key === page)!.label;

  return (
    <div
      className={`workbench page-${page}${focus && page === "map" ? " focus" : ""}${docked ? " docked" : ""}`}
      style={{ "--panel-width": `${panel.width}px` } as React.CSSProperties}
    >
      <TopBar
        theme={theme}
        onTheme={() => setTheme(theme === "light" ? "dark" : "light")}
        workspaces={workspaces}
        workspaceId={workspaceId}
        onOpen={(id) => navigate(pagePath(id, page))}
        onNew={newWorkspace}
        onRename={renameWorkspace}
        earthEngine={earthEngine}
        onEarthEngine={() => setSetupOpen(true)}
        magonia={{
          open: docked || page === "assistant",
          onToggle: () => (page === "assistant" ? magoniaSmaller() : setDocked(!docked)),
        }}
      />
      <Rail workspaceId={workspaceId} />

      {page === "data" && (
        <Sidebar>
          <DataPanel catalogue={catalogue} settings={settings} onChange={change} progress={progress} />
        </Sidebar>
      )}

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

        {page === "data" && (
          <DataPage
            catalogue={catalogue}
            settings={settings}
            onChange={change}
            areas={shown}
            entries={entries}
            mapPath={workspaceId === null ? null : pagePath(workspaceId, "map")}
          />
        )}
        {page === "analyses" && (
          <AnalysesPage
            catalogue={catalogue}
            settings={settings}
            areas={shown}
            entries={entries}
            options={optionsFor}
            dataPath={workspaceId === null ? null : pagePath(workspaceId, "data")}
            mapPath={workspaceId === null ? null : pagePath(workspaceId, "map")}
            analyses={analyses}
            onAdd={(kind: Kind) => changeAnalyses(addAnalysis(analyses, kind, settings.variables))}
            onChange={(id, update) =>
              changeAnalyses(analyses.map((a) => (a.id === id ? ({ ...a, ...update } as Analysis) : a)))
            }
            onRemove={(id) => changeAnalyses(analyses.filter((a) => a.id !== id))}
            onReorder={changeAnalyses}
            onSettings={change}
          />
        )}

        {page === "model" && (
          <ModelPage
            experiments={experiments}
            onChange={changeExperiments}
            areas={shown}
            variables={catalogue}
            title={(v) => variableTitle(v, settings)}
            entries={(variable) => entries(variable)}
            options={(areaId, variable) => optionsFor(areaId, variable)}
            seasonal={settings.resolution === "seasonal"}
            dataPath={workspaceId === null ? null : pagePath(workspaceId, "data")}
            mapPath={workspaceId === null ? null : pagePath(workspaceId, "map")}
            onShown={setExperimentsShown}
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
        {page !== "assistant" && (
          <div
            className="dock-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize Magonia"
            aria-valuenow={panel.width}
            aria-valuemin={PANEL_WIDTH.min}
            tabIndex={0}
            title="Drag to resize"
            onPointerDown={resize}
            onKeyDown={(e) => {
              const step = e.key === "ArrowLeft" ? 40 : e.key === "ArrowRight" ? -40 : 0;
              if (step) setPanel((p) => ({ ...p, width: panelClamp(p.width + step) }));
            }}
          />
        )}
        <AssistantCard
          key={workspaceId}
          workspaceId={workspaceId}
          view={view}
          onPropose={adopt}
          loading={{
            opening: earthEngine === null || workspaceId === null,
            series: progress.total - progress.done - progress.failed,
          }}
          actions={
            page === "assistant" ? (
              <button
                className="icon-button"
                aria-label="Make Magonia smaller"
                title="Back to the side panel"
                onClick={magoniaSmaller}
              >
                <ShrinkIcon size={14} />
              </button>
            ) : (
              <>
                <button
                  className="icon-button"
                  aria-label="Make Magonia bigger"
                  title="Open Magonia full size"
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
