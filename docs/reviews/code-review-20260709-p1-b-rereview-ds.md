# WU-SEMANTIC-OWNERSHIP-01 P1-B Fix Re-Review — AgentDS

## 审查范围

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: fix re-review
- 审查对象：仅 accepted code review findings 的 fix，不重新扩大到整个 umbrella WU
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-codex.md`
- Fix controller validation: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-controller-validation.md`
- 原 DS review: `docs/reviews/code-review-20260709-p1-b-ds.md`
- MiMo review: `docs/reviews/code-review-20260709-181830-p1-b-mimo.md`

## Accepted Finding 逐项验证

### P1B-CODE-ACCEPTED-F01 — Watchdog helper docstrings ✅ FIXED

- **文件/行号**: `dayu/host/durable/run_transition.py:4373,4427,4479`
- **验证**: 三个 helper 函数（`_active_watchdog_attempt_cancelled_event_request`、`_active_watchdog_run_cancelled_event_request`、`_active_watchdog_cancelled_payload`）的 `cancel_request_event_id` 参数 docstring 均已更新为"来自 typed ``RunRow.cancel_request_event_id`` 的 ``CANCEL_REQUESTED`` event id；调用方已校验它引用同一 Run 的 ``CANCEL_REQUESTED``，不是从 ``RUN_CANCELLING`` payload 解析"。
- **确认**: docstring 与实现一致。调用方（line 2351, 2363）确实从 `read_cancel_requested_event_from_run_link` 获取 typed link 后传入。✅

### P1B-CODE-ACCEPTED-F02 — Schema CHECK 防御测试 ✅ FIXED

- **文件/行号**: `tests/host/test_state_schema.py:398-434`
- **验证**: `test_cancel_acceptance_status_requires_cancel_request_event_id` 参数化覆盖 `RunStatus.CANCELLING` 和 `RunStatus.CANCELLED`。测试逻辑：
  1. 通过 `_insert_run_tx` 写入合法 CANCELLING/CANCELLED Run row（含 `cancel_request_event_id`）
  2. 执行 `UPDATE host_runs SET cancel_request_event_id = NULL` 清空 typed link
  3. 断言 `HostDurableError` 且 message 匹配 `"CHECK constraint"`
- **测试有效性**: 该测试验证的是 fresh-schema DDL CHECK 约束（`status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL`）在 SQLite 层的强制执行，不是测试实现细节或 implementation accident。测试通过，220 passed。✅

### P1B-CODE-ACCEPTED-F03 — Implementation artifact 记录 tool_trace expansion ✅ FIXED

- **文件/行号**: `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md:44`
- **验证**: artifact 已新增明确记录："`tool_trace.py` now observes the shared Host lifecycle event set from `dayu.host.lifecycle_events`. This intentionally expands the older local subset to the complete Host lifecycle event set so Tool Trace uses the same lifecycle semantics as other Host projections."
- **代码验证**: `tool_trace.py:218` 的 `_CANONICAL_EVENT_TYPES` 确实使用 `*event_type_values(HOST_RUN_LIFECYCLE_EVENT_TYPES)` 展开完整 lifecycle event set。✅

### P1B-CODE-ACCEPTED-F04 — `cancel_cancelling_run_row` docstring 文档化 link 保留语义 ✅ FIXED

- **文件/行号**: `dayu/host/durable/state.py:3482-3484`
- **验证**: docstring 已新增明确说明："``cancel_request_event_id`` 在 Run 进入 ``CANCELLING`` 时已经固定；schema 保证 ``CANCELLING`` row 必须持有该 typed cancel link。本 mutator 只写入 terminal refs 与 ``CANCELLED`` 状态，保留原有 cancel link。"
- **实现确认**: UPDATE SET 子句确实不包含 `cancel_request_event_id`，依赖 CANCELLING 状态进入时 `mark_run_cancelling_row` 写入的值。当前语义正确（CHECK 约束保证 CANCELLING row 必有该字段）。✅

## 范围外检查

### Fix 是否引入超出 accepted scope 的 runtime 语义变更？

- **F01**: 仅 docstring，无 runtime 变更。✅
- **F02**: 仅测试，无 production code 变更。✅
- **F03**: 仅 artifact，无 code 变更。✅
- **F04**: 仅 docstring，无 runtime 变更。✅

**结论**: fix 未引入任何 runtime 语义变更。所有 production code diff 均为 docstring 修改，不改变行为。

### 是否重新争论 rejected/deferred finding？

- **Rejected F01/F02（非 CANCELLED terminal 必须清除 cancel link）**: fix 未实现此要求，未在 docstring 或测试中重新争论该立场。✅
- **Deferred F03（read_api 常量清理）**: `read_api.py` 未被修改。✅

### 新测试是否有效且不测试 implementation accident？

`test_cancel_acceptance_status_requires_cancel_request_event_id` 测试的是 SQLite DDL CHECK 约束的强制执行——这是一个 schema-level invariant，属于 durable schema owner boundary。测试不依赖任何内部实现细节（不依赖特定函数签名、不依赖 transaction runner 内部状态、不依赖 mock）。该测试验证的是"向 CANCELLING/CANCELLED Run row 写入 NULL cancel_request_event_id 会被拒绝"这一公共契约，是有效的防御深度测试。✅

## 验证结果

```
pytest tests/host/test_durable_schema.py tests/host/test_state_schema.py \
  tests/host/test_run_attempt_transitions.py tests/host/test_engine_ingest_mapping.py \
  tests/host/test_recovery_scan.py tests/host/test_outbox_durable.py -x -q
-> 220 passed in 1.89s

pyright -> 0 errors, 0 warnings, 0 informations

git diff --check -> passed
```

## Residual Risks

无新增 residual risk。四个 accepted finding 全部关闭，fix 均为文档/测试/artifact 层变更，不改变 runtime 行为。P1-B 实现层面已有的 residual risks（stress_support.py 终端 tuple 残留、CANCELLING → LOST stale link 测试缺口、schema 版本升级无兼容迁移）已在原 AgentDS review 和 MiMo review 中记录，fix 未扩大或缩小这些风险。

## 结论: **PASS**

P1-B 四个 accepted code review findings 均已正确修复：
- F01: watchdog docstrings 不再错误描述 payload 解析来源
- F02: schema CHECK 防御有显式回归测试覆盖
- F03: implementation artifact 记录了 tool_trace lifecycle event-set expansion
- F04: `cancel_cancelling_run_row` docstring 文档化了 typed link 保留语义

Fix 未引入 runtime 语义变更，未重新争论 rejected/deferred finding，新测试有效且不测试 implementation accident。P1-B 可进入下一 gate。

---

*AgentDS re-review completed 2026-07-09. No blocking finding. P1-B fix gate passes.*
