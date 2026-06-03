# full-repo-review-fix-round-1 Codex 修复报告

## Scope

- Gate: `full-repo-review-fix-round-1`
- 输入 artifact:
  - `docs/reviews/repo-review-20260602-221156.md`
  - `docs/reviews/repo-review-20260602-221158.md`
- 执行约束：仅处理 controller 已裁决范围；未 commit、未 push、未开 PR。

## Changed Files

- `dayu/contracts/tool_await.py`
- `dayu/contracts/tool_schema.py`
- `dayu/contracts/tool_call.py`
- `dayu/engine/runners/openai/runner.py`
- `dayu/host/durable/state.py`
- `dayu/host/admission.py`
- `dayu/host/durable/transaction.py`
- `dayu/engine/README.md`
- `dayu/host/README.md`
- `tests/README.md`
- `tests/contracts/test_tool_call.py`
- `tests/contracts/test_tool_schema.py`
- `tests/contracts/test_tool_outcome_exhaustive.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`
- `tests/host/test_run_attempt_transitions.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_admission_queue.py`
- `tests/host/test_durable_transaction.py`

## Accepted Fixes

1. `ToolAwaitSpec` / `ToolAwaitSnapshot` datetime 边界
   - 直接证据：`ToolAwaitSpec.__post_init__` 原先只校验 `await_kind` 与 `resume_token`；`ToolAwaitSnapshot.__post_init__` 原先只校验 `snapshot_id`。
   - 修复：`deadline is not None` 时、`captured_at` 必须是 timezone-aware datetime；补中文 docstring 异常说明。
   - 测试：新增 naive / aware datetime 构造测试，并同步既有 snapshot 测试数据为 aware datetime。

2. `ToolParametersSchema.properties` key 与截断策略映射
   - 直接证据：`ToolParametersSchema.__post_init__` 原先不遍历 `properties` key；`truncate_limit_key_for_strategy` 原先直接索引映射，缺映射时泄漏 `KeyError`。
   - 修复：拒绝空白 property key；未知策略映射抛 `ValueError`；`ToolTruncateSpec` 复用同一 helper，避免同类路径语义分叉。
   - 测试：新增空白 property key、全 enum 映射覆盖和缺映射 `ValueError` 测试。

3. `GeminiToolCallState.thought_signature`
   - 直接证据：dataclass 原先无 `__post_init__`，空白签名可构造。
   - 修复：新增构造期校验，拒绝空白 `thought_signature`。
   - 测试：新增空白签名拒绝测试。

4. OpenAI-compatible Runner SSE Content-Type 分流与 pending readany 清理
   - 直接证据：`_is_sse_response` 原先对非 JSON Content-Type 走 SSE，`text/plain` / `application/octet-stream` 会被送入 SSE parser；`_cancel_pending_readany` 对已完成 task 直接返回，不消费异常。
   - 修复：只把大小写不敏感的 `text/event-stream` media type 视为 SSE；保留缺失 Content-Type 的现有 fallback；已 done task 调用 `pending.exception()` 消费异常。
   - 测试：更新 Content-Type 分流测试，保留缺失 Content-Type fallback 集成测试；新增 done task 异常消费测试。

5. `terminal_attempt_row` terminal refs CAS 守卫
   - 直接证据：`cancel_running_attempt_row` 同类 active attempt 终态写入包含 `_TERMINAL_REFS_UNSET_WHERE_SQL`，`terminal_attempt_row` 原先缺失。
   - 修复：`terminal_attempt_row` 的 CAS WHERE 增加 terminal refs unset 守卫。
   - 测试：构造 check constraint 暂时关闭的损坏 active attempt row，验证 terminal CAS 不覆盖既有 refs。

6. `ATTACH_ACTIVE` 对 ACCEPTED active Run 的幂等记录
   - 直接证据：`_StartRunOperation._handle_active_run` 的 ACCEPTED 分支原先直接返回，不调用 `record_idempotent_result`；非 ACCEPTED attach active 分支会记录。
   - 修复：ACCEPTED 分支同样记录 run idempotent result。
   - 测试：更新 admission 测试，验证首次 attach 记录幂等结果，同 key retry 返回 `idempotent_replay=True` 且不新增事件。

