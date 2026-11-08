import type { Tiles, Variable, VariableKey } from "../api";
import { num } from "../format";
import { groups } from "../variables";
import type { Layer } from "./MapView";
import { Growing } from "./Brand";
import { CloseIcon } from "./Icons";
import { shiftMonth, ticks } from "../months";

type Props = {
  catalogue: Variable[];
  layer: Layer | null;
  onLayer: (layer: Layer | null) => void;
  month: string | null;
  onMonth: (month: string) => void;
  compare: string | null;
  onCompare: (month: string | null) => void;
  grid: VariableKey | null;
  onGrid: (variable: VariableKey | null) => void;
  tiles: Tiles | null;
  error: string | null;
  loading: boolean;
  onClose: () => void;
};

// The map's layers: one variable for one month, its colour ramp, and the tools that read it
export default function LayerPanel(props: Props) {
  const { catalogue, layer, month, compare, grid, tiles } = props;
  const variable = catalogue.find((v) => v.key === layer?.variable);
  const set = (change: Partial<Layer>) => layer && props.onLayer({ ...layer, ...change });

  return (
    <section className="floating panel layer-panel" aria-label="Map layers">
      <header className="panel-head">
        <h3>Layers</h3>
        <button className="icon-button" aria-label="Close layers" title="Close (L)" onClick={props.onClose}>
          <CloseIcon size={14} />
        </button>
      </header>

      <label className="field">
        <span>Variable</span>
        <select
          className="select"
          value={layer?.variable ?? ""}
          onChange={(e) => {
            const key = e.target.value as VariableKey | "";
            props.onLayer(key ? { variable: key, opacity: layer?.opacity ?? 0.8, scale: key === "spei" ? (layer?.scale ?? 3) : undefined } : null);
          }}
        >
          <option value="">None (basemap only)</option>
          {groups(catalogue).map(([group, variables]) => (
            <optgroup key={group} label={group}>
              {variables.map((v) => (
                <option key={v.key} value={v.key}>
                  {v.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      {layer?.variable === "spei" && (
        <label className="field">
          <span>Time scale</span>
          <select className="select" value={layer.scale ?? 3} onChange={(e) => set({ scale: Number(e.target.value) })}>
            {(variable?.scales ?? [1, 3, 6, 12]).map((s) => (
              <option key={s} value={s}>
                {s} month{s > 1 ? "s" : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      {layer && month && (
        <>
          <div className="field">
            <span>Month</span>
            <div className="stepper">
              <button aria-label="Previous month" title="Previous month ([)" onClick={() => props.onMonth(shiftMonth(month, -1))}>
                ‹
              </button>
              <input type="month" aria-label="Month shown" value={month} onChange={(e) => e.target.value && props.onMonth(e.target.value)} />
              <button aria-label="Next month" title="Next month (])" onClick={() => props.onMonth(shiftMonth(month, 1))}>
                ›
              </button>
            </div>
          </div>

          <label className="field">
            <span>
              Opacity <span className="meta">{Math.round(layer.opacity * 100)}%</span>
            </span>
            <input type="range" min={0} max={1} step={0.05} value={layer.opacity} onChange={(e) => set({ opacity: Number(e.target.value) })} />
          </label>

          <div className="legend-ramp" aria-label={`${variable?.name ?? ""} colour scale`}>
            {tiles ? (
              <>
                <div className="ramp" style={{ background: `linear-gradient(to right, ${tiles.palette.join(", ")})` }} />
                <div className="ramp-ticks">
                  {ticks(tiles.low, tiles.high).map(({ value, at, digits }) => (
                    <span key={value} style={{ left: `${at * 100}%` }}>
                      {num(value, digits)}
                    </span>
                  ))}
                </div>
                <div className="meta">
                  {variable?.name}
                  {variable?.units ? ` (${variable.units})` : ""} · {variable?.product} · mean of {month}
                </div>
              </>
            ) : props.error ? (
              <p className="error-text">{props.error}</p>
            ) : (
              <p className="meta working" role="status">
                {props.loading && <Growing size={16} />}
                {props.loading ? `Drawing ${variable?.name} for ${month} on Earth Engine…` : ""}
              </p>
            )}
          </div>

          <label className="check">
            <input type="checkbox" checked={compare !== null} onChange={(e) => props.onCompare(e.target.checked ? shiftMonth(month, -12) : null)} />
            Swipe compare with another month
          </label>
          {compare && (
            <div className="field">
              <span>Right of the divider</span>
              <div className="stepper">
                <button aria-label="Previous compared month" onClick={() => props.onCompare(shiftMonth(compare, -1))}>
                  ‹
                </button>
                <input type="month" aria-label="Compared month" value={compare} onChange={(e) => e.target.value && props.onCompare(e.target.value)} />
                <button aria-label="Next compared month" onClick={() => props.onCompare(shiftMonth(compare, 1))}>
                  ›
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <label className="check">
        <input type="checkbox" checked={grid !== null} onChange={(e) => props.onGrid(e.target.checked ? (layer?.variable ?? "ndvi") : null)} />
        Outline the pixels over each area
      </label>
      {grid && (
        <p className="meta">
          {catalogue.find((v) => v.key === grid)?.name} pixels at {catalogue.find((v) => v.key === grid)?.resolution}: each area's mean is made of
          these.
        </p>
      )}
    </section>
  );
}
