# Run log

Append-only activity log. One file per day, every run identified by a `run_id`.

    logs/Run_Log_<YYYY-MM-DD>.jsonl

One JSON object per line, one line per activity. All of a day's runs append to the
same file and stay separable by `run_id`, so a day is easy to replay or mine for
insight.

## Use

    RUN=$(python3 runlog.py start --trigger scheduled --note "3x/day run")
    python3 runlog.py log --run-id "$RUN" --phase P1 --event scout_query \
        --status ok --target Dice --detail "posted_date=ONE" --meta results=25
    python3 runlog.py end --run-id "$RUN" --status ok --detail "8 new roles"

    python3 runlog.py report --date 2026-07-11     # summary, incl. every blocked/error
    python3 runlog.py replay --run-id "$RUN"       # chronological replay

## Rules

- **Append-only.** Lines are never rewritten or deleted.
- **Log the skips and blocks too.** A run that did nothing must still say why.
- `start` prints only the run_id on stdout, so a shell can capture it.
- A run with no `run_end` line is reported as `[UNCLOSED]` — it died mid-flight.

## Fields

`schema, run_id, seq, ts, phase, phase_name, event, status, target, detail, meta`

Phases: `P0` orient, `P1` scout, `P2` read_jd, `P3` tailor, `P4` fill_submit,
`P5` track, `P5b` cockpit, `P6` feed, `P7` outreach, `P8` interview_prep,
`P9` brief, `P10` run_end.

Statuses: `ok` (done), `skip` (deliberate no-op), `blocked` (a guardrail refused
it), `error` (attempted and failed).

## Tests

    python3 test_runlog.py
