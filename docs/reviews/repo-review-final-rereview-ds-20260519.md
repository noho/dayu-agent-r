# Final Re-Review: MiMo + DS Accepted Findings 修复后验证

## Scope

- **Mode**: Re-review of accepted findings fixes
- **Branch**: `feat/host-p10-5-public-contract-freeze`
- **Base**: `main`
- **Output file**: `docs/reviews/repo-review-final-rereview-ds-20260519.md`
- **Input artifacts**:
  - `docs/reviews/repo-review-20260519-154715.md` (MiMo 25 findings)
  - `docs/reviews/repo-review-ds-20260519-154715.md` (DS 25 findings)
  - `docs/reviews/repo-review-fix-codex-20260519.md` (MiMo fix record)
  - `docs/reviews/repo-review-ds-fix-codex-20260519.md` (DS fix record)
- **Included**: All 23 accepted findings across both reviews, corresponding production code, test files, and all deferred/rejected findings for counter-evidence check
- **Excluded**: `AGENTS.md` / `CLAUDE.md` cosmetic alignment (not part of any finding), Host README rewrite (separate scope), MiMo Finding 22 (fixed in prior round)

## Verification Method

1. 逐文件阅读 git diff `main...HEAD` 中每个 accepted finding 触及的生产代码
2. 对关键修复做程序化验证（ABC/abstractmethod 判定、ToolResultMeta 构造期校验、schema version 读取）
3. 运行合并测试套件（229 tests）和 pyright（0 errors）
4. 对 deferred/rejected findings 做反向证据扫描（`_record_terminal_replay` 残留、`TimeoutError` 残留、broad suppress 残留）
5. 检查跨修复交互（schema version bump 与 DB 约束、wait 相关多处修改的冲突可能、warnings 新增对日志行为的语义影响）

## 结论：PASS

23 个 accepted findings 的修复均已落地且行为正确。未发现 deferred/rejected findings 的直接反证。未发现修复间交互引入的新阻断 bug。229 tests passed, pyright 0 errors/0 warnings/0 informations。

以下逐项列出每个 accepted finding 的验证结果，并对 deferred/rejected findings 做反向证据检查。

---

## MiMo Accepted Findings 验证

### MiMo-02: HostDispatchScheduler._drain_loop 异常处理
- **状态**: 已修复
- **文件**: `dayu/host/dispatch.py`
- **证据**: try/except 移入 while 循环内部；非取消异常捕获后写 WARNING 并 continue（非 closed 时 sleep 后退避）；取消异常正常 break。循环不会因非取消异常静默退出。
- **判定**: PASS

### MiMo-03: cleanup 失败路径 warning 日志
- **状态**: 已修复
- **文件**: `dayu/host/dispatch.py`
- **证据**: `_safe_close_worker_handle` 与 `_safe_release_lane_token` 的 except 分支增加 `_LOGGER.warning(..., exc_info=True)`，记录关键上下文（worker_id、lane_name 等）。
- **判定**: PASS

### MiMo-04: host_wait_records snapshot 三元组约束 + VERSION bump
- **状态**: 已修复
- **文件**: `dayu/host/durable/schema.py`
- **证据**: `HOST_SCHEMA_VERSION = 10`（第25行）；`TABLE_HOST_WAIT_RECORDS` DDL 中 snapshot_ref / snapshot_captured_at / snapshot_digest 三列 CHECK 约束为同时 NULL 或同时非 NULL（第598-606行）。
- **判定**: PASS

### MiMo-08: JsonValue 文档 float 有限性
- **状态**: 已修复
- **文件**: `dayu/contracts/json_value.py`
- **证据**: 模块 docstring 与 `JsonValue` TypeAlias docstring 均明确 `float` 运行时必须是有限 JSON number，调用方需用 `math.isfinite` 拒绝 NaN 与正负无穷。
- **判定**: PASS

### MiMo-09: ToolResultMeta 校验
- **状态**: 已修复
- **文件**: `dayu/contracts/tool_result.py`
- **证据**: `__post_init__` 校验 `tool_name.strip() != ""` 和 `finished_at >= started_at`。程序化验证确认：空 tool_name → ValueError，finished_at < started_at → ValueError，合法值通过。
- **判定**: PASS

### MiMo-10: ToolParametersSchema 文档
- **状态**: 已修复
- **文件**: `dayu/contracts/tool_schema.py`
- **证据**: 模块 docstring 明确 `required` 字段名必须来自 `properties`，本模块不做完整 runtime validator。
- **判定**: PASS

### MiMo-11: AgentRunRequest messages 非空校验
- **状态**: 已修复
- **文件**: `dayu/engine/contracts/agent_run.py`
- **证据**: `__post_init__` 中 `len(self.messages) == 0` 时 raise `ValueError("AgentRunRequest.messages must be non-empty")`。
- **判定**: PASS

