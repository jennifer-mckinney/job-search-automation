#!/usr/bin/env python3
"""
test_fit.py - role_fit + values_veto.

The two tests that matter most here are NOT the happy path. They are:

    test_silence_is_not_a_pass    a company with no public record must NOT sail
                                  through on the absence of bad news
    test_no_source_no_claim       an adverse finding about a NAMED HUMAN BEING with
                                  no citable URL must RAISE, not score

Both encode a discipline rule as CAPABILITY rather than policy. You cannot forget
them, because the code will not let you do the wrong thing. That is the difference
between a guardrail and a good intention.

Run:  python3 -m pytest fit/ -q       (or:  python3 fit/test_fit.py)

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import values_veto as vv                                          # noqa: E402
import role_fit                                                   # noqa: E402
from values_veto import Signal, Verdict, evaluate, Excluded       # noqa: E402
from role_fit import Skill, score, select, EVIDENCE_WEIGHT, _hit  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Run against config.example.json with a couple of concrete values filled in,
    so the shipped example is itself proven to work. Isolate the verdict store."""
    c = json.loads((ROOT / "config" / "config.example.json").read_text())
    c["criteria"].update({
        "comp_floor": 200000,
        "freshness_hours": 48,
        "tracks": {
            "primary":  {"weight": 1.00, "keywords": ["ai governance"]},
            "fallback": {"weight": 0.25, "keywords": ["program manager"]},
        },
        "intersection": {"side_a": ["governance"], "side_b": ["build", "architect"]},
        "mission_signals": {"a": ["audit"], "b": ["mentor"]},
        "excluded_sectors": {"finance": ["hedge fund"]},
    })
    c["values_veto"]["excluded_companies"] = [
        {"company": "ExampleCorp", "aliases": ["ExampleCo Labs"], "reason": "values"},
    ]
    p = tmp_path / "config.json"
    p.write_text(json.dumps(c))
    monkeypatch.setattr(vv, "CONFIG", p)
    monkeypatch.setattr(role_fit, "CONFIG", p)
    monkeypatch.setattr(vv, "VERDICTS", tmp_path / "company_verdicts.json")
    return c


@pytest.fixture
def veto_cfg(cfg):
    return cfg["values_veto"]


@pytest.fixture
def skills():
    return [
        Skill("AI Governance", "explicit", ["Employer A"], "my-project"),   # 1.00
        Skill("Hybrid Retrieval", "explicit", [], "my-project"),            # 0.75
        Skill("Change Management", "explicit", ["Employer A"], ""),         # 0.40
    ]


GOV_BUILD = ("Director of AI Governance. You will BUILD and architect the controls, "
             "implement audit tooling, and mentor a team. $250,000. Remote.")


def sigs(veto_cfg, **kw):
    return [Signal(n, kw.get(n, 0.8), source="https://example.org/r", cfg=veto_cfg)
            for n in veto_cfg["signals"]]


# ============================================================================
# THE INVARIANT - one numeric system across every slice
# ============================================================================
def test_fit_score_never_escapes_zero_one(cfg, skills):
    for body in (GOV_BUILD, "", "software engineer live coding", "x" * 800):
        f = score("Acme", "Director of AI Governance", body, posted=NOW, skills=skills)
        assert 0.0 <= f.score <= 1.0


def test_veto_score_never_escapes_zero_one(veto_cfg):
    for v in (0.0, 0.5, 1.0):
        r = evaluate("Acme", sigs(veto_cfg, **{n: v for n in veto_cfg["signals"]}),
                     cfg=veto_cfg)
        assert 0.0 <= r.score <= 1.0


def test_all_declared_weights_are_zero_to_one(cfg, veto_cfg):
    assert all(0.0 <= w <= 1.0 for w in EVIDENCE_WEIGHT.values())
    assert all(0.0 <= t["weight"] <= 1.0 for t in cfg["criteria"]["tracks"].values())
    assert abs(sum(veto_cfg["signals"].values()) - 1.0) < 1e-9


