# Contributing to DataHarbour Project (DHP)

Thanks for contributing. This guide keeps contributions consistent, reviewable, and production-safe.

## 1. Before You Start

- Read `README.md`, `docs/architecture.md`, and `docs/runbook.md`.
- Check open issues/PRs to avoid duplicate effort.
- For larger changes, open an issue first to align on scope.

## 2. Local Development Setup

```bash
cp .env.example .env
make build-spark
make up
```

Optional service-local development:

```bash
cd services/job-service && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8001
cd services/metadata-service && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8002
cd services/log-service && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8003
cd services/storage-service && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8004
```

## 3. Branch and Commit Guidelines

Recommended branch naming:

- `feature/<short-description>`
- `fix/<short-description>`
- `chore/<short-description>`

Commit guidance:

- Keep commits focused and atomic.
- Use clear imperative subject lines.
- Avoid bundling refactors with behavior changes unless necessary.

## 4. Coding Standards

- Keep APIs backward compatible whenever possible.
- Prefer explicit error handling with actionable messages.
- Keep configuration in environment variables.
- Do not hardcode secrets, tokens, or credentials.
- Update docs for behavior, API, config, or ops changes.

## 5. Testing Requirements

Run tests before opening a PR:

```bash
make test
```

When relevant, also validate:

- Endpoint behavior in Swagger (`/docs`)
- End-to-end flows using Postman collection in `docs/postman/`
- Observability panels and target health in Grafana/Prometheus

## 6. Pull Request Expectations

A good PR includes:

- Clear problem statement
- What changed and why
- Validation evidence (commands + outcome)
- Risk and rollback notes for operational changes
- Linked issue(s)

Use the PR template and fill all sections.

## 7. Documentation Expectations

Update markdown docs when you change:

- API routes, payloads, status codes, auth headers
- Runtime behavior (job lifecycle, retries, callbacks)
- Infrastructure (compose, k8s, observability)
- New runbook procedures or troubleshooting guidance

## 8. Security and Responsible Disclosure

If you find a vulnerability, do not open a public issue.

- Follow `SECURITY.md`
- Use private disclosure channels first

## 9. Community Standards

By participating, you agree to follow `CODE_OF_CONDUCT.md`.
