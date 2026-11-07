export type Theme = "light" | "dark";
// What the researcher chose: a theme, or the one the system uses
export type ThemeChoice = Theme | "system";

// Area colours, by position in the workspace: the Okabe–Ito palette, chosen to stay apart for
// colour-blind readers and recommended by many journals. The dark theme starts from its lighter
// members so the first areas keep their contrast on a dark background.
const PALETTE: Record<Theme, string[]> = {
  light: ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"],
  dark: ["#56B4E9", "#E69F00", "#2EC4A0", "#E08FC1", "#F0E442", "#FF7A3D"],
};

export const areaColour = (theme: Theme, index: number) =>
  PALETTE[theme][index % PALETTE[theme].length];

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
