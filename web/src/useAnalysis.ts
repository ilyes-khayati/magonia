import { useEffect, useRef, useState } from "react";

export type AnalysisState<T> = { status: "loading" } | { status: "done"; data: T } | { status: "failed"; error: string };

// Runs each analysis request once its series have been extracted, keeping results by request
export function useAnalysis<B, T>(requests: { key: string; body: B }[], run: (body: B) => Promise<T>) {
  const [results, setResults] = useState<Map<string, AnalysisState<T>>>(new Map());
  const started = useRef(new Set<string>());

  useEffect(() => {
    for (const { key, body } of requests) {
      if (started.current.has(key)) continue;
      started.current.add(key);
      const save = (state: AnalysisState<T>) => setResults((old) => new Map(old).set(key, state));
      save({ status: "loading" });
      run(body)
        .then((data) => save({ status: "done", data }))
        .catch((error: Error) => save({ status: "failed", error: error.message }));
    }
  }, [requests, run]);

  return results;
}
