import { describe, expect, it } from "vitest";
import { addAnalysis, readAnalyses, variablesOf } from "./analyses";

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
