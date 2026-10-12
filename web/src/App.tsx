import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchSeries, type Masking, type SeriesResponse, type VariableKey } from "./api";

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

const VARIABLES: Record<VariableKey, { label: string; colour: string }> = {
  ndvi: { label: "NDVI", colour: "#7ddc8a" },
  lst: { label: "Land surface temperature", colour: "#ffb36b" },
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
  // The map's event handler is created once, so it reads the current choices from a ref
  const choices = useRef({ variable: "ndvi" as VariableKey, masking: "pixel" as Masking });
  const area = useRef<unknown>(null);

  async function load(geometry: unknown) {
    const { variable, masking } = choices.current;
    setStatus("loading");
    try {
      setResult(await fetchSeries(geometry, START, END, variable, masking));
      setStatus("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("error");
    }
  }

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
    if (area.current) load(area.current);
  }

  const points = result?.points ?? [];
  const removed = points.filter((point) => point.masked).length;
  const colour = VARIABLES[result?.variable ?? variable].colour;
  const title = result ? `Mean ${result.name}${result.units ? ` (${result.units})` : ""}, ${YEARS}` : "";

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
          {Object.entries(VARIABLES).map(([value, { label }]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Cloud filter"
          value={masking}
          onChange={(e) => choose({ masking: e.target.value as Masking })}
          disabled={status === "loading"}
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
          {status === "done" && masking !== "none" && (
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
                domain={result?.variable === "ndvi" ? [0, 1] : ["dataMin - 2", "dataMax + 2"]}
                tickFormatter={(value) => Number(value).toFixed(result?.variable === "ndvi" ? 2 : 0)}
                tick={{ fill: "#8a8a8a", fontSize: 11 }}
                width={36}
              />
              <Tooltip
                contentStyle={{ background: "#111", border: "1px solid #333" }}
                formatter={(value) => Number(value).toFixed(result?.variable === "ndvi" ? 3 : 1)}
              />
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
