# GitHub Copilot instructions — AMMBA

The canonical onboarding document for this repo is [`AGENTS.md`](../AGENTS.md).
Please read it first. The summary below is the minimum context.

## Project summary

AMMBA is a P2P energy market mechanism for the Energy Web Chain. It runs
periodic batch auctions: orders are collected during a 15-minute slot, a
sigmoid-based uniform clearing price is computed from the supply/demand
ratio, and quantities are allocated pro-rata through an AMM pool. After
delivery, an execution node computes VCG-style penalties for deviations.

## Components

- `amm-smart-contract/` — Solidity 0.8.24, Hardhat 2. On-chain audit anchor.
- `amm-clearing-node/` — Python 3.13, FastAPI, `uv`. Clearing pipeline in
  `src/clearing.py`.
- `amm-execution-node/` — Python 3.13, FastAPI, `uv`. Penalties in
  `src/penalties.py`.

Each component has a more detailed `AGENTS.md` in its directory.

## Conventions Copilot should follow

- Use `uv` for Python dependency and command running.
- Use `npx hardhat` for contract commands.
- Python services are **fully async** — use `async`/`await` and
  `httpx.AsyncClient`, never `requests` or blocking I/O.
- All on-chain numeric values are scaled by `NODE_FLOAT_SCALING_FACTOR = 10000`.
- Trade `_id` is `"0x" + blake2b-256(json.dumps(trade, sort_keys=True))`. The
  `sort_keys=True` is essential — never remove it.
- Trade objects use a **nested** `bid.bid_component` / `offer.offer_component`
  schema. Don't propose flat alternatives.
- The sigmoid module is deliberately duplicated between the two Python
  services. Update both when you change one.
- Configuration is loaded from `configuration.yaml` + env-var overrides via
  `src/config.py` in each service. Don't hard-code values.

## Commit messages

This repo uses [Conventional Commits](https://www.conventionalcommits.org/).
Allowed types: `feat`, `fix`, `perf`, `deps`, `refactor`, `docs`, `build`,
`ci`, `chore`, `test`. Optional scopes: `clearing`, `execution`, `contract`,
`compose`, `ci`, `docs`. Add `!` for breaking changes.

## Testing

Suggest test changes alongside code changes. Test layout:
`amm-*-node/tests/test_<module>.py` mirroring `src/<module>.py`.
Contract tests live in `amm-smart-contract/test/`.
