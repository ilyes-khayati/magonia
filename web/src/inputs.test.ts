import { describe, expect, it } from "vitest";
import { waitingFor } from "./inputs";

describe("waitingFor", () => {
  it("names the series that failed and why, instead of waiting for ever", () => {
    expect(
      waitingFor([
        { name: "NDVI", state: { status: "loading" } },
        {
          name: "LST",
          state: { status: "failed", error: "Earth Engine did not answer." },
        },
      ]),
    ).toBe("LST could not be loaded: Earth Engine did not answer.");
  });

  it("lists the series still loading or not asked for yet", () => {
    expect(
      waitingFor([
        { name: "NDVI", state: { status: "loading" } },
        { name: "LST", state: undefined },
        { name: "SPEI", state: undefined },
      ]),
    ).toBe("Waiting for NDVI, LST and SPEI to load.");
    expect(
      waitingFor([
        { name: "NDVI", state: undefined },
        { name: "NDVI", state: undefined },
      ]),
    ).toBe("Waiting for NDVI to load.");
  });

  it("says it is computing once every series is there", () => {
    expect(waitingFor([])).toBe("Computing…");
  });
});
