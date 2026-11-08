import { useCallback, useEffect, useRef, useState } from "react";
import {
  ask,
  assistantInfo,
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  renameConversation,
  restoreConversation,
  type Conversation,
  type PaperCard,
  type PassageCard,
  type Proposal,
  type View,
} from "../api";
import { applyEvent, conversationTitle, fromSaved, type Turn } from "../chat";
import { AnswerText, Sources } from "./Answer";
import { MagonMark } from "./Brand";
import { ChevronIcon, CloseIcon, PlusIcon, SendIcon } from "./Icons";

// The conversation open in each workspace is this browser's own convenience
const OPEN = (workspaceId: number) => `magonia-conversation-${workspaceId}`;

function rememberOpen(workspaceId: number, id: number | null) {
  try {
    if (id === null) localStorage.removeItem(OPEN(workspaceId));
    else localStorage.setItem(OPEN(workspaceId), String(id));
  } catch {
    // not remembered; the latest conversation opens next time
  }
}

function rememberedOpen(workspaceId: number): number | null {
  try {
    return Number(localStorage.getItem(OPEN(workspaceId))) || null;
  } catch {
    return null;
  }
}

// "14:05" today, else "3 Oct"
function when(stamp: string): string {
  const d = new Date(stamp);
  return d.toDateString() === new Date().toDateString()
    ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// The conversations of the workspace: open one, start a new one, rename or delete one. A new
// conversation leaves the others as they were.
function Conversations(props: {
  conversations: Conversation[];
  openId: number | null;
  busy: boolean;
  onOpen: (id: number | null) => void;
  onRename: (id: number, title: string) => void;
  onDelete: (c: Conversation) => void;
}) {
  const { conversations, openId, busy, onOpen, onRename, onDelete } = props;
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState<number | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const current = conversations.find((c) => c.id === openId);

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) {
        setOpen(false);
        setRenaming(null);
      }
    };
    document.addEventListener("keydown", close);
    document.addEventListener("mousedown", close);
    return () => {
      document.removeEventListener("keydown", close);
      document.removeEventListener("mousedown", close);
    };
  }, [open]);

  const choose = (id: number | null) => {
    onOpen(id);
    setOpen(false);
  };

  return (
    <div className="conversations-menu" ref={box}>
      <button
        className="conversation-name"
        aria-expanded={open}
        aria-label="Conversations"
        title="Your conversations in this workspace"
        disabled={busy}
        onClick={() => setOpen(!open)}
      >
        <span>{current ? conversationTitle(current) : "New conversation"}</span>
        <ChevronIcon size={13} />
      </button>
      {open && (
        <div className="floating conversations" role="group" aria-label="Conversations">
          <button className="row" onClick={() => choose(null)}>
            <PlusIcon size={14} />
            New conversation
          </button>
          {conversations.length > 0 && <hr />}
          <ul>
            {conversations.map((c) =>
              renaming === c.id ? (
                <li key={c.id}>
                  <form
                    className="rename"
                    onSubmit={(e) => {
                      e.preventDefault();
                      const title = new FormData(e.currentTarget).get("title")?.toString().trim();
                      if (title) onRename(c.id, title);
                      setRenaming(null);
                    }}
                  >
                    <input
                      className="input"
                      name="title"
                      aria-label="Name of the conversation"
                      defaultValue={conversationTitle(c)}
                      autoFocus
                      onKeyDown={(e) => e.key === "Escape" && (e.stopPropagation(), setRenaming(null))}
                    />
                  </form>
                </li>
              ) : (
                <li key={c.id} aria-current={c.id === openId}>
                  <button className="open" onClick={() => choose(c.id)} onDoubleClick={() => setRenaming(c.id)}>
                    <span>{conversationTitle(c)}</span>
                    <span className="meta">{when(c.updated)}</span>
                  </button>
                  <button className="link" aria-label={`Rename ${conversationTitle(c)}`} onClick={() => setRenaming(c.id)}>
                    Rename
                  </button>
                  <button
                    className="icon-button"
                    aria-label={`Delete ${conversationTitle(c)}`}
                    title="Delete"
                    onClick={() => onDelete(c)}
                  >
                    <CloseIcon size={13} />
                  </button>
                </li>
              ),
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// An analysis Magonia proposes: added only when the researcher clicks (AI-07)
function ProposalCard({ proposal, onAdd }: { proposal: Proposal; onAdd?: (p: Proposal) => void }) {
  const [added, setAdded] = useState(false);
  return (
    <div className="proposal" role="group" aria-label={`Proposed: ${proposal.title}`}>
      <div>
        <span className="meta">{proposal.kind === "instruction" ? "Keep as an instruction?" : "Magon proposes"}</span>
        <strong>{proposal.title}</strong>
        {proposal.why && <span className="meta">{proposal.why}</span>}
      </div>
      {added ? (
        <span className="meta">{proposal.kind === "instruction" ? "Saved" : "Added"}</span>
      ) : (
        <button
          className="primary"
          disabled={!onAdd}
          onClick={() => {
            onAdd?.(proposal);
            setAdded(true);
          }}
        >
          {proposal.kind === "instruction" ? "Save" : "Add it"}
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
  onUndoable?: (text: string, undo: () => Promise<void>) => void; // offer to bring back a deletion
  attached?: { title: string; key: number } | null; // the card asked about, sent with the question
  onDetach?: () => void;
};

export default function AssistantCard(props: Props) {
  const { workspaceId, view, actions, loading, onPropose, onPin, onPinPassage, onUndoable, attached, onDetach } = props;
  const box = useRef<HTMLTextAreaElement>(null);

  // a card attached from its page: ready to ask about at once
  useEffect(() => {
    if (attached) box.current?.focus();
  }, [attached]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  // follows the answer as it is written, until the researcher scrolls up to read
  const [following, setFollowing] = useState(true);

  // the model in use, told again when it is changed in Settings
  useEffect(() => {
    const refresh = () =>
      assistantInfo()
        .then((info) => setModel(info.model))
        .catch(() => undefined);
    refresh();
    window.addEventListener("magon-settings", refresh);
    return () => window.removeEventListener("magon-settings", refresh);
  }, []);

  // Each workspace has its own conversations; the card is re-created when the workspace
  // changes. The one open last time opens again, else the latest.
  async function refresh(): Promise<Conversation[]> {
    if (workspaceId === null) return [];
    const all = await listConversations(workspaceId);
    setConversations(all);
    return all;
  }
  // Opens a conversation, or none for a new one: nothing is saved until its first question
  const opened = useRef<number | null>(null);
  const show = useCallback(
    (id: number | null) => {
      opened.current = id;
      setOpenId(id);
      setError(null);
      setTurns([]);
      setFollowing(true);
      if (workspaceId !== null) rememberOpen(workspaceId, id);
      if (id !== null)
        listMessages(id)
          // a slower answer for a conversation left meanwhile is ignored, and a question sent
          // before the history arrived is not wiped out by it
          .then((saved) => opened.current === id && setTurns((t) => (t.length ? t : saved.map(fromSaved))))
          .catch(() => undefined);
    },
    [workspaceId],
  );

  useEffect(() => {
    if (workspaceId === null) return;
    listConversations(workspaceId)
      .then((all) => {
        setConversations(all);
        const last = rememberedOpen(workspaceId);
        const chosen = all.find((c) => c.id === last) ?? all[0];
        if (chosen) show(chosen.id);
      })
      .catch(() => undefined);
  }, [workspaceId, show]);

  async function rename(id: number, title: string) {
    try {
      await renameConversation(id, title);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function remove(c: Conversation) {
    try {
      await deleteConversation(c.id);
      const rest = await refresh();
      if (c.id === openId) show(rest[0]?.id ?? null);
      onUndoable?.(`Conversation “${conversationTitle(c)}” deleted`, async () => {
        await restoreConversation(c.id);
        await refresh();
        show(c.id);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (following && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [turns, following]);

  function scrolled() {
    const el = log.current;
    if (el) setFollowing(el.scrollHeight - el.scrollTop - el.clientHeight < 24);
  }

  async function submit() {
    const question = draft.trim();
    if (!question || busy || workspaceId === null || loading?.opening) return;
    setDraft("");
    setError(null);
    setBusy(true);
    setFollowing(true);
    setTurns((t) => [
      ...t,
      { role: "user", content: question, details: {} },
      { role: "assistant", content: "", details: {} },
    ]);
    try {
      // a new conversation is saved with its first question
      let id = openId;
      if (id === null) {
        id = (await createConversation(workspaceId)).id;
        opened.current = id;
        setOpenId(id);
        rememberOpen(workspaceId, id);
      }
      onDetach?.(); // asked: the next question is about whatever is open again
      await ask(id, question, (event) =>
        setTurns((t) => [...t.slice(0, -1), applyEvent(t[t.length - 1], event)]),
        view,
      );
    } catch (e) {
      setTurns((t) => t.slice(0, -2));
      setDraft(question);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      refresh().catch(() => undefined);
    }
  }

  return (
    <section className="card assistant" aria-label="Magon">
      <div className="card-head">
        <div className="magon-title">
          <MagonMark size={30} thinking={busy} />
          <div>
            <h3>Magon</h3>
            <span className="meta">{model ? `Research assistant · ${model.replace(" (Ollama)", "")}` : "Research assistant"}</span>
          </div>
        </div>
        <div className="row">{actions}</div>
      </div>
      <Conversations
        conversations={conversations}
        openId={openId}
        busy={busy}
        onOpen={show}
        onRename={rename}
        onDelete={remove}
      />

      {turns.length > 0 && (
        <div className="conversation" aria-live="polite" ref={log} onScroll={scrolled}>
          {turns.map((turn, i) => {
            const anchor = `answer-${i}`;
            const last = busy && i === turns.length - 1;
            return turn.role === "user" ? (
              <div key={i} className="turn user">
                <div className="message-head">
                  <span className="avatar" aria-hidden="true">
                    Y
                  </span>
                  <span className="message-name">You</span>
                </div>
                <div className="message-body">{turn.content}</div>
              </div>
            ) : (
              <div key={i} className="turn assistant">
                <div className="message-head">
                  <MagonMark size={22} thinking={last} />
                  <span className="message-name">Magon</span>
                </div>
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
                    className="text-button pin-answer"
                    onClick={() => onPin(turns[i - 1]?.content ?? "", turn)}
                  >
                    Pin to the board
                  </button>
                )}
              </div>
            );
          })}
          {!following && (
            <button
              type="button"
              className="icon-button to-latest"
              aria-label="Go to the latest"
              title="Go to the latest"
              onClick={() => setFollowing(true)}
            >
              <ChevronIcon size={15} />
            </button>
          )}
        </div>
      )}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {loading?.opening ? (
        <p className="meta" role="status">
          Opening your workspace, so that Magon can see it…
        </p>
      ) : loading?.series ? (
        <p className="meta" role="status">
          {loading.series} {loading.series === 1 ? "series is" : "series are"} still loading; Magon sees what has loaded.
        </p>
      ) : null}
      {attached && (
        <div className="attached" role="group" aria-label="Asking about">
          <span className="meta">Asking about</span>
          <strong>{attached.title}</strong>
          <button className="icon-button" aria-label={`Do not ask about ${attached.title}`} title="Ask about everything open instead" onClick={onDetach}>
            <CloseIcon size={12} />
          </button>
        </div>
      )}
      <div className="composer">
        <label htmlFor="ask" className="visually-hidden">
          Ask Magon
        </label>
        <textarea
          ref={box}
          id="ask"
          rows={2}
          value={draft}
          disabled={workspaceId === null}
          placeholder={
            attached ? `What would you like to know about ${attached.title}?` : "When does NDVI peak in my areas, and was any year unusual?"
          }
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          className="send"
          aria-label="Send"
          title="Send (Enter)"
          onClick={submit}
          disabled={busy || !draft.trim() || loading?.opening}
        >
          <SendIcon size={14} />
        </button>
      </div>
      <p className="composer-hint meta">Enter to send · Shift+Enter for a new line</p>
    </section>
  );
}
