#!/usr/bin/env python3
"""
role_fit.py - the acceptance criteria. Which roles are worth an application.

Most job-search automation skips this. It scouts, it tailors, it applies - and the
decision of WHETHER a role deserves the effort is a vibe, or a keyword count, or
nothing at all. This module makes that decision explicit, scored, and rankable.

    THE PIPELINE. Three stages, cheapest first, each able to kill the role.

      1. HARD GATES   (free)   comp, level, freshness, location, sector, blocklist
      2. FIT SCORE    (free)   0.00-1.00, with an apply floor
      3. VALUES VETO  (costly) values_veto.py - the COMPANY screen, cached per company

    Stage 3 runs last and only on survivors, because it costs a research cycle.

ONE NUMERIC SYSTEM. Every score here and in values_veto lives on [0.00, 1.00] - fit,
veto, evidence weights, track weights. No integers, no 4-point scales, no negative
that escapes the range. It is ASSERTED at the end of score(), not merely intended.
A system with three different scoring scales is a system whose numbers cannot be
compared, and you will eventually compare them anyway.

WHY THE APPLY FLOOR IS LOW (0.60 by default) AND NOT HIGH.
A job description is a WISH LIST. Nobody meets 100% of one - they are written to
describe a person who does not exist. Scoring against a wish list and then demanding
0.80 rejects roles you would win. So: let the HARD GATES disqualify, and let the
SCORE only RANK what survives. Clearing the floor is permission to be RANKED, not
permission to apply - the queue is then cut to your weekly budget.

THE EVIDENCE MODEL is the part worth stealing.
Skills are scored on a 2x2 - do you have EMPLOYER evidence (you did it at a job) and
do you have PORTFOLIO evidence (you can show the artifact) - crossed with whether the
claim is EXPLICIT or IMPLICIT. The counter-intuitive part, and the one people get
backwards: PORTFOLIO-ONLY evidence outranks EMPLOYER-ONLY evidence. Employer evidence
proves the COMMON thing - lots of candidates have held that title. The portfolio
proves the RARE thing - the artifact most of your competition cannot produce. Weight
accordingly. Defaults are in fit/skills.example.json.

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

from values_veto import blocked, load_config as _load_veto_cfg   # noqa: F401

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "config.json"
SKILLS = Path(__file__).resolve().parent / "skills.json"


def load_config(path: Optional[Path] = None) -> dict:
    p = Path(path or CONFIG)
    if not p.exists():
        raise SystemExit(f"no config at {p}. Copy config/config.example.json to "
                         f"config/config.json and edit it.")
    c = json.loads(p.read_text())["criteria"]
    w = c["weights"]
    pos = w["intersection"] + w["track"] + w["evidence"] + w["mission"]
    if abs(pos - 1.0) > 1e-6:
        raise SystemExit(f"criteria.weights (excluding coding_penalty) must sum to "
                         f"1.00, got {pos}")
    return c


def _clamp(x: float) -> float:
    """THE invariant. Everything in this system lives on [0.0, 1.0]."""
    return max(0.0, min(1.0, x))


def _hit(text: str, words: List[str]) -> bool:
    """Word-boundary match for SHORT tokens; substring for phrases.

    A real defect this prevents:  "ai" in "retail supply chain"  ->  True
    ("retAIl", "chAIn"). Substring-matching a two-letter token silently mis-classified
    an entire career track. Same family: "ml" inside "html". Anything under four
    characters MUST match on a word boundary."""
    for w in words:
        w = w.lower()
        if len(w) <= 3:
            if re.search(rf"\b{re.escape(w)}\b", text):
                return True
        elif w in text:
            return True
    return False


# ============================================================================
# THE EVIDENCE MODEL - the 2x2, crossed with explicit/implicit
# ============================================================================
# PORTFOLIO-ONLY BEATS EMPLOYER-ONLY. This is the part people get backwards.
# Employer evidence proves the COMMON thing (many candidates held that title).
# Portfolio evidence proves the RARE thing (the artifact your competition cannot
# produce). Weight the rare claim higher, or your rubric rewards being ordinary.
EVIDENCE_WEIGHT = {
    ("explicit", "both"):      1.00,   # did it at work AND can show the artifact
    ("explicit", "portfolio"): 0.75,   # THE RARE CLAIM
    ("explicit", "employer"):  0.40,   # the common claim
    ("implicit", "both"):      0.50,
    ("implicit", "portfolio"): 0.35,
    ("implicit", "employer"):  0.20,
    ("explicit", "none"):      0.00,   # an unevidenced claim is worth nothing
    ("implicit", "none"):      0.00,
}


@dataclass
class Skill:
    name: str
    kind: str                    # "explicit" | "implicit"
    employers: List[str]         # where you did it. Empty = no employer evidence.
    artifacts: str               # named, showable artifacts. Empty = none.

    @property
    def evidence_class(self) -> str:
        if self.employers and self.artifacts:
            return "both"
        if self.artifacts:
            return "portfolio"
        if self.employers:
            return "employer"
        return "none"

    @property
    def weight(self) -> float:
        k = "explicit" if self.kind.lower().startswith("expl") else "implicit"
        return EVIDENCE_WEIGHT[(k, self.evidence_class)]


def load_skills(path: Optional[Path] = None) -> List[Skill]:
    """Your evidence inventory. See fit/skills.example.json.

    NOTE ON EMPTY CELLS: an empty value means NO EVIDENCE. Do not use a placeholder
    like "-" or "n/a" - a non-empty string is TRUTHY, and it will be counted as real
    evidence, inflating skills you cannot actually back. Leave it empty."""
    p = Path(path or SKILLS)
    if not p.exists():
        return []
    raw = json.loads(p.read_text())
    return [Skill(name=s["name"], kind=s.get("kind", "explicit"),
                  employers=[e for e in s.get("employers", []) if e and e.strip()],
                  artifacts=(s.get("artifacts") or "").strip())
            for s in raw["skills"]]


def _tokens(name: str) -> List[str]:
    s = re.sub(r"\(.*?\)", " ", name.lower())
    return [p.strip() for p in re.split(r"[/,&]| and ", s) if len(p.strip()) > 4]


def _parse_comp(text: str) -> Optional[int]:
    best = None
    for m in re.finditer(r"\$\s?(\d{2,3})(?:,(\d{3}))?\s*(k\b)?", text, re.I):
        raw = m.group(0).lower().replace("$", "").replace(",", "").replace(" ", "")
        n = int(re.sub(r"\D", "", raw) or 0)
        if "k" in raw and n < 1000:
            n *= 1000
        if 50_000 <= n <= 900_000:
            best = max(best or 0, n)
    return best


@dataclass
class Fit:
    company: str
    role: str
    url: str = ""
    score: float = 0.0                       # [0.00, 1.00]. ALWAYS.
    track: str = ""
    components: dict = field(default_factory=dict)
    rejects: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    matched: List[str] = field(default_factory=list)

    @property
    def gated_out(self) -> bool:
        return bool(self.rejects)

    def clears_floor(self, floor: float) -> bool:
        return not self.rejects and self.score >= floor


# ============================================================================
# THE SCORE
# ============================================================================
def score(company: str, role: str, jd_body: str, url: str = "",
          posted: Optional[datetime] = None, skills: Optional[List[Skill]] = None,
          cfg: Optional[dict] = None) -> Fit:
    """Stage 1 (hard gates) + Stage 2 (fit score).

    Stage 3, the VALUES VETO, is a separate module and runs AFTER this - only on
    roles that clear the floor, because it costs a research cycle per company.

    Score from the JD BODY, never the title. Titles lie about level and about scope.
    """
    c = cfg or load_config()
    skills = skills if skills is not None else load_skills()
    f = Fit(company=company, role=role, url=url)
    t = f"{role}\n{jd_body}".lower()

    # ======================= STAGE 1. HARD GATES. Binary. ====================
    # No score rescues these. A gated role is INVISIBLE, not merely deprioritised.

    # One call, two walls: the BLOCKLIST (permanent) and a researched FAIL verdict.
    why = blocked(company)
    if why:
        f.rejects.append(f"{company}: {why}")

    for sector, words in (c.get("excluded_sectors") or {}).items():
        hit = next((w for w in words if w in t), None)
        if hit:
            f.rejects.append(f"excluded sector: {sector} (matched {hit!r})")

    levels = c.get("level_words") or []
    if levels and not _hit(role.lower(), levels):
        f.rejects.append(f"below level floor: {role!r}")

    # COMP. Unstated is a FLAG, never a reject - most boards omit it, and absence
    # of evidence is not evidence. Rejecting on missing data empties your pipeline.
    floor = c.get("comp_floor") or 0
    comp = _parse_comp(jd_body)
    if floor:
        if comp is None:
            f.flags.append(f"comp NOT STATED - cannot verify the ${floor:,} floor")
        elif comp < floor:
            f.rejects.append(f"below comp floor: ${comp:,} < ${floor:,}")
        else:
            f.reasons.append(f"comp ${comp:,} clears the ${floor:,} floor")

    # FRESHNESS. Same rule: a board that does not expose a posted date gets a FLAG.
    hours = c.get("freshness_hours") or 0
    if hours:
        if posted is None:
            f.flags.append("posted date NOT EXPOSED by this board - age unverifiable")
        else:
            age = (datetime.now(timezone.utc) - posted).total_seconds() / 3600
            if age > hours:
                f.rejects.append(f"stale: posted {age:.0f}h ago (floor {hours}h)")

    loc = c.get("location_ok") or []
    if loc and not _hit(t, loc):
        f.flags.append("location not matched - your call, not the machine's")

    # ======================= STAGE 2. THE FIT SCORE. [0, 1] ==================
    w = c["weights"]

    # --- C1. THE INTERSECTION - your thesis. The rare combination. -----------
    ix = c["intersection"]
    a = _hit(t, ix["side_a"])
    b = _hit(t, ix["side_b"])
    c_int = 1.00 if (a and b) else (0.30 if (a or b) else 0.00)
    f.components["intersection"] = c_int
    f.reasons.append(
        f"INTERSECTION {c_int:.2f}: " +
        ("BOTH sides - this is the rare role only you can claim" if (a and b)
         else "one side only - you compete with a much larger field" if (a or b)
         else "neither side - is this even your field?"))

    # --- C2. TRACK ------------------------------------------------------------
    c_trk, best = 0.0, ""
    for name, spec in c["tracks"].items():
        if _hit(t, spec["keywords"]) and spec["weight"] > c_trk:
            c_trk, best = spec["weight"], name
    f.track = best
    f.components["track"] = c_trk
    f.reasons.append(f"TRACK {c_trk:.2f}: {best or 'not one of your tracks'}")

    # --- C3. EVIDENCE - from your inventory, never from memory ---------------
    hits = sorted([s for s in skills
                   if (tk := _tokens(s.name)) and any(x in t for x in tk)],
                  key=lambda s: -s.weight)
    top = hits[:6]
    c_evd = (sum(s.weight for s in top) / len(top)) if top else 0.0
    f.components["evidence"] = c_evd
    for s in top:
        f.matched.append(f"{s.name} [{s.kind}/{s.evidence_class}] {s.weight:.2f}")
    rare = [s for s in top if s.evidence_class == "portfolio"]
    if rare:
        f.reasons.append(f"{len(rare)} RARE portfolio-backed skill(s) - the claim most "
                         f"of your competition cannot make: "
                         f"{', '.join(s.name[:30] for s in rare[:3])}")

    # --- C4. MISSION PULL - does the WORK align (NOT the company screen) ------
    sig = {k: v for k, v in (c.get("mission_signals") or {}).items() if k != "note"}
    fired = [k for k, words in sig.items() if _hit(t, words)]
    c_msn = (len(fired) / len(sig)) if sig else 0.0
    f.components["mission"] = c_msn
    f.reasons.append(f"MISSION {c_msn:.2f}: {len(fired)}/{len(sig)} signals")

    # --- PENALTY. Subtract, then CLAMP. --------------------------------------
    # Keep it simple: a role can only go negative if it already scores near zero
    # everywhere, which is far below any sane floor. The clamp is a formality, not
    # load-bearing math. A multiplier would be cleverer and harder to reason about.
    pen = w["coding_penalty"] if _hit(t, c.get("coding_penalty_keywords") or []) else 0.0
    f.components["penalty"] = -pen
    if pen:
        f.reasons.append(f"PENALTY -{pen:.2f}: this role's primary duty is something "
                         f"you have chosen not to claim. Be honest about the boundary.")

    raw = (w["intersection"] * c_int + w["track"] * c_trk
           + w["evidence"] * c_evd + w["mission"] * c_msn) - pen
    f.score = round(_clamp(raw), 4)

    # THE INVARIANT. One numeric system - asserted, not hoped for.
    assert 0.0 <= f.score <= 1.0, f"score {f.score} escaped [0,1]; the invariant broke"
    return f


def select(fits: List[Fit], floor: float, budget: int):
    """RANK, then CUT.

    Clearing the floor is permission to be RANKED, not permission to apply. Without
    this step a "strict" gate still passes 30 roles a week against a budget of 8, and
    you burn your effort on whichever ones happened to be scouted first.

    Gated roles appear in NEITHER list. They do not exist."""
    ok = sorted([f for f in fits if f.clears_floor(floor)], key=lambda x: -x.score)
    return ok[:budget], ok[budget:]


if __name__ == "__main__":
    c = load_config()
    sk = load_skills()
    from collections import Counter
    print(f"\napply floor {c['apply_floor']}  |  comp {c['comp_floor']:,}  |  "
          f"freshness {c['freshness_hours']}h")
    print(f"weights: {c['weights']}")
    print(f"skills loaded: {len(sk)}  {dict(Counter(s.evidence_class for s in sk))}")
    if sk:
        print("\nstrongest (explicit + employer AND portfolio = 1.00):")
        for s in sorted(sk, key=lambda x: -x.weight)[:6]:
            print(f"  {s.weight:.2f}  {s.name[:44]:<46} {s.artifacts[:30]}")
