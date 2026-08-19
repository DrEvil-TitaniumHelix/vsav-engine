/* frame.js — the ENGINE-LEVEL client frame, shared by every game screen.
 *
 * One implementation, every game inherits it (index.html strategic client,
 * tactical.html tactical client, and any future screen). A capability added
 * here exists everywhere at once — features are never implemented per-game.
 *
 * Owns: pan clamping, zoom controls (+/−/fit + wheel math), topbar-aware
 * layout, camera glide (centerOn — AI step follow, unit nav),
 * next/previous-unit stepping, and the end-turn glow. Each screen calls
 * initFrame(...) with the handful of hooks that genuinely differ per screen
 * (how to select a unit, which units can still act, what "fit" means, which
 * button glows).
 *
 * FIXED-POSITION DISCIPLINE (Bruce's rule): every control lives at a fixed
 * pixel position that never changes at runtime. Topbar elements are therefore
 * never display:none'd — FRAME.show() toggles visibility so a hidden control
 * keeps its layout slot, and variable-width text sits in fixed-width cells
 * (the .fixw class). Topbars must not flex-wrap; the window's minimum size
 * guarantees the row fits.
 *
 * The screen keeps ownership of its pan/zoom state (panX/panY/scale as plain
 * globals) — frame.js reads/writes them through the hooks' get/set to avoid
 * cross-file globals.
 */

