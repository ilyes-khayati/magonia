// The workbench's pages; each has its own address, /workspaces/<id>/<page>
export const PAGES = [
  { key: "map", label: "Map", title: "Draw and choose areas and data" },
  { key: "charts", label: "Charts", title: "The chosen variables over time" },
  { key: "analyses", label: "Analyses", title: "Relations between the variables" },
  { key: "assistant", label: "Magonia", title: "Talk with the Magonia assistant" },
] as const;

export type Page = (typeof PAGES)[number]["key"];

export const isPage = (value: string | undefined): value is Page => PAGES.some((p) => p.key === value);

export const pagePath = (workspaceId: number, page: Page) => `/workspaces/${workspaceId}/${page}`;
