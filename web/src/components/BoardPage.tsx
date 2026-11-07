import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { BoardItem } from "../board";
import { moved } from "../cards";
import { paint, selectedIn } from "../highlight";
import { AnswerText, Sources } from "./Answer";
import CardSlot from "./CardSlot";
import Cautions from "./Cautions";
import { CloseIcon, PlusIcon } from "./Icons";

type Props = {
  board: BoardItem[];
  onChange: (board: BoardItem[]) => void;
  onRemove: (id: number) => void; // removed with an Undo
  onNote: () => void;
  onSection: () => void;
  pagePath: (page: string) => string | null;
  // the live card for an item, or null to show what was kept when it was pinned
  live: (item: BoardItem, update: (change: Partial<BoardItem>) => void, remove: () => void) => React.ReactNode | null;
};

const FROM: Record<string, string> = { data: "Data", analyses: "Analyses", model: "Model", assistant: "Magon" };

// The research board: findings pinned from anywhere, as they were when pinned, with notes
export default function BoardPage({ board, onChange, onRemove, onNote, onSection, pagePath, live }: Props) {
  const update = (id: number, change: Partial<BoardItem>) => onChange(board.map((b) => (b.id === id ? { ...b, ...change } : b)));

  return (
    <div className="page">
      <div className="page-head">
        <h1>Board</h1>
        <div className="row">
          <button className="button" onClick={onSection}>
            <PlusIcon size={14} />
            Add a section
          </button>
          <button className="primary row" onClick={onNote}>
            <PlusIcon size={14} />
            Add a note
          </button>
        </div>
      </div>

      {!board.length ? (
        <section className="suggestions" aria-label="How to use the board">
          <h2>Pin what you find, and keep it</h2>
          <div className="tiles">
            <div className="tile">
              <strong>Pin a card</strong>
              <span className="meta">Use the pin on any chart or analysis. It stays live here, with the date it was pinned.</span>
            </div>
            <div className="tile">
              <strong>Pin an experiment</strong>
              <span className="meta">On the Model page, Pin keeps a run with its scores and explanations.</span>
            </div>
            <div className="tile">
              <strong>Pin an answer or a passage</strong>
              <span className="meta">
                Pin an answer from Magon with its question, or a single passage from a paper.
              </span>
            </div>
            <button className="tile" onClick={onNote}>
              <strong>Write a note</strong>
              <span className="meta">Ideas, doubts and what to check next. Magon can read your notes.</span>
            </button>
          </div>
        </section>
      ) : (
        <div className="page-grid">
          {board.map((b, i) => (
            <CardSlot
              key={b.id}
              id={String(b.id)}
              label={b.title}
              layout={b.kind === "section" ? { wide: true } : (b.layout ?? {})}
              onLayout={(layout) => update(b.id, { layout })}
              onMove={(step) => onChange(moved(board, i, i + step))}
              onDrop={(from) => onChange(moved(board, board.findIndex((x) => String(x.id) === from), i))}
              image={!!b.source}
            >
              {b.kind === "section" ? (
                <Section
                  b={b}
                  update={(change) => update(b.id, change)}
                  remove={() => onRemove(b.id)}
                />
              ) : (() => {
                const card = b.source
                  ? live(
                      b,
                      (change) => update(b.id, change),
                      () => onRemove(b.id),
                    )
                  : null;
                return card ? (
                  <div className="board-live">
                    <span className="meta row" style={{ justifyContent: "space-between" }}>
                      <span>
                        Pinned {b.pinned}
                        {b.page && pagePath(b.page) && (
                          <>
                            {" · "}
                            <Link to={pagePath(b.page)!}>open {FROM[b.page] ?? b.page}</Link>
                          </>
                        )}
                      </span>
                      <button
                        className="link"
                        aria-label={`Unpin ${b.title}`}
                        onClick={() => onRemove(b.id)}
                      >
                        Unpin
                      </button>
                    </span>
                    {card}
                  </div>
                ) : null;
              })() ?? (
              <Item
                b={b}
                update={(change) => update(b.id, change)}
                remove={() => onRemove(b.id)}
                pagePath={pagePath}
              />
              )}
            </CardSlot>
          ))}
        </div>
      )}
    </div>
  );
}

const KIND: Record<BoardItem["kind"], string> = {
  note: "Note",
  answer: "Magon's answer",
  experiment: "Experiment",
  card: "Card",
  passage: "Passage",
  section: "Section",
};

type ItemProps = {
  b: BoardItem;
  update: (change: Partial<BoardItem>) => void;
  remove: () => void;
  pagePath: (page: string) => string | null;
};

