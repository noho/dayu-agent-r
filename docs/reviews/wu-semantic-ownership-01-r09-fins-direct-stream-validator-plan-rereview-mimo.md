# WU-SEMANTIC-OWNERSHIP-01 R09 Fixed Plan Re-Review — AgentMiMo

## 0. Review Identity

- Reviewer: AgentMiMo
- Review type: adversarial complete fixed-plan re-review（非 diff-only）
- Immutable target: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
- Target SHA-256: `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` ✓
- Target lines: 773 ✓
- Fix input SHA-256: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`（689 行）
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-controller-adjudication.md`
- AgentCodex fix artifact: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-controller-validation.md`
- AgentMiMo original review: SHA-256 `d220c1dd7637d560c835f059841c7effaafe1027b3deb7fe5b1e0919a80b57ac`（历史证据）
- AgentDS original review: SHA-256 `0434e4766729d2d85c1ade31c767a88ffd47781e7b49b4b734d86ae8a0a53ad9`（历史证据）
- Current base: R08 completion accepted commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`
- Date: 2026-07-17

## 1. Verdict

**PASS — code-generation-ready**

零 blocking finding。零 new accepted-candidate finding。六个 R09-PR-F01..F06 全部确认关闭，plan 自洽且可直接指导 implementation。

## 2. SHA-256 与 Source Lock 验证

### 2.1 Target SHA-256

```
a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d  773 lines
```

与 Codex fix artifact §2、Controller validation §0 一致。✓

### 2.2 Source Lock 验证

