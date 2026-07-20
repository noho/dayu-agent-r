# WU-SEMANTIC-OWNERSHIP-01 P2-B Plan Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-B`
- Gate: plan validation before review
- Plan artifact: `docs/host/wu-semantic-ownership-01-p2-b-plan.md`
- Plan delivery artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-plan-codex.md`

## Motivation Check

P2-B motivation remains valid, with one important narrowing:

- MiMo 08 remains a real Host terminal answer continuity / projection boundary issue because current code still describes and implements descriptor-backed final answer hydration by mutating a transient payload view.
- MiMo 09 remains real because Host import-boundary helper ignores `ast.ImportFrom` with `node.level > 0`.
- MiMo 12 remains real only as test fixture hardening. Current direct evidence supports `snapshot_digest="pending"` in compact material / RunInputBuilder tests, not broad production memory corruption.

The plan correctly keeps severity at P2 and does not expand into Conversation Memory redesign.

## Owner Boundary Validation

The plan identifies the right owners:

- Engine emits final answer events, but Host EngineEvent ingest / terminal closeout owns durable terminal facts.
- Conversation Memory is a read model and must not make mutated payload views look like canonical EventLog truth.
- RunInputBuilder consumes durable facts / memory snapshot / resolver material and must not expose refs, digests, or Host governance text.
- `tests/host/test_import_boundary.py` owns AST dependency scan semantics.
- tests-only memory snapshot factories own snapshot / cursor / digest construction for Host memory-related tests.

## Plan Completeness

The plan includes:

- direct evidence for all three findings;
- accepted / narrowed finding disposition;
- allowed files/modules;
- explicit non-goals and stop conditions;
- a one-slice implementation strategy with justification;
- validation commands for import-boundary, memory projection, run input, compact material, pyright, and `git diff --check`;
- propagation audit expectations;
- README trigger checks for `dayu/host/README.md` and `tests/README.md`.

## Controller Notes For Reviewers

Reviewers should challenge these points:

- Whether MiMo 08 can be safely fixed by resolver typed material without changing durable terminal payload schema.
- Whether the plan's "one slice" is still appropriate given it includes design truth, production projection code, import-boundary tests, and fixture factory migration.
- Whether relative import resolution can be implemented deterministically from scanned file path and package root without adding a fragile custom import resolver.
- Whether direct memory consumer descriptor-blind behavior plus durable projection / RunInputBuilder equivalence tests fully cover final answer continuity.
- Whether moving `"pending"` sentinel into a tests helper is enough, or whether the plan should require an explicit source scan assertion.

## Validation

- `git diff --check`
  - Result: passed

No production tests or pyright are required for this planning-only gate because only docs/control artifacts changed.

## Verdict

Ready for AgentMiMo / AgentDS plan review.
