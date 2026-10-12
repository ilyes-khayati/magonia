import { useEffect, useRef, useState } from "react";
import { fetchSeries, type SeriesOptions, type SeriesResponse } from "./api";

export type SeriesState =
  | { status: "loading" }
  | { status: "done"; data: SeriesResponse }
  | { status: "failed"; error: string };

// Fetches every requested series once and keeps the results by request, so going
// back to an earlier choice is instant
export type SeriesRequest = { key: string; options: SeriesOptions };

export function useSeries(requests: SeriesRequest[]): Map<string, SeriesState> {
  const [results, setResults] = useState<Map<string, SeriesState>>(new Map());
  const started = useRef(new Set<string>());

  useEffect(() => {
    for (const { key, options } of requests) {
      if (started.current.has(key)) continue;
      started.current.add(key);
      const save = (state: SeriesState) => setResults((old) => new Map(old).set(key, state));
      save({ status: "loading" });
      fetchSeries(options)
        .then((data) => save({ status: "done", data }))
        .catch((error: Error) => {
          started.current.delete(key); // allow a retry on the next change
          save({ status: "failed", error: error.message });
        });
    }
  }, [requests]);

  return results;
}
