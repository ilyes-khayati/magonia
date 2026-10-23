import { useEffect, useRef, useState } from "react";
import { ask, assistantInfo, clearMessages, listMessages } from "../api";
import { SendIcon } from "./Icons";

type Turn = { role: "user" | "assistant"; content: string };

export default function AssistantCard({
  workspaceId,
}: {
  workspaceId: number | null;
}) {
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
    if (workspaceId !== null) listMessages(workspaceId).then(setTurns).catch(() => undefined);
  }, [workspaceId]);

  useEffect(() => end.current?.scrollIntoView({ block: "nearest" }), [turns]);

  async function submit() {
    const question = draft.trim();
    if (!question || busy || workspaceId === null) return;
    setDraft("");
    setError(null);
    setBusy(true);
    setTurns((t) => [
      ...t,
      { role: "user", content: question },
      { role: "assistant", content: "" },
    ]);
    try {
      await ask(workspaceId, question, (piece) =>
        setTurns((t) => [
          ...t.slice(0, -1),
          { role: "assistant", content: t[t.length - 1].content + piece },
        ]),
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
          <span className="meta">
            {model ? `Answers by ${model}` : "Research assistant"}
          </span>
        </div>
        {turns.length > 0 && (
          <button className="link" onClick={clear} disabled={busy}>
            New conversation
          </button>
        )}
      </div>

      {turns.length > 0 && (
        <div className="conversation" aria-live="polite">
          {turns.map((turn, i) => (
            <div key={i} className={`turn ${turn.role}`}>
              {turn.content ||
                (busy && i === turns.length - 1 ? (
                  <span className="thinking">Thinking…</span>
                ) : (
                  ""
                ))}
            </div>
          ))}
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
          placeholder="Why is the cereal field greener than the orchard in spring?"
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
