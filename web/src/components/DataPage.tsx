import { Link } from "react-router";
import type { Area, Variable, VariableKey } from "../api";
import { areaLabel, variableTitle, type Settings } from "../settings";
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

export default function DataPage({
  catalogue,
  settings,
  onChange,
  areas,
  entries,
  mapPath,
  onPin,
  onAsk,
}: Props) {
  const keys = ordered(
    catalogue
      .filter((v) => settings.variables.includes(v.key))
      .map((v) => v.key),
    settings.chartOrder,
  );
  const chosen = keys.map((k) => catalogue.find((v) => v.key === k)!);
  const move = (from: number, to: number) =>
    onChange({ chartOrder: moved(keys, from, to) });

  const summary = chosen.flatMap((v) =>
    summarise(
      variableTitle(v, settings),
      entries(v.key).flatMap((e) =>
        e.state?.status === "done"
          ? [
              {
                name: areaLabel(v, settings, e.area),
                units: v.units,
                key: v.key,
                points: e.state.data.points,
              },
            ]
          : [],
      ),
    ),
  );

  // One choice of areas for every chart: all together, or one at a time
  const hiddenNow = chosen.length
    ? (settings.hiddenAreas[chosen[0].key] ?? [])
    : [];
  const showOnly = (ids: number[]) =>
    onChange({
      hiddenAreas: Object.fromEntries(chosen.map((v) => [v.key, ids])),
    });
  const alone =
    hiddenNow.length === areas.length - 1
      ? areas.find((a) => !hiddenNow.includes(a.id))
      : undefined;

  const summaryCard = summary.length > 0 && (
    <section className="card summary-card" aria-label="Summary">
      <div className="card-head">
        <h3>Summary</h3>
        <span className="meta">Computed from the charts below</span>
      </div>
      <ul className="summary">
        {summary.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );

  return (
    <div className="page">
      <div className="page-head">
        <h1>Data</h1>
        <div className="page-tools">
          {areas.length > 1 && chosen.length > 0 && (
            <div
              className="segmented"
              role="group"
              aria-label="Areas in the charts"
            >
              <button
                aria-pressed={hiddenNow.length === 0}
                onClick={() => showOnly([])}
              >
                All areas
              </button>
              {areas.map((a) => (
                <button
                  key={a.id}
                  aria-pressed={alone?.id === a.id}
                  onClick={() =>
                    showOnly(
                      areas.filter((x) => x.id !== a.id).map((x) => x.id),
                    )
                  }
                >
                  {a.name}
                </button>
              ))}
            </div>
          )}
          <div className="segmented" role="group" aria-label="Chart type">
            <button
              aria-pressed={settings.mode === "series"}
              onClick={() => onChange({ mode: "series" })}
            >
              Time series
            </button>
            <button
              aria-pressed={settings.mode === "seasonal"}
              onClick={() => onChange({ mode: "seasonal" })}
            >
              Seasonal cycle
            </button>
            <button
              aria-pressed={settings.mode === "distribution"}
              onClick={() => onChange({ mode: "distribution" })}
            >
              Distribution
            </button>
          </div>
        </div>
      </div>

      {!areas.length ? (
        <p className="placeholder">
          {mapPath ? (
            <Link to={mapPath}>Draw or upload an area on the map</Link>
          ) : (
            "Draw or upload an area on the map"
          )}{" "}
          to begin.
        </p>
      ) : !chosen.length ? (
        <section className="suggestions" aria-label="Suggested charts">
          <h2>What would you like to see?</h2>
          {groups(catalogue).map(([group, variables]) => (
            <div key={group} className="tile-group">
              <h3 className="meta group-name">{group}</h3>
              <div className="tiles">
                {variables.map((v) => (
                  <button
                    key={v.key}
                    className="tile"
                    onClick={() => onChange({ variables: [v.key] })}
                  >
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
        <>
          {summaryCard}
          <div className="page-grid">
            {chosen.map((v, i) => (
              <CardSlot
                key={v.key}
                id={v.key}
                label={variableTitle(v, settings)}
                layout={settings.cards[`chart:${v.key}`] ?? {}}
                onLayout={(layout) =>
                  onChange({
                    cards: { ...settings.cards, [`chart:${v.key}`]: layout },
                  })
                }
                onMove={(step) => move(i, i + step)}
                onDrop={(from) => move(keys.indexOf(from as typeof v.key), i)}
                onPin={
                  onPin &&
                  ((card) =>
                    onPin(card, variableTitle(v, settings), {
                      type: "chart",
                      variable: v.key,
                    }))
                }
                onAsk={onAsk && ((title) => onAsk(`${title} chart`))}
              >
                <ChartCard
                  variable={v}
                  title={variableTitle(v, settings)}
                  entries={entries(v.key).map((e) => {
                    const named = {
                      ...e,
                      area: { ...e.area, name: areaLabel(v, settings, e.area) },
                    };
                    return named.state?.status === "done"
                      ? {
                          ...named,
                          state: {
                            ...named.state,
                            data: {
                              ...named.state.data,
                              points: display(
                                named.state.data.points,
                                settings.display,
                              ),
                            },
                          },
                        }
                      : named;
                  })}
                  mode={settings.mode}
                  shown={describeDisplay(settings.display)}
                  anomaly={settings.display.anomaly !== null}
                  hidden={settings.hiddenAreas[v.key] ?? []}
                  onHidden={(ids) =>
                    onChange({
                      hiddenAreas: { ...settings.hiddenAreas, [v.key]: ids },
                    })
                  }
                  pickAreas={false}
                />
              </CardSlot>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