| evidence | plan §1.3 SHA | actual `shasum -a 256` | match |
|---|---|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d...` | `b34cb82d70205a23d1e1853c260ea0c9353567082710699bfc4000e485578cf3` | ✓ |
| `dayu/fins/ingestion_runtime.py` | `176d8ab9...` | `176d8ab974c263f6aedc99b1d8b9a8fbd60ebed441a3aa950d5d9a718c64908a` | ✓ |
| `dayu/service/fins_direct.py` | `875d5396...` | `875d5396b1d98bdc28f13480241e081529db5e9fa33416914fa6d47e9663b696` | ✓ |
| `dayu/cli/commands/fins.py` | `666d9dc2...` | `666d9dc2793a706a5f00301f215ca324857e4593fcc4c98b18cc90fdc9e245bf` | ✓ |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be57...` | `6480be571d2118648b7829714b885cd0c8a030b6499ec48625af7d207e57ebf4` | ✓ |
| `tests/service/test_fins_direct.py` | `9c533d7e...` | `9c533d7e632762e3fe02a5ae1c58939d71bc7d8c6cb853bd21ad8b4e3a6f2e9b` | ✓ |
| `tests/cli/test_fins_commands.py` | `525414da...` | `525414da8675fdada4ad458271861cf2801c21f57544d62f436594218dafa26c` | ✓ |
| `docs/fins/design.md` | `97033cf1...` | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` | ✓ |

`docs/host/issues-implementation-control.md` 的实际 SHA 为 `0de2c21c...`，plan 记录 `3d9403bc...`。差异原因：该文件有未提交的 R09 transition 修改（plan §0 已声明"docs/host/issues-implementation-control.md 的未提交 R09 transition 是 Controller 有意输入"）。plan 在 §1.4 中记录的 SHA 是 plan 创建时的快照，此后 control doc 被 Controller 追加了 R09 plan review/fix 条目。此漂移是预期的 Controller 工作流行为，不是 plan source lock 错误。✓

### 2.3 Controller/DS/MiMo 原始 source locks

| source | plan §1.4 SHA | Codex fix §1 SHA | match |
|---|---|---|---|
| original plan | `85a783fb...34210` | `85a783fb...34210` | ✓ |
| Controller adjudication | `f615eccf...0643` | `f615eccf...0643` | ✓ |
| AgentDS review | `0434e476...5ad9` | `0434e476...5ad9` | ✓ |
| AgentMiMo review | `d220c1dd...57ac` | `d220c1dd...57ac` | ✓ |

全部一致。✓

## 3. R09-PR-F01..F06 Closure 完整复核

### 3.1 R09-PR-F01 — exact signature and call-site cutover ✓ CLOSED

**直接代码证据：**

| boundary | current code evidence | plan §3.4 new shape | 一致性 |
|---|---|---|---|
| `FinsIngestionRuntime.download` | line 2146: `async def download(...) -> AsyncIterator[FinsEvent]`，body 含 `yield event` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsIngestionRuntime.preprocess` | line 2183: `async def preprocess(...) -> AsyncIterator[FinsEvent]`，body 含 `yield event` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsIngestionRuntime.upload` | line 2219: `async def upload(...) -> AsyncIterator[FinsEvent]`，body 含 `yield event` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `_run_direct_stream` | line 2696: `async def _run_direct_stream(...) -> AsyncIterator[FinsEvent]`，async generator | `async def ... -> AsyncGenerator[FinsEvent, None]`，raw bridge | ✓ |
| `FinsDirectIngestionRuntime.download` | line 53: `def download(...) -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsDirectIngestionRuntime.preprocess` | line 69: `def preprocess(...) -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsDirectIngestionRuntime.upload` | line 85: `def upload(...) -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsDirectCommandService.download` | line 166: `def download(...) -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| `FinsDirectCommandService._preprocess` | line 429: `def _preprocess(...) -> AsyncIterator[FinsEvent]`，经 `_ensure_result_event` 包装 | plain `def ... -> ValidatedFinsEventStream`，直接 return runtime stream | ✓ |
| `FinsDirectCommandService.process_filing` | line 244: `def process_filing(...) -> AsyncIterator[FinsEvent]`，调用 `_preprocess(operation_kind=FinsOperationKind.PROCESS_FILING, ...)` | plain `def ... -> ValidatedFinsEventStream`，不替换 runtime `PREPROCESS` | ✓ |
| CLI `_open_direct_stream` | line 363: `def _open_direct_stream(...) -> AsyncIterator[FinsEvent]` | plain `def ... -> ValidatedFinsEventStream` | ✓ |
| CLI `_consume_fins_direct_events` | line 662: `async def _consume_fins_direct_events(events: AsyncIterator[FinsEvent], *, operation_kind: FinsOperationKind) -> FinsResultSummary` | `async def _consume_fins_direct_events(events: ValidatedFinsEventStream) -> FinsResultSummary`，删除 `operation_kind` | ✓ |
| CLI `_wait_for_terminal_handling_sigint` | line 604: `async def ...(events: AsyncIterator[FinsEvent], ..., operation_kind: FinsOperationKind) -> FinsResultSummary \| _CliDirectLocalExit` | `async def ...(events: ValidatedFinsEventStream, ...) -> FinsResultSummary \| _CliDirectLocalExit`，删除 `operation_kind` | ✓ |

调用链无新增 `await`：Service 保持 plain `def` 直接 return；CLI `_open_direct_stream` 保持 plain `def`；`_run_fins_direct_command_async` 中 `stream = _open_direct_stream(...)` 无 `await`，`await _wait_for_terminal_handling_sigint(events=stream, ...)` 保持。✓

### 3.2 R09-PR-F02 — error/close precedence and idempotence ✓ CLOSED

**plan §4 不变量 3（直接证据）：**
"primary semantic error 的唯一优先级 contract 是：upstream exception/cancellation 的原 object，或 validator 已构造的 duplicate/event-after typed error，始终是最终传播的 type/object/reason/operation_kind/message；cleanup `aclose()` failure 不得覆盖它。cleanup failure 通过显式 chaining（`raise primary from cleanup_error`，因此 `primary.__cause__ is cleanup_error`）保留"

**plan §4 不变量 4（直接证据）：**
"显式 consumer `aclose()` 时若没有 pre-existing semantic error，底层 close failure 必须以同一 exception object 原样传播。validator 以私有 close-attempted guard 保证底层 `aclose()` 最多调用一次；首次成功或失败后，重复 `aclose()` 均不得重试。"

