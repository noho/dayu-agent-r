# WU-SEMANTIC-OWNERSHIP-01 P1-B Plan Fix Narrow Re-Review (AgentMiMo)

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P1-B`
- Gate: plan fix narrow re-review
- Reviewer: AgentMiMo
- Date: 2026-07-09
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-b-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-plan-review-controller-adjudication.md`
- Initial review artifacts: `docs/reviews/plan-review-20260709-p1-b-mimo.md`, `docs/reviews/plan-review-20260709-p1-b-ds.md`

## Conclusion

**pass**

All controller accepted findings P1B-PLAN-F01..F06 are closed. The fix artifact accurately reflects the plan changes, and no new blockers were introduced.

---

## Controller Accepted Findings Closure Status

### P1B-PLAN-F01: S0 design truth update 具体结构

- **Status**: closed
- **Controller required fix**:
  1. Specify where in `docs/host/design.md` the design update should land, or require S0 artifact to record the final insertion location.
  2. Specify the minimum structure: Host terminal/lifecycle event set, public outbox terminal item set, and non-public terminal fact skip/diagnostic behavior.
  3. Explicitly contrast `RUN_LOST` read model / Read API / HostEvent projection as `lost` terminal with Outbox skip behavior.
- **Plan verification** (lines 187-191):
  - ✓ Line 187: "优先在 `docs/host/design.md` 的状态迁移 terminal facts 表之后，或 Durable Store / EventLog / Outbox ownership 段落之后写入设计真源"
  - ✓ Line 187: "若 implementation 选择其它等价位置，S0 implementation artifact 必须记录最终插入位置、章节标题和选择理由"
  - ✓ Lines 188-191: 要求最小三段结构（Host terminal / lifecycle event set、Public outbox terminal item set、Non-public terminal fact skip / diagnostic behavior）
  - ✓ Line 191: 明确对比 `RUN_LOST` 在 Read Model / Read API / HostEvent 中投影为 `lost` terminal，与 Outbox skip / diagnostic behavior
- **Residual risk**: final wording still depends on S0 implementation, but the artifact must record insertion location and can be re-reviewed against the minimum structure.

### P1B-PLAN-F02: terminal helper `str` vs `HostRunEventType` API 决策

- **Status**: closed
- **Controller required fix**:
  1. State whether helper functions accept raw EventLog `str` event types or typed `HostRunEventType`.
  2. If accepting `str`, document that this is because EventLog rows expose strings and helper performs parse/classification internally.
  3. If requiring `HostRunEventType`, require callers to parse first and include parse behavior in the plan.
- **Plan verification** (lines 116-126):
  - ✓ Lines 116-119: 函数签名明确使用 `str` 参数类型
  - ✓ Lines 125-126: 明确选择理由——EventLog rows、projection filters、SQL `IN` 参数、HostEvent projection 和 diagnostics 当前暴露 durable strings；若强制每个消费者先 parse，会把同一 parse/classification 责任分散回消费者
  - ✓ Line 125: 明确 `lifecycle_events.py` 在 helper 内部完成 parse / classification：合法 Run lifecycle string 映射为 `HostRunEventType`；未知或非 Run event string 返回 `None` / `False`
  - ✓ Line 126: `HostRunEventType` 仍是 helper 内部集合和新生产代码使用的 typed source-of-truth；`event_type_values(...)` 是唯一允许把 typed tuple 转成 string tuple 的 helper
- **Residual risk**: implementation must ensure docstrings state this behavior; this is now part of the plan contract.

### P1B-PLAN-F03: durable/outbox latest public terminal sequence 使用 shared public set

- **Status**: closed
- **Controller required fix**:
  1. Explicitly require `durable/outbox.py` to use `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` or `event_type_values(...)`.
  2. Prohibit a second local public outbox terminal tuple in `durable/outbox.py`.
  3. Add tests/validation for "latest public terminal sequence is not advanced by `RUN_LOST`".
- **Plan verification** (lines 221, 229-230, 238):
  - ✓ Line 221: "durable/outbox.py latest public terminal sequence 必须使用 `lifecycle_events.PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` 的字符串值形式或 `event_type_values(PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES)`"
  - ✓ Line 221: "不得包含 `RUN_LOST`，也不得在 `durable/outbox.py` 保留第二份本地 public outbox terminal tuple"
  - ✓ Line 229: "latest public terminal sequence 不被 lost 推进到需要 item 的位置"
  - ✓ Line 230: "Durable outbox projection state 覆盖 `RUN_LOST` 在最新 EventLog sequence 后出现时，latest public terminal sequence 仍停留在最近一个 public outbox terminal item event，不能产生 'checkpoint 落后但无 item 可投递' 的假 lag"
  - ✓ Line 238: S1 Validation 包含 `pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py`
- **Residual risk**: actual test filenames may need adjustment during implementation if the repository uses different outbox test file names; the required coverage is now explicit.

