# WU-SEMANTIC-OWNERSHIP-01 / R09 Fins direct-stream validator 独立完整 Code Re-Review — AgentMiMo

## 1. Scope

- Mode: immutable cumulative implementation re-review
- Branch: `phaseflow/host-issues-control`
- HEAD: `9d36a115400fb59fd95475189810b43a09fda31b`
- 12-path sorted manifest SHA-256: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` ✓（`printf paths | LC_ALL=C sort | sha256sum`）
- Canonical cumulative binary diff SHA-256: `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d` ✓（tracked 10 paths `git diff --binary HEAD` + 2 untracked no-index binary diffs）
- Target lock: **no-drift** — 12 文件 content SHA-256 全部匹配 Controller validation §5。
- Fix artifact（AgentCodex）: 271 lines, SHA-256 `c9affe9935d2825284c10bcccd61169c3836cb5076d13de90bb517787e8c85d7`
- Controller validation: 141 lines, SHA-256 `5a6a12c5fc4679de26bc841402fe93d91847fd9015a2c9e54266d04dd8ebfd5b`
- Staged tree: empty ✓
- Output file: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-code-rereview-mimo.md`

## 2. R09-CR-F01..F04 闭合验证

| 原始 Finding | 严重程度 | 闭合证据 | 状态 |
|---|---|---|---|
| R09-CR-F01 CLI stream owner 未在所有退出路径关闭 raw source | HIGH | `_run_fins_direct_command_async`（fins.py:234-252）用 try/except 包裹 stream 消费；consumer 异常路径走 `_raise_primary_after_fins_stream_close`（fins.py:268-272）；正常结束走 `await stream.aclose()`（fins.py:251）；SIGINT 路径走 cancellation → drain → close 链。所有路径测试断言 `closed_streams == 1`。 | **closed** |
| R09-CR-F02 owner tests 用不真实 cast 绕过 source 类型契约 | MEDIUM | `test_fins_direct_stream.py` 全部使用真实 `async def` generator（如 `_controlled_raw_stream` L40-74），无 `_ControlledRawStream` mock class，无 `cast(AsyncGenerator[...], source)`。 | **closed** |
| R09-CR-F03 未验证真实 generator close 的 cancellation/finally 因果链 | MEDIUM | `_RawStreamObservation` dataclass 跟踪 `generator_exit_calls`/`finally_calls`；`test_validated_stream_repeated_aclose_closes_source_once`（L567-592）断言 `generator_exit_calls == 1, finally_calls == 1`；`test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails`（L426-458）断言因果链。新增 integration test 证明 consumer abort → validator aclose → GeneratorExit/finally → cancellation_state.request_cancel。 | **closed** |
| R09-CR-F04 Fins README exact direct signatures 陈旧 | LOW | `dayu/fins/README.md:192-194` 签名已更新为 `-> ValidatedFinsEventStream`，与 `ingestion_runtime.py` L2150/2189/2227 一致。 | **closed** |

## 3. 逐维度完整重审

使用 5 个并行专项 subagent 覆盖全部 12-path target。以下为各维度直接代码证据审查结论。

### 3.1 状态机完整性（direct_stream.py）

**通过。** OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED 全路径覆盖：

| 路径 | 代码位置 | 结论 |
|---|---|---|
| progress before result (OPEN) | L131-139 | 非 RESULT 直接 return，状态保持 OPEN |
| first result (OPEN → RESULT_BUFFERED) | L132-138 | 缓存 event，`_state = RESULT_BUFFERED` |
| duplicate result (RESULT_BUFFERED) | L141-146 | 构造 DUPLICATE_RESULT，进入 `_raise_primary_after_close` |
| event after result (RESULT_BUFFERED) | L147-153 | 构造 EVENT_AFTER_RESULT，进入 `_raise_primary_after_close` |
| clean EOF without RESULT (OPEN) | L126-127 → L207-213 | MISSING_RESULT 协议错误 |
| clean EOF with RESULT (RESULT_BUFFERED) | L126-127 → L214-218 | `_clean_exhaustion = True`，返回 buffered result |
| RESULT_YIELDED → StopAsyncIteration | L120-122 | 设 CLOSED，raise StopAsyncIteration |
| upstream exception/cancellation | L128-129 | 捕获 BaseException，传入 `_raise_primary_after_close` |