### MiMo-12: run_agent_and_wait fallback 路径 warning
- **状态**: 已修复
- **文件**: `dayu/engine/agent.py`
- **证据**: unknown terminal shape fallback 路径增加 `_LOGGER.warning(...)` 记录 terminal type 与 data type。
- **判定**: PASS

### MiMo-14: poll_interval_seconds > 0 校验
- **状态**: 已修复
- **文件**: `dayu/runtime/cancellation.py`
- **证据**: `_validate_poll_interval()` 函数在 `await_or_cancel`、`wait_for_or_cancel`、`await_or_cancel_or_timeout` 中调用；拒绝 coroutine 时主动 close 避免未 await 警告。
- **判定**: PASS

### MiMo-15: LaneController 异常链保留
- **状态**: 已修复
- **文件**: `dayu/runtime/lane.py`
- **证据**: 两处外层取消异常处理从 `raise cancelled` 改为 `raise cancelled from exc`，保留异常链。
- **判定**: PASS

### MiMo-16: HostToolAwaitingAcceptPort ABC
- **状态**: 已修复
- **文件**: `dayu/host/waiting.py`
- **证据**: `HostToolAwaitingAcceptPort(ABC)` 类声明；`accept_tool_awaiting` 标记为 `@abstractmethod`。程序化验证：`inspect.isabstract()` → True，`__isabstractmethod__` → True。
- **判定**: PASS

### MiMo-17: _record_terminal_replay 重命名
- **状态**: 已修复
- **文件**: `dayu/host/admission.py`
- **证据**: 方法定义在第1819行为 `_record_terminal_cancel_ack`，调用点在第1546行为 `self._record_terminal_cancel_ack(...)`。全仓搜索 `_record_terminal_replay` 零结果。
- **判定**: PASS

---

## DS Accepted Findings 验证

### DS-05: BatchToolExecutionContext 校验
- **状态**: 已修复
- **文件**: `dayu/contracts/tool_call.py`
- **证据**: `__post_init__` 对 `run_id`、`session_id`、`iteration_id` 做非空/非空白校验，raise ValueError。
- **判定**: PASS

### DS-06: _cancel_task_and_wait 收窄异常吞没
- **状态**: 已修复
- **文件**: `dayu/runtime/cancellation.py`
- **证据**: 从 `suppress(asyncio.CancelledError, Exception)` 改为仅 `except asyncio.CancelledError: pass`，普通异常 catch 后写 WARNING 并记录诊断。全仓搜索 broad suppress 模式零残留。
- **判定**: PASS

### DS-08: _await_task_after_outer_cancellation 退避
- **状态**: 已修复
- **文件**: `dayu/runtime/lane.py`
- **证据**: 增加 `_OUTER_CANCELLATION_SETTLE_SLEEP_SECONDS = 0.01` 常量，shielded task 未完成时 `await asyncio.sleep(...)` 后再 continue，避免紧循环。
- **判定**: PASS

### DS-09: _prepare_database_parent OSError 包装
- **状态**: 已修复
- **文件**: `dayu/runtime/lane.py`
- **证据**: `parent.mkdir()` 包装在 try/except OSError 中，raise `RuntimeLaneConfigError` 并保留异常链。
- **判定**: PASS

### DS-10: finish_reason mismatch warning
- **状态**: 已修复
- **文件**: `dayu/engine/agent.py`
- **证据**: `state.finish_reason` 与 `RunnerDoneData.finish_reason` 不一致时写 WARNING（含 session_id、run_id、iteration_id、两个 finish_reason 值、provider_request_id）。不改变 RunnerDoneData.finish_reason 作为最终分类输入的既有行为（按 fix record 声明为 intentional）。
- **判定**: PASS

### DS-11: SSE 无法归属 tool_call_delta 丢弃
- **状态**: 已修复
- **文件**: `dayu/engine/runners/openai/sse_parser.py`
- **证据**: `_tool_call_delta_event` 返回类型改为 `RunnerToolCallDeltaData | None`；delta 无 index 且无 id 时 return None 并写 WARNING；调用方检查 `event_data is not None` 后才 yield。
- **判定**: PASS

### DS-17: TimeoutError 死代码移除
- **状态**: 已修复
- **文件**: `dayu/host/tool_runtime.py`
- **证据**: 两处 `except (HostTransactionRetryExhaustedError, TimeoutError)` 改为 `except HostTransactionRetryExhaustedError`。全文件搜索 `TimeoutError` 零残留。
- **判定**: PASS

