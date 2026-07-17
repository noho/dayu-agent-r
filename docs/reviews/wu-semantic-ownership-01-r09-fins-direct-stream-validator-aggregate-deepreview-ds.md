# WU-SEMANTIC-OWNERSHIP-01 / R09 最终 dual cumulative aggregate deepreview

## 0. Review metadata

- **Reviewer**: AgentDS (aggregate deepreview)
- **Artifact**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-ds.md`
- **Date**: 2026-07-17T17:09:19+08:00
- **Mode**: aggregate deepreview（不是新 WU/issue/feature，也不是重复 code re-review）
- **Immutable target**: 完整 12-path cumulative tree
  - HEAD: `9d36a115400fb59fd95475189810b43a09fda31b`
  - sorted manifest SHA-256: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`
  - canonical cumulative binary diff SHA-256: `60f52a7ebbd1608b11d28dd0206bf4176eac59e5dfc4a03fa87393c9457caf3e`
  - staged tree: empty
- **Authority order**: AGENTS.md → overdesign controller discussion → fins/host/engine/tool/ui design → R09 final plan → 全部 R09 artifacts
- **Prior Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-final-rereview-controller-adjudication.md` — verdict PASS / zero accepted finding
- **12-path manifest**:

| # | Path | Role |
|---|------|------|
| 1 | `dayu/cli/commands/fins.py` | CLI consumer、SIGINT、确定性关闭 |
| 2 | `dayu/fins/README.md` | Fins 开发手册 |
| 3 | `dayu/fins/direct_events.py` | direct 事件、协议错误与结果契约 |
| 4 | `dayu/fins/direct_stream.py` | ValidatedFinsEventStream 终态协议校验 |
| 5 | `dayu/fins/ingestion_runtime.py` | raw bridge、producer、direct stream 入口 |
| 6 | `dayu/service/README.md` | Service 层手册 |
| 7 | `dayu/service/fins_direct.py` | Service 透传层 |
| 8 | `tests/README.md` | 测试手册 |
| 9 | `tests/cli/test_fins_commands.py` | CLI 层测试 |
| 10 | `tests/fins/test_fins_direct_stream.py` | ValidatedFinsEventStream 契约测试 |
| 11 | `tests/fins/test_fins_ingestion_runtime.py` | Runtime 层测试 |
| 12 | `tests/service/test_fins_direct.py` | Service 层测试 |

## 1. Scope 与方法

本 review 把 accepted plan、完整 implementation、全部 code review/fix/re-review finding ledger、Controller validations 与最终 12-path product/test/README 组合行为作为一个 aggregate system 审查。重点审查跨层组合：

1. Fins unique validator owner 与 runtime producer / raw bridge / Service / CLI 的端到端行为
2. RESULT exactly-one-and-last 协议
3. primary / cleanup / cancel / SIGINT / consumer error 竞态
4. terminal_result availability
5. operation provenance / object identity
6. LLM-facing error projection
7. real async generator tests 与 coverage / smoke evidence 真实性
8. README / design truth
9. security retention（direct event 不泄漏内部治理标识）
10. deferred scope 无偷带

**判定标准**：新 finding 必须有直接代码反例、severity、semantic owner、最小当前修复。无 finding 则明确 zero accepted/material finding。

## 2. Cross-layer aggregate 审查

### 2.1 端到端调用链

```text
CLI (run_fins_direct_command)
  → Service (FinsDirectCommandService.download/process_filing/upload_filing/...)
    → Runtime (FinsIngestionRuntime.download/preprocess/upload)
      → _run_direct_stream (raw async generator via thread + queue bridge)
        → _run_direct_stream_producer (sync producer on daemon thread)
      → ValidatedFinsEventStream (终态协议校验 + raw source lifecycle owner)
