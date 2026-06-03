# Code Review — full-repo-review-fix-round-1 Re-Review

## Scope

- Mode: current changes (workspace fix diff only)
- Branch: `refactor/host-layer-followup-wu-layer-01-02`
- Base: N/A（re-review 只审本轮 fix diff，不重新 diff main）
- Gate: `full-repo-review-fix-round-1-rereview-ds`
- Output file: `docs/reviews/repo-review-fix-round1-rereview-ds-20260602.md`
- Review date: 2026-06-02 22:40 CST
- Included scope: 19 个变更文件（7 production + 3 README + 9 test），详见下方 Changed Files
- Excluded scope: 未变更文件不在此 re-review 范围内
- Input artifacts:
  - `docs/reviews/repo-review-20260602-221156.md`
  - `docs/reviews/repo-review-20260602-221158.md`
  - `docs/reviews/repo-review-fix-round1-codex-20260602.md`

## Changed Files

```
dayu/contracts/tool_await.py                       | 28 ++++++-
dayu/contracts/tool_call.py                        | 12 +++
dayu/contracts/tool_schema.py                      | 16 +++-
dayu/engine/README.md                              |  2 +
dayu/engine/runners/openai/runner.py               | 12 +--
dayu/host/README.md                                |  1 +
dayu/host/admission.py                             | 11 +++
dayu/host/durable/state.py                         |  1 +
dayu/host/durable/transaction.py                   | 79 ++++++++++++++++----
tests/README.md                                    |  8 +-
tests/contracts/test_tool_call.py                  | 39 +++++++++-
tests/contracts/test_tool_outcome_exhaustive.py    |  6 +-
tests/contracts/test_tool_schema.py                | 47 ++++++++++++
tests/engine/runners/openai/test_runner_diagnostics.py | 28 +++++++
tests/engine/runners/openai/test_streaming_capability_and_content_type.py | 43 +++--------
tests/host/test_admission_queue.py                 | 12 ++-
tests/host/test_compaction_operation.py            | 22 ++++++
tests/host/test_durable_transaction.py             | 84 +++++++++++++++++++++
tests/host/test_run_attempt_transitions.py         | 86 +++++++++++++++++++++-
```

## Independent Verification

```
source .venv/bin/activate && python -m pytest [19 affected test files] → 186 passed in 1.02s
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/ → 0 errors, 0 warnings, 0 informations
git diff --check → 通过
```

与 controller 报告一致，无偏差。

## Findings

### 逐项修复裁决

#### Fix 1: ToolAwaitSpec / ToolAwaitSnapshot datetime 时区校验 → **正确修复**

- **文件(行号)**: `dayu/contracts/tool_await.py:59-63, 95-98, 101-111`
- **root cause 验证**: 原始 finding 指出 naive datetime 构造成功但下游与 aware datetime 比较时抛 `TypeError`。修复在构造期调用 `_require_timezone_aware_datetime()`，使用 `value.tzinfo is None or value.utcoffset() is None` 双重校验，覆盖了 `tzinfo` 非 None 但 `utcoffset()` 返回 None 的边界情况（如损坏的 tzinfo 实现）。
- **regression 检查**: `_require_timezone_aware_datetime` 是 `tool_await.py` 模块级私有函数，只在该模块内使用，无跨模块签名泄漏。`ToolAwaitSnapshot.captured_at` 字段不是 Optional，因此不检查 `is not None` 是正确设计——每个 `ToolAwaitSnapshot` 都必须有时区感知的 `captured_at`。
- **测试覆盖**: `test_tool_await_datetimes_must_be_timezone_aware` 同时覆盖 naive 拒绝和 aware 接受，且 `test_tool_outcome_exhaustive.py` 中的 snapshot 构造已同步更新为 `datetime(2026, 1, 1, tzinfo=UTC)`。

#### Fix 2: ToolParametersSchema 空白 property key + truncate_limit_key_for_strategy → **正确修复**

