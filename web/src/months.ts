// Months as "YYYY-MM", and round values for a colour ramp

export const shiftMonth = (month: string, by: number) => {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return d.toISOString().slice(0, 7);
};

// Round values along the colour ramp, placed where they fall on it
export function ticks(low: number, high: number) {
  const raw = (high - low) / 5;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw)!;
  const digits = Math.max(0, -Math.floor(Math.log10(step) + 1e-9) + (step / power === 2.5 ? 1 : 0));
  const out = [];
  for (let v = Math.ceil(low / step) * step; v <= high + 1e-9; v += step) out.push({ value: v, at: (v - low) / (high - low), digits });
  return out;
}