```

#### 2.1.1 Runtime raw bridge（`_run_direct_stream`）

**审查结论：无 material finding。**

- 线程桥使用 `queue.Queue(maxsize=32)` + `asyncio.to_thread` 把同步 producer 桥接到 async consumer。
- `_direct_queue_get` 在 producer 线程意外死亡时返回合成 `_DirectStreamProducerDone()` 哨兵，防止 consumer 永久阻塞（`ingestion_runtime.py:4628-4651`）。
- `_put_direct_queue` 在 consumer 已关闭（cancellation_state 已取消）时丢弃后续事件并返回 False，防止 producer 卡在无人读取的队列上（`ingestion_runtime.py:4654-4683`）。
- `finally: cancellation_state.request_cancel()` 在 consumer 退出（正常或异常）时通知 producer 停止（`ingestion_runtime.py:2768-2769`）。
- producer 的 `_run_direct_stream_producer` 在 Exception 时构造 failure RESULT，并在 finally 中保证 `_DirectStreamProducerDone` 哨兵投递（`ingestion_runtime.py:2771-2801`）。

#### 2.1.2 ValidatedFinsEventStream 状态机

**审查结论：无 material finding。**

状态转换完整且互斥：

```
OPEN ──(first RESULT)──→ RESULT_BUFFERED
OPEN ──(StopAsyncIteration, no RESULT)──→ CLOSED + raise MISSING_RESULT
RESULT_BUFFERED ──(StopAsyncIteration)──→ RESULT_YIELDED (clean exhaustion)
RESULT_BUFFERED ──(duplicate RESULT)──→ CLOSED + raise DUPLICATE_RESULT
RESULT_BUFFERED ──(non-RESULT event)──→ CLOSED + raise EVENT_AFTER_RESULT
RESULT_YIELDED ──(__anext__)──→ CLOSED + StopAsyncIteration
ANY ──(_raise_primary_after_close)──→ CLOSED + re-raise primary
ANY ──(aclose)──→ CLOSED
CLOSED ──(aclose)──→ CLOSED (idempotent, direct_stream.py:168-169)
CLOSED ──(__anext__)──→ StopAsyncIteration (direct_stream.py:118-119)
```

关键 invariant 验证：

| Invariant | 证据 | 结论 |
|-----------|------|------|
| 首个 RESULT 被缓存，不在当前位置 yield | `direct_stream.py:132-138` — state OPEN 时遇 RESULT → RESULT_BUFFERED，continue | ✓ |
| clean exhaustion 后才 yield RESULT | `direct_stream.py:194-218` — `_finish_clean_exhaustion` 仅在 StopAsyncIteration 且 state=RESULT_BUFFERED 时返回 | ✓ |
| RESULT 后任何事件都产生 protocol error | `direct_stream.py:141-153` — state 非 OPEN（即 RESULT_BUFFERED）时，任何事件都 raise | ✓ |
| 无 RESULT 的 clean exhaustion 产生 MISSING_RESULT | `direct_stream.py:207-213` — state=OPEN 时 clean exhaustion → MISSING_RESULT | ✓ |
| CLOSED 是终态且幂等 | `direct_stream.py:118-119`（anext→StopAsyncIteration）、`168-169`（aclose→return） | ✓ |
| terminal_result 仅在 clean exhaustion 后可用 | `direct_stream.py:190-192` — 双条件 `_clean_exhaustion and _terminal_result_value is not None` | ✓ |

#### 2.1.3 Error precedence（primary vs cleanup）

**审查结论：无 material finding。**

三条 close-and-re-raise 路径均正确：

1. **Validator `_raise_primary_after_close`**（`direct_stream.py:220-240`）：先 close raw source，close_error 作为 primary 的 `__cause__`，始终重抛 primary。若 close 成功则 `raise primary`（line 240）。

2. **CLI `_raise_primary_after_fins_stream_close`**（`fins.py:255-272`）：相同模式，primary 保持身份，close_error 作为 cause。

3. **CLI `_cancel_and_drain_fins_event_task`**（`fins.py:669-697`）：child task 的 cleanup error 去重逻辑正确 — 若 cleanup_error is primary_error，返回 None 防止 self-cause/self-context 循环。测试 `test_cli_event_task_drain_deduplicates_same_primary_close_cause`（`test_fins_commands.py:1284-1313`）显式验证 `close_error.__cause__ is None and close_error.__context__ is None`。

#### 2.1.4 Service 透传层

**审查结论：无 material finding。**

- `FinsDirectCommandService` 是纯机械透传：构造 typed request → 调用 `self._runtime.download/preprocess/upload(...)` → 返回同一个 `ValidatedFinsEventStream` 实例。
- 测试 `test_fins_owned_protocol_error_fields_and_object_are_propagated_by_identity`（`test_fins_direct.py:494-527`）验证 `captured.value is owner_error`（object identity）。
- 测试 `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance`（`test_fins_direct.py:530-558`）和 `test_process_material_keeps_runtime_preprocess_protocol_error_provenance`（`test_fins_direct.py:561-589`）验证 Service 不把 runtime PREPROCESS 来源改成入口 alias。
- Service 不暴露 job handle、job event、`request_cancel`、durable cancel API（`test_fins_direct.py:611-622`）。

#### 2.1.5 CLI consumer 与确定性关闭

**审查结论：无 material finding。**

CLI 主流程（`_run_fins_direct_command_async`，`fins.py:210-252`）：

```text
open stream → consume events (with SIGINT handling) → close stream → return exit_code
                     ↓ (exception)
              close stream (with primary identity) → re-raise
