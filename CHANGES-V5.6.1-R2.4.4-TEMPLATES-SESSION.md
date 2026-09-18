# Agape V5.6.1 R2.4.4 — source templates + local session repair

- Replaces the expandable project-starter button list with a proper data-driven Template dropdown inside Paste text.
- Keeps Blank source as the default and requires an explicit Load template action before replacing source text.
- Adds the reusable Agape full-system source test as a built-in template while retaining the flooring-recycling research template.
- Keeps loaded template text editable in the normal Source box.
- Adds a server-side-only compatibility retry for loopback child services that return SESSION_REQUIRED. The Core local-session token is never exposed to the browser or sent to remote hosts.
- Adds regression tests for the dropdown, built-in template, loopback-only session retry and token loading.
