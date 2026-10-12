import { useEffect, useRef, useState } from "react";
import { Map as MapLibre, type GeoJSONSource, type LngLatBoundsLike } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { TerraDraw, TerraDrawPolygonMode, TerraDrawRectangleMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { BASEMAPS, baseStyle, type Basemap } from "../basemaps";
import { LayersIcon } from "./Icons";

export type Tool = "polygon" | "rectangle" | null;

export type MapArea = { id: number; geometry: GeoJSON.Geometry; colour: string };

// Where the map should move to; `key` changes to repeat the same move
export type Target = { key: number; center?: [number, number]; bounds?: LngLatBoundsLike };

type Props = {
  areas: MapArea[];
  tool: Tool;
  target: Target | null;
  onDrawn: (geometry: GeoJSON.Polygon) => void;
  focus: boolean;
  onFocus: () => void;
};

const JENDOUBA: [number, number] = [8.561, 36.508];

export default function MapView({ areas, tool, target, onDrawn, focus, onFocus }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibre | null>(null);
  const draw = useRef<TerraDraw | null>(null);
  const drawn = useRef(onDrawn);
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [choosing, setChoosing] = useState(false);

  // The draw handler is registered once, so it calls the latest onDrawn through a ref
  useEffect(() => {
    drawn.current = onDrawn;
  }, [onDrawn]);

  useEffect(() => {
    const instance = new MapLibre({
      container: container.current!,
      style: baseStyle("satellite"),
      center: JENDOUBA,
      zoom: 14,
    });
    instance.on("load", () => {
      instance.addSource("areas", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      instance.addLayer({
        id: "areas-fill",
        type: "fill",
        source: "areas",
        paint: { "fill-color": ["get", "colour"], "fill-opacity": 0.18 },
      });
      instance.addLayer({
        id: "areas-line",
        type: "line",
        source: "areas",
        paint: { "line-color": ["get", "colour"], "line-width": 2.5 },
      });

      const terra = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map: instance }),
        modes: [new TerraDrawPolygonMode(), new TerraDrawRectangleMode()],
      });
      terra.start();
      terra.on("finish", (id) => {
        const feature = terra.getSnapshotFeature(id);
        terra.clear();
        if (feature?.geometry.type === "Polygon") drawn.current(feature.geometry);
      });
      draw.current = terra;
      setReady(true);
    });
    map.current = instance;
    return () => instance.remove();
  }, []);

  useEffect(() => {
    if (!ready) return;
    const source = map.current!.getSource("areas") as GeoJSONSource;
    source.setData({
      type: "FeatureCollection",
      features: areas.map((area) => ({
        type: "Feature",
        id: area.id,
        properties: { colour: area.colour },
        geometry: area.geometry,
      })),
    });
  }, [areas, ready]);

  useEffect(() => {
    if (!ready) return;
    draw.current!.setMode(tool ?? "static");
  }, [tool, ready]);

  // The map must re-measure itself when the side panels open or close
  useEffect(() => {
    const timer = window.setTimeout(() => map.current?.resize(), 50);
    return () => window.clearTimeout(timer);
  }, [focus]);

  useEffect(() => {
    if (!ready || !target) return;
    if (target.bounds) map.current!.fitBounds(target.bounds, { padding: 80, maxZoom: 16 });
    else if (target.center) map.current!.flyTo({ center: target.center, zoom: 14 });
  }, [target, ready]);

  function chooseBasemap(next: Basemap) {
    for (const key of Object.keys(BASEMAPS)) {
      map.current?.setLayoutProperty(key, "visibility", key === next ? "visible" : "none");
    }
    setBasemap(next);
    setChoosing(false);
  }

  return (
    <>
      {/* MapLibre's own CSS sets the map's position, so a wrapper does the placing */}
      <div className="map-frame">
        <div ref={container} className="map" data-ready={ready} />
      </div>
      <div className="corner">
        {choosing && (
          <div className="floating basemaps" role="group" aria-label="Basemap">
            {(Object.keys(BASEMAPS) as Basemap[]).map((key) => (
              <button key={key} aria-pressed={key === basemap} onClick={() => chooseBasemap(key)}>
                {BASEMAPS[key].label}
              </button>
            ))}
          </div>
        )}
        <button
          className="floating button"
          aria-pressed={focus}
          title={focus ? "Show the panels again" : "Hide the panels and show only the map"}
          onClick={onFocus}
        >
          {focus ? "Show panels" : "Focus map"}
        </button>
        <div className="floating zoom">
          <button aria-label="Zoom in" onClick={() => map.current?.zoomIn()}>
            +
          </button>
          <button aria-label="Zoom out" onClick={() => map.current?.zoomOut()}>
            −
          </button>
        </div>
        <button
          className="floating button row"
          aria-expanded={choosing}
          onClick={() => setChoosing(!choosing)}
        >
          <LayersIcon size={16} />
          {BASEMAPS[basemap].label}
        </button>
      </div>
    </>
  );
}