```

关键路径全部有真实 async generator 测试：

| 路径 | 测试 | 验证点 |
|------|------|--------|
| 正常六命令 | `test_live_fins_commands_render_progress_and_terminal_summary` | 6 commands × exit_code + closed_streams==1 |
| consumer error + close cause | `test_cli_stream_owner_preserves_consumer_error_and_cleanup_cause` | primary identity + cause + close count |
| 外部 task cancellation | `test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause` | CancelledError + cause + close count |
| SIGINT 本地退出 | `test_cli_stream_owner_sigint_local_exit_closes_once` | exit_code=130 + cancellation_token + close count |
| SIGINT + close failure | `test_cli_stream_owner_sigint_close_failure_propagates_without_primary` | close_error identity + no cause/context + close count |
| child drain dedup | `test_cli_event_task_drain_deduplicates_same_primary_close_cause` | cleanup_error is None + no self-cycle |
| child drain keep cause | `test_cli_event_task_drain_keeps_close_cause_when_child_already_done` | cleanup_error is close_error + close count |
| duplicate result → CLI | `test_fins_owned_duplicate_result_uses_existing_cli_error_presentation` | exit=1 + message + closed_streams==1 |
| missing result → CLI | `test_fins_owned_missing_result_uses_existing_cli_error_presentation` | exit=1 + message + closed_streams==1 |
| stream exception → CLI | `test_stream_failure_propagates_to_cli_error` | exit=1 + no job_id leak + closed_streams==1 |

**SIGINT 处理审查**（`_wait_for_terminal_handling_sigint`，`fins.py:602-666`）：

- 使用 `asyncio.wait(FIRST_COMPLETED)` 同时等待 event consumer 和 SIGINT monitor。
- 第一次 SIGINT：取消 event_task，请求取消 token，渲染 cancel 消息。等待 event_task 完成（带 `asyncio.CancelledError`）。若 child cancellation 带了 cleanup cause，离开 handler 后传播。若无 cause，返回 `_CliDirectLocalExit(exit_code=EXIT_KEYBOARD_INTERRUPT)`。
- 异常路径：`_cancel_and_drain_fins_event_task` 取消并等待仍在运行的 event_task，cleanup error 作为 primary 的 cause 传播。
- `finally` 块保证 SIGINT monitor 关闭和 sigint_task 取消。

### 2.2 RESULT exactly-one-and-last 验证

**审查结论：无 material finding。**

Validator 的 `__anext__` 循环（`direct_stream.py:117-153`）正确实现：

1. 首个 RESULT 在 OPEN 状态遇到 → 缓存到 `_buffered_result_event`，设置 `_terminal_result_value`，状态转 RESULT_BUFFERED，`continue`（不 yield）。
2. RESULT_BUFFERED 状态遇到任何事件 → 构造相应 protocol error（DUPLICATE_RESULT 或 EVENT_AFTER_RESULT），调用 `_raise_primary_after_close`。
3. raw source StopAsyncIteration → `_finish_clean_exhaustion`：若 OPEN → MISSING_RESULT；若 RESULT_BUFFERED → yield buffered RESULT。
4. RESULT yield 后下一次 `__anext__` → CLOSED + StopAsyncIteration。

Service 与 CLI 无任何 duplicate/missing 检查逻辑，完全依赖 validator。Service `_collect_events` 使用 `async for` 机械消费；CLI `_consume_fins_direct_events` 同样机械消费并通过 `events.terminal_result` 获取终态。

### 2.3 Operation provenance / object identity

**审查结论：无 material finding。**

Provenance 链路：

```
CLI command_name (e.g., "process_filing")
  → Service operation_kind=FinsOperationKind.PROCESS_FILING (for logging)
  → Runtime direct_operation_kind=FinsOperationKind.PREPROCESS (runtime truth)
  → ValidatedFinsEventStream._operation_kind=FinsOperationKind.PREPROCESS
  → FinsDirectStreamProtocolError.operation_kind=FinsOperationKind.PREPROCESS
