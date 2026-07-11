# Fit — the acceptance criteria

**Which roles are worth an application, and which companies are worth working for.**

Most job-search automation skips this. It scouts, it tailors, it applies — and the decision of *whether a role deserves the effort* is a vibe, a keyword count, or nothing at all. This module makes that decision explicit, scored, and rankable.

## The pipeline

| Stage | Module | Cost | Kills the role? |
|---|---|---|---|
| 1. **Hard gates** | `role_fit` | free | Yes — **invisible**, not deferred |
| 2. **Fit score**, `apply_floor` | `role_fit` | free | Yes — below floor → no tailor cycle |
| 3. **Values veto** | `values_veto` | one research cycle **per company, cached forever** | **Yes — you never see it** |

Stage 3 runs **last**, and only on roles that already cleared the floor, because it is the only expensive step.

## Use

```bash
cp config/config.example.json config/config.json   # your criteria
cp fit/skills.example.json  fit/skills.json        # your evidence
python3 fit/role_fit.py                            # sanity-check what loaded
python3 fit/values_veto.py                         # verdict report + who needs your ruling
python3 -m pytest fit/ -q                          # 30 tests
```

```python
from role_fit import score, select, load_config
from values_veto import blocked, evaluate, record, Signal

cfg = load_config()
f = score("Acme", "Director of AI Governance", jd_body, posted=posted_at)

if f.gated_out:            ...   # invisible. Not deferred — gone.
if not f.clears_floor(cfg["apply_floor"]):  ...   # feed only. No tailor cycle.

queue, overflow = select(fits, floor=cfg["apply_floor"], budget=8)   # RANK, then CUT
```

---

## Five ideas worth stealing, even if you never run this code

### 1. One numeric system, asserted

Every score — fit, veto, evidence weight, track weight — lives on **`[0.00, 1.00]`**, and `score()` **asserts it**. A system with three different scales is a system whose numbers cannot be compared, and you *will* compare them anyway.

### 2. The floor is low on purpose

A job description is a **wish list**. Nobody meets 100% of one — they describe a person who does not exist. Scoring against a wish list and then demanding 0.80 rejects roles you would win.

**Let the gates disqualify. Let the score only rank what survives.** Clearing the floor is permission to be *ranked*, not permission to apply — the queue is then cut to your weekly budget. A "strict" gate with no ranking still passes 30 roles a week against a budget of 8, and you burn your effort on whichever ones happened to be scouted first.

### 3. Portfolio evidence outranks employer evidence

The 2×2: do you have **employer** evidence (you did it at a job) and/or **portfolio** evidence (you can show the artifact)?

| | Weight |
|---|---|
| employer **+** portfolio | **1.00** — unassailable |
| **portfolio only** | **0.75** — the rare claim |
| employer only | 0.40 — the common claim |
| neither | 0.00 |

People get this backwards. Employer evidence proves the **common** thing — plenty of candidates held that title. The portfolio proves the **rare** thing — the artifact your competition cannot produce. Weight it the other way round and your rubric rewards being ordinary.

The uncomfortable use of this file: the skills with employer evidence and **zero artifacts** are usually the career you are trying to *leave*. Seeing them score 0.40 while your portfolio-only skills score 0.75 is the point, not a bug.

### 4. The values veto is a GATE, not a weight

You can match 99% of a job description and still not want to work there. When that happens you do not want the role ranked slightly lower — you want it **gone**.

**A score component can only ever discount. Only a gate makes something invisible.** That is the entire argument for this being a separate stage rather than another weight.

Three states, and **the machine never breaks the tie**:

| | |
|---|---|
| **PASS** | proceed |
| **FAIL** | suppressed, never shown again — **but logged.** The cache *is* the analytics log |
| **UNKNOWN** | **escalated to you.** Not guessed. Not defaulted. Escalated. |

### 5. Two discipline rules, enforced in code

These are the reason to trust the output. Both are **capability, not policy** — you cannot forget them, because the code will not let you do the wrong thing.

**Silence is not a pass.** A company with no public record has no bad findings — and under a naive scorer sails through at a fake `1.00`, with "no scandals found" silently read as "clean." So an unresearched signal returns `None`, **not "good"**, and more than `max_nulls` of them forces `UNKNOWN`. *Absence of evidence is not evidence.*

**No source, no claim — especially about people.** Signals in `person_signals` concern **real, named human beings**. An LLM is one confident sentence away from inventing a scandal about someone. So an **adverse** finding on such a signal **requires a citable URL, or `Signal()` raises.** Suspect but can't cite? Return `None` → `UNKNOWN` → a human rules. The system can **never** manufacture a `FAIL` by inference.

Note the asymmetry: a *positive* finding needs no URL. The rule guards against **manufactured harm**, not against saying nice things.

### Bonus: an exclusion is a wall, not a verdict

Your excluded-company list is **not** a low score. A verdict is something research can *overwrite* — an agent could research an excluded company, score it 0.72, call `record()`, and your exclusion would be **silently gone**. Nothing would flag it.

So exclusions live in their own list, are checked **first**, and `evaluate()` and `record()` **refuse** on them. You cannot research your way past a wall, because the code will not let you try.

Aliases catch subsidiaries, and corporate suffixes and TLDs are normalised away — `ExampleCorp.com, Inc.` still matches. (Get that order wrong and a company's *actual legal name* walks straight through your blocklist. A wall with a hole in it is not a wall.)

---

## Files

| | |
|---|---|
| `role_fit.py` | Hard gates, the 0–1 score, rank-then-cut |
| `values_veto.py` | The company screen: signals, three states, blocklist, verdict log |
| `skills.example.json` | Your evidence inventory — copy to `skills.json` (gitignored) |
| `test_fit.py` | 30 tests, run against `config.example.json` itself |

Criteria live in `config/config.json` under `criteria` and `values_veto`. **No personal data ships in this repo.**
