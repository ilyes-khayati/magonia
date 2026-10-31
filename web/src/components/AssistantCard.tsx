import { useEffect, useRef, useState } from "react";
import {
  ask,
  assistantInfo,
  clearMessages,
  listMessages,
  type PaperCard,
  type PassageCard,
  type Proposal,
  type View,
} from "../api";
import { applyEvent, fromSaved, type Turn } from "../chat";
import { AnswerText, Sources } from "./Answer";
import { SendIcon } from "./Icons";

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

type Props = {
  workspaceId: number | null;
  view?: View; // what is open, sent with each question so the assistant can discuss it
  actions?: React.ReactNode; // controls for where the card is shown, next to its own
  // until the workspace has opened, a question would reach Magonia without the data
  loading?: { opening: boolean; series: number }; // series: how many are still loading
  onPropose?: (proposal: Proposal) => void; // the researcher adds what Magonia proposed
  onPin?: (question: string, turn: Turn) => void; // keep an answer on the board
  onPinPassage?: (paper: PaperCard, passage: PassageCard) => void; // keep one passage
};

export default function AssistantCard(props: Props) {
  const { workspaceId, view, actions, loading, onPropose, onPin, onPinPassage } = props;
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
                {!last && <Sources turn={turn} anchor={anchor} onPinPassage={onPinPassage} />}
                {turn.role === "assistant" && turn.content && !(busy && last) && onPin && (
                  <button
                    className="link pin-answer"
                    onClick={() => onPin(turns[i - 1]?.content ?? "", turn)}
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