def test_penalty_cannot_drive_the_score_negative(cfg, skills):
    f = score("Acme", "Principal Engineer", "software engineer. live coding.",
              posted=NOW, skills=skills)
    assert f.score == 0.0 and f.components["penalty"] < 0


# ============================================================================
# RULE 1: SILENCE IS NOT A PASS
# A company with no public record has no bad findings. Under a naive scorer it
# sails through at a fake 1.00 - "no scandals found" silently read as "clean".
# ============================================================================
def test_silence_is_not_a_pass(veto_cfg):
    """The whole point. A company you know nothing about is UNKNOWN, never PASS."""
    r = evaluate("GhostCo", [], cfg=veto_cfg)
    assert r.verdict == "UNKNOWN"
    assert r.score is None                       # not 1.0, not 0.0. NONE.
    assert "Absence of evidence is not evidence" in r.reason
    assert len(r.nulls) == len(veto_cfg["signals"])


def test_too_many_nulls_forces_unknown_even_with_perfect_scores(veto_cfg):
    """Three perfect signals and four blanks is NOT a pass. Coverage gates first."""
    keep = list(veto_cfg["signals"])[:len(veto_cfg["signals"]) - veto_cfg["max_nulls"] - 1]
    r = evaluate("ThinCo", [Signal(n, 1.0, source="https://x.org/a", cfg=veto_cfg)
                            for n in keep], cfg=veto_cfg)
    assert r.verdict == "UNKNOWN" and r.score is None


def test_nulls_within_tolerance_renormalise_and_do_not_dilute(veto_cfg):
    keep = list(veto_cfg["signals"])[:len(veto_cfg["signals"]) - veto_cfg["max_nulls"]]
    r = evaluate("ThinCo", [Signal(n, 0.9, source="https://x.org/a", cfg=veto_cfg)
                            for n in keep], cfg=veto_cfg)
    assert r.verdict == "PASS" and r.score == pytest.approx(0.9)


# ============================================================================
# RULE 2: NO SOURCE, NO CLAIM - especially about people
# person_signals concern REAL, NAMED HUMAN BEINGS. An invented finding is
# defamation. The code REFUSES to accept one.
# ============================================================================
def test_no_source_no_claim(veto_cfg):
    with pytest.raises(ValueError, match="NO SOURCE, NO CLAIM"):
        Signal("leadership_integrity", 0.1, source="", cfg=veto_cfg)
    with pytest.raises(ValueError, match="NO SOURCE, NO CLAIM"):
        Signal("leadership_integrity", 0.2, source="I read something once", cfg=veto_cfg)


def test_sourced_adverse_finding_is_allowed(veto_cfg):
    s = Signal("leadership_integrity", 0.1,
               source="https://www.sec.gov/litigation/complaints/x.pdf", cfg=veto_cfg)
    assert s.researched and s.score == 0.1


def test_the_rule_guards_against_HARM_not_against_praise(veto_cfg):
    """A POSITIVE finding needs no URL. The rule exists to stop manufactured harm."""
    assert Signal("leadership_integrity", 0.9, cfg=veto_cfg).researched


def test_unsourced_suspicion_yields_UNKNOWN_never_FAIL(veto_cfg):
    """The escape hatch, and the correct behaviour: suspect but cannot cite -> None.
    That becomes UNKNOWN, and a human rules. It NEVER becomes a FAIL."""
    ss = [Signal(n, 0.8, source="https://x.org/a", cfg=veto_cfg)
          for n in veto_cfg["signals"] if n != "leadership_integrity"]
    ss.append(Signal("leadership_integrity", None, note="rumour, nothing citable",
                     cfg=veto_cfg))
    r = evaluate("MurkyCo", ss, cfg=veto_cfg)
    assert r.verdict != "FAIL"
    assert "leadership_integrity" in r.nulls


def test_non_person_signals_do_not_require_a_url(veto_cfg):
    """Only person_signals carry the defamation risk. Do not over-apply the rule."""
    assert Signal("employee_sentiment", 0.1, cfg=veto_cfg).researched


