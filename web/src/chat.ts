import type { AnswerDetails, ChatEvent, ChatMessage, CheckedNumber } from "./api";

// One message in the conversation as the chat panel shows it
export type Turn = {
  role: "user" | "assistant";
  content: string;
  details: AnswerDetails;
  status?: string; // what the assistant is doing right now, e.g. searching
  error?: string;
};

export const fromSaved = (m: ChatMessage): Turn => ({ role: m.role, content: m.content, details: m.details ?? {} });

// The answer after one more event from the API
export function applyEvent(turn: Turn, event: ChatEvent): Turn {
  const details = turn.details;
  switch (event.type) {
    case "text":
      return { ...turn, content: turn.content + event.text, status: undefined };
    case "search":
      return {
        ...turn,
        status: `Searching OpenAlex: ${event.query}…`,
        details: { ...details, searches: [...(details.searches ?? []), event.query] },
      };
    case "search_failed":
      return { ...turn, status: undefined, error: `The search "${event.query}" failed: ${event.error}` };
    case "papers":
      return {
        ...turn,
        status: "Reading the papers found…",
        details: { ...details, papers: [...(details.papers ?? []), ...event.papers] },
      };
    case "check":
      return {
        ...turn,
        content: event.text,
        status: undefined,
        details: {
          ...details,
          check: { cited: event.cited, removed: event.removed, unverified: event.unverified },
          numbers: event.numbers,
        },
      };
    case "error":
      return { ...turn, status: undefined, error: event.message };
    case "view":
      return { ...turn, status: "Reading your workspace…", details: { ...details, cards: event.cards } };
    case "read": {
      const { area, variable, year } = event;
      return {
        ...turn,
        status: `Looking closer at ${area} ${variable.toUpperCase()}${year ? ` in ${year}` : ""}…`,
        details: { ...details, reads: [...(details.reads ?? []), { area, variable, year }] },
      };
    }
  }
}

export type Part = { text: string } | { cites: number[] } | { number: CheckedNumber };

// Splits an answer into plain text and citation groups such as [1, 3]
export function citationParts(text: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    parts.push({ cites: match[1].split(",").map((n) => Number(n.trim())) });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last) });
  return parts;
}

// Splits an answer into text, citation groups and checked numbers
export function answerParts(text: string, numbers: CheckedNumber[] = []): Part[] {
  const chars = Array.from(text);
  const at = (start: number, end?: number) => chars.slice(start, end).join("");
  // numbers checked on another text (e.g. while still streaming) are not placed
  if (numbers.some((n) => at(n.start, n.end) !== n.text)) return citationParts(text);
  const parts: Part[] = [];
  let last = 0;
  for (const n of [...numbers].sort((a, b) => a.start - b.start)) {
    if (n.start > last) parts.push(...citationParts(at(last, n.start)));
    parts.push({ number: n });
    last = n.end;
  }
  if (last < chars.length) parts.push(...citationParts(at(last)));
  return parts;
}
