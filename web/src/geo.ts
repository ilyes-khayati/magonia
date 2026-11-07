// Lengths and areas on the Earth, for measuring while drawing. Spherical formulas: within
// about 0.5% of the ellipsoid, which is far below what a drawn outline is accurate to.

const R = 6_371_008.8; // mean Earth radius, metres
const rad = (d: number) => (d * Math.PI) / 180;

export function length(points: number[][]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const [lon1, lat1] = points[i - 1];
    const [lon2, lat2] = points[i];
    const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
    total += 2 * R * Math.asin(Math.min(1, Math.sqrt(a)));
  }
  return total;
}

// The area of a ring, in m² (Chamberlain and Duquette 2007)
export function area(ring: number[][]): number {
  if (ring.length < 3) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const [lon1, lat1] = ring[i];
    const [lon2, lat2] = ring[(i + 1) % ring.length];
    sum += rad(lon2 - lon1) * (2 + Math.sin(rad(lat1)) + Math.sin(rad(lat2)));
  }
  return Math.abs((sum * R * R) / 2);
}

// A square of a given side, in metres, centred on a point: one pixel as an area
export function square([lon, lat]: [number, number], side: number): GeoJSON.Polygon {
  const dLat = (side / 2 / R) * (180 / Math.PI);
  const dLon = dLat / Math.cos(rad(lat));
  return {
    type: "Polygon",
    coordinates: [
      [
        [lon - dLon, lat - dLat],
        [lon + dLon, lat - dLat],
        [lon + dLon, lat + dLat],
        [lon - dLon, lat + dLat],
        [lon - dLon, lat - dLat],
      ],
    ],
  };
}

// Coordinates typed or pasted: "lat, lon", a box "west, south, east, north", or a list of
// "lon lat" pairs forming a polygon. Returns null when the text is none of these.
export function parseCoordinates(text: string): { point: [number, number] } | { polygon: GeoJSON.Polygon } | null {
  const numbers = (text.match(/-?\d+(?:\.\d+)?/g) ?? []).map(Number);
  const valid = (lon: number, lat: number) => Math.abs(lon) <= 180 && Math.abs(lat) <= 90;
  if (numbers.length === 2) {
    const [lat, lon] = numbers;
    return valid(lon, lat) ? { point: [lon, lat] } : null;
  }
  if (numbers.length === 4 && !/\n/.test(text.trim())) {
    const [w, s, e, n] = numbers;
    if (!valid(w, s) || !valid(e, n) || w >= e || s >= n) return null;
    return { polygon: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] } };
  }
  if (numbers.length >= 6 && numbers.length % 2 === 0) {
    const ring: number[][] = [];
    for (let i = 0; i < numbers.length; i += 2) ring.push([numbers[i], numbers[i + 1]]);
    if (!ring.every(([lon, lat]) => valid(lon, lat))) return null;
    const [first, last] = [ring[0], ring[ring.length - 1]];
    if (first[0] !== last[0] || first[1] !== last[1]) ring.push(first);
    return ring.length >= 4 ? { polygon: { type: "Polygon", coordinates: [ring] } } : null;
  }
  return null;
}
