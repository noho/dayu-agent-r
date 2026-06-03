# Code Review

## Scope

- Mode: current changes (re-review fix diff only)
- Branch: `refactor/host-layer-followup-wu-layer-01-02`
- Base: `HEAD`（本轮 fix diff 相对当前 HEAD 的 workspace changes）
- Output file: `docs/reviews/repo-review-fix-round1-rereview-mimo-20260602.md`
- Review date: 2026-06-02
- Gate: `full-repo-review-fix-round-1-rereview-mimo`
- Included scope: 19 个修改文件（7 个 production、9 个 test、3 个 README）
- Excluded scope: 未修改文件
- Parallel review coverage: 无（单 reviewer 直接走读 fix diff）

## 输入 Artifact

- `docs/reviews/repo-review-20260602-221156.md`（全仓 review 第一轮，4 subagent）
- `docs/reviews/repo-review-20260602-221158.md`（全仓 review 第二轮，7 slice）
- `docs/reviews/repo-review-fix-round1-codex-20260602.md`（Codex 修复报告）

## 已知 Controller 本地验证

- `pytest` 186 passed
- `pyright` 0 errors
- `git diff --check` 通过

## Findings

未发现实质性问题。

## Fix-by-Fix Verification

### Fix 1: `ToolAwaitSpec` / `ToolAwaitSnapshot` datetime 时区校验

- **Root cause**: `__post_init__` 未检查 `deadline` / `captured_at` 是否 timezone-aware，naive datetime 可构造成功但下游比较时抛 `TypeError`。
- **修复**: 新增 `_require_timezone_aware_datetime` 私有辅助函数，在 `deadline is not None` 和 `captured_at` 时调用。
- **直接证据**: `tool_await.py:59-63`（deadline 校验）、`tool_await.py:95-98`（captured_at 校验）、`tool_await.py:101-111`（辅助函数）。
- **测试**: `test_tool_call.py:222-247` 覆盖 naive datetime 拒绝和 aware datetime 通过；`test_tool_outcome_exhaustive.py:102` 已有 snapshot 测试同步为 `tzinfo=UTC`。
- **回归风险**: 无。仅在构造期新增校验，不影响运行时数据流。

### Fix 2: `ToolParametersSchema` blank property key + truncation strategy 映射

- **Root cause**: `__post_init__` 不遍历 `properties` key 验证非空；`truncate_limit_key_for_strategy` 直接索引映射，缺映射时泄漏 `KeyError`。
- **修复**: 新增 property key 非空白校验（`tool_schema.py:63-67`）；改用 `.get()` + 显式 `ValueError`（`tool_schema.py:220-222`）；`ToolTruncateSpec.__post_init__` 复用同一 helper（`tool_schema.py:195`）。
- **测试**: `test_tool_schema.py:30-39`（blank key 拒绝）、`test_tool_schema.py:57-68`（全 enum 映射覆盖）、`test_tool_schema.py:71-87`（缺映射 ValueError）。
- **回归风险**: 无。`_TRUNCATE_LIMIT_KEYS_BY_STRATEGY` 当前覆盖全部 4 个枚举成员，穷举测试确认。

### Fix 3: `GeminiToolCallState.thought_signature` 校验

- **Root cause**: dataclass 无 `__post_init__`，空白签名可构造。
- **修复**: 新增 `__post_init__` 拒绝空白 `thought_signature`（`tool_call.py:46-56`）。
- **测试**: `test_tool_call.py:194-198`。
- **回归风险**: 无。仅构造期校验。

### Fix 4: SSE Content-Type 白名单 + pending readany 异常消费

- **Root cause**: `_is_sse_response` 对非 JSON Content-Type 走 SSE，`text/plain` / `application/octet-stream` 被送入 SSE parser；`_cancel_pending_readany` 对已完成 task 不消费异常。
- **修复**: `_is_sse_response` 改用 `media_type == "text/event-stream"` 精确匹配（`runner.py:138-139`），保留缺失 Content-Type 的 SSE fallback（`runner.py:136-137`）；已 done task 调用 `pending.exception()` 消费异常（`runner.py:867-871`）。
- **测试**: `test_streaming_capability_and_content_type.py:244-258`（非 SSE、带参数 SSE、大小写不敏感）；`test_runner_diagnostics.py:182-197`（done task 异常消费）；集成测试保留缺失 Content-Type fallback（`test_streaming_capability_and_content_type.py:336-374`）。
- **回归风险**: 低。缺失 Content-Type 仍走 SSE fallback，与旧行为一致；非 SSE Content-Type 不再误入 SSE parser，是行为纠正。

### Fix 5: `terminal_attempt_row` terminal refs CAS 守卫

- **Root cause**: `terminal_attempt_row` 的 CAS WHERE 子句缺少 `_TERMINAL_REFS_UNSET_WHERE_SQL`，与 `cancel_running_attempt_row` 等同类函数不一致。
- **修复**: 在 WHERE 子句中增加 `_TERMINAL_REFS_UNSET_WHERE_SQL`（`state.py:3801`）。
- **直接证据**: `_TERMINAL_REFS_UNSET_WHERE_SQL` 在 `state.py:79` 定义，被 20+ 处 CAS 函数引用；`terminal_attempt_row` 原先缺失，现已补齐。
- **测试**: `test_run_attempt_transitions.py` 中新增测试构造 check constraint 暂时关闭的损坏 active attempt row，验证 terminal CAS 不覆盖既有 refs。
- **回归风险**: 无。WHERE 条件更严格，不会放宽写入。

