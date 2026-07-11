# User Guide

A simple guide to running your job search with this system. No coding needed for daily use.

## What this is

A personal job-search tool. It helps you track roles, keep applications from going cold, and see what to do each day. The heart of it is the **cockpit** — one page you open in your browser.

## What you need

- A web browser (for the cockpit — that alone works with no setup).
- Python 3.9+ only if you want the setup wizard and the document tailoring. Most people can start with just the browser.

## Fastest setup

Two ways, pick one.

**Option A — the wizard (recommended).** Open a terminal in this folder and run:

```bash
bash setup.sh
```

It asks a few questions (name, email, LinkedIn, location, weekly targets), writes your `config.json`, and offers to open the cockpit. That's it.

**Option B — just open the cockpit.** Double-click `cockpit/Job_Search_Cockpit.html`. It opens with demo data so you can try it immediately. Replace the demo entries with your own when ready (see "Adding your roles").

**Option C — let an AI assistant set it up.** Open `AI_SETUP_PROMPT.md`, copy the prompt into an AI assistant, and answer its questions. It will fill in your config and starting roles for you.

## Using it day to day

Open the cockpit each morning and work the **Today** tab top to bottom. That's the whole routine.

- **Red** items = do now.
- **Amber** = this week.
- **Blue** = when you can.

When something changes — you apply, get a reply, book a screen — go to the **Board** tab and drag the card to its new column. Everything else updates automatically.

## The tabs, in plain terms

- **Today** — your to-do list for the search, sorted by urgency.
- **Board** — drag cards between stages (Sourced, Applying, Applied, Screening, Interview, Offer, Closed). Each card shows how long it has been sitting there.
- **Pipeline** — a table of every active application and whether any are going cold.
- **Outreach** — recruiters and people in your network to contact, with weekly targets.
- **Performance** — are you hitting your weekly application and outreach goals.
- **Effectiveness** — what's working (turns on once you have enough applications).
- **Overview** — a clean summary you can show someone.

## Adding your roles

The cockpit ships with demo companies. To use your own, open `cockpit/Job_Search_Cockpit.html` in a text editor and edit the `SEED` list near the top of the script — copy a line, change the company, role, and stage. Or ask an AI assistant to do it for you using the prompt in `AI_SETUP_PROMPT.md`.

## Keeping your data safe

Everything stays on your computer. There is no cloud, no account, nothing sent anywhere.

The cockpit file itself is the source of truth. When a scheduled run updates your pipeline, it rewrites that file, and the page auto-refreshes so what you are looking at is never stale. Cards you drag are held in your browser until a run folds them into your application log; once the file agrees, the local copy retires itself. If the run has newer information about a card than you do, the run wins.

To back up, or to move to another browser, click **Export board_data.json** on the Board tab and keep the file. **Discard un-logged moves** throws away any card moves that have not made it into your log yet and shows you exactly what the last run wrote.

## Tailoring documents (optional)

If you set up Python, you can generate a starter cover letter and resume:

```bash
python3 tailor/tailor.py --config config/config.json --role tailor/role.example.json --out tailor/output
```

Edit the results by hand — they're a fast first draft, not the finished piece.

## If something looks off

- The cockpit shows demo data → you haven't replaced `SEED` yet. That's expected on first open.
- Your changes disappeared → either you opened it in a different browser or cleared browser data (use **Export** to keep a backup), or a run had newer information for that card and took precedence. Card moves are only held locally until they reach your application log.
- The page reloaded while you were reading → that is the auto-refresh pulling in a scheduled run's update. It never interrupts a drag, and it keeps you on the tab you were using.
- `setup.sh` won't run → make sure you have Python 3 and you're in the repo folder.

## License

GPL-3.0. Free to use and share; improvements stay open. A commercial license is available from the author.
