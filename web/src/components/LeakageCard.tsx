import type { Leakage } from "../analyses";
import { leakageOf, type LeakageBody, type SeriesOptions, type Variable, type VariableKey } from "../api";
import { areaColour, type Theme } from "../theme";
import { num, oneArea } from "../format";
import { TimeChart } from "../plot/Chart";
import { dateOf } from "../plot/time";
import { useAnalysis } from "../useAnalysis";
import { large } from "../variables";
import type { Entry } from "./ChartCard";
import CardTitle from "./CardTitle";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Leakage;
  onChange: (change: Partial<Leakage>) => void;
  onRemove: () => void;
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
  seasonal: boolean;
};

const LABEL: Record<string, string> = { Ridge: "Ridge", RandomForest: "Random Forest", XGBoost: "XGBoost" };

// The same wavelet-hybrid forecast twice: parts from the whole record, as usually published, and
// parts from the past only, as a forecast made at the time would have them
export default function LeakageCard({ analysis, onChange, onRemove, variables, title, entries, options, seasonal }: Props) {
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const areas = entries(analysis.response).map((e) => e.area);
  const areaId = areas.some((a) => a.id === analysis.area) ? analysis.area! : (areas[0]?.id ?? null);
  const ready = entries(analysis.response).find((e) => e.area.id === areaId)?.state?.status === "done";
  const body: LeakageBody | null = areaId !== null && ready && !seasonal ? { response: options(areaId, analysis.response), test_years: analysis.test_years } : null;
  const signature = JSON.stringify(body);
  const requests = signature === "null" ? [] : [{ key: signature, body: JSON.parse(signature) as LeakageBody }];
  const result = useAnalysis(requests, leakageOf).get(signature);
  const found = result?.status === "done" ? result.data : null;
  const theme = (document.documentElement.dataset.theme as Theme) ?? "light";
  const digits = large(analysis.response) ? 2 : 4;

  const at = found?.dates.map((d) => dateOf(`${d}-01`)) ?? [];
  const series = found
    ? [
        { id: "observed", name: "Observed", colour: "var(--ink)", width: 2, points: at.map((date, i) => ({ date, value: found.observed[i] })) },
        { id: "whole", name: "Parts from the whole record", colour: areaColour(theme, 1), width: 1.3, dashed: true, points: at.map((date, i) => ({ date, value: found.whole[i] })) },
        { id: "causal", name: "Parts from the past only", colour: areaColour(theme, 0), width: 1.3, points: at.map((date, i) => ({ date, value: found.causal[i] })) },
      ]
    : [];

  return (
    <section className="card" aria-label="Leakage audit">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Wavelet leakage audit" onRename={(n) => onChange({ name: n })} />
          <span className="meta">
            {name(analysis.response)} one month ahead, each wavelet part forecast from lags of the parts and added back, with
            the parts decomposed over the whole record and from the past only
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      <div className="drivers">
        <label className="field">
          Variable
          <select className="select" value={analysis.response} onChange={(e) => onChange({ response: e.target.value as VariableKey })}>
            {variables.map((v) => (
              <option key={v.key} value={v.key}>
                {title(v)}
              </option>
            ))}
          </select>
        </label>
        {areas.length > 1 && (
          <label className="field">
            Area
            <select className="select" value={areaId ?? ""} onChange={(e) => onChange({ area: Number(e.target.value) })}>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="field">
          Test years
          <select className="select" value={analysis.test_years} onChange={(e) => onChange({ test_years: Number(e.target.value) })}>
            {[2, 3, 4, 5].map((y) => (
              <option key={y} value={y}>
                last {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      {seasonal ? (
        <p className="placeholder">The audit needs monthly values. Change the time step on the left to native or monthly.</p>
      ) : result?.status === "failed" ? (
        <p className="placeholder">{result.error}</p>
      ) : !found ? (
        <p className="placeholder" role="status">
          {body ? "Decomposing every month from its past, then fitting each model both ways…" : `Waiting for ${name(analysis.response)} to load.`}
        </p>
      ) : (
        <>
          <div className="table-scroll" tabIndex={0}>
            <table className="stats">
              <caption className="visually-hidden">Skill with the parts decomposed both ways</caption>
              <thead>
                <tr>
                  <th scope="col">Model</th>
                  <th scope="col" title="R² of the trend part's forecast">Trend R², whole</th>
                  <th scope="col">Trend R², past only</th>
                  <th scope="col" title={`Error on ${name(analysis.response)} itself`}>RMSE, whole</th>
                  <th scope="col">RMSE, past only</th>
                  <th scope="col" title="Lags of the series, no decomposition">RMSE, plain lags</th>
                </tr>
              </thead>
              <tbody>
                {found.rows.map((r) => (
                  <tr key={r.model}>
                    <th scope="row">{LABEL[r.model] ?? r.model}</th>
                    <td>{num(r.trend_whole, 2)}</td>
                    <td>{num(r.trend_causal, 2)}</td>
                    <td>{num(r.whole, digits)}</td>
                    <td>{num(r.causal, digits)}</td>
                    <td>{num(r.raw, digits)}</td>
                  </tr>
                ))}
                <tr className="baseline">
                  <th scope="row">White noise (placebo)</th>
                  <td>{num(found.placebo.whole, 2)}</td>
                  <td>{num(found.placebo.causal, 2)}</td>
                  <td />
                  <td />
                  <td />
                </tr>
                <tr className="baseline">
                  <th scope="row">Persistence · climatology</th>
                  <td />
                  <td />
                  <td colSpan={3}>
                    {num(found.baselines.persistence, digits)} · {num(found.baselines.climatology, digits)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <span className="meta">
            Test period {found.test[0]} to {found.test[1]}: {LABEL[found.best] ?? found.best}&apos;s forecasts both ways
          </span>
          <TimeChart title="Leakage audit" series={series} height={200} y={{ label: name(analysis.response), digits: digits > 2 ? 2 : 1 }} linked={false} />
          <div className="legend">
            {series.map((s) => (
              <span key={s.id} className="row" style={{ gap: 6 }}>
                <span className="swatch" style={{ background: s.colour }} />
                {s.name}
              </span>
            ))}
          </div>
          <ul className="summary">
            {oneArea(found.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <span className="meta">
            A forecast made at the time could only have decomposed the months before it. Whatever a whole-record score has
            on top of the past-only one came from later data.
          </span>
        </>
      )}
    </section>
  );
}
