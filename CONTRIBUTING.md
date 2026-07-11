# Contributing

Thanks for your interest in improving this project. Contributions of all sizes are welcome.

## Ground rules

- **No personal data in commits.** Never commit a real `config.json`, application log, resume, or any file containing personal contact details. The `.gitignore` blocks the obvious ones — double-check before you push.
- **Keep the guardrails.** The human-in-the-loop and least-privilege behaviors are features, not limitations. Do not add code that submits behind auth walls, creates accounts, solves captchas, or sends messages without explicit user action.
- **Small, focused pull requests** are easier to review and merge.

## Development setup

```bash
# Optional Python tooling (for tailor.py and setup.sh)
python3 -m pip install python-docx

# Syntax checks before you push
bash -n setup.sh
python3 -m py_compile tailor/tailor.py
```

The cockpit is a single self-contained HTML file — open it directly in a browser to test; no build step.

## Coding standards

- Clean, readable code over cleverness. No dead code or commented-out blocks.
- Python: type hints where practical, clear names, graceful error handling.
- JavaScript: keep the cockpit dependency-free and single-file.
- Match the existing style; do not reformat unrelated code.

## Commit and PR process

1. Branch from `main`.
2. Make your change and run the syntax checks above.
3. Update `CHANGELOG.md` under `[Unreleased]`.
4. If behavior or the public interface changes, bump `VERSION` per [SemVer](https://semver.org).
5. Open a pull request using the template; describe what and why.

## Versioning

`VERSION` is the source of truth. MAJOR for breaking changes, MINOR for new features, PATCH for fixes.

## License of contributions

By contributing, you agree your contributions are licensed under **GPL-3.0**, consistent with the project license.
