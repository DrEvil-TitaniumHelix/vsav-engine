"""
llm_planner.py - The LLM plan-proposer (expert-AI stage 3).

A language model writes ONE operational plan per player turn in the
plans.py DSL; the plan compiler expands it into proposals through the
legality gate. The model has NO authority anywhere in this pipeline:

  - the gate validates every compiled action exactly as it does a human's;
  - the plan is compile-checked (plans.validate_plan) before use, with one
    corrective retry;
  - invalid JSON, an invalid plan, an API failure, a safety decline, or a
    missing API key all fall back to the shipped policy AI for that turn -
    the game ALWAYS completes, fully logged and verifiable.

Games played this way remain byte-exact replayable: the log records gate
actions, not who proposed them. The LLM's orders, commentary, token usage
and fallbacks are written to a sidecar ORDERS LOG (JSONL) so a human can
read the AI's plan for every turn next to the game log it produced.

Transport is injectable for tests: any callable
    transport(system_text, user_text, schema) -> (raw_text, usage_dict)
The default transport calls the Anthropic API (model claude-fable-5,
structured JSON output, prompt-cached system prompt). The `anthropic`
package is imported lazily inside that transport only - the engine stays
stdlib-only for everything CI runs.

Families: bluegray first (stage-3 pilot). Register other families'
briefing builders in BRIEFERS as their plan compilers land in plans.py.
"""
import json
import os
import time

import plans

DEFAULT_MODEL = "claude-fable-5"
DEFAULT_EFFORT = "medium"

# Structured-output schema for a plan. Objects carry additionalProperties
# false throughout (API requirement); optional hex fields are always-present
# strings where "" means absent (stripped after parsing).
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "commentary": {
            "type": "string",
            "description": "2-4 sentences: the operational intent this turn."},
        "orders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "verb": {"type": "string",
                             "enum": ["push", "hold", "standoff", "run_exit"]},
                    "units": {"type": "array", "items": {"type": "string"}},
                    "objective": {
                        "type": "string",
                        "description": "4-digit hex CCRR for push; \"\" otherwise"},
                    "at": {
                        "type": "string",
                        "description": "4-digit hex CCRR for hold; \"\" = hold in place"},
                },
                "required": ["verb", "units", "objective", "at"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["commentary", "orders"],
    "additionalProperties": False,
}


# ------------------------------------------------------------ briefings
def _bg_briefing(tg, side):
    """Compact, factual state briefing for a Blue & Gray game. Open
    information - both orders of battle are public on the map."""
    s = tg.s
    enemy = tg.game.enemy(side)
    out = [f"GAME TURN {s['turn']} of {tg.turns} ({tg.turn_label()})"
           + (" - NIGHT: no combat this turn" if tg.is_night() else ""),
           f"You command: {side}. Phase: {s['phase']}. "
           f"VP so far: " + " ".join(f"{k} {v}" for k, v in sorted(s["vp"].items()))]

    def unit_line(u):
        st = tg.game.stats(u["slot"])
        return (f"  {u['pid']} {u['slot']} ({tg.cls(u)}, str {st[0] or st[1]}, "
                f"MA {st[2]}) at {u['col']:02d}{u['row']:02d}")

    out.append(f"\nYOUR UNITS ({side}):")
    out += [unit_line(u) for u in sorted(tg._live(side), key=lambda x: x["pid"])]
    out.append(f"\nENEMY UNITS ({enemy}):")
    out += [unit_line(u) for u in sorted(tg._live(enemy), key=lambda x: x["pid"])]

    occ_cfg = tg.vp_cfg.get("occupation") or {}
    out.append("\nVP HEXES (hex: points, scoring side, currently credited to):")
    for owner_key, hexes in sorted(occ_cfg.items()):
        for hx, pts in sorted(hexes.items()):
            out.append(f"  {hx}: {pts} VP, scores for {owner_key}, "
                       f"held by {s['occ'].get(hx) or 'nobody'}")
    if tg.exit_hexes:
        rates = tg.vp_cfg.get("exit_per_csp", {})
        out.append("EXIT HEXES: " + " ".join(f"{c:02d}{r:02d}" for c, r in
                                             sorted(tg.exit_hexes))
                   + f" (VP per exited CSP: " +
                   " ".join(f"{k} {v}" for k, v in sorted(rates.items())) + ")")
    due = sorted(pid for pid, d in s["pool"].items()
                 if d <= s["turn"] and tg.reserve[pid]["side"] == side)
    if due:
        out.append("REINFORCEMENTS DUE (enter automatically this turn): "
                   + " ".join(f"{p} {tg.reserve[p]['slot']}" for p in due))
    out.append(
        "\nWrite this turn's plan as JSON. Refer to units by their pid "
        "(e.g. u12). Units you leave unassigned follow standing doctrine "
        "(advance on the nearest objective; artillery stands off; the train "
        "runs for the exit). Combat obligations are handled by the engine - "
        "your plan commands the MOVEMENT.")
    return "\n".join(out)


