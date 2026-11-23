// Progress chart for Statistics: x = solve number, y = time.
//   single solves   grey dots (+2: a hollow ring; DNF: an × along the top band)
//   ao5 / ao12      2px lines (blue / orange, validated on the dark surface);
//                   a DNF average breaks the line
//   PB              a ring round the best single, labelled; a dotted step line
//                   traces the PB so far (it drops at each new PB)
//   best averages   a diamond, labelled, where the best ao3 / ao5 / ao12 ended
//                   (ao3 has no line: just its diamond and the readout)
//   sessions        in "All time", a hairline and the session's name where it changes
// Hover (or arrow keys when focused) snaps a crosshair to the nearest solve and
// shows every series there. The Solves table is the non-hover view of the same data.
// Drawn as one path per series, so ~5000 solves stay quick.

import { h, fmt, fmtSolve } from "./util.js";

const SVG = "http://www.w3.org/2000/svg";
// ao3 / ao5 / ao12: palette slots 3 / 1 / 2, validated together on the dark surface
const COLORS = { ao3: "#199e70", ao5: "#3987e5", ao12: "#d95926", single: "#8c8c8c", text: "#dce4ee",
                 muted: "#8c8c8c", grid: "#363636", axis: "#4a4a4a", cross: "#6b6b6b", surface: "#242424" };
const BEST_KEYS = ["ao3", "ao5", "ao12"];
const PAD = { left: 50, right: 70, top: 24, bottom: 30 };
const HEIGHT = 340;
const DNF_BAND = 12;          // y of the DNF markers, inside the top padding

const s = (tag, attrs = {}) => {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
};
const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);

/** Round numbers for an axis from 0 to max: [step, top]. */
function niceScale(max, ticks = 5) {
  if (!(max > 0)) return [1, 1];
  const raw = max / ticks;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw);
  return [step, Math.ceil(max / step) * step];
}

