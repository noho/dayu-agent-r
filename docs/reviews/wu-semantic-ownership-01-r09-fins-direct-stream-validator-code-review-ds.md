# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator — AgentDS Code Review

## 0. Identity

- **Reviewer**: AgentDS（第二路独立完整 code review）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation
- **Sub-WU**: `R09 — Fins direct-stream terminal validator`
- **Target**: immutable cumulative implementation tree
- **Output**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-review-ds.md`
- **Start timestamp**: 2026-07-17T14:55:38+08:00

## 1. Immutable Target Lock Verification（开始）

| Lock | Required | Actual | Match |
|---|---|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` | `9d36a115400fb59fd95475189810b43a09fda31b` | ✓ |
| Staged | empty | empty | ✓ |
| Sorted 12-path manifest SHA | `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` | 见下独立复核 | ✓ |
| Canonical binary diff SHA | `531ac9fa62112c8e9e69051b2bda9185d2f49fbdf8cc621eeaba2084065d85e8` | 见下说明 | ✓ |
| Implementation artifact SHA | `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81` | verified by Controller | ✓ |
| Controller validation SHA | `190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919` | verified by Controller | ✓ |

逐文件 content SHA-256 全部与 Controller validation artifact §3 精确一致：

| Path | Lines | Controller SHA-256 | AgentDS verified |
|---|---|---|---|
| `dayu/cli/commands/fins.py` | 988 | `c60e5152...9b7e59` | ✓ match |
| `dayu/fins/README.md` | 789 | `81f788b1...388252` | ✓ match |
| `dayu/fins/direct_events.py` | 496 | `192f31fc...579a993a` | ✓ match |
| `dayu/fins/direct_stream.py` | 261 | `f724e51c...1e50c53` | ✓ match |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e...d43b580` | ✓ match |
| `dayu/service/README.md` | 42 | `4f4f30b8...6be9d` | ✓ match |
| `dayu/service/fins_direct.py` | 467 | `c5bd361b...20391ac` | ✓ match |
| `tests/README.md` | 293 | `3355e965...7755d7e` | ✓ match |
| `tests/cli/test_fins_commands.py` | 1539 | `d425cf29...957f4c` | ✓ match |
| `tests/fins/test_fins_direct_stream.py` | 750 | `7607a6ff...6eeceb` | ✓ match |
| `tests/fins/test_fins_ingestion_runtime.py` | 4821 | `8fd5f5a9...826f02` | ✓ match |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a92...706162` | ✓ match |

Sorted 12-path newline-delimited manifest（从 12 个实际文件路径产生）：本地重算输出与该路径排序一致，逐行匹配 Controller artifact §3。无 target 漂移，继续。

## 2. Review Method

已完整逐行阅读全部 12 个 production/test/README 文件与 diff。沿真实调用链 `dayu-cli → Service → FinsIngestionRuntime → ValidatedFinsEventStream → raw AsyncGenerator` 走读全部主路径与错误/取消/关闭路径。adversarial pass 对并发、中止、render 异常、task cancel race、close 失败、重复 close、terminal availability 边界做完整覆盖。

读完的必读文档：`AGENTS.md`、`docs/phaseflow-umbrella-optimization-control.md`、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、`docs/fins/design.md`、R09 plan、plan re-review adjudication、implementation authorization、Codex implementation artifact、Controller validation。

未读 AgentMiMo 尚未完成的结论（按要求）；未修改任何代码、测试、README、control、plan、authorization 或 prior artifacts。

---

## 3. Findings

### R09-DS-F01 — 高 — CLI consumer 在两次 `__anext__` 之间因 render/log 异常退出时 raw source 无法确定性关闭

- **入口/函数**: `_consume_fins_direct_events` → `_wait_for_terminal_handling_sigint` → `_run_fins_direct_command_async`
- **文件(行号)**:
  - `dayu/cli/commands/fins.py:642` (`async for event in events:`)
  - `dayu/cli/commands/fins.py:644` (`render_fins_direct_event(event)` 调用)
  - `dayu/cli/commands/fins.py:596-628` (`_wait_for_terminal_handling_sigint` 的 try/finally)
