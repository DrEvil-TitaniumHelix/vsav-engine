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
      #rulespanel, #tierpanel { color:#dde3ea; }
      #rulespanel .dim, #tierpanel .dim, #guidepanel .dim { color:#9aa3ad; }
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

  // ---------- shared top-right panels: Tier / Rules / Tables ----------
  // One implementation for every screen (Bruce 2026-07-17: "all of these
  // interfaces need tier selection … essentially unified"). A client calls
  // initPanels({game, flow, clientItems, toast}) once; the frame owns the
  // buttons, the panels (created if the page doesn't declare them), the
  // open-one-close-others behavior, and the tier-change flow.
  let PH = null, tierArm = null;
  const $id = (i) => document.getElementById(i);
  const escp = (s) => String(s).replace(/[&<>]/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
  const PANEL_IDS = ['rulespanel', 'tablespanel', 'tierpanel', 'pbmpanel',
                     'guidepanel'];
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
  function renderTierBtn() {
    const B = $id('tierbtn');
    if (!B) return;
    const g = PH && PH.game(), T = g && g.tier;
    if (!T || T.choices.length < 2) { show(B, false); return; }
    show(B, true);
    B.textContent = `Tier ${T.active} of ${T.earned} ▾`;
    B.classList.toggle('on', $id('tierpanel').style.display === 'block');
  }
  function renderTierPanel() {
    const P = $id('tierpanel'), T = PH.game().tier;
    let h = `<b>Engine enforcement tier</b>
             <div class="dim" style="margin:4px 0 8px">This game has earned
             <b>Tier ${T.earned}</b>. You may run it at any tier up to that badge —
             lower tiers switch validated rule systems OFF and hand them to you,
             the umpire. Changing tier starts a NEW game.</div>`;
    T.choices.forEach(c => {
      const active = c === T.active, armed = tierArm === c;
      h += `<div class="tierrow" data-t="${c}" style="padding:6px 8px; margin:3px 0;
              border-radius:6px; cursor:${active ? 'default' : 'pointer'};
              border:1px solid ${active ? '#3a6ea5' : armed ? '#e0a34e' : '#3a3f47'};
              background:${active ? '#2b3f55' : '#2c2f36'}">
              ${T.labels[c] || ('Tier ' + c)}
              ${active ? ' <span style="color:#9fc27f">— ACTIVE</span>'
                       : armed ? ' <span style="color:#e0a34e">— click again to restart at this tier</span>' : ''}
            </div>`;
    });
    P.innerHTML = h;
    P.querySelectorAll('.tierrow').forEach(el => el.onclick = async () => {
      const c = +el.dataset.t;
      if (c === PH.game().tier.active) return;
      if (tierArm !== c) { tierArm = c; renderTierPanel(); return; }
      tierArm = null;
      const r = await (await fetch('/api/reset', {method: 'POST',
        body: JSON.stringify({tier: c})})).json();
      if (r.error) { (PH.toast || alert)(r.error); return; }
      // "/" reroutes to the client the new tier plays in (tactical <-> board);
      // the serverless demo installs its own hook (reload + session tier)
      if (window.DEMO_TIER_HOOK) window.DEMO_TIER_HOOK(r);
      else location.href = '/';
    });
  }
  // ---------- rules panel (from the scenario's declared rules_scope) ----------
  function renderRules() {
    const P = $id('rulespanel');
    if (!P || P.style.display !== 'block') return;
    const G = PH.game(), FLOW = PH.flow();
    const rs = FLOW && FLOW.rules_scope;
    const T = G && G.tier;
    let h = `<b>Rules enforced by the engine</b>`;
    if (T) h += `<div style="margin:4px 0 2px; color:#8fb8d8">${T.labels[T.active]}
                 ${T.earned > T.active ? ` <span class="dim">(earned: Tier ${T.earned} —
                 switch with the Tier button)</span>` : ''}</div>`;
    if (!rs) {
      h += (T && T.earned > 0)
        ? `<div class="dim" style="margin-top:6px">You selected Tier 0 — free play by
           choice. NOTHING is enforced: move any piece anywhere, including the printed
           tracks, exactly as in VASSAL. You are the umpire. The validated Tier
           ${T.earned} gate is available from the Tier button (starts a new game).</div>`
        : `<div class="dim" style="margin-top:6px">Tier 0 — free play. No rules are
           enforced for this game yet; move pieces as you would at a physical table.
           You are the umpire.</div>`;
    } else {
      h += `<div class="dim" style="margin:4px 0 8px">${FLOW.scenario || G.name}.
            Every proposed action passes through the legality gate and is accepted or
            rejected against these rules. Numbers in parentheses cite the game's own
            rulebook sections.</div>`;
      h += `<div style="color:#9fc27f;font-weight:600">Enforced</div><ul>`;
      (rs.enforced || []).forEach(r => h += `<li>${r}</li>`);
      h += `</ul>`;
      if (rs.not_enforced && rs.not_enforced.length) {
        h += `<div style="color:#e0a34e;font-weight:600">Not yet enforced — umpire these yourself</div><ul>`;
        rs.not_enforced.forEach(r => h += `<li>${r}</li>`);
        h += `</ul>`;
      }
      if (rs.rulings && rs.rulings.length) {
        h += `<div style="color:#8fb8d8;font-weight:600">Engine rulings & scope notes</div><ul>`;
        rs.rulings.forEach(r => h += `<li>${r}</li>`);
        h += `</ul>`;
      }
    }
    // ---- basic client functions (engine-level; adapts to gate/tier/features)
    const gated = !!FLOW, hasArr = gated && !!FLOW.arrivals,
          hasCbt = gated && !!FLOW.combat;
    h += `<div style="color:#d8c98f;font-weight:600;margin-top:8px">Using this client</div><ul>`;
    h += `<li><b>Sides</b> — pick who you're playing with the buttons top-left; switch
          any time for hot-seat play.</li>`;
    h += `<li><b>Counters</b> — hover for a unit's stats card; click to select (the card
          pins bottom-left). Clicking a stack offers each unit or the whole stack.</li>`;
    h += gated
      ? `<li><b>Moving</b> — drag the selected counter. Green hexes are the legal
         destinations the gate computed (numbers = movement points spent); anything
         else snaps back. Illegal proposals are rejected with the rule citation.</li>`
      : `<li><b>Moving</b> — drag the selected counter anywhere on the board, printed
         tracks included, exactly as in VASSAL. Nothing is checked in free play.</li>`;
    h += `<li><b>Pass</b> — marks the selected unit done without moving.</li>`;
    if (G.facing)
      h += `<li><b>Facing</b> — right-click a counter to rotate it.</li>`;
    if (hasArr)
      h += `<li><b>Arrivals & sea panel</b> (top-left) — supply rolls and landings,
            reinforcement placement, embark/debark, replacements: every button submits
            through the gate.</li>`;
    if (hasCbt)
      h += `<li><b>Combat panel</b> (top-right, combat phase) — click your units and
            enemy units to build a battle, watch the live odds preview, then resolve:
            the engine rolls its own seeded die on the validated CRT and walks you
            through retreats, exchanges and advances.</li>`;
    (PH.clientItems ? PH.clientItems(gated) : []).forEach(li => h += li);
    if (gated)
      h += `<li><b>End player turn</b> — asks the gate to close your turn; it refuses
            (with citations) while obligations are open.</li>`;
    if (T && T.choices.length > 1)
      h += `<li><b>Tier</b> — run the game at any enforcement level up to its earned
            badge, from Tier 0 free play to the full gate. Changing tier starts a new
            game.</li>`;
    h += `<li><b>Reset game</b> — restarts the scenario from its setup.</li>`;
    h += `<li><b>VASSAL interop</b> — the live save (live\\game_*.vsav) is a real
          VASSAL save you can open in the desktop app at any time.</li>`;
    h += `</ul>`;
    const CR = G && G.credits;
    if (CR) {
      h += `<div style="color:#8fb8d8;font-weight:600;margin-top:8px">Credits</div><ul>`;
      if (CR.game) {
        const gm = CR.game;
        h += `<li><b>${gm.title}</b> — ${gm.publisher}, ${gm.year}.<br>
              ${gm.design}${gm.development ? '; ' + gm.development : ''}${gm.art ? '; ' + gm.art : ''}
              <span class="dim">(${gm.source})</span></li>`;
      }
      if (CR.module) {
        const md = CR.module;
        h += `<li><b>${md.title}</b> — ${md.implementation}.<br>
              With: ${md.contributors}.<br>
              <span class="dim">${md.library} (${md.source})</span></li>`;
      }
      if (CR.note) h += `<li class="dim">${CR.note}</li>`;
      h += `</ul>`;
    }
    const SD = G && G.source_defects;
    if (SD && SD.list && SD.list.length) {
      h += `<div style="color:#c99ae0;font-weight:600">Defects found in the printed game — and how the engine resolves them</div>
            <div class="dim" style="margin:4px 0 6px">Encoding a game is a formal check of its own
            rulebook. These are defects of the ORIGINAL published game (editing errors,
            contradictions, undefined cases), each with the resolution this engine enforces and
            the authority for that resolution.</div><ul>`;
      SD.list.forEach(d => {
        h += `<li><b>${d.defect}</b> <span class="dim">[${d.kind}; rules ${d.rules.join(', ')}]</span><br>
              <span style="color:#9fc27f">Resolved:</span> ${d.resolution}<br>
              <span class="dim">Authority: ${d.authority}</span></li>`;
      });
      h += `</ul>`;
    }
    // official rules the PUBLISHER hosts publicly (links, nothing rehosted)
    const RD = G && G.rules_docs;
    if (RD) {
      const links = Object.entries(RD).filter(([k, v]) =>
        typeof v === 'string' && v.startsWith('http'));
      if (links.length) {
        h += `<div style="color:#d8c98f;font-weight:600;margin-top:8px">Official
              rules — free from the publisher</div><ul>`;
        links.forEach(([k, v]) => {
          h += `<li><a href="${v}" target="_blank" rel="noopener"
                 style="color:#9cc4ee">${k.replace(/_/g, ' ')}</a></li>`;
        });
        h += `</ul>`;
      }
    }
    // original docs packed inside the USER'S OWN module (BYO builds only):
    // shown from their file, read locally, never shipped by us
    const DOCS = (window.BYO_MANIFEST && window.BYO && BYO.extract)
      ? (window.BYO_MANIFEST.docs || []) : [];
    if (DOCS.length) {
      h += `<div style="color:#d8c98f;font-weight:600;margin-top:8px">Rulebook &
            charts — from your module</div>
            <div class="dim" style="margin:4px 0 6px">These open the original
            documents packed inside YOUR module file, read locally in your
            browser — this site does not ship them.</div>`;
      DOCS.forEach((d, i) => {
        h += `<button class="sidebtn" data-doc="${i}"
               style="margin:2px 6px 2px 0">${d.label}</button>`;
      });
    }
    h += `<div class="dim" style="margin-top:10px">Rules here are restated in our
          own words for engine enforcement — game mechanics are not copyrightable,
          but the game's printed text and art are, and remain the publisher's.
          Support the original game.</div>`;
    P.innerHTML = h;
    P.querySelectorAll('[data-doc]').forEach(btn => btn.onclick = async () => {
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
    });
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
            (Tier 0/1, or none applicable).</div>`;
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
  // tier, victory text carried as data in game.json "guide") plus any
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
       <p>Free play — the engine enforces nothing at this tier. Move any piece
       anywhere, exactly as at a physical table or in VASSAL; you are the
       umpire. The validated rules gate is available from the Tier button.</p>`,
  };
  function guideSections() {
    const G = PH.game(), FLOW = PH.flow();
    const gd = (G && G.guide) || {};
    const tierOn = G && G.tier && G.tier.active > 0;
    const mode = !FLOW ? 'free'
      : FLOW.mode === 'napoleonic' ? 'napoleonic'
      : FLOW.segment !== undefined ? 'tactical' : 'strategic';
    const S = [];
    S.push(['This game',
      `<h2>${G.name}</h2>
       <p>Sides: ${G.sides.map((s) => s.label).join(' vs ')}. Pick yours top-left;
       switch any time for hot-seat play${tierOn ? ' — every action still goes' +
       ' through the same rules gate' : ''}.</p>
       ${G.tier ? `<p>${G.tier.labels[G.tier.active]}${G.tier.choices.length > 1
          ? ' — other tiers are on the Tier button.' : '.'}</p>` : ''}`]);
    S.push(['How a turn works', TURN_GUIDE[tierOn ? mode : 'free']]);
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
       ${G.tier && G.tier.active >= 3 ? `<li>The <b>AI</b> plays any side you
       don't — stepped (press SPACE per action) or auto, at slow/medium/fast
       pace. It proposes through the same gate you play through.</li>` : ''}
       <li><b>Reset game</b> restarts the scenario; the <b>Tier</b> button
       replays it at a different enforcement level.</li></ul>`]);
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
    ensurePanel('tierpanel',
      `display:none; position:fixed; top:52px; right:8px; width:360px;
       max-width:44vw; background:#23262c; border:1px solid #3a3f47;
       border-radius:10px; padding:12px 14px; z-index:60; font-size:13px;
       box-shadow:0 6px 24px rgba(0,0,0,.5)`);
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
      renderTierBtn();
    };
    const tb = $id('tierbtn');
    if (tb) tb.onclick = () => {
      const opened = soloPanel('tierpanel');
      tierArm = null;
      if (opened) renderTierPanel();
      renderTierBtn();
    };
    const rb = $id('rulesbtn');
    if (rb) rb.onclick = () => {
      if (soloPanel('rulespanel')) renderRules();
      renderTierBtn();
    };
    const tab = $id('tablesbtn');
    if (tab) tab.onclick = () => {
      if (soloPanel('tablespanel')) renderTables();
      renderTierBtn();
    };
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
           show, setGuide, setGuideSuffix, soleNext,
           initPanels, soloPanel, renderTierBtn, renderRules, renderTables };
})();
