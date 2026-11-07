import { createContext, useContext } from "react";

// One moment shared by every chart and the map: hovering a date on one chart marks it on
// all of them, a click chooses the month the map shows, and a drag zooms them together.
// Hover changes on every mouse move, so it has its own context and only the overlays read it.

export type Span = [Date, Date];

export type Time = {
  month: string | null; // "2020-03"
  setMonth: (month: string | null) => void;
  zoom: Span | null;
  setZoom: (zoom: Span | null) => void;
};

export const TimeContext = createContext<Time>({ month: null, setMonth: () => {}, zoom: null, setZoom: () => {} });
export const HoverContext = createContext<{ hover: Date | null; setHover: (d: Date | null) => void }>({
  hover: null,
  setHover: () => {},
});

export const useTime = () => useContext(TimeContext);
export const useHover = () => useContext(HoverContext);

export const monthOf = (d: Date) => d.toISOString().slice(0, 7);
export const dateOf = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);
