# AI-Assisted Setup

Prefer to be walked through setup by an AI assistant instead of editing files? Copy the prompt below into an AI assistant that can read and write files in this folder (for example a Cowork-style session), and answer its questions one at a time.

---

## Paste this prompt

> You are helping me set up the Reverse-Recruiter Job Search System in this folder. Do it conversationally — ask me one question at a time, then generate the files. Steps:
>
> 1. Ask me for: my full name, email, phone (optional), LinkedIn URL, and location preference (remote / relocation / based in a city). Then ask for my weekly application target and weekly outreach target (suggest 8 and 5).
> 2. From `config/config.example.json`, create `config/config.json` with my answers filled in. Do not include the `_comment` field.
> 3. Ask me for my current roles — for each: company, role title, and which stage it's in (Sourced, Applying, Applied, Screening, Interview, Offer, Closed). Also ask for a fit rating (Strong / Good / Moderate / Stretch) and the source (e.g. LinkedIn, Greenhouse).
> 4. Open `cockpit/Job_Search_Cockpit.html`, and replace the `SEED` object's `cards` array with my real roles (keep the same field shape). Set each card's `enteredAt` and `createdAt` to today's date.
> 5. Ask me for any executive recruiters or warm-network contacts I want to track, and update the `D.recruiters` and `D.network` arrays accordingly.
> 6. Set `SEED.updated` (date) and `SEED.updatedAt` (ISO timestamp) to now — this stamps when the file was last written. Do NOT touch `CFG`: today and the week start are derived from the system clock, so there are no dates to maintain.
> 7. Show me a summary of what you changed and remind me that my personal data files are gitignored and should not be committed.
>
> Ask me the first question now.

---

## Notes

- The assistant only edits your local copies. Nothing is sent anywhere.
- Your real `config.json` and any personalized cockpit are gitignored — keep them out of the public repo.
- If you would rather not use an AI assistant, run `bash setup.sh` for the same result via simple prompts.
