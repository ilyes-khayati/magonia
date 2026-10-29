import { describe, expect, it } from "vitest";
import type { SeriesOptions, VariableKey } from "./api";
import { bodyOf, isPaper, newExperiment, PAPER, readExperiments, recipeDifferences, sameRecipe, type Recipe } from "./experiments";

const options = (areaId: number, variable: VariableKey) => ({ area_id: areaId, variable }) as unknown as SeriesOptions;
const paper: Recipe = { ...PAPER, area: 1 };

describe("experiments", () => {
  it("start from the paper's method, not yet run", () => {
    const e = newExperiment([], 1);
    expect(e).toMatchObject({ id: 1, name: "Paper method 1", ran: null, explain: false });
    expect(isPaper(e.recipe)).toBe(true);
    expect(isPaper({ ...e.recipe, area: 7 })).toBe(true); // the area is not part of the method
    expect(isPaper({ ...e.recipe, calendar: false })).toBe(false);
  });

  it("send the paper's request unchanged, and later choices only when they differ", () => {
    expect(bodyOf(paper, options)).toEqual({
      response: { area_id: 1, variable: "ndvi" },
      drivers: [
        { area_id: 1, variable: "lst" },
        { area_id: 1, variable: "spei" },
      ],
      own_lags: null,
      driver_lags: null,
      test_years: 3,
    });
    const own = bodyOf(
      { ...paper, models: ["XGBoost", "Ridge"], params: { XGBoost: { max_depth: 3 }, RandomForest: { max_depth: 9 } }, calendar: false, rolling: false },
      options,
    );
    expect(own.models).toEqual(["Ridge", "XGBoost"]);
    expect(own.params).toEqual({ XGBoost: { max_depth: 3 } }); // a model not chosen sends nothing
    expect(own).toMatchObject({ calendar: false, rolling: false });
  });

  it("compare recipes whatever the order of their choices", () => {
    expect(sameRecipe(paper, { ...paper, drivers: ["spei", "lst"], models: ["XGBoost", "Ridge", "RandomForest"] })).toBe(true);
    expect(sameRecipe(paper, { ...paper, test_years: 5 })).toBe(false);
    expect(sameRecipe(paper, null)).toBe(false);
  });

  it("say what differs between two runs", () => {
    const name = (k: VariableKey) => k.toUpperCase();
    expect(recipeDifferences(paper, { ...paper, test_years: 5, drivers: ["spei"] }, [], name)).toEqual([
      "drivers LST, SPEI against SPEI",
      "last 3 against 5 years held out",
    ]);
  });

  it("are read back, and forecast cards from before become experiments that have run", () => {
    const saved = [{ ...newExperiment([], 1), id: 4 }];
    const old = { kind: "models" as const, response: "ndvi" as VariableKey, drivers: ["lst"] as VariableKey[], own_lags: [1, 12], driver_lags: null, test_years: 4 };
    const read = readExperiments([...saved, { junk: true }], [old]);
    expect(read.map((e) => e.id)).toEqual([4, 5]);
    expect(read[1]).toMatchObject({ name: "Forecast 5", recipe: { own_lags: [1, 12], test_years: 4, area: null } });
    expect(sameRecipe(read[1].recipe, read[1].ran)).toBe(true);
  });
});
