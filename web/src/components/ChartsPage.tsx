import { Link } from "react-router";
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
  mapPath: string | null;
};

export default function ChartsPage({ catalogue, settings, onChange, areas, entries, mapPath }: Props) {
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
        <p className="placeholder">
          {mapPath ? <Link to={mapPath}>Draw or upload an area on the map</Link> : "Draw or upload an area on the map"} to
          begin.
        </p>
      ) : !chosen.length ? (
        <section className="suggestions" aria-label="Suggested charts">
          <h2>What would you like to see?</h2>
          <div className="tiles">
            {catalogue.map((v) => (
              <button key={v.key} className="tile" onClick={() => onChange({ variables: [v.key] })}>
                <strong>{v.name}</strong>
                <span className="meta">
                  {v.product} · {v.resolution} · {v.cadence}
                </span>
              </button>
            ))}
          </div>
        </section>
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
