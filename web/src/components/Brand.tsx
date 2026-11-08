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

// Magon is the smallest piece of the pattern: one living spot, three pixels across, brightest at
// its heart. While it thinks, light passes over it, cell by cell.
const SPOT = ["131", "343", "131"];

export function MagonMark({ size = 24, thinking = false, tone = "tile" }: Props & { thinking?: boolean; tone?: "tile" | "ink" }) {
  const id = useId();
  const ink = tone === "ink";
  const pad = ink ? 4 : 18,
    cell = (100 - 2 * pad) / 3,
    gap = cell * (ink ? 0.16 : 0.12);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      aria-hidden="true"
      className={`magon-mark${thinking ? " thinking" : ""}`}
    >
      {!ink && (
        <>
          <defs>
            <clipPath id={`${id}c`}>
              <rect width="100" height="100" rx="22.5" />
            </clipPath>
          </defs>
          <rect width="100" height="100" rx="22.5" fill={GROUND} />
        </>
      )}
      <g clipPath={ink ? undefined : `url(#${id}c)`}>
        {SPOT.map((row, j) =>
          [...row].map((d, i) => {
            const x = pad + i * cell + gap / 2,
              y = pad + j * cell + gap / 2,
              w = cell - gap;
            return (
              <g key={`${i}-${j}`}>
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={w}
                  rx={w * 0.18}
                  fill={ink ? "currentColor" : LEVELS[+d]}
                  opacity={ink ? [0.3, 0.45, 0.6, 0.8, 1][+d] : 1}
                />
                {thinking && (
                  <rect
                    className="glint"
                    x={x}
                    y={y}
                    width={w}
                    height={w}
                    rx={w * 0.18}
                    style={{ animationDelay: `${(i + j) * 0.14}s` }}
                  />
                )}
              </g>
            );
          }),
        )}
      </g>
    </svg>
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
    const cells = size >= 48 ? 16 : size >= 24 ? 10 : 6;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = Math.round(size * dpr);
    el.height = Math.round(size * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const sim = makeSim(Math.max(24, cells * 4), Math.floor(Math.random() * 1e6) + 1);
    step(sim, 700);
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