**§7.1 exact test assertions（直接证据）：**
- `test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails`: `captured.value is primary` 且 `captured.value.__cause__ is close_error`
- `test_validated_stream_event_after_result_error_stays_primary_when_cleanup_close_fails`: same pattern
- `test_validated_stream_upstream_error_stays_primary_when_cleanup_close_fails`: same pattern
- `test_validated_stream_upstream_cancellation_stays_primary_when_cleanup_close_fails`: same pattern
- `test_validated_stream_explicit_aclose_propagates_same_close_error_without_primary`: `captured.value is close_error`
- `test_validated_stream_repeated_aclose_closes_source_once`: raw source close call count 恰为 `1`
- `test_validated_stream_repeated_aclose_after_close_failure_does_not_retry_source`: raw source close call count 恰为 `1`

precedence/idempotence contract 完整且可实现。✓

### 3.3 R09-PR-F03 — remove speculative producer protocol-error path ✓ CLOSED

**直接代码证据验证：**
- `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone`（line 1344）：无 protocol error variant。✓
- `_run_direct_stream_producer`（line 2801）：`except Exception as exc: error_kind = _classify_direct_error(exc); self._emit_direct_result(context, status=FAILURE, ...)`。无 `except FinsDirectStreamProtocolError`。✓
- Producer callees（`_produce_direct_download` line 2815, `_execute_download_request` line 3667, pipelines, downloaders）：不 import `FinsDirectStreamProtocolError`。✓

**plan 验证：**
- §2.3 第 4 点已修正为准确描述："producer callees 当前没有 `FinsDirectStreamProtocolError` origin；`_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` 已完整表达真实 producer 数据流。producer 的 generic execution exception 继续映射为有界 business failure `RESULT`"
- §4 不变量 6："raw bridge 的 native async error/cancellation 由 async generator 自然传播，validator 是 missing/duplicate/event-after 三种 protocol error 的唯一构造 owner"
- §5.4/§5.5：无 typed queue item、无 producer catch、无对应 test
- §7.1：无 `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity`

speculative path 已彻底删除。✓

### 3.4 R09-PR-F04 — terminal-result availability contract ✓ CLOSED

**plan §3.2（直接证据）：**
"`terminal_result` 只允许在 clean exhaustion 后读取。OPEN、RESULT_BUFFERED 或 consumer/error/cancel 导致的 abortive close 后读取，统一抛普通 `RuntimeError`，消息固定来自 `direct_stream.py` 模块私有常量 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE = "Fins direct terminal result is not available before clean stream exhaustion"`。这属于调用方 programmer-contract violation，不是 missing/duplicate/event-after stream protocol error；不新增 public 或 private error class。"

**plan §4 不变量 7（直接证据）：**
"`terminal_result` 只有 clean exhaustion 后可读；OPEN、RESULT_BUFFERED 和所有 abortive close 路径使用 §3.2 的同一 module-owned safe message 抛普通 `RuntimeError`。clean exhaustion 后返回 buffered result 中的同一 `FinsResultSummary` object。"

**§7.1 exact tests（直接证据）：**
- `test_validated_stream_terminal_result_in_open_raises_owned_runtime_error`
- `test_validated_stream_terminal_result_while_result_buffered_raises_owned_runtime_error`
- `test_validated_stream_terminal_result_after_abortive_close_raises_owned_runtime_error`
- `test_validated_stream_terminal_result_after_clean_exhaustion_is_same_object`

四类 availability/object tests 完整，使用 `RuntimeError` + `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE`，不新增 error class。Controller rejected DS-N01（不需要 `CLOSED_CLEAN/CLOSED_ABORTED` 新状态），plan 正确采纳。✓

### 3.5 R09-PR-F05 — retain existing CLI public presentation ✓ CLOSED

**直接代码证据：**
- 当前 CLI `run_fins_direct_command`（line 203-204）：`except FinsDirectStreamProtocolError as exc: render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`
- plan §5.4 CLI："run_fins_direct_command catch owner error时严格沿用现有 `render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`，返回既有 `EXIT_FAILURE`；不得展示 raw `reason.value`，不得 import/枚举 reason、解析 message 或重建 error"

**plan §5.3 README fresh scan（直接证据）：**