### DS-18: WaitPoller cancelled 去重
- **状态**: 已修复
- **文件**: `dayu/host/wait_adapter.py`
- **证据**: `WaitPoller.__init__` 增加 `self._abandoned_cancelled_wait_ids: set[str]`；`poll_once` 中检查 `record.wait_id in self._abandoned_cancelled_wait_ids` 跳过重复 abandon；成功 abandon 后加入集合。
- **判定**: PASS（注：同一实例内去重有效；跨进程重启/重建 poller 场景见剩余风险）

### DS-20: compactor diagnostic suffix 包含异常消息
- **状态**: 已修复
- **文件**: `dayu/host/compaction_operation.py`
- **证据**: 新增 `_exception_diagnostic_suffix(exc)` 函数返回 `f"{exc.__class__.__name__}:{message}"`；proposal exception path 从 `diagnostic_suffix=exc.__class__.__name__` 改为 `diagnostic_suffix=_exception_diagnostic_suffix(exc)`。
- **判定**: PASS

### DS-21: COMPACT_RANGE_OUTSIDE_REQUEST
- **状态**: 已修复
- **文件**: `dayu/host/context_governance.py`, `dayu/host/compaction.py`
- **证据**: `CompactQualityIssue` enum 新增 `COMPACT_RANGE_OUTSIDE_REQUEST = "compact_range_outside_request"`；新增 `_compact_ranges_from_request()` 检查 dropped/summarized range 起止 ref 属于 `request.older_raw_turn_refs`；集成到 `check_compaction_candidate()`。
- **判定**: PASS

### DS-25: _finalize_success 双重 emit 防护
- **状态**: 已修复
- **文件**: `dayu/engine/runners/openai/sse_parser.py`
- **证据**: `_finalize_success` guard 从 `if self._terminated and self._finish_reason is FinishReason.ERROR: return` 改为 `if self._terminated: return`，覆盖所有 finish_reason 的双重 Done emit 路径。
- **判定**: PASS

---

## Rejected / Deferred Findings 反向证据检查

针对主控驳回或 deferred 的 findings，逐项检查是否有直接反证（即当前工作区中已存在与驳回理由矛盾的事实）。

### MiMo Finding 01 (RECOVERING cancel semantic) — Deferred
- 驳回理由: documented structured unsupported
- 检查: `dayu/host/command.py` 中 RECOVERING 相关 cancel 路径未变化；README 仍标注 deferred unsupported。无新引入的 RECOVERING 状态推进。
- **结论**: 无反证

### MiMo Finding 05 (purge_session) — Deferred
- 驳回理由: documented structured unsupported
- 检查: `purge_session` 路径未变化。无新增 purge 实现。
- **结论**: 无反证

### MiMo Finding 06 (state mutation result 语义) — Deferred
- 驳回理由: 涉及状态 mutation result 语义调整
- 检查: 未发现与 StateMutationResult 语义矛盾的新增使用。
- **结论**: 无反证

### MiMo Finding 07 (诊断结构扩展) — Deferred
- 驳回理由: 涉及诊断结构扩展
- 检查: 诊断结构未变化，与 deferred 状态一致。
- **结论**: 无反证

### MiMo Finding 13 (provider finish_reason 归一) — Deferred
- 驳回理由: 涉及 provider finish_reason 归一语义调整
- 检查: DS Finding 10 fix 仅新增 mismatch warning，不改变 finish_reason 取值逻辑。与 deferral 无冲突。
- **结论**: 无反证

### DS Finding 01 (heartbeat task concurrency) — Rejected
- 驳回理由: 单 event loop 下 check+assignment 不并发交错
- 检查: `_ensure_heartbeat_task` 无 await，仍在单 event loop 下运行。未发现多线程共用 controller 的新证据。
- **结论**: 无反证

### DS Finding 02 (native coroutine .close()) — Rejected
- 驳回理由: Python 3.11 已验证 native coroutine 有 close
- 检查: 运行环境仍为 Python 3.11。未发现 async generator 或旧式 coroutine 被误用。
- **结论**: 无反证

### DS Finding 03 (engine_ingest reactive recovery) — Rejected
- 驳回理由: engine_ingest 有 reactive recovery，旧 execution terminal 应 stale
- 检查: engine_ingest recovery 逻辑未变化。
- **结论**: 无反证

### DS Finding 04 (budget_after_compact overflow) — Rejected
- 驳回理由: token estimate 低值不等于 overflow，未证明压缩循环条件
- 检查: budget 估算逻辑未变化。
- **结论**: 无反证

### DS Finding 07 (runtime lane SQLite retry) — Deferred
- 驳回理由: 涉及错误分类语义
- 检查: runtime lane 的 SQLite 错误处理未变化。
- **结论**: 无反证

