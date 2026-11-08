export type Theme = "light" | "dark";
// What the researcher chose: a theme, or the one the system uses
export type ThemeChoice = Theme | "system";

// Area colours, by position in the workspace, taken from fields seen from above: olive, straw,
// river, soil, heather and sky. They differ in lightness as well as hue, so they stay apart for
// colour-blind readers; the dark theme uses lighter members so they keep their contrast.
const PALETTE: Record<Theme, string[]> = {
  light: ["#4f6b2c", "#b07d1f", "#2a6f68", "#8a4a2b", "#7a4a6b", "#4f7fa3"],
  dark: ["#b5cf6b", "#e3b450", "#62b8ac", "#d68d5e", "#c58ab5", "#8fbbd9"],
};

export const areaColour = (theme: Theme, index: number) =>
  PALETTE[theme][index % PALETTE[theme].length];

// Each model keeps one colour on every chart, whatever its rank: the trees in straw and river,
// Ridge in heather, set apart from both
const MODEL_SLOT: Record<string, number> = { XGBoost: 1, RandomForest: 2, Ridge: 4, MLP: 5, LSTM: 3, GRU: 0 };
export const modelColour = (theme: Theme, model: string) => areaColour(theme, MODEL_SLOT[model] ?? 3);

export function initialTheme(): ThemeChoice {
  try {
    const saved = localStorage.getItem("magonia-theme");
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    // storage unavailable (private window): fall back to the default
  }
  return "light";
}

export const systemTheme = (): Theme =>
  typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";

export function applyTheme(choice: ThemeChoice): Theme {
  const theme = choice === "system" ? systemTheme() : choice;
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("magonia-theme", choice);
  } catch {
    // not remembered, but the page still works
  }
  return theme;
}
