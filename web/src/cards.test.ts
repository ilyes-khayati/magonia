import { describe, expect, it } from "vitest";
import { moved, ordered } from "./cards";

describe("card order", () => {
  it("moves a card to another card's place", () => {
    expect(moved(["a", "b", "c", "d"], 0, 2)).toEqual(["b", "c", "a", "d"]);
    expect(moved(["a", "b", "c", "d"], 3, 0)).toEqual(["d", "a", "b", "c"]);
    expect(moved(["a", "b"], 1, 5)).toEqual(["a", "b"]); // out of range: unchanged
  });

  it("keeps a saved order and puts new cards after it", () => {
    expect(ordered(["ndvi", "lst", "spei"], ["spei", "gone", "ndvi"])).toEqual(["spei", "ndvi", "lst"]);
    expect(ordered(["ndvi"], undefined)).toEqual(["ndvi"]);
  });
});