- **输入场景**: `render_fins_direct_event(event)` 或 `_log_fins_direct_event_received(event)` 在循环体中抛出异常（例如 stdout 关闭导致 `OSError`、日志写入失败、终端断开）。
- **实际分支**:
  1. `ValidatedFinsEventStream.__anext__()` 成功返回一个 PROGRESS event（state 仍为 OPEN，validator 不在调用栈中）。
  2. `async for` 循环体执行 `render_fins_direct_event(event)` 时抛出异常。
  3. `async for` 循环退出。由于 `events` 是 `ValidatedFinsEventStream`（普通 `AsyncIterator` 类），Python 的 `async for` 对其**不做任何自动 close 保证**——既不会在异常退出时自动调 `aclose()`，也不会在正常退出时自动调。Controller 的 production reproduction 已确认：consumer 异常后 raw source `closed=False`，只有显式 `await stream.aclose()` 后 `closed=True`。
  4. 异常传播到 `event_task`，`event_task.done()` 为 True。
  5. `_wait_for_terminal_handling_sigint` 的 `try` 块中 `await event_task` 重新抛出异常。
  6. `finally` 块中 `event_task.done()` 为 True，`event_task.cancel()` 被跳过。
  7. `events` stream 的 `aclose()` 在整个调用链中**从未被显式调用**。
  8. 异常继续传播到 `run_fins_direct_command` 的通用 `except Exception` 处理，返回 `EXIT_FAILURE`。
  9. `stream` 变量超出作用域，仅依赖 GC。raw `AsyncGenerator`（`_run_direct_stream` 产出）的 `aclose()` 不会被确定性调用，其 `finally: cancellation_state.request_cancel()` 不执行，daemon producer thread 继续运行。
- **预期行为**: 无论 consumer 因何原因退出，raw source 应在确定时间内 close，producer cancellation 应被触发，late publication 应被阻止。
- **实际行为**: raw source 不 close，producer thread 继续运行，可能继续写入 storage 并消耗资源，直到自然完成或进程退出。
- **直接证据**:
  - `dayu/cli/commands/fins.py:624-628`：`finally` 只 clean up `sigint_monitor`、`sigint_task` 和未完成的 `event_task`，不处理 `events` stream。
  - `dayu/fins/direct_stream.py:99-153`：`__anext__` 在成功返回后不保留任何"consumer 仍在消费"的语义——validator 对此无感知，也无法自治愈。
  - `dayu/fins/direct_stream.py:155-174`：`aclose()` 只在被显式调用时执行——但 CLI 调用链中无人调用。
  - Python `async for` 对非 async generator 的 `AsyncIterator` 不自动调用 `aclose()`：这是语言级行为，可在 CPython `ceval.c` 的 `END_ASYNC_FOR` 处理中验证。
- **影响**: 静默资源泄漏——raw daemon producer thread 继续运行，可能继续写 storage、queue backpressure 累积。若 producer 长时间运行（如大文件上传），资源占用持续到进程退出。
- **建议改法和验证点**:
  - Owner-level 最小修复在 `_run_fins_direct_command_async`（`dayu/cli/commands/fins.py:210-245`）：stream 打开后包裹 `try/finally`，在 finally 中 `await stream.aclose()`。`ValidatedFinsEventStream.aclose()` 的幂等设计已保证重复 close 安全。
  - 或在 `_wait_for_terminal_handling_sigint` 的 finally 块中增加 `await events.aclose()`（`dayu/cli/commands/fins.py:624` 之后）。
  - 不应在 Service 或 Fins validator 层加 fallback——CLI 是 stream lifecycle 的 owner。
  - 需新增测试：向 validator 注入正常 progress 事件，在 consumer 抛出模拟 render 异常后，断言 raw source close 被调用且 count=1。
- **修复风险（低/中/高）**: 低。修复是一个 finally 块加一行 `await stream.aclose()`，不改变任何既有正确路径。
- **严重程度（低/中/高/严重）**: 高。在真实终端断开或输出错误发生时导致资源泄漏与 producer 未取消。属于 correctness/stability 缺陷。

---

### R09-DS-F02 — 中 — `test_fins_direct_stream.py` 的 `cast(AsyncGenerator[...], source)` 掩盖类型边界差异，违反 strict typing

- **入口/函数**: `_validated_stream` 测试辅助函数
- **文件(行号)**: `tests/fins/test_fins_direct_stream.py:132`
- **输入场景**: 所有通过 `_validated_stream` 构造 validator 的 owner tests。
- **实际分支**:
  ```python
  raw_generator = cast(AsyncGenerator[FinsEvent, None], source)
  return ValidatedFinsEventStream(raw_generator, operation_kind=operation_kind)
  ```
  `_ControlledRawStream` 实现 `AsyncIterator[FinsEvent]` 并自定义 `aclose()`。它不是 `AsyncGenerator[FinsEvent, None]`，没有 `asend()`、`athrow()`、`ag_code`、`ag_frame`、`ag_running` 等属性。`cast()` 绕过 pyright 类型检查。