```

关键判决：`process_filing` 和 `process_material` 的 runtime 真源 operation_kind 是 `PREPROCESS`（因为底层都是 `FinsPreprocessRequest`）。Service 只在日志中使用入口名，不改变 runtime provenance。测试 `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance` 和 `test_process_material_keeps_runtime_preprocess_protocol_error_provenance` 分别在 Service 和 CLI 层验证。

Object identity 契约：Service 返回的 stream 就是 runtime 返回的同一个 `ValidatedFinsEventStream` 实例。测试 `assert stream is runtime.returned_streams[-1]` 显式验证。

### 2.4 LLM-facing error projection

**审查结论：无 material finding。**

`FinsDirectStreamProtocolError` 是 `ValueError` 子类，包含三个 typed 字段：

- `reason: FinsDirectStreamProtocolErrorKind` — `"missing_result"` / `"duplicate_result"` / `"event_after_result"`
- `operation_kind: FinsOperationKind` — 用户可读操作类型
- `message: str` — 用户可读且非空的错误说明

CLI 展示使用 `exc.message`（`fins.py:201`），不把内部 enum value 或治理标识暴露为业务事实。错误展示格式为 `"dayu-cli {command_name}: {message}"`，与既有 CLI error presentation 一致。

`FinsEvent`、`FinsProgress`、`FinsResultSummary` 的 `_validate_safe_text` 守卫拒绝内部治理文本（job_id、sequence、cursor、resume token、绝对路径、provider raw payload、"财报正文"）进入 direct event（`direct_events.py:36-51` 和 `444-479`）。

### 2.5 Real async generator tests 与 coverage 真实性

**审查结论：无 material finding。**

三层测试全部使用真实 `ValidatedFinsEventStream` 包装真实 `async def` raw generator，不是 cast/fake/mock：

| 层 | Fake 策略 | 验证 |
|----|-----------|------|
| Runtime | `_ConsumerAbortDownloadAdapter` + 真实 `_run_direct_stream` bridge | `test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation` — 验证 raw finally、cancel check、late event fence |
| Service | `_FakeIngestionRuntime._raw_stream` 是真实 async generator | `_validated_stream` 通过 `ValidatedFinsEventStream(source, operation_kind=...)` 构造 |
| CLI | `_FakeFinsDirectService._raw_stream` 是真实 async generator | `_stream` 通过 `ValidatedFinsEventStream(source, operation_kind=...)` 构造 |

关键行为全部使用真实 Python async generator 语义：

- `finally` 块在 `aclose()` / `GeneratorExit` / task cancellation 时执行 → 测试验证 `closed_streams` 计数器递增。
- `asyncio.CancelledError` 与 `__cause__` 链 → 测试显式验证 `captured.value.__cause__ is close_error`。
- `StopAsyncIteration` 耗尽 → 测试验证 `anext(stream)` 抛出 `StopAsyncIteration`。
- `aclose()` 幂等 → 测试 `await stream.aclose(); await stream.aclose()` 后 `closed_streams == 1`。

**Smoke evidence**：test 文件使用 `pytest.mark.asyncio` 标记的 `async def` 测试函数，通过 pytest-asyncio 运行真实 event loop。`_FakeIngestionRuntime` 的 `_raw_stream` 是真实 `async def` 用 `yield` 产出事件，不是 `AsyncMock` 或 `MagicMock`。

### 2.6 README / design truth

**审查结论：无 material finding。**

Fins README（`dayu/fins/README.md`）的关键声明与代码一致：

| README 声明 | 代码证据 | 结论 |
|-------------|----------|------|
| "Direct stream 入口是 plain `def`，立即返回 `ValidatedFinsEventStream`" | `ingestion_runtime.py:2145-2182` — `def download(...) -> ValidatedFinsEventStream` | ✓ |
| "validator 是恰好一个且最后一个 RESULT 的唯一 Fins owner" | `direct_stream.py:1-6` module docstring + 完整状态机 | ✓ |
| "缓存首个 RESULT，直到 raw source 正常耗尽后才发布" | `direct_stream.py:132-138` + `194-218` | ✓ |
| "缺少/重复/RESULT 后仍有事件分别抛出同一 typed contract" | `direct_stream.py:207-213` + `141-153` | ✓ |
| "Service 与 CLI 只机械消费，不再次扫描或重建错误" | Service `fins_direct.py:201` `return self._runtime.download(...)` — 透传；CLI `fins.py:700-722` — `async for` + `events.terminal_result` | ✓ |
| "Direct event 不包含 job id、sequence、cursor..." | `direct_events.py:36-51` `_DISALLOWED_TEXT_FRAGMENTS` + `_validate_safe_text` | ✓ |
| "组件树: direct_events.py / direct_stream.py" | `README.md:439-440` | ✓ |

README 的 `Agent更新约束【必须遵守】` 要求"代码真源高于历史 plan、review artifact"，本 review 已按当前代码逐条验证 README 声明。

### 2.7 Security retention

**审查结论：无 material finding。**

Direct event 安全守卫机制完整：

1. `_DISALLOWED_TEXT_FRAGMENTS` 禁止 job_id、sequence、cursor、resume token、tool_call_id、storage path、raw payload、provider payload、绝对路径、财报正文等内部标识（`direct_events.py:36-51`）。
2. `_FINS_JOB_ID_PATTERN` 正则拒绝 hex job ID（`direct_events.py:27-29`）。
3. `_ABSOLUTE_POSIX_PATH_PATTERN` 和 `_ABSOLUTE_WINDOWS_PATH_PATTERN` 拒绝绝对路径（`direct_events.py:30-35`）。
4. 所有 FinsEvent 字段（message、ticker、filing_kind、document_label、progress.stage、result.title、result.error_message、detail.label/value）在构造时经 `_validate_safe_text` 校验。
5. CLI 诊断日志使用有界截断（`_FINS_DIAGNOSTIC_TEXT_MAX_CHARS=120`）和数量限制（`_FINS_DIAGNOSTIC_DETAIL_MAX_ITEMS=4`），防止日志体积失控。

### 2.8 Deferred scope 无偷带

**审查结论：无 material finding。**

逐项验证 R09 实现树不包含以下 deferred scope：

| Deferred 项 | 当前树状态 | 证据 |
|-------------|-----------|------|
| Issue 142 | 未触及 | grep 无匹配 |
| Issue 151 | 未触及 | grep 无匹配 |
| Issue 175 (process isolation) | 继续是既有 deferred owner | Controller adjudication line 51-52 |
| Issue 177 | 未触及 | grep 无匹配 |
| Issue 178 | 未触及 | grep 无匹配 |
| Web/WeChat/render tracker | 未触及 | CLI 层只处理 stdout/stderr |
| Topic 8/9 | 未触及 | grep 无匹配 |
| 统一 tool authorization | 未触及 | 无 tool auth 相关变更 |

`ValidatedFinsEventStream` 不 import Host、Engine、Service assembly、Web/WeChat adapter 或 tool authorization。`FinsDirectStreamProtocolError` 不包含 tool_call_id、job_id 或 Host governance state。

## 3. Prior findings final ledger

基于 Controller 裁决（`code-final-rereview-controller-adjudication.md` §3）并经本 aggregate review 独立复核：

| Finding | Controller 裁决 | Aggregate 复核 | 最终状态 |
|---------|----------------|---------------|----------|
| R09-CR-F01 (CLI consumer close) | closed | CLI 正常/异常/外部取消/SIGINT 全部路径经确定性 close boundary → `closed_streams == 1` | **closed** |
| R09-CR-F02 (real async generators) | closed | 三层测试全部使用真实 `async def` generator + `ValidatedFinsEventStream`，无 cast/fake escape | **closed** |
| R09-CR-F03 (GeneratorExit/finally/close) | closed | `_run_direct_stream` finally、`_close_source_once` at-most-once、cleanup cause 全有 owner-level test | **closed** |
| R09-CR-F04 (README signature) | closed | README 三个 `ValidatedFinsEventStream` 返回签名与代码一致 | **closed** |
| F01 self-cause follow-up | closed | `test_cli_event_task_drain_deduplicates_same_primary_close_cause` 验证 `close_error.__cause__ is None and close_error.__context__ is None` | **closed** |
| R09-RR-F01 (README tree) | closed | README main-component tree 精确列出 `direct_events.py` / `direct_stream.py` | **closed** |

**Aggregate 新增 finding：0。**

## 4. Cross-layer race condition deep-dive

### 4.1 Producer finish vs consumer close race

**Scenario**: Producer 已 put `_DirectStreamProducerDone` 到 queue；consumer 在读取前调用 `aclose()`。

**Analysis**:
1. `aclose()` → state = CLOSED → `_close_source_once()` → `self._source.aclose()`
2. Raw generator finally 运行 `cancellation_state.request_cancel()`
3. Producer 已完成（`_DirectStreamProducerDone` 已入队），cancel 是 no-op
4. `_run_direct_stream` 的 generator frame 被清理
5. Queue 中的 `_DirectStreamProducerDone` 成为 garbage（consumer 不会再读取）

**结论**：无危害。Producer 已完成，无资源泄漏。Validator state 已是 CLOSED，后续操作被吸收。  **无 finding**。

### 4.2 Producer thread dies without sentinel

**Scenario**: Producer 线程因非 Exception 的 BaseException（如 `KeyboardInterrupt` 在错误线程）退出，未执行 finally 中的 `_DirectStreamProducerDone` put。

**Analysis**:
1. `_direct_queue_get` 检测 thread 不再 alive → 返回合成 `_DirectStreamProducerDone()`（`ingestion_runtime.py:4649-4651`）
2. `_run_direct_stream` while loop breaks
3. `_finish_clean_exhaustion` 被调用
4. 若 state 仍是 OPEN（无 RESULT 被缓冲）→ raise `MISSING_RESULT`
5. 若 state 是 RESULT_BUFFERED → yield RESULT

**结论**：合成哨兵保证 consumer 不会永久阻塞。MISSING_RESULT 是正确语义（stream 确实没有完整终态）。  **无 finding**。

### 4.3 Double close idempotency

**Scenario**: Consumer 连续调用 `stream.aclose()` 两次。

**Analysis**:
1. 第一次：state → CLOSED，`_close_source_once()` → `_source_close_attempted = True`，调用 `self._source.aclose()`
2. 第二次：state 已是 CLOSED → 直接 return（`direct_stream.py:168-169`）

测试 `test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation` 显式验证 `await stream.aclose(); await stream.aclose()` 后 `closed_streams == 1`。  **无 finding**。

### 4.4 terminal_result after aclose

**Scenario**: Consumer 在 clean exhaustion 后调用 `aclose()`，然后读取 `terminal_result`。

**Analysis**:
1. Clean exhaustion: `_finish_clean_exhaustion` 设置 `_clean_exhaustion = True`，`_terminal_result_value` 已设置
2. `aclose()`: state = CLOSED，但 `_clean_exhaustion` 是 True → 不清除 buffer（`direct_stream.py:171-173`）
3. `terminal_result`: 检查 `_clean_exhaustion`（True）和 `_terminal_result_value is not None`（True）→ 返回

**结论**：`terminal_result` 在 close 后仍可用。  但需注意调用顺序：必须先用 `async for` 耗尽 stream，再读 `terminal_result`，最后 `aclose()`。  **无 finding**。

## 5. README 完备性检查

### 5.1 Fins README

- 设计意图 ✓：明确 "Fins direct stream 是 CLI / Service direct 调用的用户可见进度边界"
- 架构边界 ✓：Fins 不依赖 Host，Fins 不负责 Host durable truth
- 接口 ✓：三个 direct stream 入口列出了 `-> ValidatedFinsEventStream` 返回类型
- 关键执行路径 ✓：Direct stream 路径说明了 raw bridge + validator + Service/CLI 机械消费
- 状态机 ✓：`FinsResultStatus` 三元组
- 主要组件 ✓：组件树列出 `direct_events.py` / `direct_stream.py`
- 稳定边界 ✓：Fins 不负责 Host/Engine/Service/UI/ToolRuntime 的职责

### 5.2 Service README

`dayu/service/README.md` 中 R09 相关声明与代码一致：

| README 声明 | 代码证据 | 结论 |
|-------------|----------|------|
| "terminal 协议由 Fins validator 唯一拥有" | `direct_stream.py:1-6` module docstring + `dayu/service/fins_direct.py` 无任何 protocol error 构造 | ✓ |
| "Service 的 protocol、public 与 private direct methods 都以 plain `def` 直接返回 runtime 提供的同一个 `ValidatedFinsEventStream`" | `fins_direct.py:163-204` — `def download(...) -> ValidatedFinsEventStream` 直接 `return self._runtime.download(...)` | ✓ |
| "不 await、迭代、包装或重建 stream" | Service 无 `async for`、无 stream wrapper、无 `ValidatedFinsEventStream` 构造 | ✓ |
| "missing、duplicate、event-after-result 与 terminal availability 均由 Fins validator 判定一次" | Service 无任何 protocol error 构造或 `terminal_result` 条件判断 | ✓ |
| "调用方通过 `async for` 消费 PROGRESS 与唯一 terminal RESULT，并在 clean exhaustion 后读取 validator 的 terminal result" | CLI `_consume_fins_direct_events` 使用 `async for` + `events.terminal_result`（`fins.py:700-722`） | ✓ |
| "Service direct API 不暴露 job id、event sidecar、cursor 或 `request_cancel(job_id)`" | `test_fins_direct.py:611-622` 显式断言 | ✓ |

### 5.3 Tests README

`tests/README.md` 中 R09 相关声明与实际测试覆盖一致：

| README 声明 | 代码证据 | 结论 |
|-------------|----------|------|
| "Fins direct：覆盖 reusable Fins direct Service boundary 的...同一个 `ValidatedFinsEventStream` identity pass-through" | `test_fins_direct.py:494-527` — `captured.value is owner_error` + `assert stream is runtime.returned_streams[-1]` | ✓ |
| "Fins-owned typed protocol error object 与 runtime `PREPROCESS` provenance 不被 Service alias 重建" | `test_fins_direct.py:530-589` — process_filing/process_material 双层验证 | ✓ |
| "`tests/fins/test_fins_direct_stream.py` 以真实 `async def` generator 和独立 typed observation state 覆盖唯一 Fins validator owner" | `test_fins_direct_stream.py:40-75` — `_controlled_raw_stream` 是真实 `async def` generator；`_RawStreamObservation` 是独立 typed dataclass | ✓ |
| "progress 顺序、RESULT 缓存至 clean exhaustion、missing / duplicate / event-after-result typed reason" | `test_fins_direct_stream.py:244-366` — 四个独立测试 | ✓ |
| "result-then-error 不泄漏 success" | `test_fins_direct_stream.py:497-528` — `observed == []` | ✓ |
| "upstream exception/cancellation object identity" | `test_fins_direct_stream.py:369-422` — `captured.value is primary` | ✓ |
| "`GeneratorExit` / `finally`" | `test_fins_direct_stream.py:40-74` — `_controlled_raw_stream` 显式计数 `generator_exit_calls` / `finally_calls` | ✓ |
| "primary 与 cleanup close failure chaining" | `test_fins_direct_stream.py:425-494` — `primary.__cause__ is close_error` | ✓ |
| "显式/repeated close 至多一次" | `test_fins_direct_stream.py:531-628` — `generator_exit_calls == 1` | ✓ |
| "`terminal_result` 在 OPEN / RESULT_BUFFERED / abortive / clean 四类状态的 availability 与同一结果实例" | `test_fins_direct_stream.py:631-742` — 四个独立测试；`stream.terminal_result is summary` | ✓ |

以上 10 条声明均在 `tests/fins/test_fins_direct_stream.py`（742 行，16 个测试函数）中有直接对应测试，本 aggregate review 已全量走读。

## 6. Findings

**未发现实质性问题（zero accepted/material finding）。**

经过对全部 12-path 的端到端、跨层、状态机、竞态、错误优先级、对象身份、LLM-facing 投影、测试真实性、README 真值和 deferred scope 的 exhaustive aggregate review，无直接代码反例可支撑新 finding。

## 7. Open Questions

无。

## 8. Residual Risk

以下条目为既有设计观察或 deferred owner 记录，不构成 R09 finding：

| 条目 | Owner | 说明 |
|------|-------|------|
| Producer daemon thread 无 join | Fins runtime（既有设计选择，non-actionable） | daemon thread 在阻塞 I/O 中时进程 exit 不等待；cooperative cancellation 已通过 `_DirectCancellationChecker` 传播。目前无 join 需求。 |
| Queue polling interval (0.05s) | Fins runtime（既有设计选择，non-actionable） | `_direct_queue_get` 的 50ms 超时在延迟与 CPU 使用间取平衡；CLI 场景可接受。 |
| Issue 175 process isolation | Fins Docling process isolation / Issue 175 | 既有 deferred owner，不在 R09 scope。 |

## 9. Final verdict

- **Verdict**: **PASS / ZERO ACCEPTED OR MATERIAL FINDING**.
- **Current accepted/open finding**: 0.
- **New material finding**: 0.
- **Blocker**: 0.
- **R09 aggregate deepreview**: complete.
- **Next gate**: R09 final closeout（仅当 Controller 裁决本 aggregate review 后授权）。

## 10. Artifact metadata

- **File**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-aggregate-deepreview-ds.md`
- **Reviewer**: AgentDS
- **Lines**: 见外部计算
- **Immutable target verified**: ✓（HEAD、manifest、diff、staged 均与 Controller adjudication §1 一致）
