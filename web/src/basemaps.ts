import type { StyleSpecification } from "maplibre-gl";

// All basemaps live in one style and are switched by visibility, so the areas and
// drawing layers on top survive a change of basemap.
export const BASEMAPS = {
  satellite: {
    label: "Satellite",
    tiles: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
  },
  terrain: {
    label: "Terrain",
    tiles: "https://tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "© OpenTopoMap (CC-BY-SA), © OpenStreetMap contributors",
  },
  streets: {
    label: "Streets",
    tiles: "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
    attribution: "© CARTO, © OpenStreetMap contributors",
  },
  dark: {
    label: "Dark",
    tiles: "https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    attribution: "© CARTO, © OpenStreetMap contributors",
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
        { type: "raster", tiles: [map.tiles], tileSize: 256, attribution: map.attribution },
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
