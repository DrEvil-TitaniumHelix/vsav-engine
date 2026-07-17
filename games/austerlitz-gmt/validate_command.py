"""
validate_command.py - phase-3 command-system validation.

Checks the transcribed command tables cell-by-cell against the chart
[charts p1], then exercises the whole Family-A turn structure through the
REAL gate: pool declaration [A15.1], initiative [4.4], LIM draws
[3.0.B.2], activation rolls + Command Breakdown [4.5.1/4.7] including the
ENEMY opportunity, full/limited budgets [4.6], the limited-activation
adjacency ban (designer Q&A), In/Out of Command [4.3.3], artillery
attachment (A15.1 special rule), division breakpoint LIM effects
[11.2.1], fatigue accumulation/recovery/thresholds [13.1-13.3 + errata],
and finally replays a full scripted game independently via verify_game.

Run: python games/austerlitz-gmt/validate_command.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import command as cmd_mod
import gamespec
import verify_game
from napoleonic import NapoleonicGame

FAILS = []


def check(label, ok):
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILS.append(label)


def fresh(seed):
    live = tempfile.mkdtemp(prefix="aus_cmd_")
    # tier=1 pins the phase-3 command flow (schema 3): this file is the
    # mechanics harness for that flow; phase-4 melee/reactions have
    # their own validator (validate_shock.py)
    g = NapoleonicGame(gamespec.load(HERE),
                       os.path.join(HERE, "scenario_northern_flank.json"),
                       live, seed=seed, tier=1)
    return g, live


def by_slot(g, slot, side=None):
    for u in g.s["units"].values():
        if u["slot"] == slot and (side is None or u["side"] == side):
            return u
    raise KeyError(slot)


GAME = gamespec.load(HERE)
CMD = GAME.spec["command"]

print("== table transcription [charts p1] ==")
bd = cmd_mod.breakdown
check("breakdown die 0: A=stop N=retreat C=enemy [4.7]",
      (bd(CMD, "A", 0), bd(CMD, "N", 0), bd(CMD, "C", 0))
      == ("stop", "retreat", "enemy"))
check("breakdown die 4: A=full N=limited C=stop [4.7]",
      (bd(CMD, "A", 4), bd(CMD, "N", 4), bd(CMD, "C", 4))
      == ("full", "limited", "stop"))
check("breakdown die 7: A=charge N=full C=limited [4.7]",
      (bd(CMD, "A", 7), bd(CMD, "N", 7), bd(CMD, "C", 7))
      == ("charge", "full", "limited"))
check("breakdown die 9: A=reactivate N=full C=full [4.7]",
      (bd(CMD, "A", 9), bd(CMD, "N", 9), bd(CMD, "C", 9))
      == ("reactivate", "full", "full"))
check("ENEMY twice in a row = STOP [4.7]",
      bd(CMD, "C", 0, prior="enemy") == "stop")
check("REACTIVATE twice in a row = FULL [4.7]",
      bd(CMD, "A", 9, prior="reactivate") == "full")
ia = cmd_mod.independent_allowance
check("independent table French: 0->2, 5->3, 8->4, 9->5 [A4.3.2]",
      (ia(CMD, "french", 0), ia(CMD, "french", 5), ia(CMD, "french", 8),
       ia(CMD, "french", 9)) == (2, 3, 4, 5))
check("independent table Allied: 4->0, 5->1 [A4.3.2]",
      (ia(CMD, "allied", 4), ia(CMD, "allied", 5)) == (0, 1))
cc = cmd_mod.command_change
check("command change French 0 = corps or 3 div LIMs [4.2]",
      cc(CMD, "french", 0) == "corps1_or_div3")
check("command change Allied 0 = corps or 2 div LIMs [4.2]",
      cc(CMD, "allied", 0) == "corps1_or_div2")
check("command change French 4 = 1 division LIM, 5 = none [4.2]",
      (cc(CMD, "french", 4), cc(CMD, "french", 5)) == ("div1", "none"))
check("Buxhowden adds one: Allied 3 rolls off div1 onto none [4.2 note]",
      (cc(CMD, "allied", 3), cc(CMD, "allied", 3, buxhowden=True))
      == ("div1", "none"))
check("command ranges: Napoleon 12 / Tsar 10 / Buxhowden 8; corps 8-6; "
      "division 5-4 [A4.2]",
      CMD["command_ranges"]["overall"] == {"Napoleon": 12,
                                           "Tsar Alexander": 10,
                                           "Buxhowden": 8}
      and CMD["command_ranges"]["corps"] == {"French": 8, "Allied": 6}
      and CMD["command_ranges"]["division"] == {"French": 5, "Allied": 4})
fte = cmd_mod.fatigue_threshold_effects
check("fatigue 7 = one-time morale level; 8 = disorder; 9 = both; no "
      "repeats [13.3 + errata]",
      fte(7, set()) == (["morale_level"], [7])
      and fte(8, {7}) == (["disorder"], [8])
      and fte(9, {7, 8}) == (["morale_level", "disorder"], [9])
      and fte(7, {7}) == ([], []))

print("== pool placement + initiative [3.0.A/4.4/A15.1] ==")
g, live = fresh(11)
check("schema 3 command flow is on", g.s["schema"] == 3
      and g.s["phase"] == "command")
r = g.propose("French", {"type": "move", "unit": "x", "dest": [1, 1]})
check("no unit actions during Pool Placement [3.0.A]", not r["legal"])
r = g.propose("Allied", {"type": "set_pool", "lims": ["Markov"]})
check("pool declaration order enforced", not r["legal"])
r = g.propose("French", {"type": "set_pool", "lims": ["Markov"]})
check("cannot declare the enemy's LIM", not r["legal"])
r = g.submit("French", {"type": "set_pool",
                        "lims": ["Suchet", "Independent"]})
check("French declaration accepted [A15.1 voluntary pool]",
      r["verdict"]["legal"])
r = g.submit("Allied", {"type": "set_pool",
                        "lims": ["Markov", "Vorpatzki"]})
ini = r["result"]["initiative"]
check("initiative rolled + logged on pool close [4.4]",
      ini["winner"] in ("French", "Allied") and len(ini["rolls"]) >= 1)
check("all four LIMs in the pool", len(g.s["pool"]) == 4)
check("division LIMs booked for fatigue, Independent not [13.1.1 + Q&A]",
      sorted(g.s["fat_lim"]) == ["Allied:2", "Allied:3v", "French:3"])
winner, loser = ini["winner"], ("French" if ini["winner"] == "Allied"
                                else "Allied")
r = g.propose(loser, {"type": "choose_initiative_lim",
                      "lim": f"{loser}:Markov"})
check("only the initiative winner chooses [4.4]", not r["legal"])
enemy_lim = [ref for ref in g.s["pool"]
             if ref.startswith(loser)][0]
r = g.propose(winner, {"type": "choose_initiative_lim", "lim": enemy_lim})
check("ANY pool LIM may be chosen, the opponent's included [4.4]",
      r["legal"])

print("== activation roll -> breakdown cascade [4.5.1/4.7] ==")
g, live = fresh(11)     # seed 11: Allied wins initiative 5-4
g.submit("French", {"type": "set_pool", "lims": ["Suchet", "Independent"]})
g.submit("Allied", {"type": "set_pool", "lims": ["Markov", "Vorpatzki"]})
g.submit("Allied", {"type": "choose_initiative_lim",
                    "lim": "Allied:Markov"})
r = g.submit("Allied", {"type": "activation_choice", "choice": "full"})
res = r["result"]
check("failed roll (9 vs 4) goes to the Breakdown Table [4.5.1]",
      res["activation_roll"]["die"] == 9
      and res["activation_roll"]["vs"] == 4 and "breakdown" in res)
check("Cautious column die 4 = STOP, commander finished [4.7]",
      res["breakdown"]["column"] == "C"
      and res["breakdown"]["result"] == "stop")
check("engine immediately draws the next LIM [3.0.B.2]",
      "drawn" in res and res["drawn"]["lim"] == "French:Independent")
check("Independent LIM rolls its table: die 5 -> 3 leaders [A4.3.2]",
      res["independent"]["die"] == 5 and res["independent"]["allowed"] == 3
      and sorted(res["independent"]["eligible"])
      == ["French:M", "French:T"])

print("== limited activation: budgets + adjacency ban [4.6.2 + Q&A] ==")
r = g.submit("French", {"type": "activation_choice", "choice": "limited",
                        "division": "French:M"})
act = g.s["act"]
check("limited is automatic, no roll [4.5.1]",
      "activation_roll" not in r["result"] and act["atype"] == "limited")
mil = by_slot(g, "22 CaC")
check("limited budget = half MA rounded down (12 -> 6) [4.6.2.a]",
      act["budget"][mil["pid"]] == 6.0)
check("Milhaud may not command artillery [A15.1 special rule]",
      not any(g.unit(p)["arm"].startswith("artillery")
              for p in act["incommand"]))
reach_full = g.reachable(mil["pid"], budget=12.0)
reach_lim = g.reachable(mil["pid"], budget=6.0, avoid_adjacent=True)
foes = [(v["col"], v["row"]) for v in g.s["units"].values()
        if v["side"] == "Allied" and v["arm"] != "leader"]
adj = set()
for f in foes:
    adj.add(f)
    for nb in GAME.neighbors(*f):
        adj.add(tuple(nb))
check("limited reachability never enters a hex adjacent to the enemy "
      "[4.6.2 + designer Q&A: any hexside]",
      reach_lim and not any((c, r_) in adj for (c, r_, _) in reach_lim))
check("full reachability does reach enemy-adjacent hexes (control)",
      any((c, r_) in adj for (c, r_, _) in reach_full))
g.submit("French", {"type": "end_activation"})
r = g.submit("French", {"type": "activation_choice", "choice": "full",
                        "division": "French:T"})
check("Treilhard full activation succeeds (die 1 vs 5) [4.5.1]",
      r["result"]["activation_roll"]["die"] == 1
      and g.s["act"]["atype"] == "full")
tre = by_slot(g, "10 Hus")
check("full budget = full MA [4.6.1]",
      g.s["act"]["budget"][tre["pid"]] == 12.0)
r = g.submit("French", {"type": "move", "unit": tre["pid"],
                        "dest": [63, 3], "facing": 3})
check("in-command move inside the activation is legal", r["verdict"]["legal"])
r = g.propose("French", {"type": "move", "unit": tre["pid"],
                         "dest": [64, 3]})
check("one move per unit per activation [4.6.1]", not r["legal"])
suchet_inf = by_slot(g, "2/17 Leg")
r = g.propose("French", {"type": "move", "unit": suchet_inf["pid"],
                         "dest": [63, 9]})
check("units of another division may not act [4.3.3]", not r["legal"])

print("== once per turn + non-LIM eligibility [3.0.C/4.6] ==")
g.submit("French", {"type": "end_activation"})
while g.s["phase"] == "activation":        # play out remaining draws
    act = g.s["act"]
    if act["pending"] == "choice":
        kw = {"type": "activation_choice", "choice": "limited"}
        if act["kind"] == "independent":
            kw["division"] = [d for d in act["indep"]["eligible"]
                              if d not in act["indep"]["done"]][0]
        g.submit(act["side"], kw)
    elif act["pending"] == "bd_offer":
        g.submit(act["side"], {"type": "bd_decline"})
    else:
        g.submit(act["side"], {"type": "end_activation"})
if g.s["phase"] == "non_lim":
    o_f = g._nonlim_options("French")
    check("divisions that activated or committed LIMs are not non-LIM "
          "eligible [3.0.C.1]", o_f["divisions"] == [])
else:
    check("non-LIM auto-skipped: no eligible picks on either side "
          "[3.0.C]", g.s["phase"] == "command" and g.s["turn"] == 2)

print("== fatigue segment [13.1/13.2] ==")
g2, live2 = fresh(11)
g2.submit("French", {"type": "set_pool",
                     "lims": ["Suchet", "Independent"]})
g2.submit("Allied", {"type": "set_pool", "lims": ["Markov", "Vorpatzki"]})
g2.submit("Allied", {"type": "choose_initiative_lim",
                     "lim": "Allied:Markov"})
g2.submit("Allied", {"type": "activation_choice", "choice": "full"})
while g2.s["phase"] == "activation":
    act = g2.s["act"]
    if act["pending"] == "choice":
        kw = {"type": "activation_choice", "choice": "limited"}
        if act["kind"] == "independent":
            kw["division"] = [d for d in act["indep"]["eligible"]
                              if d not in act["indep"]["done"]][0]
        g2.submit(act["side"], kw)
    elif act["pending"] == "bd_offer":
        g2.submit(act["side"], {"type": "bd_decline"})
    else:
        g2.submit(act["side"], {"type": "end_activation"})
while g2.s["phase"] == "non_lim":
    g2.submit(g2.s["mover"], {"type": "pass_non_lim"})
check("turn 1 -> 2 with +1 fatigue for every committed command "
      "[13.1.1 + Q&A: even a STOP fatigues]",
      g2.s["turn"] == 2 and
      all(g2.s["fatigue"][dk] == 1 for dk in
          ("French:3", "French:M", "French:T", "Allied:2", "Allied:3v")))
g2.submit("French", {"type": "set_pool", "lims": []})
g2.submit("Allied", {"type": "set_pool", "lims": []})
while g2.s["phase"] == "non_lim":
    g2.submit(g2.s["mover"], {"type": "pass_non_lim"})
check("idle turn 3+ hexes from the enemy recovers one level [13.2]",
      g2.s["turn"] == 3 and
      all(g2.s["fatigue"][dk] == 0 for dk in g2.s["fatigue"]))

print("== fatigue threshold 7: one-time morale loss [13.3 + errata] ==")
g3, live3 = fresh(11)
g3.s["fatigue"]["Allied:2"] = 6
g3.submit("French", {"type": "set_pool", "lims": []})
g3.submit("Allied", {"type": "set_pool", "lims": ["Markov"]})
g3.submit("Allied", {"type": "choose_initiative_lim",
                     "lim": "Allied:Markov"})
g3.submit("Allied", {"type": "end_activation"})    # decline the attempt
while g3.s["phase"] == "non_lim":
    g3.submit(g3.s["mover"], {"type": "pass_non_lim"})
inf = by_slot(g3, "3/Arkh")
check("declined attempt still fatigues (LIM committed) -> level 7 "
      "[designer Q&A]", g3.s["fatigue"]["Allied:2"] == 7)
check("reaching 7: every unit of the division lost one morale level "
      "[13.3 errata]", inf["morale_state"] == "shaken"
      and 7 in g3.s["fat_crossed"]["Allied:2"])

print("== breakpoint: LIM ban + no full activation [11.2.1] ==")
g4, live4 = fresh(11)
for slot in ("13 CaC", "21 CaC", "10 Hus"):     # Treilhard bp level 3
    u = by_slot(g4, slot)
    u["sp_lost"] = u["sp"] - 1
    u["sp"] = 1                                 # cumulative loss > half
check("three cavalry at Unit Breakpoint = T/CR at Division Breakpoint "
      "[11.1/11.2 - Command Card level 3]",
      g4._at_div_breakpoint("French:T"))
check("Independent LIM itself stays available (per-division exclusion "
      "happens at the draw [A4.3.2])",
      "Independent" in g4._available_lims("French"))
g4.submit("French", {"type": "set_pool", "lims": ["Independent"]})
g4.submit("Allied", {"type": "set_pool", "lims": []})
if g4.s["phase"] == "initiative":
    g4.submit(g4.s["initiative"], {"type": "choose_initiative_lim",
                                   "lim": "French:Independent"})
elig = g4.s["act"]["indep"]["eligible"]
check("breakpoint division may not activate under the Independent LIM "
      "[11.2.1]", "French:T" not in elig and "French:M" in elig)
r = g4.propose("French", {"type": "activation_choice", "choice": "full",
                          "division": "French:T"})
check("gate rejects the breakpoint division outright", not r["legal"])

print("== ENEMY breakdown opportunity [4.7] ==")
seed_found = None
for seed in range(1, 400):
    g5, live5 = fresh(seed)
    g5.submit("French", {"type": "set_pool", "lims": []})
    g5.submit("Allied", {"type": "set_pool", "lims": ["Markov"]})
    if g5.s["initiative"] != "Allied":
        continue
    g5.submit("Allied", {"type": "choose_initiative_lim",
                         "lim": "Allied:Markov"})
    r = g5.submit("Allied", {"type": "activation_choice", "choice": "full"})
    bdres = r["result"].get("breakdown")
    if bdres and bdres["result"] == "enemy":
        seed_found = seed
        break
check(f"found an ENEMY result via seeded dice (seed {seed_found})",
      seed_found is not None)
if seed_found:
    offer = r["result"]["breakdown_offer"]
    check("the FRENCH player is offered his closest division [4.7]",
          offer["side"] == "French" and g5.s["mover"] == "French"
          and g5.s["act"]["pending"] == "bd_offer")
    # Markov stands at (68,12); Suchet (60,13) d=8, Milhaud (62,6) d=?,
    # Treilhard (62,3): the engine computed the argmin set - verify vs
    # brute force
    dists = {}
    for dk in ("French:3", "French:M", "French:T"):
        ldr = g5._leader_of(dk)
        mk = by_slot(g5, "Markov")
        dists[dk] = g5._dist((ldr["col"], ldr["row"]),
                             (mk["col"], mk["row"]))
    best = min(dists.values())
    argmin = sorted(k for k, v in dists.items() if v == best)
    check("closest-division set matches brute-force leader distances "
          "[4.7]", sorted(offer["closest"]) == argmin)
    wrong = [dk for dk in ("French:3", "French:M", "French:T")
             if dk not in offer["closest"]]
    if wrong:
        r = g5.propose("French", {"type": "bd_activate",
                                  "division": wrong[0]})
        check("a farther division is rejected [4.7]", not r["legal"])
    g5.submit("French", {"type": "bd_activate",
                         "division": offer["closest"][0]})
    r = g5.submit("French", {"type": "activation_choice",
                             "choice": "limited"})
    check("opportunity division opens a normal activation [4.7]",
          g5.s["act"]["atype"] == "limited"
          and g5.s["act"]["kind"] == "breakdown")
    g5.submit("French", {"type": "end_activation"})
    while g5.s["phase"] == "activation":
        act = g5.s["act"]
        if act["pending"] == "choice":
            g5.submit(act["side"], {"type": "end_activation"})
        elif act["pending"] == "bd_offer":
            g5.submit(act["side"], {"type": "bd_decline"})
        else:
            g5.submit(act["side"], {"type": "end_activation"})
    while g5.s["phase"] == "non_lim":
        g5.submit(g5.s["mover"], {"type": "pass_non_lim"})
    check("free activation adds no fatigue to the opportunity division "
          "[designer Q&A]",
          all(g5.s["fatigue"][dk] == 0 for dk in
              ("French:3", "French:M", "French:T")))

print("== artillery attachment [A15.1 special rule] ==")
g6, live6 = fresh(11)
g6.submit("French", {"type": "set_pool", "lims": ["Suchet"]})
g6.submit("Allied", {"type": "set_pool", "lims": ["Vorpatzki"]})
# move a/B next to Vorpatzki so it is in his range
ab = by_slot(g6, "a/B")
vor = by_slot(g6, "Vorpatzki")
ab["col"], ab["row"] = vor["col"], vor["row"] + 1
ref = f"{g6.s['initiative']}:" + \
    ("Suchet" if g6.s["initiative"] == "French" else "Vorpatzki")
g6.submit(g6.s["initiative"], {"type": "choose_initiative_lim",
                               "lim": ref})
g6.submit(g6.s["act"]["side"], {"type": "activation_choice",
                                "choice": "limited"})
act = g6.s["act"]
if act["div"] == "Allied:3v":
    check("a/B attaches to Vorpatzki (his only command) [A15.1 + "
          "AUS-CMD-2]", ab["pid"] in act["incommand"]
          and g6.s["arty_used"].get(ab["pid"]) == "Allied:3v")
else:
    arts = [p for p in act["incommand"]
            if g6.unit(p)["arm"].startswith("artillery")]
    check("V-corps batteries in range attach to Suchet [A15.1: incl. "
          "the 1/V foot battery]", len(arts) >= 1)

print("== full scripted game -> independent replay [spec #9] ==")
g7, live7 = fresh(20260716)
turns_played = 0
while not g7.flow()["over"] and g7.s["turn"] <= 6:
    ph = g7.s["phase"]
    if ph == "command":
        g7.submit(g7.s["mover"], {"type": "set_pool",
                                  "lims": list(g7.scenario["initial_lims"]
                                               [g7.s["mover"]])})
    elif ph == "initiative":
        own = [ref for ref in g7.s["pool"]
               if ref.startswith(g7.s["initiative"])]
        g7.submit(g7.s["initiative"],
                  {"type": "choose_initiative_lim",
                   "lim": own[0] if own else g7.s["pool"][0]})
    elif ph == "activation":
        act = g7.s["act"]
        if act["pending"] == "choice":
            kw = {"type": "activation_choice", "choice": "full"}
            if act["kind"] == "independent":
                kw["division"] = [d for d in act["indep"]["eligible"]
                                  if d not in act["indep"]["done"]][0]
            if act["kind"] != "independent" and \
                    g7._at_div_breakpoint(act["div"] or ""):
                kw["choice"] = "limited"
            g7.submit(act["side"], kw)
        elif act["pending"] == "bd_offer":
            g7.submit(act["side"], {"type": "bd_activate",
                                    "division": act["bd_closest"][0]})
        elif act["stage"] == "move":
            moved_something = False
            for pid in act["incommand"]:
                u = g7.unit(pid)
                if pid in g7.s["moved"] or u["arm"] == "leader" \
                        or u.get("dead") \
                        or u.get("morale_state") == "routed":
                    continue
                lm = g7.legal_moves(pid)
                if lm["can_act"] and lm["dests"]:
                    # push toward the enemy: cheapest closer dest
                    ex = 40 if u["side"] == "Allied" else 75
                    dests = sorted(lm["dests"],
                                   key=lambda d: (abs(d["col"] - ex),
                                                  d["cost"]))
                    d = dests[0]
                    g7.submit(u["side"], {"type": "move", "unit": pid,
                                          "dest": [d["col"], d["row"]],
                                          "facing": d["facing"]})
                    moved_something = True
                    break
            if not moved_something:
                # try a shot before ending
                fired = False
                for pid in act["incommand"]:
                    u = g7.unit(pid)
                    if pid in g7.s["fired"] or u["arm"] == "leader":
                        continue
                    for tgt in g7.s["units"].values():
                        if tgt["side"] == u["side"] \
                                or tgt["arm"] == "leader" \
                                or tgt.get("dead"):
                            continue
                        r = g7.submit(u["side"],
                                      {"type": "fire", "unit": pid,
                                       "target": tgt["pid"]})
                        if r["verdict"]["legal"]:
                            fired = True
                            break
                    if fired:
                        break
                if not fired:
                    g7.submit(act["side"], {"type": "end_activation"})
        else:
            g7.submit(act["side"], {"type": "end_activation"})
        pf = g7.s.get("pending_fire")
        if pf:
            g7.submit(pf["defender_side"], {"type": "return_fire"})
    elif ph == "non_lim":
        o = g7._nonlim_options(g7.s["mover"])
        if o["divisions"]:
            g7.submit(g7.s["mover"], {"type": "non_lim",
                                      "division": o["divisions"][0]})
        elif o["units"]:
            g7.submit(g7.s["mover"], {"type": "non_lim",
                                      "unit": o["units"][0]})
        else:
            g7.submit(g7.s["mover"], {"type": "pass_non_lim"})
    elif ph == "rally":
        did = False
        for u in g7.s["units"].values():
            if u["side"] != g7.s["mover"] or not g7.on_map(u):
                continue
            if u.get("morale_state", "good") == "good" \
                    or u["pid"] in g7.s.get("rallied", []):
                continue
            r = g7.submit(g7.s["mover"], {"type": "rally",
                                          "unit": u["pid"]})
            if r["verdict"]["legal"]:
                did = True
                break
        if not did:
            g7.submit(g7.s["mover"], {"type": "end_rally"})
log = os.path.join(live7, "game_austerlitz-gmt.log.jsonl")
n_lines = sum(1 for _ in open(log, encoding="utf-8"))
check(f"scripted game reached turn {g7.s['turn']} ({n_lines} log entries)",
      g7.s["turn"] >= 4 and n_lines > 60)
ok, msg = verify_game.verify(HERE, log)
check(f"verify_game replay: {msg[:90]}", ok)

print()
if FAILS:
    print(f"{len(FAILS)} FAILURES:")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("validate_command: ALL GREEN")