BRIEFERS = {"bluegray": _bg_briefing}


def build_system(doctrine_text, scenario_name, sides):
    return f"""You are the commanding general of one side in a hex-and-counter \
wargame: {scenario_name}. Each player turn you issue ONE operational plan; a \
deterministic compiler turns it into unit orders, and a rules engine (the \
legality gate) validates every order against the printed rules. You cannot \
break a rule - illegal orders are simply rejected - so spend your effort on \
JUDGMENT: where to concentrate, what to refuse, what the victory schedule pays.

PLAN LANGUAGE (JSON, schema-enforced):
  verb "push":     units advance toward "objective" (4-digit hex CCRR),
                   never voluntarily ending adjacent to enemies they can't
                   fight at 1-1 (combat is mandatory in this game).
  verb "hold":     units stand at / move to "at" (or their current hex if
                   "at" is "").
  verb "standoff": artillery keeps a 2-3 hex bombardment distance.
  verb "run_exit": the unit road-marches for the exit hexes and exits.
Set unused string fields to "". Units not named in any order follow the
standing doctrine automatically.

DOCTRINE (accumulated knowledge - weigh it, don't worship it):
{doctrine_text}

Sides in this game: {' vs '.join(sides)}. Answer with JSON only."""


# ------------------------------------------------------------ transports
def claude_transport(model=DEFAULT_MODEL, effort=DEFAULT_EFFORT,
                     max_tokens=16000):
    """Default transport: Anthropic API, structured JSON output, cached
    system prompt. Lazy import keeps the engine stdlib-only unless used."""
    client_box = []

    def call(system_text, user_text, schema):
        import anthropic
        if not client_box:
            client_box.append(anthropic.Anthropic())
        client = client_box[0]
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system_text,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_text}],
            extra_body={"output_config": {"effort": effort,
                                          "format": {"type": "json_schema",
                                                     "schema": schema}}},
        )
        if getattr(resp, "stop_reason", None) == "refusal":
            raise RuntimeError("model declined the request (stop_reason=refusal)")
        text = "".join(b.text for b in resp.content
                       if getattr(b, "type", "") == "text")
        u = resp.usage
        usage = {"model": model, "in": u.input_tokens, "out": u.output_tokens,
                 "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                 "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}
        return text, usage

    return call


def openai_transport(model="gpt-5.6", max_tokens=16000):
    """OpenAI transport (Responses API, strict json_schema output). Lazy
    import, same contract as claude_transport: the plan schema already meets
    OpenAI strict-mode rules (additionalProperties false, all-required)."""
    client_box = []

    def call(system_text, user_text, schema):
        from openai import OpenAI
        if not client_box:
            client_box.append(OpenAI())
        resp = client_box[0].responses.create(
            model=model,
            max_output_tokens=max_tokens,
            input=[{"role": "system", "content": system_text},
                   {"role": "user", "content": user_text}],
            text={"format": {"type": "json_schema", "name": "turn_plan",
                             "schema": schema, "strict": True}},
        )
        text = resp.output_text
        if not text:
            raise RuntimeError(f"empty output (status={resp.status}) — "
                               "refusal or truncation")
        u = resp.usage
        cached = getattr(getattr(u, "input_tokens_details", None),
                         "cached_tokens", 0) or 0
        usage = {"model": model, "in": u.input_tokens, "out": u.output_tokens,
                 "cache_read": cached, "cache_write": 0}
        return text, usage

    return call


