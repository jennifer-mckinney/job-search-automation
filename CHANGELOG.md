# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). The `VERSION` file is
the single source of truth for the current release.

## [Unreleased]

### Planned
- Cross-platform integration layer (Windows/Linux equivalents for reminders/notifications).

## [1.3.0] - 2026-07-11

The release that answers the question the system had been quietly skipping: **which roles are actually worth an application, and which companies are worth working for?** Everything before this could scout, tailor and stage. Nothing in it could say *no* for a good reason.

### Added

- **`fit/role_fit.py` — the acceptance criteria.** Hard gates (comp, level, freshness, location, sector, blocklist) run first and are unrescuable by score. Then a fit score on **one numeric system, `[0.00, 1.00]`, asserted in code**. Then **rank-then-cut** to your weekly budget.

  **The apply floor is deliberately low (0.60 by default), and that is the interesting part.** A job description is a *wish list* — it describes a person who does not exist. Scoring against a wish list and then demanding 0.80 rejects roles you would win. So the **gates** disqualify, and the **score** only ranks what survives. Clearing the floor is permission to be *ranked*, not permission to apply. Without ranking, a "strict" gate still passes 30 roles a week against a budget of 8, and you spend your effort on whichever ones happened to be scouted first.

  **The evidence model is the part worth stealing.** Skills score on a 2×2 — employer evidence (you did it at a job) × portfolio evidence (you can show the artifact) — crossed with explicit/implicit. **Portfolio-only (0.75) outranks employer-only (0.40)**, and people get this backwards: employer evidence proves the *common* thing (plenty of candidates held that title); the portfolio proves the *rare* thing (the artifact your competition cannot produce). Weight it the other way round and your rubric rewards being ordinary. Configure in `fit/skills.json`.

- **`fit/values_veto.py` — the company screen. A GATE, not a scoring component.** You can match 99% of a job description and still not want to work there. When that happens you do not want the role ranked slightly lower — you want it **gone**. A score component can only ever *discount*; only a gate makes something *invisible*. That is the whole argument for this being a separate stage rather than another weight.

  Weighted signals on `[0,1]`, and **three states — with the machine never breaking the tie**: **PASS** proceeds; **FAIL** is suppressed and never shown again *but is logged* (the cache **is** the analytics log — never shown again is not the same as never recorded); **UNKNOWN** is **escalated to the human**. Not guessed, not defaulted — escalated. Runs last and only on floor-clearing roles, because it is the only expensive step; verdicts cache **per company, forever**.

  **Two discipline rules, enforced as capability rather than policy** — you cannot forget them, because the code will not let you do the wrong thing:

  1. **Silence is not a pass.** A company with no public record has no bad findings, and under a naive scorer sails through at a fake `1.00` — "no scandals found" silently read as "clean." An unresearched signal returns `None`, **not "good"**, and more than `max_nulls` of them forces `UNKNOWN`. *Absence of evidence is not evidence.*
  2. **No source, no claim — especially about people.** Signals in `person_signals` concern **real, named human beings**, and an LLM is one confident sentence away from inventing a scandal about someone. An **adverse** finding on such a signal **requires a citable URL, or `Signal()` raises**. Suspect but cannot cite? Return `None` → `UNKNOWN` → a human rules. The system can **never** manufacture a `FAIL` by inference. Note the asymmetry: a *positive* finding needs no URL — the rule guards against manufactured **harm**, not against saying nice things.

- **An exclusion is a WALL, not a verdict.** Your excluded-company list is not a low score. A verdict is something research can *overwrite* — an agent could research an excluded company, score it 0.72, call `record()`, and your exclusion would be **silently gone**, with nothing to flag it. So exclusions live in their own config list, are checked **first**, and `evaluate()` and `record()` **refuse** on them. Aliases catch subsidiaries; corporate suffixes and TLDs are normalised away, so `ExampleCorp.com, Inc.` still matches — get that order wrong and a company's *actual legal name* walks straight through your blocklist.

- **`fit/test_fit.py` — 30 tests**, run against `config.example.json` itself, so the example config that ships is *proven* to work rather than assumed to.

### Changed

- **Board reconciler is now event-driven.** `launchd` `WatchPaths` on the export file replaces a 60-second `StartInterval` poll: **1,440 idle wakeups a day → 0**. Each idle poll had also been minting a run id, producing hundreds of orphan `[UNCLOSED]` runs that buried the real ones. The scheduled run remains the safety net.
- **Configuration schema** gains `criteria` and `values_veto` blocks. Both are heavily commented in `config.example.json`: the defaults are placeholders, not advice.
- **Prose fit ratings are retired.** "Strong / Good / Moderate / Stretch" was never defined anywhere, and — more importantly — it never *ranked*.

### Fixed

- **Short-token substring matching.** `"ai" in "retail supply chain"` returns **`True`** ("ret**ai**l", "ch**ai**n"), which silently mis-classified an entire career track. Tokens under four characters now match on word boundaries. Same family: `ml` inside `html`.
- **Placeholder cells read as evidence.** A `"-"` in a skills table is a *non-empty string*, and therefore **truthy** — it was being counted as real evidence and inflating claims that could not be backed. Empty means empty.

## [1.2.0] - 2026-07-11

