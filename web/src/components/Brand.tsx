import { useEffect, useId, useRef } from "react";
import { GROUND, LEVELS, clear, gridFor, makeSim, pixels, seed, step } from "../turing";

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

// Magon is a living orb of the same greens: round, because Magon is a mind where Magonia is a
// place. Waves of growth cross it; still at rest, they quicken and ripple out while it thinks.
type Dot = { x: number; y: number; r: number; level: number };

function orbDots(n: number, t: number, thinking: boolean): Dot[] {
  const cell = 100 / n,
    a = t * (thinking ? 0.0022 : 0.0006),
    dots: Dot[] = [];
  for (let j = 0; j < n; j++)
    for (let i = 0; i < n; i++) {
      const x = (i + 0.5) * cell,
        y = (j + 0.5) * cell,
        dx = (x - 50) / 50,
        dy = (y - 50) / 50,
        r = Math.hypot(dx, dy);
      if (r > 0.9) continue;
      const f =
        Math.sin(dx * 3.1 + a * 1.3) +
        Math.sin(dy * 3.7 - a) +
        Math.sin((dx + dy) * 2.3 + a * 0.7) +
        Math.sin(r * 7 - a * (thinking ? 4 : 1.2));
      const v = Math.max(0, Math.min(0.999, ((f + 4) / 8) * (1 - 0.45 * r * r) + 0.12 * (1 - r)));
      dots.push({ x, y, r: n <= 9 ? cell * 0.42 : cell * (0.21 + 0.25 * v), level: Math.floor(v * 5) });
    }
  return dots;
}

const RIM = "rgba(196, 234, 106, 0.22)";

export function MagonMark({ size = 24, thinking = false, tone = "color" }: Props & { thinking?: boolean; tone?: "color" | "ink" }) {
  const n = size >= 40 ? 11 : size >= 24 ? 9 : 7;
  if (thinking && tone === "color") return <ThinkingOrb size={size} n={n} />;
  const dots = orbDots(n, 4000, false);
  const ink = tone === "ink";
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true" className="magon-mark">
      {!ink && <circle cx="50" cy="50" r="50" fill={GROUND} />}
      {dots.map((d, k) => (
        <circle
          key={k}
          cx={d.x}
          cy={d.y}
          r={d.r}
          fill={ink ? "currentColor" : LEVELS[d.level]}
          opacity={ink ? [0.3, 0.45, 0.6, 0.8, 1][d.level] : 1}
        />
      ))}
      {!ink && <circle cx="50" cy="50" r="49" fill="none" stroke={RIM} strokeWidth="2" />}
    </svg>
  );
}

function ThinkingOrb({ size, n }: { size: number; n: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.round(size * dpr);
    el.height = Math.round(size * dpr);
    ctx.setTransform((size * dpr) / 100, 0, 0, (size * dpr) / 100, 0, 0);
    const draw = (t: number) => {
      ctx.clearRect(0, 0, 100, 100);
      ctx.fillStyle = GROUND;
      ctx.beginPath();
      ctx.arc(50, 50, 50, 0, Math.PI * 2);
      ctx.fill();
      for (const d of orbDots(n, t, true)) {
        ctx.fillStyle = LEVELS[d.level];
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.strokeStyle = `rgba(196, 234, 106, ${0.25 + 0.2 * Math.sin(t * 0.006)})`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(50, 50, 49, 0, Math.PI * 2);
      ctx.stroke();
    };
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      draw(4000);
      return;
    }
    let raf = 0;
    const tick = (t: number) => {
      draw(t);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [size, n]);
  return <canvas ref={canvas} className="magon-mark" style={{ width: size, height: size }} aria-hidden="true" />;
}

// The wordmark: lowercase, tightly set, the dot of the i a pixel of the mark
export function Wordmark({ className = "wordmark" }: { className?: string }) {
  return (
    <span className={className}>
      magon<span className="wordmark-i">ı</span>a
    </span>
  );
}

// Shown while Magonia opens a workspace: the mark grows, with the name beside it
export function Opening() {
  return (
    <div className="opening" aria-hidden="true">
      <Growing size={160} />
      <Wordmark />
      <div className="meta shimmer">Opening your workspace…</div>
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
