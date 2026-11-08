import { describe, expect, it } from "vitest";
import { DISC, gridFor, inDisc, makeSim, pixels, step } from "./turing";

describe("the mark's pattern", () => {
  it("keeps square grids of the five levels, blank outside the shape", () => {
    for (const [n, rows] of Object.entries(DISC)) {
      expect(rows).toHaveLength(+n);
      for (const row of rows) expect(row).toMatch(new RegExp(`^[0-4.]{${n}}$`));
    }
  });

  it("uses a coarser grid for a smaller mark", () => {
    expect(gridFor(16)).toHaveLength(8);
    expect(gridFor(40)).toHaveLength(11);
    expect(gridFor(64)).toHaveLength(16);
    expect(gridFor(160)).toHaveLength(26);
  });

  it("keeps the live mark inside a round field", () => {
    expect(inDisc(0.5, 0.5)).toBe(true);
    expect(inDisc(0.02, 0.02)).toBe(false);
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
