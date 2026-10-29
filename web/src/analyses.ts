import type { VariableKey } from "./api";

// The analyses a researcher adds to a workspace. Each kind has its own options; a new kind
// is a new member of the union, an entry in KINDS and a card for the Analyses page.

export type Correlation = {
  kind: "correlation";
  response: VariableKey;
  driver: VariableKey;
  deseasonalise: boolean;
};

export type Decomposition = {
  kind: "decomposition";
  variable: VariableKey;
};

export type Trend = {
  kind: "trend";
  variable: VariableKey;
};

export type Lags = {
  kind: "lags";
  response: VariableKey;
  drivers: VariableKey[];
  deseasonalise: boolean;
  area?: number; // the area studied, saved so that it is still chosen after a reload
};

// A forecast card from before the Model page; read once and turned into an experiment
export type Models = {
  kind: "models";
  response: VariableKey;
  drivers: VariableKey[];
  own_lags: number[] | null; // null: recommended by code
  driver_lags: Partial<Record<VariableKey, number[]>> | null;
  test_years: number;
};

export type AnalysisBody = Correlation | Decomposition | Trend | Lags;

export type Analysis = { id: number } & AnalysisBody;

export type Kind = Analysis["kind"];

type KindInfo = {
  kind: Kind;
  label: string;
  question: string; // what it answers, for the suggestions on an empty page
  description: string;
  // a new analysis of this kind, starting from the variables chosen for the charts
  create: (chosen: VariableKey[]) => AnalysisBody;
};

const ALL: VariableKey[] = ["ndvi", "lst", "spei"];

const other = (key: VariableKey, chosen: VariableKey[]): VariableKey =>
  chosen.find((k) => k !== key) ?? (key === "ndvi" ? "lst" : "ndvi");

export const KINDS: KindInfo[] = [
  {
    kind: "correlation",
    label: "Correlation and lag",
    question: "Does one variable follow another?",
    description: "How closely one variable follows another, 0 to 12 months later.",
    create: (chosen) => {
      const response = chosen[0] ?? "ndvi";
      return { kind: "correlation", response, driver: other(response, chosen), deseasonalise: true };
    },
  },
  {
    kind: "decomposition",
    label: "Trend and season",
    question: "Is it changing over the years, beyond the yearly cycle?",
    description: "Splits a variable into its slow trend and its seasonal cycle with a wavelet, as in the paper.",
    create: (chosen) => ({ kind: "decomposition", variable: chosen[0] ?? "ndvi" }),
  },
  {
    kind: "trend",
    label: "Long-term trend",
    question: "Is it rising or falling over the years, and is that real?",
    description: "The slope of the annual means (Sen) and whether it could be chance (Mann–Kendall).",
    create: (chosen) => ({ kind: "trend", variable: chosen[0] ?? "ndvi" }),
  },
  {
    kind: "lags",
    label: "Memory and lags",
    question: "Which past months matter?",
    description: "Which past months of a variable, and of its drivers, stand out, tested as in the paper.",
    create: (chosen) => {
      const response = chosen[0] ?? "ndvi";
      const others = ALL.filter((k) => k !== response);
      const charted = others.filter((k) => chosen.includes(k));
      return { kind: "lags", response, drivers: charted.length ? charted : others, deseasonalise: true };
    },
  },
];

// The series an analysis needs; a decomposition works at the product's own time step
export type Need = { variable: VariableKey; native: boolean };

export function needsOf(analysis: Analysis): Need[] {
  switch (analysis.kind) {
    case "correlation":
      return [analysis.response, analysis.driver].map((variable) => ({ variable, native: false }));
    case "decomposition":
      return [{ variable: analysis.variable, native: true }];
    case "trend":
      return [{ variable: analysis.variable, native: false }];
    case "lags":
      return [analysis.response, ...analysis.drivers].map((variable) => ({ variable, native: false }));
  }
}

// The variables an analysis needs, fetched whether or not they are charted
export const variablesOf = (analysis: Analysis): VariableKey[] => needsOf(analysis).map((n) => n.variable);

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
