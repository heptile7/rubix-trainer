// JSON calls to cube_web.py. Writes go through one queue so they reach the
// server in the order they were made (two quick clicks never arrive swapped).

import { toast } from "./util.js";

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
    throw new Error(`${method} ${path}: ${res.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.json();
}

let queue = Promise.resolve();
let onWriteFailed = () => {};

/** Called after a queued write fails (the store reloads its state from the server). */
export function setWriteFailedHandler(fn) { onWriteFailed = fn; }

/** Queued write; resolves to the response, or null if it failed (already reported). */
function write(method, path, body) {
  const result = queue.then(() => call(method, path, body)).catch((err) => {
    toast("Couldn't save that change - is the server still running?");
    logError(String(err));
    onWriteFailed(err);
    return null;
  });
  queue = result;
  return result;
}

const enc = encodeURIComponent;

export const api = {
  state:        () => call("GET", "/api/state"),
  deal:         (mode, name) => call("GET", `/api/deal/${mode}/${enc(name)}`),
  times:        (mode, limit = 50) => call("GET", `/api/times/${mode}?limit=${limit}`),
  summary:      (mode) => call("GET", `/api/summary/${mode}`),
  addTime:      (attempt) => write("POST", "/api/times", attempt),
  deleteLast:   (mode) => write("DELETE", `/api/times/last/${mode}`),
  solves:       (mode, scope, flagged, limit = 200, caseName = "") =>
    call("GET", `/api/solves/${mode}?scope=${scope}&flagged=${flagged}&limit=${limit}` +
                (caseName ? `&case=${enc(caseName)}` : "")),
  setPenalty:   (id, penalty) => write("PUT", `/api/solves/${id}/penalty`, { penalty }),
  setFlag:      (id, flagged, note) => write("PUT", `/api/solves/${id}/flag`, { flagged, note }),
  deleteSolve:  (id) => write("DELETE", `/api/solves/${id}`),
  saveSettings: (values) => write("PUT", "/api/settings", { values }),
  newSession:   (mode, name) => write("POST", `/api/session/${mode}`, { name }),
  selectSession: (mode, n) => write("PUT", `/api/session/${mode}/${n}`),
  renameSession: (mode, n, name) => write("PATCH", `/api/session/${mode}/${n}`, { name }),
  deleteSession: (mode, n) => write("DELETE", `/api/session/${mode}/${n}`),
  setSelected:  (mode, names) => write("PUT", `/api/selected/${mode}`, { names }),
  setStatus:    (mode, names, status) => write("PUT", `/api/status/${mode}`, { names, status }),
  saveGroup:    (mode, name, names) => write("PUT", `/api/groups/${mode}/${enc(name)}`, { names }),
  deleteGroup:  (mode, name) => write("DELETE", `/api/groups/${mode}/${enc(name)}`),
};

/** Send a browser-side error to cube_timer.log (never throws). */
export function logError(message) {
  try {
    fetch("/api/log", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: "error", message }),
      keepalive: true,
    }).catch(() => {});
  } catch { /* ignore */ }
}