### DS Finding 12 (stream/non-stream usage ordering) — Deferred
- 驳回理由: 事件顺序语义调整
- 检查: stream/non-stream 的 usage 处理顺序未变化。
- **结论**: 无反证

### DS Finding 13 (aiohttp streaming total timeout) — Deferred
- 驳回理由: 需确认其他超时机制覆盖
- 检查: aiohttp timeout 配置未变化。
- **结论**: 无反证

### DS Finding 14 (旧库迁移) — Rejected
- 驳回理由: AGENTS.md 全新起库约束
- 检查: `bootstrap_host_durable_store` 仍按 fresh bootstrap 设计；`HOST_SCHEMA_VERSION` bump 到 10 不包含迁移逻辑。
- **结论**: 无反证

### DS Finding 15 (write transaction read-then-insert) — Deferred
- 驳回理由: 未证明并发穿透
- 检查: write transaction 内 read-then-insert 逻辑未变化。
- **结论**: 无反证

### DS Finding 16 (dispatch drain loop 持久错误) — Deferred
- 驳回理由: 需单独设计错误分类/升级策略
- 检查: MiMo Finding 02 fix 仅增加单次异常 warning + continue，未引入错误计数或熔断，与 deferral 方向一致。
- **结论**: 无反证

### DS Finding 19 (duplicate index 与恢复) — Deferred
- 驳回理由: 涉及恢复语义
- 检查: index 逻辑未变化。
- **结论**: 无反证

### DS Finding 23 (dataclass 空字符串校验) — Deferred
- 驳回理由: 更宽契约收紧
- 检查: 本次修复中 DS Finding 5 和 MiMo Finding 11 分别做了 targeted 校验，但未做全量收紧，与 deferral 范围一致。
- **结论**: 无反证

### DS Finding 24 (RunResumeHint) — Deferred
- 驳回理由: 涉及 resume 语义设计
- 检查: `RunResumeHint` 未变化。
- **结论**: 无反证

---

## 跨修复交互检查

- **schema version bump (MiMo-04) + DB 约束**: `HOST_SCHEMA_VERSION = 10`，snapshot 三元组约束仅影响新增/更新 wait_records 行；与 DS-18 (WaitPoller cancelled dedup) 无冲突，WaitPoller 只读取 wait_records 不修改 schema。
- **多重 wait 相关修复**: MiMo-04 (snapshot 约束)、MiMo-16 (ABC 端口)、DS-18 (poller dedup)、DS-17 (TimeoutError 移除) 均触及 wait 路径，但作用在不同层：schema DDL、public port 类型、poller 运行时、ToolRuntime retry 异常处理。无共享可变状态冲突。
- **多重 warning 新增**: MiMo-02/03/12、DS-06/10/11 均只新增 WARNING 级别日志，无控制流变更，不造成日志语义冲突。
- **AGENTS.md / CLAUDE.md 同步**: minor text alignments，与修复无冲突。

**结论**: 未发现跨修复引入的新阻断 bug。

---

## 测试与类型检查

- **合并测试**: `229 passed in 1.81s`（覆盖 contracts、runtime、engine、host 所有 touched 模块的单元测试）
- **pyright**: `0 errors, 0 warnings, 0 informations`（覆盖 `dayu/contracts`、`dayu/runtime`、`dayu/engine`、`dayu/host` 及所有对应测试文件）
- **残留旧名扫描**: `_record_terminal_replay` 零结果；`TimeoutError` 在 tool_runtime.py 零结果；broad `suppress(asyncio.CancelledError, Exception)` 零结果
- **git diff --check**: 通过，无空白冲突

## Open Questions

无。

## Residual Risk

- 未运行全仓测试：本次覆盖 accepted findings 触及的 contracts、runtime、engine、host 模块及对应 16 个测试文件。未触及模块（fins、cli、render、service、utils）的测试未运行。
- DS-18 (WaitPoller cancelled dedup)：只在同一 `WaitPoller` 实例内去重；进程重启或重建 poller 时，durable 中的 CANCELLED poll wait 仍可能再次触发 abandon。当前 `resolve_wait` 对 CANCELLED 做 late reject 而非终态迁移，durable 级一次性 abandon 需单独设计。
- DS-10 (finish_reason mismatch)：当前仅写 warning，不拒绝或修正不一致。若下游依赖 finish_reason 一致性做决策，本 warning 可能不足。
- DS-21 (COMPACT_RANGE_OUTSIDE_REQUEST)：新增 public enum 值 `compact_range_outside_request`；下游若对 `CompactQualityIssue` 做穷尽展示需同步识别。
- MiMo-04 (schema VERSION 10)：无旧库迁移兼容。按 AGENTS.md fresh-schema 起库约束此为预期行为。
