import { describe, expect, it } from "vitest";
import type { CheckedNumber, PaperCard } from "./api";
import { answerParts, applyEvent, citationParts, conversationTitle, styled, withInstruction, type Turn } from "./chat";

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

  it("takes back what was said when the model wrote out a tool call", () => {
    let turn = applyEvent(empty, { type: "text", text: '```json {"name": "read_series"} ```' });
    turn = applyEvent(turn, { type: "rewrite", text: "" });
    expect(turn.content).toBe("");
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

  it("keeps the page of a citation to a passage", () => {
    expect(citationParts("Lost NDVI [1, p. 12].")).toEqual([
      { text: "Lost NDVI " },
      { cites: [1], page: 12 },
      { text: "." },
    ]);
  });

  it("leaves text without citations alone", () => {
    expect(citationParts("No citations here.")).toEqual([{ text: "No citations here." }]);
  });
});

describe("reading the workspace", () => {
  it("remembers which cards the answer was given and shows what it reads", () => {
    let turn = applyEvent(empty, { type: "view", cards: ["NDVI chart", "Correlation 1: NDVI and LST"] });
    expect(turn.status).toBe("Reading your workspace…");
    turn = applyEvent(turn, { type: "read", area: "Orchard", variable: "ndvi", year: 2022 });
    expect(turn.status).toBe("Looking closer at Orchard NDVI in 2022…");
    turn = applyEvent(turn, { type: "text", text: "It peaks in August." });
    expect(turn.status).toBeUndefined();
    expect(turn.details.cards).toEqual(["NDVI chart", "Correlation 1: NDVI and LST"]);
    expect(turn.details.reads).toEqual([{ area: "Orchard", variable: "ndvi", year: 2022 }]);
  });
});

describe("checked numbers", () => {
  const n = (start: number, text: string, status: "verified" | "unverified" = "verified") => ({
    start,
    end: start + text.length,
    text,
    status,
    source: status === "verified" ? "NDVI chart" : null,
  });

  it("places each number between the text and citations around it", () => {
    const text = "Peak 0.89 in Aug [1]; −0.15 is odd.";
    expect(answerParts(text, [n(5, "0.89"), n(22, "−0.15", "unverified")])).toEqual([
      { text: "Peak " },
      { number: n(5, "0.89") },
      { text: " in Aug " },
      { cites: [1] },
      { text: "; " },
      { number: n(22, "−0.15", "unverified") },
      { text: " is odd." },
    ]);
  });

  it("counts characters as the engine does, past characters JavaScript stores as two", () => {
    const text = "🌿 NDVI 0.89";
    expect(answerParts(text, [n(7, "0.89")]).at(-1)).toEqual({ number: n(7, "0.89") });
  });

  it("ignores numbers that do not match the text", () => {
    expect(answerParts("Peak 0.89.", [n(0, "0.89")])).toEqual([{ text: "Peak 0.89." }]);
  });
});

describe("styled", () => {
  const number = { start: 0, end: 0, text: "63", status: "verified", source: "card" } as CheckedNumber;

  it("shows bold, headings and bullets without their markers", () => {
    expect(styled([{ text: "### Models\n- **XGBoost** leans on LST\n* Ridge on its past" }])).toEqual([
      { text: "Models", bold: true },
      { text: "\n• ", bold: false },
      { text: "XGBoost", bold: true },
      { text: " leans on LST\n• Ridge on its past", bold: false },
    ]);
  });

  it("keeps numbers and citations in place, bold when inside bold", () => {
    expect(styled([{ text: "LST **at " }, { number }, { text: "%** [" }, { cites: [1] }, { text: "]" }])).toEqual([
      { text: "LST ", bold: false },
      { text: "at ", bold: true },
      { number, bold: true },
      { text: "%", bold: true },
      { text: " [", bold: false },
      { cites: [1], bold: false },
      { text: "]", bold: false },
    ]);
  });
});

describe("instructions from the chat", () => {
  it("are added as a line, once", () => {
    expect(withInstruction("", "Answer in French.")).toBe("- Answer in French.");
    expect(withInstruction("Be brief.", "Cite pages.")).toBe("Be brief.\n- Cite pages.");
    expect(withInstruction("- Answer in French.", "answer in french.")).toBe("- Answer in French.");
  });
});

describe("conversation titles", () => {
  it("are the name given, else the first question, shortened", () => {
    expect(conversationTitle({ title: "Drought lags", first_question: "Is there a lag?" })).toBe("Drought lags");
    expect(conversationTitle({ title: null, first_question: "Is there a lag?" })).toBe("Is there a lag?");
    expect(conversationTitle({ title: null, first_question: null })).toBe("New conversation");
    const long = conversationTitle({ title: null, first_question: "word ".repeat(30) });
    expect(long.length).toBeLessThanOrEqual(58);
    expect(long.endsWith("…")).toBe(true);
  });
});
