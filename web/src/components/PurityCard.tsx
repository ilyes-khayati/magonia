import * as Plot from "@observablehq/plot";
import type { Purity } from "../analyses";
import { areaPurity, type Area, type PurityPixel, type PurityResponse } from "../api";
import { num, oneArea } from "../format";
import { PlotFrame } from "../plot/Chart";
import { MONTHS } from "../stats";
import { useAnalysis } from "../useAnalysis";
import CardTitle from "./CardTitle";
import { CloseIcon } from "./Icons";

type Props = {
  analysis: Purity;
  onChange: (change: Partial<Purity>) => void;
  onRemove: () => void;
  areas: Area[];
  start: string; // "YYYY-MM"
  end: string;
};

// perennial green to annual-crop brown, through a pale middle that reads as "mixed"
const SHARE = ["#1b7837", "#a6dba0", "#f7f7f7", "#dfc27d", "#8c510a"];

// d3's spherical drawing reads a counter-clockwise ring as "everything but this"; GeoJSON's
// convention is the opposite, so rings are turned clockwise before drawing
function clockwise(ring: number[][]): number[][] {
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i++) sum += (ring[i + 1][0] - ring[i][0]) * (ring[i + 1][1] + ring[i][1]);
  return sum < 0 ? [...ring].reverse() : ring;
}

function forDrawing(geometry: GeoJSON.Geometry): GeoJSON.Geometry {
  if (geometry.type === "Polygon") return { ...geometry, coordinates: geometry.coordinates.map(clockwise) };
  if (geometry.type === "MultiPolygon") return { ...geometry, coordinates: geometry.coordinates.map((p) => p.map(clockwise)) };
  return geometry;
}

// One MODIS pixel as a square on the ground, for drawing: its centre and side
function square(p: PurityPixel, side: number): GeoJSON.Feature {
  const dLat = side / 2 / 111_320;
  const dLon = dLat / Math.cos((p.lat * Math.PI) / 180);
  return {
    type: "Feature",
    properties: p,
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          // clockwise, as d3 draws it
          [p.lon - dLon, p.lat - dLat],
          [p.lon - dLon, p.lat + dLat],
          [p.lon + dLon, p.lat + dLat],
          [p.lon + dLon, p.lat - dLat],
          [p.lon - dLon, p.lat - dLat],
        ],
      ],
    },
  };
}

function maps(found: PurityResponse, area: Area): Plot.PlotOptions {
  const cells = { type: "FeatureCollection", features: found.pixels.map((p) => square(p, found.pixel_m)) } as GeoJSON.FeatureCollection;
  return {
    projection: { type: "mercator", domain: cells },
    color: { domain: [0, 1], range: SHARE, interpolate: "rgb" },
    marks: [
      Plot.geo(cells, { fill: (f: GeoJSON.Feature) => (f.properties as PurityPixel).share, stroke: "var(--card)", strokeWidth: 0.4 }),
      Plot.geo(cells.features.filter((f) => (f.properties as PurityPixel).inside), { fill: "none", stroke: "currentColor", strokeWidth: 0.8 }),
      Plot.geo(forDrawing(area.geometry), { fill: "none", stroke: "black", strokeWidth: 2.2 }),
      Plot.tip(
        found.pixels,
        Plot.pointer({
          x: "lon",
          y: "lat",
          title: (p: PurityPixel) => `${Math.round(p.share * 100)}% annual crop\nswing ${num(p.amplitude, 2)} over the year\n${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}`,
        }),
      ),
    ],
  };
}

function cycles(found: PurityResponse): Plot.PlotOptions {
  const rows = [
    ...found.seasonal.map((v, m) => ({ m, v, which: "Most seasonal nearby (annual crop)" })),
    ...found.perennial.map((v, m) => ({ m, v, which: "Most even nearby (perennial)" })),
    ...found.area_cycle.map((v, m) => ({ m, v, which: "The area's pixels" })),
  ];
  return {
    x: { domain: [0, 11], ticks: 12, tickFormat: (m: number) => MONTHS[m] ?? "", label: null },
    y: { label: "NDVI", labelArrow: "none", grid: true, tickFormat: (v: number) => num(v, 1) },
    color: { domain: ["Most seasonal nearby (annual crop)", "Most even nearby (perennial)", "The area's pixels"], range: [SHARE[4], SHARE[0], "currentColor"] },
    marks: [
      Plot.lineY(rows.filter((r) => r.which !== "The area's pixels"), { x: "m", y: "v", z: "which", stroke: "which", strokeWidth: 1.5, strokeDasharray: "4 3" }),
      Plot.lineY(rows.filter((r) => r.which === "The area's pixels"), { x: "m", y: "v", stroke: "which", strokeWidth: 2.4 }),
      Plot.dot(rows, { x: "m", y: "v", fill: "which", r: 2 }),
    ],
  };
}

// How much of each pixel over and around the area is annual crop: an area mean is only as
// pure as the pixels it is made of
export default function PurityCard({ analysis, onChange, onRemove, areas, start, end }: Props) {
  const area = areas.find((a) => a.id === analysis.area) ?? areas[0];
  const body = area ? { area: area.id, start, end } : null;
  const signature = JSON.stringify(body);
  const requests = body ? [{ key: signature, body }] : [];
  const result = useAnalysis(requests, areaPurity).get(signature);
  const found = result?.status === "done" ? result.data : null;

  return (
    <section className="card" aria-label="Pixel purity">
      <div className="card-head">
        <div>
          <CardTitle name={analysis.name} fallback="Pixel purity" onRename={(n) => onChange({ name: n })} />
          <span className="meta">
            Each MODIS NDVI pixel&apos;s average year ({start.slice(0, 4)}–{end.slice(0, 4)}) split between the most seasonal and the
            most even vegetated pixels within 1.5 km (temporal unmixing)
          </span>
        </div>
        <button className="icon-button" aria-label="Remove this analysis" title="Remove this analysis" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>

      {areas.length > 1 && (
        <div className="drivers">
          <label className="field">
            Area
            <select className="select" value={area?.id ?? ""} onChange={(e) => onChange({ area: Number(e.target.value) })}>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {!area ? (
        <p className="placeholder">Draw or upload an area on the map first.</p>
      ) : result?.status === "failed" ? (
        <p className="placeholder">{result.error}</p>
      ) : !found ? (
        <p className="placeholder" role="status">
          Reading every pixel around {area.name} from Earth Engine…
        </p>
      ) : (
        <>
          <div className="purity-figures">
            <PlotFrame title={`Pixel purity of ${area.name}`} options={maps(found, area)} height={260} />
            <PlotFrame title={`Average years around ${area.name}`} options={cycles(found)} height={260} />
          </div>
          <div className="coherence-key">
            <span className="ramp" style={{ background: `linear-gradient(to right, ${SHARE.join(", ")})` }} />
            <span className="meta">0 → 100% annual crop</span>
            <span className="meta">Thick outline: the area. Thin outlines: its own pixels. Dashed: the two references.</span>
          </div>
          <ul className="summary">
            {oneArea(found.summary).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
