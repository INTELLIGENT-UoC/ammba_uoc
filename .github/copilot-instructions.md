# GitHub Copilot instructions — AMMBA

The canonical onboarding document for this repo is [`AGENTS.md`](../AGENTS.md).
Please read it first. The summary below is the minimum context.

## Project summary

AMMBA is a P2P energy market mechanism and an alternative matching engine for
the GSY DEX. It runs periodic batch auctions: orders are collected during a
15-minute slot, a sigmoid-based uniform clearing price is computed from the
supply/demand ratio, and quantities are allocated pro-rata through an AMM pool.
It consumes and produces the GSY DEX `int.*` ontology objects.

## Components

- `amm-clearing-node/` — **(v1)** Python 3.12+, FastAPI, `uv`. Clearing pipeline
  in `src/clearing.py`; `int.*` ↔ internal translation in `src/adapters.py`.
- `amm-smart-contract/` — Solidity 0.8.24, Hardhat 2. On-chain audit anchor.
- `amm-execution-node/` — **(deferred)** Penalties; not part of the v1 MVP.

Each component has a more detailed `AGENTS.md` in its directory.

## Conventions Copilot should follow

- Use `uv` for Python dependency and command running.
- Use `npx hardhat` for contract commands.
- The service is **fully async** — use `async`/`await` and `httpx.AsyncClient`,
  never `requests` or blocking I/O.
- The wire format is the `int.*` ontology (`amm-clearing-node/schemas/intelligent/`):
  flat, camelCase, EUR/kWh, ISO-8601, UUIDs. Translate only in `src/adapters.py`;
  never propose leaking internal field names onto the wire (schemas are
  `additionalProperties: false`).
- Trade IDs are deterministic `uuid5` (`adapters.trade_uuid`), not blake2b.
- Prices: internal ct/kWh, wire EUR/kWh — convert via `CT_PER_EUR` in `adapters.py`.
- All on-chain numeric values are scaled by `NODE_FLOAT_SCALING_FACTOR = 10000`.
- Validate against the schemas with `src/ontology.py` (no `jsonschema` dependency).
- Configuration is loaded from `configuration.yaml` + env-var overrides via
  `src/config.py`. Don't hard-code values.

## Commit messages

This repo uses [Conventional Commits](https://www.conventionalcommits.org/).
Allowed types: `feat`, `fix`, `perf`, `deps`, `refactor`, `docs`, `build`,
`ci`, `chore`, `test`. Optional scopes: `clearing`, `execution`, `contract`,
`compose`, `ci`, `docs`. Add `!` for breaking changes.

## Testing

Suggest test changes alongside code changes. Test layout:
`amm-*-node/tests/test_<module>.py` mirroring `src/<module>.py`.
Contract tests live in `amm-smart-contract/test/`.
