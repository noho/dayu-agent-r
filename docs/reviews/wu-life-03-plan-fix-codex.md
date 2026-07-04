# WU-LIFE-03 Plan Fix Codex

## Scope

- Work unit: WU-LIFE-03 Active cancel watchdog and post-cancel timeout
- Gate: plan fix
- Plan artifact fixed: `docs/host/wu-life-03-active-cancel-watchdog-plan.md`
- Fix artifact: `docs/reviews/wu-life-03-plan-fix-codex.md`
- Validation: `git diff --check`

This plan-fix pass edited only the plan artifact and this fix artifact. No production code, tests, README, control doc, GitHub issue, commit, push, or PR work was performed.

## Changed Plan Sections

- `First-principles Judgment And Direct Code Evidence`: added direct evidence for late terminal ingest behavior and recovery scanner conflict with `CANCELLING`.
- `Affected Files / Modules`: added `dayu/host/recovery.py` and the recovery test owner because the accepted reopen finding requires scanner/watchdog ownership changes.
- `Contract / Schema / State-machine / Public-interface Changes`: added watchdog interval ownership, additive payload compatibility, public projection validation, and `dispatch_record_id` source.
- `Implementation Decisions`: added deterministic tick + cancel wakeup + periodic SQL scan model, injectable UTC clock policy, independent timeout closeout input/helper, explicit late terminal reject/diagnostic rules, and recovery/watchdog startup ordering.
- `Implementation Slices`: added concrete durable/ingest tests for late final/failure/suspend after `RUN_CANCELLING`, SQL scan tests for zero/one/multiple cancelling runs, clean-close-reopen owner `STOPPED`, crash/inconclusive reopen, and watchdog-disabled recovery behavior.
- `Tests / Validation Commands And Expected Assertions`: added expected assertions for late terminal rules, SQL scan coverage, public projection compatibility, and clean-close-reopen not becoming `LOST`.
- `Risks / Open Questions`: added cross-instance UTC clock skew and watchdog-disabled opt-out residual risks with owner/destination.

## Finding-by-finding Fix Mapping

| Finding | Final status | Fix summary |
| --- | --- | --- |
| F01 Recovery scanner and active cancel watchdog reopen ordering | 已修复 | Plan now defines enabled-watchdog ownership of accepted-cancel `CANCELLING` runs, startup tick before recovery scan, recovery deferral for remaining accepted-cancel `CANCELLING`, clean-close owner `STOPPED`, crash/inconclusive orphan, and watchdog-disabled behavior. |
| F02 Late terminal race after `RUN_CANCELLING` | 已修复 | Plan now cites current ingest/precondition evidence and explicitly requires `final_answer` and `run_failed` after `RUN_CANCELLING` to be rejected with diagnostic and no canonical terminal, while `run_suspended` / `tool_awaiting` stay waiting-confirmation rejected diagnostics. |
| F03 Watchdog scheduling model | 已修复 | Plan now requires deterministic `tick(now)`, cancel-commit wakeup, and periodic fallback scan; interval owner defaults to existing `dispatch_poll_interval_seconds`, and interval only affects detection latency. |
| F04 Clock policy | 已修复 | Plan now requires injectable UTC now provider for watchdog tests, production comparison against durable UTC timestamps plus Host UTC now, and records cross-instance clock skew as residual risk. |
| F05 Diagnostic payload mapping | 已修复 | Plan now requires independent `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_in_transaction(...)`, reuses row CAS helpers, and defines `dispatch_record_id` as dispatch-record lookup by attempt id. |
| F06 Payload compatibility/projection validation | 已修复 | Plan now states timeout fields are additive, must not replace existing consumed payload fields, and adds public watcher/projection validation after timeout `RUN_CANCELLED`. |
| F07 Watchdog scan strategy | 已修复 | Plan now requires SQL scan of durable current `CANCELLING` runs, forbids in-memory tracking set, and adds zero/one/multiple cancelling run validation. |

## Validation Run

```bash
git diff --check
```

Result: passed with no output.

## Blocking Open Questions

None.

## Residual Risks

| Risk | Owner / destination |
| --- | --- |
| Timeout `CANCELLED` does not physically stop provider/tool work; old side effects may continue outside Host. | WU-TOOLS-CANCEL-01 |
| Timeout default value needs production tuning across providers and local/remote worker backends. | Host runtime config follow-up under GitHub Issue #87 |
| Cross-instance reopen compares durable UTC timestamp from one instance with current UTC clock from another; clock skew may make timeout detection early or late by the skew amount. | Host lifecycle watchdog runtime tuning under GitHub Issue #87 |
| Watchdog-disabled assembly is an explicit special/test opt-out; orphaned `CANCELLING` runs can still follow recovery `LOST` / inconclusive behavior instead of timeout `CANCELLED`. | Host runtime assembly policy under GitHub Issue #87 |
| Host-only timeout cannot diagnose the exact blocked boundary such as HTTP abort vs tool subprocess hang. | WU-TOOLS-CANCEL-01 and Tool Trace diagnostics lane #70 / #34 / #119 / #71 |
| WU-WAIT-04 still needs product-level E2E confirmation of user-visible cancel recovery. | WU-WAIT-04 after WU-LIFE-03 and WU-TOOLS-CANCEL-01 |
