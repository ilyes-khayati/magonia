import type { Area, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import { summarise } from "../stats";
import ChartCard, { type Entry } from "./ChartCard";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
};

export default function ChartsPage({ catalogue, settings, onChange, areas, entries }: Props) {
  const chosen = catalogue.filter((v) => settings.variables.includes(v.key));

  const summary = chosen.flatMap((v) =>
    summarise(
      variableTitle(v, settings),
      entries(v.key).flatMap((e) =>
        e.state?.status === "done"
          ? [{ name: e.area.name, units: v.units, key: v.key, points: e.state.data.points }]
          : [],
      ),
    ),
  );

  return (
    <div className="page">
      <div className="page-head">
        <h1>Charts</h1>
        <div className="segmented" role="group" aria-label="Chart type">
          <button aria-pressed={settings.mode === "series"} onClick={() => onChange({ mode: "series" })}>
            Time series
          </button>
          <button aria-pressed={settings.mode === "seasonal"} onClick={() => onChange({ mode: "seasonal" })}>
            Seasonal cycle
          </button>
        </div>
      </div>

      {!areas.length ? (
        <p className="placeholder">Draw or upload an area on the map to begin.</p>
      ) : !chosen.length ? (
        <p className="placeholder">Choose a variable on the left to see it here.</p>
      ) : (
        <div className="page-grid">
          {chosen.map((v) => (
            <ChartCard
              key={v.key}
              variable={v}
              title={variableTitle(v, settings)}
              entries={entries(v.key)}
              mode={settings.mode}
            />
          ))}
        </div>
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
    </div>
  );
}
