#!/usr/bin/env python3
"""
Real-browser tests for Job_Search_Cockpit.html.

Drives an actual Chrome (Playwright, channel="chrome") against a copy of the
cockpit served over http://localhost, so localStorage, rendering, real HTML5
drag-and-drop and the three-way merge are exercised for real - not stubbed.

    python3 test_cockpit_browser.py [path-to-cockpit.html]

Copyright (C) 2026 Jennifer McKinney
SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

PASS = FAIL = 0


def chk(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {extra}")


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    """The default handler sends Last-Modified, and mtime is only 1-second
    granular. Two rewrites inside one second => 304 => Chrome renders the STALE
    file and the merge tests lie. Never let the page be revalidated."""

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        super().end_headers()

    def log_message(self, *a):
        pass


def serve(directory: Path) -> tuple[int, socketserver.TCPServer]:
    handler = functools.partial(NoCacheHandler, directory=str(directory))
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd.server_address[1], httpd


def col_counts(page) -> dict:
    """Read the board's rendered column headers: {stage name: card count}."""
    return page.evaluate("""() => {
        const out = {};
        document.querySelectorAll('#c_board .col').forEach(c => {
            const n = c.querySelector('.colhead .n')?.textContent?.trim();
            const t = c.querySelector('.colhead .ct')?.textContent?.trim();
            if (n) out[n] = parseInt(t, 10);
        });
        return out;
    }""")


def ready(page) -> None:
    """The board lives inside a tab panel, so it is attached but not visible
    unless the Board tab is active. Wait on attachment, not visibility."""
    page.wait_for_selector("#c_board .col", state="attached")


def show_board(page) -> None:
    page.click("nav button[data-t='board']")
    page.wait_for_selector("#c_board .col", state="visible")


