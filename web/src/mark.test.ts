import { describe, expect, it } from "vitest";
import { EYE, STORK, gridFor } from "./mark";

describe("the stork mark", () => {
  it("keeps square grids of four densities, blank where the stork is not", () => {
    for (const [n, rows] of Object.entries(STORK)) {
      expect(rows).toHaveLength(+n);
      for (const row of rows) expect(row).toMatch(new RegExp(`^[1-4.]{${n}}$`));
    }
  });

  it("uses a coarser grid for a smaller mark", () => {
    expect(gridFor(16)).toHaveLength(8);
    expect(gridFor(40)).toHaveLength(11);
    expect(gridFor(64)).toHaveLength(16);
    expect(gridFor(160)).toHaveLength(26);
  });

  it("leaves the eye's place empty, for its one dot", () => {
    const grid = STORK[26];
    const [x, y] = EYE;
    expect(grid[Math.floor(y * 26)][Math.floor(x * 26)]).toBe(".");
  });
});
