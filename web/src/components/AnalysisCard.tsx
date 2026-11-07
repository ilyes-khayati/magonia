import type { Analysis } from "../analyses";
import type { SeriesOptions, Variable, VariableKey } from "../api";
import { variableTitle, type Settings } from "../settings";
import type { Entry } from "./ChartCard";
import CorrelationCard from "./CorrelationCard";
import DecompositionCard from "./DecompositionCard";
import LagsCard from "./LagsCard";
import PhenologyCard from "./PhenologyCard";
import CoherenceCard from "./CoherenceCard";
import ScalesCard from "./ScalesCard";
import TrendCard from "./TrendCard";

type Props = {
  analysis: Analysis;
  onChange: (change: Partial<Analysis>) => void;
  onRemove: () => void;
  catalogue: Variable[];
  settings: Settings;
  entries: (variable: VariableKey, native?: boolean) => Entry[];
  options: (areaId: number, variable: VariableKey, native?: boolean) => SeriesOptions;
};

// One analysis as its card, wherever it is shown: the Analyses page or the board
export default function AnalysisCard({ analysis, onChange, onRemove, catalogue, settings, entries, options }: Props) {
  const title = (v: Variable) => variableTitle(v, settings);
  switch (analysis.kind) {
    case "correlation":
      return (
        <CorrelationCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={entries}
          native={(v) => entries(v, true)}
          options={(id, v) => options(id, v, true)}
          seasonal={settings.resolution === "seasonal"}
        />
      );
    case "coherence":
      return (
        <CoherenceCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={entries}
          options={options}
          seasonal={settings.resolution === "seasonal"}
        />
      );
    case "scales":
      return (
        <ScalesCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={entries}
          options={options}
          seasonal={settings.resolution === "seasonal"}
        />
      );
    case "decomposition":
      return (
        <DecompositionCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={entries(analysis.variable, true)}
          options={(areaId) => options(areaId, analysis.variable, true)}
        />
      );
    case "phenology":
      return (
        <PhenologyCard
          name={analysis.name}
          onRename={(name) => onChange({ name })}
          onRemove={() => onRemove()}
          entries={entries("ndvi", true)}
          options={(areaId) => options(areaId, "ndvi", true)}
        />
      );
    case "trend":
      return (
        <TrendCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={entries(analysis.variable)}
          options={(areaId) => options(areaId, analysis.variable)}
        />
      );
    case "lags":
      return (
        <LagsCard
          analysis={analysis}
          onChange={(change) => onChange(change)}
          onRemove={() => onRemove()}
          variables={catalogue}
          title={title}
          entries={(variable) => entries(variable)}
          options={(areaId, variable) => options(areaId, variable)}
          seasonal={settings.resolution === "seasonal"}
        />
      );
  }
}