export function progressChart() {
  const legend = h("div.chart-legend");
  const svg = s("svg", { class: "chart-svg", height: HEIGHT, role: "img" });
  const tip = h("div.chart-tip", { hidden: true });
  const empty = h("p.muted", { text: "No solves to chart yet.", hidden: true });
  const wrap = h("div.chart-wrap", { tabindex: 0, "aria-label": "Progress chart; arrow keys move between solves" },
    svg, tip);
  const el = h("div.chart", null, legend, wrap, empty);

  let data = [], sessions = {}, allTime = false, width = 0, hover = -1;
  let pbSoFar = [], pbCount = 0, bestAt = {};
  let x = () => 0, y = () => 0, cross = null, focusDot = null;

  legend.append(
    key("dot", COLORS.single, "Single"), key("ring", COLORS.single, "+2"), key("x", COLORS.muted, "DNF"),
    key("line", COLORS.ao5, "ao5"), key("line", COLORS.ao12, "ao12"), key("pb", COLORS.text, "PB"),
    key("steps", COLORS.text, "PB progression"), key("diamond", COLORS.ao3, "Best ao3"),
    key("diamond", COLORS.ao5, "Best ao5"), key("diamond", COLORS.ao12, "Best ao12"));

  function key(kind, color, label) {
    const k = s("svg", { width: 18, height: 10, class: "key" });
    if (kind === "line") k.append(s("line", { x1: 1, y1: 5, x2: 17, y2: 5, stroke: color, "stroke-width": 2, "stroke-linecap": "round" }));
    else if (kind === "steps") k.append(s("path", { d: "M1 2 H8 V8 H17", fill: "none", stroke: color, "stroke-width": 1.5, "stroke-dasharray": "2 2" }));
    else if (kind === "diamond") k.append(s("path", { d: "M9 0 L14 5 L9 10 L4 5 Z", fill: color }));
    else if (kind === "dot") k.append(s("circle", { cx: 9, cy: 5, r: 3, fill: color }));
    else if (kind === "ring" || kind === "pb") k.append(s("circle", { cx: 9, cy: 5, r: kind === "pb" ? 4 : 3, fill: "none", stroke: color, "stroke-width": 1.5 }));
    else k.append(s("path", { d: "M6 2 L12 8 M12 2 L6 8", stroke: color, "stroke-width": 1.5 }));
    const span = h("span.key-item");
    span.append(k, document.createTextNode(label));
    return span;
  }

  /** rows: newest first (api.solves); names: {session number: name}; all: draw session changes. */
  function update(rows, names = {}, all = false) {
    data = rows.slice().reverse();
    sessions = names;
    allTime = all;
    hover = -1;
    draw();
  }

  function draw() {
    width = Math.max(320, wrap.clientWidth || 800);
    svg.setAttribute("width", width);
    svg.setAttribute("viewBox", `0 0 ${width} ${HEIGHT}`);
    svg.replaceChildren();
    tip.hidden = true;
    empty.hidden = data.length > 0;
    wrap.hidden = !data.length;
    if (!data.length) return;

    const values = data.flatMap((r) => [num(r.time), num(r.ao5), num(r.ao12)]).filter((v) => v != null);
    const [step, top] = niceScale(values.length ? Math.max(...values) : 1);
    const n = data.length;
    const plotW = width - PAD.left - PAD.right, plotH = HEIGHT - PAD.top - PAD.bottom;
    x = (i) => PAD.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
    y = (v) => PAD.top + plotH - (v / top) * plotH;

    // grid and axes: solid hairlines, one shade off the surface
    for (let v = 0; v <= top + 1e-9; v += step) {
      svg.append(s("line", { x1: PAD.left, x2: width - PAD.right, y1: y(v), y2: y(v),
                             stroke: v === 0 ? COLORS.axis : COLORS.grid, "stroke-width": 1 }));
      const t = s("text", { x: PAD.left - 6, y: y(v) + 4, "text-anchor": "end", class: "tick" });
      t.textContent = fmt(v);
      svg.append(t);
    }
    // x ticks every `every` solves (a whole number), plus the last unless it would crowd
    const room = Math.max(2, Math.floor(plotW / 90));
    const every = Math.max(1, Math.ceil((n - 1) / (room - 1)));
    const ticks = [];
    for (let i = 0; i < n; i += every) ticks.push(i);
    if (ticks[ticks.length - 1] !== n - 1) {
      if (n - 1 - ticks[ticks.length - 1] < every / 2 && ticks.length > 1) ticks.pop();
      ticks.push(n - 1);
    }
    for (const i of ticks) {
      const t = s("text", { x: x(i), y: HEIGHT - PAD.bottom + 16, "text-anchor": "middle", class: "tick" });
      t.textContent = `#${data[i].n}`;
      svg.append(t);
    }

    // session changes (all time)
    if (allTime) {
      let lastLabel = -Infinity;
      data.forEach((r, i) => {
        if (i && r.session !== data[i - 1].session) {
          const xs = (x(i - 1) + x(i)) / 2;
          svg.append(s("line", { x1: xs, x2: xs, y1: PAD.top, y2: HEIGHT - PAD.bottom, stroke: COLORS.axis, "stroke-width": 1 }));
          if (xs - lastLabel > 80) {
            const t = s("text", { x: xs + 4, y: HEIGHT - PAD.bottom - 6, class: "session-label" });
            t.textContent = sessions[r.session] || `Session ${r.session}`;
            svg.append(t);
            lastLabel = xs;
          }
        }
      });
    }

    // single solves: dots, +2 rings, DNF crosses (one path each)
    let dots = "", rings = "", crosses = "";
    const r = n > 400 ? 1.8 : 3;
    data.forEach((row, i) => {
      const cx = x(i);
      if (row.penalty === "dnf") {
        crosses += `M${cx - 3} ${DNF_BAND - 3}L${cx + 3} ${DNF_BAND + 3}M${cx + 3} ${DNF_BAND - 3}L${cx - 3} ${DNF_BAND + 3}`;
        return;
      }
      const cy = y(row.time);
      const arc = `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
      if (row.penalty === "+2") rings += arc; else dots += arc;
    });
    svg.append(s("path", { d: dots, fill: COLORS.single, "fill-opacity": 0.75, class: "dots" }),
               s("path", { d: rings, fill: "none", stroke: COLORS.single, "stroke-width": 1.3, class: "rings" }),
               s("path", { d: crosses, stroke: COLORS.muted, "stroke-width": 1.4, class: "dnfs" }));

    // averages: break the line at a missing or DNF average
    for (const keyName of ["ao12", "ao5"]) {
      let d = "", pen = false, last = -1;
      data.forEach((row, i) => {
        const v = num(row[keyName]);
        if (v == null) { pen = false; return; }
        d += `${pen ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`;
        pen = true;
        last = i;
      });
      if (!d) continue;
      svg.append(s("path", { d, fill: "none", stroke: COLORS[keyName], "stroke-width": 2,
                             "stroke-linejoin": "round", "stroke-linecap": "round", class: `line-${keyName}` }));
      // direct label at the end of the line
      const t = s("text", { x: x(last) + 8, y: y(num(data[last][keyName])) + 4, class: "end-label" });
      t.textContent = `${keyName} ${fmt(data[last][keyName])}`;
      svg.append(t);
    }
    spreadEndLabels();

    // PB progression: the best single so far, as a dotted step line
    let best = -1, steps = "";
    pbSoFar = data.map((row, i) => {
      if (num(row.time) == null) return best < 0 ? null : data[best].time;
      if (best < 0 || row.time < data[best].time) {
        steps += best < 0 ? `M${x(i).toFixed(1)} ${y(row.time).toFixed(1)}`
                          : `H${x(i).toFixed(1)}V${y(row.time).toFixed(1)}`;
        best = i;
      }
      return data[best].time;
    });
    if (best >= 0) {
      steps += `H${x(n - 1).toFixed(1)}`;
      svg.append(s("path", { d: steps, fill: "none", stroke: COLORS.text, "stroke-opacity": 0.7, "stroke-width": 1.5,
                             "stroke-dasharray": "2 3", class: "pb-steps" }));
    }
    pbCount = new Set(pbSoFar.filter((v) => v != null)).size;

    // labels placed so they don't cover each other: [x, y, width] of each one so far
    const placed = [...svg.querySelectorAll(".end-label")].map((t) => {
      const w = t.textContent.length * 6.6 + 6;
      return [Number(t.getAttribute("x")) + w / 2, Number(t.getAttribute("y")) - 4, w];
    });
    const label = (cx, cy, text, cls, prefer) => {
      const w = text.length * 6.6 + 6;
      const tries = prefer === "below" ? [18, -12, 32, -26, 46] : [-12, 18, -26, 32, -40, 46];
      let ty = cy + tries[0];
      for (const dy of tries) {
        const yy = cy + dy;
        if (yy < PAD.top - 4 || yy > HEIGHT - PAD.bottom + 2) continue;
        if (!placed.some(([px, py, pw]) => Math.abs(px - cx) < (pw + w) / 2 && Math.abs(py - yy) < 13)) { ty = yy; break; }
      }
      // keep it inside the plot horizontally
      const lx = Math.min(Math.max(cx, PAD.left + w / 2), width - w / 2 - 2);
      placed.push([lx, ty, w]);
      const t = s("text", { x: lx, y: ty + 4, "text-anchor": "middle", class: cls });
      t.textContent = text;
      svg.append(t);
    };

    // personal best
    if (best >= 0) {
      svg.append(s("circle", { cx: x(best), cy: y(data[best].time), r: 6, fill: "none", stroke: COLORS.text, "stroke-width": 1.5, class: "pb" }));
      label(x(best), y(data[best].time), `PB ${fmt(data[best].time)}`, "pb-label", "below");
    }

    // best ao3 / ao5 / ao12: a diamond with a 2px surface ring where each ended
    bestAt = {};
    for (const k of BEST_KEYS) {
      let b = -1;
      data.forEach((row, i) => { const v = num(row[k]); if (v != null && (b < 0 || v < data[b][k])) b = i; });
      if (b < 0) continue;
      bestAt[k] = b;
      const cx = x(b), cy = y(data[b][k]), d = 5.5;
      svg.append(s("path", { d: `M${cx} ${cy - d}L${cx + d} ${cy}L${cx} ${cy + d}L${cx - d} ${cy}Z`,
                             fill: COLORS[k], stroke: COLORS.surface, "stroke-width": 2, class: `best best-${k}` }));
      label(cx, cy, `best ${k} ${fmt(data[b][k])}`, "best-label");
    }

    // hover layer
    cross = s("line", { y1: PAD.top, y2: HEIGHT - PAD.bottom, stroke: COLORS.cross, "stroke-width": 1, visibility: "hidden" });
    focusDot = s("circle", { r: 5, fill: "none", stroke: COLORS.text, "stroke-width": 2, visibility: "hidden" });
    const hit = s("rect", { x: PAD.left - 10, y: 0, width: plotW + 20, height: HEIGHT, fill: "transparent" });
    svg.append(cross, focusDot, hit);
  }

  /** Keep the two end labels from sitting on top of each other. */
  function spreadEndLabels() {
    const labels = [...svg.querySelectorAll(".end-label")];
    if (labels.length === 2) {
      const [a, b] = labels.map((t) => Number(t.getAttribute("y")));
      if (Math.abs(a - b) < 14) {
        const mid = (a + b) / 2, up = a < b ? 0 : 1;
        labels[up].setAttribute("y", mid - 7);
        labels[1 - up].setAttribute("y", mid + 7);
      }
    }
  }

  function show(i) {
    if (!data.length) return;
    hover = Math.max(0, Math.min(data.length - 1, i));
    const row = data[hover];
    const cx = x(hover);
    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
    cross.setAttribute("visibility", "visible");
    const cy = row.penalty === "dnf" ? DNF_BAND : y(row.time);
    focusDot.setAttribute("cx", cx); focusDot.setAttribute("cy", cy);
    focusDot.setAttribute("visibility", "visible");
    // values lead, labels follow; built with textContent (case names are data)
    const line = (value, label, color) => {
      const div = h("div.tip-row");
      if (color) div.append(h("span.tip-key", { style: `background:${color}` }));
      div.append(h("strong", { text: value }), h("span", { text: ` ${label}` }));
      return div;
    };
    tip.replaceChildren(
      h("div.tip-head", { text: `#${row.n}${row.case ? `  ·  ${row.case}` : ""}` }),
      line(fmtSolve(row), "single"),
      line(fmt(row.ao3), "ao3", COLORS.ao3),
      line(fmt(row.ao5), "ao5", COLORS.ao5),
      line(fmt(row.ao12), "ao12", COLORS.ao12),
      line(fmt(pbSoFar[hover]), "PB so far"),
      ...BEST_KEYS.filter((k) => bestAt[k] === hover).map((k) => h("div.tip-note", { text: `★ best ${k}` })),
      ...(pbSoFar[hover] != null && row.time === pbSoFar[hover] && (hover === 0 || pbSoFar[hover - 1] !== row.time)
        ? [h("div.tip-note", { text: "★ new PB" })] : []),
      ...(row.note ? [h("div.tip-note", { text: `⚑ ${row.note}` })] : []),
      h("div.tip-date", { text: row.ts }));
    tip.hidden = false;
    const left = cx + 14 + 170 > width ? cx - 14 - 170 : cx + 14;
    tip.style.left = `${left}px`;
    tip.style.top = `${PAD.top}px`;
  }

  function hide() {
    hover = -1;
    tip.hidden = true;
    cross?.setAttribute("visibility", "hidden");
    focusDot?.setAttribute("visibility", "hidden");
  }

  svg.addEventListener("pointermove", (e) => {
    if (!data.length) return;
    const box = svg.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * width;
    const plotW = width - PAD.left - PAD.right;
    show(data.length === 1 ? 0 : Math.round(((px - PAD.left) / plotW) * (data.length - 1)));
  });
  svg.addEventListener("pointerleave", hide);
  wrap.addEventListener("focus", () => show(hover < 0 ? data.length - 1 : hover));
  wrap.addEventListener("blur", hide);
  wrap.addEventListener("keydown", (e) => {
    const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity };
    if (!(e.key in moves)) return;
    e.preventDefault();
    const m = moves[e.key];
    show(m === -Infinity ? 0 : m === Infinity ? data.length - 1 : hover + m);
  });

  let resizeJob = 0;
  new ResizeObserver(() => {
    clearTimeout(resizeJob);
    resizeJob = setTimeout(() => {
      if (data.length && Math.abs((wrap.clientWidth || 0) - width) > 4) draw();
    }, 120);
  }).observe(el);

  return { el, update, show, get points() { return data.length; },
           get pbCount() { return pbCount; }, get bestAt() { return { ...bestAt }; } };
}
