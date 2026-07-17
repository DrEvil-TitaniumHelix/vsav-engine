/* bridge.js — runs THE actual Python engine in the browser (Pyodide/WASM)
 * for the full-function demo. No JS port, no second rules engine: the same
 * code that passes the repo's validators answers every /api/* call here.
 *
 * A baked game page defines (before this file):
 *   window.DEMO_SLUG    — game folder name under /app/games
 *   window.DEMO_NAME    — display name (gate overlay text)
 *   window.BYO_MANIFEST — module manifest (byo.js runs the gate)
 * This file:
 *   1. installs a fetch shim that queues /api/* calls,
 *   2. in parallel: byo.js gate (user's module) + Pyodide boot + app.zip,
 *   3. writes module-provided engine files (setup saves) into the engine FS,
 *   4. srv.load_game(<slug>), builds counter/map blob URLs from the module,
 *   5. answers the queued /api/* calls through srv.route_get/route_post.
 * Per-session state: the engine's live/ dir is in-memory — a reload starts a
 * fresh session (the audit log of the session is still real and downloadable).
 */
(function () {
  "use strict";
  const SLUG = window.DEMO_SLUG, M = window.BYO_MANIFEST;
  if (!SLUG || !M) return;

  // ---------- status pill ----------
  const pill = document.createElement("div");
  pill.style.cssText =
    "position:fixed; left:50%; bottom:18px; transform:translateX(-50%);" +
    "z-index:99998; background:rgba(25,28,34,.95); color:#9cc4ee;" +
    "border:1px solid #3a6ea5; border-radius:16px; padding:6px 20px;" +
    "font:14px 'Segoe UI',system-ui,sans-serif;";
  function setStatus(t) {
    if (!pill.parentNode && document.body) document.body.appendChild(pill);
    pill.textContent = t;
    pill.style.display = t ? "" : "none";
  }

  // ---------- fetch shim: queue /api/* until the engine is up -------------
  const realFetch = window.fetch.bind(window);
  let handle = null;                    // py callable once booted
  let mapBlobUrl = null;
  const queue = [];
  window.fetch = (url, opts) => {
    const u = String((url && url.url) || url);
    if (!u.includes("/api/")) return realFetch(url, opts);
    return new Promise((resolve, reject) => {
      queue.push({ u, opts, resolve, reject });
      pump();
    });
  };
  function pump() {
    if (!handle) return;
    while (queue.length) serve(queue.shift());
  }
  function parseReq(u, opts) {
    const url = new URL(u, location.href);
    const method = (opts && opts.method) || "GET";
    let payload;
    if (method === "GET") {
      payload = {};                     // parse_qs shape: {key: [values]}
      for (const [k, v] of url.searchParams) (payload[k] = payload[k] || []).push(v);
    } else {
      payload = opts && opts.body ? JSON.parse(opts.body) : {};
    }
    return { path: url.pathname, method, payload };
  }
  function serve(job) {
    try {
      const { path, method, payload } = parseReq(job.u, job.opts);
      const out = handle(method, path, JSON.stringify(payload));
      const obj = JSON.parse(out);
      patchAssets(path, obj);
      if (path === "/api/pbm/export" && obj.doc) {  // download semantics
        const blob = new Blob([JSON.stringify(obj.doc)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = obj.filename || "turn.json";
        a.click();
      }
      job.resolve({ ok: true, status: 200, json: async () => obj,
                    text: async () => out });
    } catch (e) {
      console.error("bridge: api error", job.u, e);
      job.resolve({ ok: true, status: 200,
                    json: async () => ({ error: String(e.message || e) }) });
    }
  }
  function patchAssets(path, obj) {
    // the engine says "/gasset/map" — the art actually lives in blob URLs
    // extracted from the user's own module
    const g = obj && (obj.game || (path === "/api/load_game" && obj.game));
    if (obj && obj.game && mapBlobUrl) obj.game.map_url = mapBlobUrl;
    if (obj && obj.game) obj.game.counters_url = "";
  }

  // ---------- boot ----------
  async function bootPyodide() {
    setStatus("Starting the game engine (first load takes a few seconds)…");
    const pyodide = await loadPyodide({ indexURL: "../../py/pyodide/" });
    const buf = await (await realFetch("../../py/app.zip")).arrayBuffer();
    pyodide.FS.mkdirTree("/app");
    pyodide.unpackArchive(buf, "zip", { extractDir: "/app" });
    return pyodide;
  }

  async function extractCounters(stateObj) {
    // one pass over the full roster (setup saves carry every counter incl.
    // reinforcements) — blob URL per distinct image, from the user's module
    const keys = new Set();
    for (const u of stateObj.units || []) keys.add(u.img || (u.name + ".png"));
    const prefix = M.assets.counters.prefix, req = M.assets.counters.req;
    let missing = 0;
    await Promise.all([...keys].map(async (k) => {
      try {
        const blob = await BYO.extract(req, prefix + k);
        BYO._counters.set(k, BYO.util.urlFor(blob, k));
      } catch (e) { missing++; console.warn("bridge: counter missing in module:", k); }
    }));
    if (missing) console.warn("bridge:", missing, "counter images not found in module");
  }

  (async function main() {
    try {
      const [byo, py] = await Promise.all([BYO.ready, bootPyodide()]);
      setStatus("Reading your module…");
      // module-provided engine files (e.g. the module's own setup save)
      for (const ef of M.engine_files || []) {
        const blob = await BYO.extract(ef.req, ef.entry);
        py.FS.writeFile("/app/games/" + SLUG + "/" + ef.fs_path,
                        new Uint8Array(await blob.arrayBuffer()));
      }
      setStatus("Loading " + (window.DEMO_NAME || SLUG) + "…");
      py.runPython(
        "import sys, os\n" +
        "sys.path.insert(0, '/app/ui'); sys.path.insert(0, '/app/engine')\n" +
        "os.makedirs('/app/live', exist_ok=True)\n" +
        "import server as srv\n" +
        "srv.LIVE = '/app/live'\n" +
        "import json as _bridge_json\n" +
        "def _bridge_handle(method, path, payload_json):\n" +
        "    try:\n" +
        "        payload = _bridge_json.loads(payload_json or '{}')\n" +
        "        r = (srv.route_get(path, payload) if method == 'GET'\n" +
        "             else srv.route_post(path, payload))\n" +
        "        if r is None: r = {'error': 'unknown api ' + path}\n" +
        "        return _bridge_json.dumps(r)\n" +
        "    except Exception as e:\n" +
        "        import traceback; traceback.print_exc()\n" +
        "        return _bridge_json.dumps({'error': str(e)})\n"
      );
      const savedTier = sessionStorage.getItem("tier:" + SLUG);
      const loadGame = py.globals.get("srv").load_game;
      try {
        if (savedTier !== null) loadGame("/app/games/" + SLUG, Number(savedTier));
        else loadGame("/app/games/" + SLUG);
      } catch (e) {                     // stale/invalid stored tier — earned tier
        console.warn("bridge: stored tier rejected, loading earned tier", e);
        sessionStorage.removeItem("tier:" + SLUG);
        loadGame("/app/games/" + SLUG);
      }
      const h = py.globals.get("_bridge_handle");
      // map + counters from the module BEFORE releasing the client's calls
      mapBlobUrl = await BYO.entryUrl(M.assets.map.req, M.assets.map.entry);
      const state = JSON.parse(h("GET", "/api/state", "{}"));
      await extractCounters(state);
      handle = h;
      setStatus("");
      pump();
    } catch (e) {
      console.error("bridge boot failed", e);
      setStatus("Engine failed to start: " + (e.message || e));
    }
  })();

  // tier switches reload this page (engine state is per-session); the frame's
  // tier control calls this hook instead of navigating to "/"
  window.DEMO_TIER_HOOK = (r) => {
    if (r && r.tier !== undefined)
      sessionStorage.setItem("tier:" + SLUG, r.tier);
    location.href = "./";               // loader picks the right client
  };
})();