| README | decision | rationale |
|---|---|---|
| 根 `README.md` SHA `2f5cebfd...` | no update | 无 Fins direct protocol reason/error-code format 章节 |
| `dayu/README.md` SHA `16bbdc87...` | no update | 分层/装配不变 |
| `dayu/fins/README.md` SHA `50c07ae6...` | **implementation 必须更新** | 当前 line 511 写 plain `AsyncIterator` 且只覆盖 missing/duplicate |
| `dayu/service/README.md` SHA `8d7d7680...` | **implementation 必须更新** | 当前 lines 15/35 把 terminal 收口归给 Service |
| `tests/README.md` SHA `6c0614af...` | **implementation 必须更新** | 当前 lines 149/196 将 missing/duplicate checker 归给 Service/runtime |

CLI 保持既有 presentation，README trigger 正确。✓

### 3.6 R09-PR-F06 — operation-kind provenance propagation ✓ CLOSED

**直接代码证据：**
- Service `process_filing`（line 264）：`self._preprocess(operation_kind=FinsOperationKind.PROCESS_FILING, ...)`
- Service `process_material`（line 294）：`self._preprocess(operation_kind=FinsOperationKind.PROCESS_MATERIAL, ...)`
- `_preprocess`（line 466）：`return _ensure_result_event(self._runtime.preprocess(request, ...), operation_kind=operation_kind, ...)`
- Runtime `preprocess`（line 2207）：`direct_operation_kind=FinsOperationKind.PREPROCESS`

**plan §3.4（直接证据）：**
"Service 的 `process_filing/process_material` 名称与 runtime validator 的 `PREPROCESS` 值有意不同：前者只是入口/日志语义，后者才是 direct stream error provenance。"

**plan §7.2/§7.3（直接证据）：**
- Service: `[新增] test_process_filing_keeps_runtime_preprocess_protocol_error_provenance`
- Service: `[新增] test_process_material_keeps_runtime_preprocess_protocol_error_provenance`
- CLI: `[新增] test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli`
- CLI: `[新增] test_process_material_keeps_runtime_preprocess_protocol_error_provenance_through_cli`

provenance identity 与反例 tests 完整。✓

## 4. New Challenge 验证

### 4.1 Challenge 1: exact plain-def/raw-bridge/Service/CLI signatures 与调用是否符合当前代码

**结论: PASS — 签名表精确，调用链无歧义**

plan §3.4 的 18 行签名表逐条对照当前代码验证（见 §3.1）。关键验证点：

1. runtime `download/preprocess/upload` 当前是 `async def` 含 `yield`（async generator），改为 plain `def` 返回 `ValidatedFinsEventStream`。移除 `yield` 后 `async` 无意义——`ValidatedFinsEventStream` 是同步构造的具体对象，不是 coroutine。✓
2. `_run_direct_stream` 保持 `async def` async generator，返回类型从 `AsyncIterator[FinsEvent]` 收窄为 `AsyncGenerator[FinsEvent, None]`。方法体仍含 `yield item` 和 `yield result_event`（后者将被删除，只保留 `yield item`）。✓
3. Service protocol/public methods 当前已是 plain `def`，只改返回类型。`return self._runtime.download(...)` 继续透传。✓
4. CLI helpers 当前是 plain `def` 返回 `AsyncIterator[FinsEvent]`，改为返回 `ValidatedFinsEventStream`。`stream = _open_direct_stream(...)` 无 `await`。✓
5. `_wait_for_terminal_handling_sigint` 删除 `operation_kind` 参数。`_consume_fins_direct_events` 删除 `operation_kind` 参数。✓

无歧义，implementation agent 可直接参照。✓

### 4.2 Challenge 2: missing/duplicate/event-after/result-then-error、primary error/cancel 与 cleanup cause、close-at-most-once、terminal_result availability 是否可实现且无隐藏状态矛盾

**结论: PASS — 状态机自洽，无隐藏矛盾**

**状态转换完整性验证：**

