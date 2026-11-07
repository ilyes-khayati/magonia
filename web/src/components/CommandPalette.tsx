import { useEffect, useMemo, useRef, useState } from "react";

export type Command = { id: string; label: string; group: string; hint?: string; run: () => void };

// ⌘K: every action by name, typed instead of clicked
export default function CommandPalette({ commands, onClose }: { commands: Command[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => input.current?.focus(), []);

  const shown = useMemo(() => {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    return commands.filter((c) => words.every((w) => `${c.group} ${c.label}`.toLowerCase().includes(w)));
  }, [commands, query]);

  const run = (c: Command | undefined) => {
    if (!c) return;
    onClose();
    c.run();
  };

  return (
    <div className="palette-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="palette" role="dialog" aria-label="Commands">
        <input
          ref={input}
          className="palette-input"
          placeholder="Type a command…"
          aria-label="Command"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndex(Math.min(index + 1, shown.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndex(Math.max(index - 1, 0));
            } else if (e.key === "Enter") run(shown[index]);
            else if (e.key === "Escape") onClose();
          }}
        />
        <ul className="palette-list" role="listbox">
          {shown.map((c, i) => (
            <li key={c.id} role="option" aria-selected={i === index}>
              <button onPointerEnter={() => setIndex(i)} onClick={() => run(c)}>
                <span className="palette-group">{c.group}</span>
                <span>{c.label}</span>
                {c.hint && <kbd>{c.hint}</kbd>}
              </button>
            </li>
          ))}
          {!shown.length && <li className="meta palette-empty">No command matches.</li>}
        </ul>
      </div>
    </div>
  );
}
