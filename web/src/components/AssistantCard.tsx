import { useEffect, useRef, useState } from "react";
import {
  ask,
  assistantInfo,
  clearMessages,
  listMessages,
  type CheckedNumber,
  type PaperCard,
  type Proposal,
  type View,
} from "../api";
import { answerParts, applyEvent, fromSaved, styled, type Turn } from "../chat";
import { SendIcon } from "./Icons";

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
function AnswerText(props: { text: string; papers: PaperCard[]; numbers?: CheckedNumber[]; anchor: string }) {
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

// An analysis Magonia proposes: added only when the researcher clicks (AI-07)
function ProposalCard({ proposal, onAdd }: { proposal: Proposal; onAdd?: (p: Proposal) => void }) {
  const [added, setAdded] = useState(false);
  return (
    <div className="proposal" role="group" aria-label={`Proposed: ${proposal.title}`}>
      <div>
        <span className="meta">Magonia proposes</span>
        <strong>{proposal.title}</strong>
        {proposal.why && <span className="meta">{proposal.why}</span>}
      </div>
      {added ? (
        <span className="meta">Added</span>
      ) : (
        <button
          className="primary"
          disabled={!onAdd}
          onClick={() => {
            onAdd?.(proposal);
            setAdded(true);
          }}
        >
          Add it
        </button>
      )}
    </div>
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
function Sources({ turn, anchor }: { turn: Turn; anchor: string }) {
  const papers = turn.details.papers ?? [];
  const check = turn.details.check;
  const cards = turn.details.cards ?? [];
  const reads = turn.details.reads ?? [];
  const numbers = turn.details.numbers ?? [];
  const verified = numbers.filter((n) => n.status === "verified");
  const flagged = numbers.filter((n) => n.status !== "verified");
  const cited = check ? check.cited.flatMap((n) => papers.filter((p) => p.n === n)) : [];
  const others = papers.filter((p) => !cited.includes(p));
  if (!papers.length && !check?.removed.length && !check?.unverified.length && !cards.length && !numbers.length)
    return null;
  return (
    <div className="sources">
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

type Props = {
  workspaceId: number | null;
  view?: View; // what is open, sent with each question so the assistant can discuss it
  actions?: React.ReactNode; // controls for where the card is shown, next to its own
  // until the workspace has opened, a question would reach Magonia without the data
  loading?: { opening: boolean; series: number }; // series: how many are still loading
  onPropose?: (proposal: Proposal) => void; // the researcher adds what Magonia proposed
  onPin?: (question: string, answer: string) => void; // keep an answer on the board
};

export default function AssistantCard({ workspaceId, view, actions, loading, onPropose, onPin }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    assistantInfo()
      .then((info) => setModel(info.model))
      .catch(() => undefined);
  }, []);

  // Each workspace has its own conversation; the card is re-created when the workspace changes
  useEffect(() => {
    if (workspaceId !== null)
      listMessages(workspaceId)
        // a question sent before the history arrived must not be wiped out by it
        .then((saved) => setTurns((t) => (t.length ? t : saved.map(fromSaved))))
        .catch(() => undefined);
  }, [workspaceId]);

  // braces matter: newer browsers return a promise from scrollIntoView, which React would
  // take for a clean-up function
  useEffect(() => {
    end.current?.scrollIntoView({ block: "nearest" });
  }, [turns]);

  async function submit() {
    const question = draft.trim();
    if (!question || busy || workspaceId === null || loading?.opening) return;
    setDraft("");
    setError(null);
    setBusy(true);
    setTurns((t) => [
      ...t,
      { role: "user", content: question, details: {} },
      { role: "assistant", content: "", details: {} },
    ]);
    try {
      await ask(workspaceId, question, (event) =>
        setTurns((t) => [...t.slice(0, -1), applyEvent(t[t.length - 1], event)]),
        view,
      );
    } catch (e) {
      setTurns((t) => t.slice(0, -2));
      setDraft(question);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (workspaceId === null) return;
    await clearMessages(workspaceId);
    setTurns([]);
  }

  return (
    <section className="card assistant" aria-label="Magonia assistant">
      <div className="card-head">
        <div>
          <h3>Ask Magonia</h3>
          <span className="meta">{model ? `Answers by ${model} · literature from OpenAlex` : "Research assistant"}</span>
        </div>
        <div className="row">
          {turns.length > 0 && (
            <button className="link" onClick={clear} disabled={busy}>
              New conversation
            </button>
          )}
          {actions}
        </div>
      </div>

      {turns.length > 0 && (
        <div className="conversation" aria-live="polite">
          {turns.map((turn, i) => {
            const anchor = `answer-${i}`;
            const last = busy && i === turns.length - 1;
            return turn.role === "user" ? (
              <div key={i} className="turn user">
                {turn.content}
              </div>
            ) : (
              <div key={i} className="turn assistant">
                {turn.status && <span className="thinking">{turn.status}</span>}
                {!turn.status && !turn.content && last && <span className="thinking">Thinking…</span>}
                {turn.content && (
                  <div>
                    <AnswerText
                      text={turn.content}
                      papers={turn.details.papers ?? []}
                      numbers={turn.details.numbers}
                      anchor={anchor}
                    />
                  </div>
                )}
                {turn.error && <p className="error">{turn.error}</p>}
                {(turn.details.proposals ?? []).map((p, k) => (
                  <ProposalCard key={k} proposal={p} onAdd={onPropose} />
                ))}
                {!last && <Sources turn={turn} anchor={anchor} />}
                {turn.role === "assistant" && turn.content && !(busy && last) && onPin && (
                  <button
                    className="link pin-answer"
                    onClick={() => onPin(turns[i - 1]?.content ?? "", turn.content)}
                  >
                    Pin to the board
                  </button>
                )}
              </div>
            );
          })}
          <div ref={end} />
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {loading?.opening ? (
        <p className="meta" role="status">
          Opening your workspace, so that Magonia can see it…
        </p>
      ) : loading?.series ? (
        <p className="meta" role="status">
          {loading.series} {loading.series === 1 ? "series is" : "series are"} still loading; Magonia sees what has loaded.
        </p>
      ) : null}
      <div className="composer">
        <label htmlFor="ask" className="visually-hidden">
          Ask Magonia
        </label>
        <textarea
          id="ask"
          rows={2}
          value={draft}
          disabled={workspaceId === null}
          placeholder="When does NDVI peak in my areas, and was any year unusual?"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="icon-button round"
          aria-label="Send"
          title="Send (Enter)"
          onClick={submit}
          disabled={busy || !draft.trim() || loading?.opening}
        >
          <SendIcon size={15} />
        </button>
      </div>
    </section>
  );
}
