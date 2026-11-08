import { useEffect } from "react";
import { NavLink } from "react-router";
import { PAGES, pagePath } from "../pages";
import { MagonMark } from "./Brand";
import { AnalysisIcon, BoardIcon, BookIcon, ChartIcon, MapIcon, ModelIcon } from "./Icons";

const ICONS: Record<Exclude<(typeof PAGES)[number]["key"], "assistant">, (p: { size?: number }) => React.ReactNode> = {
  map: MapIcon,
  data: ChartIcon,
  analyses: AnalysisIcon,
  model: ModelIcon,
  board: BoardIcon,
  library: BookIcon,
};

type Props = {
  workspaceId: number | null;
  magon: { open: boolean; thinking?: boolean; onToggle: () => void };
  workspace: React.ReactNode; // the workspace menu, at the head
  settings: React.ReactNode; // the settings menu, under Magon
};

// An activity bar, as in a code editor: the workspace at the head, one icon per page, and at the
// foot Magon, which opens beside whichever page is open (⌘J or Ctrl+J from anywhere): a
// colleague at hand, not a page of its own. Settings sit under it. Names show on hover.
export default function Rail({ workspaceId, magon, workspace, settings }: Props) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "j" && (e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey) {
        e.preventDefault();
        magon.onToggle();
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [magon]);

  return (
    <nav className="rail" aria-label="Pages">
      {workspace}
      {workspaceId !== null &&
        PAGES.map(({ key, label, title }) => {
          if (key === "assistant") return null;
          const Icon = ICONS[key];
          return (
            <NavLink key={key} to={pagePath(workspaceId, key)} className="rail-link" aria-label={label} title={`${label}: ${title}`}>
              <Icon size={22} />
            </NavLink>
          );
        })}
      <span className="rail-gap" />
      <button
        className="rail-link magon"
        aria-pressed={magon.open}
        aria-label="Magon"
        title={magon.open ? "Close Magon (⌘J)" : "Ask Magon, the research assistant (⌘J)"}
        onClick={magon.onToggle}
      >
        <MagonMark size={30} thinking={magon.thinking} />
      </button>
      {settings}
    </nav>
  );
}
