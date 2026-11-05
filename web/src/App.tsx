import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMatch, useNavigate } from "react-router";
import {
  createArea,
  createWorkspace,
  deleteArea,
  deleteWorkspace,
  deleteWorkspaceForever,
  earthEngineStatus,
  fetchCatalogue,
  getInstructions,
  setInstructions,
  listWorkspaces,
  openWorkspace,
  renameArea,
  restoreArea,
  restoreWorkspace,
  updateWorkspace,
  type Area,
  type EarthEngineStatus,
  type Proposal,
  type Variable,
  type VariableKey,
  type Workspace,
  type WorkspaceSummary,
  type PaperCard,
  type PassageCard,
} from "./api";
import { addAnalysis, needsOf, readAnalyses, type Analysis, type Kind, type Models, type Need } from "./analyses";
import { withInstruction, type Turn } from "./chat";
import { boardForMagonia, pin, readBoard, snapshotLines, type BoardItem, type Source } from "./board";
import AnalysisCard from "./components/AnalysisCard";
import ChartCard from "./components/ChartCard";
import PinnedExperiment from "./components/PinnedExperiment";
import BoardPage from "./components/BoardPage";
import { describeDisplay } from "./display";
import { EMPTY, MODEL_NAMES, newExperiment, readExperiments, type Experiment } from "./experiments";
import { readAreaFile } from "./areaFiles";
import AnalysesPage from "./components/AnalysesPage";
import AssistantCard from "./components/AssistantCard";
import DataPage from "./components/DataPage";
import DataPanel from "./components/DataPanel";
import EarthEngineSetup from "./components/EarthEngineSetup";
import { CloseIcon, ExpandIcon, ShrinkIcon } from "./components/Icons";
import MapView, { type Target, type Tool } from "./components/MapView";
import LibraryPage from "./components/LibraryPage";
import ModelPage from "./components/ModelPage";
import Rail from "./components/Rail";
import Sidebar from "./components/Sidebar";
import Toolbar from "./components/Toolbar";
import TopBar from "./components/TopBar";
import UndoBar from "./components/UndoBar";
import Reader from "./components/Reader";
import { ReaderContext, whereToRead, type Readable } from "./reader";
import { PAGES, isPage, pagePath, type Page } from "./pages";
import { DEFAULTS, readSettings, seriesKey, seriesOptions, variableTitle, type Settings } from "./settings";
import { applyTheme, areaColour, initialTheme, type Theme } from "./theme";
import { removeFrom, restoreAt, type Removed, type Undo } from "./undo";
import { useSeries } from "./useSeries";

type Message = { text: string; error?: boolean } | null;

