// Small stroke icons. They are decorative: every button using one has its own label.

type IconProps = { size?: number };

function Svg({ size = 18, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="square"
      strokeLinejoin="miter"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export const PolygonIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 7l7-4 7 5-2 10-9 2z" />
  </Svg>
);

export const RectangleIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="4" y="6" width="16" height="12" rx="1" />
  </Svg>
);

export const UploadIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
  </Svg>
);

export const SearchIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </Svg>
);

export const LayersIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3l9 5-9 5-9-5z" />
    <path d="M3 13l9 5 9-5" />
  </Svg>
);

export const MoonIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Svg>
);

export const SunIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" />
  </Svg>
);

export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const CloseIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

export const InfoIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v6M12 7.5v.5" />
  </Svg>
);

export const ExpandIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
  </Svg>
);

export const SendIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 12l16-8-6 16-2.5-6.5z" />
  </Svg>
);

// The pages' icons, as in a code editor's activity bar: round, soft strokes, each with one dot of
// the mark. When a page opens, its strokes draw themselves in and the dot fills with the accent.
function PageSvg({ size = 22, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="page-icon"
    >
      {children}
    </svg>
  );
}

export const MapIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <path className="draw" pathLength={1} d="M3.5 6.8 9 4.5l6 2.3 5.5-2.3v12.7L15 19.5l-6-2.3-5.5 2.3z" />
    <path className="draw" pathLength={1} d="M9 4.5v12.7M15 6.8v12.7" />
    <circle className="dot" cx="12" cy="11.5" r="1.6" fill="currentColor" stroke="none" />
  </PageSvg>
);

export const ChartIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <path className="draw" pathLength={1} d="M3.5 19.5h17" />
    <path className="draw" pathLength={1} d="M3.5 15.5c1.5-1.8 2.6-4.5 4.4-4.5s2.4 2.6 4 2.6 2.7-4.2 4.6-5.6" />
    <circle className="dot" cx="18.6" cy="6.6" r="1.9" fill="currentColor" stroke="none" />
  </PageSvg>
);

export const AnalysisIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <path className="draw" pathLength={1} d="M3.5 6.5c2-2 4 2 6 0s4-2 6 0 3 1.6 5 .2" />
    <path className="draw" pathLength={1} d="M3.5 13.5 16 11.4" />
    <circle className="dot" cx="18.6" cy="11" r="1.7" fill="currentColor" stroke="none" />
    <path className="draw" pathLength={1} d="M3.5 18.5c1.5-1 3 1 4.5 0s3-1 4.5 0 3 1 4.5 0 3-1 4 0" />
  </PageSvg>
);

// A small neural network: three inputs, two hidden units, one output
export const ModelIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <path className="draw" pathLength={1} d="M6 6l5 2.4M6 6l5 8.6M6 12l5-3.4M6 12l5 3M6 18l5-9.2M6 18l5-2.6M13.6 8.8l4.4 2.6M13.6 15.2l4.4-2.6" strokeWidth={1.1} />
    <circle className="draw" pathLength={1} cx="4.5" cy="6" r="1.7" />
    <circle className="draw" pathLength={1} cx="4.5" cy="12" r="1.7" />
    <circle className="draw" pathLength={1} cx="4.5" cy="18" r="1.7" />
    <circle className="draw" pathLength={1} cx="12.3" cy="8.6" r="1.8" />
    <circle className="draw" pathLength={1} cx="12.3" cy="15.4" r="1.8" />
    <circle className="dot" cx="19.8" cy="12" r="2.3" fill="currentColor" stroke="none" />
  </PageSvg>
);

export const BoardIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <rect className="draw" pathLength={1} x="3.5" y="3.5" width="7.5" height="9.5" rx="2" />
    <rect className="draw" pathLength={1} x="13" y="3.5" width="7.5" height="5.5" rx="2" />
    <rect className="draw" pathLength={1} x="13" y="11" width="7.5" height="9.5" rx="2" />
    <rect className="draw" pathLength={1} x="3.5" y="15" width="7.5" height="5.5" rx="2" />
    <circle className="dot" cx="16.75" cy="15.75" r="1.5" fill="currentColor" stroke="none" />
  </PageSvg>
);

export const BookIcon = (p: IconProps) => (
  <PageSvg {...p}>
    <rect className="draw" pathLength={1} x="3.5" y="4" width="4" height="16" rx="1.2" />
    <rect className="draw" pathLength={1} x="9.5" y="4" width="4" height="16" rx="1.2" />
    <path className="draw" pathLength={1} d="M15.6 5.6 18.9 4.7l3.3 14.5-3.3.9z" />
    <circle className="dot" cx="5.5" cy="7.5" r="1.1" fill="currentColor" stroke="none" />
  </PageSvg>
);

export const ChevronIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);

export const ShrinkIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" />
  </Svg>
);

export const GripIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="9" cy="6" r="1" />
    <circle cx="15" cy="6" r="1" />
    <circle cx="9" cy="12" r="1" />
    <circle cx="15" cy="12" r="1" />
    <circle cx="9" cy="18" r="1" />
    <circle cx="15" cy="18" r="1" />
  </Svg>
);

export const WidthIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 12h18M7 8l-4 4 4 4M17 8l4 4-4 4" />
  </Svg>
);

export const ImageIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="M21 16l-5-5-9 9" />
  </Svg>
);

export const NotebookIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 3h11a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H6z" />
    <path d="M6 3v18M9 8l-2 0M9 12l-2 0M9 16l-2 0M11 8l3 3-3 3" />
  </Svg>
);

export const PinIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 3h6l-1 6 3 3H7l3-3zM12 12v9" />
  </Svg>
);

export const CopyIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="8" y="8" width="12" height="12" rx="2" />
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
  </Svg>
);

export const InspectIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3v5M12 16v5M3 12h5M16 12h5" />
    <rect x="10" y="10" width="4" height="4" />
  </Svg>
);

export const RulerIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 17L17 3l4 4L7 21z" />
    <path d="M7 13l2 2M10 10l2 2M13 7l2 2" />
  </Svg>
);

export const GridIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h16v16H4zM4 9.33h16M4 14.67h16M9.33 4v16M14.67 4v16" />
  </Svg>
);

export const SwipeIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4h16v16H4zM12 2v20" />
    <path d="M8 10l-2 2 2 2M16 10l2 2-2 2" />
  </Svg>
);

export const CoordinatesIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 8V4h4M16 4h4v4M20 16v4h-4M8 20H4v-4" />
    <path d="M12 9v6M9 12h6" />
  </Svg>
);

export const UndoIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 14L4 9l5-5" />
    <path d="M4 9h10a6 6 0 010 12h-3" />
  </Svg>
);

export const RedoIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M15 14l5-5-5-5" />
    <path d="M20 9H10a6 6 0 000 12h3" />
  </Svg>
);

export const SettingsIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="3" />
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
    />
  </Svg>
);

export const FitIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5" />
    <rect x="9" y="9" width="6" height="6" />
  </Svg>
);

export const MoreIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth={2.5} strokeLinecap="round" />
  </Svg>
);
