import { Link } from "react-router";
import type { Area, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import { summarise } from "../stats";
import type { Source } from "../board";
import { moved, ordered } from "../cards";
import CardSlot from "./CardSlot";
import { describeDisplay, display } from "../display";
import ChartCard, { type Entry } from "./ChartCard";
import { groups } from "../variables";

const firstSentence = (text: string) => text.split(/(?<=\.)\s/)[0];

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
  mapPath: string | null;
  onPin?: (card: HTMLElement, title: string, source: Source) => void;
  onAsk?: (title: string) => void;
};

export default function DataPage({ catalogue, settings, onChange, areas, entries, mapPath, onPin, onAsk }: Props) {
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
          {groups(catalogue).map(([group, variables]) => (
            <div key={group} className="tile-group">
              <h3 className="meta group-name">{group}</h3>
              <div className="tiles">
                {variables.map((v) => (
                  <button key={v.key} className="tile" onClick={() => onChange({ variables: [v.key] })}>
                    <strong>{v.name}</strong>
                    {v.learn && <span>{firstSentence(v.learn.what)}</span>}
                    <span className="meta">
                      {v.product} · {v.resolution} · {v.cadence}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
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
              onPin={onPin && ((card) => onPin(card, variableTitle(v, settings), { type: "chart", variable: v.key }))}
              onAsk={onAsk && ((title) => onAsk(`${title} chart`))}
            >
              <ChartCard
                variable={v}
                title={variableTitle(v, settings)}
                entries={entries(v.key).map((e) =>
                  e.state?.status === "done"
                    ? { ...e, state: { ...e.state, data: { ...e.state.data, points: display(e.state.data.points, settings.display) } } }
                    : e,
                )}
                mode={settings.mode}
                shown={describeDisplay(settings.display)}
                anomaly={settings.display.anomaly !== null}
                hidden={settings.hiddenAreas[v.key] ?? []}
                onHidden={(ids) => onChange({ hiddenAreas: { ...settings.hiddenAreas, [v.key]: ids } })}
              />
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
