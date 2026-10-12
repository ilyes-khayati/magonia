import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  fetchCatalogue,
  fetchSeries,
  type Masking,
  type SeriesResponse,
  type Variable,
  type VariableKey,
} from "./api";

const SATELLITE: StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: [
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    },
  },
  layers: [{ id: "satellite", type: "raster", source: "satellite" }],
};

const JENDOUBA: [number, number] = [8.561, 36.508];
const START = "2020-01-01";
const END = "2025-01-01";

type Status = "idle" | "drawing" | "loading" | "done" | "error";

// The variables themselves come from the API's catalogue; only their colours live here
const COLOURS: Record<VariableKey, string> = {
  ndvi: "#7ddc8a",
  lst: "#ffb36b",
  spei: "#6cb8ff",
};

// Axis range and decimals per variable; SPEI rarely leaves -3..3
type Axis = { domain: [number | string, number | string]; digits: number; ticks?: number[] };

const AXES: Record<VariableKey, Axis> = {
  ndvi: { domain: [0, 1], digits: 2 },
  lst: { domain: ["dataMin - 2", "dataMax + 2"], digits: 0 },
  spei: { domain: [-3, 3], digits: 0, ticks: [-3, -2, -1, 0, 1, 2, 3] },
};

const YEARS = `${START.slice(0, 4)}–${Number(END.slice(0, 4)) - 1}`;

const CLOUD_FILTERS: Record<Masking, string> = {
  pixel: "Remove cloudy pixels",
  date: "Remove cloudy dates",
  none: "No cloud filter",
};

const MESSAGES: Record<Status, string> = {
  idle: "Draw an area to see how it changes over time.",
  drawing: "Click to place points. Click the first point to close the area.",
  loading: "Asking Earth Engine…",
  done: "",
  error: "",
};

export default function App() {
  const container = useRef<HTMLDivElement>(null);
  const draw = useRef<TerraDraw | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<SeriesResponse | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [variable, setVariable] = useState<VariableKey>("ndvi");
  const [masking, setMasking] = useState<Masking>("pixel");
  const [scale, setScale] = useState(12);
  // The map's event handler is created once, so it reads the current choices from a ref
  const choices = useRef({ variable: "ndvi" as VariableKey, masking: "pixel" as Masking, scale: 12 });
  const area = useRef<unknown>(null);

  async function load(geometry: unknown) {
    const { variable, masking, scale } = choices.current;
    setStatus("loading");
    try {
      const months = variable === "spei" ? scale : null;
      setResult(await fetchSeries(geometry, START, END, variable, masking, months));
      setStatus("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }

  const [catalogue, setCatalogue] = useState<Variable[]>([]);

  useEffect(() => {
    fetchCatalogue()
      .then(setCatalogue)
      .catch((e) => {
        setError(`Could not reach the Magonia API (${e.message}).`);
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    const map = new MapLibre({
      container: container.current!,
      style: SATELLITE,
      center: JENDOUBA,
      zoom: 14,
    });
    map.on("load", () => {
      const terra = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [new TerraDrawPolygonMode()],
      });
      terra.start();
      terra.on("finish", async (id) => {
        const feature = terra.getSnapshotFeature(id);
        if (!feature) return;
        terra.setMode("static");
        area.current = feature.geometry;
        await load(feature.geometry);
      });
      draw.current = terra;
      setReady(true);
    });
    return () => map.remove();
  }, []);

  function startDrawing() {
    draw.current?.clear();
    draw.current?.setMode("polygon");
    area.current = null;
    setResult(null);
    setStatus("drawing");
  }

  function choose(change: Partial<typeof choices.current>) {
    choices.current = { ...choices.current, ...change };
    setVariable(choices.current.variable);
    setMasking(choices.current.masking);
    setScale(choices.current.scale);
    if (area.current) load(area.current);
  }

  const points = result?.points ?? [];
  const removed = points.filter((point) => point.masked).length;
  const shown = result?.variable ?? variable;
  const colour = COLOURS[shown];
  const scales = catalogue.find((entry) => entry.key === "spei")?.scales ?? [];
  const axis = AXES[shown];
  // SPEI is one grid cell, not an average over the area
  const statistic = result?.variable === "spei" ? "" : "Mean ";
  const title = result ? `${statistic}${result.name}${result.units ? ` (${result.units})` : ""}, ${YEARS}` : "";

  return (
    <>
      <div className="map-frame">
        <div ref={container} className="map" />
      </div>
      <header className="panel top">
        <h1>Magonia</h1>
        <button onClick={startDrawing} disabled={!ready || status === "loading"}>
          {status === "done" || status === "error" ? "Draw another area" : "Draw an area"}
        </button>
        <select
          aria-label="Variable"
          value={variable}
          onChange={(e) => choose({ variable: e.target.value as VariableKey })}
          disabled={status === "loading"}
        >
          {catalogue.map((entry) => (
            <option key={entry.key} value={entry.key}>
              {entry.name}
            </option>
          ))}
        </select>
        {variable === "spei" && (
          <select
            aria-label="Time scale"
            value={scale}
            onChange={(e) => choose({ scale: Number(e.target.value) })}
            disabled={status === "loading"}
          >
            {scales.map((months) => (
              <option key={months} value={months}>
                {months} {months === 1 ? "month" : "months"}
              </option>
            ))}
          </select>
        )}
        <select
          aria-label="Cloud filter"
          value={masking}
          onChange={(e) => choose({ masking: e.target.value as Masking })}
          disabled={status === "loading" || variable === "spei"}
          title={variable === "spei" ? "SPEI has no quality flags" : undefined}
        >
          {Object.entries(CLOUD_FILTERS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </header>
      <section className="panel bottom">
        <p className={status === "error" ? "error" : ""}>
          {status === "error" ? error : status === "done" ? title : MESSAGES[status]}
          {status === "done" && result?.variable !== "spei" && masking !== "none" && (
            <span className="note">
              {" "}
              · {removed} {removed === 1 ? "date" : "dates"} without usable data
            </span>
          )}
        </p>
        {status === "done" && (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={points}>
              <CartesianGrid stroke="#ffffff14" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#8a8a8a", fontSize: 11 }} minTickGap={40} />
              <YAxis
                domain={axis.domain}
                ticks={axis.ticks}
                tickFormatter={(value) => Number(value).toFixed(axis.digits)}
                tick={{ fill: "#8a8a8a", fontSize: 11 }}
                width={36}
              />
              <Tooltip
                contentStyle={{ background: "#111", border: "1px solid #333" }}
                formatter={(value) => Number(value).toFixed(axis.digits + 1)}
              />
              {shown === "spei" && <ReferenceLine y={0} stroke="#ffffff55" />}
              <Line dataKey="value" stroke={colour} dot={false} strokeWidth={1.6} />
            </LineChart>
          </ResponsiveContainer>
        )}
        {status === "done" &&
          result?.warnings.map((warning) => (
            <p key={warning} className="warning">
              {warning}
            </p>
          ))}
      </section>
    </>
  );
}
