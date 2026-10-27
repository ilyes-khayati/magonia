import { describe, expect, it } from "vitest";
import type { PaperCard } from "./api";
import { applyEvent, citationParts, type Turn } from "./chat";

const empty: Turn = { role: "assistant", content: "", details: {} };
const card = (n: number): PaperCard => ({
  n,
  id: `W${n}`,
  short: `Author${n} et al., 2022`,
  title: "A study",
  authors: [],
  year: 2022,
  venue: null,
  doi: null,
  abstract: null,
  open_access_url: null,
  cited_by: 0,
  countries: [],
});

describe("applyEvent", () => {
  it("builds an answer from a search, its papers, the text and the check", () => {
    let turn = applyEvent(empty, { type: "search", query: "olive drought" });
    expect(turn.status).toBe("Searching OpenAlex: olive drought…");
    turn = applyEvent(turn, { type: "papers", papers: [card(1), card(2)] });
    turn = applyEvent(turn, { type: "text", text: "Drought lowers NDVI [1]" });
    turn = applyEvent(turn, { type: "text", text: " [9]." });
    expect(turn.status).toBeUndefined();
    expect(turn.content).toBe("Drought lowers NDVI [1] [9].");

    turn = applyEvent(turn, { type: "check", text: "Drought lowers NDVI [1].", cited: [1], removed: [9], unverified: [] });
    expect(turn.content).toBe("Drought lowers NDVI [1].");
    expect(turn.details).toEqual({
      searches: ["olive drought"],
      papers: [card(1), card(2)],
      check: { cited: [1], removed: [9], unverified: [] },
    });
  });

  it("keeps errors visible", () => {
    const turn = applyEvent(empty, { type: "search_failed", query: "olive", error: "no network" });
    expect(turn.error).toBe('The search "olive" failed: no network');
  });
});

describe("citationParts", () => {
  it("separates citation groups from the text", () => {
    expect(citationParts("NDVI falls [1, 3] in drought [2].")).toEqual([
      { text: "NDVI falls " },
      { cites: [1, 3] },
      { text: " in drought " },
      { cites: [2] },
      { text: "." },
    ]);
  });

  it("leaves text without citations alone", () => {
    expect(citationParts("No citations here.")).toEqual([{ text: "No citations here." }]);
  });
});
