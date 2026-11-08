import { describe, expect, it } from "vitest";
import { GRIDS, gridFor, makeSim, pixels, step } from "./turing";

describe("the mark's pattern", () => {
  it("keeps square grids of the five levels", () => {
    for (const [n, rows] of Object.entries(GRIDS)) {
      expect(rows).toHaveLength(+n);
      for (const row of rows) expect(row).toMatch(new RegExp(`^[0-4]{${n}}$`));
    }
  });

  it("uses a coarser grid for a smaller mark", () => {
    expect(gridFor(16)).toHaveLength(5);
    expect(gridFor(30)).toHaveLength(10);
    expect(gridFor(180)).toHaveLength(14);
  });

  it("grows the same maze from the same seed, with both bare and green pixels", () => {
    const grow = () => {
      const sim = makeSim(30, 21);
      step(sim, 600);
      return pixels(sim, 10);
    };
    const first = grow();
    expect(first).toEqual(grow());
    expect(first).toHaveLength(100);
    expect(Math.min(...first)).toBe(0);
    expect(Math.max(...first)).toBeGreaterThanOrEqual(3);
  });
});
