#!/usr/bin/env python3
"""
runlog.py - append-only activity log for the reverse-recruiter system.

Part of the open-source release. See USER_GUIDE.md.

Every scheduled run appends its activities to a per-day JSONL file:

    logs/Run_Log_<YYYY-MM-DD>.jsonl

One JSON object per line, one line per activity. Runs are identified by a
run_id, so a single day's file can hold all three scheduled runs (plus any
ad-hoc ones) and still be replayed or queried per run.

Design rules:
  - Append-only. Nothing is ever rewritten or deleted.
  - One file per day, so history is trivially browsable and replayable.
  - Every line carries the run_id, a per-run sequence number, and a UTC stamp.
  - Machine-readable first (JSONL), with a human report built on top.

Usage:
    RUN=$(python3 runlog.py start --note "scheduled 3x/day")
    python3 runlog.py log  --run-id "$RUN" --phase P1 --event scout_query \
        --status ok --target Dice --detail "posted_date=ONE" --meta results=25
    python3 runlog.py end  --run-id "$RUN" --status ok --detail "8 new roles"
    python3 runlog.py report --date 2026-07-11
    python3 runlog.py replay --run-id "$RUN"

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA_VERSION = "1.0"

# Phases mirror the Run Workflow SOP exactly. Keep these in sync with the SOP.
PHASES: Dict[str, str] = {
    "P0": "orient",
    "P1": "scout",
    "P2": "read_jd",
    "P3": "tailor",
    "P4": "fill_submit",
    "P5": "track",
    "P5b": "cockpit",
    "P6": "feed",
    "P7": "outreach",
    "P8": "interview_prep",
    "P9": "brief",
    "P10": "run_end",
}

# ok      = the action completed
# skip    = deliberately not done (idempotent no-op, already current, nothing due)
# blocked = a hard stop or guardrail refused the action (account wall, captcha, no address)
# error   = the action was attempted and failed
STATUSES = ("ok", "skip", "blocked", "error")


def utc_now() -> str:
    """UTC timestamp, second precision, always suffixed Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_log_dir() -> Path:
    return Path(__file__).resolve().parent / "logs"


def log_path(log_dir: Path, day: Optional[str] = None) -> Path:
    """Path to the JSONL file for a given day (default: today, UTC)."""
    day = day or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return log_dir / f"Run_Log_{day}.jsonl"


def new_run_id() -> str:
    """Unique, sortable, human-readable run id."""
    t = datetime.now(timezone.utc)
    return f"RUN-{t.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def _parse_meta(pairs: Optional[List[str]]) -> Dict[str, Any]:
    """--meta k=v --meta n=3 -> {"k": "v", "n": 3}. Numbers are coerced."""
    meta: Dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--meta expects key=value, got: {pair!r}")
        k, v = pair.split("=", 1)
        try:
            meta[k] = int(v)
        except ValueError:
            try:
                meta[k] = float(v)
            except ValueError:
                meta[k] = v
    return meta


