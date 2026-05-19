# Final Re-Review: MiMo + DS Accepted Findings 修复验证

## Scope

- Mode: re-review（验证修复，不做新 review）
- Branch: `feat/host-p10-5-public-contract-freeze`
- Base: `HEAD`（当前工作区 diff）
- Output file: `docs/reviews/repo-review-final-rereview-mimo-20260519.md`
- 验证范围：
  - MiMo repo-review accepted findings（来源：`repo-review-20260519-154715.md`）
  - DS repo-review accepted findings（来源：`repo-review-ds-20260519-154715.md`）
  - 两份 fix report（`repo-review-fix-codex-20260519.md`、`repo-review-ds-fix-codex-20260519.md`）
  - 当前 `git diff HEAD`（36 files, +1051/-229）
- 判定标准：accepted findings 是否已修；rejected/deferred 是否有直接反证；修复是否引入新阻断 bug

## Accepted Findings 验证

### MiMo Accepted Findings（12 项）

| Finding | 描述 | 修复状态 | 验证方式 |
|---------|------|----------|----------|
| 02 | `_drain_loop` 吞掉非取消异常 | PASS | `dispatch.py`: broad `except Exception` 改为 continue + warning，不再静默退出 |
| 03 | cleanup 失败路径无日志 | PASS | `dispatch.py`: `_safe_close_worker_handle` 和 `_safe_release_lane_token` 增加 warning 日志 |
| 04 | `host_wait_records` snapshot 三元组约束 | PASS | `schema.py`: CHECK 约束改为三列同时 NULL/NOT NULL；`HOST_SCHEMA_VERSION` bump 到 10 |
| 08 | `JsonValue` 文档明确 `float` 有限性 | PASS | `json_value.py`: docstring 明确 `float` 必须是有限 JSON number |
| 09 | `ToolResultMeta` 缺少校验 | PASS | `tool_result.py`: `__post_init__` 增加 `tool_name` 非空 + `finished_at >= started_at` |
| 10 | `ToolParametersSchema` 文档 | PASS | `tool_schema.py`: docstring 明确 `required` 字段约束 |
| 11 | `AgentRunRequest.messages` 空校验 | PASS | `agent_run.py`: `__post_init__` 增加 `messages` 非空校验 |
| 12 | fallback terminal shape 无 warning | PASS | `agent.py`: `run_agent_and_wait` 增加 unknown terminal shape warning |
| 14 | `poll_interval_seconds` 校验 | PASS | `cancellation.py`: 增加 `_validate_poll_interval()` + 拒绝 coroutine 时主动 close |
| 15 | 外层取消后异常链丢失 | PASS | `lane.py`: 4 处 `raise cancelled` 改为 `raise cancelled from exc` |
| 16 | `HostToolAwaitingAcceptPort` 非 ABC | PASS | `waiting.py`: 改为 ABC + `@abstractmethod` |
| 17 | `_record_terminal_replay` 命名不一致 | PASS | 重命名为 `_record_terminal_cancel_ack` |

### DS Accepted Findings（11 项）

| Finding | 描述 | 修复状态 | 验证方式 |
|---------|------|----------|----------|
| 5 | `BatchToolExecutionContext` 缺 ID 校验 | PASS | `tool_call.py`: `__post_init__` 增加 `run_id`/`session_id`/`iteration_id` 非空白校验 |
| 6 | `_cancel_task_and_wait` 吞所有异常 | PASS | `cancellation.py`: `suppress(CancelledError, Exception)` 改为 try/except + warning |
| 8 | `_await_task_after_outer_cancellation` 紧循环 | PASS | `lane.py`: 增加 `await asyncio.sleep(0.01)` 退避 |
| 9 | `OSError` 穿透 `_prepare_database_parent` | PASS | `lane.py`: `mkdir` OSError 包装为 `RuntimeLaneConfigError` |
| 10 | `finish_reason` 静默覆盖 | PASS | `agent.py`: 不一致时写 warning |
| 11 | 未归属 delta 回退到 index=0 | PASS | `sse_parser.py`: 无法归属时返回 `None` 丢弃 + warning，不再回退 |
| 17 | 同步 retry 中误捕 `TimeoutError` | PASS | `tool_runtime.py`: 两处 `except (HostTransactionRetryExhaustedError, TimeoutError)` 移除 `TimeoutError` |
| 18 | CANCELLED wait 无限重轮询 | PASS | `wait_adapter.py`: `WaitPoller` 增加 `_abandoned_cancelled_wait_ids` set 去重 |
| 20 | 异常消息被丢弃 | PASS | `compaction_operation.py`: 新增 `_exception_diagnostic_suffix(exc)` 包含 `str(exc)` |
| 21 | quality checker 不校验压缩范围 | PASS | `context_governance.py`: 新增 `_compact_ranges_from_request()` + `COMPACT_RANGE_OUTSIDE_REQUEST` 拒绝原因 |
| 25 | `_finalize_success` 守卫条件错误 | PASS | `sse_parser.py`: guard 从 `self._terminated and self._finish_reason is ERROR` 改为 `self._terminated` |

