import { describe, expect, it } from "vitest";
import { area, length, parseCoordinates, square } from "./geo";
import { coordinate, distance, num, range, signed, surface } from "./format";
import { shiftMonth, ticks } from "./months";

describe("measuring", () => {
  it("measures a degree of latitude as about 111 km", () => {
    expect(length([[8.5, 36], [8.5, 37]])).toBeCloseTo(111_195, -2);
  });

  it("gives a 250 m pixel an area of 6.25 ha", () => {
    const ring = square([8.56, 36.5], 250).coordinates[0];
    expect(area(ring) / 1e4).toBeCloseTo(6.25, 1);
  });
});

describe("typed coordinates", () => {
  it("reads a point as latitude, longitude", () => {
    expect(parseCoordinates("36.508, 8.561")).toEqual({ point: [8.561, 36.508] });
  });

  it("reads a box as west, south, east, north", () => {
    const found = parseCoordinates("8.55, 36.50, 8.57, 36.52");
    expect(found && "polygon" in found && found.polygon.coordinates[0]).toHaveLength(5);
  });

  it("closes a polygon given as lon lat pairs", () => {
    const found = parseCoordinates("8.55 36.50\n8.57 36.50\n8.57 36.52");
    expect(found && "polygon" in found && found.polygon.coordinates[0].at(-1)).toEqual([8.55, 36.5]);
  });

  it("refuses what is not coordinates", () => {
    expect(parseCoordinates("olive")).toBeNull();
    expect(parseCoordinates("120, 300")).toBeNull();
    expect(parseCoordinates("8.57, 36.50, 8.55, 36.52")).toBeNull(); // west after east
  });
});

describe("typeset numbers", () => {
  it("writes a true minus sign, and no sign on a rounded zero", () => {
    expect(num(-0.25, 2)).toBe("−0.25");
    expect(num(-0.001, 2)).toBe("0.00");
    expect(num(null)).toBe("–");
  });

  it("writes ranges with an en dash and slopes with their sign", () => {
    expect(range(-1, 2, 1)).toBe("−1.0 – 2.0");
    expect(signed(0.012, 3)).toBe("+0.012");
  });

  it("writes places, lengths and areas in their usual units", () => {
    expect(coordinate(8.5612, 36.5085, 4)).toBe("36.5085° N, 8.5612° E");
    expect(distance(820)).toBe("820 m");
    expect(distance(1520)).toBe("1.52 km");
    expect(surface(640_000)).toBe("64.00 ha");
    expect(surface(1_000_000)).toBe("1.00 km²");
  });
});

describe("months", () => {
  it("steps across a year", () => {
    expect(shiftMonth("2024-01", -1)).toBe("2023-12");
    expect(shiftMonth("2023-04", 12)).toBe("2024-04");
  });

  it("puts round values on a colour ramp", () => {
    expect(ticks(-2.5, 2.5).map((t) => t.value)).toEqual([-2, -1, 0, 1, 2]);
    expect(ticks(0, 50).map((t) => t.value)).toEqual([0, 10, 20, 30, 40, 50]);
    expect(ticks(0, 0.9).map((t) => t.value.toFixed(1))).toEqual(["0.0", "0.2", "0.4", "0.6", "0.8"]);
  });
});

describe("one area's sentences", () => {
  it("drop the area's name when every sentence has it", async () => {
    const { oneArea } = await import("./format");
    expect(oneArea(["Orchard: trend rising.", "Orchard: peak in March."])).toEqual(["Trend rising.", "Peak in March."]);
    expect(oneArea(["Orchard: rising.", "Forest: falling."])).toEqual(["Orchard: rising.", "Forest: falling."]);
  });
});
