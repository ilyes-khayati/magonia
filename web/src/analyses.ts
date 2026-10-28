import type { VariableKey } from "./api";

// The analyses a researcher adds to a workspace. Each kind has its own options; a new kind
// is a new member of the union, an entry in KINDS and a card for the Analyses page.

export type Correlation = {
  kind: "correlation";
  response: VariableKey;
  driver: VariableKey;
  deseasonalise: boolean;
};

export type Analysis = { id: number } & Correlation;

export type Kind = Analysis["kind"];

type KindInfo = {
  kind: Kind;
  label: string;
  description: string;
  // a new analysis of this kind, starting from the variables chosen for the charts
  create: (chosen: VariableKey[]) => Omit<Analysis, "id">;
};

const other = (key: VariableKey, chosen: VariableKey[]): VariableKey =>
  chosen.find((k) => k !== key) ?? (key === "ndvi" ? "lst" : "ndvi");

export const KINDS: KindInfo[] = [
  {
    kind: "correlation",
    label: "Correlation and lag",
    description: "How closely one variable follows another, 0 to 12 months later.",
    create: (chosen) => {
      const response = chosen[0] ?? "ndvi";
      return { kind: "correlation", response, driver: other(response, chosen), deseasonalise: true };
    },
  },
];

// The variables an analysis needs, fetched whether or not they are charted
export function variablesOf(analysis: Analysis): VariableKey[] {
  switch (analysis.kind) {
    case "correlation":
      return [analysis.response, analysis.driver];
  }
}

export function addAnalysis(analyses: Analysis[], kind: Kind, chosen: VariableKey[]): Analysis[] {
  const id = Math.max(0, ...analyses.map((a) => a.id)) + 1;
  return [...analyses, { id, ...KINDS.find((k) => k.kind === kind)!.create(chosen) }];
}

// Saved analyses of a kind this version does not know are dropped
export function readAnalyses(saved: unknown): Analysis[] {
  if (!Array.isArray(saved)) return [];
  return saved.filter(
    (a): a is Analysis =>
      typeof a === "object" && a !== null && typeof a.id === "number" && KINDS.some((k) => k.kind === a.kind),
  );
}
