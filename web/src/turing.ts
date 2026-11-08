// Magonia's mark is a Turing pattern, the maze that dryland vegetation grows into, measured on a
// pixel grid as a satellite would. The pattern is grown once by the Gray–Scott equations and kept
// as fixed grids for the still mark; the loader grows a fresh one while Magonia works.

// Five levels of green, from bare ground to dense canopy, on a near-black ground
export const LEVELS = ["#132a16", "#2f5420", "#6e9f2e", "#c4ea6a", "#ecfbbf"];
export const GROUND = "#07100a";

// The still mark, grown and frozen: one digit per pixel, by level. A finer grid for larger sizes,
// so the maze keeps the same weight from the favicon to the app icon.
export const GRIDS: Record<number, string[]> = {
  5: ["02431", "24310", "43102", "31024", "10243"],
  7: ["2341034", "4443014", "0134300", "0003421", "4310343", "3430143", "1240042"],
  10: [
    "2234200343",
    "4444300144",
    "3334420013",
    "0113442000",
    "0001344200",
    "1100134421",
    "4431013444",
    "3443001343",
    "1244100342",
    "1134100342",
  ],
  14: [
    "31002343000144",
    "10024443211344",
    "00344334433442",
    "01443113444430",
    "01442001233200",
    "00344100000000",
    "10134410000123",
    "41014431113444",
    "43001443344434",
    "44200234443212",
    "34300134321001",
    "34300244100001",
    "44200243000013",
    "43000343000034",
  ],
};

// The grid for a mark drawn this many pixels wide: about four screen pixels per cell at least
export function gridFor(size: number): string[] {
  return size >= 64 ? GRIDS[14] : size >= 30 ? GRIDS[10] : size >= 20 ? GRIDS[7] : GRIDS[5];
}

export type Sim = {
  n: number;
  u: Float32Array;
  v: Float32Array;
  nu: Float32Array;
  nv: Float32Array;
  random: () => number;
};

const F = 0.0545; // feed and kill rates of the coral, or maze, regime
const K = 0.062;

function random(seed: number) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

const wrap = (i: number, n: number) => ((i % n) + n) % n;

// Plants a few drops of the second chemical, from which the maze grows
export function seed(sim: Sim, cx: number, cy: number, r: number) {
  for (let y = -r; y <= r; y++)
    for (let x = -r; x <= r; x++)
      if (x * x + y * y <= r * r) {
        const i = wrap(cy + y, sim.n) * sim.n + wrap(cx + x, sim.n);
        sim.u[i] = 0.5;
        sim.v[i] = 0.25 + sim.random() * 0.1;
      }
}

// Clears a disc, which the maze then grows back into
export function clear(sim: Sim, cx: number, cy: number, r: number) {
  for (let y = -r; y <= r; y++)
    for (let x = -r; x <= r; x++)
      if (x * x + y * y <= r * r) {
        const i = wrap(cy + y, sim.n) * sim.n + wrap(cx + x, sim.n);
        sim.u[i] = 1;
        sim.v[i] = 0;
      }
}

export function makeSim(n: number, seedValue: number): Sim {
  const size = n * n;
  const sim: Sim = {
    n,
    u: new Float32Array(size).fill(1),
    v: new Float32Array(size),
    nu: new Float32Array(size),
    nv: new Float32Array(size),
    random: random(seedValue),
  };
  const drops = Math.max(3, Math.round(size / 110));
  for (let k = 0; k < drops; k++) seed(sim, Math.floor(sim.random() * n), Math.floor(sim.random() * n), 2);
  return sim;
}

// Advances the reaction and diffusion, on a torus so the pattern has no edges
export function step(sim: Sim, times: number) {
  const n = sim.n;
  for (let t = 0; t < times; t++) {
    const { u, v, nu, nv } = sim;
    for (let y = 0; y < n; y++) {
      const up = wrap(y - 1, n) * n,
        row = y * n,
        down = wrap(y + 1, n) * n;
      for (let x = 0; x < n; x++) {
        const l = wrap(x - 1, n),
          r = wrap(x + 1, n),
          i = row + x;
        const lu =
          -u[i] + 0.2 * (u[row + l] + u[row + r] + u[up + x] + u[down + x]) + 0.05 * (u[up + l] + u[up + r] + u[down + l] + u[down + r]);
        const lv =
          -v[i] + 0.2 * (v[row + l] + v[row + r] + v[up + x] + v[down + x]) + 0.05 * (v[up + l] + v[up + r] + v[down + l] + v[down + r]);
        const uvv = u[i] * v[i] * v[i];
        nu[i] = Math.min(1, Math.max(0, u[i] + lu - uvv + F * (1 - u[i])));
        nv[i] = Math.min(1, Math.max(0, v[i] + 0.5 * lv + uvv - (K + F) * v[i]));
      }
    }
    sim.u = nu;
    sim.nu = u;
    sim.v = nv;
    sim.nv = v;
  }
}

const level = (a: number) => (a < 0.09 ? 0 : a < 0.17 ? 1 : a < 0.24 ? 2 : a < 0.31 ? 3 : 4);

// The pattern averaged into cells × cells pixels, each given one of the five levels
export function pixels(sim: Sim, cells: number): number[] {
  const { n, v } = sim,
    k = n / cells,
    out: number[] = [];
  const at = (x: number, y: number) => v[wrap(Math.floor(y), n) * n + wrap(Math.floor(x), n)];
  for (let j = 0; j < cells; j++)
    for (let i = 0; i < cells; i++) {
      let sum = 0;
      for (const dx of [0.25, 0.75]) for (const dy of [0.25, 0.75]) sum += at((i + dx) * k, (j + dy) * k);
      out.push(level(sum / 4));
    }
  return out;
}
