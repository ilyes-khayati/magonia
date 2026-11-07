import type { VariableKey } from "./api";

// The analyses a researcher adds to a workspace. Each kind has its own options; a new kind
// is a new member of the union, an entry in KINDS and a card for the Analyses page.

// The researcher's own name for an analysis, shown instead of its kind's
type Named = { name?: string };

export type Correlation = Named & {
  kind: "correlation";
  response: VariableKey;
  driver: VariableKey;
  deseasonalise: boolean;
  components?: boolean; // also correlated part by part, after a wavelet decomposition
};

export type Decomposition = Named & {
  kind: "decomposition";
  variable: VariableKey;
};

export type Trend = Named & {
  kind: "trend";
  variable: VariableKey;
};

export type Phenology = Named & { kind: "phenology" }; // always NDVI, the greenness of vegetation

export type Lags = Named & {
  kind: "lags";
  response: VariableKey;
  drivers: VariableKey[];
  deseasonalise: boolean;
  area?: number; // the area studied, saved so that it is still chosen after a reload
};

export type Scales = Named & {
  kind: "scales";
  response: VariableKey;
  deseasonalise: boolean;
  area?: number;
};

export type Coherence = Named & {
  kind: "coherence";
  response: VariableKey;
  driver: VariableKey;
  deseasonalise: boolean;
  area?: number;
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

export type AnalysisBody = Correlation | Decomposition | Trend | Phenology | Lags | Scales | Coherence;

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

// The accumulation scales a drought-scale analysis tries: the short ones crops answer to, and
// the longer ones of trees and groundwater
export const SPEI_SCALES = [1, 2, 3, 4, 6, 9, 12];

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
    description: "Splits a variable into its slow trend and its seasonal cycle with a wavelet (discrete Meyer).",
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
    kind: "phenology",
    label: "Season dates",
    question: "When does the season start, peak and end, and does it shift?",
    description: "Start, peak, end, length and amplitude of each growing season, from NDVI.",
    create: () => ({ kind: "phenology" }),
  },
  {
    kind: "lags",
    label: "Memory and lags",
    question: "Which past months matter?",
    description: "Which past months of a variable, and of its drivers, stand out beyond chance and autocorrelation.",
    create: (chosen) => {
      const response = chosen[0] ?? "ndvi";
      const others = ALL.filter((k) => k !== response);
      const charted = others.filter((k) => chosen.includes(k));
      return { kind: "lags", response, drivers: charted.length ? charted : others, deseasonalise: true };
    },
  },
  {
    kind: "scales",
    label: "Drought scale and lag",
    question: "Which drought scale does it answer to, and how fast?",
    description: "A variable against SPEI at 1 to 12 months of accumulation and 0 to 6 months of lag.",
    create: (chosen) => ({ kind: "scales", response: chosen.find((k) => k !== "spei") ?? "ndvi", deseasonalise: true }),
  },
  {
    kind: "coherence",
    label: "Wavelet coherence",
    question: "When, and at which periods, do two variables move together?",
    description: "Coherence of two variables month by month and period by period, with which one leads.",
    create: (chosen) => {
      const response = chosen[0] ?? "ndvi";
      return { kind: "coherence", response, driver: other(response, chosen), deseasonalise: false };
    },
  },
];

// The series an analysis needs; a decomposition works at the product's own time step
export type Need = { variable: VariableKey; native: boolean; scale?: number }; // scale: a SPEI accumulation other than the chosen one

export function needsOf(analysis: Analysis): Need[] {
  switch (analysis.kind) {
    case "correlation":
      return [analysis.response, analysis.driver].flatMap((variable) => [
        { variable, native: false },
        ...(analysis.components ? [{ variable, native: true }] : []),
      ]);
    case "decomposition":
      return [{ variable: analysis.variable, native: true }];
    case "trend":
      return [{ variable: analysis.variable, native: false }];
    case "phenology":
      return [{ variable: "ndvi", native: true }];
    case "lags":
      return [analysis.response, ...analysis.drivers].map((variable) => ({ variable, native: false }));
    case "coherence":
      return [analysis.response, analysis.driver].map((variable) => ({ variable, native: false }));
    case "scales":
      return [
        { variable: analysis.response, native: false },
        ...SPEI_SCALES.map((scale) => ({ variable: "spei" as const, native: false, scale })),
      ];
  }
}

// The variables an analysis needs, fetched whether or not they are charted
export const variablesOf = (analysis: Analysis): VariableKey[] => needsOf(analysis).map((n) => n.variable);

export function addAnalysis(analyses: Analysis[], kind: Kind, chosen: VariableKey[]): Analysis[] {
  const id = Math.max(0, ...analyses.map((a) => a.id)) + 1;
  return [...analyses, { id, ...KINDS.find((k) => k.kind === kind)!.create(chosen) }];
}

// A copy placed right after the original, to change one thing and compare
export function duplicateAnalysis(analyses: Analysis[], id: number): Analysis[] {
  const index = analyses.findIndex((a) => a.id === id);
  if (index < 0) return analyses;
  const original = analyses[index];
  const name = `${original.name ?? KINDS.find((k) => k.kind === original.kind)!.label} (copy)`;
  const copy: Analysis = { ...structuredClone(original), id: Math.max(0, ...analyses.map((a) => a.id)) + 1, name };
  return [...analyses.slice(0, index + 1), copy, ...analyses.slice(index + 1)];
}

// Saved analyses of a kind this version does not know are dropped
export function readAnalyses(saved: unknown): Analysis[] {
  if (!Array.isArray(saved)) return [];
  return saved.filter(
    (a): a is Analysis =>
      typeof a === "object" && a !== null && typeof a.id === "number" && KINDS.some((k) => k.kind === a.kind),
  );
}
