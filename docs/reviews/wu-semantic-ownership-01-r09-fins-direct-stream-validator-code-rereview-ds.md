# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator — AgentDS Complete Code Re-Review

## 0. Identity

- **Reviewer**: AgentDS（独立 complete code re-review）
- **Umbrella**: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation
- **Sub-WU**: `R09 — Fins direct-stream terminal validator`
- **Gate**: 本轮是 cumulative S1+S2+code-review-fix 完整树的独立 re-review；不是新 WU/issue
- **Output**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-ds.md`
- **Start timestamp**: 2026-07-17T16:26:34+08:00

## 1. Immutable Target Lock Verification

### 1.1 HEAD 与 staged

| Lock | Expected | Actual | Match |
|---|---|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` | `9d36a115400fb59fd95475189810b43a09fda31b` | ✓ |
| Staged | empty | empty | ✓ |

### 1.2 12-path cumulative manifest SHA-256

- **Expected**: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`
- **Actual（独立重算）**: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4`
- **Match**: ✓

### 1.3 12-path content locks

| Path | Lines | Expected SHA-256 | Actual (独立重算) | Match |
|---|---:|---|---|---|
| `dayu/cli/commands/fins.py` | 1057 | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` | 同 | ✓ |
| `dayu/fins/README.md` | 789 | `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7` | 同 | ✓ |
| `dayu/fins/direct_events.py` | 496 | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` | 同 | ✓ |
| `dayu/fins/direct_stream.py` | 261 | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` | 同 | ✓ |
| `dayu/fins/ingestion_runtime.py` | 6920 | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` | 同 | ✓ |
| `dayu/service/README.md` | 42 | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` | 同 | ✓ |
| `dayu/service/fins_direct.py` | 467 | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` | 同 | ✓ |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` | 同 | ✓ |
| `tests/cli/test_fins_commands.py` | 1803 | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` | 同 | ✓ |
| `tests/fins/test_fins_direct_stream.py` | 742 | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` | 同 | ✓ |
| `tests/fins/test_fins_ingestion_runtime.py` | 4925 | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` | 同 | ✓ |
| `tests/service/test_fins_direct.py` | 720 | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` | 同 | ✓ |

### 1.4 先决 artifact locks

| Artifact | Lines | Expected SHA-256 | Match |
|---|---|---|---|
| accepted plan | 773 | `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` | ✓ (Controller validation 锁) |
| original implementation | 274 | `3c16b65678e234f3f88379c01a371eb3059f5bb52ff68ac1db772a5c135d2d81` | ✓ (Controller validation 锁) |
| original Controller validation | 104 | `190a1e61f165446a3ad9ebccb3de53b1c954df7186076b1405ca2797721ba919` | ✓ (Controller validation 锁) |
| MiMo code review | 131 | `ee79e2e19b794110becc72133ce1b1627827006c0be75050e45f0e07a9cb5df3` | ✓ (adjudication 锁) |
| DS code review | 367 | `0f1a46b3ca17a2c9b69d32f16ce028e0ef29c4f2829c9b47c7d8b6a900825363` | ✓ (adjudication 锁) |
| Controller adjudication | 181 | `4fbc1e7bb25c3cbe5af61b40753fdc147e083e28913de39000c6a912382bccbc` | ✓ (fix artifact entry 锁) |
| Codex fix artifact | 271 | `c9affe9935d2825284c10bcccd61169c3836cb5076d13de90bb517787e8c85d7` | ✓ (Controller fix validation 锁) |
| Controller fix validation | 141 | `5a6a12c5fc4679de26bc841402fe93d91847fd9015a2c9e54266d04dd8ebfd5b` | ✓ (entry 锁) |
| canonical cumulative binary diff | — | `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d` | ✓ (Controller fix validation 锁) |

### 1.5 未读取但非 target 的 working tree 路径

下列路径在 `git status` 中显示但不在 12-path target manifest 中：

- `docs/host/issues-implementation-control.md`（Controller-owned，R09 entry 前即存在）
- `docs/reviews/` 下全部 review/adjudication/fix/validation artifacts（review evidence，非 implementation target）
- `dayu/fins/direct_stream.py` 与 `tests/fins/test_fins_direct_stream.py`（在 manifest 内，为新增文件）
- `workspace/tmp/` 下的临时 coverage/smoke 产物（非 durable diff）

reviewer 没有修改、stage 或纳入这些路径。

## 2. Review Method

已对全部 12 个 product/test/README 文件执行完整逐行走读。沿真实调用链：

```text
run_fins_direct_command
  → _run_fins_direct_command_async
    → _open_direct_stream → Service → FinsIngestionRuntime.download/preprocess/upload
      → ValidatedFinsEventStream(source=_run_direct_stream(...), ...)
    → _wait_for_terminal_handling_sigint
      → _consume_fins_direct_events
        → async for event in events (ValidatedFinsEventStream.__anext__)
      → asyncio.wait(event_task, sigint_task) race
    → stream.aclose() / _raise_primary_after_fins_stream_close
    → _cancel_and_drain_fins_event_task
