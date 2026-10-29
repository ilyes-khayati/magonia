import { describe, expect, it } from "vitest";
import { boardForMagonia, pin, readBoard } from "./board";

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
      { title: "Note: Idea", text: "Check 2017." },
      { title: "Trend", text: "Rising. Caution. Short." },
    ]);
  });
});
