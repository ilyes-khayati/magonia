import { NavLink } from "react-router";
import { PAGES, pagePath } from "../pages";
import { AnalysisIcon, ChartIcon, MapIcon, SparkIcon } from "./Icons";

// Magonia is opened from the top bar, not from here
const ICONS = { map: MapIcon, data: ChartIcon, analyses: AnalysisIcon, assistant: SparkIcon };

// The pages of the workbench
export default function Rail({ workspaceId }: { workspaceId: number | null }) {
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
    </nav>
  );
}
