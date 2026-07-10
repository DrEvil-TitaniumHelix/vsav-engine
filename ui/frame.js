/* frame.js — the ENGINE-LEVEL client frame, shared by every game screen.
 *
 * One implementation, every game inherits it (index.html strategic client,
 * tactical.html tactical client, and any future screen). A capability added
 * here exists everywhere at once — features are never implemented per-game.
 *
 * Owns: pan clamping, zoom controls (+/−/fit + wheel math), topbar-aware
 * layout (the bar wraps; everything follows its real height), camera glide
 * (centerOn — AI step follow, unit nav), next/previous-unit stepping, and the
 * end-turn glow. Each screen calls initFrame(...) with the handful of hooks
 * that genuinely differ per screen (how to select a unit, which units can
 * still act, what "fit" means, which button glows).
 *
 * The screen keeps ownership of its pan/zoom state (panX/panY/scale as plain
 * globals) — frame.js reads/writes them through the hooks' get/set to avoid
 * cross-file globals.
 */

const FRAME = (() => {
  let H = null;   // hooks from initFrame

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
    (H.followTop || []).forEach(({ id, gap }) => {
      const el = document.getElementById(id);
      if (el) el.style.top = (h + (gap || 0)) + 'px';
    });
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
    const nav = document.getElementById('unitnav');
    if (nav) nav.style.display = n > 0 ? '' : 'none';
    const btn = document.getElementById(H.endBtnId);
    if (btn) btn.classList.toggle('pulse', H.turnDone());
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
    // the topbar wraps at narrow widths — everything below follows its height
    new ResizeObserver(layoutBars).observe(H.topbar);
    window.addEventListener('resize', layoutBars);
    layoutBars();
  }

  return { initFrame, apply, zoomAt, centerOn, navUnit, onRender, layoutBars };
})();
