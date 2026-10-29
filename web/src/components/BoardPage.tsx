import { Link } from "react-router";
import type { BoardItem } from "../board";
import { moved } from "../cards";
import CardSlot from "./CardSlot";
import Cautions from "./Cautions";
import { CloseIcon, PlusIcon } from "./Icons";

type Props = {
  board: BoardItem[];
  onChange: (board: BoardItem[]) => void;
  onNote: () => void;
  pagePath: (page: string) => string | null;
  // the live card for an item, or null to show what was kept when it was pinned
  live: (item: BoardItem, update: (change: Partial<BoardItem>) => void, remove: () => void) => React.ReactNode | null;
};

const FROM: Record<string, string> = { data: "Data", analyses: "Analyses", model: "Model", assistant: "Magonia" };

// The research board: findings pinned from anywhere, as they were when pinned, with notes
export default function BoardPage({ board, onChange, onNote, pagePath, live }: Props) {
  const update = (id: number, change: Partial<BoardItem>) => onChange(board.map((b) => (b.id === id ? { ...b, ...change } : b)));

  return (
    <div className="page">
      <div className="page-head">
        <h1>Board</h1>
        <button className="primary row" onClick={onNote}>
          <PlusIcon size={14} />
          Add a note
        </button>
      </div>

      {!board.length ? (
        <section className="suggestions" aria-label="How to use the board">
          <h2>Pin what you find, and keep it</h2>
          <div className="tiles">
            <div className="tile">
              <strong>Pin a card</strong>
              <span className="meta">The pin in a card&apos;s tools puts the live card here: hover it, change it, dated.</span>
            </div>
            <div className="tile">
              <strong>Pin an experiment</strong>
              <span className="meta">On the Model page, &quot;Pin&quot; puts a run here with its scores and explanations.</span>
            </div>
            <div className="tile">
              <strong>Pin an answer</strong>
              <span className="meta">Under each of Magonia&apos;s answers, &quot;Pin&quot; keeps it with its question.</span>
            </div>
            <button className="tile" onClick={onNote}>
              <strong>Write a note</strong>
              <span className="meta">Ideas, doubts, what to check next. Magonia reads them too.</span>
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
              layout={b.layout ?? {}}
              onLayout={(layout) => update(b.id, { layout })}
              onMove={(step) => onChange(moved(board, i, i + step))}
              onDrop={(from) => onChange(moved(board, board.findIndex((x) => String(x.id) === from), i))}
              image={!!b.source}
            >
              {(() => {
                const card = b.source
                  ? live(
                      b,
                      (change) => update(b.id, change),
                      () => onChange(board.filter((x) => x.id !== b.id)),
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
                        onClick={() => onChange(board.filter((x) => x.id !== b.id))}
                      >
                        Unpin
                      </button>
                    </span>
                    {card}
                  </div>
                ) : null;
              })() ?? (
              <section className={`card board-item kind-${b.kind}`} aria-label={b.title}>
                <div className="card-head">
                  <div>
                    {b.kind === "note" ? (
                      <input
                        className="note-title"
                        aria-label="Note title"
                        defaultValue={b.title}
                        onBlur={(e) => e.target.value.trim() && update(b.id, { title: e.target.value.trim() })}
                      />
                    ) : (
                      <h3>{b.title}</h3>
                    )}
                    <span className="meta">
                      {b.kind === "note" ? "Note" : b.kind === "answer" ? "Magonia's answer" : b.kind === "experiment" ? "Experiment" : "Card"}{" "}
                      · pinned {b.pinned}
                      {b.page && pagePath(b.page) && (
                        <>
                          {" · "}
                          <Link to={pagePath(b.page)!}>open {FROM[b.page] ?? b.page}</Link>
                        </>
                      )}
                    </span>
                  </div>
                  <button
                    className="icon-button"
                    aria-label={`Remove ${b.title} from the board`}
                    title="Remove from the board"
                    onClick={() => onChange(board.filter((x) => x.id !== b.id))}
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
                    onBlur={(e) => update(b.id, { lines: e.target.value.split("\n").filter((l) => l.trim()) })}
                  />
                ) : (
                  <ul className="summary">
                    {b.lines.map((line, k) => (
                      <li key={k}>{line}</li>
                    ))}
                  </ul>
                )}
                <Cautions items={b.cautions} />
              </section>
              )}
            </CardSlot>
          ))}
        </div>
      )}
    </div>
  );
}
