import type { AnswerDetails, ChatEvent, ChatMessage, CheckedNumber, Conversation } from "./api";

// One message in the conversation as the chat panel shows it
export type Turn = {
  role: "user" | "assistant";
  content: string;
  details: AnswerDetails;
  status?: string; // what the assistant is doing right now, e.g. searching
  error?: string;
};

// The workspace's instructions with one more line, unless it is there already
export function withInstruction(existing: string, instruction: string): string {
  const lines = existing.split("\n").filter((l) => l.trim());
  if (lines.some((l) => l.replace(/^[\s-]+/, "").trim().toLowerCase() === instruction.toLowerCase())) return existing;
  return [...lines, `- ${instruction}`].join("\n");
}

// What a conversation is called: its name, else its first question
export function conversationTitle(c: Pick<Conversation, "title" | "first_question">): string {
  if (c.title) return c.title;
  const q = c.first_question?.trim();
  if (!q) return "New conversation";
  return q.length > 60 ? `${q.slice(0, 57).trimEnd()}…` : q;
}

export const fromSaved = (m: ChatMessage): Turn => ({ role: m.role, content: m.content, details: m.details ?? {} });

// The answer after one more event from the API
export function applyEvent(turn: Turn, event: ChatEvent): Turn {
  const details = turn.details;
  switch (event.type) {
    case "text":
      return { ...turn, content: turn.content + event.text, status: undefined };
    case "rewrite":
      return { ...turn, content: event.text };
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
          check: {
            cited: event.cited,
            removed: event.removed,
            unverified: event.unverified,
            pages_removed: event.pages_removed,
          },
          numbers: event.numbers,
          app: event.app,
          support: event.support,
          faithfulness: event.faithfulness,
        },
      };
    case "error":
      return { ...turn, status: undefined, error: event.message };
    case "view":
      return { ...turn, status: "Reading your workspace…", details: { ...details, cards: event.cards } };
    case "route":
      return { ...turn, details: { ...details, route: { kind: event.kind, source: event.source } } };
    case "verifying":
      return { ...turn, status: "Checking each statement against the paper it cites…" };
    case "reading":
      return { ...turn, status: `Reading ${event.count === 1 ? "1 paper" : `${event.count} papers`} in full…` };
    case "passages":
      return {
        ...turn,
        status: "Writing from the passages found…",
        details: {
          ...details,
          passages: [...(details.passages ?? []), ...event.passages],
          read: { ...details.read, ...event.read },
        },
      };
    case "proposal":
      return { ...turn, details: { ...details, proposals: [...(details.proposals ?? []), event.proposal] } };
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

export type Part = { text: string } | { cites: number[]; page?: number } | { number: CheckedNumber };

// Splits an answer into plain text and citation groups such as [1, 3] or [1, p. 6]
export function citationParts(text: string): Part[] {
  const parts: Part[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+(?:\s*,\s*\d+)*?)(?:,\s*p\.\s*(\d+))?\]/g)) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index) });
    const cites = match[1].split(",").map((n) => Number(n.trim()));
    parts.push(match[2] ? { cites, page: Number(match[2]) } : { cites });
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

export type Styled = Part & { bold?: boolean };

// The little markdown the model writes: **bold**, "# " headings shown bold, and "- " or "* "
// list markers shown as bullets. Done over the parts, so that numbers and citations keep their
// places, and bold may span them.
export function styled(parts: Part[]): Styled[] {
  const out: Styled[] = [];
  let bold = false;
  let heading = false;
  let lineStart = true;
  for (const part of parts) {
    if (!("text" in part)) {
      out.push({ ...part, bold: bold || heading });
      lineStart = false;
      continue;
    }
    const t = part.text;
    let buffer = "";
    const flush = () => {
      if (buffer) out.push({ text: buffer, bold: bold || heading });
      buffer = "";
    };
    let i = 0;
    while (i < t.length) {
      if (t.startsWith("**", i)) {
        flush();
        bold = !bold;
        i += 2;
        lineStart = false;
        continue;
      }
      if (lineStart) {
        const rest = t.slice(i);
        const title = /^#{1,6} +/.exec(rest);
        if (title) {
          flush();
          heading = true;
          i += title[0].length;
          lineStart = false;
          continue;
        }
        const bullet = /^[*-] +/.exec(rest);
        if (bullet) {
          buffer += "• ";
          i += bullet[0].length;
          lineStart = false;
          continue;
        }
      }
      const c = t[i];
      if (c === "\n") {
        flush();
        heading = false;
        buffer += c;
        lineStart = true;
      } else {
        buffer += c;
        if (c !== " " && c !== "\t") lineStart = false;
      }
      i += 1;
    }
    flush();
  }
  // consecutive pieces of the same weight read as one
  return out.reduce<Styled[]>((all, p) => {
    const prev = all.at(-1);
    if (prev && "text" in prev && "text" in p && !!prev.bold === !!p.bold) prev.text += p.text;
    else all.push({ ...p });
    return all;
  }, []);
}
