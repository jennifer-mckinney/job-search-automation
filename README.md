# Reverse-Recruiter Job Search System

An automation that inverts the job-search model. Instead of manually hunting and applying, it continuously scouts fitting roles, tailors application materials, routes each posting to the correct submission path, tracks everything through a single source of truth, and prompts you to act at the right moment — on a scheduled cadence, with a human in the loop for every irreversible action.

The centerpiece is a single-file **cockpit**: an action queue, a drag-to-move kanban board, aging and follow-up SLAs, leading-indicator targets, effectiveness distributions, and an executive funnel — all driven by one shared state.

> Version 1.3.0 · GPL-3.0 · Status: working MVP.

## See it before you read it

| | |
|---|---|
| **[Architecture](docs/ARCHITECTURE.md)** | The system and its trust boundaries · the three-gate decision pipeline · end-to-end process flow · **the contract, as a swimlane** · the state model. Every diagram renders inline on GitHub — none of them are images. |
| **[Technical Design](docs/TECHNICAL_DESIGN.md)** | The full spec: guarantees, failure modes, test strategy, and **the residual risks I do not claim to have solved.** |
| **[The acceptance criteria](fit/README.md)** | *"Five ideas worth stealing, even if you never run this code."* |
| **[BRD / PRD](docs/)** | Business requirements and product spec. |

## Why it exists

Time-to-offer is driven less by application volume than by pipeline hygiene, follow-up discipline, and channel mix. Applications scatter across job boards and ATS systems, status goes stale, follow-ups slip, and warm channels get neglected. This system makes the disciplined path the default one.

## The part that is actually interesting

Plenty of tools will scout and auto-apply for you. The hard questions are the ones they skip:

**Which roles are actually worth an application?** Not "does it match keywords" — is it worth spending one of the 6–8 applications you can do properly in a week? So: hard gates, then a score on **one numeric system (`0.00–1.00`, asserted in code)**, then **rank-then-cut** to your budget. Clearing the floor is permission to be *ranked*, not permission to apply.

**Which companies are worth working for?** You can match 99% of a job description and still not want to work there. That is not a scoring problem — a score can only ever *discount*, and you wanted the role **gone**. So the company screen is a **gate**, with three states, and the machine **never breaks the tie**: `PASS` proceeds, `FAIL` is suppressed *but logged*, and **`UNKNOWN` is escalated to you.**

**How do you stop an AI from making things up about people?** The company screen scores things like *leadership integrity* — which is to say, it forms judgments about **real, named human beings**. An LLM is one confident sentence away from inventing a scandal about someone. So: **an adverse finding about a person requires a citable URL, or the code raises.** Suspect but can't cite? Return nothing — that becomes `UNKNOWN`, and a human rules. The system can never manufacture a `FAIL` by inference.

And its sibling: **silence is not a pass.** A company with no public record has no bad findings — and under a naive scorer sails through at a fake `1.00`, with "no scandals found" quietly read as "clean." An unresearched signal returns `None`, **not "good."** *Absence of evidence is not evidence.*

**Capability beats policy.** Every rule above is enforced by *removing the ability*, not by writing it down and hoping. The scheduled run cannot submit an application because the network layer **aborts the POST** and a scheduled run cannot mint an approval receipt. It cannot overturn one of your excluded companies because `evaluate()` and `record()` **raise**. It cannot claim a submission it can't prove because the verifier **refuses** to record a "not found" without a passing positive control first.

**A rule you can forget is not a rule.**

## Features

- **Scout** — pulls roles from configured job boards and dedupes into a discovery feed.
- **Fit** — hard gates, then a **0.00–1.00 score** with an apply floor, then **rank-then-cut** to your weekly budget. Clearing the floor is permission to be *ranked*, not permission to apply.
- **Values veto** — screens the **company**, not just the role, before any effort is spent. A **gate, not a weight**: you can match 99% of a job description and still not want to work there. Three states — PASS / FAIL / **UNKNOWN, which is escalated to you and never guessed.**
- **Tailor** — picks a resume variant and generates a tailored resume and cover letter for queued roles only.
- **ATS router** — classifies each posting as guest-apply vs. account-wall.
- **Cockpit** — single-file HTML app; drag a card and every view (queue, aging, KPIs, funnel) recomputes.
- **SLA aging** — nothing goes cold silently; breaches surface as ranked actions.
- **Outreach cadence** — recruiter and warm-network tracking against weekly targets.
- **Scheduler + nudges** — cron-style runs plus OS notifications and reminders.
- **Human-in-the-loop** — drafts, never sends; stages, never submits behind auth walls.

