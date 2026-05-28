# Security Policy

## Reporting a Vulnerability

**Do not open public GitHub issues for security vulnerabilities.**

Please report security issues privately via [GitHub's private vulnerability reporting](https://github.com/INTELLIGENT-UoC/ammba_uoc/security/advisories/new), or by email to the maintainers.

When reporting, include:

- A description of the vulnerability and its impact.
- Steps to reproduce, or a proof-of-concept.
- Affected component(s): `amm-smart-contract`, `amm-clearing-node`, `amm-execution-node`, or other.
- Your assessment of severity.

We aim to acknowledge reports within **5 business days** and provide a remediation timeline within **15 business days** of acknowledgement. Coordinated disclosure preferred.

## Scope

In scope:

- Logic flaws in the clearing algorithm (sigmoid pricing, pro-rata allocation, preference matching) that allow value extraction or manipulation.
- Smart-contract vulnerabilities in `AMMContract.sol` (access control, reentrancy, integer issues, signature/replay).
- Penalty-calculation flaws in the execution node.
- Server-side vulnerabilities in either FastAPI service (auth bypass, SSRF, injection, key handling).
- Supply-chain issues introduced by direct dependencies.

Out of scope:

- Issues in third-party services we integrate with (Energy Web Chain, GSY DEX) — please report those upstream.
- Vulnerabilities requiring physical access to a user's machine or compromised RPC endpoints.

## Supported Versions

This project is pre-1.0. Only the latest tagged release on `main` receives security fixes. We will not backport.