- **文件(行号)**: `dayu/contracts/tool_schema.py:63-67, 195, 220-222`
- **root cause 验证**:
  - 空白 key 校验：在 `property_names` 循环中检查 `property_name.strip() == ""`，与 `ToolCallRequest.__post_init__` 的校验标准一致。
  - `truncate_limit_key_for_strategy`：从直接 `dict[key]` 改为 `.get(key)` + 显式 `ValueError`。`ToolTruncateSpec.__post_init__` 也改为调用同一 helper（`tool_schema.py:195`），消除了原来两处语义分叉（dict 直接索引 vs helper 调用）的风险。
- **regression 检查**: `truncate_limit_key_for_strategy` 现在导出到 `__all__`，与新增公开测试的 import 一致。helper 在 contracts 包内，不跨层。

#### Fix 3: GeminiToolCallState thought_signature 校验 → **正确修复**

- **文件(行号)**: `dayu/contracts/tool_call.py:46-56`
- **root cause 验证**: 添加 `__post_init__`，拒绝 `thought_signature.strip() == ""`。与同模块 `ToolCallRequest.__post_init__` 的字符串校验标准一致。
- **测试覆盖**: `test_gemini_tool_call_state_rejects_blank_signature` 使用 `" \n"` 测试纯空白字符。

#### Fix 4: SSE Content-Type 白名单 + pending readany 异常消费 → **正确修复**

- **文件(行号)**: `dayu/engine/runners/openai/runner.py:125-139, 867-871`
- **root cause 验证**:
  - `_is_sse_response`：从黑名单（`"json" not in content_type` → SSE）改为白名单（提取 media type，大小写不敏感比较 `== "text/event-stream"`）。缺失 Content-Type 仍保留 SSE fallback（`content_type.strip() == ""` → True）。`_JSON_CONTENT_TYPE_FRAGMENT` 常量已移除，无残留死代码。
  - `_cancel_pending_readany`：在 `pending.done()` 分支调用 `pending.exception()` 消费异常，捕获 `CancelledError` 后 pass。与 `dayu/runtime/cancellation.py` 的模式一致。
- **测试覆盖变更分析**: `test_stream_true_unknown_content_type_is_not_sse` 从异步集成测试改为 `_is_sse_response` 单元测试。该函数是 Content-Type 分流的唯一决策点——其返回值直接决定后续路径（SSE parser vs JSON path），因此单元测试在函数级别充分覆盖了决策逻辑。缺失 Content-Type 的集成测试保留在 `test_stream_true_missing_content_type_falls_back_to_sse` 中。

#### Fix 5: terminal_attempt_row CAS 守卫 → **正确修复**

- **文件(行号)**: `dayu/host/durable/state.py:3801`
- **root cause 验证**: WHERE 子句添加 `{_TERMINAL_REFS_UNSET_WHERE_SQL}`，与 `cancel_running_attempt_row`（`state.py:3914`）及其他所有 active attempt 终态写入保持一致。`_TERMINAL_REFS_UNSET_WHERE_SQL` 定义在 `state.py:79`，全模块 22 处引用全部一致。
- **测试覆盖**: `test_terminal_attempt_row_reports_cas_lost_when_terminal_refs_already_set` 使用 `PRAGMA ignore_check_constraints = ON` 模拟损坏的 active attempt row（已有 terminal refs），验证 CAS 返回 `CAS_LOST` 而不覆盖既有 refs。

#### Fix 6: ATTACH_ACTIVE ACCEPTED 幂等记录 → **正确修复**

- **文件(行号)**: `dayu/host/admission.py:1019-1029`
- **root cause 验证**: ACCEPTED 分支现在调用 `record_idempotent_result`（与 `created_event_id=None, created_event_sequence=None`，因为 ACCEPTED Run 尚未写入 EventLog），与非 ACCEPTED attach active 分支（`admission.py:1040-1050`）对称。
- **测试覆盖**: `test_reject_conflicts_and_attach_active_returns_accepted_active` 新增 retry 验证：同 `client_request_id` 再次 `start_run` 返回 `idempotent_replay=True` 且 `run_id` 匹配，同时 `idempotency_records` 计数确认为 `before_idempotency + 1`（首次 attach 记录一条）。

