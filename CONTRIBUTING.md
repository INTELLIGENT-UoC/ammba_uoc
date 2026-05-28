# Contributing to AMMBA

Thanks for your interest. This document describes the development workflow.

## Workflow

We use **trunk-based development**:

1. Open an issue first for non-trivial changes so the approach can be discussed.
2. Branch off `main` with a descriptive name: `feat/sigmoid-cap`, `fix/vcg-rounding`, `docs/readme-arch`.
3. Open a Pull Request into `main`. CI must be green before merge.
4. Squash-merge by default. The PR title becomes the commit on `main` and feeds the changelog (see below).

Direct pushes to `main` are blocked by branch protection.

## Commit messages — Conventional Commits

PR titles (and commits on `main` after squash) **must** follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <description>
```

Allowed types and where they show up in release notes:

| Type        | Section in CHANGELOG  | Bumps version |
|-------------|-----------------------|---------------|
| `feat`      | Features              | minor         |
| `fix`       | Bug Fixes             | patch         |
| `perf`      | Performance           | patch         |
| `deps`      | Dependencies          | patch         |
| `refactor`  | Refactor              | patch         |
| `docs`      | Documentation         | patch         |
| `build`     | Build                 | patch         |
| `ci`        | (hidden)              | none          |
| `chore`     | (hidden)              | none          |
| `test`      | (hidden)              | none          |

Add `!` after the type, or `BREAKING CHANGE:` in the body, to trigger a major-version bump.

Examples:
```
feat(clearing): add steepness optimizer
fix(execution): correct VCG counterfactual when supply == demand
deps: bump web3 from 7.4 to 7.6
feat(contract)!: change clearMarket signature to take MarketResult struct
```

Optional scopes: `clearing`, `execution`, `contract`, `compose`, `ci`, `docs`.

## Releases — managed by release-please

You don't tag or write changelog entries manually. [release-please](https://github.com/googleapis/release-please) watches `main` and:

1. Opens a **Release PR** whenever there are unreleased Conventional Commits.
2. The PR updates `version.txt`, `.release-please-manifest.json`, and `CHANGELOG.md`.
3. When you merge the Release PR, it tags `vX.Y.Z` and creates a GitHub Release.

After tagging, manually bump matching versions in:
- `amm-clearing-node/pyproject.toml`
- `amm-execution-node/pyproject.toml`
- `amm-smart-contract/package.json`

(A follow-up automation can sync these — see open issues.)

## Local development

Install pre-commit hooks once:

```bash
pip install pre-commit
pre-commit install
```

Run the test suite for whichever component you touched:

```bash
# Clearing node
cd amm-clearing-node && uv sync --extra dev && uv run pytest -v

# Execution node
cd amm-execution-node && uv sync --extra dev && uv run pytest -v

# Smart contract
cd amm-smart-contract && npm ci && npx hardhat test
```

## Branch protection (maintainers)

The `main` branch should be protected via **Settings → Branches → Add rule**:

- Require a pull request before merging
- Require approvals: at least 1
- Dismiss stale reviews when new commits are pushed
- Require status checks to pass: select **CI** (the aggregate job from `ci.yml`)
- Require branches to be up to date before merging
- Require linear history
- Do not allow bypassing the above (off for admins as well, ideally)
- Block force pushes and deletions

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities. **Do not** open public issues for security problems.

## License

By contributing you agree that your contributions are licensed under **GPL-3.0-or-later**.
