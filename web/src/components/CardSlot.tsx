import { useRef, useState } from "react";
import type { CardLayout } from "../cards";
import { saveChartImage } from "../chartImage";
import { MagonMark } from "./Brand";
import { ChevronIcon, CopyIcon, GripIcon, ImageIcon, NotebookIcon, PinIcon, WidthIcon } from "./Icons";

type Props = {
  id: string;
  label: string; // the card's name, for the tools' labels
  layout: CardLayout;
  onLayout: (layout: CardLayout) => void;
  onMove: (step: -1 | 1) => void; // with the keyboard: one place earlier or later
  onDrop: (from: string) => void; // another card dropped on this one takes its place
  onNotebook?: () => void; // export the analysis as a notebook that reproduces it
  onPin?: (card: HTMLElement) => void; // keep the card as it is now on the board
  onDuplicate?: () => void; // a copy beside it, to change one thing and compare
  onAsk?: (title: string) => void; // ask Magon about this card, by its title as shown
  image?: boolean; // whether the card has charts to save as an image
  children: React.ReactNode;
};

// A card's place on the page: dragged by its grip (or moved with the arrow keys on it),
// half or full width, and folded to its title
export default function CardSlot(props: Props) {
  const { id, label, layout, onLayout, onMove, onDrop, onNotebook, onPin, onDuplicate, onAsk, image = true, children } = props;
  const slot = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      ref={slot}
      className="slot"
      data-slot={id}
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
        {onAsk && (
          <button
            className="tool-button ask"
            aria-label={`Ask Magon about ${label}`}
            title="Ask Magon about this"
            onClick={() => onAsk(slot.current?.querySelector(".card h3")?.textContent ?? label)}
          >
            <MagonMark size={14} tone="ink" />
          </button>
        )}
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
        {onPin && (
          <button
            className="tool-button"
            aria-label={`Pin ${label} to the board`}
            title="Pin to the board, as it is now"
            onClick={() => {
              const card = slot.current?.querySelector<HTMLElement>(".card");
              if (card) onPin(card);
            }}
          >
            <PinIcon size={14} />
          </button>
        )}
        {onDuplicate && (
          <button
            className="tool-button"
            aria-label={`Duplicate ${label}`}
            title="Duplicate, to change one thing and compare"
            onClick={onDuplicate}
          >
            <CopyIcon size={14} />
          </button>
        )}
        {image && <button
          className="tool-button"
          aria-label={`Save ${label} as an image`}
          title="Save the chart as an image"
          onClick={() => {
            const card = slot.current?.querySelector<HTMLElement>(".card");
            const subtitle = card?.querySelector(".card-head .meta")?.textContent ?? "";
            if (card) saveChartImage(card, card.querySelector("h3")?.textContent ?? label, subtitle);
          }}
        >
          <ImageIcon size={14} />
        </button>}
        {onNotebook && (
          <button
            className="tool-button"
            aria-label={`Export ${label} as a notebook`}
            title="Export as a Python notebook that reproduces it"
            onClick={onNotebook}
          >
            <NotebookIcon size={14} />
          </button>
        )}
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