#### Fix 7: HostTransactionRunner rollback 失败后连接收口 → **正确修复**

- **文件(行号)**: `dayu/host/durable/transaction.py:241, 276, 292-295, 310-314, 317-321, 339, 355-358, 372-377, 386-415, 542-553`
- **root cause 验证**: 原 finding 指出 COMMIT 失败 + ROLLBACK 失败后 `_active_transaction_count` 归零但连接仍持有 transaction，下次 `BEGIN IMMEDIATE` 不可恢复。修复机制：
  1. `_connection_unusable` 标记（`transaction.py:241`）
  2. `_raise_if_connection_unusable()` 在每次 retry 循环入口 fail-fast（`transaction.py:276, 339`）
  3. `_rollback_if_needed_or_mark_unusable()` 检查 `connection.in_transaction`（Python 3.2+ 内置属性），仅在仍处于 transaction 时 rollback；rollback 失败后关闭连接并标记不可用（`transaction.py:398-415`）
  4. `_rollback()` 返回值从 `None` 改为 `bool`（`transaction.py:542-553`）
  5. 所有三个 `except` 块（`sqlite3.Error`、`HostDurableError`、`Exception`）在 `run_write` 和 `run_read` 中统一使用新方法
- **异常链分析**: rollback 失败时抛出 `HostDurableError("rollback failed; connection is unusable") from exc`——原始异常通过 `__cause__` 保留，不影响调用方根因排查。
- **边界情况**: `_active_transaction_count` 仍在 `finally` 块中递减（`transaction.py:289-290`）。rollback 失败后计数器归零但 `_connection_unusable=True`，下次调用先命中 `_raise_if_connection_unusable()` 而非计数器检查，行为安全。
- **测试覆盖**: `test_commit_failure_with_rollback_failure_marks_runner_unusable` 使用 fake connection 模拟 BEGIN 成功、COMMIT 失败、ROLLBACK 失败，验证 connection 被关闭且后续 `run_write` 直接抛 `HostDurableError("connection is unusable")`。

### 被驳回 Finding: compaction CLEAR-then-REPLACE evidence refs 污染 → **驳回成立**

- **文件(行号)**: `dayu/host/compaction_operation.py:454-457`
- **直接证据**: REPLACE 分支的 guard 条件 `if operation is not PinnedPatchOperation.REPLACE:` 在首次遇到 REPLACE patch 时执行 `values = []` 与 `evidence_refs = []`，清空此前 CLEAR pass 的累积。CLEAR evidence refs 在 `operation` 从 CLEAR 切换到 REPLACE 时被重置。
- **边界确认**: 多个连续 REPLACE pass 的 evidence refs 通过 `extend` 累积——这是设计意图，因为多个 REPLACE pass 共同产出一个 merged REPLACE 结果。不存在 CLEAR evidence 污染 REPLACE 的问题。
- **回归测试**: `test_tuple_patch_replace_drops_prior_clear_evidence` 确认 CLEAR with `("clear-evidence",)` + REPLACE with `("replace-evidence",)` → 最终 `evidence_refs == ("replace-evidence",)`。

### DS 并发 Compaction Residual Risk → **不阻塞本轮 PASS**

- 当前 proactive compaction（dispatch 触发）与 reactive compaction（engine_ingest 触发）无显式 run-level mutex。
- 现有防线：两者均在事务外执行 compaction work，写回时通过 CAS（`run.status` / `input_event_sequence` / attempt terminal refs）做 stale result recheck。这是乐观并发控制，能防止脏写，但不是严格互斥。
- 在当前单 worker 部署模型下，同一 run 同时执行两条 compaction 路径的概率极低。proactive path 在 scheduler drain loop 内触发，reactive path 在 EngineEvent ingest 写入 request 并关闭 attempt 后触发——两者在 run 生命周期上的触发窗口重叠有限。
- 这是一个需要在 Host durable 层设计 compaction ownership / fencing 语义才能正确关闭的 residual risk，涉及跨路径状态机扩展，不属于本轮小型同层修复的合理范围。
- **结论**: 作为 residual risk 记录，不阻塞本轮 PASS。

