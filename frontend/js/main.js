// Shared helpers used across pages. Currently minimal — most logic lives in
// analysis.js. Kept as a separate file so we can hook page-wide behaviour
// (analytics, theme toggles, etc.) without touching the page-specific code.

window.GaitMind = window.GaitMind || {};

// Resolve API base URL. When the frontend is served by the FastAPI app itself
// the base is just the current origin; in dev with a separate file:// load,
// fall back to localhost:8000.
GaitMind.apiBase = (() => {
  if (location.protocol.startsWith("http")) return "";
  return "http://127.0.0.1:8000";
})();

GaitMind.api = async function api(path, options = {}) {
  const res = await fetch(GaitMind.apiBase + path, options);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json();
};
