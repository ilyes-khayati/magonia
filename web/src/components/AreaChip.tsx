import { useState } from "react";
import type { Area } from "../api";
import ContextMenu from "./ContextMenu";
import { MoreIcon } from "./Icons";

type Props = {
  area: Area;
  colour: string;
  hidden: boolean;
  onZoom: () => void;
  onToggle: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
};

// One area: click its name to go to it, its dot to show or hide it, and ⋯ to rename or delete it
// (with an Undo)
export default function AreaChip({ area, colour, hidden, onZoom, onToggle, onRename, onDelete }: Props) {
  const [editing, setEditing] = useState(false);
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);

  function finish(name: string) {
    setEditing(false);
    if (name.trim() && name.trim() !== area.name) onRename(name.trim());
  }

  return (
    <span className="chip" data-hidden={hidden}>
      <button
        className="dot-button"
        aria-pressed={!hidden}
        aria-label={hidden ? `Show ${area.name}` : `Hide ${area.name}`}
        title={hidden ? "Show on the map" : "Hide from the map"}
        onClick={onToggle}
      >
        <span className="dot" style={{ background: hidden ? "transparent" : colour, borderColor: colour }} />
      </button>
      {editing ? (
        <input
          aria-label={`New name for ${area.name}`}
          defaultValue={area.name}
          autoFocus
          onFocus={(e) => e.currentTarget.select()}
          onBlur={(e) => finish(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") finish(e.currentTarget.value);
            if (e.key === "Escape") setEditing(false);
          }}
        />
      ) : (
        <button className="chip-name" title={`Go to ${area.name}`} onClick={onZoom} onDoubleClick={() => setEditing(true)}>
          <span>{area.name}</span>
          <span className="km2">{area.area_km2 < 10 ? area.area_km2.toFixed(2) : Math.round(area.area_km2)} km²</span>
        </button>
      )}
      <button
        className="remove"
        aria-label={`More for ${area.name}`}
        aria-expanded={menu !== null}
        title="Rename, hide or delete"
        onClick={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          setMenu({ x: box.left, y: box.bottom + 6 });
        }}
      >
        <MoreIcon size={16} />
      </button>
      {menu && (
        <ContextMenu
          x={menu.x}
          y={menu.y}
          onClose={() => setMenu(null)}
          items={[
            { label: "Go to this area", run: onZoom },
            { label: "Rename…", run: () => setEditing(true) },
            { label: hidden ? "Show on the map" : "Hide from the map", run: onToggle },
            "divider",
            { label: "Delete", run: onDelete },
          ]}
        />
      )}
    </span>
  );
}
