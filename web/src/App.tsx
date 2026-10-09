import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchSeries, type SeriesPoint } from "./api";

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

const MESSAGES: Record<Status, string> = {
  idle: "Draw an area to see its vegetation.",
  drawing: "Click to place points. Click the first point to close the area.",
  loading: "Asking Earth Engine…",
  done: `Mean NDVI, MODIS 250 m, ${START.slice(0, 4)}–${Number(END.slice(0, 4)) - 1}`,
  error: "",
};

export default function App() {
  const container = useRef<HTMLDivElement>(null);
  const draw = useRef<TerraDraw | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);

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
        setStatus("loading");
        try {
          setSeries(await fetchSeries(feature.geometry, START, END));
          setStatus("done");
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          setStatus("error");
        }
      });
      draw.current = terra;
      setReady(true);
    });
    return () => map.remove();
  }, []);

  function startDrawing() {
    draw.current?.clear();
    draw.current?.setMode("polygon");
    setSeries([]);
    setStatus("drawing");
  }

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
      </header>
      <section className="panel bottom">
        <p className={status === "error" ? "error" : ""}>
          {status === "error" ? error : MESSAGES[status]}
        </p>
        {status === "done" && (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={series}>
              <CartesianGrid stroke="#ffffff14" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: "#8a8a8a", fontSize: 11 }} minTickGap={40} />
              <YAxis domain={[0, 1]} tick={{ fill: "#8a8a8a", fontSize: 11 }} width={32} />
              <Tooltip
                contentStyle={{ background: "#111", border: "1px solid #333" }}
                formatter={(value) => Number(value).toFixed(3)}
              />
              <Line dataKey="ndvi" stroke="#7ddc8a" dot={false} strokeWidth={1.6} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        )}
      </section>
    </>
  );
}