### 3.2 self-cause/context cycle 防护

**通过。** `_raise_primary_after_close`（L220-240）中 `primary_error` 和 `close_error` 是独立对象，`raise primary_error from close_error`（L239）不形成 `e.__cause__ is e` 循环。CLI `_cancel_and_drain_fins_event_task`（fins.py:682-697）对 `cancellation_error is primary_error`（L687）和 `cleanup_error is primary_error`（L690）做 identity check 返回 None。测试 `test_cli_event_task_drain_deduplicates_same_primary_close_cause`（test_fins_commands.py:1285）断言去重。

### 3.3 aclose 幂等性

**通过。** 双重守卫：状态守卫 `if self._state is CLOSED: return`（L168-169）+ source 关闭守卫 `_source_close_attempted`（L255-258）确保 `_source.aclose()` 至多调用一次。

### 3.4 terminal_result contract

**通过。** clean exhaustion 后返回同一 `FinsResultSummary` 对象（L190-192）。非 clean exhaustion 状态抛 `RuntimeError(_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE)`（L30-32 模块私有常量）。

### 3.5 primary error precedence

**通过。** upstream exception/cancellation 或 validator 构造的 typed error 始终是最终传播对象。cleanup aclose failure 通过 `raise primary from close_error` 链接。不替换 primary。测试 `test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails`（L426-458）断言 `primary.reason is DUPLICATE_RESULT` 且 `primary.__cause__ is close_error`。

### 3.6 no catch-and-rewrite

**通过。** validator 不将 producer/upstream/cancel/close 异常转化为 business `RESULT`。`__anext__` 中仅捕获 `StopAsyncIteration`（纯 EOF）和 `BaseException`（直接重抛同一对象）。

### 3.7 runtime raw bridge（ingestion_runtime.py）

**通过。** `_run_direct_stream`（L2702-2769）是纯 raw bridge：只消费 queue item、yield raw event、break on `_DirectStreamProducerDone`。零 `FinsDirectStreamProtocolError` 使用。`_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone`（L1343）保持不变。producer generic exception 映射为 business failure RESULT（L2791-2799），不构造 protocol error。

### 3.8 cooperative cancellation 与 late-publication fence

**通过。** `_DirectStreamCancellationState`（L1258-1311）`request_cancel()` 在 raw bridge finally 中调用（L2769）。`_DirectCancellationChecker.__call__`（L1320-1335）检查 `cancellation_state.is_cancelled()` 和 `cancellation_token.is_cancelled()`。`_put_direct_queue`（L4671-4683）在 `cancellation_state.is_cancelled()` 时返回 False 丢弃事件。

### 3.9 Service 层（fins_direct.py）

**通过。** `_ensure_result_event` 已删除。六个 public method 直接返回 runtime 的 `ValidatedFinsEventStream`（L201/453/346/411）。Service 不 import `FinsDirectStreamProtocolErrorKind`。Service 不添加自己的 `operation_kind`。protocol error 从 runtime 透传（测试断言 `stream is runtime.returned_streams[-1]`，L520/553/584）。

### 3.10 CLI 层（fins.py）

**通过。**
- Stream close: `_run_fins_direct_command_async` try/except + `_raise_primary_after_fins_stream_close` + `await stream.aclose()` 覆盖所有退出路径
- SIGINT: operation-scoped cancellation token（L640），event_task.cancel()（L641），close failure 传播（L650-653）
- Presentation: `dayu-cli {command_name}: {exc.message}` + EXIT_FAILURE（L200-202）
- CLI 不 import `FinsDirectStreamProtocolErrorKind`
- CLI 不重建 error，透传 owner 对象
- 所有 stream helper 返回 `ValidatedFinsEventStream`（L390/436/463/495/532/557/582）
- asyncio done-task outcome 语义正确：event_task.done()（L629）、sigint_task.done()（L632）、cancel race 处理（L644-655）

### 3.11 签名/溯源/身份传播