# ============================================================================
# THREE STATES - and the machine never breaks the tie
# ============================================================================
def test_middle_is_unknown_not_a_guess(veto_cfg):
    r = evaluate("Acme", sigs(veto_cfg, **{n: 0.55 for n in veto_cfg["signals"]}),
                 cfg=veto_cfg)
    assert r.verdict == "UNKNOWN" and "human rules" in r.reason


def test_hard_fail_beats_a_perfect_score(veto_cfg):
    """A company can look immaculate on every signal and still have an active
    discrimination judgment. That is what the override is for."""
    r = evaluate("Acme", sigs(veto_cfg, **{n: 1.0 for n in veto_cfg["signals"]}),
                 hard_fail="discrimination_judgment", cfg=veto_cfg)
    assert r.verdict == "FAIL" and r.score == 0.0


# ============================================================================
# THE BLOCKLIST IS A WALL, NOT A VERDICT
# An exclusion is not a low score. A VERDICT is something research can OVERWRITE:
# an agent could research an excluded company, score it 0.72, call record(), and
# the exclusion would be silently GONE. These tests make that impossible.
# ============================================================================
def test_research_CANNOT_overwrite_an_exclusion(veto_cfg):
    with pytest.raises(Excluded, match="EXCLUDED"):
        evaluate("ExampleCorp", sigs(veto_cfg, **{n: 1.0 for n in veto_cfg["signals"]}),
                 cfg=veto_cfg)                       # a PERFECT score. Still refused.


def test_record_CANNOT_overwrite_an_exclusion(cfg):
    v = Verdict(company="ExampleCorp", verdict="PASS", score=0.95, decided_by="agent",
                decided_on="2026-07-11", reason="looks great!")
    with pytest.raises(Excluded, match="refusing to record"):
        vv.record(v)
    assert vv.blocked("ExampleCorp").startswith("EXCLUDED")


def test_aliases_and_legal_entity_variants_are_blocked(cfg):
    """A blocklist that only catches the exact parent brand is not a blocklist.
    'ExampleCorp.com, Inc.' must still hit - strip the TLD BEFORE the suffix, or
    the company's actual legal name walks straight through."""
    for v in ("ExampleCorp", "EXAMPLECORP", "  examplecorp  ", "ExampleCorp, Inc.",
              "ExampleCorp.com, Inc.", "ExampleCo Labs"):
        assert vv.is_excluded(v), f"{v!r} must be excluded"
    assert vv.is_excluded("NeutralCo") is None


def test_an_excluded_company_is_never_researched(cfg):
    """Do not spend a research cycle confirming a settled decision."""
    assert vv.needs_research("ExampleCorp") is False
    assert vv.needs_research("SomeNewCo") is True


def test_excluded_company_is_gated_no_matter_how_good_the_role(cfg, skills):
    f = score("ExampleCorp", "Director of AI Governance", GOV_BUILD,
              posted=NOW, skills=skills)
    assert f.gated_out and any("EXCLUDED" in r for r in f.rejects)


def test_a_new_exclusion_needs_no_code_change(cfg):
    """The design test: it is CONFIG, not a constant buried in a module."""
    assert cfg["values_veto"]["excluded_companies"][0]["company"] == "ExampleCorp"


# ============================================================================
# THE CACHE IS THE LOG - a FAIL is never shown again, but never discarded
# ============================================================================
def test_fail_is_captured_not_discarded(cfg, veto_cfg):
    vv.record(evaluate("BadCo", sigs(veto_cfg, **{n: 0.05 for n in veto_cfg["signals"]}),
                       cfg=veto_cfg))
    assert vv.lookup("BadCo")["verdict"] == "FAIL"
    assert vv.blocked("BadCo").startswith("veto FAIL:")     # distinguishable from a wall


def test_unknown_is_queued_for_a_human(cfg, veto_cfg):
    vv.record(evaluate("MurkyCo", [], cfg=veto_cfg))
    assert [v["company"] for v in vv.pending()] == ["MurkyCo"]


def test_suppression_count_is_the_roi_number(cfg, veto_cfg):
    vv.record(evaluate("BadCo", sigs(veto_cfg, **{n: 0.05 for n in veto_cfg["signals"]}),
                       cfg=veto_cfg))
    for _ in range(3):
        vv.note_suppression("BadCo")
    assert vv.lookup("BadCo")["roles_suppressed"] == 3


