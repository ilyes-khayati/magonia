import type { Analysis } from "./analyses";
import type { VariableKey } from "./api";
import type { CardLayout } from "./cards";
import type { Experiment } from "./experiments";

// What a pinned card is drawn from: its own copy of the card's choices, so that it stays live
// (hover, zoom, change it) without following later changes on its page
export type Source =
  | { type: "chart"; variable: VariableKey }
  | { type: "analysis"; analysis: Analysis }
  | { type: "experiment"; experiment: Experiment };

// The research board (#80, #90): what the researcher pinned, kept as it was when pinned, so
// that the board is a dated record of findings even after the analyses change.
export type BoardItem = {
  id: number;
  kind: "card" | "experiment" | "answer" | "note";
  title: string;
  lines: string[]; // the findings, as the card or Magonia said them
  cautions?: string[];
  image?: string; // the card's charts, as a data URL
  question?: string; // for an answer: what was asked
  page?: string; // where it came from, to open it again
  source?: Source; // drawn live from this; items pinned before had only a picture
  pinned: string; // ISO date
  layout?: CardLayout;
};

export function pin(board: BoardItem[], item: Omit<BoardItem, "id" | "pinned">): BoardItem[] {
  const id = Math.max(0, ...board.map((b) => b.id)) + 1;
  return [...board, { ...item, id, pinned: new Date().toISOString().slice(0, 10) }];
}

export function readBoard(saved: unknown): BoardItem[] {
  if (!Array.isArray(saved)) return [];
  return saved.filter(
    (b): b is BoardItem =>
      typeof b === "object" && b !== null && typeof b.id === "number" && typeof b.title === "string" && Array.isArray(b.lines),
  );
}

// What a card says, read from the page: its summary sentences and the guardrails' cautions
export function snapshotLines(card: HTMLElement): { lines: string[]; cautions: string[] } {
  const text = (sel: string) => [...card.querySelectorAll(sel)].map((el) => el.textContent?.trim() ?? "").filter(Boolean);
  return { lines: text(".summary > li"), cautions: text(".cautions li") };
}

// What Magonia is told about the board: each pinned item in a line or two
export function boardForMagonia(board: BoardItem[]): { title: string; text: string }[] {
  return board.map((b) => ({
    title: b.kind === "note" ? `Note: ${b.title}` : b.title,
    text: [b.question ? `Asked: ${b.question}` : "", ...b.lines, ...(b.cautions ?? []).map((c) => `Caution. ${c}`)]
      .filter(Boolean)
      .join(" ")
      .slice(0, 1500),
  }));
}
