#!/usr/bin/env python3
"""
Tests for browser_guard.py — proves the submit is blocked at the NETWORK layer.

A fake ATS server records every POST it actually receives. A real Chrome page
submits a real form. The assertion that matters: when unapproved, the server
receives NOTHING — the request never left the browser.

    python3 test_browser_guard.py

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import http.server
import socketserver
import tempfile
import threading
from pathlib import Path

import browser_guard as BG
import runlog

PASS = FAIL = 0
RECEIVED: list[str] = []


def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {extra}")


class FakeATS(http.server.BaseHTTPRequestHandler):
    """Stands in for greenhouse/lever/etc. Records any POST it truly receives."""

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"""<html><body>
            <form id="f" method="POST" action="/apply">
              <input name="email" value="x@y.z"><button type="submit">Submit</button>
            </form></body></html>""")

    def do_POST(self):
        RECEIVED.append(self.path)          # <-- the ground truth
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def main() -> int:
    httpd = socketserver.TCPServer(("127.0.0.1", 0), FakeATS)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    # Treat our fake server's host as an "ATS" for the guard.
    hosts = [f"127.0.0.1:{port}"]

    tmp = Path(tempfile.mkdtemp())
    logs, approvals = tmp / "logs", tmp / "approvals"

    def submit(trigger, company="Acme", role="TPM"):
        g = BG.GuardedBrowser(runlog.new_run_id(), trigger=trigger, company=company,
                              role=role, log_dir=logs, approvals=approvals,
                              ats_hosts=hosts)
        with g.page() as pg:
            pg.goto(base + "/job")
            pg.click("button[type=submit]")
            pg.wait_for_timeout(400)
        return g

    # --- 1. UNATTENDED scheduled run: submit must be impossible --------------
    RECEIVED.clear()
    g = submit("scheduled")
    chk("scheduled run: POST never reached the server", RECEIVED == [], str(RECEIVED))
    chk("scheduled run: submit was aborted by the guard", len(g.blocked) == 1)
    chk("scheduled run: nothing was allowed through", len(g.allowed) == 0)

    # --- 2. ATTENDED but NOT approved: still blocked -------------------------
    RECEIVED.clear()
    g = submit("attended")
    chk("attended without a receipt: POST never reached the server",
        RECEIVED == [], str(RECEIVED))
    chk("attended without a receipt: aborted", len(g.blocked) == 1)

    # --- 3. A scheduled run cannot even MINT a receipt -----------------------
    try:
        BG.approve("RUN-x", "Acme", "TPM", "operator", approvals=approvals,
                   trigger="scheduled")
        chk("scheduled run refused an approval receipt", False, "it minted one!")
    except PermissionError:
        chk("scheduled run refused an approval receipt", True)

    # --- 4. ATTENDED + approved: the POST goes through ----------------------
    RECEIVED.clear()
    rid = runlog.new_run_id()
    BG.approve(rid, "Acme", "TPM", "operator", approvals=approvals, trigger="attended")
    g = BG.GuardedBrowser(rid, trigger="attended", company="Acme", role="TPM",
                          log_dir=logs, approvals=approvals, ats_hosts=hosts)
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("approved + attended: the POST DID reach the server", RECEIVED == ["/apply"],
        str(RECEIVED))
    chk("approved submit was allowed exactly once", len(g.allowed) == 1)

    # --- 5. the receipt is single-use ---------------------------------------
    chk("receipt is consumed after use",
        not BG.is_approved(rid, "Acme", "TPM", "attended", approvals))
    RECEIVED.clear()
    g = BG.GuardedBrowser(rid, trigger="attended", company="Acme", role="TPM",
                          log_dir=logs, approvals=approvals, ats_hosts=hosts)
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("a consumed receipt cannot authorise a second submit", RECEIVED == [],
        str(RECEIVED))

    # --- 6. a receipt for a DIFFERENT role does not unlock this one ----------
    RECEIVED.clear()
    rid2 = runlog.new_run_id()
    BG.approve(rid2, "Acme", "Other Role", "operator", approvals=approvals)
    g = BG.GuardedBrowser(rid2, trigger="attended", company="Acme", role="TPM",
                          log_dir=logs, approvals=approvals, ats_hosts=hosts)
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("a receipt is scoped to one company+role", RECEIVED == [], str(RECEIVED))

    # --- 6b. VALIDATION-WEEK MODES ------------------------------------------
    # A scheduled run must NEVER be talked into observe mode. Fail-closed.
    RECEIVED.clear()
    g = BG.GuardedBrowser(runlog.new_run_id(), trigger="scheduled", company="Acme",
                          role="TPM", log_dir=logs, approvals=approvals,
                          ats_hosts=hosts, mode="observe")   # <-- asks for observe
    chk("scheduled run cannot be put into observe mode", g.mode == "enforce", g.mode)
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("scheduled run still blocks even when observe was requested",
        RECEIVED == [], str(RECEIVED))

    # Attended + observe: the submit goes through, but is recorded as would-block.
    RECEIVED.clear()
    g = BG.GuardedBrowser(runlog.new_run_id(), trigger="attended", company="Acme",
                          role="TPM", log_dir=logs, approvals=approvals,
                          ats_hosts=hosts, mode="observe")
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("attended observe mode does not break a real application",
        RECEIVED == ["/apply"], str(RECEIVED))
    chk("attended observe mode records what it WOULD have blocked",
        len(g.blocked) == 1 and g.blocked[0].get("observed_only") is True)

    # STAGING must survive: a non-submit write (file upload) is allowed without a
    # receipt, or the assistant cannot attach a resume at all.
    RECEIVED.clear()
    g = BG.GuardedBrowser(runlog.new_run_id(), trigger="scheduled", company="Acme",
                          role="TPM", log_dir=logs, approvals=approvals,
                          ats_hosts=hosts, allow_patterns=[r"/apply$"])
    with g.page() as pg:
        pg.goto(base + "/job")
        pg.click("button[type=submit]")
        pg.wait_for_timeout(400)
    chk("an allow-listed non-submit endpoint (e.g. file upload) is permitted, "
        "so STAGING still works", RECEIVED == ["/apply"], str(RECEIVED))

    # Every ATS write is observed regardless of mode - the validation dataset.
    evs_all = runlog.read_events(logs)
    chk("every ATS write is recorded as ats_write_observed",
        len([e for e in evs_all if e["event"] == "ats_write_observed"]) >= 6)

    # --- 7. everything landed in the run log --------------------------------
    evs = runlog.read_events(logs)
    blocked = [e for e in evs if e["event"] == "ats_submit_blocked"]
    crit = [e for e in blocked if e["meta"].get("severity") == "critical"]
    chk("every blocked attempt is in the run log", len(blocked) >= 4, str(len(blocked)))
    chk("a blocked submit in a SCHEDULED run is logged critical", len(crit) >= 1)
    chk("the allowed submit is in the run log",
        any(e["event"] == "ats_submit" and e["status"] == "ok" for e in evs))
    chk("browser open/close activity is logged",
        any(e["event"] == "browser_open" for e in evs)
        and any(e["event"] == "browser_close" for e in evs))

    httpd.shutdown()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
