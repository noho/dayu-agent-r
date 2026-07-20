# WU-SEMANTIC-OWNERSHIP-01 P3-K Goal Confirmation

## Work Unit

- Umbrella: `WU-SEMANTIC-OWNERSHIP-01`
- Sub work unit: `P3-K - Test harness semantic coupling cleanup`
- Work unit type: semantic ownership / test-contract hardening follow-up
- Entry source: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Current gate: goal confirmation
- Next gate: plan by AgentCodex

## Motivation Check

The motivation is valid.

P3-K is not a request to weaken tests. The issue is that some tests and test helpers have become parallel owners of production semantics:

- exact dataclass field-set locks can make tests a schema registry even when the public contract is owner-level required fields or wire values;
- raw SQL helpers can duplicate recovery, liveness, checkpoint, or EventLog semantics that should be owned by production durable APIs or focused diagnostic helpers;
- fake implementations can mirror production schema too tightly and fail before the real public contract fails;
- cancellation test doubles are split across Host / Engine / Service with subtly different timestamp and method semantics;
- LLM-facing tests sometimes assert exact wording where only required semantic content is the contract.

This is a real semantic ownership risk because it can cause future production-contract changes to be blocked or guided by test fixtures rather than production owners.

## Direct Evidence

Source findings accepted in round2 adjudication:

- `TF-1`: exact field-set tests in `tests/host/test_memory_projection.py`, `tests/engine/test_engine_event_contract.py`, and `tests/contracts/test_tool_result_envelope.py`.
- `TF-2`: raw SQL helpers in `tests/host/public_smoke_support.py`, `tests/host/recovery_support.py`, and `tests/host/stress_support.py`.
- `TF-3`: test fakes coupled to production memory / compaction vNext schemas in `tests/host/fake_compaction.py` and `tests/host/memory_snapshot_factories.py`.
- `TF-4`: multiple cancellation fake implementations in `tests/host/fake_cancellation.py`, `tests/engine/runners/openai/_fakes.py`, and `tests/service/test_fins_direct.py`.
- `TF-5`: exact LLM-facing text assertions in `tests/host/test_run_input_builder.py` and `tests/host/test_memory_projection.py`.

## Owner Boundary

- Production code owns production semantics, public contracts, durable schema, EventLog facts, memory / compaction shapes, cancellation protocol, and LLM-facing content rules.
- Tests own verification of behavior and regression surfaces.
- Test helpers may provide diagnostics and fixtures, but they must not become independent truth sources for production schema, recovery state, or LLM wording unless the exact shape is explicitly public contract.

## Success Signals

- Each TF finding is classified as `accepted`, `rejected-with-reason`, `deferred-with-owner`, or `needs-more-evidence` against current code.
- The plan slices are based on semantic owner boundaries, not on reviewer IDs or file count.
- Exact field-set assertions are retained only where exact public / wire contract is the intended promise.
- Raw SQL is removed or narrowed where production query helpers exist; any remaining raw SQL is documented as diagnostic-only or corruption-test setup.
- Cancellation fakes converge on a protocol-faithful test helper where practical.
- LLM-facing tests assert required semantic content unless exact wording is the contract.
- Changes must preserve or improve test coverage and must pass pyright.

## Non-goals

- Do not rewrite all tests mechanically.
- Do not weaken tests to accept incorrect production behavior.
- Do not change production contracts solely to satisfy tests.
- Do not fix unrelated pre-existing production bugs discovered while reading tests; route them to a follow-up owner unless they are directly caused by P3-K changes.
- Do not enter P3-K implementation before a reviewed, code-generation-ready plan is accepted.

## Blocking Questions

None. The next gate is a scoped P3-K plan by AgentCodex.