// The workspace as it is now, for undoing a removal made earlier
type Latest = {
  analyses: Analysis[];
  experiments: Experiment[];
  board: BoardItem[];
  changeAnalyses: (next: Analysis[]) => void;
  changeExperiments: (next: Experiment[]) => void;
  changeBoard: (next: BoardItem[]) => void;
};

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
  const [board, setBoard] = useState<BoardItem[]>([]);
  const [tool, setTool] = useState<Tool>(null);
  const [target, setTarget] = useState<Target | null>(null);
  const [message, setMessage] = useState<Message>(null);
  const [catalogue, setCatalogue] = useState<Variable[]>([]);
  const [settings, setSettings] = useState<Settings>(DEFAULTS);
  const [panel, setPanel] = useState(panelSaved);
  const [earthEngine, setEarthEngine] = useState<EarthEngineStatus | null>(null);
  const [setupOpen, setSetupOpen] = useState(false);
  const [focus, setFocus] = useState(false);
  const [undo, setUndo] = useState<Undo | null>(null);
  const [attached, setAttached] = useState<{ title: string; key: number } | null>(null);
  const [reading, setReading] = useState<Readable | null>(null);
  // a paper opens inside Magonia when it is the researcher's own, else in a new tab
  const read = useCallback((paper: PaperCard, page?: number) => {
    const where = whereToRead(paper, page);
    if (!where) return;
    if (where.inside) setReading(where);
    else window.open(where.url, "_blank", "noreferrer");
  }, []);
  const closeReader = useCallback(() => setReading(null), []);
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

  // "Ask Magon about this" on a card: Magon opens beside the page with the card attached
  function askAbout(title: string) {
    setAttached({ title, key: Date.now() });
    if (page !== "assistant") setDocked(true);
  }

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

  const fail = useCallback(
    (error: unknown) => setMessage({ text: error instanceof Error ? error.message : String(error), error: true }),
    [],
  );

  // What was removed, offered back from the bar at the foot of the page. An undo runs later
  // than the removal, so it acts on the workspace as it is then, through `latest`.
  const latest = useRef<Latest | null>(null);
  function offer(text: string, run: () => void | Promise<void>, everywhere = false) {
    setUndo({ key: Date.now(), text, run, workspace: everywhere ? null : workspaceId });
  }
  const clearUndo = useCallback(() => setUndo(null), []);

  function show(id: number, workspace: Workspace) {
    setWorkspaceId(id);
    setAreas(workspace.areas);
    setSettings(readSettings(workspace.settings));
    setHidden(new Set((workspace.settings.hidden as number[] | undefined) ?? []));
    setAnalyses(readAnalyses(workspace.settings.analyses));
    // forecast cards from before the Model page become experiments
    const saved = Array.isArray(workspace.settings.analyses) ? (workspace.settings.analyses as { kind?: string }[]) : [];
    setExperiments(readExperiments(workspace.settings.experiments, saved.filter((a): a is Models => a.kind === "models")));
    setBoard(readBoard(workspace.settings.board));
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
  }, [routed, valid, page, workspaces, workspaceId, navigate, fail]);

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
      offer(`${area.name} deleted`, async () => {
        const back = await restoreArea(area.id);
        setAreas((now) => [...now.filter((a) => a.id !== back.id), back].sort((a, b) => a.id - b.id));
      });
    } catch (error) {
      fail(error);
    }
  }

  // A deleted workspace waits in Recently deleted; another one opens meanwhile
  async function removeWorkspace(id: number) {
    const gone = workspaces.find((w) => w.id === id);
    try {
      await deleteWorkspace(id);
      let rest = workspaces.filter((w) => w.id !== id);
      if (!rest.length) rest = [await createWorkspace("My workspace")];
      setWorkspaces(rest);
      if (id === workspaceId) navigate(pagePath(rest[0].id, page));
      offer(
        `${gone?.name ?? "Workspace"} moved to Recently deleted`,
        () => bringBack(id),
        true,
      );
    } catch (error) {
      fail(error);
    }
  }

  async function bringBack(id: number) {
    const back = await restoreWorkspace(id);
    setWorkspaces((now) => [back, ...now.filter((w) => w.id !== id)]);
    navigate(pagePath(id, page));
  }

  async function forget(id: number) {
    try {
      await deleteWorkspaceForever(id);
    } catch (error) {
      fail(error);
    }
  }

  // Settings, hidden areas and analyses are saved with the workspace, half a second after the
  // last change
  function save(next: {
    settings?: Settings;
    hidden?: Set<number>;
    analyses?: Analysis[];
    experiments?: Experiment[];
    board?: BoardItem[];
  }) {
    window.clearTimeout(saving.current);
    const id = workspaceId;
    if (id === null) return;
    const saved = {
      ...(next.settings ?? settings),
      hidden: [...(next.hidden ?? hidden)],
      analyses: next.analyses ?? analyses,
      experiments: next.experiments ?? experiments,
      board: next.board ?? board,
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

  function changeBoard(next: BoardItem[]) {
    setBoard(next);
    save({ board: next });
  }

  latest.current = { analyses, experiments, board, changeAnalyses, changeExperiments, changeBoard };

  function removeAnalysis(id: number) {
    const { rest, removed } = removeFrom(analyses, id);
    if (!removed) return;
    changeAnalyses(rest);
    offer("Analysis removed", () => {
      const now = latest.current!;
      now.changeAnalyses(restoreAt(now.analyses, removed));
    });
  }

  function removeExperiment(id: number) {
    const { rest, removed } = removeFrom(experiments, id);
    if (!removed) return;
    changeExperiments(rest);
    offer(`${removed.item.name} deleted`, () => {
      const now = latest.current!;
      now.changeExperiments(restoreAt(now.experiments, removed as Removed<Experiment>));
    });
  }

  function removePin(id: number) {
    const { rest, removed } = removeFrom(board, id);
    if (!removed) return;
    changeBoard(rest);
    const what = removed.item.kind === "section" ? "Section" : removed.item.kind === "note" ? "Note" : "Pin";
    offer(`${what} removed from the board`, () => {
      const now = latest.current!;
      now.changeBoard(restoreAt(now.board, removed));
    });
  }

  // A card pinned to the board: drawn live there from its own copy of the card's choices. Its
  // sentences are kept too, for Magonia and for when its data is not loaded.
  function pinCard(card: HTMLElement, title: string, source: Source) {
    const { lines, cautions } = snapshotLines(card);
    const kind = source.type === "experiment" ? "experiment" : "card";
    changeBoard(pin(board, { kind, title, lines, cautions, page, source }));
    setMessage({ text: `Pinned ${title} to the board.` });
  }

  // The live card of a pinned item
  function livePin(item: BoardItem, update: (change: Partial<BoardItem>) => void, remove: () => void) {
    const source = item.source;
    if (!source) return null;
    const title = (v: Variable) => variableTitle(v, settings);
    if (source.type === "chart") {
      const v = catalogue.find((x) => x.key === source.variable);
      return v ? (
        <ChartCard
          variable={v}
          title={title(v)}
          entries={entries(v.key)}
          mode={settings.mode}
          hidden={settings.hiddenAreas[v.key] ?? []}
        />
      ) : null;
    }
    if (source.type === "analysis")
      return (
        <AnalysisCard
          analysis={source.analysis}
          onChange={(change) => update({ source: { type: "analysis", analysis: { ...source.analysis, ...change } as Analysis } })}
          onRemove={remove}
          catalogue={catalogue}
          settings={settings}
          entries={entries}
          options={optionsFor}
        />
      );
    return (
      <PinnedExperiment
        experiment={source.experiment}
        onChange={(experiment) => update({ source: { type: "experiment", experiment } })}
        onRemove={remove}
        areas={areas.filter((a) => !hidden.has(a.id))}
        variables={catalogue}
        title={title}
        entries={(variable) => entries(variable)}
        options={(areaId, variable) => optionsFor(areaId, variable)}
      />
    );
  }

  function pinAnswer(question: string, turn: Turn) {
    const answer = turn.content;
    const next = pin(board, {
      kind: "answer",
      title: `Magon: ${question.length > 60 ? `${question.slice(0, 57)}…` : question}`,
      question,
      lines: answer.split("\n").filter((l) => l.trim()),
      answer: { text: answer, details: turn.details },
      page: "assistant",
    });
    changeBoard(next);
    setMessage({ text: "Pinned the answer to the board." });
  }

  // One passage of a paper, kept on its own with its page and a link to the paper
  function pinPassage(paper: PaperCard, passage: PassageCard) {
    const link = paper.doi ? `https://doi.org/${paper.doi}` : (paper.open_access_url ?? undefined);
    const title = `${paper.short}, p. ${passage.page}`;
    changeBoard(pin(board, { kind: "passage", title, lines: [passage.text], link, page: "assistant" }));
    setMessage({ text: `Pinned the passage from ${title} to the board.` });
  }

  // An instruction asked for in the chat, saved because the researcher clicked; Undo puts
  // the instructions back as they were
  async function keepInstruction(id: number, instruction: string) {
    try {
      const before = (await getInstructions(id)).text;
      await setInstructions(id, withInstruction(before, instruction));
      offer(`Saved as an instruction for Magon: ${instruction}`, async () => {
        await setInstructions(id, before);
      });
    } catch (error) {
      fail(error);
    }
  }

  // What Magonia proposed, added because the researcher clicked (AI-07): its card, and the
  // period if one was asked for
  function adopt(p: Proposal) {
    if (workspaceId === null) return;
    if (p.kind === "instruction") {
      keepInstruction(workspaceId, p.text ?? p.title);
      return;
    }
    const nextSettings = p.period
      ? { ...settings, start: p.period.start ?? settings.start, end: p.period.end ?? settings.end }
      : settings;
    setSettings(nextSettings);
    const visible = areas.filter((a) => !hidden.has(a.id));
    const areaId = (p.area ? areas.find((a) => a.name === p.area)?.id : undefined) ?? visible[0]?.id ?? null;
    if (p.kind === "experiment") {
      const recipe = {
        ...structuredClone(EMPTY),
        area: areaId,
        response: p.variable ?? "ndvi",
        drivers: p.drivers ?? [],
        calendar: true,
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
    // pinned cards are drawn live, so their series are fetched too
    const pinned = board.flatMap(({ source }): Need[] =>
      !source
        ? []
        : source.type === "chart"
          ? [{ variable: source.variable, native: false }]
          : source.type === "analysis"
            ? needsOf(source.analysis)
            : (source.experiment.ran ? [source.experiment.ran.response, ...source.experiment.ran.drivers] : []).map(
                (variable) => ({ variable, native: false }),
              ),
    );
    const all: Need[] = [
      ...settings.variables.map((variable) => ({ variable, native: false })),
      ...analyses.flatMap(needsOf),
      ...forecast,
      ...pinned,
    ];
    return all.filter((n, i) => all.findIndex((m) => m.variable === n.variable && m.native === n.native) === i);
  }, [settings.variables, analyses, experiments, board]);
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
  // (built afresh each render: it is only read when a question is sent)
  const view = {
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
    board: boardForMagonia(board),
    focus: attached?.title ?? null,
  };
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
  const magon = {
    open: docked || page === "assistant",
    onToggle: () => (page === "assistant" ? magoniaSmaller() : setDocked(!docked)),
  };

  return (
    <ReaderContext.Provider value={read}>
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
        onDelete={removeWorkspace}
        onRestore={(id) => bringBack(id).catch(fail)}
        onForget={forget}
        earthEngine={earthEngine}
        onEarthEngine={() => setSetupOpen(true)}
      />
      <Rail workspaceId={workspaceId} magon={magon} />

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
            onPin={pinCard}
            onAsk={askAbout}
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
            onRemove={removeAnalysis}
            onReorder={changeAnalyses}
            onSettings={change}
            onPin={pinCard}
            onAsk={askAbout}
          />
        )}

        {page === "board" && (
          <BoardPage
            board={board}
            onChange={changeBoard}
            onRemove={removePin}
            onNote={() => changeBoard(pin(board, { kind: "note", title: "Note", lines: [] }))}
            onSection={() => changeBoard(pin(board, { kind: "section", title: "New section", lines: [] }))}
            pagePath={(p) => (workspaceId === null || !isPage(p) ? null : pagePath(workspaceId, p))}
            live={livePin}
          />
        )}
        {page === "library" && workspaceId !== null && (
          <LibraryPage key={workspaceId} workspaceId={workspaceId} onUndoable={(text, run) => offer(text, run)} />
        )}
        {page === "model" && (
          <ModelPage
            experiments={experiments}
            onChange={changeExperiments}
            onRemove={removeExperiment}
            areas={shown}
            variables={catalogue}
            title={(v) => variableTitle(v, settings)}
            entries={(variable) => entries(variable)}
            options={(areaId, variable) => optionsFor(areaId, variable)}
            seasonal={settings.resolution === "seasonal"}
            dataPath={workspaceId === null ? null : pagePath(workspaceId, "data")}
            mapPath={workspaceId === null ? null : pagePath(workspaceId, "map")}
            onShown={setExperimentsShown}
            onPin={pinCard}
          />
        )}

        <UndoBar
          undo={undo && (undo.workspace === null || undo.workspace === workspaceId) ? undo : null}
          onDone={clearUndo}
          onError={fail}
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

      {/* One assistant for every page, so a conversation carries on when the page changes:
          a full page of its own, or a panel beside the others */}
      <aside className="dock" aria-label="Magon's panel">
        {page !== "assistant" && (
          <div
            className="dock-handle"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize Magon's panel"
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
          onPin={pinAnswer}
          onPinPassage={pinPassage}
          onUndoable={(text, run) => offer(text, run)}
          attached={attached}
          onDetach={() => setAttached(null)}
          loading={{
            opening: earthEngine === null || workspaceId === null,
            series: progress.total - progress.done - progress.failed,
          }}
          actions={
            page === "assistant" ? (
              <button
                className="icon-button"
                aria-label="Make Magon smaller"
                title="Back to the side panel"
                onClick={magoniaSmaller}
              >
                <ShrinkIcon size={14} />
              </button>
            ) : (
              <>
                <button
                  className="icon-button"
                  aria-label="Make Magon bigger"
                  title="Open Magon full size"
                  onClick={() => workspaceId !== null && navigate(pagePath(workspaceId, "assistant"))}
                >
                  <ExpandIcon size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label="Close Magon"
                  title="Close Magon"
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
      {reading && <Reader paper={reading} onClose={closeReader} />}
    </div>
    </ReaderContext.Provider>
  );
}