| 状态 | 事件 | 下一状态 | 行为 |
|---|---|---|---|
| OPEN | PROGRESS | OPEN | yield 原 event |
| OPEN | first RESULT | RESULT_BUFFERED | buffer event + FinsResultSummary |
| OPEN | clean EOF | CLOSED | raise MISSING_RESULT |
| OPEN | upstream error/cancel | CLOSED | 记录 primary，cleanup close，传播 primary |
| RESULT_BUFFERED | second RESULT | CLOSED | 构造 DUPLICATE_RESULT 为 primary，cleanup close |
| RESULT_BUFFERED | later PROGRESS | CLOSED | 构造 EVENT_AFTER_RESULT 为 primary，cleanup close |
| RESULT_BUFFERED | upstream error/cancel | CLOSED | 丢弃 buffered RESULT，记录 primary，cleanup close |
| RESULT_BUFFERED | clean EOF | RESULT_YIELDED | yield buffered RESULT |
| RESULT_YIELDED | next __anext__ | CLOSED | StopAsyncIteration |
| any non-CLOSED | consumer aclose() | CLOSED | close raw source at most once，传播 close error |

**隐藏状态矛盾检查：**

1. **RESULT_YIELDED 后 upstream error**：不可能。RESULT_YIELDED 只从 RESULT_BUFFERED + clean EOF 进入。clean EOF 意味着 producer 已完成且 queue 已 drain，不会再有 upstream event/error。MiMo original review F-CANDIDATE-03 已确认此点，Controller rejected 该 finding。✓
2. **duplicate 路径后 consumer aclose() race**：duplicate 路径先 cleanup close source，再 raise primary error。raise 后 `__anext__` 传播 error，consumer 收到 error 后调用 `aclose()`。此时 close-attempted guard 检测到 source 已 close，不再调用底层 `aclose()`。无 race。✓
3. **upstream error in RESULT_BUFFERED 后 buffered RESULT 丢弃**：plan §4 明确"丢弃 buffered RESULT"。consumer 看到的是 upstream error（primary），不是 result。`result -> error` 不先发布 success。✓
4. **close failure chaining 一致性**：所有路径统一使用 `raise primary from cleanup_error`。`primary.__cause__ is cleanup_error`。不使用 `__context__`（implicit chaining），使用 `__cause__`（explicit chaining）。✓
5. **close-attempted guard 与 CLOSED 状态关系**：guard 是私有 bool flag，独立于状态枚举。即使状态已是 CLOSED，重复 `aclose()` 检查 guard 后不再调用底层。不引入 `CLOSED_CLEAN/CLOSED_ABORTED` 子状态。✓
6. **terminal_result availability flag 与 clean exhaustion**：由单独的 clean-exhaustion flag 唯一表达（§4 不变量 7），不由状态名推断。RESULT_YIELDED 后设置 flag；abortive close 不设置。✓

无隐藏状态矛盾。✓

### 4.3 Challenge 3: speculative producer protocol-error channel 是否已彻底删除且既有 generic business-failure mapping 不变

**结论: PASS — 彻底删除，既有 mapping 不变**

验证方法：搜索 plan 全文。

- "typed queue item"：仅出现在 §2.3 第 4 点作为历史描述（"producer callees 当前没有 FinsDirectStreamProtocolError origin"）和 §3.4 表格 `_run_direct_stream` 行的"不再判断 terminal protocol"。无新增 queue variant。✓
- "producer protocol-error"：仅出现在 §2.3 第 4 点和 §1.4（Controller adjudication 裁决记录）。无新增 producer catch。✓
- `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity`：已删除。✓

既有 contract 保持：
- `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone`（§2.3 第 4 点）✓
- `_run_direct_stream_producer` 的 `except Exception → business failure RESULT`（§4 不变量 6）✓
- raw bridge native async error/cancel 自然传播（§4 不变量 6）✓

### 4.4 Challenge 4: Service/CLI provenance identity tests 是否在不重写 owner 算法情况下可执行

**结论: PASS — 可执行，不重写 owner 算法**

**fixture 纪律验证（plan §7.4）：**

