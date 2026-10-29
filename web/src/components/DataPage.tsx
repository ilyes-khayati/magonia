import { Link } from "react-router";
import type { Area, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import { summarise } from "../stats";
import { moved, ordered } from "../cards";
import CardSlot from "./CardSlot";
import ChartCard, { type Entry } from "./ChartCard";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
  mapPath: string | null;
};

export default function DataPage({ catalogue, settings, onChange, areas, entries, mapPath }: Props) {
  const keys = ordered(
    catalogue.filter((v) => settings.variables.includes(v.key)).map((v) => v.key),
    settings.chartOrder,
  );
  const chosen = keys.map((k) => catalogue.find((v) => v.key === k)!);
  const move = (from: number, to: number) => onChange({ chartOrder: moved(keys, from, to) });

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
        <h1>Data</h1>
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
          {chosen.map((v, i) => (
            <CardSlot
              key={v.key}
              id={v.key}
              label={variableTitle(v, settings)}
              layout={settings.cards[`chart:${v.key}`] ?? {}}
              onLayout={(layout) => onChange({ cards: { ...settings.cards, [`chart:${v.key}`]: layout } })}
              onMove={(step) => move(i, i + step)}
              onDrop={(from) => move(keys.indexOf(from as typeof v.key), i)}
            >
              <ChartCard variable={v} title={variableTitle(v, settings)} entries={entries(v.key)} mode={settings.mode} />
            </CardSlot>
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
