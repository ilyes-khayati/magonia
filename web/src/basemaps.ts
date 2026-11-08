import type { StyleSpecification } from "maplibre-gl";

// All basemaps live in one style and are switched by visibility, so the areas and
// drawing layers on top survive a change of basemap. Every one is served without a key. Each
// has the deepest zoom its tiles exist at in rural Tunisia; closer in, the map enlarges that
// level instead of asking for tiles that come back as "not available".
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
export const BASEMAPS = {
  satellite: {
    label: "Satellite",
    tiles: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maxzoom: 18,
  },
  terrain: {
    label: "Terrain",
    tiles: "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors",
    maxzoom: 17,
  },
  streets: {
    label: "Streets",
    tiles: `${ESRI}/World_Street_Map/MapServer/tile/{z}/{y}/{x}`,
    attribution: "© Esri, HERE, Garmin, © OpenStreetMap contributors",
    maxzoom: 18,
  },
  dark: {
    label: "Dark",
    tiles: `${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`,
    attribution: "© Esri, HERE, Garmin, © OpenStreetMap contributors",
    maxzoom: 16,
  },
} as const;

export type Basemap = keyof typeof BASEMAPS;

export function baseStyle(initial: Basemap): StyleSpecification {
  const entries = Object.entries(BASEMAPS) as [Basemap, (typeof BASEMAPS)[Basemap]][];
  return {
    version: 8,
    sources: Object.fromEntries(
      entries.map(([key, map]) => [
        key,
        { type: "raster", tiles: [map.tiles], tileSize: 256, attribution: map.attribution, maxzoom: map.maxzoom },
      ]),
    ),
    layers: entries.map(([key]) => ({
      id: key,
      type: "raster",
      source: key,
      layout: { visibility: key === initial ? "visible" : "none" },
    })),
  };
}
