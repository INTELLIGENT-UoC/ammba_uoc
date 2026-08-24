# CLAUDE.md

This file is read by Claude Code at the start of every session in this repo.

**Primary onboarding document: [AGENTS.md](AGENTS.md).** Read it first — it has
the project map, conventions, "how to make changes safely" recipes, and what
not to break. Everything below is Claude-Code-specific guidance only.

**Before changing anything touching the GSY integration, read
`INTEGRATION_NOTES.md`** (a local, gitignored working file — present on the
maintainer's checkout, not in the public tree). It lists every provisional
decision (transport, pool representation, identifiers, units, calibration
assumptions, proposed ontology extensions) and exactly where in the code to
change each one when GSY / Energy Web answer.

## Work tracking (ticket system)

- **GitHub Issues is the ticket system for this repo.** All engineering TODOs,
  blockers, and roadmap items live there — never in TODO comments or scratch
  files.
- **Milestones map the roadmap:** `v1.x staging integration` →
  `v2.0 settlement` → `backlog`. The `blocked-external` label marks items
  waiting on an upstream project (gateway fix, id-mapping, contract freeze);
  everything else is actionable now.
- **Claude session workflow:** run `gh issue list` when picking up work or
  reporting status; open an issue for any new TODO you discover instead of
  leaving it in prose; reference issues from commits/PRs (`Closes #N`); comment
  and close when state changes (e.g. an external blocker lifts). Keep the board
  truthful — it is the single source of "what is still to do".
- **This is a public repository:** issue wording stays strictly technical.
  Consortium-internal matters never go into issues; they belong in the local
  notes file.

## Tool preferences in this repo

- Use **`uv run`** to invoke Python tools — both services are uv-managed.
  `uv run pytest`, `uv run uvicorn`, etc. Don't activate `.venv` manually.
- Use **`npx hardhat`** for contract work — don't install Hardhat globally.
- Use **`docker compose`** (v2 syntax, not `docker-compose`).

## Where to look first for each kind of task

| Task | Open this file |
|---|---|
| Change the clearing pipeline | [`amm-clearing-node/src/clearing.py`](amm-clearing-node/src/clearing.py) |
| Change the wire format (orders/trades) | [`amm-clearing-node/src/adapters.py`](amm-clearing-node/src/adapters.py) + [`schemas/intelligent/`](amm-clearing-node/schemas/intelligent) |
| Validate against the ontology | [`amm-clearing-node/src/ontology.py`](amm-clearing-node/src/ontology.py) |
| Change the price function | [`amm-clearing-node/src/sigmoid.py`](amm-clearing-node/src/sigmoid.py) |
| Test end-to-end locally | [`amm-clearing-node/sim/`](amm-clearing-node/sim) (off-chain DB simulator) |
| Change the contract | [`amm-smart-contract/contracts/AMMContract.sol`](amm-smart-contract/contracts/AMMContract.sol) |
| Per-component dev guide | `<component>/AGENTS.md` |
| Algorithmic / data-model reference | [`ARCHITECTURE.md`](ARCHITECTURE.md) |

> `amm-execution-node` is the **v2 settlement engine** (skeleton; live
> execution pending GSY's contract freeze). Its penalty mechanism stays
> dormant inside it. `sigmoid.py` is still duplicated in both nodes — keep the
> copies in sync.

## Verification before claiming a task is done

For every change, run the relevant test command (see AGENTS.md "How to verify
your change" table). If you change something that crosses components (e.g.
both clearing and execution sigmoid), run **both** test suites. Don't claim
"done" without a green test run.

## Things Claude often gets wrong here

- **The wire format is the flat `int.*` ontology** (`schemas/intelligent/`), not
  the AMM's internal dicts. Orders in, trades out, and the clearing result all
  follow the camelCase, EUR/kWh, ISO-8601, UUID `int.*` schemas. The old nested
  `bid_component`/`offer_component` trade shape (and `trade_builder.py`) is
  retired. Convert at the `adapters.py` boundary; never leak internal names
  (`energy`, `energy_rate`, `status`, nested `requirements`) onto the wire.
- **Trade IDs are deterministic `uuid5`** (`adapters.trade_uuid`), not blake2b.
  Don't reintroduce blake2b hashing for trade/order IDs.
- **Validation is dependency-free on purpose** (`src/ontology.py`). Don't pull in
  `jsonschema`; extend the small validator if a schema feature is missing.
- **Prices cross the boundary in EUR/kWh; the sigmoid runs in ct/kWh.** The
  `CT_PER_EUR` conversion lives only in `adapters.py` — keep it there.
- **`marketId`/IDs are UUIDs on the `int.*` wire.** The `0x`-prefixed bytes32
  form is only the on-chain settlement / CGW query-payload path; don't conflate
  the two.
- **Don't add new top-level dependencies casually** — uv.lock changes require
  thought and a regenerated lockfile.