def drag(page, card_id: str, to_col: str) -> None:
    """Real HTML5 drag-and-drop with a genuine DataTransfer, as Chrome fires it."""
    page.evaluate("""([id, toCol]) => {
        const cards = [...document.querySelectorAll('#c_board .kcard')];
        const cols  = [...document.querySelectorAll('#c_board .col')];
        const co = STATE.cards.find(c => c.id === id).company;
        const src = cards.find(c => c.querySelector('.kco').textContent.trim() === co);
        const stageName = STAGES.find(s => s.id === toCol).name;
        const dst = cols.find(c => c.querySelector('.colhead .n').textContent.trim() === stageName);
        const dt = new DataTransfer();
        src.dispatchEvent(new DragEvent('dragstart', {bubbles: true, dataTransfer: dt}));
        dst.dispatchEvent(new DragEvent('dragover',  {bubbles: true, dataTransfer: dt}));
        dst.dispatchEvent(new DragEvent('drop',      {bubbles: true, dataTransfer: dt}));
        src.dispatchEvent(new DragEvent('dragend',   {bubbles: true, dataTransfer: dt}));
    }""", [card_id, to_col])
    page.wait_for_timeout(120)


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "Job_Search_Cockpit.html").resolve()
    if not src.exists():
        print(f"cockpit not found: {src}")
        return 1

    tmp = Path(tempfile.mkdtemp())
    target = tmp / "cockpit.html"
    shutil.copy(src, target)
    port, httpd = serve(tmp)
    url = f"http://127.0.0.1:{port}/cockpit.html"
    print(f"testing {src.name} in real Chrome at {url}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(accept_downloads=True)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text)
                 if m.type == "error" and "favicon" not in m.text.lower()
                 and "404" not in m.text else None)
        page.goto(url)
        ready(page)

        # --- 1. it renders at all -------------------------------------------
        chk("page loads with no JS errors", not errors, str(errors[:2]))
        tabs = page.eval_on_selector_all("nav button", "els => els.map(e => e.textContent)")
        chk("all 7 tabs render",
            tabs == ["Today", "Board", "Pipeline", "Outreach", "Performance",
                     "Effectiveness", "Overview"], str(tabs))

        counts = col_counts(page)
        chk("board renders 7 columns", len(counts) == 7, str(counts))
        seed_applied = page.evaluate("SEED.cards.filter(c => c.col === 'applied').length")
        chk("Applied column matches SEED", counts.get("Applied") == seed_applied,
            f"rendered={counts.get('Applied')} seed={seed_applied}")

        # --- 2. real drag ----------------------------------------------------
        card = page.evaluate("SEED.cards.find(c => c.col === 'applied').id")
        drag(page, card, "screen")
        after = col_counts(page)
        chk("drag moves the card on the board",
            after.get("Screening") == counts.get("Screening", 0) + 1
            and after.get("Applied") == counts.get("Applied") - 1, str(after))
        chk("moveCard set status + reset time-in-column",
            page.evaluate(f"(() => {{const c = STATE.cards.find(x => x.id === '{card}');"
                          "return c.col === 'screen' && c.status === 'Screening' "
                          "&& (c.history || []).length > 0;})()"))
        pend = page.evaluate("JSON.parse(localStorage.getItem('cockpit_pending_v2') || '[]')")
        chk("pending move written to localStorage",
            len(pend) == 1 and pend[0]["id"] == card and pend[0]["to"] == "screen", str(pend))

        # --- 3. survives a reload (file unchanged) ---------------------------
        page.reload()
        ready(page)
        chk("un-logged move survives a real reload",
            page.evaluate(f"STATE.cards.find(c => c.id === '{card}').col") == "screen")

        # --- 4. a RUN rewrites the file, folding the move in -----------------
        html = target.read_text()
        html2 = re.sub(r'(\{id:"%s".*?col:")applied(")' % re.escape(card),
                       r"\1screen\2", html, count=1, flags=re.S)
        chk("test harness could rewrite SEED (simulating a run)", html2 != html)
        target.write_text(html2)
        page.reload()
        ready(page)
        chk("board still correct after the run logged it",
            page.evaluate(f"STATE.cards.find(c => c.id === '{card}').col") == "screen")
        chk("pending move retired itself once the file agreed",
            page.evaluate("JSON.parse(localStorage.getItem('cockpit_pending_v2') || '[]').length") == 0)

        # --- 5. conflict: run wins -------------------------------------------
        other = page.evaluate("SEED.cards.find(c => c.col === 'applied').id")
        drag(page, other, "screen")
        html3 = re.sub(r'(\{id:"%s".*?col:")applied(")' % re.escape(other),
                       r"\1closed\2", target.read_text(), count=1, flags=re.S)
        target.write_text(html3)
        page.reload()
        ready(page)
        chk("run wins the conflict (run said closed, she said screen)",
            page.evaluate(f"STATE.cards.find(c => c.id === '{other}').col") == "closed")
        chk("stale local move dropped",
            page.evaluate("JSON.parse(localStorage.getItem('cockpit_pending_v2') || '[]').length") == 0)

        # --- 6. no hardcoding (FR-20) ----------------------------------------
        chk("CFG.today derived from the clock in a real browser",
            page.evaluate("CFG.today") == page.evaluate("new Date().toISOString().slice(0,10)"))
        page.click("nav button[data-t='performance']")
        row = page.evaluate("""() => {
            const m = [...document.querySelectorAll('#t_perf .mini')]
                .find(e => e.textContent.includes('Avg days to first response'));
            return m ? m.querySelector('.n').textContent.trim() : null;
        }""")
        chk("avg days to first response is derived, not a placeholder dash",
            row is not None and row != "—" and (row == "No screens yet"
                                                or re.fullmatch(r"\d+d", row) is not None),
            f"rendered value = {row!r}")

        # --- 7. export -------------------------------------------------------
        show_board(page)
        with page.expect_download() as dl:
            page.click("#c_export")
        d = dl.value
        chk("Export button downloads board_data.json", d.suggested_filename == "board_data.json",
            d.suggested_filename)
        payload = json.loads(Path(d.path()).read_text())
        chk("board_data.json has the contract shape",
            "updated" in payload and "cards" in payload
            and {"company", "role", "status", "column", "daysInColumn"} <= set(payload["cards"][0]),
            str(list(payload.get("cards", [{}])[0])[:6]))

        # --- 8. tab persistence across reload (auto-refresh safety) ----------
        page.click("nav button[data-t='pipeline']")
        page.reload()
        ready(page)
        chk("active tab preserved across reload (auto-refresh won't yank you)",
            page.evaluate("currentTab") == "pipeline")

        chk("no JS errors across the whole session", not errors, str(errors[:2]))
        browser.close()

    httpd.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
