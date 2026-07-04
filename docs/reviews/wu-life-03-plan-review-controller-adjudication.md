# WU-LIFE-03 Plan Review Controller Adjudication

## Scope

- Work unit: WU-LIFE-03 Active cancel watchdog and post-cancel timeout
- Gate: plan review
- Plan artifact: `docs/host/wu-life-03-active-cancel-watchdog-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260704-105429.md`
  - `docs/reviews/plan-review-20260704-105503.md`
- Controller decision timestamp: 20260704-105721

## Overall Decision

Plan review does not pass yet. The plan direction is aligned with Host / Engine design truth, but accepted findings require a plan fix before implementation.

The material root issue is that the plan promises reopen timeout closeout for `CANCELLING` runs while existing startup recovery can process the same runs first. The plan must decide the ownership and ordering between startup recovery and active cancel watchdog instead of leaving it to implementation.

## Finding Adjudication

### F01: Recovery scanner and watchdog reopen ordering

- Sources:
  - MiMo Finding 01: reopen path recovery scanner / watchdog interaction unspecified.
  - DS Finding 01: `StartupRecoveryScanner` may mark clean-close `CANCELLING` runs `LOST` before watchdog sees them.
- Decision: accepted.
- Reason: Both reviewers cite direct code evidence from `open_host.py`, `recovery.py`, and `recovery_process.py`. The finding affects the plan's claimed success signal and would cause an implementation agent to choose a state-machine policy during implementation.
- Required plan fix:
  - Explicitly define the ordering and ownership between startup recovery and active cancel watchdog for `CANCELLING` runs.
  - Decide whether watchdog scan runs before recovery scan, recovery scanner skips/delegates `CANCELLING`, or recovery scanner invokes the timeout closeout policy.
  - Cover both clean-close-reopen owner `STOPPED` and crash/inconclusive orphan scenarios.
  - Define behavior when watchdog is disabled by configuration.
  - Add validation that clean-close-reopen cannot convert accepted cancel into `LOST` before timeout policy is applied.

### F02: Late terminal race behavior after `RUN_CANCELLING`

- Source: DS Finding 02.
- Decision: accepted.
- Reason: The plan currently says implementation tests should document actual behavior. That is not code-generation-ready for a lifecycle state machine. The plan must state expected accept/reject rules based on current ingest code evidence or explicitly require a narrow implementation change.
- Required plan fix:
  - Read and cite existing ingest behavior for `final_answer`, `run_failed`, and `run_suspended` after `RUN_CANCELLING`.
  - Explicitly state whether each is accepted, rejected, or mapped to diagnostic/no canonical terminal.
  - Add focused validation for final answer, failure, and suspended/awaiting late arrivals after cancel.

### F03: Watchdog tick / poll scheduling model

- Source: DS Finding 03.
- Decision: accepted.
- Reason: Timeout semantics require a concrete trigger model. Leaving event-based wakeup vs periodic scan vs hybrid to implementation risks either lost wakeups or unnecessary runtime complexity.
- Required plan fix:
  - Choose a scheduling model. Preferred direction is a deterministic tick method plus hybrid runtime: wake on cancel commit and periodic fallback scan.
  - Define interval ownership and default / test override policy.
  - State that interval affects detection latency, not the timeout threshold.

### F04: Clock source and deterministic tests

- Sources:
  - MiMo Finding 02: clock source not a positive implementation requirement.
  - DS Finding 04: cross-instance clock skew residual risk.
- Decision: accepted.
- Reason: Deterministic timeout tests and reopen behavior require explicit clock policy. Cross-instance skew does not block the current work unit but must be recorded as bounded residual risk.
- Required plan fix:
  - Add injectable clock / now provider as an implementation requirement for watchdog tests.
  - State production timeout comparison uses durable UTC event timestamps plus current Host UTC clock.
  - Add cross-instance clock skew as a residual risk with owner / destination under Host lifecycle watchdog runtime tuning.

### F05: Timeout diagnostic payload mapping

- Sources:
  - MiMo Finding 03: relation between new timeout input and existing `ActiveCancelCloseoutInput` unclear.
  - DS Finding 06: `dispatch_record_id` source not defined.
- Decision: accepted.
- Reason: The plan must be directly implementable. Timeout closeout lacks Engine event fields, so it needs a distinct input/helper shape and explicit dispatch record lookup.
- Required plan fix:
  - Specify an independent `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_in_transaction`.
  - Reuse existing row CAS helpers, but build timeout-specific EventLog event requests.
  - State `dispatch_record_id` comes from existing dispatch record lookup by attempt id.

### F06: Payload compatibility and public projection validation

- Source: DS Finding 05.
- Decision: accepted.
- Reason: SQLite schema remains unchanged, but EventLog payload shape changes can still affect projections. Additive payload fields are likely safe, but the plan should require projection/watch validation.
- Required plan fix:
  - Add validation that timeout `RUN_CANCELLED` still projects to public cancelled HostEvent / Run snapshot correctly.
  - Add a note that diagnostic fields are additive and must not replace existing payload fields consumed by read/projection/outbox paths.

### F07: Watchdog scan query ownership and efficiency

- Source: MiMo Finding 04.
- Decision: accepted.
- Reason: This is low severity, but a simple direction prevents overengineering. Existing wait poller pattern supports SQL scan without adding in-memory ownership state.
- Required plan fix:
  - Prefer SQL scan of current `CANCELLING` runs over a new in-memory tracking set.
  - Add validation for zero, one, and multiple `CANCELLING` runs.

## Residual Risk Decisions

- Provider/tool physical interruption remains deferred-with-owner to WU-TOOLS-CANCEL-01.
- Product-level user-visible cancel recovery remains deferred-with-owner to WU-WAIT-04.
- Timeout defaults and clock skew are deferred-with-owner to Host lifecycle watchdog runtime tuning under GitHub Issue 87, but the current plan must record the bounded risk and include deterministic tests.
- Tool Trace detailed blocked-boundary diagnostics remain deferred-with-owner to WU-TOOLS-CANCEL-01 and the Tool Trace diagnostics lane.

## Next Gate

Proceed to plan fix. AgentCodex must update only `docs/host/wu-life-03-active-cancel-watchdog-plan.md` and may create a plan-fix artifact under `docs/reviews/`. No implementation, code changes, commits, pushes, PRs, or GitHub comments are allowed.
