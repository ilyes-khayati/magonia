// Magonia's mark is a Turing pattern, the maze that dryland vegetation grows into, measured on a
// pixel grid as a satellite would, inside a round field. The pattern is grown once by the
// Gray–Scott equations and kept as fixed grids for the still marks; the loaders grow a fresh one
// while Magonia or Magon works.

// Five levels of green, from bare ground to dense canopy, on a near-black ground
export const LEVELS = ["#132a16", "#2f5420", "#6e9f2e", "#c4ea6a", "#ecfbbf"];
export const GROUND = "#07100a";

// The mark, grown once and frozen: one digit per pixel, by level, "." outside the field. The field
// is round but not perfect, like real land, and has no outline: its edge is the pixels themselves.
// A finer grid for larger sizes, so the maze keeps its weight from the favicon to the app icon.
export const DISC: Record<number, string[]> = {
  26: [
    "..........................",
    ".......344002430..........",
    ".....10143003420000.......",
    "....4300000134100014......",
    "....34311234443200243.....",
    "...0134444442344323420....",
    "...02443321000244443003...",
    "...44410000000002331014...",
    "...441001233321000000243..",
    "..4200024444444200124444..",
    "..10001443223444334443124.",
    "..00234420000024444310000.",
    ".0144444310000034310001110",
    ".0343113443100034100144443",
    ".0342000344410244001443344",
    ".0143000013443442004430024",
    ".0044332001344430034410014",
    ".014344430002310014410003.",
    ".024212443100000134200034.",
    "..4420014441012334310034..",
    "...44200134334444442134...",
    "....44300034443211444.....",
    ".....44100242000001.......",
    "......430144100111........",
    "........33430034..........",
    "..........................",
  ],
  16: [
    ".....024........",
    "...410243004....",
    "..34300310142...",
    "..434200123430..",
    "..003434444344..",
    "..0034443200244.",
    ".02442000000012.",
    ".344200123331000",
    ".431002444444300",
    ".200024311124434",
    ".003444200000343",
    ".03432343100034.",
    "..441014442004..",
    "...410002442....",
    "....3320014.....",
    "......43........",
  ],
  11: [
    "...400.....",
    "..3400441..",
    ".24420120..",
    ".433420113.",
    ".1003444443",
    ".0014433200",
    "01344100000",
    ".4431013444",
    ".410004444.",
    "..012342...",
    "....44.....",
  ],
  8: [
    "..440...",
    ".034003.",
    ".234301.",
    ".4334200",
    "21003444",
    "00014433",
    ".134410.",
    "..441...",
  ],
};

// The grid for a mark drawn this many pixels wide: cells stay about three screen pixels or more
export function gridFor(size: number): string[] {
  return DISC[size >= 120 ? 26 : size >= 48 ? 16 : size >= 28 ? 11 : 8];
}

// Whether a point of the unit square falls inside the field, for the live mark
export function inDisc(x: number, y: number): boolean {
  const a = Math.atan2(y - 0.5, x - 0.5);
  return Math.hypot(x - 0.5, y - 0.5) < 0.47 * (1 + 0.05 * Math.sin(3 * a + 1) + 0.035 * Math.sin(5 * a));
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
