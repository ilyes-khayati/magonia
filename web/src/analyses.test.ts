import { describe, expect, it } from "vitest";
import { addAnalysis, duplicateAnalysis, needsOf, readAnalyses, variablesOf } from "./analyses";

describe("analyses", () => {
  it("starts a correlation from the charted variables", () => {
    const [added] = addAnalysis([], "correlation", ["ndvi", "spei"]);
    expect(added).toEqual({ id: 1, kind: "correlation", response: "ndvi", driver: "spei", deseasonalise: true });
  });

  it("picks a second variable when only one is charted", () => {
    const [added] = addAnalysis([], "correlation", ["ndvi"]);
    expect(variablesOf(added)).toEqual(["ndvi", "lst"]);
  });

  it("gives each new analysis its own id", () => {
    const two = addAnalysis(addAnalysis([], "correlation", []), "correlation", []);
    expect(two.map((a) => a.id)).toEqual([1, 2]);
  });

  it("drops saved analyses it cannot read", () => {
    const saved = [{ id: 1, kind: "correlation", response: "ndvi", driver: "lst", deseasonalise: true }, { id: 2, kind: "telepathy" }, null];
    expect(readAnalyses(saved).map((a) => a.id)).toEqual([1]);
    expect(readAnalyses(undefined)).toEqual([]);
  });
});

describe("decomposition", () => {
  it("asks for its variable at the product's own time step", () => {
    const [added] = addAnalysis([], "decomposition", ["lst", "ndvi"]);
    expect(added).toEqual({ id: 1, kind: "decomposition", variable: "lst" });
    expect(needsOf(added)).toEqual([{ variable: "lst", native: true }]);
  });
});

describe("lags", () => {
  it("tests the charted variables as drivers, or all the others", () => {
    const [charted] = addAnalysis([], "lags", ["ndvi", "spei"]);
    expect(charted).toMatchObject({ kind: "lags", response: "ndvi", drivers: ["spei"], deseasonalise: true });
    const [alone] = addAnalysis([], "lags", ["ndvi"]);
    expect(needsOf(alone).map((n) => n.variable)).toEqual(["ndvi", "lst", "spei"]);
  });
});

describe("duplicating an analysis", () => {
  it("places a named copy right after the original, with its own id", () => {
    const list = addAnalysis(addAnalysis([], "trend", ["ndvi"]), "phenology", ["ndvi"]);
    const copied = duplicateAnalysis(list, list[0].id);
    expect(copied.map((a) => a.kind)).toEqual(["trend", "trend", "phenology"]);
    expect(copied[1]).toMatchObject({ id: 3, name: "Long-term trend (copy)", variable: "ndvi" });
    // the copy is its own: changing it leaves the original
    expect(copied[1]).not.toBe(list[0]);
    expect(duplicateAnalysis(copied, 3)[2].name).toBe("Long-term trend (copy) (copy)");
  });

  it("ignores an id that is not there", () => {
    const list = addAnalysis([], "trend", ["ndvi"]);
    expect(duplicateAnalysis(list, 9)).toBe(list);
  });
});
