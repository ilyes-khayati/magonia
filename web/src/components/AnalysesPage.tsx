import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { KINDS, type Analysis, type Kind } from "../analyses";
import { moved } from "../cards";
import type { Area, SeriesOptions, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import CardSlot from "./CardSlot";
import type { Entry } from "./ChartCard";
import CorrelationCard from "./CorrelationCard";
import DecompositionCard from "./DecompositionCard";
import LagsCard from "./LagsCard";
import TrendCard from "./TrendCard";
import { PlusIcon } from "./Icons";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  areas: Area[];
  entries: (variable: VariableKey, native?: boolean) => Entry[];
  options: (areaId: number, variable: VariableKey, native?: boolean) => SeriesOptions;
  analyses: Analysis[];
  onAdd: (kind: Kind) => void;
  onChange: (id: number, change: Partial<Analysis>) => void;
  onRemove: (id: number) => void;
  onReorder: (analyses: Analysis[]) => void;
  onSettings: (change: Partial<Settings>) => void;
  dataPath: string | null;
  mapPath: string | null;
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const month = (value: string) => {
  const [year, m] = value.split("-").map(Number);
  return `${MONTHS[m - 1]} ${year}`;
};
const STEPS = { native: "each product's own time step", monthly: "monthly", seasonal: "seasonal means" };
const CLOUDS = { pixel: "cloudy pixels removed", date: "cloudy dates removed", none: "no cloud filter" };

// The menu of analysis types, closed by a choice, Escape or a click elsewhere
function AddAnalysis({ onAdd }: { onAdd: (kind: Kind) => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", close);
    document.addEventListener("mousedown", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("mousedown", close);
    };
  }, [open]);

  return (
    <div className="add-analysis" ref={box}>
      <button className="primary row" aria-expanded={open} onClick={() => setOpen(!open)}>
        <PlusIcon size={14} />
        Add analysis
      </button>
      {open && (
        <div className="floating kinds" role="group" aria-label="Analysis types">
          {KINDS.map(({ kind, label, description }) => (
            <button
              key={kind}
              onClick={() => {
                onAdd(kind);
                setOpen(false);
              }}
            >
              <strong>{label}</strong>
              <span className="meta">{description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function AnalysesPage(props: Props) {
  const { catalogue, settings, areas, entries, options, analyses, onAdd, onChange, onRemove, onReorder, onSettings, dataPath, mapPath } =
    props;
  const title = (v: Variable) => variableTitle(v, settings);
  const data = [
    `${month(settings.start)} to ${month(settings.end)}`,
    STEPS[settings.resolution],
    CLOUDS[settings.masking],
    settings.fill ? `gaps up to ${settings.maxGap} filled` : "gaps left empty",
  ].join(" · ");

  function card(analysis: Analysis) {
    switch (analysis.kind) {
      case "correlation":
        return (
          <CorrelationCard
            analysis={analysis}
            onChange={(change) => onChange(analysis.id, change)}
            onRemove={() => onRemove(analysis.id)}
            variables={catalogue}
            title={title}
            entries={entries}
            seasonal={settings.resolution === "seasonal"}
          />
        );
      case "decomposition":
        return (
          <DecompositionCard
            analysis={analysis}
            onChange={(change) => onChange(analysis.id, change)}
            onRemove={() => onRemove(analysis.id)}
            variables={catalogue}
            title={title}
            entries={entries(analysis.variable, true)}
            options={(areaId) => options(areaId, analysis.variable, true)}
          />
        );
      case "trend":
        return (
          <TrendCard
            analysis={analysis}
            onChange={(change) => onChange(analysis.id, change)}
            onRemove={() => onRemove(analysis.id)}
            variables={catalogue}
            title={title}
            entries={entries(analysis.variable)}
            options={(areaId) => options(areaId, analysis.variable)}
          />
        );
      case "lags":
        return (
          <LagsCard
            analysis={analysis}
            onChange={(change) => onChange(analysis.id, change)}
            onRemove={() => onRemove(analysis.id)}
            variables={catalogue}
            title={title}
            entries={(variable) => entries(variable)}
            options={(areaId, variable) => options(areaId, variable)}
            seasonal={settings.resolution === "seasonal"}
          />
        );
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Analyses</h1>
        {analyses.length > 0 && <AddAnalysis onAdd={onAdd} />}
      </div>
      <p className="meta data-line">
        Data: {data}
        {dataPath && (
          <>
            {" · "}
            <Link to={dataPath}>change on Data</Link>
          </>
        )}
      </p>

      {!areas.length ? (
        <p className="placeholder">
          {mapPath ? <Link to={mapPath}>Draw or upload an area on the map</Link> : "Draw or upload an area on the map"} to
          begin.
        </p>
      ) : !analyses.length ? (
        <section className="suggestions" aria-label="Suggested analyses">
          <h2>What would you like to find out?</h2>
          <div className="tiles">
            {KINDS.map(({ kind, label, question, description }) => (
              <button key={kind} className="tile" onClick={() => onAdd(kind)}>
                <strong>{label}</strong>
                <span>{question}</span>
                <span className="meta">{description}</span>
              </button>
            ))}
          </div>
        </section>
      ) : (
        <div className="page-grid">
          {analyses.map((analysis, i) => (
            <CardSlot
              key={analysis.id}
              id={String(analysis.id)}
              label={KINDS.find((k) => k.kind === analysis.kind)!.label}
              layout={settings.cards[`analysis:${analysis.id}`] ?? {}}
              onLayout={(layout) => onSettings({ cards: { ...settings.cards, [`analysis:${analysis.id}`]: layout } })}
              onMove={(step) => onReorder(moved(analyses, i, i + step))}
              onDrop={(from) => onReorder(moved(analyses, analyses.findIndex((a) => String(a.id) === from), i))}
            >
              {card(analysis)}
            </CardSlot>
          ))}
        </div>
      )}
    </div>
  );
}
