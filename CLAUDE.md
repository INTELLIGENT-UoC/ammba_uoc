# CLAUDE.md

This file is read by Claude Code at the start of every session in this repo.

**Primary onboarding document: [AGENTS.md](AGENTS.md).** Read it first — it has
the project map, conventions, "how to make changes safely" recipes, and what
not to break. Everything below is Claude-Code-specific guidance only.

## Tool preferences in this repo

- Use **`uv run`** to invoke Python tools — both services are uv-managed.
  `uv run pytest`, `uv run uvicorn`, etc. Don't activate `.venv` manually.
- Use **`npx hardhat`** for contract work — don't install Hardhat globally.
- Use **`docker compose`** (v2 syntax, not `docker-compose`).

## Where to look first for each kind of task

| Task | Open this file |
|---|---|
| Change the clearing pipeline | [`amm-clearing-node/src/clearing.py`](amm-clearing-node/src/clearing.py) |
| Change the price function | [`amm-clearing-node/src/sigmoid.py`](amm-clearing-node/src/sigmoid.py) **and** [`amm-execution-node/src/sigmoid.py`](amm-execution-node/src/sigmoid.py) (kept in sync) |
| Change penalties | [`amm-execution-node/src/penalties.py`](amm-execution-node/src/penalties.py) |
| Change the contract | [`amm-smart-contract/contracts/AMMContract.sol`](amm-smart-contract/contracts/AMMContract.sol) |
| Per-component dev guide | `<component>/AGENTS.md` |
| Algorithmic / data-model reference | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

## Verification before claiming a task is done

For every change, run the relevant test command (see AGENTS.md "How to verify
your change" table). If you change something that crosses components (e.g.
both clearing and execution sigmoid), run **both** test suites. Don't claim
"done" without a green test run.

## Things Claude often gets wrong here

- **Don't flatten the trade schema** — the nested
  `bid.bid_component`/`offer.offer_component` shape is required by the
  GSY DEX off-chain DB.
- **Don't break hash determinism** — `json.dumps(..., sort_keys=True)` is
  load-bearing in `trade_builder.py:blake2b_hash`.
- **Don't drop the `0x` prefix** on blake2b hashes or bytes32 market IDs.
- **Don't add new top-level dependencies casually** — uv.lock changes require
  thought and a regenerated lockfile.
