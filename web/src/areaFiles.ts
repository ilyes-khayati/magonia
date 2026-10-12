import { kml } from "@tmcw/togeojson";
import shp from "shpjs";

export type NamedGeometry = { name: string; geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon };

// Reads an uploaded GeoJSON, KML or zipped shapefile into named polygons
export async function readAreaFile(file: File): Promise<NamedGeometry[]> {
  const lower = file.name.toLowerCase();
  let data: unknown;
  if (lower.endsWith(".zip")) {
    data = await shp(await file.arrayBuffer());
  } else if (lower.endsWith(".kml")) {
    data = kml(new DOMParser().parseFromString(await file.text(), "text/xml"));
  } else if (lower.endsWith(".geojson") || lower.endsWith(".json")) {
    data = JSON.parse(await file.text());
  } else {
    throw new Error("Upload a GeoJSON, KML or zipped shapefile (.zip).");
  }

  const base = file.name.replace(/\.[^.]+$/, "");
  const features = (Array.isArray(data) ? data : [data]).flatMap((part) =>
    toFeatures(part as GeoJSON.GeoJSON),
  );
  const polygons = features.filter(
    (feature) => feature.geometry?.type === "Polygon" || feature.geometry?.type === "MultiPolygon",
  );
  if (!polygons.length) throw new Error(`${file.name} contains no polygons.`);

  return polygons.map((feature, index) => {
    const label = feature.properties?.name ?? feature.properties?.NAME;
    return {
      name: typeof label === "string" && label.trim() ? label.trim() : polygons.length > 1 ? `${base} ${index + 1}` : base,
      geometry: feature.geometry as NamedGeometry["geometry"],
    };
  });
}

function toFeatures(data: GeoJSON.GeoJSON): GeoJSON.Feature[] {
  if (data.type === "FeatureCollection") return data.features;
  if (data.type === "Feature") return [data];
  return [{ type: "Feature", properties: {}, geometry: data as GeoJSON.Geometry }];
}
