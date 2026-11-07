export type Theme = "light" | "dark";

// Area colours, by position in the workspace: the Okabe–Ito palette, chosen to stay apart for
// colour-blind readers and recommended by many journals. The dark theme starts from its lighter
// members so the first areas keep their contrast on a dark background.
const PALETTE: Record<Theme, string[]> = {
  light: ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"],
  dark: ["#56B4E9", "#E69F00", "#2EC4A0", "#E08FC1", "#F0E442", "#FF7A3D"],
};

export const areaColour = (theme: Theme, index: number) =>
  PALETTE[theme][index % PALETTE[theme].length];

export function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("magonia-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // storage unavailable (private window): fall back to the default
  }
  return "light";
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem("magonia-theme", theme);
  } catch {
    // not remembered, but the page still works
  }
}
