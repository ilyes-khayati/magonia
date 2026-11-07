import { useState } from "react";
import type { Area, Masking, Resolution, Variable, VariableKey } from "../api";
import { parseMonth, speiScale, type Settings } from "../settings";
import { InfoIcon } from "./Icons";
import LearnPanel from "./LearnPanel";
import { groups } from "../variables";

type Props = {
  catalogue: Variable[];
  areas: Area[];
  settings: Settings;
  onChange: (change: Partial<Settings>) => void;
  progress: { done: number; total: number; failed: number };
};

// A month field. Where the browser has no month picker it is a plain text box, so the
// text is kept as typed and only a readable month reaches the settings.
function MonthField({ label, value, min, max, onChange }: {
  label: string;
  value: string;
  min?: string;
  max?: string;
  onChange: (month: string) => void;
}) {
  const [text, setText] = useState(value);
  const [shown, setShown] = useState(value);
  // a change from elsewhere (undo, another workspace) replaces the text, unless it is
  // the month the text already reads as
  if (value !== shown) {
    setShown(value);
    if (parseMonth(text) !== value) setText(value);
  }
  const valid = parseMonth(text) !== null;
  return (
    <label className="field">
      {label}
      <input
        type="month"
        className="input"
        value={text}
        min={min}
        max={max}
        placeholder="YYYY-MM"
        aria-invalid={!valid}
        onChange={(e) => {
          setText(e.target.value);
          const month = parseMonth(e.target.value);
          if (month) onChange(month);
        }}
        onBlur={() => setText(value)}
      />
      {!valid && <span className="reason">Type a month as YYYY-MM, for example 2020-01.</span>}
    </label>
  );
}

const Scales = ({ scales }: { scales: number[] }) =>
  scales.map((months) => (
    <option key={months} value={months}>
      {months} {months === 1 ? "month" : "months"}
    </option>
  ));

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

// Time left, from how long the series done so far took; only once one is done
const started = { at: 0, from: 0 };
function eta(progress: Props["progress"]): string | null {
  const finished = progress.done + progress.failed;
  const now = performance.now();
  if (finished === 0 || started.at === 0 || finished < started.from) {
    started.at = now;
    started.from = finished;
    return null;
  }
  const each = (now - started.at) / Math.max(1, finished - started.from);
  if (finished === started.from) return null;
  const left = Math.round((each * (progress.total - finished)) / 1000);
  return left > 1 ? ` · about ${left < 60 ? `${left} s` : `${Math.round(left / 60)} min`} left` : null;
}

export default function DataPanel({ catalogue, areas, settings, onChange, progress }: Props) {
  const [open, setOpen] = useState<VariableKey | null>(null);
  function toggle(key: VariableKey) {
    const on = settings.variables.includes(key);
    // keep the catalogue order whatever the order of clicks
    const next = catalogue.map((v) => v.key).filter((k) => (k === key ? !on : settings.variables.includes(k)));
    onChange({ variables: next });
  }

  // An area keeps its own scale only where it differs from the one for all areas
  function setScale(scale: number) {
    const own = Object.entries(settings.scaleByArea).filter(([id, s]) => s !== scale && areas.some((a) => a.id === Number(id)));
    onChange({ scale, scaleByArea: Object.fromEntries(own) });
  }
  function setAreaScale(areaId: number, scale: number) {
    const { [areaId]: _, ...rest } = settings.scaleByArea;
    onChange({ scaleByArea: scale === settings.scale ? rest : { ...rest, [areaId]: scale } });
  }

  return (
    <>
      <div className="section">
        <span className="label">Period</span>
        <div className="period-fields">
          <MonthField label="From" value={settings.start} min="2000-03" max={settings.end} onChange={(start) => onChange({ start })} />
          <MonthField label="To" value={settings.end} min={settings.start} onChange={(end) => onChange({ end })} />
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

      {progress.done + progress.failed < progress.total && (
        <div className="progress" aria-hidden="true">
          <div style={{ width: `${(100 * (progress.done + progress.failed)) / progress.total}%` }} />
        </div>
      )}
      <p className="status top-status" role="status" aria-live="polite">
        <span className="dot" data-busy={progress.done + progress.failed < progress.total} />
        {progress.total === 0
          ? "Nothing to load yet"
          : progress.done + progress.failed < progress.total
            ? `Extracting ${progress.done + progress.failed + 1} of ${progress.total} series from Earth Engine${eta(progress) ?? ""}`
            : progress.failed
              ? `${progress.failed} of ${progress.total} failed`
              : "All results up to date"}
      </p>
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
                  <div className="variable-row">
                    <label className="variable-label" title={`${variable.product} · ${variable.resolution} · ${variable.cadence}`}>
                      <input type="checkbox" checked={on} onChange={() => toggle(variable.key)} />
                      <span className="variable-text">
                        <span className="variable-name">{variable.name}</span>
                        <span className="visually-hidden">{variable.product}</span>
                        <span className="variable-spec">
                          {variable.resolution} · {variable.cadence === "monthly" ? "monthly" : `every ${variable.cadence}`}
                        </span>
                      </span>
                    </label>
                    {variable.learn && (
                      <button
                        className="icon-button bare"
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
                    <>
                      <label className="row meta" style={{ justifyContent: "space-between", paddingLeft: 26 }}>
                        Time scale
                        <select className="select" value={settings.scale} onChange={(e) => setScale(Number(e.target.value))}>
                          <Scales scales={variable.scales} />
                        </select>
                      </label>
                      {areas.length > 1 && (
                        <details className="per-area" open={Object.keys(settings.scaleByArea).length > 0}>
                          <summary className="meta">A different scale for an area</summary>
                          {areas.map((area) => (
                            <label key={area.id} className="row meta" style={{ justifyContent: "space-between" }}>
                              {area.name}
                              <select
                                className="select"
                                value={speiScale(settings, area.id)}
                                onChange={(e) => setAreaScale(area.id, Number(e.target.value))}
                              >
                                <Scales scales={variable.scales} />
                              </select>
                            </label>
                          ))}
                        </details>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </fieldset>

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

    </>
  );
}
