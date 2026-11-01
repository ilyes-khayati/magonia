import { useState } from "react";

type Props = {
  name?: string; // the researcher's own name for it, if given
  fallback: string; // what it is called otherwise, e.g. "Long-term trend"
  onRename?: (name: string | undefined) => void; // an empty name goes back to the fallback
};

// A card's title, renamed by double-clicking it: Enter keeps the name, Escape leaves it
export default function CardTitle({ name, fallback, onRename }: Props) {
  const [editing, setEditing] = useState(false);
  const shown = name || fallback;

  function finish(value: string) {
    setEditing(false);
    const next = value.trim();
    if (next !== shown) onRename?.(next && next !== fallback ? next : undefined);
  }

  if (editing)
    return (
      <input
        className="card-title-input"
        aria-label={`New name for ${shown}`}
        defaultValue={shown}
        autoFocus
        onBlur={(e) => finish(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") finish(e.currentTarget.value);
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  return (
    <h3
      title={onRename ? "Double-click to rename" : undefined}
      onDoubleClick={onRename && (() => setEditing(true))}
    >
      {shown}
    </h3>
  );
}