1. **Service fake runtime**：必须返回同一个 `ValidatedFinsEventStream`，或抛一个由 Fins owner test fixture 预先取得的 typed error。实现方式：构造一个 fake async generator 产出 invalid raw sequence（如无 RESULT），传给 production `ValidatedFinsEventStream`，让它产生 typed error。Service test 断言返回的 stream/error 是同一个 object。不重写 protocol algorithm。✓
2. **CLI fake Service**：必须返回同一个 production validator stream/error。实现方式：同上。不得用裸 tuple 正常耗尽迫使 CLI 重建 missing。✓
3. **process_filing/material 反例**：断言返回 stream identity、error `reason/operation_kind/message/object`，证明 `operation_kind is PREPROCESS` 而不是 `PROCESS_FILING/PROCESS_MATERIAL`。实现方式：fake runtime 的 `preprocess` 返回一个 `ValidatedFinsEventStream`，其 `operation_kind=FinsOperationKind.PREPROCESS`。Service `process_filing` 透传该 stream。test 断言 stream 的 `operation_kind` 是 `PREPROCESS`。✓

provenance identity tests 可执行。✓

### 4.5 Challenge 5: CLI 保持既有 presentation、README triggers、coverage>=80、pyright/Ruff/source scans、真实 smoke 是否完整

**结论: PASS — 全部完整**

| 验证项 | plan 位置 | 状态 |
|---|---|---|
| CLI `dayu-cli {command}: {exc.message}` + EXIT_FAILURE | §5.4 CLI | ✓ 保持 |
| README trigger: 根/dayu no-update, fins/service/tests update | §5.3 | ✓ 有 fresh SHA 和 rationale |
| 每个 changed production file coverage >=80% | §8.2 | ✓ 逐文件 `--fail-under=80` |
| full pyright 0 errors | §8.3 | ✓ |
| scoped Ruff 零 | §8.3 | ✓ 覆盖所有 changed Python files |
| source/propagation scans | §8.4 | ✓ 四组 rg scan + 判定规则 |
| 真实 download/preprocess/upload smoke | §9.1 | ✓ 三条 `python -m dayu.cli` 命令 |
| injected adversarial smoke | §9.2 | ✓ 明确区分 test injection |

### 4.6 Challenge 6: no overdesign / no fallback / security / no Topic 8/9 / deferred Issue scope

**结论: PASS — 全部合规**

| 验证项 | 直接证据 |
|---|---|
| 无 overdesign | §3.1: 新模块只承载一个状态机 + 私有状态，不建立 framework/factory/profile/兼容层 |
| 无 fallback | §5.6: 禁止 compatibility re-export/wrapper、loose parsing、hasattr/getattr |
| 无 hasattr/getattr | §3.2: "不使用 hasattr/getattr 或 loose close probing" |
| security retained | §10.3: safe-text guard、cancellation、backpressure、storage containment 全部保留 |
| no Topic 8 | §10.2: 明确不实施 |
| no Topic 9 | §10.2: 明确不实施 |
| deferred Issues | §10.2: 142/151/175/177/178 明确列出 |
| no factory/wrapper | §3.2: "不增加仅透传构造器的 factory/wrapper" |

## 5. Plan 内部一致性验证

### 5.1 §2.2 三处分散 decision 描述 vs 当前代码

| plan 陈述 | 代码证据 | match |
|---|---|---|
| runtime `_run_direct_stream` 缓存首个 RESULT | line 2752: `result_event: FinsEvent \| None = None` + line 2763: `if item.event_type is FinsEventType.RESULT` | ✓ |
| runtime DUPLICATE check | line 2764: `if result_event is not None: raise DUPLICATE` | ✓ |
| runtime MISSING check | line 2773: `if result_event is None: raise MISSING` | ✓ |
| Service `_ensure_result_event` 重复缓存 | line 495: `result_event: FinsEvent \| None = None` + line 498: `if result_event is not None: raise DUPLICATE` | ✓ |
| CLI 遇首个 result 即返回 | line 679: `if event.result is not None: return event.result` | ✓ |
| CLI missing fallback | line 690: `raise FinsDirectStreamProtocolError(MISSING_RESULT, ...)` | ✓ |
| CLI 无 duplicate checker | 代码确认：`_consume_fins_direct_events` 无 duplicate 检查 | ✓ |

