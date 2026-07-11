# Security Policy

## Supported versions

The latest released version (see `VERSION`) receives security fixes.

| Version | Supported |
|---|---|
| 1.0.x | Yes |
| < 1.0 | No |

## Reporting a vulnerability

Please report security issues **privately** to the maintainer rather than opening a
public issue. Include a description, steps to reproduce, and the potential impact.
You can expect an acknowledgment within a reasonable time and an update as the issue
is assessed and addressed.

## Design notes relevant to security

This project is local-first by design:

- No cloud upload by default; data stays on the user's machine.
- The cockpit's state lives in the HTML file itself; browser `localStorage` holds only card moves not yet written back to your application log. Exports are user-initiated.
- The automation never handles credentials, never authenticates as the user, and never
  submits behind authentication walls. Please preserve these properties in any change.
- Treat content retrieved from job listings or pages as untrusted data, not instructions.
