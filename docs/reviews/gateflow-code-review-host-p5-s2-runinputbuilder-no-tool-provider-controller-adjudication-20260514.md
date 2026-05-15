# Host Phase 5 P5-S2 Code Review Controller Adjudication

- gate: Host Phase 5 P5-S2 code review adjudication
- slice: P5-S2 RunInputBuilder And No-tool Provider Boundary
- branch: `feat/host-phase5-local-dispatch`
- adjudication date: 2026-05-14
- design source: `docs/host/design.md` §23
- approved plan: `docs/host/phase5-runinputbuilder-local-dispatch-plan.md`

## Inputs

- implementation artifact: `docs/reviews/gateflow-implementation-host-p5-s2-runinputbuilder-no-tool-provider-20260514.md`
- code reviews:
  - `docs/reviews/gateflow-code-review-host-p5-s2-runinputbuilder-no-tool-provider-mimo-20260514.md`
  - `docs/reviews/gateflow-code-review-host-p5-s2-runinputbuilder-no-tool-provider-ds-20260514.md`

## Controller Judgment

P5-S2 is accepted for commit. Both reviewers found no blocking issue and independently reconfirmed validation.

The implementation satisfies the P5-S2 core boundary:

- current prompt is reconstructed from durable `USER_INPUT_ACCEPTED` only;
- continuity reads only canonical EventLog facts before the current Attempt boundary and orders by `event_sequence`;
- provider contracts are typed and do not introduce `Any` / `object` / untyped signatures;
- `AttemptDispatchSnapshot` carries durable identity refs, dispatch refs, policy snapshot ref, and cancellation token only;
- no-tool request constraints are enforced through `disable_tools=True`, `tool_schemas=()`, and `AgentPolicy.allow_tool_calls=False`;
- scheduler, LocalProxy, WorkerProxy, Engine dispatch, EngineEvent ingest, ToolRuntime, Memory, Context Governance, and real tool execution remain out of scope.

## Finding Disposition

| Finding | Controller disposition | Required action |
|---|---|---|
| MiMo findings | No findings | None |
| DS M1: SQL continuity reader includes failed/cancelled/lost events that currently project to `None` | Accepted as nonblocking observation. No correctness issue; JSON payload is not parsed for those events because `_continuity_message_from_event` returns before payload parsing for unprojected types. | No P5-S2 fix |
| DS L1: empty-check style mismatch | Rejected as incorrect premise. `dayu.host.api._require_non_empty` already uses `value.strip() == ""`, matching `PolicySnapshot` semantics. | None |
| DS L2: test token does not explicitly inherit `CancellationToken` | Accepted as nonblocking style observation. Structural Protocol typing is intentional and pyright validates the use site. | No P5-S2 fix |

## Validation

Controller validation:

```text
pytest tests/host/test_run_input_builder.py tests/host/test_package_exports.py tests/host/test_weak_typing_guard.py -q
11 passed in 0.26s

python -m pyright dayu/host tests/host
0 errors, 0 warnings, 0 informations

git diff --check
passed
```

Reviewer validation:

- MiMo reconfirmed 11 tests passed, pyright clean, diff check passed.
- DS reconfirmed 11 tests passed, pyright clean, diff check passed.

## Residual Risk Tracking

- Artifact-backed current prompt loading is not implemented in P5-S2; current builder requires durable `display_text`.
- Real Memory, compact artifact, ToolRuntime/tool schema providers remain Phase 9, Phase 10, and Phase 6 owners.
- LocalProxy / scheduler creation of real `AttemptDispatchSnapshot` remains P5-S3.

## Decision

P5-S2 is ready to commit as an accepted implementation slice after README synchronization.
