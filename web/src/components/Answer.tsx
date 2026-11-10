import { useReader, whereToRead } from "../reader";
import { type CheckedNumber, type PaperCard, type PassageCard, type ReadStatus, type SupportCheck } from "../api";
import { answerParts, styled, type Turn } from "../chat";

// How one of Magonia's answers is shown, in the chat and when pinned to the board: citations
// as badges that point to their paper cards, numbers marked as checked or not, and sources

// What the paper card says about how much of the paper Magonia read
const READ: Record<ReadStatus, string> = {
  read: "Read in full",
  blocked: "The publisher does not allow downloads, so only the abstract was read",
  unreadable: "The PDF could not be read, so only the abstract was",
  "abstract only": "No open-access PDF, so only the abstract was read",
};

const FLAG = {
  sign: "found only with the opposite sign",
  elsewhere: "found, but for another year, month or variable than the sentence says",
  unverified: "not found in what Magon was given",
};

// A number from the answer: underlined with its source when checked, highlighted when not
function Num({ n }: { n: CheckedNumber }) {
  if (n.status === "verified") {
    return (
      <span className="num verified" title={`From ${n.source}`}>
        {n.text}
      </span>
    );
  }
  const why = n.status === "unverified" ? FLAG.unverified : `${FLAG[n.status]} (${n.source})`;
  return (
    <mark className="num flagged" title={`Check this number: ${why}`}>
      {n.text}
      <span className="visually-hidden"> ({why})</span>
    </mark>
  );
}

// The answer text, with each citation shown as a numbered badge that points to its paper card
// and each checked number marked
type Part = ReturnType<typeof styled>[number];
type Line = { kind: "text" | "bullet" | "number" | "blank"; marker?: string; depth: number; parts: Part[] };

// The answer split into lines, each a paragraph line or a list item with its marker taken off,
// so that lists hang from their markers instead of wrapping under them
function answerLines(parts: Part[]): Line[] {
  const lines: Line[] = [{ kind: "text", depth: 0, parts: [] }];
  for (const part of parts) {
    if (!("text" in part)) {
      lines.at(-1)!.parts.push(part);
      continue;
    }
    part.text.split("\n").forEach((piece, i) => {
      if (i > 0) lines.push({ kind: "text", depth: 0, parts: [] });
      if (piece) lines.at(-1)!.parts.push({ ...part, text: piece });
    });
  }
  return lines.map((line) => {
    const first = line.parts[0];
    if (!first) return { ...line, kind: "blank" };
    if (!("text" in first)) return line;
    const item = /^(\s*)(•|\d+[.)])\s+/.exec(first.text);
    if (!item) return line;
    const rest = { ...first, text: first.text.slice(item[0].length) };
    return {
      kind: item[2] === "•" ? "bullet" : "number",
      marker: item[2] === "•" ? "•" : item[2].replace(")", "."),
      depth: item[1].length >= 2 ? 1 : 0,
      parts: [rest, ...line.parts.slice(1)],
    };
  });
}

export function AnswerText(props: { text: string; papers: PaperCard[]; numbers?: CheckedNumber[]; anchor: string }) {
  const { text, papers, numbers, anchor } = props;
  const read = useReader();
  const show = (part: Part, i: number) => {
    const shown =
      "text" in part ? (
        part.text
      ) : "number" in part ? (
        <Num n={part.number} />
      ) : (
        <span className="cites">
          {part.cites.map((n) => {
            const paper = papers.find((p) => p.n === n);
            const page = "page" in part ? part.page : undefined;
            return (
              <a
                key={n}
                className={page && paper && read && whereToRead(paper, page) ? "cite readable" : "cite"}
                href={`#${anchor}-${n}`}
                title={paper ? `${paper.short}. ${paper.title}${page ? `, p. ${page} (click to open it there)` : ""}` : undefined}
                onClick={(e) => {
                  // a cited page opens the paper at that page; a plain citation goes to the source below
                  if (!page || !paper || !read || !whereToRead(paper, page)) return;
                  e.preventDefault();
                  read(paper, page);
                }}
              >
                {n}
                {page && <span className="cite-page">p. {page}</span>}
              </a>
            );
          })}
        </span>
      );
    return part.bold ? <strong key={i}>{shown}</strong> : <span key={i}>{shown}</span>;
  };
  return (
    <div className="answer-text">
      {answerLines(styled(answerParts(text, numbers))).map((line, i) =>
        line.kind === "blank" ? (
          <div key={i} className="answer-gap" />
        ) : line.kind === "text" ? (
          <p key={i}>{line.parts.map(show)}</p>
        ) : (
          <div key={i} className={`answer-item depth-${line.depth}`}>
            <span className="answer-marker">{line.marker}</span>
            <span>{line.parts.map(show)}</span>
          </div>
        ),
      )}
    </div>
  );
}

