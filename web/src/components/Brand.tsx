import { useEffect, useId, useRef } from "react";
import { GRIDS, GROUND, LEVELS, clear, gridFor, makeSim, pixels, seed, step } from "../turing";

type Props = { size?: number };

// Magonia's mark: one satellite pixel's worth of Turing pattern, as an app tile. The tile and its
// cells are drawn, not imported, so they stay sharp at every size.
export function MagoniaMark({ size = 28 }: Props) {
  const id = useId();
  const grid = gridFor(size);
  const n = grid.length,
    cell = 100 / n;
  const gap = size / n >= 4 ? cell * 0.1 : 0;
  const rx = size / n >= 6 ? cell * 0.16 : 0;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" className="magonia-mark">
      <defs>
        <clipPath id={`${id}c`}>
          <rect width="100" height="100" rx="22.5" />
        </clipPath>
        <linearGradient id={`${id}g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.16" />
          <stop offset="0.5" stopColor="#ffffff" stopOpacity="0" />
          <stop offset="1" stopColor="#000000" stopOpacity="0.12" />
        </linearGradient>
      </defs>
      <g clipPath={`url(#${id}c)`}>
        <rect width="100" height="100" fill={GROUND} />
        {grid.map((row, j) =>
          [...row].map((d, i) => (
            <rect
              key={`${i}-${j}`}
              x={i * cell + gap / 2}
              y={j * cell + gap / 2}
              width={cell - gap}
              height={cell - gap}
              rx={rx}
              fill={LEVELS[+d]}
            />
          )),
        )}
        {size >= 40 && <rect width="100" height="100" fill={`url(#${id}g)`} />}
      </g>
    </svg>
  );
}

// Magon is the thinking part of Magonia: a brain seen from above, its two halves filled with the
// same grown maze, which on a brain reads as its folds: two greens, so the outline holds on light
// and dark grounds alike. While it thinks, light runs over it.
const BRAIN = [
  "...XXX.XXX...",
  ".XXXXX.XXXXX.",
  ".XXXXX.XXXXX.",
  "XXXXXX.XXXXXX",
  "XXXXXX.XXXXXX",
  "XXXXXX.XXXXXX",
  "XXXXXX.XXXXXX",
  ".XXXXX.XXXXX.",
  ".XXXXX.XXXXX.",
  "..XXXX.XXXX..",
  "...XX...XX...",
];
const SMALL_BRAIN = [".XX.XX.", "XXX.XXX", "XXX.XXX", "XXX.XXX", "XXX.XXX", ".XX.XX."];

export function MagonMark({ size = 24, thinking = false, tone = "color" }: Props & { thinking?: boolean; tone?: "color" | "ink" }) {
  const mask = size >= 28 ? BRAIN : SMALL_BRAIN;
  const folds = size >= 28 ? GRIDS[14] : GRIDS[7];
  const cols = mask[0].length,
    rows = mask.length;
  const cell = 100 / cols,
    top = (100 - rows * cell) / 2;
  const gap = size / cols >= 3 ? cell * 0.1 : 0;
  const ink = tone === "ink";
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" className={`magon-mark${thinking ? " thinking" : ""}`}>
      {mask.map((row, j) =>
        [...row].map((c, i) => {
          if (c !== "X") return null;
          const fold = +folds[j % folds.length][i % folds.length] >= 3;
          const x = i * cell + gap / 2,
            y = top + j * cell + gap / 2,
            w = cell - gap;
          return (
            <g key={`${i}-${j}`}>
              <rect
                x={x}
                y={y}
                width={w}
                height={w}
                rx={w * 0.15}
                fill={ink ? "currentColor" : fold ? "var(--brain-fold)" : "var(--brain)"}
                opacity={ink ? (fold ? 0.55 : 1) : 1}
              />
              {thinking && (
                <rect className="glint" x={x} y={y} width={w} height={w} rx={w * 0.15} style={{ animationDelay: `${(i + j) * 0.06}s` }} />
              )}
            </g>
          );
        }),
      )}
    </svg>
  );
}

// Shown while Magonia opens a workspace: the mark grows, with the name beside it
export function Opening() {
  return (
    <div className="opening" aria-hidden="true">
      <Growing size={160} />
      <div className="wordmark">magonia</div>
      <div className="meta">Opening your workspace…</div>
    </div>
  );
}

// The loader: the mark come alive. A fresh maze grows, is cleared in one place and grows back,
// for as long as the work lasts. With reduced motion it is the still mark.
export function Growing({ size = 20 }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const cells = size >= 120 ? 24 : size >= 48 ? 16 : size >= 24 ? 10 : 6;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.round(size * dpr);
    el.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const sim = makeSim(Math.max(24, cells * 4), Math.floor(Math.random() * 1e6) + 1);
    step(sim, 2400); // past the first spots, to the maze
    const unit = size / cells,
      gap = unit >= 4 ? unit * 0.1 : 0,
      r = size * 0.225;
    const draw = () => {
      const levels = pixels(sim, cells);
      ctx.clearRect(0, 0, size, size);
      ctx.save();
      ctx.beginPath();
      ctx.roundRect(0, 0, size, size, r);
      ctx.clip();
      ctx.fillStyle = GROUND;
      ctx.fillRect(0, 0, size, size);
      levels.forEach((l, k) => {
        ctx.fillStyle = LEVELS[l];
        ctx.fillRect((k % cells) * unit + gap / 2, Math.floor(k / cells) * unit + gap / 2, unit - gap, unit - gap);
      });
      ctx.restore();
    };
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      draw();
      return;
    }
    let frame = 0,
      raf = 0;
    const tick = () => {
      step(sim, 3);
      if (++frame % 240 === 0) {
        const cx = Math.floor(sim.random() * sim.n),
          cy = Math.floor(sim.random() * sim.n);
        clear(sim, cx, cy, Math.round(sim.n / 5));
        seed(sim, cx, cy, 2);
      }
      draw();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [size]);
  return <canvas ref={canvas} className="growing" style={{ width: size, height: size }} aria-hidden="true" />;
}
