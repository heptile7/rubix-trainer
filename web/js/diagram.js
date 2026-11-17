// Top-down picture of a last-layer case as SVG: a port of
// CaseDiagram._draw in cube_diagram.py (same geometry and colours).
// Drawn once on a 100-unit viewBox; CSS sets the size, so resizing is free.
//
// diagram = {top: [[x, z, colour]], sides: [[x, z, nx, nz, colour]],
//            arrows: [[ax, az, bx, bz, isSwap]], perm: bool}

const YELLOW = "#f6d90b";
const C_UNORIENTED = "#4a4a4a";
const C_OUTLINE = "#151515";
const C_ARROW = "#1b1b1b";       // corner arrows
const C_ARROW_EDGE = "#7a1fa2";  // edge arrows

const S = 100;
const PAD = S * 0.03;
const STRIP = S * 0.085;
const ORIGIN = PAD + STRIP + S * 0.03;
const CELL = (S - 2 * ORIGIN) / 3;
const INSET = Math.max(1, S * 0.012);
const r2 = (v) => Math.round(v * 100) / 100;

function rect(x0, y0, x1, y1, fill) {
  return `<rect x="${r2(x0)}" y="${r2(y0)}" width="${r2(x1 - x0)}" height="${r2(y1 - y0)}" fill="${fill}"/>`;
}

/** Arrow head at (x, y) pointing along unit vector (ux, uy); tk arrowshape (d1, d2, d3). */
function head(x, y, ux, uy, width) {
  const d1 = S * 0.07, d2 = S * 0.085, d3 = S * 0.03 + width / 2;
  const nx = -uy, ny = ux;
  const pts = [
    [x, y],
    [x - ux * d2 + nx * d3, y - uy * d2 + ny * d3],
    [x - ux * d1, y - uy * d1],
    [x - ux * d2 - nx * d3, y - uy * d2 - ny * d3],
  ];
  return pts.map(([a, b]) => `${r2(a)},${r2(b)}`).join(" ");
}

export function diagramSvg(d) {
  const parts = [];

  // Top face
  for (const [x, z, color] of d.top) {
    const x0 = ORIGIN + (x + 1) * CELL, y0 = ORIGIN + (z + 1) * CELL;
    parts.push(rect(x0 + INSET, y0 + INSET, x0 + CELL - INSET, y0 + CELL - INSET,
                    color === YELLOW ? YELLOW : C_UNORIENTED));
  }

  // Side stickers of the top layer (OLL: only the yellow ones)
  for (const [x, z, nx, nz, color] of d.sides) {
    if (!d.perm && color !== YELLOW) continue;
    let x0, x1, y0, y1;
    if (nz) {
      x0 = ORIGIN + (x + 1) * CELL + INSET;
      x1 = x0 + CELL - 2 * INSET;
      y0 = nz < 0 ? PAD : S - PAD - STRIP;
      y1 = y0 + STRIP;
    } else {
      y0 = ORIGIN + (z + 1) * CELL + INSET;
      y1 = y0 + CELL - 2 * INSET;
      x0 = nx < 0 ? PAD : S - PAD - STRIP;
      x1 = x0 + STRIP;
    }
    parts.push(rect(x0, y0, x1, y1, color));
  }

  // Arrows (PLL only)
  const width = Math.max(2, Math.round(S * 0.022));
  for (const [ax, az, bx, bz, swap] of d.arrows) {
    let x0 = ORIGIN + (ax + 1.5) * CELL, y0 = ORIGIN + (az + 1.5) * CELL;
    let x1 = ORIGIN + (bx + 1.5) * CELL, y1 = ORIGIN + (bz + 1.5) * CELL;
    const len = Math.hypot(x1 - x0, y1 - y0);
    const ux = (x1 - x0) / len, uy = (y1 - y0) / len;
    const trim = 0.26 * CELL;
    x0 += ux * trim; y0 += uy * trim; x1 -= ux * trim; y1 -= uy * trim;
    const color = ax && az ? C_ARROW : C_ARROW_EDGE;
    // the shaft stops inside the head so its round cap doesn't poke through the tip
    const back = S * 0.07;
    const sx = swap ? x0 + ux * back : x0, sy = swap ? y0 + uy * back : y0;
    parts.push(`<line x1="${r2(sx)}" y1="${r2(sy)}" x2="${r2(x1 - ux * back)}" y2="${r2(y1 - uy * back)}" ` +
               `stroke="${color}" stroke-width="${width}" stroke-linecap="round"/>`);
    parts.push(`<polygon points="${head(x1, y1, ux, uy, width)}" fill="${color}" stroke="none"/>`);
    if (swap) parts.push(`<polygon points="${head(x0, y0, -ux, -uy, width)}" fill="${color}" stroke="none"/>`);
  }

  return `<svg class="pic" viewBox="0 0 ${S} ${S}" aria-hidden="true">` +
         `<g stroke="${C_OUTLINE}" stroke-width="1">` +
         parts.join("") + "</g></svg>";
}
