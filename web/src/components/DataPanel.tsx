import { useState } from "react";
import type { Masking, Resolution, Variable, VariableKey } from "../api";
import type { Settings } from "../settings";
import { InfoIcon } from "./Icons";
import LearnPanel from "./LearnPanel";
import { groups } from "../variables";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  progress: { done: number; total: number; failed: number };
};

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

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
  const [open, setOpen] = useState<VariableKey | null>(null);
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
        {groups(catalogue).map(([group, variables]) => (
          <div key={group} className="variable-group">
            <span className="meta group-name">{group}</span>
            {variables.map((variable) => {
              const on = settings.variables.includes(variable.key);
              return (
                <div key={variable.key} className="variable" data-on={on}>
                  <div className="row" style={{ alignItems: "flex-start", gap: 6, justifyContent: "space-between" }}>
                    <label className="row" style={{ alignItems: "flex-start", gap: 10, cursor: "pointer" }}>
                      <input type="checkbox" checked={on} onChange={() => toggle(variable.key)} />
                      <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <span style={{ fontWeight: 500 }}>{variable.name}</span>
                        <span className="meta">
                          {variable.product} · {variable.resolution} · {variable.cadence}
                        </span>
                      </span>
                    </label>
                    {variable.learn && (
                      <button
                        className="icon-button round"
                        aria-label={`About ${variable.name}`}
                        title={`About ${variable.name}`}
                        aria-expanded={open === variable.key}
                        onClick={() => setOpen(open === variable.key ? null : variable.key)}
                      >
                        <InfoIcon size={13} />
                      </button>
                    )}
                  </div>
                  {open === variable.key && <LearnPanel variable={variable} />}
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
          </div>
        ))}
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

      <fieldset className="section display-options">
        <legend className="label">Show on the charts</legend>
        <label className="row" style={{ justifyContent: "space-between" }}>
          <span>Smooth</span>
          <input
            type="checkbox"
            checked={settings.display.smooth}
            onChange={(e) => onChange({ display: { ...settings.display, smooth: e.target.checked } })}
          />
        </label>
        <span className="reason">Savitzky–Golay over 5 steps: removes noise, keeps peaks in place.</span>
        <label className="row" style={{ justifyContent: "space-between" }}>
          <span>Anomalies</span>
          <input
            type="checkbox"
            checked={settings.display.anomaly !== null}
            onChange={(e) => {
              const from = Number(settings.start.slice(0, 4));
              const to = Math.min(from + 9, Number(settings.end.slice(0, 4)));
              onChange({ display: { ...settings.display, anomaly: e.target.checked ? { from, to } : null } });
            }}
          />
        </label>
        {settings.display.anomaly && (
          <div className="row" style={{ gap: 8 }}>
            <label className="field" style={{ flex: 1 }}>
              Reference from
              <input
                className="input"
                type="number"
                min={2000}
                max={settings.display.anomaly.to}
                value={settings.display.anomaly.from}
                onChange={(e) => onChange({ display: { ...settings.display, anomaly: { ...settings.display.anomaly!, from: Number(e.target.value) } } })}
              />
            </label>
            <label className="field" style={{ flex: 1 }}>
              to
              <input
                className="input"
                type="number"
                min={settings.display.anomaly.from}
                max={2100}
                value={settings.display.anomaly.to}
                onChange={(e) => onChange({ display: { ...settings.display, anomaly: { ...settings.display.anomaly!, to: Number(e.target.value) } } })}
              />
            </label>
          </div>
        )}
        <span className="reason">Each value minus the mean of its month over the reference years.</span>
        <span className="label" id="months-shown">
          Months
        </span>
        <div className="months" role="group" aria-labelledby="months-shown">
          {["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"].map((letter, i) => {
            const m = i + 1;
            const all = settings.display.months.length === 0;
            const on = all || settings.display.months.includes(m);
            return (
              <button
                key={m}
                aria-pressed={on}
                aria-label={MONTH_NAMES[i]}
                title={MONTH_NAMES[i]}
                onClick={() => {
                  const current = all ? Array.from({ length: 12 }, (_, k) => k + 1) : settings.display.months;
                  const next = on ? current.filter((x) => x !== m) : [...current, m].sort((a, b) => a - b);
                  onChange({ display: { ...settings.display, months: next.length === 12 || next.length === 0 ? [] : next } });
                }}
              >
                {letter}
              </button>
            );
          })}
        </div>
        <span className="reason">
          {settings.display.months.length ? "Only the months pressed are shown." : "All months are shown; press one to leave it out."}
        </span>
      </fieldset>

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
