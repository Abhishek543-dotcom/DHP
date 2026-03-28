# Contributing

Thanks for your interest in improving Lakehouse Platform.

## Getting Started

1. Fork the repository and create a feature branch.
2. Copy `.env.example` to `.env` and set local values.
3. Start local infrastructure:
   - `cd infra`
   - `docker-compose -f docker-compose.dev.yaml up -d`
4. Run tests before opening a PR:
   - `make test`

## Development Guidelines

- Prefer small, focused pull requests.
- Add tests for behavior changes.
- Keep API contracts backward compatible where possible.
- Never commit secrets or credentials.

## Pull Requests

A good PR includes:
- Problem statement and proposed solution.
- Testing notes (commands and outputs).
- Any migration or deployment considerations.

## Code of Conduct

By participating, you agree to follow the project's Code of Conduct.
