# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction Review (MiMo)

## 1. Review target and scope

- **Plan**: `docs/host/wu-semantic-ownership-01-r03-accepted-call-evidence-llm-projection-plan.md`
- **Correction artifacts**: `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-codex.md`, `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-adjudication.md`, `docs/reviews/wu-semantic-ownership-01-r03-s1-plan-correction-controller-validation.md`
- **Scope**: R03-S1 plan correction only — durable transition owner `run_transition.py` 扩边、source Attempt execution identity、WaitRecord/source Attempt 同源前置条件、mismatch no-partial-facts 测试。不涉及 S2/S3、Issue #177/#178 或 authorization。
- **Review posture**: adversarial — 尽力找出 plan 不应该交给 implementation agent 的最强证据。

## 2. Assumptions tested

| # | Assumption | Direct evidence source | Verdict |
|---|---|---|---|
| 1 | `_waiting_tool_result_event_request` 把 `execution_id` 硬编码为 `None` | `run_transition.py:3754` — `execution_id=None` | **Confirmed** |
| 2 | `_invalid_waiting_resolution_precondition` 未校验 `wait_record.execution_id == source_attempt.execution_id` | `run_transition.py:5299-5369` — 完整 precondition 无该检查 | **Confirmed** |
| 3 | `resume_run_from_waiting_in_transaction` 和 `_terminal_run_from_waiting_in_transaction` 都已读取 `source_attempt` | `run_transition.py:1771` 和 `run_transition.py:1931` | **Confirmed** |
| 4 | public `resolve_wait` 的 `_tool_result_resolution_payload` 会在调用 transition 前校验 execution 一致性 | `waiting.py:1862-1879` — `_wait_tool_call_requested_event` 校验 `awaiting.execution_id == wait_record.execution_id` 和 `row.execution_id == wait_record.execution_id` | **Confirmed** |
| 5 | `waiting.py::_accept_in_transaction` 已使用 shared writer `build_tool_call_requested_event_request` | `waiting.py:630-639` | **Confirmed** |
| 6 | `TOOL_AWAITING` payload 不含 `accepted_arguments`/`normalized_arguments_digest` 副本 | `waiting.py:2359-2376` — `tool_awaiting_payload` 参数不含这些字段 | **Confirmed** |
| 7 | `test_resolve_wait_command.py` 存在且包含 resume/terminal 测试 | 文件存在，`test_resolve_wait_completed_resumes_run_and_wakes_dispatch` 在 line 152 | **Confirmed** |
| 8 | S1 production allowlist 8 文件、test allowlist 9 文件、doc allowlist 2 文件 | Plan §6.2 | **Confirmed** — 与当前 dirty worktree 文件集合一致 |

## 3. Findings

无 material findings。以下为 review 过程中验证的非 blocker 观察：

### 观察 1: FK 约束假设

Plan §6.4 描述 mismatch fixture 时说"用该辅助 Attempt 的 execution id 把目标 `WaitRecord.execution_id` 改为满足 SQLite foreign key 但与 source Attempt 不同的值"。这假设 `host_wait_records.execution_id` 列存在指向 `host_attempts.execution_id` 的外键约束。若 FK 不存在，测试仍可工作（只是不需满足 FK），但 plan 描述会略有误导。这不是 blocker — implementation agent 在写 fixture 时会直接看到 schema 并适配。

### 观察 2: `RESUME_REQUESTED` 的 `execution_id=None`

`_resume_requested_event_request` (line 3723) 也把 `execution_id=None`。Plan 只修正 `TOOL_RESULT_ACCEPTED` 的 `execution_id`，不修正 `RESUME_REQUESTED`。这是合理的 — `RESUME_REQUESTED` 属于 resume 轮次的治理事实，其 execution identity 由 resume Attempt 持有，不属于 suspended source Attempt。Plan 的边界正确。

### 观察 3: `_waiting_tool_result_event_request` 签名变更可行性

Plan §6.3 第 11 点要求 `_waiting_tool_result_event_request` 以 typed 直接参数接收已校验的 `source_attempt: AttemptRow`。当前两个调用点（`resume_run_from_waiting_in_transaction` line 1789 和 `_terminal_run_from_waiting_in_transaction` line 1946）都已持有 `source_attempt`，签名变更无阻塞。