type PinPassage = (paper: PaperCard, passage: PassageCard) => void;

type PaperProps = {
  paper: PaperCard;
  anchor: string;
  read?: ReadStatus;
  passages: PassageCard[];
  onPinPassage?: PinPassage;
};

function Paper({ paper, anchor, read, passages, onPinPassage }: PaperProps) {
  const link = paper.doi ? `https://doi.org/${paper.doi}` : paper.open_access_url;
  const open = useReader();
  const readable = open && whereToRead(paper, 1);
  return (
    <li id={`${anchor}-${paper.n}`} className="paper">
      <span className="cite">{paper.n}</span>
      <div>
        <div>
          <strong>{paper.short}.</strong>{" "}
          {link ? (
            <a href={link} target="_blank" rel="noreferrer">
              {paper.title}
            </a>
          ) : (
            paper.title
          )}
          {paper.venue && <span className="meta"> · {paper.venue}</span>}
        </div>
        <span className="meta">
          {read ? READ[read] : paper.open_access_url ? "Open access" : "Abstract only"}
          {paper.cited_by > 0 && ` · cited by ${paper.cited_by}`}
          {paper.countries.length > 0 && ` · ${paper.countries.join(", ")}`}
        </span>
        {paper.matched && paper.matched.length > 0 && (
          <span className="meta matched">Chosen because it mentions {paper.matched.join(", ")}</span>
        )}
        {passages.length > 0 && (
          // what Magonia actually read in this paper, so a statement can be checked at its source
          <details>
            <summary>
              Passages Magon read ({passages.map((p) => `p. ${p.page}`).join(", ")})
            </summary>
            {passages.map((p, k) => (
              <blockquote key={k} className="passage">
                <span className="meta">Page {p.page}</span> {p.text}
                {readable && (
                  <>
                    {" "}
                    <button className="link" aria-label={`Open ${paper.short} at page ${p.page}`} onClick={() => open(paper, p.page)}>
                      Open
                    </button>
                  </>
                )}
                {onPinPassage && (
                  <>
                    {" "}
                    <button
                      className="link"
                      aria-label={`Pin the passage from ${paper.short}, page ${p.page}, to the board`}
                      onClick={() => onPinPassage(paper, p)}
                    >
                      Pin
                    </button>
                  </>
                )}
              </blockquote>
            ))}
          </details>
        )}
        {paper.abstract && (
          <details>
            <summary>Abstract</summary>
            <p>{paper.abstract}</p>
          </details>
        )}
      </div>
    </li>
  );
}

const VERDICT: Record<SupportCheck["status"], { mark: string; label: string }> = {
  supported: { mark: "✓", label: "Supported" },
  unclear: { mark: "?", label: "Partly or not clearly supported" },
  unsupported: { mark: "✗", label: "Not supported" },
};

function Statement({ s }: { s: SupportCheck }) {
  const label = s.status === "unclear" && !s.judged ? "A related passage was found, but not checked" : VERDICT[s.status].label;
  return (
    <li className={`statement ${s.status}`} title={label}>
      <span className="verdict" aria-hidden="true">
        {VERDICT[s.status].mark}
      </span>
      <div>
        <span className="visually-hidden">{label}: </span>
        {s.claim}
        {s.evidence && (
          <blockquote className="passage">
            <span className="meta">Checked against {s.source}</span> {s.evidence}
          </blockquote>
        )}
      </div>
    </li>
  );
}

