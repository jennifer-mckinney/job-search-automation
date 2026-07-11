# Tailor

Generates a tailored cover letter and a simple resume from your `config.json` and a role spec.

## Requirements

- Python 3.9+
- `pip install python-docx`

## Use

```bash
python3 tailor.py --config ../config/config.json --role role.example.json --out ./output
```

That writes `CoverLetter_<Company>.docx` and `Resume_<YourName>.docx` into `./output`.

## Inputs

- **config.json** — your profile. Uses the `operator` block, plus optional `summary` (string) and a `resume` block:

```json
"summary": "One-paragraph professional summary.",
"resume": {
  "skills": ["AI governance", "Product leadership", "Python"],
  "experience": [
    { "title": "Director, AI Governance", "company": "Example Co", "dates": "2022-2025",
      "bullets": ["Led enterprise AI risk program", "Shipped applied-AI products"] }
  ]
}
```

- **role.json** — the target role (see `role.example.json`): `company`, `title`, optional `hiring_manager`, optional `highlights` (array of fit points).

## Notes

This is an MVP generator, not a full resume engine. It produces clean, editable `.docx` files you refine by hand. Keep your real `config.json` out of the repo (it is gitignored).