def read_events(log_dir: Path, day: Optional[str] = None,
                run_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Read events from one day's file, or across all days when day is None."""
    if day:
        files = [log_path(log_dir, day)]
    else:
        files = sorted(log_dir.glob("Run_Log_*.jsonl"))
    events: List[Dict[str, Any]] = []
    for f in files:
        if not f.exists():
            continue
        for lineno, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as exc:
                # A corrupt line must never take down a report.
                print(f"warning: {f.name}:{lineno} is not valid JSON ({exc})",
                      file=sys.stderr)
                continue
            if run_id and ev.get("run_id") != run_id:
                continue
            events.append(ev)
    return events


def next_seq(log_dir: Path, run_id: str) -> int:
    """Per-run sequence number, so a run's events order deterministically."""
    existing = [e for e in read_events(log_dir, run_id=run_id)]
    return max((int(e.get("seq", 0)) for e in existing), default=0) + 1


def append_event(log_dir: Path, run_id: str, phase: str, event: str,
                 status: str = "ok", target: Optional[str] = None,
                 detail: Optional[str] = None,
                 meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Validate and append a single activity line. Append-only, never rewrites."""
    if phase not in PHASES:
        raise ValueError(f"unknown phase {phase!r}; expected one of {sorted(PHASES)}")
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}; expected one of {list(STATUSES)}")
    if not run_id:
        raise ValueError("run_id is required")
    if not event:
        raise ValueError("event is required")

    log_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "schema": SCHEMA_VERSION,
        "run_id": run_id,
        "seq": next_seq(log_dir, run_id),
        "ts": utc_now(),
        "phase": phase,
        "phase_name": PHASES[phase],
        "event": event,
        "status": status,
        "target": target,
        "detail": detail,
        "meta": meta or {},
    }
    path = log_path(log_dir)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def cmd_start(args: argparse.Namespace) -> int:
    run_id = args.run_id or new_run_id()
    append_event(args.log_dir, run_id, "P0", "run_start", "ok",
                 target=args.trigger, detail=args.note,
                 meta=_parse_meta(args.meta))
    # stdout is ONLY the run_id, so a shell can capture it: RUN=$(runlog.py start)
    print(run_id)
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    rec = append_event(args.log_dir, args.run_id, args.phase, args.event,
                       args.status, args.target, args.detail,
                       _parse_meta(args.meta))
    print(f"{rec['run_id']} #{rec['seq']} {rec['phase']}/{rec['event']} [{rec['status']}]")
    return 0


def cmd_end(args: argparse.Namespace) -> int:
    events = read_events(args.log_dir, run_id=args.run_id)
    counts = Counter(e.get("status") for e in events)
    meta = _parse_meta(args.meta)
    meta.update({
        "events": len(events),
        "ok": counts.get("ok", 0),
        "skip": counts.get("skip", 0),
        "blocked": counts.get("blocked", 0),
        "error": counts.get("error", 0),
    })
    append_event(args.log_dir, args.run_id, "P10", "run_end", args.status,
                 detail=args.detail, meta=meta)
    print(f"{args.run_id} closed: {meta['events']} events "
          f"({meta['ok']} ok, {meta['skip']} skip, "
          f"{meta['blocked']} blocked, {meta['error']} error)")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Chronological replay of one run, or of a whole day."""
    events = read_events(args.log_dir, args.date, args.run_id)
    if not events:
        print("no events found")
        return 1
    events.sort(key=lambda e: (e.get("run_id", ""), int(e.get("seq", 0))))
    current = None
    for e in events:
        if e["run_id"] != current:
            current = e["run_id"]
            print(f"\n=== {current} ===")
        mark = {"ok": " ", "skip": "-", "blocked": "!", "error": "X"}.get(e["status"], "?")
        line = (f" {mark} #{e['seq']:>3} {e['ts']} {e['phase']:<4} "
                f"{e['event']:<22} {e['status']:<7}")
        if e.get("target"):
            line += f" {e['target']}"
        if e.get("detail"):
            line += f" - {e['detail']}"
        print(line)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Human summary for a day (or all days). Built for replay and insight."""
    events = read_events(args.log_dir, args.date, args.run_id)
    if not events:
        print("no events found")
        return 1

    runs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in events:
        runs[e["run_id"]].append(e)

    scope = args.date or ("run " + args.run_id if args.run_id else "all days")
    print(f"Run Log report - {scope}")
    print(f"runs: {len(runs)}   events: {len(events)}")

    by_status = Counter(e["status"] for e in events)
    print("status:  " + "  ".join(f"{k}={by_status.get(k, 0)}" for k in STATUSES))

    by_phase = Counter(e["phase"] for e in events)
    print("phases:  " + "  ".join(
        f"{p}({PHASES[p]})={by_phase[p]}" for p in PHASES if by_phase.get(p)))

    problems = [e for e in events if e["status"] in ("blocked", "error")]
    if problems:
        print(f"\nblocked/error ({len(problems)}):")
        for e in problems:
            print(f"  [{e['status']}] {e['run_id']} {e['phase']}/{e['event']}"
                  f" {e.get('target') or ''} - {e.get('detail') or ''}")
    else:
        print("\nblocked/error: none")

    print("\nper run:")
    for rid in sorted(runs):
        evs = sorted(runs[rid], key=lambda e: int(e.get("seq", 0)))
        c = Counter(e["status"] for e in evs)
        closed = any(e["event"] == "run_end" for e in evs)
        print(f"  {rid}  {evs[0]['ts']} -> {evs[-1]['ts']}  "
              f"{len(evs)} events  ok={c.get('ok',0)} skip={c.get('skip',0)} "
              f"blocked={c.get('blocked',0)} error={c.get('error',0)}"
              f"{'' if closed else '  [UNCLOSED]'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="runlog.py",
        description="Append-only, per-day activity log for reverse-recruiter runs.")
    p.add_argument("--log-dir", type=Path, default=default_log_dir(),
                   help="directory holding Run_Log_<date>.jsonl (default: ./logs)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="open a run; prints the run_id on stdout")
    s.add_argument("--run-id", help="reuse a specific run id (default: generate)")
    s.add_argument("--trigger", default="scheduled",
                   help="scheduled | adhoc | replay")
    s.add_argument("--note")
    s.add_argument("--meta", action="append")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("log", help="append one activity")
    s.add_argument("--run-id", required=True)
    s.add_argument("--phase", required=True, choices=sorted(PHASES))
    s.add_argument("--event", required=True,
                   help="e.g. scout_query, jd_read, tailor_resume, log_row, cockpit_seed")
    s.add_argument("--status", default="ok", choices=list(STATUSES))
    s.add_argument("--target", help="company, file, or system acted on")
    s.add_argument("--detail")
    s.add_argument("--meta", action="append")
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("end", help="close a run with a rollup")
    s.add_argument("--run-id", required=True)
    s.add_argument("--status", default="ok", choices=list(STATUSES))
    s.add_argument("--detail")
    s.add_argument("--meta", action="append")
    s.set_defaults(func=cmd_end)

    s = sub.add_parser("report", help="summarize a day, a run, or everything")
    s.add_argument("--date", help="YYYY-MM-DD (default: all days)")
    s.add_argument("--run-id")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("replay", help="chronological event replay")
    s.add_argument("--date", help="YYYY-MM-DD")
    s.add_argument("--run-id")
    s.set_defaults(func=cmd_replay)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