### Fix 6: `ATTACH_ACTIVE` 对 ACCEPTED active Run 的幂等记录

- **Root cause**: `_handle_active_run` 的 ACCEPTED 分支直接返回，不调用 `record_idempotent_result`；非 ACCEPTED 分支会记录。
- **修复**: ACCEPTED 分支同样调用 `record_idempotent_result`（`admission.py:1019-1029`）。
- **测试**: `test_admission_queue.py:685-700` 验证首次 attach 记录幂等结果，同 key retry 返回 `idempotent_replay=True` 且不新增事件。
- **回归风险**: 无。幂等记录是 additive side effect，不影响 Run 状态。

### Fix 7: `HostTransactionRunner` rollback 失败后连接收口

- **Root cause**: 原 `_rollback()` 捕获 `sqlite3.Error` 后静默返回；COMMIT 失败后若 ROLLBACK 也失败，runner 可能继续复用仍处于 transaction 的连接。
- **修复**: `_rollback` 改为返回 `bool`（`transaction.py:542-553`）；新增 `_connection_unusable` 标志位和 `_raise_if_connection_unusable`（`transaction.py:386-396`）、`_rollback_if_needed_or_mark_unusable`（`transaction.py:398-415`）；`run_write` / `run_read` 所有 catch 路径改用新方法；rollback 失败时关闭连接、标记不可用。
- **测试**: `test_durable_transaction.py:818-850` 使用 `_CommitRollbackFailingConnection` fake 模拟 BEGIN 成功、COMMIT 失败、ROLLBACK 失败，验证 runner 关闭连接并在下一次调用前 fail fast。
- **回归风险**: 无。`_rollback` 原先的调用点已被 `_rollback_if_needed_or_mark_unusable` 替换；`in_transaction` 检查确保不在非 transaction 状态执行 ROLLBACK。

## Rejected Findings Verification

### Finding 6 (CLEAR-then-REPLACE evidence refs 污染): 驳回正确

- **代码证据**: `compaction_operation.py:454-457` — REPLACE 分支在 `operation is not PinnedPatchOperation.REPLACE` 时执行 `values = []` 和 `evidence_refs = []`，因此 CLEAR 后首次 REPLACE 会清空 CLEAR pass refs。
- **测试证据**: `test_compaction_operation.py:751-770` — `test_tuple_patch_replace_drops_prior_clear_evidence` 断言 `merged.evidence_refs == ("replace-evidence",)`。
- **结论**: 驳回理由成立。当前代码在 CLEAR→REPLACE 转换时确实清空了先前累积。

### Finding 8 (并发 compaction 守卫): residual risk 判定正确

- **代码证据**: proactive compaction 在 `dispatch.py` 写入后事务外执行，写回时按 `run.status` / `input_event_sequence` 做 stale result recheck；reactive compaction 在 `engine_ingest.py` 写入后事务外执行，写回时要求 Run 仍为 `RECOVERING` 且 attempt terminal refs 已存在。
- **结论**: 现有 stale result recheck 能防 stale write，但不是严格互斥锁。没有直接证据证明正常 owner 路径会让同一 run 同时执行两个可提交的 compaction。真正互斥需要 durable lock/state 或等价状态机扩展，属于跨路径架构设计，不适合本轮小型同层修复。判定为 residual risk 正确。

## README Consistency

- `dayu/engine/README.md:137` — 新增 Content-Type 分流说明段落，与 `_is_sse_response` 白名单逻辑一致。
- `dayu/host/README.md:301` — 新增 "transaction runner 在已进入 transaction 后若 rollback 失败，会把当前 connection 标记为不可用并拒绝后续复用" 说明，与 `transaction.py` 实现一致。
- `tests/README.md:117` — 同步更新测试覆盖描述，涵盖 timezone 边界、schema key 边界、truncation 映射穷尽性、rollback 失败隔离、attach active 幂等、CLEAR+REPLACE 隔离、Content-Type 白名单等。

## Open Questions

- 无。

## Residual Risk

- 并发 compaction 缺少显式 run-level mutex 仍是 residual risk。现有 stale result recheck 能防 stale write，但不是严格互斥。若后续要关闭该风险，应先设计 Host durable 层的 compaction ownership / fencing 语义。
- `HostTransactionRunner` rollback 失败后会关闭并标记当前 runner connection 不可用；调用方需要重建 store / runner 才能继续使用该持久化连接。这是故障收口行为，不是在线自愈。

## Conclusion

**PASS**

本轮 7 个 accepted fixes 均真修 root cause，未引入 regression。2 个 rejected findings 驳回理由成立。tests 与 README 与实现边界一致。pyright/typing/docstring/分层约束未被破坏。并发 compaction residual risk 不阻塞本轮 PASS。