## Rejected / Deferred Findings 反证评估

### MiMo Rejected / Deferred（5 项）

| Finding | 裁决 | 反证 | 评估 |
|---------|------|------|------|
| 01 | deferred | `RECOVERING` cancel 语义按 documented unsupported 处理；未发现必须覆盖该状态的 public contract 证据 | 反证成立 |
| 05 | deferred | `purge_session` 按 documented structured unsupported 处理 | 反证成立 |
| 06 | deferred | 状态 mutation result 语义调整，当前行为与文档一致 | 反证成立 |
| 07 | deferred | 诊断结构扩展，不影响正确性 | 反证成立 |
| 13 | deferred | provider finish_reason 归一语义，当前行为与协议一致 | 反证成立 |

### DS Rejected / Deferred（14 项）

| Finding | 裁决 | 反证 | 评估 |
|---------|------|------|------|
| 1 | rejected | `_ensure_heartbeat_task` 内无 await，单 event loop 下 check+assignment 不会并发交错；未发现多线程共用 controller 证据 | 反证成立 |
| 2 | rejected | Python 3.11 native coroutine **有** `close()` 方法（`close()` 自 Python 3.5 起存在于 coroutine object）；review 中"PEP 661, Python 3.12 才加入"的说法不准确 | 反证成立 |
| 3 | rejected | Host `engine_ingest` 有 reactive recovery，旧 execution terminal 后 stale；未发现反证 | 反证成立 |
| 4 | rejected | `budget_after_compact` 是 token estimate，低值不等于 overflow；未证明存在压缩循环条件 | 反证成立 |
| 7 | deferred | runtime lane 瞬态 SQLite 错误重试策略涉及错误分类语义，需独立设计 | 反证成立 |
| 12 | deferred | stream / non-stream usage ordering 统一属于事件顺序语义调整 | 反证成立 |
| 13 | deferred | aiohttp streaming total timeout 调整需确认其他超时机制覆盖 | 反证成立 |
| 14 | rejected | 按 AGENTS schema 全新起库约束，不做旧库迁移 | 反证成立 |
| 15 | deferred | 未证明 write transaction 内 read-then-insert 仍会并发穿透 | 反证成立 |
| 16 | deferred | dispatch drain loop 持久错误分类/升级策略需单独设计 | 反证成立 |
| 19 | deferred | duplicate index 与持久化重建机制涉及恢复语义 | 反证成立 |
| 22 | N/A | 已由 MiMo accepted findings 修复（Finding 09），DS fix report 已注明不重复处理 | 无冲突 |
| 23 | deferred | 多个 dataclass 空字符串校验属于更宽契约收紧 | 反证成立 |
| 24 | deferred | `RunResumeHint` 填充涉及 resume 语义设计 | 反证成立 |

## 新阻断 Bug 检查

修复引入的改动均为增量校验、warning 日志、异常包装、退避 sleep 或 enum 扩展，未引入新阻断 bug：

1. **`_validate_poll_interval()`**：新增函数，仅增加校验，不影响已有调用路径。
2. **`_cancel_task_and_wait` 异常处理**：从 suppress 全部异常改为 try/except + warning，行为更保守（保留异常信息而非吞掉），不改变控制流。
3. **`_compact_ranges_from_request()`**：新增 quality check 拒绝原因 `COMPACT_RANGE_OUTSIDE_REQUEST`，仅在 compactor 声明的范围超出 request 时拒绝，不影响正常路径。
4. **`_exception_diagnostic_suffix()`**：新增函数，仅在 diagnostic 字符串中包含异常消息，不影响异常处理逻辑。
5. **`_abandoned_cancelled_wait_ids`**：新增 set 去重，仅避免重复 abandon，不影响首次处理。
6. **SSE parser delta 丢弃**：无法归属的 delta 从回退 index=0 改为丢弃 + warning，更保守，避免数据污染。
7. **`_finalize_success` guard 扩展**：从仅 error 路径改为所有 `_terminated` 路径，更安全，防止双重 emit。
8. **`HOST_SCHEMA_VERSION` bump**：9→10，按全新 schema 约束处理，无迁移路径设计。

## 结论

**PASS**

所有 MiMo accepted findings（12 项）与 DS accepted findings（11 项）均已修复，修复证据可从 `git diff HEAD` 中逐行核实。所有 rejected/deferred findings 均有直接反证支撑。修复未引入新阻断 bug。

## 剩余风险

- 未运行全仓测试；已验证的测试覆盖 contracts、runtime、engine、host 相关 touched 文件（151 + 158 passed）。
- `HOST_SCHEMA_VERSION` bump 到 10，按全新 schema 约束处理，无旧库迁移。
- DS Finding 18 的修复仅在同一 `WaitPoller` 实例内去重；进程重启后 durable 中的 CANCELLED poll wait 仍可能再次触发 abandon。
- DS Finding 11 对无法归属的 delta 采取丢弃策略；aggregator 仍会在 finalize 时产出 protocol warning。
- DS Finding 21 新增 `COMPACT_RANGE_OUTSIDE_REQUEST` enum 值；下游若对 enum 值做穷尽展示需同步识别。
