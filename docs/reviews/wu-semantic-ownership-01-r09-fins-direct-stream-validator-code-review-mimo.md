# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator Code Review — AgentMiMo

## Scope

- Mode: immutable cumulative implementation review
- Branch: `phaseflow/host-issues-control`
- Base / HEAD: `9d36a115400fb59fd95475189810b43a09fda31b`
- 12-path sorted manifest SHA-256: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` ✓
- Canonical cumulative binary diff SHA-256: `531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8` ✓
- Implementation artifact: 274 lines, SHA-256 `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81` ✓
- Controller validation: 104 lines, SHA-256 `190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919` ✓
- Staged tree: empty ✓
- Output file: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-mimo.md`

Review 从 12 个已锁定路径的完整代码、测试与 README 逐行走读，不只读 artifact 或测试结论。

## Target Lock Verification

开始与结束均独立核对。所有 immutable target locks 匹配：

| Lock | Expected | Actual |
|---|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` | ✓ |
| 12-path manifest SHA-256 | `ce024b6...` | ✓ |
| Binary diff SHA-256 | `531ac9f...` | ✓ |
| Implementation artifact lines | 274 | 274 ✓ |
| Implementation artifact SHA-256 | `3c16b65...` | ✓ |
| Controller validation lines | 104 | 104 ✓ |
| Controller validation SHA-256 | `190a1e6...` | ✓ |
| Staged tree | empty | empty ✓ |

## Findings

### 01-未修复-高-CLI consumer 异常时不关闭 ValidatedFinsEventStream，raw source 泄漏

- **入口/函数**: `dayu/cli/commands/fins.py:631` `_consume_fins_direct_events`
- **文件(行号)**: `dayu/cli/commands/fins.py:631-653`
- **输入场景**: consumer 在 `async for event in events` 循环体内因 `render_fins_direct_event`、`_log_fins_direct_event_received` 或其它下游异常退出
- **实际分支**: `async for` 对 `AsyncIterator`（非 `AsyncGenerator`）**在正常退出和异常退出时均不调用 `aclose()`**。Python `END_ASYNC_FOR` 字节码只对真实 `async generator` 触发 cleanup；对 `AsyncIterator` 的手动 `aclose()` 方法，`async for` 从不调用
- **预期行为**: consumer 异常退出时必须关闭 `ValidatedFinsEventStream`，进而关闭 raw source 并请求 producer cancellation
- **实际行为**: stream 未关闭，raw source generator 的 `finally` 块不执行，`_DirectStreamCancellationState.request_cancel()` 不被调用，daemon producer thread 继续运行
- **直接证据**:
  - `ValidatedFinsEventStream` 继承 `AsyncIterator[FinsEvent]`（`direct_stream.py:44`），只有 `__aiter__` + `__anext__`，不是 `AsyncGenerator`
  - CPython `END_ASYNC_FOR` 对 `tp_as_async->am_anext` 结果只检查 `StopAsyncIteration`，不调用 `aclose()`
  - 实测确认：`async for` 对带 `aclose()` 的 `AsyncIterator`，正常退出和异常退出均不调用 `aclose()`
  - `_consume_fins_direct_events`（`fins.py:631-653`）无 `try/finally` 保护
  - `_wait_for_terminal_handling_sigint`（`fins.py:575-628`）在 `event_task` 异常时不关闭 stream
  - `run_fins_direct_command`（`fins.py:178-207`）catch `FinsDirectStreamProtocolError` 后不关闭 stream
- **影响**: raw source generator 泄漏，daemon producer thread 继续运行，可能导致 late publication 到 storage。进程退出时 daemon thread 终止，但非短生命周期 CLI 场景下有实际风险
- **建议改法和验证点**:
  - 最小修复：`_consume_fins_direct_events` 加 `try/finally`：
    ```python
    async def _consume_fins_direct_events(
        events: ValidatedFinsEventStream,
    ) -> FinsResultSummary:
        try:
            async for event in events:
                _log_fins_direct_event_received(event)
                render_fins_direct_event(event)
                if event.result is not None:
                    runtime_log.log_verbose(...)
            return events.terminal_result
        finally:
            await events.aclose()
    ```
  - 测试：注入 render 异常，断言 `source_close_called` 为 True 且异常正确传播
- **修复风险（低/中/高）**: 低。纯 additive，不改变状态机或 public contract
- **严重程度（低/中/高/严重）**: 高。producer 泄漏和 late publication 在非短生命周期场景有实际风险

### 02-未修复-中-测试 helper _ControlledRawStream 掩盖 async for cleanup 缺陷

- **入口/函数**: `tests/fins/test_fins_direct_stream.py:30` `_ControlledRawStream`
- **文件(行号)**: `tests/fins/test_fins_direct_stream.py:30-111`
- **输入场景**: `test_task_cancellation_closes_runtime_stream`（`tests/service/test_fins_direct.py:592`）验证 stream 关闭
- **实际分支**: `_FakeIngestionRuntime._raw_stream` 是真实 `async def` generator，其 `finally` 块在 GC 时执行。当 task 取消后，`asyncio.CancelledError` 传播触发 async generator cleanup，GC 运行 `finally` 块
- **预期行为**: 测试应直接验证 `ValidatedFinsEventStream.aclose()` 被调用，而非依赖 GC 的偶然行为
- **实际行为**: Service 的 `test_task_cancellation_closes_runtime_stream` 通过 GC 间歇性通过。`_ControlledRawStream` 的 `close_calls` 只在显式 `aclose()` 调用时计数，不反映 GC cleanup
- **直接证据**:
  - `_FakeIngestionRuntime._raw_stream`（`test_fins_direct.py:165-182`）是 `async def` generator，`finally: self.closed_streams += 1`
  - Python async generator 的 `aclose()` 在 GC 时调用 `finally` 块，但时机不确定
  - `_ControlledRawStream`（`test_fins_direct_stream.py:30`）实现 `AsyncIterator` 不是 `AsyncGenerator`，`cast(AsyncGenerator, source)` 掩盖了这一事实
  - 无测试验证 consumer 异常后 `ValidatedFinsEventStream.aclose()` 被调用
- **影响**: 测试不覆盖 consumer 异常路径的 cleanup，导致 Finding 01 未被发现
- **建议改法和验证点**:
  - 新增 owner test：consumer 异常后断言 `source.close_calls == 1`
  - 新增 CLI integration test：render 异常后断言 stream 关闭
- **修复风险（低/中/高）**: 低。纯测试补充
- **严重程度（低/中/高/严重）**: 中。测试覆盖缺陷，不直接影响生产

### 03-未修复-低-README dayu/fins/README.md:192-194 direct signatures 陈旧

- **入口/函数**: `dayu/fins/README.md:192-194`
- **文件(行号)**: `dayu/fins/README.md:192-194`
- **输入场景**: 开发者阅读 README 了解 runtime public API
- **实际分支**: README 写 `-> AsyncIterator[FinsEvent]`，实际实现返回 `ValidatedFinsEventStream`
- **预期行为**: README 应反映实际返回类型 `ValidatedFinsEventStream`
- **实际行为**: 三行签名仍写旧类型 `AsyncIterator[FinsEvent]`
- **直接证据**:
  - `dayu/fins/README.md:192`: `download(FinsDownloadRequest, ...) -> AsyncIterator[FinsEvent]`
  - `dayu/fins/README.md:193`: `preprocess(FinsPreprocessRequest, ...) -> AsyncIterator[FinsEvent]`
  - `dayu/fins/README.md:194`: `upload(FinsUploadRequest, ...) -> AsyncIterator[FinsEvent]`
  - 实际实现（`ingestion_runtime.py:2145-2259`）：`def download(...) -> ValidatedFinsEventStream`
- **影响**: 开发者误以为 runtime 返回裸 `AsyncIterator`，不知道 `ValidatedFinsEventStream` 的 terminal contract
- **建议改法和验证点**:
  - 三行签名改为 `-> ValidatedFinsEventStream`
  - 在签名后补充 validator 的 `aclose()` 语义说明
- **修复风险（低/中/高）**: 低。纯文档修正
- **严重程度（低/中/高/严重）**: 低。文档不一致，不影响运行时

## Open Questions

无。

## Residual Risk

- full-Fins 有 1 个仓库既有 environment skip（Docling），与 R09 changed owner/source 无交集。
- pytest 3 个既有 edgartools deprecation warnings，未升级为 error。
- Issue 175 继续拥有 Fins Docling process isolation；R09 不实施。
- `_ControlledRawStream` cast 为 `AsyncGenerator` 是 test-only typing concern，不影响行为正确性。

## Verdict

**FAIL / conditional**。

| Finding | Severity | Block |
|---|---|---|
| 01 — CLI consumer 异常时不关闭 stream | 高 | 是 |
| 02 — 测试 helper 掩盖 cleanup 缺陷 | 中 | 是（配合 01） |
| 03 — README direct signatures 陈旧 | 低 | 否 |

Finding 01 是 runtime 级缺陷：`async for` 对 `AsyncIterator` 不调用 `aclose()`，导致 consumer 异常时 raw source 泄漏。修复为 `_consume_fins_direct_events` 加 `try/finally` 保护（owner-level 最小修复，不改变状态机或 public contract），配合 Finding 02 的测试补充。Finding 03 为文档同步，不 block。