const FRAME = (() => {
  let H = null;   // hooks from initFrame

  // ---------- fixed-position discipline ----------
  // show(): hide/reveal a topbar control WITHOUT surrendering its layout slot,
  // so nothing around it ever moves. Never use display:none in a topbar.
  function show(id, on) {
    const el = typeof id === 'string' ? document.getElementById(id) : id;
    if (!el) return;
    el.classList.toggle('holdspace', !on);
  }
  // shared frame CSS, injected once so every screen inherits it
  (() => {
    const st = document.createElement('style');
    st.textContent = `
      .holdspace { visibility:hidden !important; pointer-events:none; }
      .fixw { display:inline-block; overflow:hidden; text-overflow:ellipsis;
              white-space:nowrap; vertical-align:middle; }
      /* fixed control heights: text changes may never re-center the row */
      .tbrow .sidebtn, .tbrow select { height:30px; box-sizing:border-box;
                                       white-space:nowrap; }
      .tbrow .chip { height:26px; box-sizing:border-box; line-height:20px; }
      /* guidance banner: the always-there "what do I do now" strip, centered
         under the topbar. Overlay (pointer-events:none) — it never moves a
         control. One implementation for every screen. */
      #frameguide { position:fixed; top:90px; left:0; right:0; z-index:44;
                    text-align:center; pointer-events:none; }
      #frameguide div { display:inline-block; margin-top:8px; padding:6px 22px;
                        border-radius:16px; background:rgba(25,28,34,.92);
                        color:#eee; font-size:15px; border:1px solid #444;
                        max-width:76%; }
      #frameguide div.over { background:rgba(70,20,15,.95); font-size:20px;
                             padding:12px 30px; }
      #frameguide b { color:#ffd75e; }
      /* THE sole way forward (Bruce's rule): when only one button can advance
         the game, it wears a pulsing red border — everything else is just
         looking around. Applied via FRAME.soleNext(). */
      .solenext { border:2px solid #ff5040 !important; color:#fff !important;
                  animation: soleglow 1.1s ease-in-out infinite; }
      /* readable panel typography — no low-contrast text (Bruce 2026-07-17) */
      #guidepanel { color:#dde3ea; }
      #guidepanel h2 { color:#fff; font-size:16px; margin:4px 0 8px; }
      #guidepanel p, #guidepanel li { color:#cfd6dd; }
      #guidepanel b { color:#fff; }
      #guidepanel code { background:#2c2f36; color:#ffd75e;
                         padding:1px 5px; border-radius:4px; }
      #guidepanel ul, #guidepanel ol { margin:4px 0 8px; padding-left:20px; }
      #guidepanel li { margin:3px 0; }
      #rulespanel { color:#dde3ea; }
      #rulespanel .dim, #guidepanel .dim { color:#9aa3ad; }
      #rulespanel details { margin:2px 0; }
      #rulespanel summary { cursor:pointer; font-weight:600; padding:4px 0; }
      #rulespanel summary:hover { filter:brightness(1.18); }
      #rulespanel .rsbody { margin:2px 0 8px 14px; }
      #rulespanel mark { background:#7a5c1e; color:#ffe9b0;
                         border-radius:2px; padding:0 1px; }
      #rulespanel mark.cur { background:#e0a34e; color:#1a1d22; }
      @keyframes soleglow {
        0%,100% { box-shadow:0 0 0 0 rgba(255,80,64,.0); }
        50%     { box-shadow:0 0 12px 3px rgba(255,80,64,.7); } }`;
    document.head.appendChild(st);
  })();

  // ---------- guidance banner ----------
  let guideEl = null, guideSuffix = '';
  function setGuideSuffix(html) { guideSuffix = html || ''; }
  function guideAvoidPanels() {
    // the banner must never cover a left-side panel (the Vorpatzki-
    // overlay bug): start it right of any visible panel anchored left
    if (!guideEl) return;
    let left = 0, right = (H && H.guideRight) || 0;
    const W = window.innerWidth;
    const ids = (H.guideAvoid || ['arrivals'])
      .concat(['combat', 'pbmpanel', 'rulespanel', 'tablespanel', 'guidepanel', 'logdock']);
    ids.forEach(id => {
      const el = document.getElementById(id);
      // NOTE: these panels are position:fixed — offsetParent is always
      // null for them, so visibility must come from getClientRects()
      if (!el || el.style.display === 'none'
          || !el.getClientRects().length) return;
      const r = el.getBoundingClientRect();
      if (!r.width || r.bottom < guideEl.getBoundingClientRect().top) return;
      if (r.left < W * 0.45)
        left = Math.max(left, r.right + 12);
      else if (r.right > W * 0.55)
        right = Math.max(right, W - r.left + 12);
    });
    guideEl.style.left = left + 'px';
    guideEl.style.right = right + 'px';
  }
  function setGuide(html, over) {   // what should the player do RIGHT NOW?
    if (!guideEl) {
      guideEl = document.createElement('div');
      guideEl.id = 'frameguide';
      guideEl.appendChild(document.createElement('div'));
      document.body.appendChild(guideEl);
      if (H && H.guideRight) guideEl.style.right = H.guideRight + 'px';
    }
    const pill = guideEl.firstChild;
    pill.className = over ? 'over' : '';
    pill.style.display = html ? '' : 'none';
    const full = html ? html + guideSuffix : html;
    if (pill.innerHTML !== full) pill.innerHTML = full;
    guideAvoidPanels();
    // panels often re-render AFTER the guide in the same refresh — their
    // new size isn't measurable yet, so re-measure on the next frame
    // (the Vorpatzki-overlay bug's second life)
    requestAnimationFrame(guideAvoidPanels);
  }

  // ---------- sole-way-forward marker ----------
  // soleNext(x): x = element | id | CSS selector | null. Exactly one control
  // may wear the red "this is the only thing to click" border at a time;
  // null clears it (several options are open — no button is forced).
  function soleNext(x) {
    document.querySelectorAll('.solenext').forEach(e => e.classList.remove('solenext'));
    if (!x) return;
    const el = typeof x !== 'string' ? x
             : document.getElementById(x) || document.querySelector(x);
    if (el) el.classList.add('solenext');
  }

  // ---------- pan & zoom ----------
  function clampPan() {
    // the map may never leave the screen: keep >=120px visible on each axis
    const s = H.get();
    if (!s.mapW) return;
    const m = 120, vp = H.viewport, mw = s.mapW * s.scale, mh = s.mapH * s.scale;
    H.set({ panX: Math.min(vp.clientWidth - m, Math.max(m - mw, s.panX)),
            panY: Math.min(vp.clientHeight - m, Math.max(m - mh, s.panY)) });
  }
  function apply() {
    clampPan();
    const s = H.get();
    H.world.style.transform = `translate(${s.panX}px,${s.panY}px) scale(${s.scale})`;
    // zoom-compensation factor for markers that must stay readable at
    // any zoom (rings, badges): CSS uses calc(Npx * var(--ringpx))
    H.world.style.setProperty('--ringpx', (1 / s.scale).toFixed(3));
  }
  function zoomAt(cx, cy, f) {
    const s = H.get();
    const ns = Math.min(H.zoomMax, Math.max(H.zoomMin, s.scale * f));
    H.set({ panX: cx - (cx - s.panX) * (ns / s.scale),
            panY: cy - (cy - s.panY) * (ns / s.scale), scale: ns });
    apply();
  }
  function centerOn(x, y) {   // glide the viewport to a map point
    const s = H.get(), vp = H.viewport;
    H.world.classList.add('glide');
    H.set({ panX: vp.clientWidth / 2 - x * s.scale,
            panY: vp.clientHeight / 2 - y * s.scale });
    apply();
    setTimeout(() => H.world.classList.remove('glide'), 400);
  }

  // ---------- topbar-aware layout ----------
  function layoutBars() {
    const h = H.topbar.offsetHeight;
    H.viewport.style.top = h + 'px';
    if (guideEl) guideEl.style.top = h + 'px';
    (H.followTop || []).forEach(({ id, gap }) => {
      const el = document.getElementById(id);
      if (el) el.style.top = (h + (gap || 0)) + 'px';
    });
    guideAvoidPanels();
  }

  // ---------- next / previous unit to act ----------
  let navIdx = -1;
  async function navUnit(dir) {
    const list = H.actable().sort((a, b) =>
      a.hexnum - b.hexnum || (a.id < b.id ? -1 : 1));
    if (!list.length) return;
    navIdx = ((navIdx + dir) % list.length + list.length) % list.length;
    const u = list[navIdx];
    centerOn(u.x, u.y);
    await H.select(u);
  }

  // ---------- per-render frame state (nav visibility + end-turn glow) ----------
  function onRender() {
    const n = H.actable().length;
    show('unitnav', n > 0);   // keeps its slot when hidden — nothing shifts
    // superseded green pulse: the red soleNext border (set by each screen's
    // guidance state machine) is now the "you're done, end the turn" signal
  }

  const UMPIRE = 'Umpire';
  let refuseT = null;
  function refusal(reasons, opts) {
    opts = opts || {};
    const rs = (reasons && reasons.length) ? reasons : ['(no reason given)'];
    let ov = document.getElementById('umpirecard');
    if (!ov) {
      ov = document.createElement('div');
      ov.id = 'umpirecard';
      ov.style.cssText = `display:none; position:fixed; top:50%; left:50%;
        transform:translate(-50%,-50%); width:min(560px,92vw); z-index:300;
        background:#26221f; border:2px solid #c0564a; border-radius:12px;
        padding:16px 20px; font-size:14px; line-height:1.5; color:#e6dfd8;
        box-shadow:0 10px 40px rgba(0,0,0,.75); cursor:pointer`;
      document.body.appendChild(ov);
    }
    const ctx = opts.context !== undefined ? opts.context
      : (guideEl && guideEl.firstChild.innerHTML
         ? `<b>Where the game stands:</b> ${guideEl.firstChild.innerHTML}` : '');
    ov.innerHTML =
      `<div style="font-size:17px; font-weight:700; color:#e88a7a">⚖ ${UMPIRE}
       — action refused</div>` +
      (opts.hint ? `<div style="margin:10px 0 2px; font-size:15px; color:#f0e6b8">
       <b>What to do:</b> ${opts.hint}</div>` : '') +
      `<div style="margin-top:10px; color:#9aa3ad; font-size:12px">The ruling —
       numbers in brackets cite the game's own rulebook:</div>
       <ul style="margin:4px 0 0 18px; padding:0">
       ${rs.map(r => `<li>${escp(r)}</li>`).join('')}</ul>` +
      (ctx ? `<div style="margin-top:10px; padding-top:8px;
       border-top:1px solid #4a423c; color:#b9c2cc">${ctx}</div>` : '') +
      `<div style="margin-top:12px; color:#9aa3ad; font-size:11px">Nothing on
       the board changed. Click to dismiss.</div>`;
    ov.style.display = 'block';
    clearTimeout(refuseT);
    refuseT = setTimeout(() => { ov.style.display = 'none'; }, 15000);
    ov.onclick = () => { clearTimeout(refuseT); ov.style.display = 'none'; };
  }

  // ---------- shared top-right panels: Mode / Rules / Tables ----------
  // One implementation for every screen (Bruce 2026-07-17: "all of these
  // interfaces … essentially unified"). A client calls
  // initPanels({game, flow, clientItems, toast, onSeats}) once; the frame owns
  // the buttons, the panels (created if the page doesn't declare them), the
  // open-one-close-others behavior, and the seat dialog.
  let PH = null;
  const $id = (i) => document.getElementById(i);
  const escp = (s) => String(s).replace(/[&<>]/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const PANEL_IDS = ['rulespanel', 'tablespanel', 'pbmpanel', 'guidepanel'];
  const BTN_FOR = { rulesbtn: 'rulespanel', tablesbtn: 'tablespanel',
                    guidebtn: 'guidepanel' };

  function ensurePanel(id, style) {
    if ($id(id)) return;
    const d = document.createElement('div');
    d.id = id;
    d.style.cssText = style;
    document.body.appendChild(d);
  }
  function soloPanel(id) {
    let opened = false;
    PANEL_IDS.forEach(p => {
      const el = $id(p);
      if (!el) return;
      if (p === id) { opened = el.style.display !== 'block';
                      el.style.display = opened ? 'block' : 'none'; }
      else el.style.display = 'none';
    });
    Object.entries(BTN_FOR).forEach(([b, p]) => {
      const el = $id(b);
      if (el) el.classList.toggle('on', p === id && opened);
    });
    return opened;
  }
  // ---------- seat model: one Mode button, two seat pickers ----------
  const SEAT_DESC = {
    human: 'you, at this screen (two Human seats = hot-seat)',
    basic: "the shipped policy AI",
    champion: 'the trained champion (self-play, graduation bar met)',
    harness: 'an outside model, moving through the match folder' };
  function seatsInfo() { const g = PH && PH.game(); return g && g.seats; }
  function renderModeBtn() {
    const B = $id('modebtn');
    if (!B) return;
    const S = seatsInfo();
    if (!S) { show(B, false); return; }
    show(B, true);
    B.textContent = `Mode: ${S.pairing} ▾`;
    B.title = 'Who sits in each seat — Human, Basic AI, Champion AI, Harness; '
      + 'every pairing is legal, computer vs computer included';
    B.classList.toggle('on', !!$id('seatsdlg'));
  }
  function closeSeatsDialog() {
    const d = $id('seatsdlg');
    if (d) d.remove();
    renderModeBtn();
  }
  function openSeatsDialog() {
    if ($id('seatsdlg')) { closeSeatsDialog(); return; }
    const S = seatsInfo(), G = PH.game();
    if (!S) return;
    const ov = document.createElement('div');
    ov.id = 'seatsdlg';
    ov.style.cssText = `position:fixed; inset:0; background:rgba(0,0,0,.55);
      z-index:70; display:flex; align-items:center; justify-content:center`;
    const label = id => ((G.sides || []).find(x => x.id === id) || {label: id}).label;
    const gs = S.generalship;
    const seatDesc = k => (k === 'champion' && gs)
      ? `the trained champion — Generalship ${gs.rung}/10, ${gs.general}` : (SEAT_DESC[k] || '');
    const rows = S.order.map(sd => `
      <div style="display:flex; align-items:center; gap:14px; margin:12px 0">
        <b style="width:130px; font-size:18px">${escp(label(sd))}</b>
        <select data-side="${sd}" style="flex:1; background:#1a1d22; color:#f0f4f8;
          border:1px solid #4a5058; border-radius:8px; padding:9px 12px; font-size:17px">
          ${S.available.map(k => `<option value="${k}" style="color:#f0f4f8; background:#1a1d22" ${S.current[sd] === k ? 'selected' : ''}>
             ${escp(S.labels[k])} — ${escp(seatDesc(k))}</option>`).join('')}
        </select></div>`).join('');
    ov.innerHTML = `<div style="width:760px; max-width:94vw; background:#23262c;
        border:1px solid #3a3f47; border-radius:12px; padding:22px 26px;
        font-size:17px; line-height:1.5; color:#e6ebf0; box-shadow:0 8px 30px rgba(0,0,0,.6)">
      <div style="font-size:24px; font-weight:700; margin-bottom:8px; color:#fff">Mode — who plays each seat</div>
      <div style="margin-bottom:12px; color:#b9c2cc">The ${UMPIRE} checks every action whoever
        sits in the seat. Any pairing is legal: Human vs Human is hot-seat, Human vs a
        computer is a match, computer vs computer plays itself for you to watch.
        Seats change immediately; the game continues from where it stands.</div>
      ${rows}
      ${gs ? `<div style="margin:6px 0 2px; padding:10px 12px; background:#1a1d22; border:1px solid #3a3f47;
        border-radius:8px; color:#c9d3dd; font-size:15px; line-height:1.45">
        <b style="color:#f0f4f8">Generalship ${gs.rung}/10 — ${escp(gs.general)}.</b>
        ${escp(gs.meaning)}.<br><span style="color:#98a3ae">Record: ${escp(gs.evidence)}. The scale is
        the training record; a rung the record does not prove is never shown.</span></div>` : ''}
      <div id="seatsprev" style="margin:14px 0 8px; color:#9cc4ee; font-weight:700; font-size:19px"></div>
      <div style="display:flex; gap:12px; justify-content:flex-end; margin-top:12px">
        <button id="seatscancel" class="sidebtn" style="font-size:16px; padding:8px 18px; color:#e6ebf0">Cancel</button>
        <button id="seatsapply" class="sidebtn" style="font-weight:700; font-size:16px; padding:8px 22px; color:#fff">Apply</button>
      </div></div>`;
    document.body.appendChild(ov);
    const sels = [...ov.querySelectorAll('select')];
    const preview = () => { $id('seatsprev').textContent =
      sels.map(x => S.names[x.value]).join(' vs '); };
    sels.forEach(x => x.onchange = preview);
    preview();
    ov.onclick = e => { if (e.target === ov) closeSeatsDialog(); };
    $id('seatscancel').onclick = closeSeatsDialog;
    $id('seatsapply').onclick = async () => {
      const seats = {};
      sels.forEach(x => seats[x.dataset.side] = x.value);
      const r = await (await fetch('/api/seats', {method: 'POST',
        body: JSON.stringify({seats})})).json();
      if (r.error) { (PH.toast || alert)(r.error); return; }
      if (G) G.seats = r.seats;
      closeSeatsDialog();
      if (PH.onSeats) PH.onSeats(r.seats);
    };
    renderModeBtn();
  }
  let rulesQ = '', rulesBuilt = '', rulesBodies = [], rulesHits = [], rulesCur = 0;
  function rulesMark(el, q) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), ts = [];
    while (w.nextNode()) ts.push(w.currentNode);
    let n = 0;
    ts.forEach(t => {
      const s = t.nodeValue, ls = s.toLowerCase();
      let i = ls.indexOf(q);
      if (i < 0) return;
      const f = document.createDocumentFragment();
      let p = 0;
      while (i >= 0) {
        f.appendChild(document.createTextNode(s.slice(p, i)));
        const m = document.createElement('mark');
        m.textContent = s.slice(i, i + q.length);
        f.appendChild(m);
        n++; p = i + q.length; i = ls.indexOf(q, p);
      }
      f.appendChild(document.createTextNode(s.slice(p)));
      t.parentNode.replaceChild(f, t);
    });
    return n;
  }
  function renderRules() {
    const P = $id('rulespanel');
    if (!P || P.style.display !== 'block') return;
    const G = PH.game(), FLOW = PH.flow();
    const rs = FLOW && FLOW.rules_scope;
    const ghdr = t => `<div style="margin:12px 0 2px; padding-top:8px;
      border-top:1px solid #3a3f47; color:#8b93a0; font-size:11px;
      letter-spacing:.12em; text-transform:uppercase">${t}</div>`;
    let top = `<b>Rules</b>`;
    top += `<div style="position:sticky; top:-12px; margin:6px -4px 0;
            padding:6px 4px; background:#23262c; z-index:5; display:flex;
            gap:6px; align-items:center">
            <input id="rsq" type="search" placeholder="Search these rules…"
             autocomplete="off" style="flex:1; min-width:0; background:#1a1d22;
             color:#dfe5ec; border:1px solid #3a3f47; border-radius:6px;
             padding:5px 8px; font-size:13px; outline:none">
            <span id="rsn" class="dim" style="white-space:nowrap; font-size:12px"></span>
            <button id="rsp" title="Previous match (Shift+Enter)" style="background:#2c2f36;
             color:#b9c2cc; border:1px solid #3a3f47; border-radius:6px;
             padding:3px 9px; cursor:pointer">‹</button>
            <button id="rsx" title="Next match (Enter)" style="background:#2c2f36;
             color:#b9c2cc; border:1px solid #3a3f47; border-radius:6px;
             padding:3px 9px; cursor:pointer">›</button></div>`;
    const GR = `The game's rules`, PL = `This platform`;
    top += ghdr(GR);
    const SI = G && G.seats;
    if (SI && rs) top += `<div style="margin:4px 0 2px; color:#8fb8d8">${escp(SI.pairing)}
                 — the ${UMPIRE} checks every action, whoever sits in the seat
                 (Mode button changes the seats).</div>`;
    if (rs && rs.banner)
      top += `<div style="margin:6px 0; padding:5px 8px; border-radius:4px; font-weight:600;
              ${/^PLAYABLE/.test(rs.banner) ? 'background:#28401f;color:#b8e09a'
                                            : 'background:#4a3820;color:#e8c37a'}">${rs.banner}</div>`;
    if (!rs)
      top += `<div class="dim" style="margin-top:6px">No rules are encoded for this
           game folder yet; move pieces as you would at a physical table.</div>`;
    const secs = [];
    const sec = (grp, color, title, n, body) => secs.push({grp, color, title, n, body});
    if (rs) {
      const enf = rs.enforced || [];
      sec(GR, '#9fc27f', 'Enforced', enf.length,
        `<div class="dim" style="margin:4px 0 8px">${FLOW.scenario || G.name}.
         Every proposed action goes to the ${UMPIRE} — the rules engine — which
         accepts or refuses it against these rules. Numbers in parentheses cite
         the game's own rulebook sections.</div>
         <ul>${enf.map(r => `<li>${r}</li>`).join('')}</ul>`);
      if (rs.not_enforced && rs.not_enforced.length)
        sec(GR, '#e0a34e', 'Not yet enforced — umpire these yourself',
          rs.not_enforced.length,
          `<ul>${rs.not_enforced.map(r => `<li>${r}</li>`).join('')}</ul>`);
      if (rs.rulings && rs.rulings.length)
        sec(GR, '#8fb8d8', 'Engine rulings & scope notes', rs.rulings.length,
          `<ul>${rs.rulings.map(r => `<li>${r}</li>`).join('')}</ul>`);
    }
    const SD = G && G.source_defects;
    if (SD && SD.list && SD.list.length)
      sec(GR, '#c99ae0', 'Defects found in the printed game', SD.list.length,
        `<div class="dim" style="margin:4px 0 6px">Encoding a game is a formal check of its own
         rulebook. These are defects of the ORIGINAL published game (editing errors,
         contradictions, undefined cases), each with the resolution this engine enforces and
         the authority for that resolution.</div><ul>` +
        SD.list.map(d =>
          `<li><b>${d.defect}</b> <span class="dim">[${d.kind}; rules ${d.rules.join(', ')}]</span><br>
           <span style="color:#9fc27f">Resolved:</span> ${d.resolution}<br>
           <span class="dim">Authority: ${d.authority}</span></li>`).join('') + `</ul>`);
    const gated = !!FLOW, hasArr = gated && !!FLOW.arrivals,
          hasCbt = gated && !!FLOW.combat;
    const ci = [];
    ci.push(`<li><b>Sides</b> — pick who you're playing with the buttons top-left; switch
          any time for hot-seat play.</li>`);
    ci.push(`<li><b>Counters</b> — hover for a unit's stats card; click to select (the card
          pins bottom-left). Clicking a stack offers each unit or the whole stack.</li>`);
    ci.push(gated
      ? `<li><b>Moving</b> — ${MOVE_HINT}. Green hexes are the legal
         destinations the ${UMPIRE} computed (numbers = movement points spent);
         anything else snaps back. Illegal proposals are refused with the rule
         citation, centre-screen.</li>`
      : `<li><b>Moving</b> — drag the selected counter anywhere on the board, printed
         tracks included, exactly as in VASSAL. Nothing is checked in free play.</li>`);
    ci.push(`<li><b>Pass</b> — marks the selected unit done without moving.</li>`);
    if (gated)
      ci.push(`<li><b>↶ Undo</b> — takes back your most recent decision (up to 5 in a
            row), unwinding the AI's replies after it. The engine replays the
            shortened game log and re-verifies every verdict, die and state hash on
            the way; repeating an action after an undo reuses the same seeded dice —
            no reroll fishing. Not available in mailed or LLM matches, where accepted
            moves stand.</li>`);
    if (G.facing)
      ci.push(`<li><b>Facing</b> — right-click a counter to rotate it.</li>`);
    if (hasArr)
      ci.push(`<li><b>Arrivals & sea panel</b> (top-left) — supply rolls and landings,
            reinforcement placement, embark/debark, replacements: every button submits
            through the gate.</li>`);
    if (hasCbt)
      ci.push(`<li><b>Combat panel</b> (top-right, combat phase) — click your units and
            enemy units to build a battle, watch the live odds preview, then resolve:
            the engine rolls its own seeded die on the validated CRT and walks you
            through retreats, exchanges and advances.</li>`);
    (PH.clientItems ? PH.clientItems(gated) : []).forEach(li => ci.push(li));
    if (gated)
      ci.push(`<li><b>End player turn</b> — asks the ${UMPIRE} to close your turn; it
            refuses (with citations) while obligations are open.</li>`);
    if (SI && gated)
      ci.push(`<li><b>Mode</b> — who sits in each seat: ${SI.available.map(k => SI.labels[k]).join(' / ')}.
            Every pairing is legal (hot-seat, you vs a computer, computer vs computer);
            seats change at once, the game continues.</li>`);
    ci.push(`<li><b>Reset game</b> — restarts the scenario from its setup.</li>`);
    ci.push(`<li><b>VASSAL interop</b> — the live save (live\\game_*.vsav) is a real
          VASSAL save you can open in the desktop app at any time.</li>`);
    sec(PL, '#d8c98f', 'Using this client', ci.length, `<ul>${ci.join('')}</ul>`);
    const CR = G && G.credits;
    if (CR) {
      let cb = `<ul>`;
      if (CR.game) {
        const gm = CR.game;
        cb += `<li><b>${gm.title}</b> — ${gm.publisher}, ${gm.year}.<br>
              ${gm.design}${gm.development ? '; ' + gm.development : ''}${gm.art ? '; ' + gm.art : ''}
              <span class="dim">(${gm.source})</span></li>`;
      }
      if (CR.module) {
        const md = CR.module;
        cb += `<li><b>${md.title}</b> — ${md.implementation}.<br>
              With: ${md.contributors}.<br>
              <span class="dim">${md.library} (${md.source})</span></li>`;
      }
      if (CR.note) cb += `<li class="dim">${CR.note}</li>`;
      sec(PL, '#8fb8d8', 'Credits', null, cb + `</ul>`);
    }
    const RD = G && G.rules_docs;
    if (RD) {
      const links = Object.entries(RD).filter(([k, v]) =>
        typeof v === 'string' && v.startsWith('http'));
      if (links.length)
        sec(PL, '#d8c98f', 'Official rules — free from the publisher', links.length,
          `<ul>` + links.map(([k, v]) =>
            `<li><a href="${v}" target="_blank" rel="noopener"
             style="color:#9cc4ee">${k.replace(/_/g, ' ')}</a></li>`).join('') + `</ul>`);
    }
    const DOCS = (window.BYO_MANIFEST && window.BYO && BYO.extract)
      ? (window.BYO_MANIFEST.docs || []) : [];
    if (DOCS.length)
      sec(PL, '#d8c98f', 'Rulebook & charts — from your module', DOCS.length,
        `<div class="dim" style="margin:4px 0 6px">These open the original
         documents packed inside YOUR module file, read locally in your
         browser — this site does not ship them.</div>` +
        DOCS.map((d, i) => `<button class="sidebtn" data-doc="${i}"
           style="margin:2px 6px 2px 0">${d.label}</button>`).join(''));
    sec(PL, '#9aa3ad', 'Copyright', null,
      `<div class="dim">Rules here are restated in our
       own words for engine enforcement — game mechanics are not copyrightable,
       but the game's printed text and art are, and remain the publisher's.
       Support the original game.</div>`);
    let grp = GR, bodyH = '';
    secs.forEach(s => {
      if (s.grp !== grp) { bodyH += ghdr(s.grp); grp = s.grp; }
      bodyH += `<details class="rsec"><summary style="color:${s.color}">${s.title}${
        s.n != null ? ` <span style="font-weight:400;color:#8b93a0">(${s.n})</span>` : ''
      }</summary><div class="rsbody">${s.body}</div></details>`;
    });
    const built = top + bodyH;
    if (built === rulesBuilt && P.firstChild) return;
    rulesBuilt = built;
    P.innerHTML = built;
    rulesBodies = [];
    P.querySelectorAll('.rsbody').forEach(b => rulesBodies.push(b.innerHTML));
    P.onclick = async ev => {
      const btn = ev.target.closest('[data-doc]');
      if (!btn) return;
      const d = DOCS[+btn.dataset.doc];
      const label = btn.textContent;
      btn.disabled = true; btn.textContent = 'Opening…';
      try {
        const urls = [];
        for (const e of d.entries) urls.push(await BYO.entryUrl(d.req, e));
        if (urls.length === 1) window.open(urls[0], '_blank');
        else {
          const w = window.open('', '_blank');
          w.document.write(`<title>${label}</title>
            <body style="margin:0; background:#191c22; text-align:center">`
            + urls.map(u => `<img src="${u}"
                style="max-width:100%; display:block; margin:8px auto">`).join('')
            + '</body>');
          w.document.close();
        }
      } catch (e) { (PH.toast || alert)('Could not open: ' + (e.message || e)); }
      btn.disabled = false; btn.textContent = label;
    };
    const box = P.querySelector('#rsq'), rsn = P.querySelector('#rsn');
    const setCur = (i, scroll) => {
      if (!rulesHits.length) return;
      rulesCur = ((i % rulesHits.length) + rulesHits.length) % rulesHits.length;
      rulesHits.forEach((m, j) => m.classList.toggle('cur', j === rulesCur));
      rsn.textContent = `${rulesCur + 1} of ${rulesHits.length}`;
      if (scroll !== false) rulesHits[rulesCur].scrollIntoView({block: 'center'});
    };
    const applySearch = scroll => {
      rulesQ = box.value.trim();
      const q = rulesQ.toLowerCase(), live = q.length >= 2;
      P.querySelectorAll('.rsec').forEach((d, i) => {
        const b = d.querySelector('.rsbody');
        b.innerHTML = rulesBodies[i];
        d.open = live && rulesMark(b, q) > 0;
      });
      rulesHits = Array.from(P.querySelectorAll('.rsbody mark'));
      rsn.textContent = live && !rulesHits.length ? 'no matches' : '';
      if (live && rulesHits.length) setCur(0, scroll);
    };
    box.oninput = () => applySearch(true);
    box.onkeydown = ev => {
      if (ev.key !== 'Enter') return;
      ev.preventDefault();
      setCur(rulesCur + (ev.shiftKey ? -1 : 1), true);
    };
    P.querySelector('#rsp').onclick = () => setCur(rulesCur - 1, true);
    P.querySelector('#rsx').onclick = () => setCur(rulesCur + 1, true);
    if (rulesQ) { box.value = rulesQ; applySearch(false); }
  }
  // ---------- tables panel (transcribed CRT / to-hit — the data the gate uses) ----------
  async function renderTables() {
    const P = $id('tablespanel');
    if (!P || P.style.display !== 'block') return;
    P.innerHTML = `<b>Game tables</b><div class="cite">Loading…</div>`;
    let tables = [];
    try { tables = (await (await fetch('/api/tables')).json()).tables || []; }
    catch (e) { P.innerHTML = `<b>Game tables</b><div class="cite">Could not load tables.</div>`; return; }
    let h = `<b>Game tables</b><div class="cite">Transcribed from the rulebook and cited — the
             same data the engine resolves combat on, not scanned images.</div>`;
    if (!tables.length)
      h += `<div class="dim" style="margin-top:6px">This game has no encoded combat tables
            (none applicable).</div>`;
    for (const t of tables) {
      h += `<h3>${escp(t.title)}</h3>`;
      if (t.cite) h += `<div class="cite">${escp(t.cite)}</div>`;
      h += `<div style="overflow-x:auto"><table><thead><tr>`;
      t.columns.forEach(c => h += `<th>${escp(c)}</th>`);
      h += `</tr></thead><tbody>`;
      t.rows.forEach(r => { h += `<tr>`; r.forEach(c => h += `<td>${escp(c)}</td>`); h += `</tr>`; });
      h += `</tbody></table></div>`;
      if (t.legend && t.legend.length) {
        h += `<div class="legend">`;
        t.legend.forEach(l => h += `<div><code>${escp(l.code)}</code>${escp(l.text)}</div>`);
        h += `</div>`;
      }
      if (t.notes && t.notes.length) {
        h += `<ul class="notes">`;
        t.notes.forEach(n => h += `<li>${escp(n)}</li>`);
        h += `</ul>`;
      }
    }
    P.innerHTML = h;
  }
  // ---------- guide panel (engine-level, Bruce 2026-07-17: every game) -----
  // Sections are GENERATED from what the engine already knows (game family,
  // seats, victory text carried as data in game.json "guide") plus any
  // hand-written per-game sections from that same block — all our own words.
  const TURN_GUIDE = {
    tactical:
      `<h2>How a turn works</h2>
       <p>Each turn has two segments. In the <b>movement segment</b> the first
       player moves any of his units — click a unit, then drag it to one of the
       green hexes the engine lights up — and the other side follows. In the
       <b>combat segment</b> fire alternates one unit at a time: select your
       unit, click an enemy in range, and the engine resolves the shot on the
       validated tables with its own seeded dice. Damage takes effect at once.
       <b>End movement</b> / <b>Pass fire</b> close your part of a segment.</p>`,
    strategic:
      `<h2>How a turn works</h2>
       <p>Each game turn one side is the phasing player: first it moves — click
       a unit, drag it to a green legal hex — then it declares battles in the
       combat phase by clicking its attackers and an adjacent enemy stack. The
       engine prices the battle, rolls its own seeded die on the validated
       table, and walks both players through retreats, exchanges and advances.
       Supply, arrivals and reinforcements appear in their own panel when the
       scenario uses them. <b>End player turn</b> hands the turn over; the gate
       refuses (with citations) while you still owe it something.</p>`,
    napoleonic:
      `<h2>How a turn works</h2>
       <p>A turn runs: <b>Pool Placement</b> (tick which commands you commit),
       <b>Initiative</b>, alternating <b>LIM activations</b> (each drawn
       command activates Full or Limited), then <b>non-LIM</b> commands, and a
       closing <b>Rally</b> step. Combat is part of an activation: fire by
       clicking an enemy in range, shock by clicking an adjacent enemy and
       choosing the attack. The defender gets real decisions — return fire,
       forming square, reactions — and the banner always names whose decision
       the game is waiting on. The turn-flow strip under the banner shows where
       you are.</p>`,
    free:
      `<h2>How a turn works</h2>
       <p>No rules are encoded for this game folder. Move any piece anywhere,
       exactly as at a physical table or in VASSAL.</p>`,
  };
  function guideSections() {
    const G = PH.game(), FLOW = PH.flow();
    const gd = (G && G.guide) || {};
    const gated = !!FLOW;
    const mode = !FLOW ? 'free'
      : FLOW.mode === 'napoleonic' ? 'napoleonic'
      : FLOW.segment !== undefined ? 'tactical' : 'strategic';
    const S = [];
    S.push(['This game',
      `<h2>${G.name}</h2>
       <p>Sides: ${G.sides.map((s) => s.label).join(' vs ')}. Pick yours top-left;
       switch any time for hot-seat play${gated ? ' — every action still goes' +
       ' through the same rules gate' : ''}.</p>
       ${G.seats && gated ? `<p>${escp(G.seats.pairing)} — the ${UMPIRE} checks every action
          whoever sits in a seat; the <b>Mode</b> button changes the seats
          (${G.seats.available.map(k => G.seats.labels[k]).join(' / ')}; any pairing).</p>` : ''}`]);
    S.push(['How a turn works', TURN_GUIDE[mode]]);
    if (gd.victory)
      S.push(['How to win', `<h2>How to win</h2><p>${gd.victory}</p>`]);
    (gd.sections || []).forEach((s) => S.push([s.title, s.html]));
    S.push(['The interface',
      `<h2>The interface</h2>
       <ul><li>The <b>banner</b> under the top bar always says what to do right
       now; when only one button can advance the game it wears a pulsing red
       border.</li>
       <li><b>Hover</b> a counter for its stats card; <b>unit ▶ / ◀ unit</b>
       (or the N / B keys) jump between your units still to act.</li>
       <li><b>Rules</b> shows exactly what the engine enforces (with rulebook
       section numbers) and this game's credits; <b>Tables</b> shows the
       transcribed data the engine plays on.</li>
       ${G.seats && G.seats.available.length > 1 ? `<li>A <b>computer seat</b>
       plays its side itself — stepped (press SPACE per action) or auto, at
       slow/medium/fast pace. It proposes through the same gate you play
       through; the <b>Mode</b> button decides who sits where.</li>` : ''}
       ${gated ? `<li><b>↶ Undo</b> takes back your last decision (up to 5
       in a row) — the AI's replies after it are unwound too. Dice are seeded,
       so redoing the same action gives the same result.</li>` : ''}
       <li><b>Reset game</b> restarts the scenario.</li></ul>`]);
    return S;
  }
  let guideSec = 0;
  function renderGuidePanel() {
    const P = $id('guidepanel');
    if (!P || P.style.display !== 'block') return;
    const S = guideSections();
    if (guideSec >= S.length) guideSec = 0;
    let nav = '';
    S.forEach(([t], i) => {
      nav += `<span data-g="${i}" style="display:inline-block; padding:5px 10px;
        margin:0 4px 6px 0; border-radius:6px; cursor:pointer; font-size:12px;
        ${i === guideSec ? 'background:#3a6ea5; color:#fff'
                         : 'background:#2c2f36; color:#b9c2cc'}">${t}</span>`;
    });
    P.innerHTML = `<div>${nav}</div><div class="gbody">${S[guideSec][1]}</div>`;
    P.querySelectorAll('[data-g]').forEach((el) => el.onclick = () => {
      guideSec = +el.dataset.g;
      renderGuidePanel();
    });
  }

  function initPanels(hooks) {
    PH = hooks;
    // panels a screen doesn't declare are created with the standard look
    ensurePanel('rulespanel',
      `display:none; position:fixed; top:52px; right:8px; width:440px;
       max-width:44vw; max-height:calc(100vh - 70px); overflow:auto;
       background:#23262c; border:1px solid #3a3f47; border-radius:10px;
       padding:12px 16px; z-index:60; font-size:13px; line-height:1.45;
       box-shadow:0 6px 24px rgba(0,0,0,.5)`);
    ensurePanel('guidepanel',
      `display:none; position:fixed; top:52px; right:8px; width:560px;
       max-width:56vw; max-height:calc(100vh - 70px); overflow:auto;
       background:#23262c; border:1px solid #3a3f47; border-radius:10px;
       padding:12px 16px; z-index:60; font-size:13px; line-height:1.5;
       box-shadow:0 6px 24px rgba(0,0,0,.5)`);
    const gb = $id('guidebtn');
    if (gb) gb.onclick = () => {
      if (soloPanel('guidepanel')) renderGuidePanel();
    };
    const mb = $id('modebtn');
    if (mb) mb.onclick = openSeatsDialog;
    const rb = $id('rulesbtn');
    if (rb) rb.onclick = () => {
      if (soloPanel('rulespanel')) renderRules();
    };
    const tab = $id('tablesbtn');
    if (tab) tab.onclick = () => {
      if (soloPanel('tablespanel')) renderTables();
    };
  }

  // ---------- undo (engine rule: one USER decision per press) ----------
  // The server owns the semantics (log-truncate + verified replay, window
  // of 5, refused in PBM/SALVO); the frame owns the one button every
  // screen shares. A screen adds <button id="undobtn"> to its topbar,
  // calls initUndo once, and renderUndo(state.undo) on every refresh.
  let undoH = null, undoBusy = false;
  function initUndo(hooks) {           // {refresh, toast}
    undoH = hooks || {};
    const b = $id('undobtn');
    if (!b) return;
    b.onclick = async () => {
      if (undoBusy) return;
      undoBusy = true;
      b.disabled = true;
      try {
        const r = await (await fetch('/api/undo',
          {method: 'POST', body: '{}'})).json();
        if (r.error) (undoH.toast || alert)(r.error);
        else if (undoH.toast) undoH.toast('Undid: ' + (r.undone || 'last decision'));
      } catch (e) { (undoH.toast || alert)('Undo failed: ' + (e.message || e)); }
      undoBusy = false;
      if (undoH.refresh) undoH.refresh();
    };
  }
  function renderUndo(st) {            // st = /api/state 's undo block
    const b = $id('undobtn');
    if (!b) return;
    const usable = !!(st && !st.blocked);
    show(b, usable);                   // keeps its layout slot when hidden
    b.disabled = !(usable && st.available > 0);
    b.textContent = usable && st.available > 0
      ? `↶ Undo (${st.available})` : '↶ Undo';
    b.title = !st ? ''
      : st.blocked ? 'Undo is not available in a match: ' + st.blocked
      : st.available > 0
        ? `take back your last decision${st.last ? ' (' + st.last + ')' : ''} — `
          + `up to ${st.max} in a row; the AI's replies after it are unwound too`
        : 'nothing to undo yet';
  }

  // ---------- wiring ----------
  function initFrame(hooks) {
    H = hooks;
    // zoom buttons + wheel
    const vpc = () => { const r = H.viewport.getBoundingClientRect();
                        return [r.left + r.width / 2, r.top + r.height / 2]; };
    document.getElementById('zin').onclick  = () => zoomAt(...vpc(), 1.3);
    document.getElementById('zout').onclick = () => zoomAt(...vpc(), 1 / 1.3);
    document.getElementById('zfit').onclick = () => H.fit();
    H.viewport.addEventListener('wheel', e => {
      e.preventDefault();
      zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });
    // unit nav buttons + N/B keys
    const prev = document.getElementById('prevunit'),
          next = document.getElementById('nextunit');
    if (prev) prev.onclick = () => navUnit(-1);
    if (next) next.onclick = () => navUnit(1);
    document.addEventListener('keydown', e => {
      if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
      if (e.code === 'KeyN') { e.preventDefault(); navUnit(1); }
      if (e.code === 'KeyB') { e.preventDefault(); navUnit(-1); }
    });
    // the topbar's height is fixed by design, but keep everything below
    // following its real height as a safety net (fonts, zoom levels)
    new ResizeObserver(layoutBars).observe(H.topbar);
    window.addEventListener('resize', layoutBars);
    layoutBars();
  }

  // THE movement instruction — one gesture, one sentence, every client
  // (Bruce 2026-07-18: never a per-game movement heuristic again). Both
  // clients move the same way: click to select, hold-drag, release.
  const MOVE_HINT = 'click a unit — its legal hexes light up green — then '
    + 'press and <b>HOLD</b> the counter, drag it onto a green hex, and '
    + 'release to drop';

  return { initFrame, apply, zoomAt, centerOn, navUnit, onRender, layoutBars,
           show, setGuide, guideAvoidPanels, setGuideSuffix, soleNext, MOVE_HINT,
           initUndo, renderUndo,
           initPanels, soloPanel, renderModeBtn, openSeatsDialog,
           renderRules, renderTables,
           refusal, UMPIRE };
})();
