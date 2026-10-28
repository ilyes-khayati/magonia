import { useEffect, useRef, useState } from "react";
import { decomposeSeries, type DecompositionResponse, type SeriesOptions } from "./api";

export type DecompositionState =
  | { status: "loading" }
  | { status: "done"; data: DecompositionResponse }
  | { status: "failed"; error: string };

// Decomposes each series once it has been extracted, keeping results by request
export function useDecomposition(requests: { key: string; options: SeriesOptions }[]) {
  const [results, setResults] = useState<Map<string, DecompositionState>>(new Map());
  const started = useRef(new Set<string>());

  useEffect(() => {
    for (const { key, options } of requests) {
      if (started.current.has(key)) continue;
      started.current.add(key);
      const save = (state: DecompositionState) => setResults((old) => new Map(old).set(key, state));
      save({ status: "loading" });
      decomposeSeries(options)
        .then((data) => save({ status: "done", data }))
        .catch((error: Error) => save({ status: "failed", error: error.message }));
    }
  }, [requests]);

  return results;
}
