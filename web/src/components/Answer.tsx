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
  unverified: "not found in what Magonia was given",
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
  const why = n.status === "sign" ? `${FLAG.sign} (${n.source})` : FLAG.unverified;
  return (
    <mark className="num flagged" title={`Check this number: ${why}`}>
      {n.text}
      <span className="visually-hidden"> ({why})</span>
    </mark>
  );
}

// The answer text, with each citation shown as a numbered badge that points to its paper card
// and each checked number marked
export function AnswerText(props: { text: string; papers: PaperCard[]; numbers?: CheckedNumber[]; anchor: string }) {
  const { text, papers, numbers, anchor } = props;
  return (
    <>
      {styled(answerParts(text, numbers)).map((part, i) => {
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
                    className="cite"
                    href={`#${anchor}-${n}`}
                    title={paper ? `${paper.short}. ${paper.title}${page ? `, p. ${page}` : ""}` : undefined}
                  >
                    {n}
                    {page && <span className="cite-page">p. {page}</span>}
                  </a>
                );
              })}
            </span>
          );
        return part.bold ? <strong key={i}>{shown}</strong> : <span key={i}>{shown}</span>;
      })}
    </>
  );
}

type PaperProps = { paper: PaperCard; anchor: string; read?: ReadStatus; passages: PassageCard[] };

function Paper({ paper, anchor, read, passages }: PaperProps) {
  const link = paper.doi ? `https://doi.org/${paper.doi}` : paper.open_access_url;
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
              Passages Magonia read ({passages.map((p) => `p. ${p.page}`).join(", ")})
            </summary>
            {passages.map((p, k) => (
              <blockquote key={k} className="passage">
                <span className="meta">Page {p.page}</span> {p.text}
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
export function Sources({ turn, anchor }: { turn: Turn; anchor: string }) {
  const papers = turn.details.papers ?? [];
  const check = turn.details.check;
  const cards = turn.details.cards ?? [];
  const reads = turn.details.reads ?? [];
  const numbers = turn.details.numbers ?? [];
  const verified = numbers.filter((n) => n.status === "verified");
  const flagged = numbers.filter((n) => n.status !== "verified");
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
    />
  );
  const fullText = Object.values(read).filter((r) => r === "read").length;
  if (!papers.length && !check?.removed.length && !check?.unverified.length && !cards.length && !numbers.length && !source)
    return null;
  return (
    <div className="sources">
      {source && <span className="meta">{source}</span>}
      {cards.length > 0 && (
        <span className="meta">
          From your workspace: {cards.join(" · ")}
          {reads.length > 0 &&
            ` · looked closer at ${reads
              .map((r) => `${r.area} ${r.variable.toUpperCase()}${r.year ? ` ${r.year}` : ""}`)
              .join(", ")}`}
        </span>
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
          {check.pages_removed.join(", ")}: Magonia read no passage from{" "}
          {check.pages_removed.length === 1 ? "that page" : "those pages"}.
        </p>
      )}
      {numbers.length > 0 && (
        <span className="meta">
          {verified.length} of {numbers.length} {numbers.length === 1 ? "number" : "numbers"} checked against what
          Magonia was given{verified.length ? "; hover one to see where it comes from" : ""}.
        </span>
      )}
      {flagged.length > 0 && (
        <p className="removed">
          {flagged.length === 1 ? "1 number was" : `${flagged.length} numbers were`} not confirmed:{" "}
          {flagged.map((n) => `${n.text} (${FLAG[n.status as "sign" | "unverified"]})`).join(", ")}.
        </p>
      )}
      {check && check.unverified.length > 0 && (
        <p className="removed">Not among the papers found, so unverified: {check.unverified.join("; ")}.</p>
      )}
    </div>
  );
}

