import type { AnswerDetails, ChatEvent, ChatMessage } from "./api";

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
        details: { ...details, check: { cited: event.cited, removed: event.removed, unverified: event.unverified } },
      };
    case "error":
      return { ...turn, status: undefined, error: event.message };
  }
}

export type Part = { text: string } | { cites: number[] };

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
