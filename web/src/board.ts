import type { Analysis } from "./analyses";
import type { AnswerDetails, BoardTrust, VariableKey } from "./api";
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
  // a section is a heading: the items after it, up to the next one, belong to it
  kind: "card" | "experiment" | "answer" | "note" | "passage" | "section";
  title: string;
  lines: string[]; // the findings, as the card or Magonia said them
  cautions?: string[];
  image?: string; // the card's charts, as a data URL
  question?: string; // for an answer: what was asked
  answer?: { text: string; details: AnswerDetails }; // for an answer: shown as in the chat
  link?: string; // for a passage: the paper it comes from
  highlights?: string[]; // what the researcher marked in the item's text
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

// The section each item belongs to: the title of the last section before it
export function sectionOf(board: BoardItem[], index: number): string | null {
  for (let i = index; i >= 0; i--) if (board[i].kind === "section") return board[i].title;
  return null;
}

// What Magonia is told about the board: each pinned item in a line or two, with its section
// and what the researcher highlighted in it
// How far Magon may trust an item: an answer whose checks failed is never its evidence
export function trustOf(b: BoardItem): BoardTrust {
  if (b.kind === "note") return "note";
  if (b.kind === "passage") return "passage";
  if (b.kind !== "answer") return "computed";
  const d = b.answer?.details;
  const failed =
    (d?.support ?? []).some((s) => s.status === "unsupported") ||
    (d?.numbers ?? []).some((n) => n.status !== "verified") ||
    (d?.app ?? []).some((m) => m.status === "unknown");
  return failed ? "failed" : "checked";
}

export function boardForMagonia(board: BoardItem[]): { title: string; text: string; trust: BoardTrust; pinned: string }[] {
  const label = { note: "Note", passage: "Passage" } as Record<string, string>;
  return board.flatMap((b, i) => {
    if (b.kind === "section") return [];
    const section = sectionOf(board, i);
    return [
      {
        title: `${section ? `[${section}] ` : ""}${label[b.kind] ? `${label[b.kind]}: ` : ""}${b.title}`,
        text: [
          ...(b.highlights ?? []).map((h) => `Highlighted: "${h}"`),
          b.question ? `Asked: ${b.question}` : "",
          ...b.lines,
          ...(b.cautions ?? []).map((c) => `Caution. ${c}`),
        ]
          .filter(Boolean)
          .join(" ")
          .slice(0, 1500),
        trust: trustOf(b),
        pinned: b.pinned,
      },
    ];
  });
}
