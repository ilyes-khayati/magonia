// shpjs ships without type definitions
declare module "shpjs" {
  export default function shp(
    data: ArrayBuffer,
  ): Promise<GeoJSON.FeatureCollection | GeoJSON.FeatureCollection[]>;
}
