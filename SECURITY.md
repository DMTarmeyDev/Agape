# Security Policy

[Main README](README.md) · [Security architecture](docs/SECURITY-AUTHORIZATION.md)

## Supported status

Agape is under active development and should currently be treated as early-alpha security-sensitive software.

Do not describe the software as unhackable.

## Reporting a vulnerability

For the public GitHub repository, report vulnerabilities privately through GitHub Security Advisories/private vulnerability reporting when available. Do not open a public Issue containing exploit details.

When reporting:

- do not publish secrets;
- do not paste exploit credentials into public tickets;
- preserve relevant logs/evidence;
- notify the project owner through a private trusted channel.

## Response principles

Security reports should be:

1. acknowledged;
2. triaged by impact;
3. reproduced safely;
4. fixed in a candidate;
5. regression-tested;
6. released through the secure update process;
7. documented without exposing unnecessary exploit secrets.

## Severity

Suggested categories:

```text
CRITICAL
HIGH
MEDIUM
LOW
INFO
```

Critical examples include:

- authentication bypass;
- remote code execution;
- arbitrary credential disclosure;
- AI authorization bypass;
- update signing bypass;
- public access to private admin functions.

## Disclosure

Use coordinated disclosure. Give maintainers reasonable time to reproduce, fix, regression-test, and release a correction before publishing exploit details.
