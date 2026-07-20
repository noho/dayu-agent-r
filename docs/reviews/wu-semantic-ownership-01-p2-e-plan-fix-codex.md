# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-E`
- Gate: plan fix
- Input plan: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-controller-adjudication.md`
- Allowed edits:
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-fix-codex.md`

## First-Principles Check

Accepted findings do not overturn the plan's core motivation: the 7 failures are still classified as validation fallout from stale tests / fixtures against accepted production contracts. The required fix is to make the plan stricter before implementation, especially where a weak test migration could hide diagnostic gating loss, wait-resume identity loss, or invalid durable fixture semantics.

No production implementation was started in this gate.

## Findings Fixed

### P2E-PLAN-F01

Controller requirement: stream heartbeat test must prove both sides of the diagnostic gate.

Plan fix:

- Promoted ordinary `logging.DEBUG` negative assertion from evidence note to required implementation assertion.
- Required positive assertion that `STREAM_DEBUG_LOG_LEVEL` captures `runner.stream_idle.heartbeat`.
- Required preserving bytes-not-dropped coverage.
- Explicitly prohibited changing `runner.py` or raising production heartbeat log level to make the stale test pass.

Owner boundary:

- Diagnostic-level truth remains `dayu.runtime.log_levels.STREAM_DEBUG_LOG_LEVEL`.
- Test alignment owner remains `tests/engine/runners/openai/test_stream_idle.py`.

### P2E-PLAN-F02

Controller requirement: wait-resume implementation must first diagnose `resume_request.messages`, then assert protocol identity closure on normal path.

Plan fix:

- Made `resume_request.messages` diagnosis the first Slice E2 wait-resume step.
- Required normal-path assertion order: `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`.
- Required `AssistantToolCall.id == original awaiting tool_call_id`.
- Required `ToolMessage.tool_call_id == AssistantToolCall.id`.
- Required fixture/request atom repair first if only current Chinese fallback guidance appears.
- Required stopping and escalating to production owner if old English guidance appears.

Owner boundary:

- Awaiting request atom and accepted result truth remain Host durable / awaiting accept owner facts.
- LLM-facing resume projection remains `dayu/host/run_input.py`.
- Integration assertion / fixture repair remains `tests/host/test_phase7_waiting_integration.py` unless old English guidance proves a production owner regression.

### P2E-PLAN-F03

Controller requirement: purge fixture must use dedicated cancel request EventLog event id and check `cancelled` coverage.

Plan fix:

- Required a dedicated cancel request EventLog row / event id for the fixture.
- Explicitly rejected reusing arbitrary existing events as `cancel_request_event_id`.
- Required checking whether `cancelled` appears in the relevant parametrize set.
- Required applying the same durable invariant fix for `cancelled` if covered.

Owner boundary:

- Durable invariant remains `dayu/host/durable/schema.py`.
- Fixture repair remains `tests/host/test_purge_session.py`.

### P2E-PLAN-F04

Controller requirement: E2 split policy must be explicit if wait-resume diagnosis triggers production owner.

Plan fix:

- Added Slice E2 stop-condition split policy.
- If wait-resume escalates to production owner, Host export / purge fixture alignment must proceed as an independent alignment slice.
- Wait-resume must then move into a production-owner follow-up slice.

Owner boundary:

- Host export snapshot and purge fixture alignment remain test-owner work.
- Wait-resume production regression, if proven, belongs to `dayu/host/run_input.py` / awaiting accept path and must not be hidden by fixture assertions.

### P2E-PLAN-F05

Controller requirement: implementation closeout must record export snapshot propagation.

Plan fix:

- Added closeout requirement to explicitly record that Engine projection export snapshot alignment and Host `HostThinkingView` export snapshot alignment are tests aligning to existing design / README public contracts.
- Added that no production or README change is required for those snapshot alignments unless implementation discovers a real contract change.

Owner boundary:

- Engine public contract truth remains `docs/engine/design.md` and `dayu.engine` exports.
- Host public contract truth remains `dayu/host/README.md`, `dayu.host.api`, and `dayu.host` exports.

## Re-review Focus

Re-review should verify:

- F01 is no longer optional evidence; both positive and negative stream heartbeat assertions are implementation requirements.
- F02 requires first-step message diagnosis and closes tool-call identity through both assistant and tool messages.
- F03 requires a dedicated cancel request event id and covers `cancelled` if parametrized.
- F04 defines the split policy before implementation begins.
- F05 is represented as an implementation closeout requirement.

## Validation

Required command for this plan-fix gate:

```bash
git diff --check
```

Result: passed.
