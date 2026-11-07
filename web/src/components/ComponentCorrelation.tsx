import { decomposeSeries, type SeriesOptions, type SeriesPoint, type VariableKey } from "../api";
import { lagCorrelation, strongest } from "../correlation";
import { num } from "../format";
import { useAnalysis } from "../useAnalysis";
import type { Entry } from "./ChartCard";

type Props = {
  response: VariableKey;
  driver: VariableKey;
  name: (key: VariableKey) => string;
  native: (variable: VariableKey) => Entry[]; // each variable at its product's own time step
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
};

const PARTS = [
  { key: "value", label: "Original" },
  { key: "trend", label: "Trend" },
  { key: "seasonal", label: "Seasonal" },
] as const;

type Part = (typeof PARTS)[number]["key"];

// A decomposed part as the monthly correlation reads it: one value per date, nothing filled
const asSeries = (points: { date: string; value: number | null; trend: number | null; seasonal: number | null }[], part: Part) =>
  points.map((p) => ({ date: p.date, value: p[part], sd: null, n_pixels: 1, masked: p[part] === null, filled: false })) as SeriesPoint[];

const requestsOf = (signature: string) =>
  (JSON.parse(signature) as SeriesOptions[]).map((o) => ({ key: JSON.stringify(o), body: o }));

// Each variable decomposed at its own time step, then its original, trend and seasonal parts
// correlated month by month at lags 0 to 12: which part carries the relationship
export default function ComponentCorrelation({ response, driver, name, native, options }: Props) {
  const drivers = native(driver);
  const ready = native(response)
    .filter((e) => e.state?.status === "done" && drivers.find((d) => d.area.id === e.area.id)?.state?.status === "done")
    .map((e) => e.area);
  const signature = JSON.stringify(ready.flatMap((a) => [options(a.id, response), options(a.id, driver)]));
  // asked once each: the hook skips requests it has already started
  const requests = requestsOf(signature);
  const results = useAnalysis(requests, decomposeSeries);

  const rows = ready.flatMap((area) => {
    const a = results.get(JSON.stringify(options(area.id, response)));
    const b = results.get(JSON.stringify(options(area.id, driver)));
    if (a?.status !== "done" || b?.status !== "done") return [];
    return PARTS.map(({ key, label }) => {
      const lags = lagCorrelation(asSeries(a.data.points, key), asSeries(b.data.points, key), 12, false);
      const top = strongest(lags);
      const zero = lags.find((l) => l.lag === 0);
      return { area: area.name, label, zero, top };
    });
  });
  const waiting = ready.length * 2 > [...results.values()].filter((r) => r.status === "done").length;

  return (
    <div className="table-scroll" tabIndex={0}>
      <table className="stats">
        <caption className="meta" style={{ textAlign: "left", captionSide: "top", paddingBottom: 4 }}>
          {name(response)} against {name(driver)}, part by part (wavelet decomposition at each product&apos;s own time step,
          then monthly)
        </caption>
        <thead>
          <tr>
            <th scope="col">Area</th>
            <th scope="col">Part</th>
            <th scope="col">r, same month</th>
            <th scope="col">Strongest lag</th>
            <th scope="col">r there</th>
            <th scope="col" title="Approximate 95% limit for no correlation">± chance</th>
            <th scope="col">n</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.area}-${r.label}`}>
              <th scope="row">{r.label === "Original" ? r.area : ""}</th>
              <td style={{ textAlign: "left" }}>{r.label}</td>
              <td>{num(r.zero?.r, 2)}</td>
              <td>{r.top ? `${r.top.lag} mo` : "–"}</td>
              <td>{num(r.top?.r, 2)}</td>
              <td>{num(r.top?.band, 2)}</td>
              <td>{r.top?.n ?? "–"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {waiting && (
        <p className="meta" role="status">
          Decomposing {name(response)} and {name(driver)} at their own time steps…
        </p>
      )}
      <p className="meta">
        Trend and seasonal parts are smooth, so their correlations look stronger than the same number would between raw
        series; the ± chance limit ignores this and is optimistic for them.
      </p>
    </div>
  );
}
