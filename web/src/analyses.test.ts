import { describe, expect, it } from "vitest";
import { addAnalysis, needsOf, readAnalyses, variablesOf } from "./analyses";

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

describe("forecast models", () => {
  it("start with every other variable as a driver and lags left to the code", () => {
    const [added] = addAnalysis([], "models", ["ndvi"]);
    expect(added).toEqual({
      id: 1,
      kind: "models",
      response: "ndvi",
      drivers: ["lst", "spei"],
      own_lags: null,
      driver_lags: null,
      test_years: 3,
    });
  });
});
