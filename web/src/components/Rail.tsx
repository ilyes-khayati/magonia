import { NavLink } from "react-router";
import { PAGES, pagePath, type Page } from "../pages";
import { AnalysisIcon, ChartIcon, MapIcon, PanelIcon, SparkIcon } from "./Icons";

const ICONS = { map: MapIcon, charts: ChartIcon, analyses: AnalysisIcon, assistant: SparkIcon };

type Props = {
  page: Page;
  workspaceId: number | null;
  docked: boolean;
  onDock: () => void;
};

// The pages of the workbench, and Magonia beside whichever page is open
export default function Rail({ page, workspaceId, docked, onDock }: Props) {
  return (
    <nav className="rail" aria-label="Pages">
      {workspaceId !== null &&
        PAGES.map(({ key, label, title }) => {
          const Icon = ICONS[key];
          return (
            <NavLink key={key} to={pagePath(workspaceId, key)} className="rail-link" title={title}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          );
        })}
      {page !== "assistant" && (
        <button
          className="rail-link dock-toggle"
          aria-pressed={docked}
          title={docked ? "Close Magonia" : "Open Magonia beside this page"}
          onClick={onDock}
        >
          <PanelIcon size={18} />
          <span>Beside</span>
        </button>
      )}
    </nav>
  );
}
