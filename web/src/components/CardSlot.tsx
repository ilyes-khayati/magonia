import { useRef, useState } from "react";
import type { CardLayout } from "../cards";
import { ChevronIcon, GripIcon, WidthIcon } from "./Icons";

type Props = {
  id: string;
  label: string; // the card's name, for the tools' labels
  layout: CardLayout;
  onLayout: (layout: CardLayout) => void;
  onMove: (step: -1 | 1) => void; // with the keyboard: one place earlier or later
  onDrop: (from: string) => void; // another card dropped on this one takes its place
  children: React.ReactNode;
};

// A card's place on the page: dragged by its grip (or moved with the arrow keys on it),
// half or full width, and folded to its title
export default function CardSlot({ id, label, layout, onLayout, onMove, onDrop, children }: Props) {
  const slot = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      ref={slot}
      className="slot"
      data-wide={layout.wide ?? false}
      data-collapsed={layout.collapsed ?? false}
      data-over={over}
      onDragOver={(e) => {
        if (!e.dataTransfer.types.includes("application/x-magonia-card")) return;
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        const from = e.dataTransfer.getData("application/x-magonia-card");
        if (from && from !== id) onDrop(from);
      }}
    >
      <div className="card-tools" role="group" aria-label={`Arrange ${label}`}>
        <button
          className="tool-button grip"
          draggable
          aria-label={`Move ${label}`}
          title="Drag to move, or use the arrow keys"
          onDragStart={(e) => {
            e.dataTransfer.setData("application/x-magonia-card", id);
            e.dataTransfer.effectAllowed = "move";
            if (slot.current) e.dataTransfer.setDragImage(slot.current, 24, 16);
          }}
          onKeyDown={(e) => {
            const step = e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : 0;
            if (!step) return;
            e.preventDefault();
            onMove(step);
          }}
        >
          <GripIcon size={14} />
        </button>
        <button
          className="tool-button"
          aria-pressed={layout.wide ?? false}
          aria-label={`Full width: ${label}`}
          title={layout.wide ? "Half width" : "Full width"}
          onClick={() => onLayout({ ...layout, wide: !layout.wide })}
        >
          <WidthIcon size={14} />
        </button>
        <button
          className="tool-button fold"
          aria-expanded={!layout.collapsed}
          aria-label={`Show ${label}`}
          title={layout.collapsed ? "Unfold" : "Fold to its title"}
          onClick={() => onLayout({ ...layout, collapsed: !layout.collapsed })}
        >
          <ChevronIcon size={14} />
        </button>
      </div>
      {children}
    </div>
  );
}