plan §2.2 表格与当前代码完全一致。✓

### 5.2 §3.4 签名表 vs 当前代码

已在 §3.1 和 §4.1 完整验证。全部 18 行签名精确。✓

### 5.3 §4 状态机 vs §7.1 test nodes

| 状态转换 | 对应 test |
|---|---|
| OPEN → PROGRESS → yield | `test_validated_stream_yields_progress_then_buffered_result_only_after_clean_end` |
| OPEN → clean EOF → MISSING_RESULT | `test_validated_stream_missing_result_uses_fins_owned_typed_code` |
| RESULT_BUFFERED → second RESULT → DUPLICATE | `test_validated_stream_duplicate_result_is_primary_and_closes_source_once` |
| RESULT_BUFFERED → later PROGRESS → EVENT_AFTER | `test_validated_stream_event_after_result_is_primary_and_closes_source_once` |
| OPEN → upstream error → primary | `test_validated_stream_upstream_error_identity_is_primary_and_closes_source_once` |
| OPEN → upstream cancel → primary | `test_validated_stream_upstream_cancellation_identity_is_primary_and_closes_source_once` |
| DUPLICATE + close fail → primary + cause | `test_validated_stream_duplicate_error_stays_primary_when_cleanup_close_fails` |
| EVENT_AFTER + close fail → primary + cause | `test_validated_stream_event_after_result_error_stays_primary_when_cleanup_close_fails` |
| upstream error + close fail → primary + cause | `test_validated_stream_upstream_error_stays_primary_when_cleanup_close_fails` |
| upstream cancel + close fail → primary + cause | `test_validated_stream_upstream_cancellation_stays_primary_when_cleanup_close_fails` |
| result → error → no result | `test_validated_stream_result_then_error_propagates_same_error_without_result` |
| aclose → close error | `test_validated_stream_explicit_aclose_propagates_same_close_error_without_primary` |
| repeated aclose → close once | `test_validated_stream_repeated_aclose_closes_source_once` |
| repeated aclose after fail → no retry | `test_validated_stream_repeated_aclose_after_close_failure_does_not_retry_source` |
| terminal in OPEN → RuntimeError | `test_validated_stream_terminal_result_in_open_raises_owned_runtime_error` |
| terminal in RESULT_BUFFERED → RuntimeError | `test_validated_stream_terminal_result_while_result_buffered_raises_owned_runtime_error` |
| terminal after abortive close → RuntimeError | `test_validated_stream_terminal_result_after_abortive_close_raises_owned_runtime_error` |
| terminal after clean exhaustion → same object | `test_validated_stream_terminal_result_after_clean_exhaustion_is_same_object` |

18 个 owner tests 覆盖 §4 状态机全部转换和不变量。✓

### 5.4 §5.4 删除清单 vs §5.5 不得修改清单 无交集

| 删除项 | 不得修改范围 | 交集 |
|---|---|---|
| `_ensure_result_event` 全函数 | — | 无（Service 内部函数） |
| `_direct_operation_kind` 全函数 | — | 无（CLI 内部函数） |
| CLI `_consume_fins_direct_events` 尾部 MISSING fallback | — | 无（CLI 内部逻辑） |
| CLI `operation_kind` 参数 | — | 无（CLI 内部签名） |
| runtime `result_event`/duplicate/missing 分支 | — | 无（runtime 内部逻辑） |
| Service/CLI imports | — | 无（内部 import） |

不得修改清单确认：docs/design/umbrella/R06/R08/storage/pipelines/Host/Engine/config/Web/WeChat/render 均不在 production allowlist 中。✓

### 5.5 §6 S1/S2 cumulative cutover 逻辑

- S1 建立 validator owner + runtime raw bridge 接入 ✓
- S2 在同一 S1 tree 上删除 Service/CLI checker ✓
- cumulative acceptance: S1+S2 一次 accept ✓
- zero-validator 防线: "任何可 accepted tree 均不得出现 zero-validator" ✓
- S2 不在 S1 之前 commit ✓

### 5.6 §8 validation matrix 可执行性

