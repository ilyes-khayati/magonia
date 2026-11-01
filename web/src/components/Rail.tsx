import { useEffect } from "react";
import { NavLink } from "react-router";
import { PAGES, pagePath } from "../pages";
import { AnalysisIcon, BookIcon, ChartIcon, MagoIcon, MapIcon, ModelIcon, PinIcon } from "./Icons";

const ICONS = {
  map: MapIcon,
  data: ChartIcon,
  analyses: AnalysisIcon,
  model: ModelIcon,
  board: PinIcon,
  library: BookIcon,
  assistant: MagoIcon,
};

type Props = {
  workspaceId: number | null;
  mago: { open: boolean; onToggle: () => void };
};

// The pages of the workbench, and at the foot Mago, which opens beside whichever page is open
// (⌘J or Ctrl+J from anywhere): a colleague at hand, not a page of its own
export default function Rail({ workspaceId, mago }: Props) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "j" && (e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        mago.onToggle();
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [mago]);

  return (
    <nav className="rail" aria-label="Pages">
      {workspaceId !== null &&
        PAGES.filter((p) => p.key !== "assistant").map(({ key, label, title }) => {
          const Icon = ICONS[key];
          return (
            <NavLink key={key} to={pagePath(workspaceId, key)} className="rail-link" title={title}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          );
        })}
      <span className="rail-gap" />
      <button
        className="rail-link mago"
        aria-pressed={mago.open}
        aria-label="Mago"
        title={mago.open ? "Close Mago (⌘J)" : "Ask Mago, the research assistant (⌘J)"}
        onClick={mago.onToggle}
      >
        <MagoIcon size={18} />
        <span>Mago</span>
      </button>
    </nav>
  );
}
