import type { SeriesState } from "./useSeries";

export type Input = { name: string; state: SeriesState | undefined };

const list = (names: string[]) =>
  names.length === 1
    ? names[0]
    : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

// What a card says while it cannot show its result: the first series that failed, with the
// reason, or else the series it is still waiting for. A failed series is said once instead
// of leaving the card on "Waiting…" for ever.
export function waitingFor(inputs: Input[]): string {
  for (const input of inputs) {
    if (input.state?.status === "failed")
      return `${input.name} could not be loaded: ${input.state.error}`;
  }
  const names = [
    ...new Set(
      inputs.filter((i) => i.state?.status !== "done").map((i) => i.name),
    ),
  ];
  return names.length ? `Waiting for ${list(names)} to load.` : "Computing…";
}
