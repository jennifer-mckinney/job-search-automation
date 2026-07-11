#!/usr/bin/env python3
"""
values_veto.py - the company screen. A GATE, not a scoring component.

You can match 99% of a job description and still not want to work there. When that
happens you do not want the role ranked slightly lower - you want it GONE. A score
component can only ever DISCOUNT. Only a gate can make something invisible. That is
the whole argument for this module existing separately from role_fit.

It runs LAST, and only on roles that already cleared the fit floor, because it costs
a research cycle per company. Verdicts cache per COMPANY, forever: research a company
once and every future role there is free.

WHAT THIS MODULE IS AND IS NOT
It does NOT do the research. It is a deterministic SCORER and RECORDER. Your agent
(or you) gathers evidence and hands it in as structured Signals; this module scores
them, enforces the discipline rules MECHANICALLY, renders the verdict, writes the log.

    THE TWO DISCIPLINE RULES. Enforced in code, not in a policy document, because a
    rule you can forget is not a rule.

    1. SILENCE IS NOT A PASS.
       A company with no public record has no bad findings - and under a naive scorer
       would sail through at a fake 1.00. So an unresearched signal returns None, NOT
       "good", and more than `max_nulls` of them forces UNKNOWN.
       Absence of evidence is not evidence.

    2. NO SOURCE, NO CLAIM - especially about people.
       Signals in `person_signals` concern REAL, NAMED HUMAN BEINGS. An LLM is one
       confident sentence away from inventing a scandal about someone. So an ADVERSE
       finding on such a signal REQUIRES a citable URL, or Signal() RAISES. Suspect
       but cannot cite? Return None -> UNKNOWN -> a human rules. The system can NEVER
       manufacture a FAIL by inference.

THREE STATES, AND THE MACHINE NEVER BREAKS THE TIE
    PASS    -> proceed
    FAIL    -> suppressed, never shown again, but LOGGED (the cache IS the log)
    UNKNOWN -> escalated to the human. Not guessed. Not defaulted. Escalated.

THE BLOCKLIST IS A WALL, NOT A VERDICT
An exclusion is not a low score. A verdict is something research can OVERWRITE - an
agent could research an excluded company, score it 0.72, call record(), and the
exclusion would be silently gone. So excluded companies live in their own list, are
checked FIRST, and evaluate()/record() REFUSE on them. You cannot research your way
past a wall, because the code will not let you try.

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "config.json"
VERDICTS = ROOT / "config" / "company_verdicts.json"   # gitignored - it is your data
_URL = re.compile(r"https?://\S+")


class Excluded(Exception):
    """Raised when anything tries to research or re-verdict an excluded company."""


def load_config(path: Optional[Path] = None) -> dict:
    p = Path(path or CONFIG)
    if not p.exists():
        raise SystemExit(f"no config at {p}. Copy config/config.example.json to "
                         f"config/config.json and edit it.")
    cfg = json.loads(p.read_text())["values_veto"]
    w = sum(cfg["signals"].values())
    if abs(w - 1.0) > 1e-6:
        raise SystemExit(f"values_veto.signals weights must sum to 1.00, got {w}")
    return cfg


# ============================================================================
# SIGNALS
# ============================================================================
@dataclass
class Signal:
    """One researched signal.

    score=None means NOT RESEARCHED / NO EVIDENCE FOUND. It does NOT mean "fine".
    That distinction is the entire reason this class exists rather than a plain float.
    """
    name: str
    score: Optional[float]      # [0.0, 1.0], or None
    source: str = ""            # citable URL. REQUIRED for an adverse person-signal.
    note: str = ""
    cfg: dict = field(default_factory=dict, repr=False)

    def __post_init__(self):
        c = self.cfg or load_config()
        object.__setattr__(self, "cfg", c)
        if self.name not in c["signals"]:
            raise ValueError(f"unknown signal {self.name!r}; expected {set(c['signals'])}")
        if self.score is None:
            return
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"{self.name}: score {self.score} escaped [0,1]")

        # RULE 2, MECHANICAL. An adverse finding about a named human needs a source.
        # Without one the signal is not merely weak - it is UNRESEARCHED.
        if (self.name in c.get("person_signals", [])
                and self.score < 0.5
                and not _URL.search(self.source)):
            raise ValueError(
                f"NO SOURCE, NO CLAIM: '{self.name}' scored {self.score} - an adverse "
                f"finding about named individuals - with no citable URL. This signal "
                f"concerns real people. Pass score=None so the verdict becomes UNKNOWN "
                f"and a human rules. Never manufacture a FAIL from inference.")

    @property
    def researched(self) -> bool:
        return self.score is not None


@dataclass
class Verdict:
    company: str
    verdict: str                            # PASS | FAIL | UNKNOWN
    score: Optional[float]                  # [0,1], or None if too little researched
    decided_by: str                         # "agent" | "human"
    decided_on: str
    reason: str = ""
    hard_fail: str = ""
    signals: Dict[str, dict] = field(default_factory=dict)
    nulls: List[str] = field(default_factory=list)
    roles_suppressed: int = 0


def evaluate(company: str, signals: List[Signal], hard_fail: Optional[str] = None,
             decided_by: str = "agent", cfg: Optional[dict] = None) -> Verdict:
    """Score the signals; render PASS / FAIL / UNKNOWN. Deterministic.

    REFUSES on an excluded company. You do not get to research your way past a wall -
    not even to confirm it. An exclusion is not a hypothesis."""
    c = cfg or load_config()

    why = is_excluded(company, c)
    if why:
        raise Excluded(
            f"{company} is EXCLUDED ({why}). Exclusion means exclusion: it is a "
            f"blocklist, not a verdict, and research cannot overturn it. If you have "
            f"changed your mind, edit excluded_companies in config.json yourself.")

    names = set(c["signals"])
    by_name = {s.name: s for s in signals}
    nulls = [n for n in names if n not in by_name or not by_name[n].researched]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = dict(company=company, decided_by=decided_by, decided_on=now,
                signals={s.name: {k: v for k, v in asdict(s).items() if k != "cfg"}
                         for s in signals},
                nulls=nulls)

    # --- HARD FAIL. Overrides everything, including a perfect weighted score. ------
    # A company can look immaculate on five signals and still have an active
    # discrimination judgment. That is what this exists for.
    if hard_fail:
        if hard_fail not in c["hard_fails"]:
            raise ValueError(f"unknown hard_fail {hard_fail!r}; expected {set(c['hard_fails'])}")
        return Verdict(verdict="FAIL", score=0.0, hard_fail=hard_fail,
                       reason=f"HARD FAIL: {c['hard_fails'][hard_fail]}", **base)

    # --- RULE 1, MECHANICAL. Silence is not a pass. -------------------------------
    if len(nulls) > c["max_nulls"]:
        return Verdict(
            verdict="UNKNOWN", score=None, **base,
            reason=(f"{len(nulls)} of {len(names)} signals unresearched "
                    f"({', '.join(sorted(nulls))}). Absence of evidence is not "
                    f"evidence. A human rules."))

    # Renormalise over what WAS researched, so nulls neither help nor hurt.
    live = sum(c["signals"][n] for n in names if n not in nulls)
    total = sum(c["signals"][s.name] * s.score for s in signals if s.researched)
    val = round(total / live, 4) if live else 0.0
    assert 0.0 <= val <= 1.0, f"veto score {val} escaped [0,1] - the invariant broke"

    if val >= c["pass_at"]:
        v, why = "PASS", f"weighted {val:.2f} >= {c['pass_at']}"
    elif val < c["fail_at"]:
        v, why = "FAIL", f"weighted {val:.2f} < {c['fail_at']}"
    else:
        v, why = "UNKNOWN", (f"weighted {val:.2f} sits between {c['fail_at']} and "
                             f"{c['pass_at']} - too close to call. A human rules.")
    return Verdict(verdict=v, score=val, reason=why, **base)


# ============================================================================
# THE BLOCKLIST - a wall. And THE CACHE - which is also the log.
# ============================================================================
def _key(company: str) -> str:
    """Normalise, so 'ExampleCorp.com, Inc.' and 'examplecorp' are the same company.

    Strip the TLD BEFORE the corporate suffix. Getting that order wrong is a real
    defect: _key("ExampleCorp.com, Inc.") would yield "examplecorpcom" rather than
    "examplecorp", and a company's ACTUAL LEGAL NAME would sail straight through the
    blocklist. A wall with a hole in it is not a wall."""
    s = company.lower().strip()
    s = re.sub(r"\.(com|io|ai|co|net|org|inc)\b", " ", s)
    s = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|plc|gmbh|sa|nv|ag|platforms|"
               r"technologies|technology|labs|group|holdings)\b", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def is_excluded(company: str, cfg: Optional[dict] = None) -> Optional[str]:
    """The REASON this company is blocklisted, else None. Ask this FIRST, always."""
    c = cfg or load_config()
    for e in c.get("excluded_companies", []):
        for name in [e["company"], *e.get("aliases", [])]:
            if _key(name) == _key(company):
                return e.get("reason", "excluded")
    return None


def _load() -> dict:
    if not VERDICTS.exists():
        return {"schema": 1, "verdicts": {}}
    return json.loads(VERDICTS.read_text())


def _save(db: dict) -> None:
    tmp = VERDICTS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, indent=2, sort_keys=True))
    tmp.replace(VERDICTS)               # atomic. A crash never truncates the log.


def record(v: Verdict, cfg: Optional[dict] = None) -> None:
    """REFUSES to write a verdict for an excluded company.

    This guard is what makes the blocklist a WALL. Without it, an agent that
    researched an excluded company and scored it 0.72 would call record() and
    SILENTLY ERASE the exclusion. Nothing would flag it."""
    why = is_excluded(v.company, cfg)
    if why:
        raise Excluded(f"refusing to record a verdict for {v.company} - it is EXCLUDED "
                       f"({why}). A verdict is overwritable; an exclusion is not. "
                       f"That is the entire point.")
    db = _load()
    db["verdicts"][_key(v.company)] = asdict(v)
    _save(db)


def lookup(company: str) -> Optional[dict]:
    return _load()["verdicts"].get(_key(company))


def blocked(company: str, cfg: Optional[dict] = None) -> Optional[str]:
    """THE ONE CALL role_fit makes. Why is this company off the table, or None.

    Two different things, one answer: the BLOCKLIST (permanent, yours, research
    cannot overturn it) and a researched FAIL verdict (a judgment, overwritable).
    Both mean the role is never shown. Only one of them is a wall - and the reason
    string says which, or a human reading the log later cannot tell them apart."""
    why = is_excluded(company, cfg)
    if why:
        return f"EXCLUDED: {why}"
    v = lookup(company)
    if v and v["verdict"] == "FAIL":
        return f"veto FAIL: {v.get('reason') or v.get('hard_fail') or 'failed the screen'}"
    return None


def needs_research(company: str, cfg: Optional[dict] = None) -> bool:
    """True only if this company is neither excluded nor already judged.

    An UNKNOWN counts as RENDERED - it is waiting on a human, not on more crawling.
    An EXCLUDED company is never researched at all: do not spend a cycle confirming
    a settled decision."""
    if is_excluded(company, cfg):
        return False
    return lookup(company) is None


def note_suppression(company: str) -> None:
    """Count what the screen spared you. This is the ROI number."""
    db = _load()
    k = _key(company)
    if k in db["verdicts"]:
        db["verdicts"][k]["roles_suppressed"] = db["verdicts"][k].get("roles_suppressed", 0) + 1
        _save(db)


def pending() -> List[dict]:
    """Every UNKNOWN awaiting a human ruling. The machine never breaks these ties."""
    return [v for v in _load()["verdicts"].values() if v["verdict"] == "UNKNOWN"]


def report() -> str:
    db = _load()["verdicts"]
    if not db:
        return "no verdicts recorded"
    from collections import Counter
    c = Counter(v["verdict"] for v in db.values())
    spared = sum(v.get("roles_suppressed", 0) for v in db.values())
    out = [f"COMPANY VERDICTS  ({len(db)} companies)",
           f"  PASS {c['PASS']}   FAIL {c['FAIL']}   UNKNOWN {c['UNKNOWN']} (awaiting you)",
           f"  roles suppressed by the screen: {spared}"]
    for v in sorted(db.values(), key=lambda x: x["verdict"]):
        s = f"{v['score']:.2f}" if v["score"] is not None else " -- "
        out.append(f"    {v['verdict']:<8} {s}  {v['company'][:28]:<30} "
                   f"[{v['decided_by']}] {v['reason'][:50]}")
    return "\n".join(out)


if __name__ == "__main__":
    print(report())
    p = pending()
    if p:
        print(f"\n{len(p)} company(ies) need YOUR ruling - the agent will not guess:")
        for v in p:
            print(f"  {v['company']}: {v['reason']}")
