# CLAUDE.md

@AGENTS.md

AGENTS.md, imported above, is the canonical onboarding document: project map,
conventions, recipes and what not to break. This file adds Claude-Code-specific
guidance only. Maintainer-specific, git-ignored instructions live in
`CLAUDE.local.md` when present.

## Work tracking (ticket system)

- **GitHub Issues is the ticket system for this repo.** All engineering TODOs,
  blockers and roadmap items live there, never in TODO comments or scratch
  files. Milestones group the issues; the `blocked-external` label marks items
  waiting on an upstream project.
- **Claude session workflow:** run `gh issue list` when picking up work or
  reporting status; open an issue for any new TODO you discover instead of
  leaving it in prose; reference issues from commits and PRs (`Closes #N`);
  comment and close when state changes. Keep the board truthful.
- **This is a public repository:** issue, commit and PR wording stays strictly
  technical.

## Tool preferences in this repo

- Use **`uv run`** to invoke Python tools; all Python components are
  uv-managed. `uv run pytest`, `uv run uvicorn`, etc. Don't activate `.venv`
  manually.
- Use **`npx hardhat`** for contract work; don't install Hardhat globally.
- Use **`docker compose`** (v2 syntax, not `docker-compose`).

## Where to look first for each kind of task

| Task                                    | Open this file                                                                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Change the clearing pipeline            | [`amm-clearing-node/src/clearing.py`](amm-clearing-node/src/clearing.py)                                                                   |
| Change the wire format (orders/trades)  | [`amm-clearing-node/src/adapters.py`](amm-clearing-node/src/adapters.py) + [`schemas/intelligent/`](amm-clearing-node/schemas/intelligent) |
| Validate against the ontology           | [`amm-clearing-node/src/ontology.py`](amm-clearing-node/src/ontology.py)                                                                   |
| Change the price function               | [`amm-clearing-node/src/sigmoid.py`](amm-clearing-node/src/sigmoid.py)                                                                     |
| Test end-to-end locally                 | [`amm-clearing-node/sim/`](amm-clearing-node/sim) (off-chain DB simulator)                                                                 |
| Change the contract                     | [`amm-smart-contract/contracts/AMMContract.sol`](amm-smart-contract/contracts/AMMContract.sol)                                             |
| Per-component dev guide                 | `<component>/AGENTS.md`                                                                                                                    |
| Mechanism, data model and configuration | [`docs/`](docs/index.md) (MkDocs site)                                                                                                     |

> `amm-execution-node` is the settlement engine (in development; live
> execution not yet enabled). Its penalty formulas are not yet wired into a
> data flow. `sigmoid.py` is duplicated in both nodes: keep the formula in
> sync.

## Verification before claiming a task is done

For every change, run the relevant test command (see AGENTS.md "How to verify
your change"). If you change something that crosses components (e.g. both
clearing and execution sigmoid), run **both** test suites. Documentation
changes need a green `mkdocs build --strict`. Don't claim "done" without a
green run.

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
  `CT_PER_EUR` conversion lives only in `adapters.py`; keep it there.
- **`marketId`/IDs are UUIDs on the `int.*` wire.** The `0x`-prefixed bytes32
  form is only the on-chain settlement / CGW query-payload path; don't conflate
  the two.
- **Docs notation follows the publication** ($\pi_t$, $K_{\mathrm{up}}$,
  $K_{\mathrm{lo}}$, $\Theta$, $B$); don't reintroduce $p_t$, $K_u$, $K_l$,
  $\theta$, $\beta$ in `docs/`.
- **Don't add new top-level dependencies casually**: uv.lock changes require
  thought and a regenerated lockfile.