// An item kept as it was pinned: its text, which the researcher can highlight
function Item({ b, update, remove, pagePath }: ItemProps) {
  const card = useRef<HTMLElement>(null);
  const [hint, setHint] = useState("");
  const highlights = b.highlights ?? [];
  // the marks are painted over the text, and again whenever the text or the marks change
  useEffect(() => {
    paint(String(b.id), card.current, highlights);
    return () => paint(String(b.id), null, []);
  });

  function highlight() {
    const text = selectedIn(card.current);
    if (!text) {
      setHint("Select some text in this card first, then click Highlight.");
      return;
    }
    setHint("");
    if (!highlights.includes(text)) update({ highlights: [...highlights, text] });
    window.getSelection()?.removeAllRanges();
  }

  return (
      <section ref={card} className={`card board-item kind-${b.kind}`} aria-label={b.title}>
        <div className="card-head">
          <div>
            {b.kind === "note" ? (
              <input
                className="note-title"
                aria-label="Note title"
                defaultValue={b.title}
                onBlur={(e) => e.target.value.trim() && update({ title: e.target.value.trim() })}
              />
            ) : (
              <h3>{b.title}</h3>
            )}
            <span className="meta">
              {KIND[b.kind]}{" "}
              · pinned {b.pinned}
              {b.page && pagePath(b.page) && (
                <>
                  {" · "}
                  <Link to={pagePath(b.page)!}>open {FROM[b.page] ?? b.page}</Link>
                </>
              )}
            </span>
          </div>
          {b.kind !== "note" && (
            <button
              className="link highlight-button"
              // keep the selection when the button is pressed
              onMouseDown={(e) => e.preventDefault()}
              onClick={highlight}
              title="Select text in this card, then click to highlight it"
            >
              Highlight
            </button>
          )}
          <button
            className="icon-button"
            aria-label={`Remove ${b.title} from the board`}
            title="Remove from the board"
            onClick={remove}
          >
            <CloseIcon size={14} />
          </button>
        </div>
        {b.image && <img className="board-image" src={b.image} alt={`${b.title}, as pinned`} />}
        {b.question && <p className="board-question">“{b.question}”</p>}
        {b.kind === "note" ? (
          <textarea
            className="note-text"
            aria-label="Note"
            rows={4}
            defaultValue={b.lines.join("\n")}
            placeholder="What you noticed, what to check next…"
            onBlur={(e) => update({ lines: e.target.value.split("\n").filter((l) => l.trim()) })}
          />
        ) : b.kind === "passage" ? (
        <blockquote className="board-passage">
          {b.lines.join(" ")}
          {b.link && (
            <>
              {" "}
              <a href={b.link} target="_blank" rel="noreferrer">
                Open the paper
              </a>
            </>
          )}
        </blockquote>
      ) : b.answer ? (
          // a pinned answer keeps its citations, paper links and checked numbers
          <div className="board-answer">
            <div className="answer-text">
              <AnswerText
                text={b.answer.text}
                papers={b.answer.details.papers ?? []}
                numbers={b.answer.details.numbers}
                anchor={`board-${b.id}`}
              />
            </div>
            <Sources turn={{ role: "assistant", content: b.answer.text, details: b.answer.details }} anchor={`board-${b.id}`} />
          </div>
        ) : (
          <ul className="summary">
            {b.lines.map((line, k) => (
              <li key={k}>{line}</li>
            ))}
          </ul>
        )}
        <Cautions items={b.cautions} />
        {hint && <p className="meta">{hint}</p>}
        {highlights.length > 0 && (
          <div className="highlights">
            <span className="meta">Highlighted</span>
            <ul>
              {highlights.map((h, k) => (
                <li key={k}>
                  <mark>{h}</mark>{" "}
                  <button
                    className="link"
                    aria-label={`Remove the highlight "${h.slice(0, 40)}"`}
                    onClick={() => update({ highlights: highlights.filter((x) => x !== h) })}
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
  );
}

// A heading for the items after it, up to the next one
function Section({ b, update, remove }: Omit<ItemProps, "pagePath">) {
  return (
    <div className="board-section" role="group" aria-label={`Section ${b.title}`}>
      <input
        className="section-title"
        aria-label="Section title"
        defaultValue={b.title}
        onBlur={(e) => e.target.value.trim() && update({ title: e.target.value.trim() })}
      />
      <button className="icon-button" aria-label={`Remove the section ${b.title}`} title="Remove the section" onClick={remove}>
        <CloseIcon size={14} />
      </button>
    </div>
  );
}