**通过。** Runtime → Service → CLI 全链路 `ValidatedFinsEventStream` 类型。`operation_kind` 从 runtime 构造函数参数传入 validator，Service 不覆盖。`process_filing`/`process_material` 的 Service alias 名称不影响 error provenance（测试断言 `captured.value.operation_kind is FinsOperationKind.PREPROCESS`，L558/589）。

### 3.12 测试覆盖

**通过。** 4 个测试文件覆盖：
- `test_fins_direct_stream.py`（743 行）：全状态机路径、aclose 幂等、primary error precedence、no self-cause cycle、real async generator
- `test_fins_ingestion_runtime.py`（4926 行）：raw bridge、producer、cancellation、observation
- `test_fins_direct.py`（721 行）：Service identity pass-through、provenance、task cancellation
- `test_fins_commands.py`（1804 行）：CLI presentation、SIGINT、consumer error、cancel race、no-storage-import

### 3.13 AGENTS.md 合规

**通过。** 无 `Any`/`object`/无类型参数。无 `hasattr`/`getattr`。无魔法数字/字符串。无 god object/function。无兼容性代码。所有函数有完整中文 docstring。

## 4. Findings

### 01-未修复-低-README dayu/fins/README.md 目录树缺少 direct_events.py 和 direct_stream.py

- **入口/函数**: `dayu/fins/README.md:431-443` 目录树
- **文件(行号)**: `dayu/fins/README.md:431-443`
- **输入场景**: 阅读 Fins 目录树了解模块组成
- **实际分支**: 目录树列出 `ingestion_runtime.py`、`service_runtime.py`、`ticker_normalization.py`，缺少 `direct_events.py` 和 `direct_stream.py`
- **预期行为**: R09 新增的两个顶层模块应在目录树中列出
- **实际行为**: 两个模块未列出，读者无法从目录树发现它们
- **直接证据**: L439 只列 `ingestion_runtime.py`，L441-442 列 `service_runtime.py` 和 `ticker_normalization.py`，无 `direct_events.py` 或 `direct_stream.py` 条目
- **影响**: 文档完整性缺陷，不影响正确性
- **建议改法和验证点**: 在目录树中添加两个条目，如 `├── direct_events.py  # Fins direct event types, protocol error, leakage guard` 和 `├── direct_stream.py  # ValidatedFinsEventStream — exactly-one-RESULT validator owner`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 5. Open Questions

无。

## 6. Residual Risk

- Fins thread-backed long operation 的 physical process isolation，owner 仍为 Issue 175（Controller validation §7 已记录）。
- `direct_stream.py:134` 使用 bare `assert result is not None`。`FinsEvent.__post_init__`（direct_events.py:340）已保证 RESULT event 的 `result` 字段非 None，`python -O` 下 `assert` 被 strip 后最坏情况是下游 AttributeError，不会产生错误业务结果。严重程度极低，不作 finding。

## 7. 原 Finding Closure 总账

| 原始 Finding | 来源 | 最终状态 |
|---|---|---|
| R09-CR-F01（HIGH） | MiMo 01 / DS F01 / DS F04 alias | **closed** — try/finally + `_raise_primary_after_fins_stream_close` 覆盖所有退出路径 |
| R09-CR-F02（MEDIUM） | MiMo 02 / DS F02 | **closed** — 真实 async generator，无 cast |
| R09-CR-F03（MEDIUM） | DS F03 | **closed** — 真实 GeneratorExit/finally 因果链测试 |
| R09-CR-F04（LOW） | MiMo 03 / DS F06 | **closed** — README 签名已更新 |
| DS former F05 | DS | **rejected**（按 Controller 裁决） |

4 accepted / 4 closed / 0 open / 0 deferred / 0 blocker

## 8. 新 Finding 总账

| ID | 严重程度 | 文件 | 行号 | 描述 |
|---|---|---|---|---|
| 01 | 低 | `dayu/fins/README.md` | 431-443 | 目录树缺少 `direct_events.py` 和 `direct_stream.py` 条目 |

1 新 finding / 严重程度：低 / 零 blocker

## 9. Target Lock 记录

