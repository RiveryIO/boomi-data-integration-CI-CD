# Security Policy

## Supported Versions

This repository contains automation scripts and configuration templates for
Boomi Data Integration CI/CD workflows. Security fixes are applied to the
latest version on the default branch.

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

If you discover a security issue in this repository (e.g. an accidental secret,
an exploitable script behaviour, or an insecure default), please report it
through one of the following channels:

- **Boomi Security:** Follow the responsible-disclosure process at
  <https://boomi.com/company/trust/> or email the Boomi security team directly.
- **GitHub private advisory:** Use the
  [Security → Report a vulnerability](../../security/advisories/new) button in
  this repository (GitHub's private advisory feature).

Please include:
1. A description of the vulnerability and its potential impact.
2. Steps to reproduce or a proof-of-concept (where safe to share).
3. Any suggested remediation if you have one.

We aim to acknowledge reports within **5 business days** and to provide a
remediation timeline within **10 business days**.

## Scope

This repository does **not** store credentials at rest. All secrets
(`ACCOUNT_ID`, `ENV_ID`, `TOKEN`) are injected at runtime via CI environment
variables or a secrets manager. If you find a committed secret in the git
history, please report it immediately so we can rotate it and purge the history.

## Dependency Updates

Dependencies are pinned in `requirements.txt`. We recommend reviewing pinned
versions regularly and updating them when upstream security advisories are
published.
