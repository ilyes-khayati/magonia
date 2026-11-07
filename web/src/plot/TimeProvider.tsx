import { useMemo, useState, type ReactNode } from "react";
import { HoverContext, TimeContext, type Span } from "./time";

export function TimeProvider({ children, month, onMonth }: { children: ReactNode; month: string | null; onMonth: (m: string | null) => void }) {
  const [zoom, setZoom] = useState<Span | null>(null);
  const [hover, setHover] = useState<Date | null>(null);
  const time = useMemo(() => ({ month, setMonth: onMonth, zoom, setZoom }), [month, onMonth, zoom]);
  const hovered = useMemo(() => ({ hover, setHover }), [hover]);
  return (
    <TimeContext.Provider value={time}>
      <HoverContext.Provider value={hovered}>{children}</HoverContext.Provider>
    </TimeContext.Provider>
  );
}
