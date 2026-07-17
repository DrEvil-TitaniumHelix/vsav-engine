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
    let left = 0;
    (H.guideAvoid || ['arrivals', 'tierpanel']).forEach(id => {
      const el = document.getElementById(id);
      // NOTE: these panels are position:fixed — offsetParent is always
      // null for them, so visibility must come from getClientRects()
      if (!el || el.style.display === 'none'
          || !el.getClientRects().length) return;
      const r = el.getBoundingClientRect();
      if (r.left < window.innerWidth * 0.45 && r.width)
        left = Math.max(left, r.right + 12);
    });
    guideEl.style.left = left + 'px';
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

  return { initFrame, apply, zoomAt, centerOn, navUnit, onRender, layoutBars,
           show, setGuide, setGuideSuffix, soleNext };
})();
