# WU-SEMANTIC-OWNERSHIP-01 P1-B Fix Re-review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-B`
- Gate: fix re-review
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-codex.md`
- Fix controller validation: `docs/reviews/wu-semantic-ownership-01-p1-b-fix-controller-validation.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-p1-b-code-review-controller-adjudication.md`
- Accepted findings: `P1B-CODE-ACCEPTED-F01` through `P1B-CODE-ACCEPTED-F04`
- Rejected/deferred scope: not re-argued per adjudication instruction

## Verification Method

逐一检查每个 accepted finding 的 fix 是否落地，fix 是否引入超出 accepted scope 的 runtime semantic change，新增测试是否有效且不依赖实现偶然性。

## Finding Verification

### P1B-CODE-ACCEPTED-F01 — Watchdog helper docstrings

- **要求**: 三个 watchdog helper 的 `cancel_request_event_id` 参数 docstring 不得再声称来自 `RUN_CANCELLING` payload 解析。
- **验证**: `dayu/host/durable/run_transition.py` diff 确认三处 docstring 已更新：
  - `_active_watchdog_attempt_cancelled_event_request` (L4370 area)
  - `_active_watchdog_run_cancelled_event_request` (L4423 area)
  - `_active_watchdog_cancelled_payload` (L4475 area)
- **新文本**: "来自 typed `RunRow.cancel_request_event_id` 的 `CANCEL_REQUESTED` event id；调用方已校验它引用同一 Run 的 `CANCEL_REQUESTED`，不是从 `RUN_CANCELLING` payload 解析。"
- **判定**: ✅ closed。docstring 准确反映当前 typed-link 数据流。

### P1B-CODE-ACCEPTED-F02 — SQLite CHECK regression test

- **要求**: 新增 focused test 证明 fresh-schema `host_runs` row 以 `status='cancelling'` 或 `status='cancelled'` 且 `cancel_request_event_id=NULL` 写入时被 SQLite CHECK 拒绝。
- **验证**: `tests/host/test_state_schema.py` 新增 `test_cancel_acceptance_status_requires_cancel_request_event_id`。
  - 使用 `@pytest.mark.parametrize("status", (RunStatus.CANCELLING, RunStatus.CANCELLED))` 覆盖两个状态。
  - 通过已有 `_insert_run_tx` helper 写入合法行（含 `cancel_request_event_id`），然后执行 `UPDATE ... SET cancel_request_event_id = NULL` 触发 CHECK。
  - 断言 `pytest.raises(HostDurableError, match="CHECK constraint")`。
- **有效性**: 测试验证的是 schema 级不变量（SQLite DDL CHECK），不依赖 Python 代码路径偶然性。即使未来 Python 层 mutator 重构，只要 schema CHECK 存在，此测试仍有效。
- **验证结果**: 2 passed（cancelling + cancelled 各 1）。
- **判定**: ✅ closed。测试有效，不测试实现偶然性。

### P1B-CODE-ACCEPTED-F03 — Implementation artifact tool_trace expansion 记录

- **要求**: implementation artifact 必须记录 `tool_trace.py` 从旧 local subset 扩展到完整 Host lifecycle event set 是 intentional P1-B semantic convergence。
- **验证**: `docs/reviews/wu-semantic-ownership-01-p1-b-implementation-codex.md` Implementation Notes 段已包含：
  > `tool_trace.py` now observes the shared Host lifecycle event set from `dayu.host.lifecycle_events`. This intentionally expands the older local subset to the complete Host lifecycle event set so Tool Trace uses the same lifecycle semantics as other Host projections.
- **判定**: ✅ closed。该文本在 P1-B 实现已存在，fix artifact 正确记录了此点。

### P1B-CODE-ACCEPTED-F04 — `cancel_cancelling_run_row` docstring

- **要求**: docstring 必须记录 `cancel_request_event_id` 在 Run 进入 `CANCELLING` 时已固定，schema 保证 `CANCELLING` row 持有该 link，mutator 在关闭到 `CANCELLED` 时保留该 link。
- **验证**: `dayu/host/durable/state.py` diff 确认 `cancel_cancelling_run_row` docstring 新增段落：
  > `cancel_request_event_id` 在 Run 进入 `CANCELLING` 时已经固定；schema 保证 `CANCELLING` row 必须持有该 typed cancel link。本 mutator 只写入 terminal refs 与 `CANCELLED` 状态，保留原有 cancel link。
- **判定**: ✅ closed。docstring 准确描述了 CANCELLING→CANCELLED preservation invariant。

## Runtime Semantic Change Check

本次 fix 范围内的变更：

| Finding | 变更类型 | Runtime semantic change |
|---|---|---|
| F01 | docstring 更新 | 无 |
| F02 | 新增测试 | 无 |
| F03 | implementation artifact 更新 | 无 |
| F04 | docstring 更新 | 无 |

Fix artifact 声明 "This fix does not change runtime semantics"，经验证成立。Fix 未引入：
- 新的 runtime compatibility path
- 下游 special case
- 被 adjudication 拒绝的 non-cancelled-link invariant

## Test Validity

`test_cancel_acceptance_status_requires_cancel_request_event_id` 的验证逻辑：

1. 通过 `_insert_run_tx` 写入合法 CANCELLING/CANCELLED row（含 typed cancel link 和对应 `CANCEL_REQUESTED` event）。
2. 执行 `UPDATE host_runs SET cancel_request_event_id = NULL WHERE run_id = ?` 清除 link。
3. 断言 SQLite `IntegrityError`（被 HostDurableStore 包装为 `HostDurableError`），匹配 "CHECK constraint"。

该测试验证 DDL 级约束，不依赖任何 Python 层实现路径。即使未来 Python mutator 重构，只要 `host_runs` 表保留 `status NOT IN ('cancelling', 'cancelled') OR cancel_request_event_id IS NOT NULL` CHECK，此测试仍有效。不测试实现偶然性。

## Validation

- `pytest tests/host/test_state_schema.py` → 37 passed
- `pytest tests/host/test_durable_schema.py` → 36 passed
- `pytest tests/host/test_state_schema.py::test_cancel_acceptance_status_requires_cancel_request_event_id` → 2 passed（cancelling + cancelled）
- `pyright` → 0 errors, 0 warnings, 0 informations

## Residual Risks

无新发现。原 review residual risks 不变：
- `tests/host/stress_support.py` terminal tuple 残留（deferred test support）。
- `cancel_cancelling_run_row` 不显式写入 `cancel_request_event_id`（依赖 CANCELLING 状态已有值，当前正确）。
- 无 CANCELLING→LOST stale link 测试（production 路径不走此分支）。

## Rejected / Deferred Findings 确认

未重新论证以下 adjudicated 决策：
- 非 CANCELLED terminal Runs 不必清除/拒绝 cancel link（rejected，P1-B plan 允许 LOST 保留 link 作为 diagnostic correlation）。
- `read_api.py` 非 terminal constant cleanup（deferred 到后续 WU）。

## Conclusion

**pass**

四个 accepted finding 全部 closed：
- F01: docstring 已修正，准确反映 typed-link 数据流。
- F02: 新增 schema 级 CHECK 回归测试，有效且不依赖实现偶然性。
- F03: implementation artifact 已记录 tool_trace lifecycle event set 扩展。
- F04: docstring 已记录 CANCELLING→CANCELLED link preservation invariant。

Fix 未引入超出 accepted scope 的 runtime semantic change。新增测试有效。