# ============================================================================
# THE EVIDENCE MODEL - the part people get backwards
# ============================================================================
def test_portfolio_evidence_OUTRANKS_employer_evidence():
    """Employer evidence proves the COMMON thing. The portfolio proves the RARE one.
    Weight it the other way round and your rubric rewards being ordinary."""
    portfolio = Skill("X", "explicit", [], "the-artifact")       # 0.75
    employer = Skill("X", "explicit", ["Employer A"], "")        # 0.40
    both = Skill("X", "explicit", ["Employer A"], "artifact")    # 1.00
    assert portfolio.weight > employer.weight
    assert both.weight == 1.00 > portfolio.weight


def test_an_empty_cell_means_NO_EVIDENCE_not_a_placeholder():
    """A placeholder like '-' is a NON-EMPTY STRING, and therefore TRUTHY. Reading
    one as real evidence inflates claims you cannot back. This was a real bug."""
    assert Skill("X", "explicit", [], "").evidence_class == "none"
    assert Skill("X", "explicit", [], "").weight == 0.0
    assert Skill("X", "explicit", ["A"], "").evidence_class == "employer"


# ============================================================================
# GATES, FLOOR, AND THE SHORT-TOKEN TRAP
# ============================================================================
def test_short_tokens_match_on_word_boundaries():
    """A real defect:  "ai" in "retail supply chain"  ->  True   ("retAIl", "chAIn").
    Substring-matching a two-letter token mis-classified an entire career track.
    Same family: "ml" inside "html"."""
    assert not _hit("retail supply chain logistics", ["ai"])
    assert not _hit("we use html and css", ["ml"])
    assert _hit("our ai platform", ["ai"])


def test_unstated_comp_and_missing_date_are_FLAGS_not_rejects(cfg, skills):
    """Most boards omit both. Rejecting on missing data empties your pipeline, and
    absence of evidence is not evidence."""
    f = score("Acme", "Director of AI Governance",
              GOV_BUILD.replace("$250,000.", ""), posted=None, skills=skills)
    assert not f.gated_out
    assert any("comp NOT STATED" in x for x in f.flags)
    assert any("posted date NOT EXPOSED" in x for x in f.flags)


def test_stale_and_underpaid_roles_are_gated(cfg, skills):
    stale = NOW - timedelta(hours=cfg["criteria"]["freshness_hours"] + 1)
    assert score("Acme", "Director of AI Governance", GOV_BUILD,
                 posted=stale, skills=skills).gated_out
    assert score("Acme", "Director of AI Governance",
                 GOV_BUILD.replace("$250,000", "$150,000"),
                 posted=NOW, skills=skills).gated_out


def test_rank_then_cut(cfg, skills):
    """Clearing the floor is permission to be RANKED, not permission to apply.
    A 'strict' gate with no ranking still passes 30 roles against a budget of 8."""
    fits = [score(f"Co{i}", "Director of AI Governance", GOV_BUILD,
                  posted=NOW, skills=skills) for i in range(12)]
    q, over = select(fits, floor=cfg["criteria"]["apply_floor"], budget=8)
    assert len(q) == 8 and len(over) == 4
    assert all(a.score >= b.score for a in q for b in over)


def test_gated_roles_appear_in_NEITHER_queue_nor_overflow(cfg, skills):
    """A gated role is not deferred. It does not exist."""
    good = score("Acme", "Director of AI Governance", GOV_BUILD, posted=NOW, skills=skills)
    gated = score("Acme", "Director of AI Governance", GOV_BUILD + " We are a hedge fund.",
                  posted=NOW, skills=skills)
    q, over = select([good, gated], floor=cfg["criteria"]["apply_floor"], budget=8)
    assert good in q and gated not in q and gated not in over


if __name__ == "__main__":
    import subprocess
    r = subprocess.run([sys.executable, "-m", "pytest", __file__, "-q"],
                       capture_output=True, text=True)
    print(r.stdout[-1400:])
    sys.exit(r.returncode)
