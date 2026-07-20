# R09 Fins Direct Stream Validator — Dual Cumulative Aggregate Deepreview

## Scope

- **Mode**: Aggregate system review (accepted plan + complete implementation + full finding ledger + Controller validations + 12-path product/test/README组合行为)
- **Umbrella**: WU-SEMANTIC-OWNERSHIP-01, sub-WU R09 "Fins Direct Stream Validator"
- **HEAD**: `9d36a115400fb59fd95475189810b43a09fda31b` (verified ✓)
- **12-path manifest**: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` (verified ✓)
- **Canonical cumulative diff**: `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e` (workspace unstaged, 12 paths)
- **Staged**: empty (verified ✓)
- **Review date**: 2026-07-17T17:11:20
- **Reviewer**: AgentMiMo
- **Authority order**: AGENTS.md → overdesign controller discussion → fins/host/engine/tool/ui design → R09 final plan → all R09 artifacts

### 12-Path Manifest

| # | File | Status |
|---|---|---|
| 1 | `dayu/fins/direct_stream.py` | NEW (261 lines) |
| 2 | `dayu/fins/direct_events.py` | MODIFIED (+1 line: `EVENT_AFTER_RESULT` enum member) |
| 3 | `dayu/fins/ingestion_runtime.py` | MODIFIED (124 +/-) |
| 4 | `dayu/service/fins_direct.py` | MODIFIED (127 +/-) |
| 5 | `dayu/cli/commands/fins.py` | MODIFIED (190 +/-) |
| 6 | `dayu/fins/README.md` | MODIFIED (10 +/-) |
| 7 | `dayu/service/README.md` | MODIFIED (4 +/-) |
| 8 | `tests/README.md` | MODIFIED (8 +/-) |
| 9 | `tests/fins/test_fins_direct_stream.py` | NEW (742 lines, 16 tests) |
| 10 | `tests/fins/test_fins_ingestion_runtime.py` | MODIFIED (257 +/-) |
| 11 | `tests/service/test_fins_direct.py` | MODIFIED (144 +/-) |
| 12 | `tests/cli/test_fins_commands.py` | MODIFIED (506 +/-) |

### Parallel Review Coverage

本 aggregate 由单一 reviewer 完成，未使用 subagent。全部 12 个产品/测试/README 文件均逐行走读，覆盖了：
- `direct_stream.py` 完整状态机（OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED）
- `direct_events.py` 安全文本守卫与类型契约
- `ingestion_runtime.py` 直播 stream 路径（download/preprocess/upload → `_run_direct_stream` → `ValidatedFinsEventStream`）
- `fins_direct.py` Service passthrough（删除 `_ensure_result_event`，直接返回 `ValidatedFinsEventStream`）
- `fins.py` CLI 确定性生命周期（`_raise_primary_after_fins_stream_close`、`_cancel_and_drain_fins_event_task`、SIGINT 处理）
- 全部 4 个 changed test 文件的真实 async generator 测试

---

## Findings

未发现实质性问题。

---

## Cross-Layer Aggregate Analysis

### 1. Fins Unique Validator Owner 与 Runtime Producer/Raw Bridge 端到端行为

**审查路径**: `FinsIngestionRuntime.download()` → `_run_direct_stream()` → `_DirectDownloadProducer` → `Queue` → `_direct_queue_get` → raw `AsyncGenerator[FinsEvent, None]` → `ValidatedFinsEventStream`

**结论**: 语义所有权正确收敛。

- R09 之前：`_run_direct_stream` 是 `async generator`，内部自行做 `MISSING_RESULT` / `DUPLICATE_RESULT` 判定，同时 Service 层 `_ensure_result_event` 也做一次相同判定，CLI 层再兜底一次。三个独立 owner。
- R09 之后：`_run_direct_stream` 降级为 raw generator（只 yield item，不做协议判定），返回 `AsyncGenerator[FinsEvent, None]`；`ValidatedFinsEventStream` 作为唯一 owner 包装该 raw generator。
- `download()`/`preprocess()`/`upload()` 从 `async def` + `yield` 改为 `def` + `return ValidatedFinsEventStream(...)`。这一改变是正确的：构造函数是同步的，不涉及 I/O，stream 消费延迟到 CLI `async for` 时才启动。
- `_run_direct_stream` 的 `finally` 块调用 `cancellation_state.request_cancel()`，确保 producer thread 在 raw generator 被关闭时停止。这与 `ValidatedFinsEventStream.aclose()` → `_close_source_once()` 形成完整的关闭链。

### 2. RESULT Exactly-One-and-Last 语义

**审查路径**: `_run_direct_stream` yield loop → `ValidatedFinsEventStream.__anext__` → state machine

**结论**: 协议判定完全在 `ValidatedFinsEventStream` 内部，state machine 逻辑正确。

- `OPEN` 状态遇到首个 `RESULT` → 缓存，不 yield，转 `RESULT_BUFFERED`
- `RESULT_BUFFERED` 状态遇到任何事件（包括第二个 `RESULT`） → 协议错误
- raw source `StopAsyncIteration` → `_finish_clean_exhaustion()`：若仍在 `OPEN` 则 `MISSING_RESULT`；否则 yield buffered result，转 `RESULT_YIELDED`
- `RESULT_YIELDED` → `CLOSED`，后续 `__anext__` 抛 `StopAsyncIteration`

无遗漏分支。

### 3. Primary/Cleanup/Cancel/SIGINT/Consumer Error 竞态

**审查路径**: CLI `_wait_for_terminal_handling_sigint` → `_consume_fins_direct_events` → `_cancel_and_drain_fins_event_task` → `_raise_primary_after_fins_stream_close`

**结论**: 竞态处理正确。

- **正常完成**: event_task 完成 → 返回 terminal_result → `stream.aclose()` 在 `_run_fins_direct_command_async` 的正常路径调用
- **SIGINT**: `sigint_monitor.wait_next` 先完成 → `cancellation_token.request_cancel()` → `event_task.cancel()` → 等待 event_task → 若 `CancelledError.__cause__` 存在则传播 close_error → 否则返回 `EXIT_KEYBOARD_INTERRUPT`
- **Consumer error (render/log)**: `_consume_fins_direct_events` 抛出异常 → `event_task` 完成并携带异常 → `_wait_for_terminal_handling_sigint` 的 `except BaseException` 捕获 → `_cancel_and_drain_fins_event_task` 等待已结束的 task → 返回 cleanup_error → `raise primary_error from cleanup_error`
- **External task cancel**: `event_task` 被外部取消 → `CancelledError.__cause__` 提取 close error → 传播
- **Stream close failure**: `_raise_primary_after_fins_stream_close` 确保 `stream.aclose()` 失败时 close_error 成为 `__cause__`，primary_error 保持身份

关键设计点：`_cancel_and_drain_fins_event_task` 检查 `cleanup_error is primary_error` 避免自引用 cause cycle。测试 `test_cli_event_task_drain_deduplicates_same_primary_close_cause` 验证了这一点。

### 4. terminal_result Availability

**审查路径**: `ValidatedFinsEventStream.terminal_result` → `_clean_exhaustion` flag

**结论**: 正确。

- 仅在 `_clean_exhaustion = True` 时可用（即 raw source 以 `StopAsyncIteration` 正常结束且包含至少一个 `RESULT`）
- abortive close 清除 `_buffered_result_event` 和 `_terminal_result_value`
- 四个状态（OPEN、RESULT_BUFFERED、RESULT_YIELDED、CLOSED-abortive、CLOSED-clean）均有测试覆盖
- CLI 在 `_consume_fins_direct_events` 中消费完所有事件后调用 `events.terminal_result`，此时必然处于 clean exhaustion 状态

### 5. Operation Provenance / Object Identity

**审查路径**: `FinsDirectStreamProtocolError` → CLI render → test assertions

**结论**: 正确。

- 协议错误对象由 `ValidatedFinsEventStream` 构造，携带 `reason`、`operation_kind`、`message`
- Service 层删除 `_ensure_result_event` 后不再构造或拦截协议错误，直接透传
- CLI 层 `_consume_fins_direct_events` 不再兜底构造 `MISSING_RESULT`，直接使用 `events.terminal_result`
- 测试 `test_fins_owned_protocol_error_object_reaches_cli_consumer_unchanged` 验证 error identity preservation
- 测试 `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli` 验证 `operation_kind` 从 runtime 到 CLI 不被篡改

### 6. LLM-facing Error Projection

**审查路径**: `FinsDirectStreamProtocolError` → CLI stderr rendering

**结论**: 正确。

- CLI 沿用既有人类可读 error prefix/message（`CliFinsUsageError` 渲染路径）
- 协议错误 `FinsDirectStreamProtocolError` 在 CLI 顶层被捕获，渲染为 stderr 错误 + `EXIT_FAILURE`
- `message` 字段由 `_validate_safe_text` 守卫，不包含 job_id、cursor、raw payload 等内部标识
- `direct_events.py` 的 `_DISALLOWED_TEXT_FRAGMENTS` 和正则确保所有 LLM-facing 文本安全

### 7. Real Async Generator Tests 与 Coverage/Smoke Evidence 真实性

**审查路径**: `tests/fins/test_fins_direct_stream.py` → `_controlled_raw_stream` → `_RawStreamObservation`

**结论**: 测试使用真实 async generator，非 mock。

- `_controlled_raw_stream` 是 `async def` generator，使用 `try/finally` 和 `GeneratorExit` 处理
- `_RawStreamObservation` 记录 `next_calls`、`generator_exit_calls`、`finally_calls`
- 覆盖：progress → buffered result、missing result、duplicate result、event after result、upstream error identity、upstream cancellation identity、close failure as cause、result then error、explicit aclose、repeated aclose、terminal_result 四个状态
- `tests/service/test_fins_direct.py` 使用 `_FakeIngestionRuntime` + real `_raw_stream()` async generator + real `ValidatedFinsEventStream`
- `tests/cli/test_fins_commands.py` 使用 `_FakeFinsDirectService` + real `_raw_stream()` + real `ValidatedFinsEventStream` + real CLI `main()`
- Controller 锁定证据：R09 累积实现验证通过 affected 161 tests / full Fins 873 tests (1 existing skip)、88-97% changed-file coverage、pyright/Ruff zero、real SEC/Docling smokes

### 8. README / Design Truth

**审查路径**: `dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md`

**结论**: README 与实现一致。

- Fins README 组件树包含 `direct_events.py` 和 `direct_stream.py`（R09-RR-F01 修复）
- Fins README 三个 direct 签名全部投影 `ValidatedFinsEventStream`（R09-CR-F04 修复）
- Service README 第 15、35 行反映终态判定和 missing/duplicate 错误所有权迁移至 Fins
- Tests README 第 149、196 行反映 owner 测试归属 Fins

### 9. Security Retention

**审查路径**: `_validate_safe_text`、`_DISALLOWED_TEXT_FRAGMENTS`、FinsEvent `__post_init__`

**结论**: 安全守卫完整保留。

- `direct_events.py` 的 `_validate_safe_text` 在 R09 中未被修改，仍执行：非空校验、长度限制、禁止内部标识符片段、禁止绝对路径、禁止 Fins job ID 正则
- 直接 stream 事件经过同一验证管道
- 测试 `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text` 和 `test_fins_event_leakage_guard_rejects_internal_or_sensitive_text` 验证守卫行为

### 10. Deferred Scope 无偷带

**审查路径**: R09 plan 授权边界 vs 实际实现

**结论**: 无偷带。

- R09 plan 授权范围：Fins validator owner (S1) + Service/CLI 机械 cutover (S2)
- 实际实现严格在授权范围内：
  - `direct_stream.py` 新建：唯一 validator owner
  - `direct_events.py`：仅新增 `EVENT_AFTER_RESULT` enum member（1 行）
  - `ingestion_runtime.py`：删除协议判定逻辑，`async def` → `def`，返回类型改为 `ValidatedFinsEventStream`
  - `fins_direct.py`：删除 `_ensure_result_event`，所有方法返回类型改为 `ValidatedFinsEventStream`
  - `fins.py`：删除 `_direct_operation_kind`，添加 `_raise_primary_after_fins_stream_close` 和 `_cancel_and_drain_fins_event_task`，返回类型改为 `ValidatedFinsEventStream`
- 未涉及：Issue 142/151/175/177/178、Web/WeChat/render tracker、Topic 8/9、统一 tool authorization
- DS former F05（`terminal_result` contract observation）按 Controller 裁决拒绝，未偷带实现

---

## Prior Findings Final Ledger

| Canonical ID | Severity | Phase | Final Disposition | Description |
|---|---|---|---|---|
| R09-CR-F01 | HIGH | Code review → Fix | CLOSED | CLI consumer deterministic close on normal, error, external cancel, and SIGINT paths |
| R09-CR-F02 | MEDIUM | Code review → Fix | CLOSED | Tests use typed real async generators, no cast or fake objects |
| R09-CR-F03 | MEDIUM | Code review → Fix | CLOSED | GeneratorExit, finally, close-at-most-once, upstream error/cancel and cleanup cause all owner-level tested |
| R09-CR-F04 | LOW | Code review → Fix | CLOSED | Fins README three direct signatures all project `ValidatedFinsEventStream` |
| R09-RR-F01 | LOW | Re-review → Fix | CLOSED | Fins main-component tree precisely includes `direct_events.py` and `direct_stream.py` |
| F01 self-cause/context | N/A | Fix follow-up | CLOSED | Drain deduplicates same-primary close error; tests assert cause/context do not form self-cycle |
| DS former F05 | N/A | Initial review | REJECTED | `terminal_result` contract observation; not a defect per Controller adjudication |

**All 6 accepted findings closed. 1 observation rejected. 0 deferred. 0 open.**

---

## Residual Risk

### Deferred Owner (既有，非 R09 引入)

- **Issue 175**: Fins Docling process isolation。既有 deferred owner 记录，非 R09 scope，不在当前实现建议范围内。

---

## Aggregate Verdict

**PASS / ZERO ACCEPTED OR MATERIAL FINDING**

R09 的跨层组合行为正确：Fins `ValidatedFinsEventStream` 作为唯一 validator owner，Service 只做 typed passthrough，CLI 只消费事件并使用 owner 证明的 terminal result。RESULT exactly-one-and-last 语义由单一状态机保证。primary/cleanup/cancel/SIGINT 竞态由确定性关闭链处理。所有 prior findings 已关闭。测试使用真实 async generator。README 与实现一致。无偷带 deferred scope。

---

**Verdict**: PASS / zero accepted or material finding

Lines 与 SHA 由外部 Controller 计算。
