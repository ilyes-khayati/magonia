import { NavLink } from "react-router";
import { PAGES, pagePath } from "../pages";
import { AnalysisIcon, ChartIcon, MapIcon, SparkIcon } from "./Icons";

const ICONS = { map: MapIcon, charts: ChartIcon, analyses: AnalysisIcon, assistant: SparkIcon };

// The pages of the workbench
export default function Rail({ workspaceId }: { workspaceId: number | null }) {
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
    </nav>
  );
}