### 其他已显式声明未改的 Low Findings → **不阻塞 PASS**

以下 findings 在 Codex 报告中显式列为 "Explicitly Not Changed"，与本轮 fix scope 一致：

- `run_read` 复用 write retry policy 参数（review-221156 Finding 2）：功能正确，纯命名问题
- `StdlibPidLivenessProbe` 平台身份采集（review-221156 Finding 3）：仅开发环境，需平台特定实现
- DS low findings 9/11/12/14/15（review-221158）：均为低严重度，不在本轮裁决范围

### README / 文档同步 → **一致**

- `dayu/engine/README.md:137`：新增 Content-Type 分流行为描述，与 `_is_sse_response` 实现一致
- `dayu/host/README.md:301`：新增 rollback 失败后 connection 不可用行为描述，与 `_rollback_if_needed_or_mark_unusable` 实现一致
- `tests/README.md`：
  - Line 117：tool call 测试覆盖描述新增"工具等待时间字段时区边界、工具参数 schema key 边界和截断策略 limit key 映射穷尽性"
  - Line 396：durable 测试覆盖描述新增"rollback 失败后 runner 不复用脏连接"、"CLEAR 后 REPLACE tuple patch evidence refs 隔离"、"attach active 幂等"
  - Line 405-409：SSE 测试覆盖描述新增"HTTP 200 Content-Type 白名单分流"、"已完成 read task 异常消费"
- 所有文档更新以代码实际行为为准，无未来设计或过期术语。

### 分层 / Import 边界 → **无违规**

- `dayu/contracts/` 无对 `dayu.engine` / `dayu.host` / `dayu.service` 的 import
- `dayu/engine/` 无对 `dayu.host` / `dayu.service` 的 import
- `dayu/host/durable/transaction.py` 的 `_rollback` 是模块私有函数，不影响 `dayu/runtime/lane.py` 中同名的独立 `_rollback`
- `_require_timezone_aware_datetime` 是 `dayu/contracts/tool_await.py` 模块级私有函数，不跨模块暴露

### Typing / Docstring → **全部合格**

- 所有新增函数均有完整中文 docstring（参数、返回值、异常）
- `_rollback` 返回值类型从 `None` 更新为 `bool`，docstring 同步更新
- `_rollback_if_needed_or_mark_unusable` 有完整 docstring
- `_raise_if_connection_unusable` 有完整 docstring
- pyright 0 errors 确认无类型问题

## Open Questions

无。

## Residual Risk

1. **并发 compaction 缺少显式 run-level mutex**：当前依赖 CAS stale result recheck（乐观并发控制），在单 worker 部署下风险极低。若未来支持多 worker 并行 dispatch 或并发 EngineEvent ingest，需在 Host durable 层设计 compaction ownership / fencing 语义。

2. **`HostTransactionRunner` rollback 失败后需调用方重建 store/runner**：不是在线自愈。当前修复实现了 fail-fast + 清晰错误信号，调用方（Host）需在 `HostDurableError("connection is unusable")` 时重建持久化连接。这是故障收口行为，已在 `dayu/host/README.md` 中记录。

3. **`_is_sse_response` 单元测试替代了原集成测试**：`text/plain` 等非 SSE Content-Type 的端到端路径未在本轮测试中通过完整 runner pipeline 验证，但 `_is_sse_response` 作为唯一决策点，单元测试已充分覆盖分支逻辑。缺失 Content-Type 的集成路径仍保留。

## 最终结论

**PASS**

7 个已修 findings 全部正确修复了 root cause，无 regression。被驳回的 CLEAR-then-REPLACE finding 对当前代码不成立（`compaction_operation.py:455-457` 的 guard 条件在首次 REPLACE 时正确重置 `evidence_refs`）。并发 compaction residual risk 不阻塞本轮 PASS。186 tests passed，pyright 0 errors，文档与实现一致，分层约束无违规。
