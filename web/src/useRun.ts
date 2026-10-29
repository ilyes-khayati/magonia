import { useMemo } from "react";
import { explainModels, fitModels, type ModelsBody } from "./api";
import { useAnalysis } from "./useAnalysis";

// A run's results, fitted (or read from the cache) when its body is known
export function useRun(body: ModelsBody | null, explain: boolean) {
  const signature = JSON.stringify(body);
  const requests = useMemo(
    () => (signature === "null" ? [] : [{ key: signature, body: JSON.parse(signature) as ModelsBody }]),
    [signature],
  );
  const fit = useAnalysis(requests, fitModels).get(signature);
  const fitted = fit?.status === "done";
  // explaining takes about a minute more, so it is asked for
  const explainRequests = useMemo(() => (explain && fitted ? requests : []), [explain, fitted, requests]);
  const why = useAnalysis(explainRequests, explainModels).get(signature);
  return { fit, why };
}
