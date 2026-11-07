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

export const MapIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z" />
    <path d="M9 4v14M15 6v14" />
  </Svg>
);

export const ChartIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4v16h16" />
    <path d="M7 15l4-5 3 3 5-7" />
  </Svg>
);

export const AnalysisIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="7" cy="17" r="2" />
    <circle cx="12" cy="9" r="2" />
    <circle cx="18" cy="13" r="2" />
    <circle cx="16" cy="5" r="1.5" />
    <path d="M4 20l16-16" strokeDasharray="2 3" />
  </Svg>
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

export const ModelIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="5" cy="6" r="2" />
    <circle cx="5" cy="18" r="2" />
    <circle cx="19" cy="12" r="2" />
    <path d="M7 6.8l10 4.4M7 17.2l10-4.4" />
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

export const BookIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" />
    <path d="M4 19V5M8 7h7M8 11h5" />
  </Svg>
);

export const CopyIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="8" y="8" width="12" height="12" rx="2" />
    <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
  </Svg>
);

// Magon: an old bearded man with a seedling, after Magon of Carthage, the agronomist; not a chat
// bubble, so the assistant does not read as a chatbot
export const MagonIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4.5 10a5.5 5.5 0 0 1 11 0" />
    <path d="M4.5 10c-.4 1.2.1 2.3 1.1 2.6M15.5 10c.4 1.2-.1 2.3-1.1 2.6" />
    <path d="M5.8 12.4c.5 4.2 2 6.8 4.2 8.6 2.2-1.8 3.7-4.4 4.2-8.6" />
    <path d="M7.5 12.8c1-.8 1.8-.8 2.5 0 .7-.8 1.5-.8 2.5 0" />
    <path d="M7.4 8.9l1.7.5M12.6 8.9l-1.7.5" />
    <path d="M19.5 21c0-4 .2-7 1-10" />
    <path d="M19.8 15.5c-1.6-.4-2.4-1.6-2.3-3 1.5.2 2.4 1.3 2.3 3z" />
    <path d="M20.3 12.5c.3-1.5 1.4-2.3 2.6-2.2-.2 1.4-1.2 2.3-2.6 2.2z" />
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
    <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
    <rect x="14" y="5" width="4" height="4" />
    <rect x="6" y="15" width="4" height="4" />
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