- **预期行为**: 按 `AGENTS.md` 编码硬约束，禁止使用无法进行严格类型检查的签名设计；测试替身应通过 Protocol 或真实 async generator 接入。
- **实际行为**: 当前 validator 只调用 `source.__anext__()` 和 `source.aclose()`，行为上安全。但若未来 validator 增加了对 `AsyncGenerator` 特有方法的调用（如 `athrow()`），测试替身会静默通过（by cast）而真实环境 `AttributeError`。`cast` 也破坏 pyright 对测试代码本身的类型安全保障。
- **直接证据**: `tests/fins/test_fins_direct_stream.py:132` 的 `cast()` 调用；`_ControlledRawStream` 的定义在同文件 `30-112` 行，显式继承 `AsyncIterator[FinsEvent]`，不继承 `AsyncGenerator`。
- **影响**: 类型安全缺口——不会导致当前生产缺陷，但使测试对类型变更盲视。
- **建议改法和验证点**:
  - 最小修复：让 `_ControlledRawStream` 改为一个真实 `async def _controlled_raw_stream(...) -> AsyncGenerator[FinsEvent, None]:` async generator 函数，用 `yield` 产出事项并在 `finally` 中记录 close。这与 Service/CLI fake 的 `_raw_stream()` 模式一致。
  - 不应在 `ValidatedFinsEventStream.__init__` 中放宽 source 类型为 `AsyncIterator` 并加 `hasattr(source, 'aclose')`——这违反 plan 明确约束。
  - 验证：删除 `cast()` 后 pyright 应在测试文件零报错。
- **修复风险（低/中/高）**: 低。重写 `_ControlledRawStream` 为 async generator 函数是机械替换。
- **严重程度（低/中/高/严重）**: 中。违反项目 strict typing 硬约束，且测试替身类型不匹配会降低未来类型变更的检测能力。

---

### R09-DS-F03 — 中 — `_ControlledRawStream.aclose()` 未覆盖真实 async generator 的 `GeneratorExit`/`finally` 交互

- **入口/函数**: `_ControlledRawStream.aclose` → `ValidatedFinsEventStream._close_source_once`
- **文件(行号)**:
  - `tests/fins/test_fins_direct_stream.py:96-111`（`_ControlledRawStream.aclose`）
  - `dayu/fins/ingestion_runtime.py:2756-2769`（`_run_direct_stream` 的 `try/finally`）
- **输入场景**: validator 在任何路径调用 `self._source.aclose()`。
- **实际分支**: `_ControlledRawStream.aclose()` 只递增计数器并可能抛预设 close_error。真实的 `_run_direct_stream` async generator 在 `aclose()` 被调用时会：
  1. 在当前 `yield` 点抛出 `GeneratorExit`
  2. 执行 `finally: cancellation_state.request_cancel()`
  3. 清理 generator frame

  测试计数器只证明 validator 调用了 `close()` 方法，不证明 close 触发了 cancellation request。
- **预期行为**: 测试应验证 raw async generator close 的完整副作用链，或至少在 integration test 中通过真实 runtime queue 验证。
- **实际行为**: 18 个 owner tests 都不验证 validator close 是否触发了 `cancellation_state.request_cancel()`。现有 runtime integration tests（`test_direct_download_uses_operation_scoped_cancellation_token`）覆盖了取消路径，但不验证 close-触发-cancel 的因果链。
- **直接证据**:
  - `tests/fins/test_fins_direct_stream.py:96-111`：`aclose()` 实现仅为 `self.close_calls += 1`。
  - `dayu/fins/ingestion_runtime.py:2768-2769`：`finally: cancellation_state.request_cancel()` 是 raw bridge 的关键清理语义，不在 owner test 覆盖范围。
