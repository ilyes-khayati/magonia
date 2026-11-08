import { useEffect } from "react";
import { NavLink } from "react-router";
import { PAGES, pagePath } from "../pages";
import { AnalysisIcon, BookIcon, ChartIcon, MagonGradientIcon, MagonIcon, MapIcon, ModelIcon, PinIcon } from "./Icons";

const ICONS = {
  map: MapIcon,
  data: ChartIcon,
  analyses: AnalysisIcon,
  model: ModelIcon,
  board: PinIcon,
  library: BookIcon,
  assistant: MagonIcon,
};

type Props = {
  workspaceId: number | null;
  magon: { open: boolean; onToggle: () => void };
  workspace: React.ReactNode; // the workspace menu, at the head
  settings: React.ReactNode; // the settings menu, under Magon
};

// The workspace at the head, the pages of the workbench, and at the foot Magon, which opens
// beside whichever page is open (⌘J or Ctrl+J from anywhere): a colleague at hand, not a page
// of its own. Settings sit under it.
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
        className="rail-link magon"
        aria-pressed={magon.open}
        aria-label="Magon"
        title={magon.open ? "Close Magon (⌘J)" : "Ask Magon, the research assistant (⌘J)"}
        onClick={magon.onToggle}
      >
        <MagonGradientIcon size={20} />
        <span>Magon</span>
      </button>
      {settings}
    </nav>
  );
}
