import type { Area, SeriesOptions, Variable, VariableKey } from "../api";
import { bodyOf, recipeLine, type Experiment, type Recipe } from "../experiments";
import { useRun } from "../useRun";
import type { Entry } from "./ChartCard";
import { CloseIcon } from "./Icons";
import Results from "./Results";

type Props = {
  experiment: Experiment;
  onChange: (experiment: Experiment) => void;
  onRemove: () => void;
  areas: Area[];
  variables: Variable[];
  title: (v: Variable) => string;
  entries: (variable: VariableKey) => Entry[];
  options: (areaId: number, variable: VariableKey) => SeriesOptions;
};

// A run pinned to the board: its results drawn live from the cache, explainable from here
export default function PinnedExperiment({ experiment: e, onChange, onRemove, areas, variables, title, entries, options }: Props) {
  const name = (key: VariableKey) => {
    const v = variables.find((x) => x.key === key);
    return v ? title(v) : key;
  };
  const ran: Recipe | null = e.ran && { ...e.ran, area: e.ran.area ?? areas[0]?.id ?? null };
  const ready =
    !!ran &&
    ran.area !== null &&
    [ran.response, ...ran.drivers].every((k) => entries(k).find((x) => x.area.id === ran.area)?.state?.status === "done");
  const { fit, why, held } = useRun(ready && ran ? bodyOf(ran, options) : null, e.explain, e.stability);
  return (
    <section className="card" aria-label={e.name}>
      <div className="card-head">
        <div>
          <h3>{e.name}</h3>
          <span className="meta">
            {areas.find((a) => a.id === ran?.area)?.name ?? "no area"} · {ran ? recipeLine(ran, name) : "not run"}
          </span>
        </div>
        <button className="icon-button" aria-label={`Remove ${e.name} from the board`} title="Remove from the board" onClick={onRemove}>
          <CloseIcon size={14} />
        </button>
      </div>
      {!ran ? (
        <p className="placeholder">This experiment had not run when it was pinned.</p>
      ) : !ready ? (
        <p className="placeholder">Waiting for the series of this area to load.</p>
      ) : (
        <Results
          fit={fit}
          why={why}
          explain={e.explain}
          onExplain={() => onChange({ ...e, explain: true })}
          held={held}
          stable={e.stability}
          onStable={() => onChange({ ...e, stability: true })}
          digits={ran.response === "lst" ? 2 : 4}
        />
      )}
    </section>
  );
}