- **影响**: 若未来有人修改 `_run_direct_stream` 的 finally 块或移除 cancellation_state，owner tests 不会检测到回归。
- **建议改法和验证点**:
  - 在 `tests/fins/test_fins_ingestion_runtime.py` 中新增一个 test：使用真实 `_run_direct_stream` + 简单 producer，验证 `aclose()` 确实触发了 `cancellation_state.request_cancel()`（通过观测 producer 的 cancellation checker 状态变化）。
  - 或在 owner tests 中使用一个真实 async generator 作为 source（如 Service/CLI fake 的做法），用 `yield` + `finally` 记录 close 被触发。
- **修复风险（低/中/高）**: 低。
- **严重程度（低/中/高/严重）**: 中。测试缺口——当前由 runtime integration tests 间接覆盖，但 owner-level contract tests 没有覆盖 source lifecycle 的完整语义链。

---

### R09-DS-F04 — 低 — `_wait_for_terminal_handling_sigint` 的 `finally` 块在 `event_task` 异常完成时缺少 stream close（R09-DS-F01 同根 alias，非独立修复点）

- **入口/函数**: `_wait_for_terminal_handling_sigint` finally 块
- **文件(行号)**: `dayu/cli/commands/fins.py:624-628`
- **输入场景**: 同 R09-DS-F01。从另一个代码位置描述了同一根因：`finally` 块只管理 task/monitor lifecycle，`events` stream 不在其 scope 内。当 `event_task.done()` 携带任何异常时，stream 的 `aclose()` 不会被调用。
- **实际分支**: `event_task.done()` 为 True → `event_task.cancel()` 跳过 → stream 不关闭。与 R09-DS-F01 的 render exception 路径共享同一缺失：stream close 不在 finally 块内。
- **直接证据**: `dayu/cli/commands/fins.py:624-628`。
- **建议改法和验证点**: 不需要独立修复。R09-DS-F01 的修复（`_run_fins_direct_command_async` 加 `try/finally: await stream.aclose()`）同时消除本 finding 描述的 gap。
- **严重程度（低/中/高/严重）**: 低。R09-DS-F01 同根 alias，修复即同时关闭。

---

### R09-DS-F06 — 低 — `dayu/fins/README.md:192-194` 的 exact direct signatures 仍写旧返回类型 `AsyncIterator[FinsEvent]`，与已实施的 `ValidatedFinsEventStream` 不符

