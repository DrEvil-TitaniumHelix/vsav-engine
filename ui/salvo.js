// salvo.js — SALVO match-folder client (Modes 2/3): the browser side of
// SALVO_PROTOCOL.md. The engine (native server or Pyodide bridge) owns all
// packet/move semantics at /api/salvo/*; this module only ferries files
// through one user-picked local folder via the File System Access API
// (Chrome/Edge). The player's own LLM reads packet.json and writes
// move.json in that folder; we poll, submit, and write back.
//
// Engine-level: any client for a SALVO-capable game family includes this
// and calls SALVO.init({slug, onUpdate}); everything else is internal.
(function () {
  'use strict';

  const POLL_MS = 1500;      // move.json poll
  const RESYNC_EVERY = 6;    // polls between server packet re-checks

  let cfg = null;            // {slug, onUpdate}
  let dir = null;            // DirectoryHandle for the match folder
  let cur = null;            // last packet written to the folder
  let status = null;         // s.salvo from the server
  let timer = null;
  let busy = false;
  let polls = 0;
  let lastMoveRaw = null;    // raw text of the last move.json we consumed/refused

  // ------------------------------------------------------------ helpers
  const J = (o) => JSON.stringify(o, null, 1);

  async function api(path, body) {
    const r = await fetch(path, body !== undefined
      ? { method: 'POST', body: JSON.stringify(body) } : undefined);
    return r.json();
  }

  async function writeFile(d, name, text) {
    const fh = await d.getFileHandle(name, { create: true });
    const w = await fh.createWritable();
    await w.write(text);
    await w.close();
  }

  async function readText(d, name) {
    try {
      const fh = await d.getFileHandle(name);
      return await (await fh.getFile()).text();
    } catch (e) { return null; }
  }

  // handle persistence so a reload (or next session) can re-attach the
  // same folder with one permission click
  function idb() {
    return new Promise((res, rej) => {
      const rq = indexedDB.open('salvo_dirs', 1);
      rq.onupgradeneeded = () => rq.result.createObjectStore('dirs');
      rq.onsuccess = () => res(rq.result);
      rq.onerror = () => rej(rq.error);
    });
  }
  async function saveHandle(h) {
    try {
      const db = await idb();
      await new Promise((res, rej) => {
        const tx = db.transaction('dirs', 'readwrite');
        tx.objectStore('dirs').put(h, cfg.slug);
        tx.oncomplete = res; tx.onerror = () => rej(tx.error);
      });
    } catch (e) { /* non-fatal: user re-picks after reload */ }
  }
  async function loadHandle() {
    try {
      const db = await idb();
      return await new Promise((res) => {
        const rq = db.transaction('dirs').objectStore('dirs').get(cfg.slug);
        rq.onsuccess = () => res(rq.result || null);
        rq.onerror = () => res(null);
      });
    } catch (e) { return null; }
  }

  // ------------------------------------------------------------ folder IO
  async function writePacket(pkt) {
    if (!dir || !pkt) return;
    const changed = !cur || cur.n !== pkt.n || cur.kind !== pkt.kind
      || (pkt.since || []).length !== (cur.since || []).length
      || pkt.mover !== cur.mover || pkt.phase !== cur.phase;
    cur = pkt;
    if (!changed) return;
    await writeFile(dir, 'packet.json', J(pkt));
    try {
      const hist = await dir.getDirectoryHandle('history', { create: true });
      await writeFile(hist,
        `packet_${String(pkt.n).padStart(6, '0')}_${pkt.kind}.json`, J(pkt));
    } catch (e) { /* history is best-effort */ }
    await writeLog();
  }

  async function writeLog() {
    try {
      const r = await api('/api/salvo/log');
      if (r.lines) await writeFile(dir, 'log.jsonl', r.lines.join('\n') + '\n');
    } catch (e) { /* refreshed on next write */ }
  }

  async function writeCard(extra) {
    const card = Object.assign({
      format: 'salvo-match/1', game: cfg.slug,
      note: 'SALVO match folder - see SALVO_PROTOCOL.md. Your agent reads '
        + 'packet.json and writes move.json; everything else is the record.',
      started: new Date().toISOString(),
    }, extra || {});
    await writeFile(dir, 'salvo.json', J(card));
  }

  // ------------------------------------------------------------ the loop
  async function poll() {
    if (busy || !dir || !status) return;
    busy = true;
    try {
      polls++;
      const raw = await readText(dir, 'move.json');
      if (raw && raw !== lastMoveRaw && cur
          && cur.kind !== 'over') {
        let move = null;
        try { move = JSON.parse(raw); } catch (e) { /* mid-write: retry */ }
        if (move && move.n === cur.n
            && (cur.kind === 'decision' || cur.kind === 'rejection')) {
          lastMoveRaw = raw;
          await consume(move, raw);
        } else if (move && move.n !== cur.n) {
          lastMoveRaw = raw;             // stale answer: note it once, move on
        }
      } else if (polls % RESYNC_EVERY === 0) {
        await sync(false);
      }
    } finally { busy = false; }
  }

  async function consume(move, raw) {
    try {
      const hist = await dir.getDirectoryHandle('history', { create: true });
      await writeFile(hist,
        `move_${String(move.n).padStart(6, '0')}.json`, raw);
    } catch (e) { /* best-effort */ }
    const r = await api('/api/salvo/move', { move });
    if (r.salvo) status = r.salvo;
    if (r.packet) await writePacket(r.packet);
    if (r.error && !r.packet) return;   // no match anymore; init() re-syncs
    if (cfg.onUpdate) cfg.onUpdate({ event: 'move', reply: r });
    // mode 2: if the house still owes play (e.g. it moved first), tick
    if (r.packet && r.packet.kind === 'wait' && status && !status.pbm) {
      const t = await api('/api/salvo/tick', {});
      if (t.packet) await writePacket(t.packet);
      if (t.salvo) status = t.salvo;
      if (cfg.onUpdate) cfg.onUpdate({ event: 'tick', reply: t });
    }
  }

  // re-pull the authoritative packet (state may have changed around us:
  // a mailed import, manual play, a reset)
  async function sync(force) {
    if (!status) return;
    const r = await api('/api/salvo/packet');
    if (r.error) { status = null; stopTimer(); if (cfg.onUpdate) cfg.onUpdate({ event: 'gone' }); return; }
    status = r.salvo || status;
    if (r.packet && status && !status.pbm && r.packet.kind === 'wait') {
      const t = await api('/api/salvo/tick', {});
      if (t.packet) { await writePacket(t.packet); if (t.salvo) status = t.salvo; return; }
    }
    if (r.packet) await writePacket(r.packet);
  }

  function startTimer() {
    stopTimer();
    timer = setInterval(poll, POLL_MS);
  }
  function stopTimer() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  // ------------------------------------------------------------ public
  const SALVO = {
    supported: () => typeof window.showDirectoryPicker === 'function',
    status: () => status,
    attached: () => !!dir,
    packet: () => cur,
    folderName: () => (dir && dir.name) || null,

    init(c) { cfg = c; },

    // reflect server state (called by the client on every refresh)
    setStatus(s) {
      status = s || null;
      if (!status) { stopTimer(); cur = null; }
      else if (dir && !timer) startTimer();
      else if (!dir) SALVO.tryResume();   // silent re-attach after reload
    },

    // reload path without a prompt: only proceeds if Chrome still holds
    // the granted permission for the stored folder handle
    async tryResume() {
      if (dir || !status || !cfg || SALVO._resuming) return false;
      SALVO._resuming = true;
      try {
        const h = await loadHandle();
        if (!h) return false;
        let perm = 'denied';
        try { perm = await h.queryPermission({ mode: 'readwrite' }); }
        catch (e) { return false; }
        if (perm !== 'granted') return false;
        dir = h;
        lastMoveRaw = await readText(dir, 'move.json');
        await sync(true);
        startTimer();
        if (cfg.onUpdate) cfg.onUpdate({ event: 'resume' });
        return true;
      } finally { SALVO._resuming = false; }
    },

    // start a match: pick folder, tell the server, seed the folder
    async begin(side, opts) {
      if (!SALVO.supported())
        throw new Error('This browser cannot grant folder access - use '
          + 'Chrome or Edge for SALVO matches.');
      dir = await window.showDirectoryPicker({ mode: 'readwrite' });
      const r = await api('/api/salvo/start',
        Object.assign({ side }, opts || {}));
      if (r.error) { dir = null; throw new Error(r.error); }
      status = r.salvo;
      await saveHandle(dir);
      await writeCard({ match_id: status.match_id, llm_side: status.llm_side,
                        pbm: status.pbm });
      cur = null;
      lastMoveRaw = await readText(dir, 'move.json'); // ignore leftovers
      await writePacket(r.packet);
      startTimer();
      if (cfg.onUpdate) cfg.onUpdate({ event: 'begin', reply: r });
      return r;
    },

    // reload path: match exists server-side, folder handle lost or stored
    async reattach() {
      if (!SALVO.supported()) throw new Error('Chrome/Edge required');
      let h = await loadHandle();
      if (h) {
        const perm = await h.requestPermission({ mode: 'readwrite' });
        if (perm !== 'granted') h = null;
      }
      if (!h) {
        h = await window.showDirectoryPicker({ mode: 'readwrite' });
      }
      dir = h;
      await saveHandle(dir);
      lastMoveRaw = await readText(dir, 'move.json');
      await sync(true);
      startTimer();
      if (cfg.onUpdate) cfg.onUpdate({ event: 'reattach' });
    },

    async stop() {
      await api('/api/salvo/stop', {});
      stopTimer();
      status = null; cur = null; dir = null;
      if (cfg.onUpdate) cfg.onUpdate({ event: 'stop' });
    },

    // external nudge (after PBM import / manual play / reset)
    nudge() { if (dir && status) sync(true); },

    async payload() { return api('/api/salvo/payload'); },
  };

  window.SALVO = SALVO;
})();