| 命令 | 可执行性 |
|---|---|
| §7.1 S1 pytest | ✓ exact test nodes |
| §7.2 S2 Service pytest | ✓ exact test nodes |
| §7.3 S2 CLI pytest | ✓ exact test nodes |
| §8.1 complete-tree pytest | ✓ |
| §8.2 coverage per-file | ✓ `--data-file`, `--include`, `--fail-under=80` |
| §8.3 pyright | ✓ `python -m pyright dayu/ tests/ utils/` |
| §8.3 Ruff | ✓ scoped to changed files |
| §8.4 rg scans | ✓ 四组 scan + exit 1 = 预期零命中 |
| §9.1 real smoke | ✓ 三条 `python -m dayu.cli` 命令 |
| §9.2 injected smoke | ✓ Fins/Service/CLI injection |

## 6. Umbrella Alignment

### 6.1 Topic 6.5 裁决实现

plan 完全实现 Topic 6.5："Make exactly-one direct-stream terminal a single Fins-owned validator contract; Service and CLI mechanically consume it"。✓

### 6.2 umbrella §7.4 closed affected-module manifest

R09 production allowlist: `direct_events.py`, `direct_stream.py` (new), `ingestion_runtime.py`, `fins_direct.py`, `fins.py` CLI。与 umbrella §7.4 R09 entry 一致。✓

### 6.3 umbrella §7.3 gate 流程

plan §12 完整列出与 umbrella §7.3 一致的 gate 流程。artifact naming stem 固定为 `wu-semantic-ownership-01-r09-fins-direct-stream-validator-*`。✓

## 7. Residual Risks

| risk | severity | owner | destination |
|---|---|---|---|
| Fins thread-backed 长事务不可物理取消 | external | Issue 175 | 不属于 R09 accepted contract |
| Docling 环境不可用导致 upload smoke skip | gate | R09 completion | 不接受 skip |
| SEC 网络不可用导致 download smoke fail | gate | R09 completion | 不接受 skip |
| `ingestion_runtime.py` 6933 行 coverage 基线 | moderate | R09 implementation | 先测 baseline，不足则 stop 回 Controller |
| control doc SHA 漂移（已提交 vs plan 记录） | none | expected | Controller 工作流正常行为 |

## 8. Finding Ledger

| ID | severity | type | disposition |
|---|---|---|---|
| （无） | — | — | zero new findings |

## 9. Closure Ledger

| finding | status | closure evidence |
|---|---|---|
| `R09-PR-F01` | closed | §3.1 签名表 18 行精确对照，调用链无新增 await |
| `R09-PR-F02` | closed | §3.2 precedence/idempotence contract + 7 exact tests |
| `R09-PR-F03` | closed | §3.3 speculative path 彻底删除 + 既有 mapping 不变 |
| `R09-PR-F04` | closed | §3.4 RuntimeError + safe message + 4 availability tests |
| `R09-PR-F05` | closed | §3.5 CLI presentation retained + README fresh scan |
| `R09-PR-F06` | closed | §3.6 provenance identity + process alias anti-example tests |

## 10. Conclusion

fixed plan SHA-256 `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`（773 行）是 code-generation-ready 的。

- R09-PR-F01..F06 全部确认关闭，有直接代码证据支撑。
- 状态机自洽，无隐藏状态矛盾。
- 签名表精确，调用链无歧义。
- speculative producer protocol-error channel 已彻底删除。
- provenance identity tests 可在不重写 owner 算法下执行。
- CLI 保持既有 presentation，README triggers 正确。
- coverage/pyright/Ruff/scans/smoke 完整可执行。
- 无 overdesign/fallback/security 漏洞。
- Topic 8/9、deferred Issues 明确不实施。

零 new findings。plan 可直接进入下一 gate。

---

AgentMiMo re-review verdict: **PASS**

## Artifact Metadata

- Artifact path: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-mimo.md`
- Target SHA-256: `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` — VERIFIED MATCH
- Target lines: 773 — VERIFIED MATCH
- No modifications made to: plan target, control doc, code, tests, README, any other artifact
- Artifact lines: 426
- `git diff --check`: PASS
- Staged tree: empty
- Git status: no stage, commit, push, or PR
