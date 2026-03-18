# Security Policy

## Supported Versions

Only the latest release receives security fixes. Older versions are not patched.

| Version | Supported |
|---------|-----------|
| latest  | Yes       |
| older   | No        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report security issues through one of these channels:

1. **GitHub Security Advisories** — preferred:
   [Report a vulnerability](https://github.com/Evey-Vendetta/workspace-map/security/advisories/new)

2. **Email** — if you prefer not to use GitHub:
   `212162984+Evey-Vendetta@users.noreply.github.com`

## Response Timeline

- **Acknowledgment:** within 48 hours of your report
- **Status update:** within 7 days (confirmed, investigating, or won't fix)
- **Critical fixes:** released within 30 days of confirmation
- **Disclosure:** coordinated with reporter; no public disclosure before a fix
  is available

## Scope

workspace-map is a local CLI tool. Relevant security issues include:

- Path traversal or arbitrary file read/write via config or search input
- Code execution via crafted config files or index data
- Credential leakage (e.g., API keys written to index files)
- Dependency vulnerabilities with direct exploit paths

Out of scope: issues requiring physical access to the machine, or
theoretical vulnerabilities with no practical exploit path.
