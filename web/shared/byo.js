/* byo.js — bring-your-own-module gate for the static web build.
 *
 * The release ships only the engine + our transcribed rules data. The
 * publisher's art (map, counters) comes out of the user's own .vmod, parsed
 * right here in the browser — nothing is ever uploaded (there is no server).
 *
 * Load order on a game page: data.js, local.js (fetch shim), manifest.js
 * (window.BYO_MANIFEST), then this file, then the game script. We wrap the
 * fetch shim so the game's first /api/state waits until the module's assets
 * are mounted; the game code itself needs no changes beyond BYO.counter().
 *
 * Manifest shape (window.BYO_MANIFEST):
 *   requirements: [{id, title, filename, size, sha256, page, hint}, ...]
 *   assets: { map:      {req, entry},
 *             counters: {req, prefix} }
 * Files are cached in IndexedDB keyed by sha256, so one successful drop
 * lasts across visits (and across games sharing a module). "?byo=reset"
 * clears this page's cached files and shows the gate again.
 */
(function () {
  const M = window.BYO_MANIFEST;
  if (!M) return;                              // not a BYO build — do nothing
  const BYO = (window.BYO = { _counters: new Map() });

  BYO.counter = function (u) {
    return BYO._counters.get(u.img || (u.name + ".png")) || "";
  };

  // --- hold the game's /api/* fetches until the module is mounted ----------
  // (only /api/: anything else — including diagnostics — must not deadlock
  // behind the gate)
  const realFetch = window.fetch.bind(window);
  let release;
  const mounted = new Promise((r) => (release = r));
  window.fetch = (url, ...rest) =>
    String((url && url.url) || url).includes("/api/")
      ? mounted.then(() => realFetch(url, ...rest))
      : realFetch(url, ...rest);

  // --- IndexedDB cache (key = sha256, value = {name, size, blob}) ----------
  function idb() {
    return new Promise((res, rej) => {
      const q = indexedDB.open("byo_modules", 1);
      q.onupgradeneeded = () => q.result.createObjectStore("files");
      q.onsuccess = () => res(q.result);
      q.onerror = () => rej(q.error);
    });
  }
  const idbGet = (db, k) =>
    new Promise((res, rej) => {
      const t = db.transaction("files").objectStore("files").get(k);
      t.onsuccess = () => res(t.result);
      t.onerror = () => rej(t.error);
    });
  const idbPut = (db, k, v) =>
    new Promise((res, rej) => {
      const t = db.transaction("files", "readwrite").objectStore("files").put(v, k);
      t.onsuccess = () => res();
      t.onerror = () => rej(t.error);
    });
  const idbDel = (db, k) =>
    new Promise((res, rej) => {
      const t = db.transaction("files", "readwrite").objectStore("files").delete(k);
      t.onsuccess = () => res();
      t.onerror = () => rej(t.error);
    });

  // --- sha256 --------------------------------------------------------------
  async function sha256hex(blob) {
    if (!(crypto && crypto.subtle))
      throw new Error("This page needs a modern browser (Chrome/Edge/Firefox) — " +
                      "crypto.subtle is unavailable here.");
    const d = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
    return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // --- minimal zip reader (central directory + stored/deflate entries) -----
  async function zipIndex(blob) {
    const tailLen = Math.min(blob.size, 70000);
    const tail = new DataView(await blob.slice(blob.size - tailLen).arrayBuffer());
    let e = -1;
    for (let i = tail.byteLength - 22; i >= 0; i--)
      if (tail.getUint32(i, true) === 0x06054b50) { e = i; break; }
    if (e < 0) throw new Error("not a zip file");
    const count = tail.getUint16(e + 10, true);
    const cdSize = tail.getUint32(e + 12, true);
    const cdOfs = tail.getUint32(e + 16, true);
    const cd = new DataView(await blob.slice(cdOfs, cdOfs + cdSize).arrayBuffer());
    const td = new TextDecoder();
    const idx = new Map();
    let p = 0;
    for (let k = 0; k < count && p + 46 <= cd.byteLength; k++) {
      if (cd.getUint32(p, true) !== 0x02014b50) break;
      const method = cd.getUint16(p + 10, true);
      const csize = cd.getUint32(p + 20, true);
      const nlen = cd.getUint16(p + 28, true);
      const elen = cd.getUint16(p + 30, true);
      const clen = cd.getUint16(p + 32, true);
      const lho = cd.getUint32(p + 42, true);
      const name = td.decode(new Uint8Array(cd.buffer, cd.byteOffset + p + 46, nlen));
      idx.set(name, { method, csize, lho });
      p += 46 + nlen + elen + clen;
    }
    return idx;
  }
  async function unzipEntry(blob, ent) {
    const lh = new DataView(await blob.slice(ent.lho, ent.lho + 30).arrayBuffer());
    if (lh.getUint32(0, true) !== 0x04034b50) throw new Error("bad zip local header");
    const start = ent.lho + 30 + lh.getUint16(26, true) + lh.getUint16(28, true);
    const comp = blob.slice(start, start + ent.csize);
    if (ent.method === 0) return comp;
    if (ent.method === 8) {
      const ds = new DecompressionStream("deflate-raw");
      return await new Response(comp.stream().pipeThrough(ds)).blob();
    }
    throw new Error("unsupported zip method " + ent.method);
  }

  const MIME = { png: "image/png", gif: "image/gif", jpg: "image/jpeg",
                 jpeg: "image/jpeg", bmp: "image/bmp", svg: "image/svg+xml" };
  const urlFor = (blob, name) =>
    URL.createObjectURL(new Blob([blob],
      { type: MIME[name.toLowerCase().split(".").pop()] || "application/octet-stream" }));

  // --- mount: marry the user's module art to our baked game data -----------
  async function mount(files) {                      // files: {reqId: blob}
    const zips = {};
    for (const r of M.requirements)
      zips[r.id] = { blob: files[r.id], idx: await zipIndex(files[r.id]) };
    const D = window.GAME_DATA;
    const me = zips[M.assets.map.req].idx.get(M.assets.map.entry);
    if (!me) throw new Error("map entry not found in module: " + M.assets.map.entry);
    D.game.map_url = urlFor(await unzipEntry(zips[M.assets.map.req].blob, me),
                            M.assets.map.entry);
    const cz = zips[M.assets.counters.req];
    const need = new Set();
    for (const u of D.units) need.add(u.img || (u.name + ".png"));
    let missing = 0;
    await Promise.all([...need].map(async (key) => {
      const e = cz.idx.get(M.assets.counters.prefix + key);
      if (!e) { missing++; console.warn("BYO: counter entry missing:", key); return; }
      BYO._counters.set(key, urlFor(await unzipEntry(cz.blob, e), key));
    }));
    if (missing) console.warn("BYO: " + missing + " counter images not found in module");
  }

  // --- the gate overlay ----------------------------------------------------
  const CSS = `
    #byogate { position:fixed; inset:0; z-index:99999; background:#1a1c20;
      color:#dde3ea; font-family:Segoe UI,system-ui,sans-serif; overflow:auto; }
    #byogate .in { max-width:660px; margin:8vh auto 40px; padding:0 24px; }
    #byogate h1 { color:#fff; font-size:24px; margin:0 0 6px; }
    #byogate .sub { color:#8a8f98; font-size:14px; margin:0 0 24px; line-height:1.5; }
    #byogate .req { background:#23262c; border:1px solid #3a3f47; border-radius:12px;
      padding:18px 20px; margin:14px 0; }
    #byogate .req h2 { margin:0 0 4px; font-size:16px; color:#fff; }
    #byogate .req .want { color:#9aa3ad; font-size:13px; margin:2px 0 10px; }
    #byogate .req .want code { background:#2c2f36; padding:1px 6px; border-radius:4px; }
    #byogate .req a { color:#9cc4ee; }
    #byogate .drop { border:2px dashed #4a4f57; border-radius:10px; padding:22px;
      text-align:center; color:#9aa3ad; font-size:14px; cursor:pointer; margin-top:8px; }
    #byogate .drop.hot { border-color:#4880bd; background:#243447; color:#cfe3f7; }
    #byogate .drop.ok { border-style:solid; border-color:#5a8a4a; background:#22301f;
      color:#a8d89a; cursor:default; }
    #byogate .msg { font-size:13px; margin-top:10px; line-height:1.5; }
    #byogate .msg.err { color:#e0a0a0; }
    #byogate .msg.busy { color:#9cc4ee; }
    #byogate .foot { color:#6c7178; font-size:12px; margin-top:22px; line-height:1.6; }
  `;

  function showGate(missing, files, db, onDone) {
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);
    const ov = document.createElement("div");
    ov.id = "byogate";
    const name = (window.GAME_DATA && GAME_DATA.game && GAME_DATA.game.name) || "this game";
    ov.innerHTML =
      `<div class="in"><h1>Bring your own module</h1>
       <p class="sub">${name} ships with no game art. Drop your own copy of the
       VASSAL module below — it is read right here in your browser and never
       uploaded. After one successful drop it is remembered on this device.</p>
       <div id="byoreqs"></div>
       <p class="foot">The file is checked against the exact version this game was
       validated against (SHA-256). All game art remains the property of its
       publisher and the module's author — that's why you bring the module.</p></div>`;
    document.body.appendChild(ov);
    const wrap = ov.querySelector("#byoreqs");
    let left = missing.length;

    for (const r of missing) {
      const card = document.createElement("div");
      card.className = "req";
      card.innerHTML =
        `<h2>${r.title}</h2>
         <div class="want">Needs <code>${r.filename}</code>
           (${(r.size / 1048576).toFixed(1)} MB) —
           <a href="${r.page}" target="_blank" rel="noopener">get it here</a>.
           ${r.hint || ""}</div>
         <div class="drop">Drop ${r.filename} here — or click to browse</div>
         <input type="file" style="display:none">
         <div class="msg"></div>`;
      wrap.appendChild(card);
      const drop = card.querySelector(".drop");
      const input = card.querySelector("input");
      const msg = card.querySelector(".msg");
      let done = false;

      async function take(file) {
        if (done || !file) return;
        msg.className = "msg busy";
        msg.textContent = "Checking " + file.name + " (" +
                          (file.size / 1048576).toFixed(1) + " MB)…";
        try {
          const hex = await sha256hex(file);
          if (hex !== r.sha256) {
            msg.className = "msg err";
            msg.innerHTML =
              `That's not the exact file this game was validated against.<br>` +
              `Expected <code>${r.filename}</code> (${r.size.toLocaleString()} bytes, ` +
              `sha256 ${r.sha256.slice(0, 12)}…) — got ${file.name} ` +
              `(${file.size.toLocaleString()} bytes, sha256 ${hex.slice(0, 12)}…).<br>` +
              `<a href="${r.page}" target="_blank" rel="noopener">Download the right version here.</a>`;
            return;
          }
          files[r.id] = file;
          if (db) { try { await idbPut(db, r.sha256, { name: file.name, size: file.size, blob: file }); }
                    catch (e) { console.warn("BYO: cache write failed", e); } }
          done = true;
          drop.className = "drop ok";
          drop.textContent = "✓ " + file.name + " — verified";
          msg.className = "msg"; msg.textContent = "";
          if (--left === 0) finish();
        } catch (e) {
          msg.className = "msg err";
          msg.textContent = "Could not read that file: " + (e.message || e);
        }
      }
      drop.onclick = () => input.click();
      input.onchange = () => take(input.files[0]);
      drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("hot"); };
      drop.ondragleave = () => drop.classList.remove("hot");
      drop.ondrop = (e) => {
        e.preventDefault(); drop.classList.remove("hot");
        take(e.dataTransfer.files[0]);
      };
    }

    async function finish() {
      const busy = document.createElement("p");
      busy.className = "sub";
      busy.textContent = "Reading module assets…";
      wrap.appendChild(busy);
      try {
        await onDone();
        ov.remove(); style.remove();
      } catch (e) {
        busy.textContent = "Could not read the module's assets: " + (e.message || e);
        busy.style.color = "#e0a0a0";
      }
    }
  }

  // --- main ----------------------------------------------------------------
  (async function () {
    let db = null;
    const files = {};
    try {
      db = await idb();
      if (/[?&]byo=reset/.test(location.search))
        for (const r of M.requirements) await idbDel(db, r.sha256);
      for (const r of M.requirements) {
        const v = await idbGet(db, r.sha256);
        if (v && v.blob) files[r.id] = v.blob;
      }
    } catch (e) { console.warn("BYO: IndexedDB unavailable — no cross-visit cache", e); }

    const missing = M.requirements.filter((r) => !files[r.id]);
    if (!missing.length) {
      try { await mount(files); release(); return; }
      catch (e) {                       // cached blob unreadable — re-gate
        console.warn("BYO: cached module failed to mount, asking again", e);
        for (const k in files) delete files[k];
      }
    }
    const ask = M.requirements.filter((r) => !files[r.id]);
    const start = () => showGate(ask, files, db, async () => { await mount(files); release(); });
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start);
  })();
})();