### Added
- **Network-layer submit guard** (`guard/browser_guard.py`). "Never submit unattended" no longer depends on the assistant's compliance. All browser writes go through a Playwright page with a request interceptor that ABORTS any `POST`/`PUT`/`PATCH` to an ATS host unless an unconsumed approval receipt exists for that exact company+role. A `trigger=scheduled` run can never mint a receipt, so an unattended submit is impossible even if something clicks the button. Receipts are single-use and role-scoped. Every navigation, allowed submit and blocked attempt is written to the run log; a blocked submit inside a scheduled run is logged `severity=critical`. Proven against a fake ATS server that records what it actually receives: **15 tests**.
- **Board auto-reconcile** (`runlog/board_ingest.py`). Closes the gap where the cockpit could run ahead of the application log. You click "Export board_data.json"; the ingester sweeps `~/Downloads`, moves the export into `_inbox/`, updates the log (matching rows by **company, never row index**), rewrites the cockpit `SEED`, stamps `updatedAt`, and archives the export so it cannot be ingested twice. Your pending card moves then retire themselves because the file finally agrees with them. Idempotent, so it is safe to run from launchd/cron every minute and at the top of every run. Full drag→export→log loop tested in a real browser: **15 tests**. This delivers BRD/PRD Phase 2.
- **Real-browser test suite** (`cockpit/test_cockpit_browser.py`). Drives an actual Chrome via Playwright: real HTML5 drag-and-drop, real `localStorage`, real reload, real download. **19 tests**. Browser-based code is now not considered done until it has been exercised in a browser.

### Fixed
- **Stale-render bug found by the browser tests.** With HTTP `Last-Modified` at one-second granularity, two rewrites of the cockpit inside the same second returned `304 Not Modified`, so the browser re-rendered the *old* board while believing it was current. Added `Cache-Control: no-store` to the cockpit. The merge logic was always correct; the browser simply never saw the new state.

## [1.1.0] - 2026-07-11

### Added
- **Run activity log** (`runlog/runlog.py`). Append-only JSONL, one file per day (`logs/Run_Log_<date>.jsonl`), every run keyed by a unique `run_id`. Records phase, event, status (`ok` / `skip` / `blocked` / `error`), target, detail and arbitrary metadata — including the steps that were skipped or blocked, so a run that did nothing still says why. `report` and `replay` subcommands query a day or a single run. A run with no `run_end` line surfaces as `[UNCLOSED]`. 20 unit tests.
- `logs/` is gitignored: run logs contain company names.

### Fixed
- **The cockpit no longer shows stale data.** `load()` preferred `localStorage` over the file's `SEED`, so once you moved a single card, every subsequent scheduled-run update was invisible in that browser until you clicked "Reset to seed" (which discarded your moves). The file is now the source of truth.
- **Removed hardcoded dates.** `CFG.today` and `CFG.weekStart` were frozen string literals, silently rotting every due-date calculation and weekly KPI as time passed. Both are now derived from the system clock (week starts Monday). The run no longer has to advance them.
- **"Avg days to first response" was a hardcoded placeholder** (`—`) masquerading as a metric. It is now computed from each card's `history[]` (first move into Screening or beyond, minus the applied date), with an honest "No screens yet" empty state when there is nothing to average.

### Changed
- **State model.** `SEED`/`D`/`CFG` in the file are authoritative and rewritten by the run. `localStorage` now holds only card moves the run has not yet folded into the application log.
- **Three-way merge on load.** A local move is kept until the *file itself* agrees with it, rather than until a timestamp elapses. A move the run has logged retires itself; if the run has newer authoritative state for that card, the run wins. A timestamp-based rule was implemented first and rejected: it silently discarded any move the run had never seen.
- **Auto-refresh.** The page reloads on focus/visibility change and on an interval, so a scheduled run's update appears in an open browser without manual intervention. Reloads are skipped mid-drag, pending moves survive, and the active tab is preserved.
- "Reset to seed" is now **"Discard un-logged moves"**, which states what it actually does and no-ops when there is nothing pending.

## [1.0.0] - 2026-07-10

### Added
- Single-file **cockpit** (HTML/CSS/JS) with seven tabs: Today, Board, Pipeline, Outreach, Performance, Effectiveness, Overview — all driven by one shared state.
- Drag-to-move **kanban board** with live time-in-column and SLA aging (amber/red thresholds per stage).
- Ranked **action queue** derived from pipeline, outreach, and SLA breaches.
- **Leading-indicator targets** (applications and outreach per week) and an executive conversion funnel.
- **tailor.py** — generates a tailored cover letter and resume from `config.json` and a role spec (python-docx).
- **setup.sh** interactive setup wizard and `AI_SETUP_PROMPT.md` for AI-assisted setup.
- Example configuration: `config.example.json`, `scout_boards.example.json`, `scout_targets.example.json`, `role.example.json`.
- Documentation: `README.md`, `USER_GUIDE.md`, generalized BRD/PRD in `docs/`.
- GPL-3.0 license with a commercial option; copyright headers on source files.

[Unreleased]: https://github.com/jennifer-mckinney/job-search-automation/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/jennifer-mckinney/job-search-automation/releases/tag/v1.2.0
[1.1.0]: https://github.com/jennifer-mckinney/job-search-automation/releases/tag/v1.1.0
[1.0.0]: https://github.com/jennifer-mckinney/job-search-automation/releases/tag/v1.0.0
