#!/usr/bin/env python3
"""Tests for runlog.py. Run: python3 test_runlog.py

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
import json
import tempfile
from pathlib import Path

import runlog

PASS = FAIL = 0


def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def main():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "logs"

        # --- run 1: a normal run with a blocked step -------------------------
        r1 = runlog.new_run_id()
        runlog.append_event(d, r1, "P0", "run_start", "ok", detail="scheduled")
        runlog.append_event(d, r1, "P1", "scout_query", "ok", target="Dice",
                            detail="posted_date=ONE", meta={"results": 25})
        runlog.append_event(d, r1, "P2", "jd_read", "ok", target="Google")
        runlog.append_event(d, r1, "P2", "fit_gate", "skip", target="Google",
                            detail="data-center infra TPM, off-track")
        runlog.append_event(d, r1, "P4", "ats_submit", "blocked", target="Carrier",
                            detail="Workday account wall")
        runlog.append_event(d, r1, "P10", "run_end", "ok")

        evs = runlog.read_events(d, run_id=r1)
        chk("6 events written", len(evs) == 6, len(evs))
        chk("seq is 1..6 in order", [e["seq"] for e in evs] == [1, 2, 3, 4, 5, 6],
            [e["seq"] for e in evs])
        chk("run_id on every line", all(e["run_id"] == r1 for e in evs))
        chk("phase_name resolved", evs[1]["phase_name"] == "scout")
        chk("meta preserved", evs[1]["meta"]["results"] == 25)
        chk("blocked captured", any(e["status"] == "blocked" for e in evs))

        # --- run 2: same day, second run -------------------------------------
        r2 = runlog.new_run_id()
        runlog.append_event(d, r2, "P0", "run_start", "ok")
        runlog.append_event(d, r2, "P1", "scout_query", "skip",
                            detail="no new postings since last run")
        runlog.append_event(d, r2, "P10", "run_end", "ok")

        chk("two runs share one daily file",
            len(list(d.glob("Run_Log_*.jsonl"))) == 1)
        chk("run 2 seq restarts at 1",
            [e["seq"] for e in runlog.read_events(d, run_id=r2)] == [1, 2, 3])
        chk("day holds 9 events", len(runlog.read_events(d)) == 9)
        chk("filter by run_id isolates a run",
            len(runlog.read_events(d, run_id=r2)) == 3)

        # --- validation -------------------------------------------------------
        for bad, why in [
            (lambda: runlog.append_event(d, r1, "P99", "x"), "bad phase rejected"),
            (lambda: runlog.append_event(d, r1, "P1", "x", "weird"), "bad status rejected"),
            (lambda: runlog.append_event(d, "", "P1", "x"), "empty run_id rejected"),
            (lambda: runlog.append_event(d, r1, "P1", ""), "empty event rejected"),
        ]:
            try:
                bad()
                chk(why, False, "no exception raised")
            except ValueError:
                chk(why, True)

        # --- corrupt line must not break reads --------------------------------
        f = runlog.log_path(d)
        with f.open("a", encoding="utf-8") as fh:
            fh.write("{ this is not json\n")
        chk("corrupt line skipped, good lines still read",
            len(runlog.read_events(d)) == 9)

        # --- append-only: nothing was rewritten -------------------------------
        raw = [l for l in f.read_text().splitlines() if l.strip()]
        chk("file is append-only (10 raw lines incl. corrupt)", len(raw) == 10, len(raw))
        first = json.loads(raw[0])
        chk("first line still run 1 start",
            first["run_id"] == r1 and first["event"] == "run_start")

        # --- replay / report exit cleanly -------------------------------------
        code = runlog.main(["--log-dir", str(d), "replay", "--run-id", r1])
        chk("replay exits 0", code == 0)
        code = runlog.main(["--log-dir", str(d), "report"])
        chk("report exits 0", code == 0)
        code = runlog.main(["--log-dir", str(d), "report", "--date", "1999-01-01"])
        chk("report on empty day exits 1", code == 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
