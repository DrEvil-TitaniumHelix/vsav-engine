"""
gate.py - Shared scaffold for every legality gate.

A gate (TacticalGame, StrategicGame, BlueGrayGame, WestwallGame) is the ONLY
door into a game's state: propose() returns a verdict with rulebook-cited
reasons; submit() applies legal actions and LOGS EVERY PROPOSAL — including
rejected ones — to an append-only JSONL game log. The log is self-contained
(initial setup + seed + every action) and engine/verify_game.py replays it
independently, re-checking every verdict, every die roll and every state
hash. The AI cannot cheat because the AI never adjudicates: it proposes,
the gate disposes.

This base class owns the parts of that contract that must never drift
between games:

  paths     one state file + one log file per game, keyed by the game dir
  audit     _log() stamps every entry with a sequence number and the
            post-entry state hash
  hashing   state_hash() = sha256 over the class's HASH_KEYS slice of the
            state, JSON-canonicalized — the replay fingerprint
  dice      _rng()/roll_die(): engine-owned, seeded, counted, replayable
            (spec #11); `seed` + `rng_calls` reproduce every die ever rolled
  verdicts  _v(ok, *reasons) — the {"legal", "reasons"} shape every
            proposal answer uses
  tiers     _resolve_tier() (spec #13) for the strategic gates
  resume    _resume_or_new(): reload the saved state file unless its schema
            is stale or it was played at another tier

Subclasses own everything rule-shaped: new_game() state layout,
propose()/submit()/_apply(), and their HASH_KEYS tuple.

HASH_KEYS is part of each game's on-disk log contract: previously recorded
games verify by reproducing these hashes. NEVER add, remove or rename
entries for a shipped game — that would orphan every existing log.
"""
import hashlib
import json
import os
import random


class GateGame:
    # The state keys covered by state_hash(). Frozen per game (see above).
    HASH_KEYS = ()
    # Fallback noun for turns past the scenario's turn_labels list
    # ("turn 4" vs "GT 4" — cosmetic only, never hashed).
    TURN_NOUN = "turn"

    def __init__(self, game, scenario_path, live_dir):
        self.game = game                      # gamespec.Game
        self.scenario = json.load(open(scenario_path, encoding="utf-8"))
        gkey = os.path.basename(os.path.normpath(game.dir))
        self.state_path = os.path.join(live_dir, f"game_{gkey}.state.json")
        self.log_path = os.path.join(live_dir, f"game_{gkey}.log.jsonl")
        cfg = self.scenario["game"]
        self.turns = int(cfg["turns"])
        self.first_player = cfg["first_player"]
        self.turn_labels = cfg.get("turn_labels", [])

    # ------------------------------------------------------------ lifecycle
    def _resolve_tier(self, tier):
        """Tier selection (spec #13): a game may be RUN below the tier it
        has EARNED. Tier 1 = movement/arrivals gate only — the entire combat
        ruleset (and everything keyed on it) is switched off. Tier 2 = the
        full validated combat gate. Tier 3 = tier 2 plus a validated policy
        AI (declared in game.json `policy_ai`); the tier-3 gate is identical
        to tier 2 — the AI is an opponent offered on top, and it submits
        through the same door. Tier 0 never reaches a gate class (no gate at
        all — the server serves free play)."""
        self.combat = self.game.spec.get("combat")
        self.tier_earned = (
            (3 if self.game.spec.get("policy_ai") else 2) if self.combat else 1)
        self.tier = self.tier_earned if tier is None \
            else max(1, min(int(tier), self.tier_earned))
        if self.tier < 2:
            self.combat = None

    def _resume_or_new(self, seed, required=()):
        """Reload the saved state file if it is structurally current,
        otherwise start a fresh game. `required` lists state keys whose
        absence marks an older schema; a tiered gate also resets when the
        saved state was played at a different tier."""
        if not os.path.exists(self.state_path):
            self.new_game(seed)
            return
        self.s = json.load(open(self.state_path, encoding="utf-8"))
        if any(k not in self.s for k in required):
            self.new_game(seed)               # older-schema state file: reset
        elif hasattr(self, "tier") \
                and self.s.get("tier", self.tier_earned) != self.tier:
            self.new_game(seed)               # state was played at another tier

    @staticmethod
    def _fresh_seed(seed):
        """The caller's seed, or a fresh unpredictable one."""
        return seed if seed is not None \
            else random.SystemRandom().randrange(10 ** 9)

    def _scenario_units(self):
        """Starting units from the scenario: pid -> unit dict (identity +
        position; subclasses add game-specific fields where needed)."""
        return {u["id"]: {"pid": u["id"], "slot": u["slot"], "side": u["side"],
                          "col": u["hex"][0], "row": u["hex"][1]}
                for u in self.scenario["units"]}

    def _units_for_log(self, units):
        """The init entry's unit record — everything a replay needs to
        confirm the starting position."""
        return [dict(pid=u["pid"], slot=u["slot"], side=u["side"],
                     hex=[u["col"], u["row"]])
                for u in units.values()]

    def _reset_log(self):
        """A new game starts a new log; stale logs never mix sessions."""
        if os.path.exists(self.log_path):
            os.remove(self.log_path)

    def save(self):
        json.dump(self.s, open(self.state_path, "w", encoding="utf-8"), indent=1)

    # ------------------------------------------------------------ audit log
    def _log(self, entry):
        entry["n"] = self.s["n"]
        self.s["n"] += 1
        entry["state_hash"] = self.state_hash()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def state_hash(self):
        """Replay fingerprint: sha256 over the HASH_KEYS slice of the state,
        canonicalized with sorted keys. verify_game.py recomputes this after
        every replayed entry — any divergence exposes an unlogged mutation."""
        core = {k: self.s[k] for k in self.HASH_KEYS}
        blob = json.dumps(core, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ------------------------------------------------------------ dice
    def _rng(self):
        """The seeded stream, advanced past every die already rolled."""
        r = random.Random(self.s["seed"])
        for _ in range(self.s["rng_calls"]):
            r.random()
        return r

    def roll_die(self):
        """Engine-owned d6: seeded, counted, replayable (spec #11)."""
        r = self._rng()
        v = 1 + int(r.random() * 6)
        self.s["rng_calls"] += 1
        return v

    # ------------------------------------------------------------ queries
    def unit(self, pid):
        return self.s["units"][str(pid)]

    def turn_label(self, t=None):
        t = self.s["turn"] if t is None else t
        return self.turn_labels[t - 1] if 0 < t <= len(self.turn_labels) \
            else f"{self.TURN_NOUN} {t}"

    def on_map(self, u):
        """Whether a unit is on the playing map. Default: always (gates with
        off-board states — at sea, exited — override)."""
        return True

    def rules_scope(self):
        """The scenario's declared scope, composed for the ACTIVE tier
        (requires _resolve_tier). Scenarios split their enforced list into
        `enforced` (tier-1 systems) + `enforced_tier2` (combat systems); at
        tier 1 the tier-2 items are presented honestly as not enforced."""
        sc = self.scenario.get("rules_scope", {})
        if self.tier >= 2:
            return {"enforced": sc.get("enforced", []) + sc.get("enforced_tier2", []),
                    "not_enforced": sc.get("umpired", [])}
        return {"enforced": sc.get("enforced", []),
                "not_enforced": sc.get("enforced_tier2", []) + sc.get("umpired", []),
                "banner": f"TIER {self.tier} MODE selected - combat is umpired"}

    # ------------------------------------------------------------ verdicts
    def _v(self, ok, *reasons):
        return {"legal": bool(ok), "reasons": list(reasons)}
