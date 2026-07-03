/* local.js — Dr Evil's Legality Engine for VASSAL, browser edition.
 *
 * A JavaScript port of the spec-driven movement engine (engine/gamespec.py),
 * plus a fetch() shim that answers the board UI's /api/* calls locally.
 * The page runs from a plain file:// double-click or any static host —
 * no server, no install. Game data is baked into data.js by build_web.py.
 *
 * Demo scope: moves live in browser memory (no .vsav write-back here —
 * that's the full engine in the GitHub repo).
 */
(function () {
  const D = window.GAME_DATA;
  if (!D) { console.error("local.js: no GAME_DATA"); return; }

  // ---------------- grid (port of gamespec.Grid) ----------------
  const G = D.spec.grid;
  const dx = G.dx, dy = G.dy, x0 = G.x0 || 0, y0 = G.y0 || 0;
  const orient = G.orient || "flat";
  const stagger = G.stagger !== false;
  const staggerSign = G.stagger_sign || 1;
  const oddRowCarry = "odd_row_carry" in G ? G.odd_row_carry : 1;
  const offsetParity = "offset_parity" in G ? G.offset_parity : 1;
  const digits = G.hexnum_digits || 2;

  const pad = (n) => String(n).padStart(digits, "0");
  const hexnum = (c, r) => pad(c) + pad(r);

  function hexToPixel(col, row) {
    if (orient === "pointy") {
      const xoff = (stagger && ((row % 2 + 2) % 2) === offsetParity) ? dx / 2 : 0;
      return [Math.round(x0 + col * dx + xoff), Math.round(y0 + row * dy)];
    }
    const odd = ((col % 2 + 2) % 2) === 1;
    const yoff = (stagger && odd) ? staggerSign * dy / 2 : 0;
    const base = row - (odd ? oddRowCarry : 0);
    return [Math.round(x0 + col * dx), Math.round(y0 + base * dy + yoff)];
  }

  function pixelToHex(x, y) {
    if (orient === "pointy") {
      const row = Math.round((y - y0) / dy);
      const xoff = (stagger && ((row % 2 + 2) % 2) === offsetParity) ? dx / 2 : 0;
      return [Math.round((x - x0 - xoff) / dx), row];
    }
    const col = Math.round((x - x0) / dx);
    const odd = ((col % 2 + 2) % 2) === 1;
    const yoff = (stagger && odd) ? staggerSign * dy / 2 : 0;
    const row = Math.round((y - y0 - yoff) / dy) + (odd ? oddRowCarry : 0);
    return [col, row];
  }

  function neighbors(col, row) {
    const [x, y] = hexToPixel(col, row);
    const offs = orient === "pointy"
      ? [[-dx, 0], [dx, 0], [-dx / 2, -dy], [dx / 2, -dy], [-dx / 2, dy], [dx / 2, dy]]
      : [[0, -dy], [0, dy], [dx, -dy / 2], [dx, dy / 2], [-dx, -dy / 2], [-dx, dy / 2]];
    return offs.map(([ox, oy]) => pixelToHex(Math.round(x + ox), Math.round(y + oy)));
  }

  // ---------------- terrain + movement (port of gamespec.Game) ----------------
  const T = D.terrain;                       // {hexes:{key:{t}}, sides:{a|b:{feat}}} or null
  const M = D.spec.movement;
  const impassable = new Set(M.impassable_terrain || ["offmap", "water"]);
  const terrainMp = M.terrain_mp || {};
  const defaultMp = "default_mp" in M ? M.default_mp : 1.0;
  const hexsideRules = M.hexside_rules || [];
  const zocCfg = M.zoc || {};
  const bounds = M.bounds;
  const sideOrder = D.spec.sides.order;

  const hexTerrain = (c, r) => {
    if (!T) return null;
    const v = T.hexes[hexnum(c, r)];
    return v ? v.t : null;
  };
  function onMap(c, r) {
    const t = hexTerrain(c, r);
    if (t !== null) return !impassable.has(t);
    if (bounds) {
      return bounds.cols[0] <= c && c <= bounds.cols[1] &&
             bounds.rows[0] <= r && r <= bounds.rows[1];
    }
    return false;
  }
  function sideFeatures(a, b) {
    if (!T || !T.sides) return {};
    return T.sides[hexnum(a[0], a[1]) + "|" + hexnum(b[0], b[1])] ||
           T.sides[hexnum(b[0], b[1]) + "|" + hexnum(a[0], a[1])] || {};
  }
  function moveCost(a, b) {
    if (!onMap(b[0], b[1])) return null;
    const f = sideFeatures(a, b);
    let base = null, add = 0;
    for (const rule of hexsideRules) {
      if (f[rule.feature] !== rule.value) continue;
      if (rule.unless && f[rule.unless]) continue;
      if (rule.effect === "prohibit") return null;
      if (rule.effect === "override" && base === null) base = rule.mp;
      else if (rule.effect === "add") add += rule.mp;
    }
    if (base === null) {
      const t = hexTerrain(b[0], b[1]);
      base = (t !== null && t in terrainMp) ? terrainMp[t] : defaultMp;
    }
    return base + add;
  }
  const enemyOf = (s) => (s === sideOrder[0] ? sideOrder[1] : sideOrder[0]);
  function zocHexes(board, enemySide) {
    const z = new Set();
    if (!zocCfg.exerts) return z;
    for (const u of board) {
      if (u.side === enemySide) {
        for (const [c, r] of neighbors(u.col, u.row)) z.add(hexnum(c, r));
      }
    }
    return z;
  }

  function legalDestinations(unit, ma, board) {
    // Dijkstra over spec move costs — mirror of gamespec.legal_destinations_t
    const enemy = enemyOf(unit.side);
    const epos = new Set(), fpos = new Set();
    for (const u of board) (u.side === enemy ? epos : fpos).add(hexnum(u.col, u.row));
    const ezoc = zocHexes(board, enemy);
    const startKey = hexnum(unit.col, unit.row);
    if (zocCfg.locked_at_start && ezoc.has(startKey)) return {};
    const stopOnEnter = !!zocCfg.stop_on_enter;
    const enterEnemy = !!M.enter_enemy_hex;
    const best = new Map([[startKey, { cost: 0, col: unit.col, row: unit.row }]]);
    const pq = [[0, unit.col, unit.row]];
    while (pq.length) {
      let bi = 0;
      for (let i = 1; i < pq.length; i++) if (pq[i][0] < pq[bi][0]) bi = i;
      const [cost, cc, cr] = pq.splice(bi, 1)[0];
      const ck = hexnum(cc, cr);
      if (cost > (best.has(ck) ? best.get(ck).cost : 1e9)) continue;
      if (ck !== startKey && ezoc.has(ck) && stopOnEnter) continue;
      for (const [nc, nr] of neighbors(cc, cr)) {
        const nk = hexnum(nc, nr);
        if (epos.has(nk) && !enterEnemy) continue;
        const c = moveCost([cc, cr], [nc, nr]);
        if (c === null) continue;
        const total = cost + c;
        if (total > ma + 1e-9) continue;
        if (total < (best.has(nk) ? best.get(nk).cost : 1e9)) {
          best.set(nk, { cost: total, col: nc, row: nr });
          pq.push([total, nc, nr]);
        }
      }
    }
    const out = {};
    for (const [k, v] of best) {
      if (k !== startKey && !fpos.has(k) && !epos.has(k)) out[k] = v;
    }
    return out;
  }

  // ---------------- game state (in-memory; demo scope) ----------------
  const pristine = JSON.stringify(D.units);
  let units = JSON.parse(pristine);
  const byId = () => new Map(units.map((u) => [u.id, u]));

  const stackAt = (hex) => units.filter((u) => u.hexnum === hex);

  function apiState() {
    return { units: JSON.parse(JSON.stringify(units)), game: D.game, notes: D.notes };
  }

  function apiLegal(id, whole) {
    const me = byId().get(id);
    let ma = me.ma;
    let movingIds = new Set([id]);
    if (whole) {
      for (const u of stackAt(me.hexnum)) {
        movingIds.add(u.id);
        ma = Math.min(ma, u.ma);
      }
    }
    const rb = units.filter((u) => u.onmap && !movingIds.has(u.id));
    const dests = legalDestinations(me, ma, rb);
    const out = [];
    for (const k in dests) {
      const v = dests[k];
      const [x, y] = hexToPixel(v.col, v.row);
      out.push({ col: v.col, row: v.row, x, y, hexnum: k,
                 cost: Math.round(v.cost * 10) / 10, terrain: hexTerrain(v.col, v.row) });
    }
    return { ma, dests: out };
  }

  function placeUnit(u, destHex) {
    const c = parseInt(destHex.slice(0, digits), 10);
    const r = parseInt(destHex.slice(digits), 10);
    const [x, y] = hexToPixel(c, r);
    Object.assign(u, { col: c, row: r, x, y, hexnum: destHex,
                       terrain: hexTerrain(c, r), onmap: onMap(c, r), status: "moved" });
  }

  function apiMove(body) {
    const me = byId().get(body.id);
    const movers = body.whole ? stackAt(me.hexnum) : [me];
    for (const u of movers) placeUnit(u, body.dest);
    return { ok: true, msg: `${me.name}: -> ${body.dest}` };
  }

  function apiPass(body) {
    const me = byId().get(body.id);
    const targets = body.whole ? stackAt(me.hexnum) : [me];
    for (const u of targets) u.status = "passed";
    return { ok: true };
  }

  function apiFace(body) {
    if (!D.game.facing) return { error: "this game has no facing" };
    const u = byId().get(body.id);
    const n = D.game.facing.count;
    u.facing = (((u.facing || 0) + (body.step || 1)) % n + n) % n;
    return { ok: true, facing: u.facing };
  }

  function apiReset() {
    units = JSON.parse(pristine);
    return { ok: true };
  }

  // ---------------- fetch shim ----------------
  const realFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    if (typeof url === "string" && url.indexOf("/api/") !== -1) {
      const q = url.split("?")[1] || "";
      const qs = Object.fromEntries(new URLSearchParams(q));
      const body = opts && opts.body ? JSON.parse(opts.body) : {};
      let resp;
      if (url.indexOf("/api/state") !== -1) resp = apiState();
      else if (url.indexOf("/api/legal") !== -1) resp = apiLegal(qs.id, qs.whole === "1");
      else if (url.indexOf("/api/move") !== -1) resp = apiMove(body);
      else if (url.indexOf("/api/pass") !== -1) resp = apiPass(body);
      else if (url.indexOf("/api/face") !== -1) resp = apiFace(body);
      else if (url.indexOf("/api/reset") !== -1) resp = apiReset();
      else resp = { error: "unknown api " + url };
      return Promise.resolve({ ok: true, json: () => Promise.resolve(resp) });
    }
    return realFetch(url, opts);
  };
})();
