import type { Area, Variable, VariableKey } from "../api";
import type { Settings } from "../settings";
import { summarise } from "../stats";
import ChartCard, { type Entry } from "./ChartCard";
import { ExpandIcon } from "./Icons";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
  wide: boolean;
  onWide: () => void;
};

export default function Results({ catalogue, settings, onChange, areas, entries, wide, onWide }: Props) {
  const chosen = catalogue.filter((v) => settings.variables.includes(v.key));
  const title = (v: Variable) => (v.key === "spei" ? `SPEI-${settings.scale}` : v.name);

  const summary = chosen.flatMap((v) =>
    summarise(
      title(v),
      entries(v.key).flatMap((e) =>
        e.state?.status === "done"
          ? [{ name: e.area.name, units: v.units, key: v.key, points: e.state.data.points }]
          : [],
      ),
    ),
  );

  return (
    <aside className="results" aria-label="Results">
      <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 15 }}>Results</h2>
        <div className="row">
          <div className="segmented" role="group" aria-label="Chart type">
            <button aria-pressed={settings.mode === "series"} onClick={() => onChange({ mode: "series" })}>
              Time series
            </button>
            <button aria-pressed={settings.mode === "seasonal"} onClick={() => onChange({ mode: "seasonal" })}>
              Seasonal cycle
            </button>
          </div>
          <button
            className="icon-button"
            aria-label={wide ? "Narrow the results panel" : "Widen the results panel"}
            title={wide ? "Narrow the results panel" : "Widen the results panel"}
            onClick={onWide}
          >
            <ExpandIcon size={14} />
          </button>
        </div>
      </div>

      {!areas.length ? (
        <p className="placeholder">Draw or upload an area to begin.</p>
      ) : !chosen.length ? (
        <p className="placeholder">Choose a variable on the left to see it here.</p>
      ) : (
        chosen.map((v) => (
          <ChartCard key={v.key} variable={v} title={title(v)} entries={entries(v.key)} mode={settings.mode} />
        ))
      )}

      {summary.length > 0 && (
        <section className="card">
          <div className="card-head">
            <h3>Summary</h3>
            <span className="meta">Computed from the data above</span>
          </div>
          <ul className="summary">
            {summary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="card ask">
        <label htmlFor="ask" style={{ fontWeight: 600 }}>
          Ask about these results
        </label>
        <textarea id="ask" rows={2} disabled placeholder="Why is the cereal field greener than the orchard in spring?" />
        <span className="meta">
          The assistant arrives in version 2. It will answer from these numbers and their provenance.
        </span>
      </section>
    </aside>
  );
}
