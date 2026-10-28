import { useEffect, useRef, useState } from "react";
import { KINDS, type Analysis, type Kind } from "../analyses";
import type { Area, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import type { Entry } from "./ChartCard";
import CorrelationCard from "./CorrelationCard";
import { PlusIcon } from "./Icons";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
  analyses: Analysis[];
  onAdd: (kind: Kind) => void;
  onChange: (id: number, change: Partial<Analysis>) => void;
  onRemove: (id: number) => void;
};

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
          <p className="meta">Decomposition, lags, models and explanations are coming.</p>
        </div>
      )}
    </div>
  );
}

export default function AnalysesPage(props: Props) {
  const { catalogue, settings, areas, entries, analyses, onAdd, onChange, onRemove } = props;
  const title = (v: Variable) => variableTitle(v, settings);

  return (
    <div className="page">
      <div className="page-head">
        <h1>Analyses</h1>
        <AddAnalysis onAdd={onAdd} />
      </div>

      {!areas.length ? (
        <p className="placeholder">Draw or upload an area on the map to begin.</p>
      ) : !analyses.length ? (
        <p className="placeholder">No analyses yet. Add one to study how your variables are related.</p>
      ) : (
        <div className="page-grid">
          {analyses.map((analysis) => {
            switch (analysis.kind) {
              case "correlation":
                return (
                  <CorrelationCard
                    key={analysis.id}
                    analysis={analysis}
                    onChange={(change) => onChange(analysis.id, change)}
                    onRemove={() => onRemove(analysis.id)}
                    variables={catalogue}
                    title={title}
                    entries={entries}
                    seasonal={settings.resolution === "seasonal"}
                  />
                );
            }
          })}
        </div>
      )}
    </div>
  );
}
