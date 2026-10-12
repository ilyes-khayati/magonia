import type { Masking, Resolution, Variable, VariableKey } from "../api";
import type { Settings } from "../settings";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  progress: { done: number; total: number; failed: number };
};

const RESOLUTIONS: [Resolution, string][] = [
  ["native", "Native"],
  ["monthly", "Monthly"],
  ["seasonal", "Seasonal"],
];

const CLOUD_FILTERS: [Masking, string][] = [
  ["pixel", "Remove cloudy pixels"],
  ["date", "Remove cloudy dates"],
  ["none", "No cloud filter"],
];

// Why each recommended step is on by default (PREP-01)
const REASONS = {
  pixel: "Recommended: drops cloudy pixels and keeps the clear part of the area.",
  date: "Drops a whole date when half the area or more is cloudy.",
  none: "Raw values: clouds will appear as sudden drops.",
  fill: "Recommended: fills short gaps by straight lines in time; longer gaps stay empty.",
};

export default function DataPanel({ catalogue, settings, onChange, progress }: Props) {
  function toggle(key: VariableKey) {
    const on = settings.variables.includes(key);
    // keep the catalogue order whatever the order of clicks
    const next = catalogue.map((v) => v.key).filter((k) => (k === key ? !on : settings.variables.includes(k)));
    onChange({ variables: next });
  }

  return (
    <>
      <fieldset className="section" style={{ border: "none", margin: 0, padding: 0 }}>
        <legend className="label" style={{ padding: 0, marginBottom: 8 }}>
          Variables
        </legend>
        {catalogue.map((variable) => {
          const on = settings.variables.includes(variable.key);
          return (
            <div key={variable.key} className="variable" data-on={on}>
              <label className="row" style={{ alignItems: "flex-start", gap: 10, cursor: "pointer" }}>
                <input type="checkbox" checked={on} onChange={() => toggle(variable.key)} />
                <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span style={{ fontWeight: 500 }}>{variable.name}</span>
                  <span className="meta">
                    {variable.product} · {variable.resolution} · {variable.cadence}
                  </span>
                </span>
              </label>
              {on && variable.scales.length > 0 && (
                <label className="row meta" style={{ justifyContent: "space-between", paddingLeft: 26 }}>
                  Time scale
                  <select
                    className="select"
                    value={settings.scale}
                    onChange={(e) => onChange({ scale: Number(e.target.value) })}
                  >
                    {variable.scales.map((months) => (
                      <option key={months} value={months}>
                        {months} {months === 1 ? "month" : "months"}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          );
        })}
      </fieldset>

      <div className="section">
        <span className="label">Period</span>
        <div style={{ display: "grid", gap: 8 }}>
          <label className="field">
            From
            <input
              type="month"
              className="input"
              value={settings.start}
              min="2000-03"
              max={settings.end}
              onChange={(e) => e.target.value && onChange({ start: e.target.value })}
            />
          </label>
          <label className="field">
            To
            <input
              type="month"
              className="input"
              value={settings.end}
              min={settings.start}
              onChange={(e) => e.target.value && onChange({ end: e.target.value })}
            />
          </label>
        </div>
      </div>

      <div className="section">
        <span className="label" id="resolution">
          Resolution
        </span>
        <div className="segmented" role="group" aria-labelledby="resolution">
          {RESOLUTIONS.map(([value, label]) => (
            <button
              key={value}
              aria-pressed={settings.resolution === value}
              onClick={() => onChange({ resolution: value })}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="section">
        <span className="label">Preparation</span>
        <label className="field">
          Cloud filter (NDVI, LST)
          <select
            className="select"
            value={settings.masking}
            onChange={(e) => onChange({ masking: e.target.value as Masking })}
          >
            {CLOUD_FILTERS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          <span className="reason">{REASONS[settings.masking]}</span>
        </label>
        <label className="row" style={{ justifyContent: "space-between", paddingTop: 6 }}>
          <span>Fill short gaps</span>
          <input type="checkbox" checked={settings.fill} onChange={(e) => onChange({ fill: e.target.checked })} />
        </label>
        {settings.fill && (
          <label className="row meta" style={{ justifyContent: "space-between" }}>
            Longest gap filled
            <select
              className="select"
              value={settings.maxGap}
              onChange={(e) => onChange({ maxGap: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 6].map((n) => (
                <option key={n} value={n}>
                  {n} {n === 1 ? "period" : "periods"}
                </option>
              ))}
            </select>
          </label>
        )}
        <span className="reason">{settings.fill ? REASONS.fill : "Gaps stay empty."}</span>
      </div>

      <p className="status" role="status" aria-live="polite">
        <span className="dot" data-busy={progress.done + progress.failed < progress.total} />
        {progress.total === 0
          ? "Nothing to load yet"
          : progress.done + progress.failed < progress.total
            ? `Loading ${progress.done + progress.failed + 1} of ${progress.total}…`
            : progress.failed
              ? `${progress.failed} of ${progress.total} failed`
              : "All results up to date"}
      </p>
    </>
  );
}