def mock_transport(_model="mock", **_kw):
    """Keyless transport for pipeline dry-runs: a valid empty plan every
    turn (empty orders = the policy plays the turn)."""
    def call(system_text, user_text, schema):
        return (json.dumps({"commentary": "mock: standing doctrine",
                            "orders": []}),
                {"model": "mock", "in": 0, "out": 0,
                 "cache_read": 0, "cache_write": 0})
    return call


# ------------------------------------------------------------ the planner
class LLMPlanner:
    """Callable planner for plans.play_game: planner(tg, side) -> plan|None.
    None means 'no plan this turn' and plans.take_turn plays pure policy."""

    def __init__(self, transport=None, doctrine_path=None, orders_log=None,
                 max_calls=400, model=DEFAULT_MODEL, effort=DEFAULT_EFFORT):
        self.transport = transport or claude_transport(model, effort)
        self.doctrine_path = doctrine_path
        self.orders_log = orders_log
        self.max_calls = max_calls
        self.calls = 0
        self.fallbacks = 0
        self.usage_total = {"in": 0, "out": 0, "cache_read": 0}
        self._system = None

    def _log(self, entry):
        if not self.orders_log:
            return
        with open(self.orders_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def _sys_for(self, tg):
        if self._system is None:
            doctrine = "(no doctrine book found)"
            path = self.doctrine_path or os.path.join(tg.game.dir, "doctrine.md")
            if os.path.exists(path):
                doctrine = open(path, encoding="utf-8").read()
            self._system = build_system(doctrine, tg.scenario["name"],
                                        tg.game.side_order)
        return self._system

    @staticmethod
    def _to_plan(raw_text):
        data = json.loads(raw_text)
        orders = []
        for o in data.get("orders", []):
            o = {k: v for k, v in o.items() if v not in ("", [])}
            orders.append(o)
        return {"orders": orders}, data.get("commentary", "")

    def __call__(self, tg, side):
        mode = "bluegray" if type(tg).__name__ == "BlueGrayGame" else None
        briefer = BRIEFERS.get(mode)
        entry = {"turn": tg.s["turn"], "side": side, "phase": tg.s["phase"]}
        if briefer is None or self.calls >= self.max_calls:
            self.fallbacks += 1
            entry.update(fallback=True, why="no briefer for family"
                         if briefer is None else "max_calls reached")
            self._log(entry)
            return None
        t0 = time.time()
        user = briefer(tg, side)
        problems, plan, commentary, usage = None, None, "", None
        try:
            for attempt in (1, 2):
                self.calls += 1
                raw, usage = self.transport(self._sys_for(tg), user, PLAN_SCHEMA)
                for k in self.usage_total:
                    self.usage_total[k] += (usage or {}).get(k, 0)
                plan, commentary = self._to_plan(raw)
                problems = plans.validate_plan(tg, side, plan)
                if not problems:
                    break
                user = (briefer(tg, side)
                        + "\n\nYour previous plan was rejected by the compiler:\n- "
                        + "\n- ".join(problems)
                        + "\nEmit a corrected plan as JSON.")
                plan = None
        except Exception as e:            # API/auth/JSON failure -> policy turn
            self.fallbacks += 1
            entry.update(fallback=True, why=f"{type(e).__name__}: {e}"[:300],
                         latency_s=round(time.time() - t0, 1))
            self._log(entry)
            return None
        if plan is None:
            self.fallbacks += 1
            entry.update(fallback=True, why="plan invalid after retry",
                         problems=problems,
                         latency_s=round(time.time() - t0, 1))
            self._log(entry)
            return None
        entry.update(fallback=False, commentary=commentary, plan=plan,
                     usage=usage, latency_s=round(time.time() - t0, 1))
        self._log(entry)
        return plan
