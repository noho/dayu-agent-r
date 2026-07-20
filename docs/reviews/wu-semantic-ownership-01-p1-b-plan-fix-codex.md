# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan Fix

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-B`
- Gate: plan fix
- Agent: AgentCodex
- Date: 2026-07-09
- Target plan: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-review-controller-adjudication.md`

## Scope

本轮只修 plan artifact，并新增本 plan-fix artifact。未修改生产代码、未修改 tests、未提交、未 push。

## First-principles judgment

Controller 接受的 P1B-PLAN-F01..F06 都是 plan 精度与 implementation-readiness 问题，不是对 P1-B 动机或架构方向的否定。问题真实存在：若 plan 不明确 design truth 落点、helper API 边界、durable outbox public set 真源、validation residual scan、direct cancel stop condition 与 non-terminal lifecycle residual 分类，后续 implementation agent 仍可能在 owner boundary 外重建语义或漏测关键路径。

## Fix status

### P1B-PLAN-F01: S0 design truth update is not concrete enough

- Status: fixed.
- Plan changes:
  - S0 now requires the design update to land after the `docs/host/design.md` state-transition terminal facts table, or after the Durable Store / EventLog / Outbox ownership section.
  - If implementation chooses another equivalent location, the S0 artifact must record the final insertion location, section title, and rationale.
  - S0 now requires a minimum three-part structure: Host terminal / lifecycle event set, public outbox terminal item set, and non-public terminal fact skip / diagnostic behavior.
  - S0 explicitly contrasts `RUN_LOST` as `lost` terminal in Read Model / Read API / HostEvent with Outbox skip / diagnostic behavior.
- Modified location: `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `S0. Design truth update`.
- Residual risk: final wording still depends on S0 implementation, but the artifact must record insertion location and can be re-reviewed against the minimum structure.

### P1B-PLAN-F02: Terminal helper API needs explicit `str` vs `HostRunEventType` decision

- Status: fixed.
- Plan changes:
  - The plan now explicitly chooses raw EventLog `str` for mapping / predicate helper parameters.
  - Rationale: EventLog rows, projection filters, SQL `IN` parameters, HostEvent projection, and diagnostics currently expose durable strings; requiring each consumer to parse first would decentralize parse/classification responsibility.
  - `lifecycle_events.py` owns parse / classification internally: known Run lifecycle strings map to `HostRunEventType`; unknown or non-Run strings return `None` / `False`.
  - `HostRunEventType` remains the typed source-of-truth for helper-owned sets and new production code, with `event_type_values(...)` as the only string tuple projection helper.
- Modified location: `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `5.1 Terminal helper`.
- Residual risk: implementation must ensure docstrings state this behavior; this is now part of the plan contract.

### P1B-PLAN-F03: durable/outbox latest public terminal sequence must consume shared public set

- Status: fixed.
- Plan changes:
  - S1 now explicitly requires `dayu/host/durable/outbox.py` latest public terminal sequence to use `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` or `event_type_values(PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES)`.
  - S1 forbids a second local public outbox terminal tuple in `durable/outbox.py`.
  - S1 expected tests now require a scenario where `RUN_LOST` appears after the latest public outbox terminal item and does not advance latest public terminal sequence or create false lag.
  - Full validation now includes outbox / durable-outbox test commands.
- Modified locations:
  - `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `S1. Terminal event/status contract helper`.
  - `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `9. Validation commands`.
- Residual risk: actual test filenames may need adjustment during implementation if the repository uses different outbox test file names; the required coverage is now explicit.

### P1B-PLAN-F04: Validation must include outbox tests and RUN_CANCELLING residual scan

- Status: fixed.
- Plan changes:
  - S1 validation now includes `pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py`.
  - Full implementation validation now includes the same outbox-focused test command.
  - S2 now requires auditing `event_payload_object(...RUN_CANCELLING...)` residual calls.
  - The plan states allowed matches are limited to audit / diagnostic / historical payload readability paths, and forbidden matches include active watchdog, engine ingest cooperative cancel, dispatch linked cancel, and recovery accepted-cancel critical closeout paths.
  - Validation regex now includes `event_payload_object\\(.*RUN_CANCELLING`.
- Modified locations:
  - `docs/host/wu-semantic-ownership-01-p1-b-plan.md` sections `S1`, `S2`, and `9. Validation commands`.
- Residual risk: residual scan is grep-based and must be interpreted by reviewer; the allowed/forbidden classification is now explicit.

### P1B-PLAN-F05: Direct cancel typed-link stop condition is missing

- Status: fixed.
- Plan changes:
  - S2 stop condition now covers queued / accepted / waiting / pre-worker direct cancel paths where `cancel_request_event_id` cannot be safely written for some Run state and cannot be fixed by transition ordering or same-transaction row mutation.
- Modified location: `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `S2. Cancellation durable linkage`.
- Residual risk: implementation must still prove each direct cancel path writes the typed link through focused tests.

### P1B-PLAN-F06: Non-terminal lifecycle constants need explicit residual classification

- Status: fixed.
- Plan changes:
  - Residual risks now classify non-terminal lifecycle constants such as `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_WAITING`, `RUN_CANCELLING`, and `RUN_RECOVERING`.
  - P1-B only migrates touched consumers that need the shared lifecycle helper for terminal / read-model / tool-trace / outbox semantics.
  - P1-B does not promise a repo-wide migration of every non-terminal lifecycle constant consumer. If `HostRunEventType` later becomes the universal Run event string owner, deferred consumers belong to a later work unit.
- Modified location: `docs/host/wu-semantic-ownership-01-p1-b-plan.md` section `11. Stop conditions / residual risks`.
- Residual risk: follow-up work may still be needed for a universal Run event string ownership migration; this is classified as deferred, not hidden.

## Propagation audit

- Design truth path: P1-B now requires `docs/host/design.md` to state Host terminal set, public outbox terminal item set, and non-public terminal skip/diagnostic behavior before implementation.
- Terminal helper path: EventLog string facts enter `lifecycle_events.py` helper parse/classification; projections and durable outbox consume helper-owned sets or string values derived from helper-owned sets.
- Durable/outbox path: latest public terminal sequence is tied to `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES`, so `RUN_LOST` remains Host terminal truth without becoming public outbox item truth.
- Cancel linkage path: S2 continues to move critical cancel linkage to typed Run state; residual `RUN_CANCELLING` payload reads are explicitly allowed only for non-critical audit/diagnostic readability.
- Residual constants path: non-terminal lifecycle constants outside touched consumers are explicitly deferred rather than silently left as an inconsistent partial migration.

## Validation

Ran:

```bash
git diff --check
```

Result: pass.

## Completion status

Plan fix complete. All accepted controller findings P1B-PLAN-F01..F06 have a corresponding plan change and residual-risk classification.