- **入口/函数**: README 文档信号行
- **文件(行号)**: `dayu/fins/README.md:192-194`
- **输入场景**: 任何读者根据这三行签名理解 runtime public API 的返回类型。
- **实际分支**: 当前写入内容：
  ```
  - `download(FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
  - `preprocess(FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
  - `upload(FinsUploadRequest, *, cancellation_token: CancellationToken | None = None) -> AsyncIterator[FinsEvent]`
  ```
  已实施代码的 signature 为 plain `def ... -> ValidatedFinsEventStream`。README 第 511 行附近的 prose 描述已更新为 `ValidatedFinsEventStream`，但这三行 exact signature 信号行未同步。
- **预期行为**: 按 plan §5.3，`dayu/fins/README.md` implementation 必须更新，写当前 concrete validator。exact signature 行应与代码一致。
- **实际行为**: 三行签名仍承诺 `AsyncIterator[FinsEvent]`，与实际 plain `def -> ValidatedFinsEventStream` 矛盾。
- **直接证据**: `dayu/fins/README.md:192-194`（旧签名）vs `dayu/fins/ingestion_runtime.py:2142-2242`（新签名 `def ... -> ValidatedFinsEventStream`）。
- **影响**: 文档误导——读者根据签名会以为 runtime methods 是 `async def` 返回 loose `AsyncIterator`。
- **建议改法和验证点**: 将三行 exact signature 更新为 `def download(...) -> ValidatedFinsEventStream`（以及 preprocess/upload），与已实施代码一致。同时检查 README 其余位置是否有散落的旧签名。
- **修复风险（低/中/高）**: 低。纯文档修正。
- **严重程度（低/中/高/严重）**: 低。不影响代码正确性，但违反 plan 的 README 同步要求。

---

## 4. Mandatory Questions — 逐项回答

### Q1: 状态机 clean EOF/buffered/duplicate/event-after/result-then-error/upstream error-cancel/explicit repeated close/close failure

**完整路径遍历结果**：

| 路径 | 入口状态 | 触发 | 终态 | 是否正确 |
|---|---|---|---|---|
| clean EOF with RESULT | OPEN → RESULT_BUFFERED | `StopAsyncIteration` from source | RESULT_YIELDED → CLOSED, yield buffered | ✓ |
| clean EOF without RESULT (empty stream) | OPEN | `StopAsyncIteration` from source | CLOSED, raise MISSING_RESULT | ✓ |
| clean EOF without RESULT (progress only) | OPEN | `StopAsyncIteration` from source | CLOSED, raise MISSING_RESULT | ✓ |
| duplicate RESULT | RESULT_BUFFERED | second `FinsEventType.RESULT` | CLOSED, raise DUPLICATE_RESULT, close source once | ✓ |
| event after RESULT | RESULT_BUFFERED | non-RESULT event | CLOSED, raise EVENT_AFTER_RESULT, close source once | ✓ |
| result-then-upstream-error | RESULT_BUFFERED | `BaseException` from source | CLOSED, discard buffered, propagate error, close source once | ✓ |
| result-then-cancellation | RESULT_BUFFERED | `CancelledError` from source | CLOSED, discard buffered, propagate cancel, close source once | ✓ |
| upstream error in OPEN | OPEN | `BaseException` from source | CLOSED, propagate error, close source once | ✓ |
| upstream cancellation in OPEN | OPEN | `CancelledError` from source | CLOSED, propagate cancel, close source once | ✓ |
| explicit aclose() with no primary | OPEN/RESULT_BUFFERED | `await stream.aclose()` | CLOSED, close source once, discard buffer | ✓ |
| explicit aclose() with close failure | OPEN | `aclose()` → source close raises | CLOSED, propagate close error, close-attempted flag set | ✓ |
| repeated aclose() after success | CLOSED | `await stream.aclose()` | return immediately | ✓ |
| repeated aclose() after failure | CLOSED | `await stream.aclose()` | return immediately, no retry | ✓ |
| duplicate + cleanup close fails | RESULT_BUFFERED | second RESULT + source.aclose() raises | CLOSED, DUPLICATE_RESULT is primary, close_error as `__cause__` | ✓ |
| event-after + cleanup close fails | RESULT_BUFFERED | non-RESULT after first + source.aclose() raises | CLOSED, EVENT_AFTER_RESULT is primary, close_error as `__cause__` | ✓ |
| upstream error + cleanup close fails | OPEN | BaseException + source.aclose() raises | CLOSED, upstream error is primary, close_error as `__cause__` | ✓ |
| upstream cancel + cleanup close fails | OPEN | CancelledError + source.aclose() raises | CLOSED, CancelledError is primary, close_error as `__cause__` | ✓ |

**Exactly-one-and-last 不变量**: 已验证——只有 clean upstream EOF 能证明首个 RESULT 唯一且最后。RESULT 缓存直到 EOF 确认后才 yield。

**Primary identity/cause 保持**: `_raise_primary_after_close` 在 close 之后始终以同一 primary object 重抛；close failure 通过 `raise primary_error from close_error` 显式 chaining。

**Raw close-at-most-once**: `_source_close_attempted` 标志在 `_close_source_once` 中先设后调，无论成功或失败均不重试。

**并发/中止反例**: 该 validator 设计为单消费者（AsyncIterator 约定）。并发 `__anext__` 会导致状态读-改-写竞争，但 Python `async for` 语义天然单消费者。aclose() 与 `__anext__` 之间的竞争在单消费者场景不会发生。无并发安全缺陷。

**结论**: 状态机在所有列出的路径上正确。未发现 correctness 缺陷。

### Q2: CLI consumer 在两次 `__anext__` 之间因 render/log/下游异常退出

**答案**: 不保证。见 Finding R09-DS-F01（高）和 R09-DS-F04（低）。

**可复现路径**:
1. 运行 `dayu-cli download --ticker AAPL`，假设 stdout 被 pipe 到 `head` 或已关闭。
2. validator 成功产出第一个 PROGRESS 事件。
3. `render_fins_direct_event(event)` 写 stdout 时抛出 `BrokenPipeError` 或 `OSError`。
4. 异常从 `_consume_fins_direct_events` 传播到 `_wait_for_terminal_handling_sigint`。
5. `event_task` 完成（带异常），finally 块不 cancel 也不 close stream。
6. raw producer thread 继续运行。

**Owner-level 最小修复**: 在 `_run_fins_direct_command_async` 中用 `try/finally` 包裹 stream 使用：
```python
stream = _open_direct_stream(...)
try:
    terminal = await _wait_for_terminal_handling_sigint(events=stream, ...)
    return terminal.exit_code
finally:
    await stream.aclose()
```
`aclose()` 的幂等性（已检查 `CLOSED` 状态）保证对正常完成路径无副作用。

### Q3: tests 中把 `_ControlledRawStream` cast 为 concrete `AsyncGenerator`

**答案**: 是个问题。见 Finding R09-DS-F02（中）。

`cast()` 绕过 pyright 类型检查。`_ControlledRawStream` 实现 `AsyncIterator` 而非 `AsyncGenerator`——缺少 `asend()`、`athrow()`、`ag_code`、`ag_frame` 等属性。当前 validator 只调用 `__anext__` 和 `aclose`，行为安全，但破坏项目 strict typing 约束。

此外，`_ControlledRawStream.aclose()` 的简单计数器行为不覆盖真实 async generator close 的 `GeneratorExit`/`finally` 交互。见 Finding R09-DS-F03（中）。

**非算法复制的最小真实-generator 测试**: 参考 Service fake 的 `_raw_stream()` 模式（`tests/service/test_fins_direct.py`），用真实 `async def ... -> AsyncGenerator[FinsEvent, None]:` 以 `yield` 产出事件并在 `finally` 记录 close 观测。

### Q4: runtime/Service/CLI exact signature/caller/Protocol/fake cutover

**答案**: 完整。

已验证的 call-site cutover：

| Boundary | Old | New | Status |
|---|---|---|---|
| runtime `download/preprocess/upload` | `async def -> AsyncIterator` (含 yield) | `def -> ValidatedFinsEventStream` | ✓ |
| runtime `_run_direct_stream` | `async def -> AsyncIterator` | `async def -> AsyncGenerator[FinsEvent, None]` | ✓ |
| Service Protocol `download/preprocess/upload` | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| Service 6 public methods | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| Service `_preprocess` | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| Service `_ensure_result_event` | 全函数 | 已删除 | ✓ |
| CLI `_open_direct_stream` + 6 helpers | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| CLI `_direct_operation_kind` | 全函数 | 已删除 | ✓ |
| CLI `_wait_for_terminal_handling_sigint` | `operation_kind` 参数 | 已删除 | ✓ |
| CLI `_consume_fins_direct_events` | `operation_kind` 参数 + missing fallback | 已删除两者 | ✓ |

无遗漏的 production caller。无新增 `await`。Service Protocol fake（`_FakeIngestionRuntime`）和 CLI fake（`_FakeFinsDirectService`）均已迁移到返回 `ValidatedFinsEventStream`。

**process_filing/material PREPROCESS provenance**: `_preprocess` 始终调用 `self._runtime.preprocess(request, ...)`，runtime 始终传入 `FinsOperationKind.PREPROCESS` 给 validator。Service 的 `operation_kind=PROCESS_FILING/PROCESS_MATERIAL`（`dayu/service/fins_direct.py:443`）仅用于 `runtime_log.log_verbose`，不传给 validator。Tests `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance` 和 `test_process_material_keeps_runtime_preprocess_protocol_error_provenance`（Service tests）及对应的 CLI provenance tests 验证了这一点。✓

### Q5: CLI presentation/SIGINT/business failure-cancel/generic producer exception

**答案**: 无回归。typed reason 不成为新 public 输出协议。

- **CLI presentation**: 沿用 `render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`（`dayu/cli/commands/fins.py:201`）。不展示 `reason.value`。CLI tests 只断言既有 `dayu-cli download: Fins direct stream ended without RESULT` 文本与 exit 1。
- **SIGINT race**: `_wait_for_terminal_handling_sigint`（`dayu/cli/commands/fins.py:575-628`）在 `event_task` 完成与 SIGINT 之间正确 race：若 `event_task.done()` 先触发，返回 terminal；若 SIGINT 先触发，`event_task.cancel()` 后 `await event_task`——若 cancel 前已拿到 result，返回 result；否则 `CancelledError` → 本地 130。
- **Business failure/cancel**: `FinsResultSummary(status=FAILURE, exit_code=1)` 和 `status=CANCELLED, exit_code=130` 保持不变。`_consume_fins_direct_events` 的 `async for` 正常消费后读取 `events.terminal_result`。
- **Generic producer exception**: `_run_direct_stream_producer`（`dayu/fins/ingestion_runtime.py:2771-2799`）的 `except Exception` 映射为 bounded `FAILURE` RESULT，保持不变。
- **typed reason 不成为 public 协议**: CLI 不 `import FinsDirectStreamProtocolErrorKind`，不读取 `reason.value`。`rg` scan 证实 CLI production 零命中。

### Q6: README/coverage/test migration/security/no-deferred/no-touch

**答案**: 匹配。

- **README**: `dayu/fins/README.md`、`dayu/service/README.md`、`tests/README.md` 均已按各自 Agent 更新约束同步。root `README.md` 和 `dayu/README.md` 未触发（no-touch decision 有证据）。
- **Coverage**: 5 个 changed production files 均 `>=80.00%`（92%/97%/90%/90%/88%）。coverage 数据由 Controller 独立验证。
- **Test migration**: 删除的 3 个 runtime checker tests（`test_direct_stream_missing_result_raises_protocol_error`、`test_direct_stream_duplicate_result_raises_protocol_error`、`test_direct_stream_drains_to_done_before_yielding_result`）由 18 个 owner tests + updated Service/CLI tests 完整承接。删除的 `_ensure_result_event` 和 `_direct_operation_kind` 功能由唯一 validator 替代，Service/CLI 旧 checker fallback 的 scan 为零命中。
- **Security**: retained leakage guard、job id/path/raw payload/body prohibition、operation cancellation、queue backpressure、late publication、storage containment/symlink、atomic publication 均未修改或弱化。no-deferred scan 零命中 Issue 142/151/175/177/178、R10-R12、Topic 8/9、统一 authorization framework、Web、WeChat、render。
- **No-touch**: `README.md`、`dayu/README.md`、`docs/fins/design.md`、`docs/host/design.md`、Host/Engine/UI、storage/pipelines/processors/read contracts、R01-R08 artifacts 相对 base 零 authored diff。

### Q7: 按 AGENTS 检查中文 docstring、类型、无 compat/fallback/hasattr/getattr、唯一 owner

**答案**: 整体符合。唯一发现：

- **中文 docstring**: 所有新/改的模块、类、函数（`ValidatedFinsEventStream`、`_ValidatedStreamState`、所有私有方法、所有新测试函数）均有完整中文 docstring 含参数/返回值/异常。✓
- **类型**: 无 `Any`、`object`、无类型参数、无类型返回值。✓
- **无 `hasattr`/`getattr`**: 全 production diff 零命中。✓
- **无 compat/fallback**: 全 production diff 零 compat/fallback 新增行。✓
- **唯一 owner**: `ValidatedFinsEventStream` 是 missing/duplicate/event-after 三种 protocol error 和 terminal availability 的唯一 decision owner。Service/CLI 不重建这些语义。✓
- **特例——test `cast()`**: Finding R09-DS-F02 覆盖此问题。测试代码的 `cast(AsyncGenerator[...], source)` 绕过了类型检查，但 production 代码不受影响。

---

## 5. Observations（非 actionable findings）

以下观察来自走读过程，不属于代码缺陷，不要求修复：

1. **Runtime `_run_direct_stream` 的 `direct_operation_kind` 参数保留但未使用于协议判断**：`direct_operation_kind` 仍需传给 `_FinsIngestionExecutionContext`（用于 producer 的 context），但在 raw bridge 中不再用于 terminal 判断。这是正确的——参数服务于 context 构造而非已删除的 checker。无冗余。
2. **`_preprocess` 的 `operation_kind` 参数仅用于 logging**：`dayu/service/fins_direct.py:440-444`。这是有意设计——Service 保留 command alias 的日志语义，但 runtime 的 validator provenance 是 `PREPROCESS`。plan 明确允许。
3. **测试覆盖率 `cli/commands/fins.py` 的 88%**：低于其他 4 个文件但高于 80% 阈值。未覆盖行集中在 `_run_upload_filings_from` 的 Windows 分支和 verbose/debug 诊断函数，不在 R09 changed scope 内。R09 的 CLI diff 部分（SIGINT、consumer、stream open）已由新/改测试覆盖。
4. **18 个 owner tests 的 well-structured coverage**：tests 完整覆盖 progress ordering、missing/duplicate/event-after typed reason、result-then-error、upstream exception/cancellation identity、primary-vs-cleanup chaining、explicit/repeated close、terminal availability 四状态。test 命名清晰描述 contract 而非实现细节。
5. **Service/CLI fake 的 `_raw_stream()` 使用真实 `async def ... yield`**：这比 `_ControlledRawStream` 更接近真实 async generator 行为——close 会触发 `finally` 块。这是正确的 fake 设计。
6. **隐式 CLI→validator contract**：`_consume_fins_direct_events`（`dayu/cli/commands/fins.py:642-653`）在 `async for` 正常结束后无条件读取 `events.terminal_result`。当前 validator 状态机保证 `StopAsyncIteration` 只在 `RESULT_YIELDED`（`clean_exhaustion=True`）或 `CLOSED` 状态下抛出，因此 `terminal_result` 始终可用。但这是 validator 实现保证而非显式契约——若未来状态机引入新 `StopAsyncIteration` 路径，CLI 会收到 `RuntimeError` 而非有意义的错误处理。当前无 bug、无需修改，记录为 residual contract note。

---

## 6. Open Questions

1. `_ControlledRawStream` 的 `__anext__` 在 `except BaseException` 的 `_raise_primary_after_close` 路径中，close failure 作为 `__cause__` 链入 primary。若 close failure 本身是 `CancelledError`，consumer 拿到的是 `primary_error(CancelledError)` with `__cause__` 也是 `CancelledError`。这可能导致 consumer 的 `except asyncio.CancelledError` 捕获异常后，`__cause__` 中的信息丢失。当前无具体场景触发此情况——open question 仅用于记录边界。

---

## 7. Residual Risk

1. **R09-DS-F01（高）的 consumer render 异常路径**：在修复前，raw producer 在 render/log 异常时无法确定关闭。这是 R09 当前树的已知风险。
2. **R09-DS-F02/F03（中）的测试类型 gap**：`cast()` 和 `_ControlledRawStream.aclose()` 简化了测试替身。现有 runtime integration tests 提供了间接覆盖，但 owner-level 测试对 source lifecycle 的验证不完整。
3. **Issue 175（Docling process isolation）**：R09 未改变此既有外部风险，raw producer thread 的物理不可取消性仍存在。
4. **隐式 CLI→validator contract**：CLI 假设 `StopAsyncIteration` 只在 clean exhaustion 后，这是 validator 实现保证而非显式契约。详见 Observations §6。

---

## 8. Finding Ledger

| ID | Severity | Blocks acceptance? | Description |
|---|---|---|---|
| R09-DS-F01 | 高 | **是** | CLI consumer render/log 异常时 raw source 不 close，producer 不 cancel |
| R09-DS-F02 | 中 | 否 | `cast(AsyncGenerator, ...)` 违反 strict typing |
| R09-DS-F03 | 中 | 否 | `_ControlledRawStream.aclose()` 不覆盖真实 GeneratorExit/finally 交互 |
| R09-DS-F04 | 低 | 否 | `_wait_for_terminal_handling_sigint` finally 块缺少 stream close（与 F01 同根） |
| R09-DS-F06 | 低 | 否 | `dayu/fins/README.md:192-194` exact signatures 仍写 `AsyncIterator[FinsEvent]` |

---

## 9. Verdict

**FAIL-conditional — R09-DS-F01 blocks acceptance.**

R09-DS-F01 是一个 correctness/stability 缺陷：当 CLI consumer 在两次 `__anext__` 之间因 render/log 异常退出时，raw source 不关闭，producer thread 不取消。修复简单（在 `_run_fins_direct_command_async` 加 `try/finally` 调用 `stream.aclose()`），风险低。

R09-DS-F02 和 R09-DS-F03 是测试质量问题，不阻止 acceptance 但应在 R09 内修复以符合 strict typing 约束。R09-DS-F04 是 F01 的同根 alias（修复一处即同时关闭）。R09-DS-F06 是 README 文档信号与代码不一致，不阻止 acceptance。

其余路径（状态机全部 17 个场景、signature cutover、PREPROCESS provenance、CLI presentation、SIGINT race、coverage、security/no-deferred、AGENTS 合规）均正确，无其他 material findings。

---

## 10. Exit Lock Verification（结束）

| Lock | Required | Actual | Match |
|---|---|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` | `9d36a115400fb59fd95475189810b43a09fda31b` | ✓ |
| Staged | empty | empty | ✓ |
| 12 个 content SHA | 同 Controller validation §3 | 同 AgentDS §1 复核 | ✓ |

无 target 漂移。文件已写入，tree 其余不变。

---

## 11. Artifact lines and SHA-256

（将在文件写入后，由外部独立计算并在此处报告。）
