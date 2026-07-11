#!/usr/bin/env bash
# Reverse-Recruiter Job Search System - setup wizard
# Copyright (C) 2026 Jennifer McKinney - GPL-3.0. WITHOUT ANY WARRANTY.
# Walks you through creating config/config.json and opening the cockpit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG_DIR="$ROOT/config"
CFG="$CFG_DIR/config.json"
EXAMPLE="$CFG_DIR/config.example.json"
COCKPIT="$ROOT/cockpit/Job_Search_Cockpit.html"

echo ""
echo "==================================================="
echo "  Reverse-Recruiter Job Search - Setup Wizard"
echo "==================================================="
echo "This asks a few questions and writes config/config.json."
echo "Press Enter to accept the [default] in brackets."
echo ""

# --- checks ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required but was not found. Install Python 3.9+ and re-run."
  exit 1
fi
if [ ! -f "$EXAMPLE" ]; then
  echo "Missing $EXAMPLE - run this from the repo root."
  exit 1
fi
if [ -f "$CFG" ]; then
  read -r -p "config.json already exists. Overwrite? [y/N] " ow
  case "${ow:-N}" in [yY]*) ;; *) echo "Keeping existing config. Exiting."; exit 0;; esac
fi

ask() { # ask "Prompt" "default" -> echoes answer
  local prompt="$1" def="${2:-}" ans
  if [ -n "$def" ]; then read -r -p "$prompt [$def]: " ans; else read -r -p "$prompt: " ans; fi
  echo "${ans:-$def}"
}

NAME="$(ask 'Your full name' 'Your Name')"
EMAIL="$(ask 'Email' 'you@example.com')"
PHONE="$(ask 'Phone (optional)' '')"
LINKEDIN="$(ask 'LinkedIn URL' 'https://www.linkedin.com/in/your-handle')"

echo ""
echo "Location preference:"
echo "  1) Open to remote"
echo "  2) Open to relocation"
echo "  3) Based in a city, open to remote"
LOC_CHOICE="$(ask 'Choose 1-3' '1')"
case "$LOC_CHOICE" in
  2) LOCATION="Open to relocation" ;;
  3) CITY="$(ask 'Which city' 'Seattle')"; LOCATION="Based in $CITY, open to remote" ;;
  *) LOCATION="Open to remote" ;;
esac

APPS="$(ask 'Weekly application target' '8')"
OUT="$(ask 'Weekly outreach target' '5')"

# --- write config via python (safe JSON) ---
python3 - "$EXAMPLE" "$CFG" "$NAME" "$EMAIL" "$PHONE" "$LINKEDIN" "$LOCATION" "$APPS" "$OUT" <<'PY'
import json, sys
example, out, name, email, phone, linkedin, location, apps, outreach = sys.argv[1:10]
with open(example) as f:
    cfg = json.load(f)
cfg.pop("_comment", None)
cfg.setdefault("operator", {})
cfg["operator"].update({
    "name": name, "email": email, "phone": phone,
    "linkedin": linkedin, "location_line": location,
})
cfg.setdefault("targets", {})
try:
    cfg["targets"]["applications_per_week"] = int(apps)
    cfg["targets"]["outreach_per_week"] = int(outreach)
except ValueError:
    pass
with open(out, "w") as f:
    json.dump(cfg, f, indent=2)
print("\nWrote", out)
PY

echo ""
echo "Done. Next steps:"
echo "  1) Open the cockpit:  $COCKPIT"
echo "  2) Replace the demo DATA/SEED in the cockpit with your roles (or ask your AI assistant to)."
echo "  3) Tailor documents:  python3 tailor/tailor.py --config config/config.json --role tailor/role.example.json --out tailor/output"
echo ""

read -r -p "Open the cockpit now? [Y/n] " op
case "${op:-Y}" in
  [nN]*) echo "You can open it later: $COCKPIT" ;;
  *) if command -v open >/dev/null 2>&1; then open "$COCKPIT";
     elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$COCKPIT";
     else echo "Open this file in your browser: $COCKPIT"; fi ;;
esac
echo "Setup complete."
