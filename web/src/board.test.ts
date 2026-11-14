import { describe, expect, it } from "vitest";
import { boardForMagonia, pin, readBoard, sectionOf, trustOf } from "./board";

describe("board", () => {
  it("pins items with an id and the date, and reads back only what it knows", () => {
    const board = pin(pin([], { kind: "note", title: "Idea", lines: ["Check 2017."] }), {
      kind: "answer",
      title: "Magonia",
      question: "Which model?",
      lines: ["XGBoost."],
    });
    expect(board.map((b) => b.id)).toEqual([1, 2]);
    expect(board[0].pinned).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(readBoard([...board, { junk: 1 }, null]).length).toBe(2);
  });

  it("tells Magonia what is pinned, notes as notes", () => {
    const told = boardForMagonia([
      { id: 1, kind: "note", title: "Idea", lines: ["Check 2017."], pinned: "2026-10-29" },
      { id: 2, kind: "card", title: "Trend", lines: ["Rising."], cautions: ["Short."], pinned: "2026-10-29" },
    ]);
    expect(told).toEqual([
      { title: "Note: Idea", text: "Check 2017.", trust: "note", pinned: "2026-10-29" },
      { title: "Trend", text: "Rising. Caution. Short.", trust: "computed", pinned: "2026-10-29" },
    ]);
  });

  it("puts each item in the section above it, and tells Magonia the section and highlights", () => {
    const board = [
      { id: 1, kind: "card" as const, title: "Trend", lines: ["Rising."], pinned: "2026-10-31" },
      { id: 2, kind: "section" as const, title: "Drought", lines: [], pinned: "2026-10-31" },
      { id: 3, kind: "passage" as const, title: "Smith, p. 4", lines: ["NDVI fell."], highlights: ["fell"], pinned: "2026-10-31" },
    ];
    expect([0, 1, 2].map((i) => sectionOf(board, i))).toEqual([null, "Drought", "Drought"]);
    expect(boardForMagonia(board)).toEqual([
      { title: "Trend", text: "Rising.", trust: "computed", pinned: "2026-10-31" },
      { title: "[Drought] Passage: Smith, p. 4", text: 'Highlighted: "fell" NDVI fell.', trust: "passage", pinned: "2026-10-31" },
    ]);
  });

  it("gives Magon an answer whose checks failed as failed, never as evidence", () => {
    const answer = (details: object) =>
      ({ id: 1, kind: "answer" as const, title: "Magon", lines: [], pinned: "2026-11-10", answer: { text: "", details } });
    expect(trustOf(answer({ support: [{ status: "supported" }] }))).toBe("checked");
    expect(trustOf(answer({ support: [{ status: "unsupported" }] }))).toBe("failed");
    expect(trustOf(answer({ numbers: [{ status: "unmatched" }] }))).toBe("failed");
  });
});
