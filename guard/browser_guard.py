#!/usr/bin/env python3
"""
browser_guard.py - the ONLY sanctioned write path to a browser.

Why this exists
---------------
"Never submit unattended" used to live only in the SOP, which means it lived only
in the assistant's compliance. A file-based token would not fix that: the assistant
can write files. What the assistant cannot do is complete an HTTP request that the
browser refuses to send.

So the guard enforces the rule at the NETWORK layer:

  * Every ATS page is opened through a Playwright page with a request interceptor.
  * Any POST / PUT / PATCH to a known ATS domain is ABORTED unless an approval
    receipt exists for that exact company + role.
  * An unattended (trigger=scheduled) run can NEVER hold an approval receipt, so
    its submits are aborted unconditionally. A stray click does nothing.
  * Every navigation, every ATS request, and every blocked attempt is written to
    the run log against the run_id.

Layering, stated honestly:
  Layer 1 PREVENTIVE (capability) - unattended runs get no browser click/type tools.
  Layer 2 PREVENTIVE (network)    - this guard aborts the submit request. <-- here
  Layer 3 PROCEDURAL              - explicit human confirmation before any submit.
  Layer 4 DETECTIVE               - full browser activity trail in the run log.

Layers 2-4 bind only if browser writes go through this guard. Claude-in-Chrome is
READ-ONLY by SOP (reading job descriptions). This is the only write path.

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional

import runlog

# Hosts where a write request means "an application is being submitted".
ATS_HOSTS: List[str] = [
    "greenhouse.io", "lever.co", "ashbyhq.com", "dayforcehcm.com",
    "myworkdayjobs.com", "icims.com", "taleo.net", "successfactors.com",
    "workable.com", "smartrecruiters.com", "jobvite.com", "bamboohr.com",
]
WRITE_METHODS = {"POST", "PUT", "PATCH"}
APPROVAL_DIR = Path(__file__).resolve().parent / "approvals"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def receipt_path(run_id: str, company: str, role: str,
                 approvals: Path = APPROVAL_DIR) -> Path:
    return approvals / run_id / f"{slug(company)}__{slug(role)}.json"


def is_ats(url: str, hosts: Optional[List[str]] = None) -> bool:
    hosts = hosts if hosts is not None else ATS_HOSTS
    return any(h in url for h in hosts)


def approve(run_id: str, company: str, role: str, approved_by: str,
            approvals: Path = APPROVAL_DIR, trigger: str = "attended") -> Path:
    """Mint a single-use approval receipt. Refuses outright for scheduled runs."""
    if trigger == "scheduled":
        raise PermissionError(
            "an unattended (scheduled) run can never hold an approval receipt")
    if not approved_by:
        raise ValueError("approved_by is required - who approved this submit?")
    p = receipt_path(run_id, company, role, approvals)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "run_id": run_id, "company": company, "role": role,
        "approved_by": approved_by,
        "approved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "consumed": False,
    }, indent=2))
    return p


def is_approved(run_id: str, company: str, role: str, trigger: str,
                approvals: Path = APPROVAL_DIR) -> bool:
    """A submit is permitted only for an attended run holding an unconsumed receipt."""
    if trigger == "scheduled":
        return False
    p = receipt_path(run_id, company, role, approvals)
    if not p.exists():
        return False
    try:
        return json.loads(p.read_text()).get("consumed") is False
    except (json.JSONDecodeError, OSError):
        return False


def consume(run_id: str, company: str, role: str,
            approvals: Path = APPROVAL_DIR) -> None:
    """Burn the receipt so one approval can never authorise two submissions."""
    p = receipt_path(run_id, company, role, approvals)
    if p.exists():
        d = json.loads(p.read_text())
        d["consumed"] = True
        d["consumed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        p.write_text(json.dumps(d, indent=2))


class GuardedBrowser:
    """A Playwright page whose ATS write requests are intercepted and logged.

    This is the enforcement point. It does not trust the caller's intent; it
    inspects the actual outbound HTTP request and aborts the ones it must.
    """

    def __init__(self, run_id: str, trigger: str = "attended",
                 company: str = "", role: str = "",
                 log_dir: Optional[Path] = None,
                 approvals: Path = APPROVAL_DIR,
                 ats_hosts: Optional[List[str]] = None,
                 mode: str = "enforce",
                 allow_patterns: Optional[List[str]] = None):
        """
        mode:
          "enforce" - abort unapproved ATS writes (production default).
          "observe" - log what WOULD be aborted, but let it through. For the
                      validation week only, and ONLY for attended sessions:
                      a scheduled run always enforces, no matter what is passed.

        allow_patterns: regexes for ATS write endpoints that are NOT submissions
          (resume/file upload, autosave, telemetry). These must be permitted even
          without a receipt, or the assistant cannot STAGE an application at all.
          Deliberately empty by default (fail-closed). Populate it from the real
          endpoints the validation week observes - do not guess them.
        """
        self.run_id = run_id
        self.trigger = trigger
        self.company = company
        self.role = role
        self.log_dir = log_dir or runlog.default_log_dir()
        self.approvals = approvals
        self.hosts = ats_hosts if ats_hosts is not None else ATS_HOSTS
        # A scheduled run can NEVER be talked into observe mode. Fail-closed.
        self.mode = "enforce" if trigger == "scheduled" else mode
        self.allow_patterns = [re.compile(p) for p in (allow_patterns or [])]
        self.blocked: List[dict] = []
        self.allowed: List[dict] = []
        self.observed: List[dict] = []
        self.navigations: List[str] = []
        self.console_errors: List[str] = []

    def _is_allowed_nonsubmit(self, url: str) -> bool:
        return any(p.search(url) for p in self.allow_patterns)

    def _log(self, phase: str, event: str, status: str, detail: str,
             meta: Optional[dict] = None) -> None:
        try:
            runlog.append_event(self.log_dir, self.run_id, phase, event, status,
                                target=self.company or None, detail=detail,
                                meta=meta or {})
        except Exception as exc:  # logging must never break the guard
            print(f"warning: could not write run log: {exc}", file=sys.stderr)

    def _route(self, route, request) -> None:
        url, method = request.url, request.method

        # Reads, and anything off-ATS, pass untouched. Clicking through form
        # pagination and opening pages is NOT gated - only the write is.
        if method not in WRITE_METHODS or not is_ats(url, self.hosts):
            route.continue_()
            return

        # Every ATS write is recorded, in every mode. This is the dataset the
        # validation week is built on.
        self.observed.append({"url": url, "method": method})
        self._log("P4", "ats_write_observed", "ok", f"{method} {url}",
                  {"url": url, "method": method, "mode": self.mode})

        # Known non-submit writes (file upload, autosave). Required for STAGING:
        # without these the assistant cannot attach a resume at all.
        if self._is_allowed_nonsubmit(url):
            self._log("P4", "ats_write_nonsubmit", "ok",
                      f"ALLOWED (non-submit endpoint) {method} {url}",
                      {"url": url, "method": method})
            route.continue_()
            return

        if is_approved(self.run_id, self.company, self.role, self.trigger,
                       self.approvals):
            consume(self.run_id, self.company, self.role, self.approvals)
            self.allowed.append({"url": url, "method": method})
            self._log("P4", "ats_submit", "ok",
                      f"{method} {url} - approved receipt consumed",
                      {"url": url, "method": method})
            route.continue_()
            return

        reason = ("unattended scheduled run - submission is impossible by design"
                  if self.trigger == "scheduled"
                  else "no approval receipt for this company/role")

        if self.mode == "observe":
            # Validation week, attended only. Record what WOULD have been aborted,
            # then let it through so a real application is not broken by a guard
            # rule we have not finished tuning.
            self.blocked.append({"url": url, "method": method, "observed_only": True})
            self._log("P4", "ats_submit_would_block", "skip",
                      f"OBSERVE ONLY (not aborted) {method} {url} - {reason}",
                      {"url": url, "method": method, "mode": "observe"})
            route.continue_()
            return

        # enforce: the request never leaves the browser.
        self.blocked.append({"url": url, "method": method})
        self._log("P4", "ats_submit_blocked", "blocked",
                  f"ABORTED {method} {url} - {reason}",
                  {"url": url, "method": method, "trigger": self.trigger,
                   "severity": "critical" if self.trigger == "scheduled" else "normal"})
        route.abort()

    @contextmanager
    def page(self, headless: bool = True) -> Iterator:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=headless)
            ctx = browser.new_context(accept_downloads=True)
            pg = ctx.new_page()
            pg.route("**/*", lambda route, request: self._route(route, request))
            pg.on("framenavigated",
                  lambda f: self.navigations.append(f.url) if f.parent_frame is None else None)
            pg.on("console",
                  lambda m: self.console_errors.append(m.text) if m.type == "error" else None)
            self._log("P4", "browser_open", "ok",
                      f"guarded browser opened (trigger={self.trigger})",
                      {"trigger": self.trigger})
            try:
                yield pg
            finally:
                self._log("P4", "browser_close", "ok",
                          f"navigations={len(self.navigations)} "
                          f"allowed_submits={len(self.allowed)} "
                          f"blocked_submits={len(self.blocked)}",
                          {"navigations": len(self.navigations),
                           "allowed": len(self.allowed),
                           "blocked": len(self.blocked),
                           "console_errors": len(self.console_errors)})
                browser.close()


def cmd_approve(a: argparse.Namespace) -> int:
    p = approve(a.run_id, a.company, a.role, a.approved_by, trigger=a.trigger)
    runlog.append_event(runlog.default_log_dir(), a.run_id, "P4", "submit_approved",
                        "ok", target=a.company,
                        detail=f"{a.role} - approved by {a.approved_by}")
    print(f"approval receipt: {p}")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    ok = is_approved(a.run_id, a.company, a.role, a.trigger)
    print(f"{'ALLOW' if ok else 'BLOCK'}  {a.company} / {a.role} "
          f"(trigger={a.trigger})")
    return 0 if ok else 1


def cmd_endpoints(a: argparse.Namespace) -> int:
    """Summarise every ATS write endpoint the guard has seen.

    This is the deliverable of the validation week: it turns a guess about which
    endpoints are submissions and which are file uploads into evidence.
    """
    from collections import Counter
    from urllib.parse import urlparse

    evs = [e for e in runlog.read_events(runlog.default_log_dir(), a.date)
           if e.get("event") in ("ats_write_observed", "ats_write_nonsubmit",
                                 "ats_submit", "ats_submit_blocked",
                                 "ats_submit_would_block")]
    if not evs:
        print("no ATS write activity recorded yet - run some attended applications "
              "in observe mode first")
        return 1

    seen = Counter()
    for e in evs:
        u = e["meta"].get("url", "")
        m = e["meta"].get("method", "")
        if not u:
            continue
        p = urlparse(u)
        seen[(p.netloc, m, p.path)] += 1

    print(f"ATS write endpoints observed ({len(seen)} distinct):\n")
    print(f"{'HOST':32} {'METHOD':7} {'PATH':46} {'N'}")
    for (host, method, path), n in seen.most_common():
        print(f"{host[:32]:32} {method:7} {path[:46]:46} {n}")
    print("\nClassify each. Endpoints that are file upload / autosave / telemetry go into")
    print("allow_patterns (needed for STAGING). Everything else stays gated by a receipt.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="browser_guard.py",
        description="Network-layer submit guard. The only sanctioned browser write path.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("approve", help="mint a single-use approval receipt (attended only)")
    for arg in ("--run-id", "--company", "--role", "--approved-by"):
        s.add_argument(arg, required=True)
    s.add_argument("--trigger", default="attended", choices=["attended", "scheduled"])
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("check", help="would a submit be allowed right now?")
    for arg in ("--run-id", "--company", "--role"):
        s.add_argument(arg, required=True)
    s.add_argument("--trigger", default="attended", choices=["attended", "scheduled"])
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("endpoints",
                       help="summarise observed ATS write endpoints (validation week)")
    s.add_argument("--date", help="YYYY-MM-DD (default: all)")
    s.set_defaults(func=cmd_endpoints)

    a = p.parse_args(argv)
    try:
        return int(a.func(a))
    except (PermissionError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
