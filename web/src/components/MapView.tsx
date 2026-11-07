import { useCallback, useEffect, useRef, useState } from "react";
import { Map as MapLibre, ScaleControl, type GeoJSONSource, type LngLatBoundsLike, type RasterTileSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  TerraDraw,
  TerraDrawLineStringMode,
  TerraDrawModeUndoRedo,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
  TerraDrawUndoRedoKeyboardShortcuts,
  type SnappableContext,
  type TerraDrawMouseEvent,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";
import { areaPixels, layerTiles, type Tiles, type VariableKey } from "../api";
import { BASEMAPS, baseStyle, type Basemap } from "../basemaps";
import { coordinate, distance, surface } from "../format";
import { area as areaOf, length } from "../geo";
import ContextMenu, { type MenuItem } from "./ContextMenu";

export type Tool = "polygon" | "rectangle" | "measure" | "inspect" | null;

export type MapArea = { id: number; geometry: GeoJSON.Geometry; colour: string };

// Where the map should move to; `key` changes to repeat the same move
export type Target = { key: number; center?: [number, number]; bounds?: LngLatBoundsLike; zoom?: number };

// A variable drawn over the basemap for one month
export type Layer = { variable: VariableKey; scale?: number; opacity: number };

export type View = { center: [number, number]; zoom: number };

type Props = {
  areas: MapArea[];
  tool: Tool;
  target: Target | null;
  onDrawn: (geometry: GeoJSON.Polygon) => void;
  onInspect: (lngLat: [number, number]) => void;
  inspected: [number, number] | null;
  focus: boolean;
  onFocus: () => void;
  visible: boolean; // the map stays loaded while another page is open
  layer: Layer | null;
  month: string | null;
  compare: string | null; // the month on the right of the swipe divider
  grid: VariableKey | null; // whose pixels are outlined over the areas
  onTiles: (tiles: Tiles | null, error?: string) => void;
  onView: (view: View) => void;
  onFit: () => void;
};

const JENDOUBA: [number, number] = [8.561, 36.508];
const INK = "#111827";

// Small, crisp handles: precise points, not blobs
const HANDLES = {
  coordinatePointWidth: 3,
  coordinatePointColor: "#ffffff",
  coordinatePointOutlineWidth: 1.5,
  coordinatePointOutlineColor: INK,
  closingPointWidth: 4,
  closingPointColor: "#ffffff",
  closingPointOutlineWidth: 2,
  closingPointOutlineColor: INK,
  snappingPointWidth: 4,
  snappingPointColor: "#ffd60a",
  snappingPointOutlineWidth: 1.5,
  snappingPointOutlineColor: INK,
  outlineColor: "#ffd60a",
  outlineWidth: 1.5,
  fillColor: "#ffd60a",
  fillOpacity: 0.12,
} as const;

type Live = { kind: "polygon" | "line"; metres: number; m2: number; last: number } | null;

export default function MapView(props: Props) {
  const { areas, tool, target, onDrawn, focus, onFocus, visible, layer, month, compare, grid, onTiles, onView } = props;
  const container = useRef<HTMLDivElement>(null);
  const other = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibre | null>(null);
  const right = useRef<MapLibre | null>(null);
  const draw = useRef<TerraDraw | null>(null);
  const drawn = useRef(onDrawn);
  const vertices = useRef<[number, number][]>([]);
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState<Basemap>("satellite");
  const [choosing, setChoosing] = useState(false);
  const [pointer, setPointer] = useState<[number, number] | null>(null);
  const [live, setLive] = useState<Live>(null);
  const [split, setSplit] = useState(0.5);
  const [menu, setMenu] = useState<{ x: number; y: number; at: [number, number] } | null>(null);
  const moved = useRef<number | null>(null);
  const inspectRef = useRef(props.onInspect);
  const toolRef = useRef(tool);
  const viewRef = useRef(onView);

  useEffect(() => {
    drawn.current = onDrawn;
    inspectRef.current = props.onInspect;
    toolRef.current = tool;
    viewRef.current = onView;
  });

  // Every corner of the areas already drawn, for snapping a new one to them
  useEffect(() => {
    vertices.current = areas.flatMap((a) =>
      a.geometry.type === "Polygon" ? (a.geometry.coordinates.flat() as [number, number][]) : a.geometry.type === "MultiPolygon" ? (a.geometry.coordinates.flat(2) as [number, number][]) : [],
    );
  }, [areas]);

  useEffect(() => {
    const instance = new MapLibre({
      container: container.current!,
      style: baseStyle("satellite"),
      center: JENDOUBA,
      zoom: 14,
      attributionControl: { compact: true },
    });
    instance.addControl(new ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
    instance.on("load", () => {
      const empty: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
      instance.addSource("areas", { type: "geojson", data: empty });
      instance.addSource("pixels", { type: "geojson", data: empty });
      instance.addSource("inspected", { type: "geojson", data: empty });
      instance.addLayer({ id: "pixels-line", type: "line", source: "pixels", paint: { "line-color": "#ffffff", "line-width": 0.8, "line-opacity": 0.85, "line-dasharray": [2, 2] } });
      instance.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": ["get", "colour"], "fill-opacity": 0.08 } });
      instance.addLayer({ id: "areas-halo", type: "line", source: "areas", paint: { "line-color": "#000000", "line-width": 3.5, "line-opacity": 0.35 } });
      instance.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": ["get", "colour"], "line-width": 1.75 } });
      instance.addLayer({
        id: "inspected",
        type: "circle",
        source: "inspected",
        paint: { "circle-radius": 4, "circle-color": "#ffd60a", "circle-stroke-color": INK, "circle-stroke-width": 1.5 },
      });

      const snap = (event: TerraDrawMouseEvent, context: SnappableContext) => {
        let best: [number, number] | undefined;
        let bestDistance = 10; // pixels
        for (const v of vertices.current) {
          const p = context.project(v[0], v[1]);
          const d = Math.hypot(p.x - event.containerX, p.y - event.containerY);
          if (d < bestDistance) [best, bestDistance] = [v, d];
        }
        return best;
      };
      const terra = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map: instance }),
        modes: [
          new TerraDrawPolygonMode({ styles: HANDLES, snapping: { toCustom: snap, toCoordinate: true }, pointerDistance: 12 }),
          new TerraDrawRectangleMode({ styles: { fillColor: "#ffd60a", fillOpacity: 0.12, outlineColor: "#ffd60a", outlineWidth: 1.5 } }),
          new TerraDrawLineStringMode({
            modeName: "measure",
            styles: { lineStringColor: "#ffd60a", lineStringWidth: 2, closingPointColor: "#ffffff", closingPointWidth: 4, closingPointOutlineColor: INK, closingPointOutlineWidth: 2 },
            snapping: { toCustom: snap },
          }),
        ],
        undoRedo: { modeLevel: new TerraDrawModeUndoRedo(), keyboardShortcuts: new TerraDrawUndoRedoKeyboardShortcuts() },
      });
      terra.start();
      // what is being drawn is measured as it grows
      terra.on("change", () => {
        const current = terra.getSnapshot().find((f) => f.properties?.mode !== "static" && (f.geometry.type === "Polygon" || f.geometry.type === "LineString"));
        if (!current) return setLive(null);
        if (current.geometry.type === "Polygon") {
          const ring = current.geometry.coordinates[0] as number[][];
          setLive({ kind: "polygon", metres: length(ring), m2: areaOf(ring), last: ring.length > 2 ? length(ring.slice(-3, -1)) : 0 });
        } else {
          const line = current.geometry.coordinates as number[][];
          setLive({ kind: "line", metres: length(line), m2: 0, last: line.length > 1 ? length(line.slice(-2)) : 0 });
        }
      });
      terra.on("finish", (id) => {
        const feature = terra.getSnapshotFeature(id);
        if (toolRef.current === "measure") return; // the measured line stays until the tool changes
        terra.clear();
        setLive(null);
        if (feature?.geometry.type === "Polygon") drawn.current(feature.geometry);
      });
      draw.current = terra;
      setReady(true);
    });
    instance.on("mousemove", (e) => setPointer([e.lngLat.lng, e.lngLat.lat]));
    instance.on("mouseout", () => setPointer(null));
    instance.on("click", (e) => {
      if (toolRef.current === "inspect") inspectRef.current([e.lngLat.lng, e.lngLat.lat]);
    });
    instance.on("contextmenu", (e) => {
      e.preventDefault();
      setMenu({ x: e.originalEvent.clientX, y: e.originalEvent.clientY, at: [e.lngLat.lng, e.lngLat.lat] });
    });
    instance.on("moveend", () => {
      const c = instance.getCenter();
      viewRef.current({ center: [c.lng, c.lat], zoom: instance.getZoom() });
    });
    map.current = instance;
    return () => instance.remove();
  }, []);

  useEffect(() => {
    if (!ready) return;
    (map.current!.getSource("areas") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: areas.map((area) => ({ type: "Feature", id: area.id, properties: { colour: area.colour }, geometry: area.geometry })),
    });
  }, [areas, ready]);

  useEffect(() => {
    if (!ready) return;
    (map.current!.getSource("inspected") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: props.inspected ? [{ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: props.inspected } }] : [],
    });
  }, [props.inspected, ready]);

  useEffect(() => {
    if (!ready) return;
    const terra = draw.current!;
    terra.clear();
    terra.setMode(tool === "polygon" || tool === "rectangle" || tool === "measure" ? tool : "static");
  }, [tool, ready]);

  // The variable's own pixels over the areas: what each area mean is made of
  const areaIds = areas.map((a) => a.id).join(",");
  useEffect(() => {
    if (!ready) return;
    const source = map.current!.getSource("pixels") as GeoJSONSource;
    if (!grid || !areaIds) {
      source.setData({ type: "FeatureCollection", features: [] });
      return;
    }
    let current = true;
    Promise.all(areaIds.split(",").map((id) => areaPixels(Number(id), grid)))
      .then((grids) => {
        if (current) source.setData({ type: "FeatureCollection", features: grids.flatMap((g) => g.features) });
      })
      .catch((error) => current && onTiles(null, error instanceof Error ? error.message : String(error)));
    return () => {
      current = false;
    };
  }, [grid, areaIds, ready, onTiles]);

  // The chosen variable for the chosen month, under the areas
  useEffect(() => {
    if (!ready) return;
    let current = true;
    showLayer(map.current!, layer, month, (tiles, error) => current && onTiles(tiles, error));
    return () => {
      current = false;
    };
  }, [layer, month, ready, onTiles]);

  useEffect(() => {
    if (ready && layer && map.current?.getLayer("layer")) map.current.setPaintProperty("layer", "raster-opacity", layer.opacity);
  }, [layer, ready]);

  // Swipe: a second map on the right of the divider, following the first, showing another month
  useEffect(() => {
    if (!ready || !compare || !layer || !other.current) return;
    const main = map.current!;
    const second = new MapLibre({
      container: other.current,
      style: baseStyle(basemap),
      center: main.getCenter(),
      zoom: main.getZoom(),
      interactive: false,
      attributionControl: false,
    });
    const follow = () => second.jumpTo({ center: main.getCenter(), zoom: main.getZoom(), bearing: main.getBearing(), pitch: main.getPitch() });
    main.on("move", follow);
    second.on("load", () => {
      second.addSource("areas", { type: "geojson", data: (main.getSource("areas") as GeoJSONSource).serialize().data as GeoJSON.FeatureCollection });
      second.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": ["get", "colour"], "line-width": 1.75 } });
      showLayer(second, layer, compare, () => {});
    });
    right.current = second;
    return () => {
      main.off("move", follow);
      second.remove();
      right.current = null;
    };
  }, [compare, layer, ready, basemap]);

  // The map must re-measure itself when the side panels open or close, or its page comes back
  useEffect(() => {
    const timer = window.setTimeout(() => {
      map.current?.resize();
      right.current?.resize();
    }, 50);
    return () => window.clearTimeout(timer);
  }, [focus, visible]);

  // A hidden map has no size, so a move waits until the map is shown, and is made only once
  useEffect(() => {
    if (!ready || !target || !visible || moved.current === target.key) return;
    moved.current = target.key;
    map.current!.resize();
    if (target.bounds) map.current!.fitBounds(target.bounds, { padding: 80, maxZoom: 16, duration: 0 });
    else if (target.center) map.current!.jumpTo({ center: target.center, zoom: target.zoom ?? 14 });
  }, [target, ready, visible]);

  function chooseBasemap(next: Basemap) {
    for (const key of Object.keys(BASEMAPS)) map.current?.setLayoutProperty(key, "visibility", key === next ? "visible" : "none");
    setBasemap(next);
    setChoosing(false);
  }

  const dragSplit = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const frame = e.currentTarget.parentElement!.getBoundingClientRect();
    e.currentTarget.setPointerCapture(e.pointerId);
    const move = (m: PointerEvent) => setSplit(Math.min(0.95, Math.max(0.05, (m.clientX - frame.left) / frame.width)));
    const handle = e.currentTarget;
    const stop = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", stop);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", stop);
  }, []);

  const items: MenuItem[] = menu
    ? [
        { label: `Copy ${coordinate(menu.at[0], menu.at[1])}`, run: () => void navigator.clipboard?.writeText(`${menu.at[1].toFixed(6)}, ${menu.at[0].toFixed(6)}`) },
        { label: "Inspect this point", run: () => props.onInspect(menu.at), hint: "I" },
        "divider",
        { label: "Zoom to the areas", run: props.onFit, hint: "Z" },
        { label: "Centre here", run: () => map.current?.easeTo({ center: menu.at, duration: 0 }) },
      ]
    : [];

  return (
    <>
      {/* MapLibre's own CSS sets the map's position, so a wrapper does the placing */}
      <div className="map-frame" data-tool={tool ?? undefined}>
        <div ref={container} className="map" data-ready={ready} />
        {compare && layer && (
          <>
            <div className="map-compare" style={{ clipPath: `inset(0 0 0 ${split * 100}%)` }}>
              <div ref={other} className="map" />
            </div>
            <div className="swipe" style={{ left: `${split * 100}%` }} onPointerDown={dragSplit} role="separator" aria-label="Drag to compare the two months">
              <span className="swipe-label left">{month}</span>
              <span className="swipe-label right">{compare}</span>
            </div>
          </>
        )}
      </div>

      <div className="map-status" aria-live="off">
        {live && (tool === "polygon" || tool === "rectangle" || tool === "measure") && (
          <span className="measure">
            {live.kind === "polygon" ? (
              <>
                Area <b>{surface(live.m2)}</b> · perimeter {distance(live.metres)}
              </>
            ) : (
              <>
                Distance <b>{distance(live.metres)}</b>
                {live.last > 0 && ` · last leg ${distance(live.last)}`}
              </>
            )}
          </span>
        )}
        {pointer && <span className="coords">{coordinate(pointer[0], pointer[1])}</span>}
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
        <div className="floating map-buttons">
          <button aria-label="Zoom in" title="Zoom in (+)" onClick={() => map.current?.zoomIn({ duration: 0 })}>
            +
          </button>
          <button aria-label="Zoom out" title="Zoom out (−)" onClick={() => map.current?.zoomOut({ duration: 0 })}>
            −
          </button>
          <button aria-label="North up" title="North up" onClick={() => map.current?.resetNorth({ duration: 0 })}>
            N
          </button>
        </div>
        <div className="floating map-buttons">
          <button aria-expanded={choosing} onClick={() => setChoosing(!choosing)} title="Basemap">
            {BASEMAPS[basemap].label}
          </button>
          <button aria-pressed={focus} title={focus ? "Show the panels again (F)" : "Hide the panels and show only the map (F)"} onClick={onFocus}>
            {focus ? "Show panels" : "Focus map"}
          </button>
        </div>
      </div>
      {menu && <ContextMenu x={menu.x} y={menu.y} items={items} onClose={() => setMenu(null)} />}
    </>
  );
}

// Adds, replaces or removes the variable's tiles under the areas
function showLayer(map: MapLibre, layer: Layer | null, month: string | null, done: (tiles: Tiles | null, error?: string) => void) {
  const drop = () => {
    if (map.getLayer("layer")) map.removeLayer("layer");
    if (map.getSource("layer")) map.removeSource("layer");
  };
  if (!layer || !month) {
    drop();
    done(null);
    return;
  }
  layerTiles(layer.variable, month, layer.scale)
    .then((tiles) => {
      const source = map.getSource("layer") as RasterTileSource | undefined;
      if (source) source.setTiles([tiles.url]);
      else {
        map.addSource("layer", { type: "raster", tiles: [tiles.url], tileSize: 256, attribution: "Google Earth Engine" });
        map.addLayer(
          { id: "layer", type: "raster", source: "layer", paint: { "raster-opacity": layer.opacity, "raster-resampling": "nearest" } },
          map.getLayer("pixels-line") ? "pixels-line" : undefined,
        );
      }
      done(tiles);
    })
    .catch((error) => done(null, error instanceof Error ? error.message : String(error)));
}