| 文件 | SHA-256 |
|---|---|
| `dayu/fins/direct_stream.py` | `f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53` |
| `dayu/fins/direct_events.py` | `192f31fc42a1be7415ccca2f658a8a84044b086f41c7c65d3dba02fc579a993a` |
| `dayu/fins/ingestion_runtime.py` | `aba78b1e4cacf7566ffd275db51392441575d90c2d9341a2e377bf801d43b580` |
| `dayu/fins/README.md` | `fe2d12627c2f8da780a7305f2e5f3611c09a3660f233c7014d272e900fded9d7` |
| `dayu/service/fins_direct.py` | `c5bd361ba1603fd76656af9f7b065d8aa07906ed5568749ef6d5e470e20391ac` |
| `dayu/service/README.md` | `4f4f30b8e1caae100c9329fe42515ca504f7057e29e92381e15cd35851f6be9d` |
| `dayu/cli/commands/fins.py` | `0db8ff2dedf541c2b58bc11342a02cd0bf4098bc9fcc19d948efa5cf4afc95a6` |
| `tests/fins/test_fins_direct_stream.py` | `781c3bd941bed675441d9a3e09ac33e525705f02b4c7049d0eb6274f761ba67a` |
| `tests/fins/test_fins_ingestion_runtime.py` | `56d9db211e04bdbb246de77432931be1f4262d20eba6bb7b486c95db19f475bf` |
| `tests/service/test_fins_direct.py` | `e90c7a9238ef00afcee9d49d5093cad387afdb77fadb7505a0d5a4825f706162` |
| `tests/cli/test_fins_commands.py` | `d139e10c7636da59e62296d935ed305e7ea0762a94fc59168b7b2a4d199c9668` |
| `tests/README.md` | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |

12-path sorted manifest SHA-256: `ce024b6df7e319fe38c3a708ec4a2cec9f66b9286c5d41763c73c17cc2fc5cb4` ✓
Canonical cumulative binary diff SHA-256: `e5f35bd8ccfe945cd74436fad25ae2cb0ca537a4d3d706f97e6721ba6a86e48d` ✓
Target lock: no-drift — 12 文件 content SHA-256 全部匹配 Controller validation §5。

## 10. Parallel Review Coverage

5 个并行专项 subagent 覆盖全部 12-path target：

| Subagent | 范围 | 结论 |
|---|---|---|
| Agent 1 | `direct_stream.py` validator 状态机（9 项验证） | 1 finding（aclose docstring — 后经人工复核确认已有 Raises 段，为误报） |
| Agent 2 | `fins.py` CLI stream lifecycle（7 项验证） | 0 findings |
| Agent 3 | `ingestion_runtime.py` runtime raw bridge（6 项验证） | 0 findings |
| Agent 4 | `fins_direct.py` Service + 3 个 test file（18 项验证） | 0 findings |
| Agent 5 | `direct_events.py` + 3 个 README + AGENTS.md 合规（20 项验证） | 2 findings（README 目录树 LOW + bare assert LOW） |

人工复核修正：Agent 1 报告的 `aclose` docstring 缺少 Raises 为误报（L164-165 已有 Raises 段）。Agent 5 报告的 bare assert（L134）经评估严重程度极低，`FinsEvent.__post_init__` 已保证 invariant，不作 finding。

## 11. 最终 Verdict

**PASS / 1 low-severity finding**。

R09-CR-F01..F04 全部 closed。状态机完整性、self-cause 防护、aclose 幂等、primary error precedence、no catch-and-rewrite、raw bridge pure pass-through、cooperative cancellation、late-publication fence、Service/CLI 语义所有权边界、签名传播、CLI presentation、SIGINT 处理、asyncio done-task 语义、测试覆盖、AGENTS.md 合规均通过。唯一新 finding 为 README 目录树文档完整性缺陷（低严重程度），不 block 实现接受。

## 12. Artifact Metadata

- Artifact lines / SHA-256: 由写入后的外部 Controller 命令记录，不由 artifact 自引用。
- Target lock: no-drift — 12-path content SHA-256 全部匹配 Controller validation §5，sorted manifest 与 canonical binary diff 均匹配。
- `docs/host/issues-implementation-control.md` 有独立未提交变更（22726 bytes diff），不在 12-path target 闭集内。
- Working tree no-drift（本次 review 未修改任何 product/test/README/control/plan/prior artifact）。