// Fact check: whether each cited statement says what its papers say
function Support({ support }: { support: SupportCheck[] }) {
  const ok = support.filter((s) => s.status === "supported").length;
  const doubtful = support.filter((s) => s.status !== "supported");
  return (
    <div className="support">
      <span className="meta">
        Fact check: {ok} of {support.length} {support.length === 1 ? "statement is" : "statements are"} supported by
        the {support.length === 1 ? "paper it cites" : "papers they cite"}
      </span>
      {doubtful.length > 0 && <ul className="statements">{doubtful.map((s, k) => <Statement key={k} s={s} />)}</ul>}
      {ok > 0 && (
        <details>
          <summary className="meta">See the supported statements and their passages ({ok})</summary>
          <ul className="statements">
            {support
              .filter((s) => s.status === "supported")
              .map((s, k) => (
                <Statement key={k} s={s} />
              ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// What the answer rests on: the papers it cites, what else was found, and what the check removed
export function Sources({ turn, anchor, onPinPassage }: { turn: Turn; anchor: string; onPinPassage?: PinPassage }) {
  const papers = turn.details.papers ?? [];
  const check = turn.details.check;
  const cards = turn.details.cards ?? [];
  const reads = turn.details.reads ?? [];
  const numbers = turn.details.numbers ?? [];
  const verified = numbers.filter((n) => n.status === "verified");
  const flagged = numbers.filter((n) => n.status !== "verified");
  const unknown = (turn.details.app ?? []).filter((m) => m.status === "unknown");
  const source = cards.length ? "" : (turn.details.route?.source ?? "");
  const cited = check ? check.cited.flatMap((n) => papers.filter((p) => p.n === n)) : [];
  const others = papers.filter((p) => !cited.includes(p));
  const read = turn.details.read ?? {};
  const passages = turn.details.passages ?? [];
  const card = (p: PaperCard) => (
    <Paper
      key={p.n}
      paper={p}
      anchor={anchor}
      read={read[String(p.n)]}
      passages={passages.filter((x) => x.n === p.n).sort((a, b) => a.page - b.page)}
      onPinPassage={onPinPassage}
    />
  );
  const fullText = Object.values(read).filter((r) => r === "read").length;
  if (!papers.length && !check?.removed.length && !check?.unverified.length && !cards.length && !numbers.length && !unknown.length && !source)
    return null;
  return (
    <div className="sources">
      {source && <span className="meta">{source}</span>}
      {cards.length > 0 && (
        <details className="used">
          <summary className="meta">
            Based on {cards.length} {cards.length === 1 ? "item" : "items"} from your workspace
            {reads.length > 0 && ` and ${reads.length} closer ${reads.length === 1 ? "reading" : "readings"}`}
          </summary>
          <ul className="used-list">
            {cards.map((c) => (
              <li key={c}>{c}</li>
            ))}
            {reads.map((r) => (
              <li key={`${r.area}-${r.variable}-${r.year}`}>
                {r.area} {r.variable.toUpperCase()}
                {r.year ? ` ${r.year}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
      {cited.length > 0 && (
        <>
          <span className="meta">
            Sources · each checked against the papers found
            {fullText > 0 && ` · ${fullText === 1 ? "1 paper" : `${fullText} papers`} read in full`}
          </span>
          <ul>{cited.map(card)}</ul>
        </>
      )}
      {others.length > 0 && (
        <details>
          <summary className="meta">
            {cited.length ? `Also found, not cited (${others.length})` : `Papers found (${others.length})`}
          </summary>
          <ul>{others.map(card)}</ul>
        </details>
      )}
      {turn.details.support && turn.details.support.length > 0 && <Support support={turn.details.support} />}
      {check && check.removed.length > 0 && (
        <p className="removed">
          Removed {check.removed.length === 1 ? "a citation" : `${check.removed.length} citations`} (
          {check.removed.map((n) => `[${n}]`).join(", ")}) that matched no paper found.
        </p>
      )}
      {check?.pages_removed && check.pages_removed.length > 0 && (
        <p className="removed">
          Removed {check.pages_removed.length === 1 ? "a page" : "pages"} from{" "}
          {check.pages_removed.join(", ")}: Magon read no passage from{" "}
          {check.pages_removed.length === 1 ? "that page" : "those pages"}.
        </p>
      )}
      {numbers.length > 0 && (
        <span className="meta">
          {verified.length} of {numbers.length} {numbers.length === 1 ? "number" : "numbers"} checked against what
          Magon was given{verified.length ? "; hover one to see where it comes from" : ""}.
        </span>
      )}
      {flagged.length > 0 && (
        <p className="removed">
          {flagged.length === 1 ? "1 number was" : `${flagged.length} numbers were`} not confirmed:{" "}
          {flagged.map((n) => `${n.text} (${FLAG[n.status as keyof typeof FLAG]})`).join(", ")}.
        </p>
      )}
      {unknown.length > 0 && (
        <p className="removed">
          Not in Magonia, so ignore {unknown.length === 1 ? "this name" : "these names"}:{" "}
          {unknown.map((m) => `“${m.text}” ${m.kind}`).join(", ")}.
        </p>
      )}
      {check && check.unverified.length > 0 && (
        <p className="removed">Not among the papers found, so unverified: {check.unverified.join("; ")}.</p>
      )}
    </div>
  );
}