## 4. Architecture boundary review

- **Layering**: `run_transition.py` 是 `dayu/host/durable/` 下的低层 transition primitive，不打开事务、不做 admission policy、不做 public facade。修正只在该模块内部，不侵入 `waiting.py` 的 public service 层或 `tool_runtime.py` 的 accept boundary。
- **Ownership**: `TOOL_RESULT_ACCEPTED` 的 `execution_id` 语义 owner 是 durable transition writer，不是下游 consumer（`accepted_result_projection.py`）或上游 producer（`waiting.py`）。Plan 正确识别了 owner。
- **Dependency direction**: 修正不引入反向依赖。`run_transition.py` 不 import `waiting.py`；`waiting.py` 已 import `run_transition.py` 的 transition helpers。
- **Test boundary**: public `resolve_wait` 测试证明正常 producer identity；direct transition 测试证明 mismatch invariant。两层职责分离清晰，不互相替代。

## 5. Execution semantics review

- **Precondition ordering**: `_invalid_waiting_resolution_precondition` 在 `resume_run_from_waiting_in_transaction` (line 1773) 和 `_terminal_run_from_waiting_in_transaction` (line 1933) 中均在任何 `event_log_store.append_event` 之前调用。新增 `wait_record.execution_id == source_attempt.execution_id` 检查只需加入现有 precondition 函数，不影响 ordering。
- **No-partial-facts**: Plan 要求 mismatch 时返回 `INVALID_STATE` 且全表 snapshot 不变。当前 precondition 失败已直接返回 `WaitResolutionTransitionResult(status=INVALID_STATE, ...)`，不执行任何 append 或 state mutation。新增检查的行为一致。
- **Idempotency**: mismatch 不涉及幂等路径 — 它是 precondition 失败，不是已提交 fact 的重放。

## 6. Implementation sequencing review

- **Slice scope**: S1 只修正 durable transition writer 和对应测试，不触碰 S2 blacklist 删除或 S3 opaque-ref propagation。边界清晰。
- **最小 test file**: Plan 只选 `test_resolve_wait_command.py` 作为唯一必改 owner test file。这是正确的 — 该文件已包含 resume/terminal 测试，且是 wait resolution transition 的直接 owner test。
- **Strict consumer retention**: Plan 明确保留 `_request_row_matches_result` 的 strict equality、descriptor 冷热互斥 guard 和 governance-only `TOOL_AWAITING` fixture。这些是已 accepted 的 contract，不应因 transition correction 而放宽。

## 7. Validation completeness review

- **Coverage target**: `run_transition.py >=80%` 由 `test_resolve_wait_command.py` 加现有 `test_run_attempt_transitions.py` 执行。合理。
- **Pyright/ruff**: Plan §6.5 列出完整验证命令。
- **Diff/allowlist**: Plan §13.4 要求 `git diff --name-only` 与 exact allowlist 做集合比较。纠正后 S1 allowlist 只新增 `run_transition.py`。

## 8. Open questions

无。

## 9. Residual risks

| Risk | Handling | Owner |
|---|---|---|
| FK 约束是否存在于 `host_wait_records.execution_id` | implementation agent 写 fixture 时直接验证；若不存在则 fixture 不需满足 FK，测试逻辑不变 | implementation |
| real public-run smoke 依赖外部环境 | 不在 S1 scope；aggregate 时验证 | controller |

## 10. Conclusion

**PASS**

Plan correction 完整、可实施、边界清晰。所有核心假设均有直接代码证据支持。`_waiting_tool_result_event_request` 的 `execution_id=None` 硬编码和 `_invalid_waiting_resolution_precondition` 缺失 execution 同源检查均被直接源码确认。修正边界正确落在 durable transition writer owner，不侵入上游 producer 或下游 consumer。测试设计合理：public tests 证正常 identity，direct transition tests 证 mismatch invariant，两层职责分离。allowlist、coverage、stop conditions 均闭合。

无 material findings。Plan 可进入 implementation agent。