7. `HostTransactionRunner` rollback 失败后连接收口
   - 直接证据：原 `_rollback()` 捕获 `sqlite3.Error` 后静默返回；COMMIT 失败后若 ROLLBACK 失败，runner 可能继续复用仍处于 transaction 的连接。
   - 修复：runner 增加 connection unusable 标记；只在 `connection.in_transaction` 为真时 rollback；rollback 失败后关闭 connection、标记不可用，并拒绝后续 `run_write` / `run_read` 复用。
   - 测试：新增 fake connection mock，模拟 BEGIN 成功、COMMIT 失败、ROLLBACK 失败，验证 runner 关闭连接并在下一次调用前 fail fast。

## Rejected Findings With Evidence

1. `dayu/host/compaction_operation.py` `_merge_tuple_field_patch` CLEAR-then-REPLACE evidence refs 污染
   - 裁决要求先验证 reachability。
   - 直接代码证据：当前 `_merge_tuple_field_patch` 的 REPLACE 分支在 `operation is not PinnedPatchOperation.REPLACE` 时同时执行 `values = []` 与 `evidence_refs = []`；因此 CLEAR 后第一次 REPLACE 会清空 CLEAR pass refs，再追加当前 REPLACE refs。
   - 结论：finding 对当前代码不成立，未做生产改动。
   - 补充测试：新增 helper-level 回归测试，确认 CLEAR 后 REPLACE 的最终 `evidence_refs == ("replace-evidence",)`。

2. DS finding 8 并发 compaction 守卫
   - 直接代码证据：proactive compaction 在 `dispatch.py` 写入 `CONTEXT_COMPACTION_REQUESTED` 后事务外执行，并在写回时按 `run.status` / `input_event_sequence` 做 stale result recheck；reactive compaction 在 `engine_ingest.py` 写入 request 并关闭当前 attempt 后事务外执行，写回时要求 Run 仍为 `RECOVERING` 且 attempt terminal refs 已存在。
   - 现有路径确实没有独立 run 级 compaction mutex；但本轮没有直接证据证明正常 owner 路径会让同一 run 同时执行两个可提交的 compaction。现有 stale result recheck 只能降低重复提交概率，不是互斥锁。
   - 结论：不做生产改动。真正互斥需要 durable lock/state 或等价状态机扩展，属于跨路径架构设计，不适合本轮小型同层修复。

## Explicitly Not Changed

- 未扩大 `run_read` retry policy API。
- 未实现 `StdlibPidLivenessProbe` 平台身份采集。
- 未处理 DS low findings 9、11、12、14、15。
- 未引入 compaction lock table、跨层锁或新 public contract。

## Commands Run

```bash
source .venv/bin/activate && python -m pytest tests/contracts/test_tool_call.py tests/contracts/test_tool_schema.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_runner_diagnostics.py tests/host/test_run_attempt_transitions.py tests/host/test_compaction_operation.py tests/host/test_admission_queue.py tests/host/test_durable_transaction.py
```

Result: `186 passed in 1.11s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

Result: 通过

## Controller Follow-up

- Controller 复核时补充了 `Content-Type` media type 大小写不敏感处理，并将白名单测试改为覆盖 `Text/Event-Stream; charset=utf-8`。
- Controller 重跑同一组受影响测试、`python -m pyright dayu/ tests/ utils/` 与 `git diff --check`，结果仍全部通过。

## Remaining Risk

- 并发 compaction 缺少显式 run-level mutex 仍是 residual risk；现有状态 recheck 能防 stale write，但不是严格互斥。若后续要关闭该风险，应先设计 Host durable 层的 compaction ownership / fencing 语义，而不是在 dispatch 或 ingest 单侧加内存锁。
- `HostTransactionRunner` rollback 失败后会关闭并标记当前 runner connection 不可用；调用方需要重建 store / runner 才能继续使用该持久化连接。这是故障收口行为，不是在线自愈。
