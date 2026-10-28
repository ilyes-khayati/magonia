import type { Area, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import type { Entry } from "./ChartCard";
import CorrelationCard from "./CorrelationCard";

type Props = {
  catalogue: Variable[];
  settings: Settings;
  areas: Area[];
  entries: (variable: VariableKey) => Entry[];
};

export default function AnalysesPage({ catalogue, settings, areas, entries }: Props) {
  const chosen = catalogue.filter((v) => settings.variables.includes(v.key));

  return (
    <div className="page">
      <div className="page-head">
        <h1>Analyses</h1>
      </div>

      {!areas.length ? (
        <p className="placeholder">Draw or upload an area on the map to begin.</p>
      ) : chosen.length < 2 ? (
        <p className="placeholder">Choose at least two variables on the left to see how they are related.</p>
      ) : (
        <div className="page-grid">
          <CorrelationCard
            variables={chosen}
            title={(v) => variableTitle(v, settings)}
            entries={entries}
            seasonal={settings.resolution === "seasonal"}
          />
        </div>
      )}
    </div>
  );
}
