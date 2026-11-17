// Small helpers shared by every screen. Ports of fmt / calc_ao /
// generate_scramble from cube_timer.py.

export const STATUSES = ["unlearned", "learning", "finished"];
export const SLOWEST_COUNT = 10;
export const MODE_TITLE = { oll: "OLL", pll: "PLL" };

/** Build an element: h("div.card.sel", {onclick}, child, "text", ...). */
export function h(spec, attrs, ...children) {
  const [tag, ...classes] = spec.split(".");
  const el = document.createElement(tag || "div");
  if (classes.length) el.className = classes.join(" ");
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "text") el.textContent = v;
      else if (k === "html") el.innerHTML = v;
      else if (k in el && k !== "list") el[k] = v;
      else el.setAttribute(k, v);
    }
  }
  for (const c of children) if (c != null && c !== false) el.append(c);
  return el;
}

export const titleCase = (s) => s[0].toUpperCase() + s.slice(1);

/** Seconds as M:SS.cc or SS.cc. */
export function fmt(seconds) {
  if (seconds < 60) return seconds.toFixed(2);
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, "0")}`;
}

/** Average of the latest n, trimming best and worst; null if too few. */
export function calcAo(times, n) {
  if (times.length < n) return null;
  const recent = times.slice(0, n).sort((a, b) => a - b);
  if (n <= 2) return recent.reduce((a, b) => a + b, 0) / n;
  return recent.slice(1, -1).reduce((a, b) => a + b, 0) / (n - 2);
}

/** "Last: … │ Best: … │ ao5: … │ ao12: …" for times newest first. */
export function resultBar(times) {
  if (!times || !times.length) return "";
  const parts = [`Last: ${fmt(times[0])}`, `Best: ${fmt(Math.min(...times))}`];
  const a5 = calcAo(times, 5), a12 = calcAo(times, 12);
  if (a5) parts.push(`ao5: ${fmt(a5)}`);
  if (a12) parts.push(`ao12: ${fmt(a12)}`);
  return parts.join("   │   ");
}

const FACES = ["R", "L", "U", "D", "F", "B"];
const MODS = ["", "'", "2"];
const OPPOSITE = { R: "L", L: "R", U: "D", D: "U", F: "B", B: "F" };
const pick = (list) => list[Math.floor(Math.random() * list.length)];

/** WCA-style random scramble - no redundant or cancelling moves. */
export function generateScramble(length = 20) {
  const out = [];
  let last = null, secondLast = null;
  for (let i = 0; i < length; i++) {
    let pool = FACES.filter((f) => f !== last);
    if (secondLast && OPPOSITE[secondLast] === last) pool = pool.filter((f) => f !== secondLast);
    const face = pick(pool);
    out.push(face + pick(MODS));
    [secondLast, last] = [last, face];
  }
  return out.join(" ");
}

export { pick };

/** Weighted random choice (random.choices with weights). */
export function pickWeighted(list, weights) {
  let total = 0;
  for (const w of weights) total += w;
  let r = Math.random() * total;
  for (let i = 0; i < list.length; i++) {
    r -= weights[i];
    if (r < 0) return list[i];
  }
  return list[list.length - 1];
}

/** Group names in the order the cases are listed. */
export const groupOrder = (cases) => [...new Set(cases.map((c) => c.group))];

let toastTimer = null;
export function toast(message) {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}
