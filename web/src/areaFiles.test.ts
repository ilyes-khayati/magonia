import { describe, expect, it } from "vitest";
import { readable } from "./areaFiles";

describe("readable", () => {
  it("turns a file name into an area name", () => {
    expect(readable("olive-jendouba_polygon")).toBe("Olive jendouba polygon");
    expect(readable("Kroumirie forest")).toBe("Kroumirie forest");
    expect(readable("---")).toBe("---");
  });
});
