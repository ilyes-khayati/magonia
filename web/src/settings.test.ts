import { describe, expect, it } from "vitest";
import { errorText } from "./api";
import { DEFAULTS, parseMonth, readSettings } from "./settings";

describe("parseMonth", () => {
  it("reads a month the way a browser picker or a person writes it", () => {
    expect(parseMonth("2020-01")).toBe("2020-01");
    expect(parseMonth("2020-1")).toBe("2020-01");
    expect(parseMonth(" 2020/12 ")).toBe("2020-12");
    expect(parseMonth("3/2021")).toBe("2021-03");
  });

  it("refuses text that is not a month", () => {
    for (const text of ["", "2020", "2020-13", "2020-0", "jan 2020", "2020-01-15"]) {
      expect(parseMonth(text)).toBeNull();
    }
  });
});

describe("readSettings", () => {
  it("tidies a month saved as typed, and replaces one that cannot be read", () => {
    const settings = readSettings({ start: "2018-3", end: "soon" });
    expect(settings.start).toBe("2018-03");
    expect(settings.end).toBe(DEFAULTS.end);
  });
});

describe("errorText", () => {
  it("names the fields FastAPI could not read", () => {
    const body = { detail: [{ loc: ["body", "start"], msg: "Input should be a valid date" }] };
    expect(errorText(body, 422)).toBe("start: Input should be a valid date");
  });

  it("passes a plain message through, and falls back to the status", () => {
    expect(errorText({ detail: "Area not found" }, 404)).toBe("Area not found");
    expect(errorText({}, 500)).toBe("status 500");
  });
});
