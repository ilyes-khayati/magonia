import { createContext, useContext } from "react";
import type { PaperCard } from "./api";

// Where a paper can be read: the researcher's own file inside Magonia, else the open-access PDF
// or the publisher's page in a new tab. #page=6 opens a PDF at page 6 in the browser's viewer.
export type Readable = { title: string; url: string; inside: boolean };

export function whereToRead(paper: Pick<PaperCard, "id" | "doi" | "open_access_url" | "pdf_url" | "short" | "title">, page?: number): Readable | null {
  const at = page ? `#page=${page}` : "";
  if (/^U\d+$/.test(paper.id)) return { title: paper.title, url: `/api/library/${paper.id}/pdf${at}`, inside: true };
  if (paper.pdf_url) return { title: paper.title, url: `${paper.pdf_url}${at}`, inside: false };
  if (paper.doi) return { title: paper.title, url: `https://doi.org/${paper.doi}`, inside: false };
  if (paper.open_access_url) return { title: paper.title, url: paper.open_access_url, inside: false };
  return null;
}

// Opens a paper at a page: provided by the app, used by answers, the board and the library
export const ReaderContext = createContext<((paper: PaperCard, page?: number) => void) | null>(null);
export const useReader = () => useContext(ReaderContext);
