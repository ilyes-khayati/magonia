import { type CheckedNumber, type PaperCard } from "../api";
import { answerParts, styled, type Turn } from "../chat";

// How one of Magonia's answers is shown, in the chat and when pinned to the board: citations
// as badges that point to their paper cards, numbers marked as checked or not, and sources

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
                return (
                  <a key={n} className="cite" href={`#${anchor}-${n}`} title={paper ? `${paper.short}. ${paper.title}` : undefined}>
                    {n}
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

function Paper({ paper, anchor }: { paper: PaperCard; anchor: string }) {
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
          {paper.open_access_url ? "Open access" : "Abstract only"}
          {paper.cited_by > 0 && ` · cited by ${paper.cited_by}`}
          {paper.countries.length > 0 && ` · ${paper.countries.join(", ")}`}
        </span>
        {paper.matched && paper.matched.length > 0 && (
          <span className="meta matched">Chosen because it mentions {paper.matched.join(", ")}</span>
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
          <span className="meta">Sources · each checked against the papers found</span>
          <ul>
            {cited.map((p) => (
              <Paper key={p.n} paper={p} anchor={anchor} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <details>
          <summary className="meta">
            {cited.length ? `Also found, not cited (${others.length})` : `Papers found (${others.length})`}
          </summary>
          <ul>
            {others.map((p) => (
              <Paper key={p.n} paper={p} anchor={anchor} />
            ))}
          </ul>
        </details>
      )}
      {check && check.removed.length > 0 && (
        <p className="removed">
          Removed {check.removed.length === 1 ? "a citation" : `${check.removed.length} citations`} (
          {check.removed.map((n) => `[${n}]`).join(", ")}) that matched no paper found.
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