```

走读覆盖全部主路径、typed protocol error 路径、consumer-body error 路径、外部 task cancellation 路径、
SIGINT 路径、completed-child race 路径和 close failure 路径。adversarial pass 对并发、中止、render/log
异常、task cancel race、close 失败、重复 close、primary/cause/context identity、asyncio done-task outcome、
真实 AsyncGenerator GeneratorExit/finally、runtime raw bridge cooperative cancellation、
late-publication fence、signature/provenance/identity propagation、CLI presentation、
README/coverage/security/no-touch/deferred scope 做完整覆盖。

已读全部必读文档：`AGENTS.md`、`docs/fins/design.md`、R09 accepted plan、MiMo 首轮 review、
DS 首轮 review、Controller adjudication、Codex fix artifact、Controller fix validation。

---

## 3. 原 Finding Closure 独立复核

### R09-CR-F01（HIGH）— CLI stream owner 未在所有退出路径关闭 raw source

**Closure evidence**:

1. `_run_fins_direct_command_async`（`dayu/cli/commands/fins.py:229-252`）：stream 创建后立即进入
   `try/except/finally` owner boundary。
   - 正常路径（line 251）：`await stream.aclose()` 在 `return terminal.exit_code` 前确定性执行。
   - 异常路径（lines 246-250）：`_raise_primary_after_fins_stream_close(stream, primary_error)`
     在重抛 primary 前执行 `await stream.aclose()`；close 失败时执行
     `raise primary_error from close_error`，保持同一 primary object 与显式 cause。

2. `_raise_primary_after_fins_stream_close`（`dayu/cli/commands/fins.py:255-272`）：
   typed `NoReturn` helper，覆盖无 close failure（直接重抛 primary）和 close failure
   （primary from close_error chaining）两条路径。不吞 primary，不覆盖 cleanup cause。

3. `_cancel_and_drain_fins_event_task`（`dayu/cli/commands/fins.py:669-697`）：
   取消并 drain child consumer task。对未完成 task 先 cancel 再 await outcome；
   对已完成 task 直接读同一 outcome（不依赖 asyncio 对第二次 await 保留 cause 的非契约行为）。
   以 object identity 去重 `cancellation_error is primary_error` 与
   `cancellation_error.__cause__ is primary_error`，消除 `raise e from e` 自因环。
   distinct cleanup cause 原样返回。

4. `_wait_for_terminal_handling_sigint`（`dayu/cli/commands/fins.py:602-667`）：
   SIGINT handler 先保存 child `CancelledError.__cause__` 为 `close_error`，
   离开 `except asyncio.CancelledError` handler 后以 `raise close_error` 传播，
   避免 Python 隐式 `__context__` 写入。然后由外层 `except BaseException`
   调用 `_cancel_and_drain_fins_event_task` 做 completed-child drain 并保持同一 primary。

5. **真实可复现路径验证**：
   - `test_cli_stream_owner_preserves_consumer_error_and_cleanup_cause`（log/render 两路参数化）：
     consumer body 异常后断言 `captured.value is primary_error`、
     `captured.value.__cause__ is close_error`、`service.closed_streams == 1`、
     validator 已 CLOSED（`StopAsyncIteration`）。
   - `test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause`：
     外部 task cancellation 注入后断言 `CancelledError` 的 `__cause__ is close_error`、
     `service.closed_streams == 1`。
   - `test_cli_stream_owner_sigint_local_exit_closes_once`：
     SIGINT 正常路径（无 close failure）断言 `exit_code == EXIT_KEYBOARD_INTERRUPT`、
     `closed_streams == 1`、cancellation token 已请求取消。
   - `test_cli_stream_owner_sigint_close_failure_propagates_without_primary`：
     SIGINT + close failure 路径断言 `captured.value is close_error`、
     `__cause__ is None`、`__context__ is None`、`closed_streams == 1`。
   - `test_cli_event_task_drain_keeps_close_cause_when_child_already_done`：
     completed-child race 中 distinct cleanup cause 保留。
   - `test_cli_event_task_drain_deduplicates_same_primary_close_cause`：
     completed-child race 中 same-primary cause 去重（`cleanup_error is None`、
     `close_error.__cause__ is None`、`close_error.__context__ is None`）。

**独立复核**：代码路径和测试覆盖均已验证全部退出路径（success、typed protocol error、
consumer log/render error、外部 cancellation、SIGINT normal、SIGINT close failure、
completed-child same-primary/different-primary race）均确定性关闭 stream，
primary/cause/context 身份均保持。**CLOSED**。

### R09-CR-F02（MEDIUM）— owner tests 用不真实 cast 绕过 source 类型契约

**Closure evidence**:

1. 原 `_ControlledRawStream`（`AsyncIterator` 子类 + `cast(AsyncGenerator, ...)`）已删除。
2. 替换为 `_controlled_raw_stream`（`tests/fins/test_fins_direct_stream.py:40-74`）：
   真实 `async def ... -> AsyncGenerator[FinsEvent, None]`，使用 `yield` 产出事件、
   `GeneratorExit` 处理、`try/finally` 记录终结事实。
3. 新增 `_RawStreamObservation` dataclass（`tests/fins/test_fins_direct_stream.py:31-38`）：
   独立 typed state 记录 `next_calls`、`generator_exit_calls`、`finally_calls`。
4. `_validated_stream` helper（`tests/fins/test_fins_direct_stream.py:77-98`）：
   直接接收 `AsyncGenerator[FinsEvent, None]`，无 cast、无 loose probing、无 `hasattr/getattr`。
5. Full pyright zero errors，测试代码零类型错误。

**独立复核**：false cast seam 已根除；所有 owner tests 使用真实 `AsyncGenerator`，
`_RawStreamObservation` 提供严格 typed observation。fix artifact scan 确认
`_ControlledRawStream`、`cast(AsyncGenerator...)` 零命中。**CLOSED**。

### R09-CR-F03（MEDIUM）— 未验证真实 generator close 的 cancellation/finally 因果链

**Closure evidence**:

1. **Owner tests 层**（`tests/fins/test_fins_direct_stream.py`）：全部 18 个 tests
   使用真实 `async def` generator + `_RawStreamObservation`，在每个 test 中断言
   `generator_exit_calls`（`GeneratorExit` 次数）和 `finally_calls`（`finally` 执行次数）。
   覆盖 clean success、missing、duplicate、event-after、result-then-error、
   upstream error/cancellation identity、primary-vs-cleanup chaining、
   explicit/repeated close success/failure、terminal availability 四类状态。
   直接证据示例：
   - `test_validated_stream_duplicate_result_is_primary_and_closes_source_once`：
     断言 `generator_exit_calls == 1`、`finally_calls == 1`——证明 validator close
     触发了真实 `GeneratorExit` 和 `finally`。
   - `test_validated_stream_repeated_aclose_closes_source_once`：
     断言第二次 `aclose()` 不增加 `generator_exit_calls`——证明 at-most-once guard。

2. **Production raw-bridge integration 层**（`tests/fins/test_fins_ingestion_runtime.py:1946-1985`）：
   `test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation`：
   - 使用真实 `FinsIngestionRuntime.download(...) -> ValidatedFinsEventStream -> _run_direct_stream`
   - `_ConsumerAbortDownloadAdapter`（line 689-747）：同步 `threading.Event` barrier
     在 producer 进入后暂停，等待 consumer abort 后释放 cancellation check
   - 断言 `adapter.cancellation_checks == (True,)`——证明 consumer abort →
     validator aclose → raw generator GeneratorExit/finally →
     `cancellation_state.request_cancel()` → producer `cancellation_checker()` 因果链
   - 断言 `StopAsyncIteration` 和 `terminal_result` 不可用——证明 late-publication fence
   - 不依赖 GC、fake-only state 或复制 validator 算法

**独立复核**：真实 generator `GeneratorExit`/`finally` 观察与 production raw-bridge
cancellation 因果链均已在 owner 层和 integration 层独立覆盖。**CLOSED**。

### R09-CR-F04（LOW）— Fins README exact direct signatures 陈旧

**Closure evidence**:

1. `dayu/fins/README.md:192-194` 三个 exact signature 已更新：
   ```
   - `def download(FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None) -> ValidatedFinsEventStream`
   - `def preprocess(FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None) -> ValidatedFinsEventStream`
   - `def upload(FinsUploadRequest, *, cancellation_token: CancellationToken | None = None) -> ValidatedFinsEventStream`
   ```
   与 production code（`ingestion_runtime.py:2145-2259`）一致。

2. Fix artifact scan 确认 Fins/Service/tests README 旧 `-> AsyncIterator[FinsEvent]`
   direct signature 零命中。

**独立复核**：三行 exact signature 已同步，无散落旧签名。**CLOSED**。

### DS former F05 observation（REJECTED / NO CURRENT FIX）

Controller 裁决为 rejected，不要求修复。CLI 继续在 clean exhaustion 后读取 owner
public `terminal_result`。当前代码无 fallback、compat 或第二语义 owner 相关新增代码。
**按裁决保持 no-current-fix，不成为 R09 finding**。

### 原 finding closure 总账

| Finding | Final status | 独立复核 |
|---|---|---|
| `R09-CR-F01` | CLOSED | CLI creator 对所有退出路径确定性 close；primary/cause/context 保持 |
| `R09-CR-F02` | CLOSED | false cast 与 `_ControlledRawStream` 删除；真实 `AsyncGenerator` + typed observation |
| `R09-CR-F03` | CLOSED | 真实 generator `GeneratorExit`/`finally` + production raw-bridge cancellation chain |
| `R09-CR-F04` | CLOSED | 三个 exact Fins runtime signatures 已更新 |
| DS former F05 | REJECTED / NO CURRENT FIX | 按裁决保持 |

**4/4 accepted findings closed；0 open；0 deferred；0 blocker。**

---

## 4. New Findings — 独立完整重新挑战

以下每个维度均已基于直接代码证据完成独立的 adversarial re-review。
未发现新的 material defect。

### 4.1 exactly-one-and-last state machine

逐路径遍历 `ValidatedFinsEventStream.__anext__`（`dayu/fins/direct_stream.py:99-153`）：

| 路径 | 入口状态 | 触发 | 终态 | 复核结果 |
|---|---|---|---|---|
| progress only → clean EOF | OPEN | `StopAsyncIteration` from source | CLOSED, raise MISSING_RESULT | ✓ |
| empty stream → clean EOF | OPEN | `StopAsyncIteration` from source | CLOSED, raise MISSING_RESULT | ✓ |
| progress → RESULT → clean EOF | OPEN → RESULT_BUFFERED | `StopAsyncIteration` from source | RESULT_YIELDED → CLOSED, yield RESULT | ✓ |
| RESULT (no prior progress) → clean EOF | OPEN → RESULT_BUFFERED | `StopAsyncIteration` from source | RESULT_YIELDED → CLOSED, yield RESULT | ✓ |
| progress → RESULT → second RESULT | RESULT_BUFFERED | second `FinsEventType.RESULT` | CLOSED, raise DUPLICATE_RESULT | ✓ |
| progress → RESULT → later progress | RESULT_BUFFERED | non-RESULT event | CLOSED, raise EVENT_AFTER_RESULT | ✓ |
| upstream error in OPEN | OPEN | `BaseException` from `source.__anext__()` | CLOSED, propagate same error, close source once | ✓ |
| upstream cancellation in OPEN | OPEN | `CancelledError` from `source.__anext__()` | CLOSED, propagate same error, close source once | ✓ |
| result-then-upstream-error | RESULT_BUFFERED | `BaseException` from `source.__anext__()` | CLOSED, discard buffered, propagate same error | ✓ |
| result-then-cancellation | RESULT_BUFFERED | `CancelledError` from `source.__anext__()` | CLOSED, discard buffered, propagate same cancel | ✓ |
| explicit aclose OPEN | OPEN | `await stream.aclose()` | CLOSED, close source once | ✓ |
| explicit aclose RESULT_BUFFERED | RESULT_BUFFERED | `await stream.aclose()` | CLOSED, discard buffered, close source once | ✓ |
| repeated aclose after success | CLOSED | `await stream.aclose()` | return immediately | ✓ |
| repeated aclose after failure | CLOSED | `await stream.aclose()` | return immediately, no retry | ✓ |
| duplicate + cleanup close fails | RESULT_BUFFERED | second RESULT + `source.aclose()` raises | CLOSED, DUPLICATE_RESULT is primary, `__cause__ is close_error` | ✓ |
| event-after + cleanup close fails | RESULT_BUFFERED | non-RESULT + `source.aclose()` raises | CLOSED, EVENT_AFTER_RESULT is primary, `__cause__ is close_error` | ✓ |
| upstream error + cleanup close fails | OPEN | `BaseException` + `source.aclose()` raises | CLOSED, upstream error is primary, `__cause__ is close_error` | ✓ |
| upstream cancel + cleanup close fails | OPEN | `CancelledError` + `source.aclose()` raises | CLOSED, CancelledError is primary, `__cause__ is close_error` | ✓ |

**不变量验证**：
- 只有 clean upstream EOF 能证明首个 RESULT 唯一且最后（`_finish_clean_exhaustion` 只在
  `StopAsyncIteration` 后调用，且只在 `RESULT_BUFFERED` 状态 yield）
- `result → error` 不先发布 success（`_raise_primary_after_close` 丢弃 buffered result）
- raw `aclose()` 至多调用一次（`_source_close_attempted` guard 先设后调）

**直接证据**：`direct_stream.py:117-153`（while 循环+状态判定）、`direct_stream.py:194-218`
（`_finish_clean_exhaustion`）、`direct_stream.py:220-240`（`_raise_primary_after_close`）、
`direct_stream.py:242-258`（`_close_source_once` guard）。

**结论**：状态机在全部 18 条路径上正确。未发现 correctness 缺陷。

### 4.2 consumer-body error 确定性关闭

**路径追踪**：`_consume_fins_direct_events` 的 `async for` 循环体（`fins.py:711-722`）中
`render_fins_direct_event(event)` 或 `_log_fins_direct_event_received(event)` 抛出异常：
1. 异常从 `async for` 循环传播，Python 不自动调用 `AsyncIterator.aclose()`
2. 异常传播到 `event_task`（`_wait_for_terminal_handling_sigint:620`）
3. `event_task.done()` 为 True，`await event_task` 重抛异常
4. `_wait_for_terminal_handling_sigint` 的 `except BaseException`（line 656）捕获
5. `_cancel_and_drain_fins_event_task(event_task, primary_error=...)` 被调用
6. 若 child task 的取消产生了 distinct cleanup cause（与 primary 不同），则返回；
   若相同（same-primary cause），返回 None（去重）
7. 异常继续传播到 `_run_fins_direct_command_async` 的 `except BaseException`（line 246）
8. `_raise_primary_after_fins_stream_close(stream, primary_error)` 关闭 stream

**关键细节**：consumer error 路径中，`event_task` 因 `async for` 循环体异常而失败（非取消），
validator 的 `__anext__` 成功返回了最后一个 event（state 可能为 OPEN 或 RESULT_BUFFERED），
但 validator 不在调用栈中。stream owner（`_run_fins_direct_command_async`）在 `except` 中
调用 `stream.aclose()`，触发 raw generator 的 `GeneratorExit`/`finally`/cancellation request。

**直接证据**：`test_cli_stream_owner_preserves_consumer_error_and_cleanup_cause` 的 log 和
render 两路参数化均通过，断言 `primary.__cause__ is close_error`、`closed_streams == 1`、
`StopAsyncIteration`（validator CLOSED）。

**结论**：consumer-body error 确定性关闭成立。primary/cause identity 均保持。

### 4.3 外部 cancellation 确定性关闭

**路径追踪**：外部 task cancellation（`command_task.cancel("external cancellation")`）：
1. `asyncio.CancelledError` 注入到 `_run_fins_direct_command_async` 中
2. `_wait_for_terminal_handling_sigint` 被取消，其 `except BaseException`（line 656）捕获
3. `_cancel_and_drain_fins_event_task(event_task, primary_error=cancellation_error)` 被调用
4. 若 event_task 未完成：`event_task.cancel()` → `await event_task` 产生子 `CancelledError`
5. 子 `CancelledError.__cause__` 若为 distinct cleanup cause，返回给 owner
6. `_wait_for_terminal_handling_sigint` 以 `raise primary_error from cleanup_error` 传播
7. 到达 `_run_fins_direct_command_async:246`，`_raise_primary_after_fins_stream_close` 关闭 stream

**直接证据**：`test_cli_stream_owner_external_cancellation_closes_once_with_cleanup_cause`
断言 `captured.value.__cause__ is close_error`、`service.closed_streams == 1`。

**结论**：外部 cancellation 确定性关闭成立。cleanup cause 身份保留。

### 4.4 SIGINT 路径

**正常 SIGINT（无 close failure）**：
1. `sigint_task.done()` → `event_task.cancel()` → `await event_task` raises `CancelledError`
2. `close_error = cancellation_error.__cause__` 为 `None`
3. 不进入 `raise close_error` 分支
4. `render_fins_direct_local_exit_after_cancel()` → 返回 `_CliDirectLocalExit(130)`
5. `_run_fins_direct_command_async` 的 try block 正常完成 → `stream.aclose()`（no-op，validator 已 CLOSED）
6. `return 130`

**SIGINT + close failure**：
1-3 同上但 `close_error is not None`
4. `raise close_error`（离开 `except CancelledError` handler 后）
5. `_wait_for_terminal_handling_sigint` 的 `except BaseException`（line 656）捕获，
   `primary_error = close_error`
6. `_cancel_and_drain_fins_event_task(event_task, primary_error=close_error)`：
   - `cancellation_error.__cause__ is close_error` → object identity match → 返回 `None`
7. `raise primary_error`（no cleanup cause chaining because None）
8. `_run_fins_direct_command_async:246`：`_raise_primary_after_fins_stream_close(stream, close_error)`
9. validator 已 CLOSED → `aclose()` 立即返回 → `raise primary_error`（line 272）

**self-cause/context 验证**：
- SIGINT handler 不在 active child exception handler 内 `raise close_error`（line 653 在
  `except asyncio.CancelledError` 之后），避免 Python 隐式 `__context__` 写入
- `_cancel_and_drain_fins_event_task` 以 `cancellation_error.__cause__ is primary_error`
  做 object identity 去重，返回 `None`
- `_raise_primary_after_fins_stream_close` 中 `raise primary_error`（line 272）：
  primary_error 与 caller 的 `except BaseException as primary_error` handler 中的是同一对象；
  Python 将此次 raise 视为 reraise，不修改 `__cause__`/`__context__`

**直接证据**：`test_cli_stream_owner_sigint_close_failure_propagates_without_primary`
断言 `captured.value is close_error`、`__cause__ is None`、`__context__ is None`、
`closed_streams == 1`。

**结论**：SIGINT 正常与 close failure 路径均正确。self-cause/context cycle 已闭合。

### 4.5 completed-child race

**same-primary cause 去重**：
`test_cli_event_task_drain_deduplicates_same_primary_close_cause`：
- event_task 已完成（cancelled + done），`CancelledError.__cause__ is close_error`
- `_cancel_and_drain_fins_event_task(event_task, primary_error=close_error)`
- `cancellation_error.__cause__ is primary_error` → True → 返回 `None`
- 断言 `close_error.__cause__ is None`、`__context__ is None`

**distinct cause 保留**：
`test_cli_event_task_drain_keeps_close_cause_when_child_already_done`：
- event_task 已完成（cancelled + done），`CancelledError.__cause__ is close_error`
- `_cancel_and_drain_fins_event_task(event_task, primary_error=asyncio.CancelledError("external"))`
- `cancellation_error.__cause__ is primary_error` → False → 返回 `close_error`
- 断言 `cleanup_error is close_error`

**asyncio done-task outcome 语义**：`_cancel_and_drain_fins_event_task` 在 `event_task.done()`
时不 cancel，直接 `await event_task` 读取同一 outcome。对 cancelled task 的第二次
`await` 在 CPython 3.11+ 重抛同一 `CancelledError` 对象，`__cause__` 得以保留。
测试不依赖此为隐式契约——completed-child race tests 在 `await asyncio.sleep(0)` 后
先断言 `event_task.done()` 再 drain，直接证明同一 outcome 可通过 drain 读取。

**结论**：completed-child race 的 same-primary 去重与 distinct cause 保留均正确。

### 4.6 真实 AsyncGenerator GeneratorExit/finally

**Owner tests**（`test_fins_direct_stream.py`）：
- 全部 source 使用 `_controlled_raw_stream`——真实 `async def ... -> AsyncGenerator`
  使用 `yield` 产出事件、`except GeneratorExit` 记录、`finally` 记录
- `_RawStreamObservation` 以独立 typed dataclass 严格记录 `generator_exit_calls`
  和 `finally_calls`
- 每个 test 断言这些观测值与预期一致（例如 duplicate path：`generator_exit_calls == 1`、
  `finally_calls == 1`；clean path：`generator_exit_calls == 0`、`finally_calls == 1`）

**虚假 seam 清除**：
- 原 `_ControlledRawStream.aclose()` 只递增计数器，不触发 `GeneratorExit`/`finally`
- 原 `cast(AsyncGenerator, ...)` 绕过 pyright
- 两者均已删除（fix artifact scan 零命中）

**结论**：真实 AsyncGenerator GeneratorExit/finally 语义已在 owner test 层完整覆盖。

### 4.7 runtime raw bridge cooperative cancellation 与 late-publication fence

**Raw bridge 实现**（`ingestion_runtime.py:2702-2769`）：
- `_run_direct_stream` 的 `finally: cancellation_state.request_cancel()`（line 2769）：
  无论正常退出、GeneratorExit（consumer close）、或 upstream error，均请求取消
- `_run_direct_stream_producer` 的 `except Exception` 将 generic exception 转为 bounded
  `FAILURE RESULT`（line 2791-2799），`finally` 确保 `_DirectStreamProducerDone()` 入队

**Consumer abort integration test**（`test_fins_ingestion_runtime.py:1946-1985`）：
- `_ConsumerAbortDownloadAdapter` 在 producer 进入后通过 `threading.Event` barrier 暂停
- consumer 显式 `aclose()`（两次，验证幂等）后释放 barrier
- adapter 在释放后调用 `request.cancellation_checker()` → 观察值为 `(True,)`
- adapter 尝试 late progress 后设置 `late_progress_returned`
- 测试断言 `cancellation_checks == (True,)`、`StopAsyncIteration`、`terminal_result` 不可用
- 因果链：`consumer abort → validator aclose → raw generator GeneratorExit/finally →
  cancellation_state.request_cancel → producer cancellation_checker → late progress blocked`

**结论**：runtime raw bridge cooperative cancellation 因果链与 late-publication fence
已验证。测试不依赖 GC、fake-only state 或复制 validator 算法。

### 4.8 runtime/Service/CLI signature/provenance/identity propagation

逐边界复查（对照 accepted plan §3.4 exact old/new signature 表）：

| Boundary | Old | New (actual) | Match plan? |
|---|---|---|---|
| runtime `download/preprocess/upload` | `async def -> AsyncIterator` | `def -> ValidatedFinsEventStream` | ✓ |
| runtime `_run_direct_stream` | `async def -> AsyncIterator` | `async def -> AsyncGenerator[FinsEvent, None]` | ✓ |
| Service Protocol 3 methods | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| Service 6 public methods | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| Service `_preprocess` | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| CLI `_open_direct_stream` + 6 helpers | `-> AsyncIterator[FinsEvent]` | `-> ValidatedFinsEventStream` | ✓ |
| CLI `_consume_fins_direct_events` | `operation_kind` param + missing fallback | 删除两者 | ✓ |
| Service `_ensure_result_event` | 全函数 | 已删除 | ✓ |
| CLI `_direct_operation_kind` | 全函数 | 已删除 | ✓ |

**process_filing/material PREPROCESS provenance**：
- `Service._preprocess`（`fins_direct.py:416-456`）：`operation_kind` 参数仅用于
  `runtime_log.log_verbose`（line 440-445），不传给 runtime
- Runtime `preprocess`（`ingestion_runtime.py:2184-2220`）：始终传入
  `operation_kind=FinsOperationKind.PREPROCESS` 给 `ValidatedFinsEventStream`
- Service `process_filing/material` 调用 `_preprocess(operation_kind=PROCESS_FILING/PROCESS_MATERIAL, ...)`
  — 仅日志用，validator 始终报告 `PREPROCESS`
- Test coverage：Service tests `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance`
  与 `test_process_material_keeps_runtime_preprocess_protocol_error_provenance`；CLI tests
  `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli` 与
  `test_process_material_keeps_runtime_preprocess_protocol_error_provenance_through_cli`

**Protocol error identity pass-through**：
- `test_fins_owned_protocol_error_object_reaches_cli_consumer_unchanged`：
  断言 `captured.value is owner_error` + `reason/operation_kind/message` 同源
- Service identity pass-through 由 `test_fins_owned_protocol_error_fields_and_object_are_propagated_by_identity` 覆盖

**结论**：全部 boundary signature cutover 正确。无遗漏 production caller。无新增 `await`。
PREPROCESS provenance 不被 Service alias 改写。Protocol error identity 经 Service/CLI 保持。

### 4.9 CLI presentation

**Protocol error presentation**：
- `run_fins_direct_command`（`fins.py:200-202`）：catch `FinsDirectStreamProtocolError`，
  沿用 `render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`，返回 `EXIT_FAILURE=1`
- CLI 不 import `FinsDirectStreamProtocolErrorKind`，不读取 `reason.value`
- CLI tests 只断言既有 prefix/message 与 exit 1：
  `"dayu-cli download: Fins direct stream ended without RESULT"`（missing）、
  `"dayu-cli download: Fins direct stream produced multiple RESULT events"`（duplicate）

**Business result exit mapping**：
- `FinsResultSummary.exit_code`：SUCCESS → 0、FAILURE → 1、CANCELLED → 130
- `test_terminal_failed_and_cancelled_status_exit_mapping` 覆盖 FAILURE/CANCELLED 两路

**SIGINT presentation**：
- 正常 SIGINT（无 close failure）：render `Fins operation cancel requested` + `Fins direct command cancelled locally` → exit 130
- SIGINT + close failure：close_error 原样传播 → 外层 `run_fins_direct_command` 的 `except Exception` catch → `render_cli_error(...)` → exit 1

**结论**：CLI presentation 保持既有 prefix/message/exit contract。typed reason 不成为新 public 输出协议。

### 4.10 README/coverage/security/no-touch/deferred scope

**README**: 复核 `dayu/fins/README.md:192-194`（三行 exact signature 已更新）、
`dayu/service/README.md:15,35`（已描述 pass-through identity）、`tests/README.md:196`
（已描述 validator owner tests 与 raw bridge integration）。root `README.md` 和
`dayu/README.md` no-touch decision 有直接证据（CLI 命令、参数、输出格式、exit mapping、
分层装配均未变）。

**Coverage**: 五个 changed production files 的逐文件 coverage 已在 Codex fix artifact
§6.2 记录（`88.56%-97.78%`），Controller fix validation 独立确认。

**Security**: retained leakage guard（`direct_events.py` 的 safe-text validation）、
job id / path / raw payload / body prohibition、operation cancellation、queue backpressure、
late-publication fence、storage containment / symlink / atomic publication 均未修改或弱化。
retained security exact tests 参数化结果为 16 passed。

**No-touch**: `direct_events.py:496`（仅新增一个 enum literal）、`direct_stream.py:261`
（全新增）、`ingestion_runtime.py:6920`（仅修改 runtime public method signature 与 raw bridge）、
`service/fins_direct.py:467`（仅修改返回类型与删除 `_ensure_result_event`）、
CLI 文件（仅修改 stream open/consumer/SIGINT boundary）。storage/pipelines/processors/
Fins tools/Host/Engine/runtime/config/root README/dayu README 相对于 base 零 authored diff。

**Deferred scope**: Issue 142/151/175/177/178、R10-R12、Topic 8/9、统一 authorization framework、
Web/WeChat/render — fix artifact scan 零命中。

**结论**：README、coverage、security、no-touch、deferred scope 均匹配 accepted contract。

---

## 5. Observations（非 actionable findings）

以下观察来自走读过程，不属于代码缺陷，不要求修复：

1. **`_consume_fins_direct_events` 对 `terminal_result` 的隐式依赖**：
   `async for` 循环结束后（line 722）无条件读取 `events.terminal_result`。
   当前 validator 状态机保证 `StopAsyncIteration` 只在 `RESULT_YIELDED`（`clean_exhaustion=True`）
   或 `CLOSED` 状态下抛出。CLOSED 状态下的 `StopAsyncIteration`（在 `__anext__:118-119`）
   不设置 `clean_exhaustion`，因此 `terminal_result` 会抛 `RuntimeError`。
   但该路径只在 validator 已被显式 close 后仍有 consumer 尝试读取时触发——这在当前
   CLI flow 中不会发生（consumer 完成或异常后 stream 才被 close）。
   这属于 validator-CLI 实现级契约，当前无 bug，不需要修改。记录为 residual contract note。

2. **`_run_direct_stream` 的 `direct_operation_kind` 参数**：
   仅用于 `_FinsIngestionExecutionContext` 构造（producer context），在 raw bridge 中
   不再用于 terminal protocol 判断。无冗余。

3. **Service `_preprocess` 的 `operation_kind` 参数**：
   仅用于 `runtime_log.log_verbose`（line 440-445）。Service 保留 command alias 日志语义，
   但不传给 runtime validator。plan 明确允许。

4. **`test_direct_consumer_abort_closes_raw_bridge_and_requests_cancellation`** 的
   `_ConsumerAbortDownloadAdapter` 使用 `threading.Event` barrier 实现同步跨线程观察。
   这比 fake/mock 更忠实地反映真实 producer 的 cross-thread 行为。设计合理。

---

## 6. Open Questions

1. **`_cancel_and_drain_fins_event_task` 对非 `CancelledError` 子类的 `BaseException`
   处理**：当前 `except BaseException as cleanup_error`（line 693）捕获所有非取消异常，
   包括 `KeyboardInterrupt`、`SystemExit` 等。若 child task 因 `KeyboardInterrupt` 死亡，
   该异常会被返回为 cleanup_error。这在当前 `asyncio.run()` 语义下不大可能触发
   （`KeyboardInterrupt` 在 `asyncio.run()` 层转为 `CancelledError`），但值得记录。

---

## 7. Residual Risk

1. **Fins thread-backed long operation 的 physical process isolation**：
   owner 仍为 Issue 175。R09 保证 cooperative cancellation request、deterministic raw close
   与 late-publication fence，不越界实现 hard process kill。

2. **Implicit validator→CLI contract**（Observations §1）：
   CLI 假设 `StopAsyncIteration` 只在 clean exhaustion 后。当前 validator 实现保证此不变量，
   但这不是显式 typed contract。若未来 validator 状态机新增 `StopAsyncIteration` 路径，
   CLI 的 `terminal_result` 读取会收到 `RuntimeError`。当前风险低，无需修改。

3. **Full Fins 的 1 个 existing environment skip 与 3 个 edgartools deprecation warnings**：
   未由 R09 新增或升级为 error；真实 SEC/Docling smokes 均已成功。

---

## 8. Verdict

**PASS — 零新 material finding**。

### 8.1 Finding closure 总账

| Finding | 原 gate | Re-review status |
|---|---|---|
| `R09-CR-F01` | Controller adjudication accepted (HIGH) | **CLOSED** — CLI creator 全部退出路径确定性 close |
| `R09-CR-F02` | Controller adjudication accepted (MEDIUM) | **CLOSED** — false cast 删除，真实 AsyncGenerator + typed observation |
| `R09-CR-F03` | Controller adjudication accepted (MEDIUM) | **CLOSED** — 真实 GeneratorExit/finally + production raw-bridge cancellation chain |
| `R09-CR-F04` | Controller adjudication accepted (LOW) | **CLOSED** — exact signatures 更新 |
| DS former F05 | Controller adjudication rejected | **NO CURRENT FIX** — 按裁决 |

**4/4 accepted findings closed；0 new findings；0 blocker；0 deferred**。

### 8.2 重新挑战结论

| 挑战维度 | 结论 |
|---|---|
| R09-CR-F01..F04 closure | 全部 4 个独立复核闭合，有直接代码证据 |
| exactly-one-and-last state machine | 18 条路径全部正确 |
| consumer-body error cleanup | 确定性关闭，primary/cause 保持 |
| external cancellation cleanup | 确定性关闭，cleanup cause 保持 |
| SIGINT + close failure | self-cause/context cycle 已闭合 |
| completed-child race | same-primary 去重 + distinct cause 保留 |
| asyncio done-task outcome | drain 读取同一 outcome，不依赖非契约行为 |
| real AsyncGenerator GeneratorExit/finally | 真实 generator + typed observation |
| runtime raw bridge cancellation | 因果链 + late-publication fence 已验证 |
| signature/provenance/identity propagation | 全部 boundary 正确，PREPROCESS 不漂移 |
| CLI presentation | 保持既有 prefix/message/exit，无 reason.value 暴露 |
| README/coverage/security/no-touch/deferred | 全部匹配 accepted contract |

### 8.3 Exit lock verification

| Lock | Expected | Actual | Match |
|---|---|---|---|
| HEAD | `9d36a115400fb59fd95475189810b43a09fda31b` | 同 | ✓ |
| Staged | empty | empty | ✓ |
| 12-path manifest SHA | `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` | 同 | ✓ |
| 12 content SHA | 全部匹配 Controller fix validation §5 | 独立重算，全部匹配 | ✓ |
| Working tree no-drift | 仅本 artifact 新增与 entry 既有路径 | 12 target 路径未漂移 | ✓ |

---

## 9. Artifact lines and SHA-256

最终 lines 与 SHA-256 由本 artifact 写入完成后的外部 Controller 命令独立计算并记录；
不在 artifact 正文内做自引用嵌入。
