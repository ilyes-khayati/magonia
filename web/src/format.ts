// Numbers as they are typeset: a true minus sign, a fixed number of decimals, and an en dash
// between the ends of a range.

const MINUS = "−";

export function num(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const text = Math.abs(value).toFixed(digits);
  // a value that rounds to zero is written without a sign
  return value < 0 && Number(text) !== 0 ? `${MINUS}${text}` : text;
}

export const range = (low: number, high: number, digits = 2) => `${num(low, digits)} – ${num(high, digits)}`;

export const signed = (value: number, digits = 2) => (value > 0 ? `+${num(value, digits)}` : num(value, digits));

export function coordinate(lon: number, lat: number, digits = 5): string {
  const ns = lat >= 0 ? "N" : "S";
  const ew = lon >= 0 ? "E" : "W";
  return `${Math.abs(lat).toFixed(digits)}° ${ns}, ${Math.abs(lon).toFixed(digits)}° ${ew}`;
}

export function distance(metres: number): string {
  return metres >= 1000 ? `${(metres / 1000).toFixed(metres >= 10_000 ? 1 : 2)} km` : `${Math.round(metres)} m`;
}

export function surface(m2: number): string {
  return m2 >= 1e6 ? `${(m2 / 1e6).toFixed(m2 >= 1e8 ? 0 : 2)} km²` : `${(m2 / 1e4).toFixed(2)} ha`;
}
