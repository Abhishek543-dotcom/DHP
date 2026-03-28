# Security Policy

## Supported Versions

Security fixes are provided for the latest `main` branch.

## Reporting a Vulnerability

Please do not create public issues for security vulnerabilities.

Preferred reporting methods:

1. Open a private GitHub Security Advisory for this repository.
2. If advisory flow is unavailable, contact project maintainers privately.

## What to Include in a Report

- Vulnerability type and impacted component(s)
- Reproduction steps or proof of concept
- Impact and exploitability assessment
- Suggested mitigation if available
- Logs/screenshots or request examples (redacted)

## Response Commitments

- Acknowledge receipt as quickly as possible
- Triage severity and impact
- Share remediation plan and expected timeline
- Coordinate disclosure after fix availability

## Scope Highlights

In-scope components include:

- API authentication (`X-API-Key`, `X-Internal-Token`)
- Job orchestration and callback pathways
- Secrets/config handling (`.env`, Docker/K8s manifests)
- Storage/log/metrics endpoints and exposure

Out of scope:

- Findings requiring unrealistic local attacker control
- Vulnerabilities in unsupported forks or heavily modified deployments

## Secret and Credential Handling

- Never commit real credentials.
- Use `.env` for local placeholders only.
- Use Kubernetes Secrets or managed secret stores in shared environments.
- Rotate credentials immediately when exposure is suspected.

## Hardening Recommendations

- Replace static API keys with managed authn/authz in production.
- Restrict dashboard/admin credentials and rotate defaults.
- Limit network exposure of internal ports and callback endpoints.
- Enable centralized audit logs and alerting.
- Use least-privilege IAM and RBAC for storage and Kubernetes access.
