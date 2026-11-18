// Boot: read the data the server put in the page, build the screen being
// opened at once and the rest when the browser is idle, route on the URL
// hash, and send the space bar to the active screen's timer.

import { logError } from "./api.js";
import { diagramSvg } from "./diagram.js";
import { Store } from "./store.js";
import { fullScreen } from "./full.js";
import { trainerScreen } from "./trainer.js";
import { galleryScreen } from "./gallery.js";
import { statsScreen } from "./stats.js";

window.addEventListener("error", (e) => logError(`${e.message} at ${e.filename}:${e.lineno}:${e.colno}\n${e.error?.stack || ""}`));
window.addEventListener("unhandledrejection", (e) => logError(`Unhandled rejection: ${e.reason?.stack || e.reason}`));

const t0 = performance.now();
const boot = JSON.parse(document.getElementById("boot").textContent);
// one SVG string per case, shared by the gallery card and the picker tile
for (const mode of ["oll", "pll"]) for (const c of boot.cases[mode]) c.svg = diagramSvg(c.diagram);
const store = new Store(boot);

const content = document.getElementById("content");
const navLinks = [...document.querySelectorAll("#sidebar a")];
const screens = {};
let active = null;

const factories = {
  full: () => fullScreen(store),
  oll: () => trainerScreen(store, "oll", "OLL Practice"),
  pll: () => trainerScreen(store, "pll", "PLL Practice"),
  cases: () => galleryScreen(store, {
    openCase(mode, c) { show(mode); screens[mode].selectCase(c); },
    practiseSelected(mode) { show(mode); screens[mode].setSource("selected"); },
  }),
  stats: () => statsScreen(store),
};

/** The screen called name, built on first use. */
function screen(name) {
  if (!screens[name]) {
    const start = performance.now();
    screens[name] = factories[name]();
    content.append(screens[name].el);
    timings[name] = +(performance.now() - start).toFixed(1);
  }
  return screens[name];
}

function show(name) {
  if (!factories[name]) name = "full";
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  const target = screen(name);
  if (active === target) return;
  if (active) {
    active.onHide?.();
    active.el.classList.remove("shown");
  }
  active = target;
  active.el.classList.add("shown");
  for (const a of navLinks) a.classList.toggle("active", a.dataset.screen === name);
  active.onShow?.();
}

window.addEventListener("hashchange", () => show(location.hash.slice(1)));

// Space drives the timer wherever focus is, except in text fields: keydown
// is Timer.press, keyup Timer.release (hold to start and inspection need both;
// a running clock stops on keydown, the moment the key goes down).
const typing = (el) => el && (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && el.type === "text"));
window.addEventListener("keydown", (e) => {
  if (e.code !== "Space" || typing(e.target)) return;
  e.preventDefault();                 // no page scroll, no button press
  if (e.repeat || !active?.timer) return;
  active.timer.press(e.timeStamp);
});
window.addEventListener("keyup", (e) => {
  if (e.code !== "Space" || typing(e.target)) return;
  e.preventDefault();
  active?.timer?.release(e.timeStamp);
});
// a clicked control would otherwise keep focus and swallow the next Space
document.addEventListener("change", (e) => {
  if (e.target.tagName === "SELECT" || e.target.type === "checkbox") e.target.blur();
});
// a clicked control would otherwise keep focus and swallow the next Space
document.addEventListener("change", (e) => { if (e.target.tagName === "SELECT") e.target.blur(); });

const timings = {};
show(location.hash.slice(1) || "full");
timings.boot = +(performance.now() - t0).toFixed(1);

// build the other screens while the browser is idle, so opening them is instant
const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 50));
const rest = Object.keys(factories).filter((n) => !screens[n]);
(function buildNext() {
  const name = rest.shift();
  if (!name) return;
  idle(() => { screen(name); buildNext(); });
})();

// for scripted checks (and curious users): window.cubeApp.timings
window.cubeApp = { store, screens, screen, show, timings };