### P1B-PLAN-F04: outbox tests + `event_payload_object(...RUN_CANCELLING...)` residual scan

- **Status**: closed
- **Controller required fix**:
  1. Add outbox/durable-outbox focused tests to S1 validation.
  2. Add `event_payload_object(...RUN_CANCELLING...)` residual scan or an equivalent `rg` pattern.
  3. State allowed matches if any remain only for audit/diagnostic paths, not critical cancel closeout.
- **Plan verification** (lines 238, 288):
  - ✓ Line 238: S1 Validation 包含 `pytest tests/host/test_outbox*.py tests/host/test_durable_outbox*.py`
  - ✓ Line 288: S2 Validation regex 包含 `event_payload_object\\(.*RUN_CANCELLING`
  - ✓ S2 明确了 allowed matches 仅限 "一次性 audit / diagnostic / historical payload readability 路径"，禁止 "active watchdog、engine ingest cooperative cancel、dispatch linked cancel、recovery accepted-cancel 等 critical closeout 路径"
- **Residual risk**: residual scan is grep-based and must be interpreted by reviewer; the allowed/forbidden classification is now explicit.

### P1B-PLAN-F05: direct cancel typed-link stop condition

- **Status**: closed
- **Controller required fix**:
  1. Add stop condition for direct cancel paths where `cancel_request_event_id` cannot be safely written for some Run state and cannot be fixed by transition ordering.
- **Plan verification** (line 293):
  - ✓ Line 293: S2 stop condition 包含 "发现 queued / accepted / waiting / pre-worker direct cancel 路径在某些 Run 状态下无法安全写入 `cancel_request_event_id`，且不能通过调整 transition 顺序或同事务 row mutation 解决"
- **Residual risk**: implementation must still prove each direct cancel path writes the typed link through focused tests.

### P1B-PLAN-F06: non-terminal lifecycle constants residual 分类

- **Status**: closed
- **Controller required fix**:
  1. Add residual classification for non-terminal lifecycle constants such as `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, and `RUN_RECOVERING`.
  2. Clarify whether P1-B's proposed `HostRunEventType` is only a current helper owner for touched Run lifecycle/terminal consumers or a full migration target with deferred consumers.
- **Plan verification** (line 387):
  - ✓ Line 387: Residual risks 明确分类 "Non-terminal Run lifecycle constants such as `RUN_ACCEPTED`、`RUN_QUEUED`、`RUN_STARTED`、`RUN_WAITING`、`RUN_CANCELLING`、`RUN_RECOVERING`"
  - ✓ Line 387: "P1-B only migrates touched consumers that need the shared lifecycle helper for terminal/read-model/tool-trace/outbox semantics"
  - ✓ Line 387: "P1-B does not promise a repository-wide migration of every non-terminal lifecycle constant consumer; if `HostRunEventType` becomes the universal Run event string owner in a later work unit, those deferred consumers must be migrated there"
- **Residual risk**: follow-up work may still be needed for a universal Run event string ownership migration; this is classified as deferred, not hidden.

---

## Fix Artifact Verification

The fix artifact `docs/reviews/wu-semantic-ownership-01-p1-b-plan-fix-codex.md` accurately reflects all plan changes:

- ✓ P1B-PLAN-F01 fix status and plan changes match lines 187-191
- ✓ P1B-PLAN-F02 fix status and plan changes match lines 116-126
- ✓ P1B-PLAN-F03 fix status and plan changes match lines 221, 229-230, 238
- ✓ P1B-PLAN-F04 fix status and plan changes match lines 238, 288
- ✓ P1B-PLAN-F05 fix status and plan changes match line 293
- ✓ P1B-PLAN-F06 fix status and plan changes match line 387
- ✓ Propagation audit in fix artifact is consistent with plan section 12

---

## New Blocker Check

No new blockers introduced by the fix:

- The fix only enhanced plan precision and implementation-readiness
- The fix did not change the architecture direction or owner boundary decisions
- The fix did not introduce new stop conditions that would prevent implementation

---

## Residual Risks (Inherited from Plan)

1. Final wording of S0 design truth update depends on implementation; artifact must record insertion location.
2. Implementation must ensure helper docstrings state `str` parameter behavior.
3. Actual outbox test filenames may need adjustment during implementation.
4. Residual scan for `event_payload_object(...RUN_CANCELLING...)` is grep-based and must be interpreted by reviewer.
5. Implementation must prove each direct cancel path writes the typed link through focused tests.
6. Non-terminal lifecycle constants migration is deferred to a later work unit if `HostRunEventType` becomes universal.

---

## Validation

```bash
git diff --check
```

Result: pass (no tracked files modified).

---

## Summary

All six controller accepted findings (P1B-PLAN-F01..F06) are closed. The plan fix artifact accurately documents the changes, and no new blockers were introduced. The plan is ready to proceed to P1-B implementation.
