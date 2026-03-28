# Security Policy

## Supported Versions

This project currently supports the latest `main` branch.

## Reporting a Vulnerability

Please do not open public issues for security vulnerabilities.

Report privately by emailing the maintainers with:
- A clear description of the issue
- Steps to reproduce
- Potential impact
- Suggested remediation (if available)

We will acknowledge receipt as quickly as possible and share remediation timelines after triage.

## Secret Management

- Do not commit real credentials.
- Use environment variables, Kubernetes Secrets, or a secret manager.
- Rotate any credential immediately if exposure is suspected.