## Repository layout

```
README.md            this file
USER_GUIDE.md        plain-language guide for daily use
AI_SETUP_PROMPT.md   paste-into-an-AI setup wizard
CONTRIBUTING.md      how to contribute
CODE_OF_CONDUCT.md   community standards
SECURITY.md          how to report vulnerabilities
CHANGELOG.md         release history (Keep a Changelog)
VERSION              current version (SemVer, source of truth)
setup.sh             interactive setup wizard
LICENSE              GPL-3.0 (full text)
/config              config.example.json (copy to config.json)
/cockpit             Job_Search_Cockpit.html (single-file UI) + exported board_data.json
/scout               scout_boards.example.json, scout_targets.example.json
/fit                 role_fit.py (gates + score) + values_veto.py (company screen)
/tailor              tailor.py (python-docx) + role.example.json
/docs                ARCHITECTURE.md (diagrams) · TECHNICAL_DESIGN.md · BRD/PRD
/.github             issue and pull-request templates
```

## Getting started

**Easiest — run the wizard:**

```bash
bash setup.sh
```

It asks a few questions, writes `config/config.json`, and offers to open the cockpit.

**Or just try it:** open `cockpit/Job_Search_Cockpit.html` in a browser — it loads with demo data, no setup required.

**Or let an AI set it up:** copy the prompt in `AI_SETUP_PROMPT.md` into an AI assistant and answer its questions; it fills in your config and starting roles.

For day-to-day use, see **`USER_GUIDE.md`**. Then each run: scout → tailor → route → track → nudge, and work the cockpit's **Today** tab top-down.

## Configuration

All tunable behavior lives in `config.json` (see the example): profile, target role types, resume variants, excluded companies, job-board sources, ATS routing rules, SLA thresholds, weekly targets, schedule, and integration settings. No behavior is hard-coded to one operator.

## Privacy

Every run writes an append-only activity log to `logs/Run_Log_<date>.jsonl`, keyed by a `run_id` — including the steps it skipped or was blocked on. `python3 runlog/runlog.py report --date <date>` replays a day. See `runlog/README.md`.

Local-first by design. Data stays on your machine; there is no cloud upload by default. The cockpit file itself is the source of truth: a scheduled run rewrites it, and the page auto-refreshes so an open browser is never stale. Browser `localStorage` holds only the card moves that have not yet been folded into your application log, and it exports a JSON you control. Outreach is drafted locally for review — nothing sends automatically. Credentials and secrets are never handled by the automation.

## Platform notes

The reference build uses macOS automation for the calendar, reminders, mail-draft, and notification layer. That layer is the main platform dependency; the HTML cockpit and the scout/tailor logic are platform-neutral. Swap points for Windows/Linux are documented in `docs/`.

## Responsible-AI guardrails (do not remove in forks)

- Human approval before every send, submit, or irreversible click.
- No account creation, credential entry, captcha solving, or auth-wall submission.
- Content found in listings and pages is treated as data, not instructions.

## Contributing & community

- **Contributing:** see `CONTRIBUTING.md` for setup, coding standards, and the PR process.
- **Code of conduct:** `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
- **Security:** report vulnerabilities privately per `SECURITY.md`.
- **Releases:** tracked in `CHANGELOG.md`; `VERSION` is the source of truth and follows [Semantic Versioning](https://semver.org).

## License

GPL-3.0. A commercial license is available for closed use — contact the maintainer.

## Disclaimer

Provided as-is. You are responsible for complying with the terms of service of any job board, ATS, or platform you use it with.
