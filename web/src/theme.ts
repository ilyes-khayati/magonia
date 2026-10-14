export type Theme = "light" | "dark";

// Area colours, by position in the workspace. Each pair differs in lightness as well
// as hue, and green/blue come first so the first two areas stay apart for
// colour-blind readers. Dark-theme versions are lighter to keep contrast.
const PALETTE: Record<Theme, string[]> = {
  light: ["#2e7d4f", "#2459b8", "#c8571c", "#8e3fa8", "#a07800", "#c2185b"],
  dark: ["#6cc28f", "#6d9df2", "#f08a4b", "#c58ae0", "#e0b84a", "#f0679a"],
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
