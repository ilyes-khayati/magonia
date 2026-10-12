import { useState } from "react";
import type { Area } from "../api";
import { CloseIcon } from "./Icons";

type Props = {
  area: Area;
  colour: string;
  hidden: boolean;
  onToggle: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
};

// One area: click to show or hide it, double-click to rename, × twice to delete
export default function AreaChip({ area, colour, hidden, onToggle, onRename, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);

  function finish(name: string) {
    setEditing(false);
    if (name.trim() && name.trim() !== area.name) onRename(name.trim());
  }

  return (
    <span className="chip" data-hidden={hidden}>
      <span className="dot" style={{ background: colour }} />
      {editing ? (
        <input
          aria-label={`New name for ${area.name}`}
          defaultValue={area.name}
          autoFocus
          onBlur={(e) => finish(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") finish(e.currentTarget.value);
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button
          aria-pressed={!hidden}
          title="Click to show or hide, double-click to rename"
          onClick={onToggle}
          onDoubleClick={() => setEditing(true)}
        >
          <span style={{ fontWeight: 500 }}>{area.name}</span>
          <span className="km2">{area.area_km2.toFixed(2)} km²</span>
        </button>
      )}
      <button
        className={confirming ? "remove confirm" : "remove"}
        aria-label={confirming ? `Confirm deleting ${area.name}` : `Delete ${area.name}`}
        onClick={() => (confirming ? onDelete() : setConfirming(true))}
        onBlur={() => setConfirming(false)}
      >
        {confirming ? "Delete?" : <CloseIcon size={14} />}
      </button>
    </span>
  );
}
