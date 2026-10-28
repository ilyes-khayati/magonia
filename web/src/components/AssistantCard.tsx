import { useEffect, useRef, useState } from "react";
import { ask, assistantInfo, clearMessages, listMessages, type PaperCard, type View } from "../api";
import { applyEvent, citationParts, fromSaved, type Turn } from "../chat";
import { SendIcon } from "./Icons";

// The answer text, with each citation shown as a numbered badge that points to its paper card
function AnswerText({ text, papers, anchor }: { text: string; papers: PaperCard[]; anchor: string }) {
  return (
    <>
      {citationParts(text).map((part, i) =>
        "text" in part ? (
          <span key={i}>{part.text}</span>
        ) : (
          <span key={i} className="cites">
            {part.cites.map((n) => {
              const paper = papers.find((p) => p.n === n);
              return (
                <a key={n} className="cite" href={`#${anchor}-${n}`} title={paper ? `${paper.short}. ${paper.title}` : undefined}>
                  {n}
                </a>
              );
            })}
          </span>
        ),
      )}
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
  const cited = check ? check.cited.flatMap((n) => papers.filter((p) => p.n === n)) : [];
  const others = papers.filter((p) => !cited.includes(p));
  if (!papers.length && !check?.removed.length && !check?.unverified.length && !cards.length) return null;
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
};

export default function AssistantCard({ workspaceId, view, actions }: Props) {
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
    if (!question || busy || workspaceId === null) return;
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
                    <AnswerText text={turn.content} papers={turn.details.papers ?? []} anchor={anchor} />
                  </div>
                )}
                {turn.error && <p className="error">{turn.error}</p>}
                {!last && <Sources turn={turn} anchor={anchor} />}
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
          disabled={busy || !draft.trim()}
        >
          <SendIcon size={15} />
        </button>
      </div>
    </section>
  );
}
