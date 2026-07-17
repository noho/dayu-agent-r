# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Review — AgentDS

## 0. Metadata

- **Reviewer**: AgentDS (adversarial plan review)
- **Immutable target**: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
- **Target SHA-256**: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`
- **Target lines**: 689
- **Controller entry**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-entry-controller-validation.md`
- **Entry verdict**: `PASS / READY_FOR_DUAL_INDEPENDENT_PLAN_REVIEW`
- **Current base**: R08 completion accepted commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`
- **Second reviewer**: AgentMiMo（独立并发，不参考彼此结论）
- **Date**: 2026-07-17

## 1. Verdict Summary

**Overall verdict: PASS — 5 accepted-candidate findings, 0 blocking, 0 rejected, 3 notes.**

本计划对 root cause 的判定正确（三层分散 decision，见 §2.2/2.3），唯一语义 owner 设计自洽（§3），状态机覆盖所有主要分支（§4），production/test/README 闭集精确（§5），S1/S2 cumulative cutover 逻辑成立（§6），validation matrix 可执行（§7/8），smoke 区分真实与 test-injected（§9），R06/R08 no-regression 边界清晰（§10），stop conditions 与 residual owner 完整（§13）。

五个 accepted-candidate finding 均为 material severity，不阻塞 plan acceptance，但必须在 implementation 前由 Controller 逐 finding adjudication + AgentCodex plan fix 关闭。

## 2. Pre-Review Evidence Verification

### 2.1 Target SHA-256 match

实际 sha256sum 输出 `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`，与 Controller entry §1 及 plan §0 声明一致。**PASS**。

### 2.2 Current evidence locks verification

逐个核验 plan §1.3 表格中 current evidence SHAs：

| file | plan SHA | actual SHA | match |
|---|---|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d...` | `b34cb82d...` | ✓ |
| `dayu/fins/ingestion_runtime.py` | `176d8ab9...` | `176d8ab9...` | ✓ |
| `dayu/service/fins_direct.py` | `875d5396...` | `875d5396...` | ✓ |
| `dayu/cli/commands/fins.py` | `666d9dc2...` | `666d9dc2...` | ✓ |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be57...` | `6480be57...` | ✓ |
| `tests/service/test_fins_direct.py` | `9c533d7e...` | `9c533d7e...` | ✓ |
| `tests/cli/test_fins_commands.py` | `525414da...` | `525414da...` | ✓ |

全部匹配。**PASS**。

### 2.3 Current test nodes 核验

逐个 grep 验证 plan §7.1-7.3 中标记为 `current` 的 test node 是否确实存在于当前代码：

**tests/fins/test_fins_ingestion_runtime.py**：
- L1721 `test_direct_download_stream_writes_storage_and_does_not_create_job_record` ✓
- L1839 `test_direct_download_unsupported_source_returns_failure_result` ✓
- L1859 `test_direct_stream_missing_result_raises_protocol_error` ✓
- L1899 `test_direct_stream_duplicate_result_raises_protocol_error` ✓
- L1954 `test_direct_stream_drains_to_done_before_yielding_result` ✓
- L2010 `test_direct_download_uses_operation_scoped_cancellation_token` ✓
- L2601 `test_direct_upload_stream_omits_paths_job_ids_and_raw_payload_text` ✓

**tests/service/test_fins_direct.py**：
- L259-596 全部 12 个 `current` nodes 存在 ✓

**tests/cli/test_fins_commands.py**：
- L407-1051 全部 11 个 `current` nodes 存在 ✓

全部核验通过。**PASS**。

### 2.4 三处分散 decision 反例核验

直接阅读 current 代码确认 plan §2.2 表格陈述：

| 层 | plan 陈述 | 代码证据 | 结论 |
|---|---|---|---|
| Runtime `_run_direct_stream` (L2696-2782) | 缓存首个 RESULT，重复抛 DUPLICATE，缺失抛 MISSING | L2763-2778 精确对应 | ✓ 陈述准确 |
| Service `_ensure_result_event` (L475-513) | 再次判定 missing/duplicate | L495-513 精确对应 | ✓ 陈述准确 |
| CLI `_consume_fins_direct_events` (L662-694) | 遇首个 result 返回，正常耗尽构造 missing fallback；无 duplicate checker | L679-693 精确对应；无 duplicate 分支 | ✓ 陈述准确 |

plan §2.2 对 CLI 的表述"当前没有 duplicate checker"与代码证据完全吻合。**PASS**。

### 2.5 `hasattr/getattr` baseline

当前波及文件 `dayu/fins/direct_events.py`、`ingestion_runtime.py`、`dayu/service/fins_direct.py`、`dayu/cli/commands/fins.py` 均零 `hasattr/getattr` 使用。**PASS**。

## 3. Adversarial Plan Review Findings

### DS-F01 [accepted-candidate] [material] async API cutover 签名精确度不足

**直接证据**：
- plan §3.2 `ValidatedFinsEventStream` interface 正确，§5.4 描述 `download/preprocess/upload` "改为直接返回 `ValidatedFinsEventStream`"
- 当前代码 `FinsIngestionRuntime.download/preprocess/upload` (L2146-2253) 均为 `async def ... -> AsyncIterator[FinsEvent]`，内部 `async for event in self._run_direct_stream(...): yield event`
- 当前 Service protocol `FinsDirectIngestionRuntime` (L51-100) 声明三个方法返回 `AsyncIterator[FinsEvent]`
- 当前 CLI `_download_stream` 等返回类型标注为 `AsyncIterator[FinsEvent]`

**缺失**：plan 未精确写出每个 call site 的 exact signature transition：
- `FinsIngestionRuntime.download/preprocess/upload` 从 `async def` 变为 `def`（不再需要 yield），返回类型从 `AsyncIterator[FinsEvent]` 变为 `ValidatedFinsEventStream`
- Service protocol `FinsDirectIngestionRuntime` 三个方法签名从 `-> AsyncIterator[FinsEvent]` 变为 `-> ValidatedFinsEventStream`
- CLI stream helpers 参数/返回类型从 `AsyncIterator[FinsEvent]` 变为 `ValidatedFinsEventStream`
- `_run_direct_stream` 的最终形态：是保留为 async generator 但改为构造 validator，还是成为 factory method

**root cause**：§15 code-generation-ready 自检表已勾选所有项，但 exact `async def`→`def` 签名映射对 implementation agent 而言至关重要——ambiguity 可能导致 agent 错误保留 `async def` + `yield` wrapper 从而形成 "zero-validator" 中间态。

**owner-boundary fix**：在 plan §5.4 各 production 文件改动中，为每个变更函数/方法增加 exact signature line（`def` vs `async def`、完整返回类型、参数类型），形成 implementation 可直接参照的签名表。特别需要覆盖 `FinsDirectIngestionRuntime` protocol 三个方法的完整新签名。

**verification**：修改后对照 current tree 逐行检查每个签名 transition 是否 unambiguous；code-generation agent 不需要自行推断。

**blocking?**：否（§3.2 interface 足以推导，但 ambiguity 可能增加 implementation 返工风险）。

---

### DS-F02 [accepted-candidate] [material] exception/close precedence 形式化不完备

**直接证据**：
- plan §4 状态机 `RESULT_BUFFERED` second RESULT → "close raw source → FinsDirectStreamProtocolError(DUPLICATE_RESULT)"
- plan §4 不变量3："validator 不 catch 后转写 producer/upstream exception"
- plan §4 "any non-CLOSED state + consumer aclose()" → "close raw source exactly once → discard buffered RESULT if not yielded → propagate source close error unchanged → CLOSED"

**缺失**：

(a) **close 自身失败时的优先级未形式化**：当 duplicate/event-after 路径执行 "close raw source → FinsDirectStreamProtocolError(DUPLICATE_RESULT)" 时，若 `await raw_source.aclose()` 自身抛出（例如底层 transport IOError），validator 中有两个待传错误：close 异常（优先由 invariant 3 保证 "propagate unchanged"）和 protocol error（被吞掉）。plan 未明确声明"close error takes precedence, protocol error is discarded"，implementation agent 可能错误地 chain/suppress 二者。

(b) **aclose 幂等性与 state CLOSED 的 race**：`aclose()` 说是幂等的("exactly once")，但如果 consumer 在收到 `DUPLICATE_RESULT` 后调用 `aclose()`，而 validator 已在 duplicate 处理中关闭了 raw source，则 `aclose()` 必须检测到 source 已关闭并返回 None。plan §4 的 `any non-CLOSED state + consumer aclose()` 与 duplicate 路径的 "close raw source → ..." 在形式上有 race：duplicate 路径不在 CLOSED 状态（它在 RESULT_BUFFERED），所以 consumer 的 `aclose()` 也会尝试关闭。两种解决：(1) duplicate 路径设置 CLOSED 后再抛 error，或 (2) aclose 内检查 `_source_closed` flag。

**owner-boundary fix**：在 plan §4 增加显式"close 失败优先级"规则和 `aclose()` 幂等性 guarantee。建议补充两条 invariant：
- "close during error handling failure: close exception propagates; protocol error is discarded (not chained/suppressed)."
- "aclose() is idempotent: if raw source is already closed (by error-handling path or prior aclose), subsequent calls return None immediately."

**verification**：新增 owner test 直接验证 `aclose` 在 error path close 后的行为（plan §7.1 未覆盖此场景）。

**blocking?**：否（行为可从现有 invariant 推导，但 ambiguity 可能导致 implementation 差异）。

---

### DS-F03 [accepted-candidate] [material] producer protocol-error channel 证据链不完整

**直接证据**：
- plan §5.4 `ingestion_runtime.py`："为 `FinsDirectStreamProtocolError` 增加严格 typed queue item；`_run_direct_stream_producer` 在 generic execution-to-failure-result catch 前原样投递该 typed error。"
- plan §7.1 `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity`：通过真实 runtime queue bridge 证明 typed producer error 不被 generic failure RESULT 吞掉。
- 当前代码 `_run_direct_stream_producer` (L2783-2813)：`except Exception as exc: error_kind = _classify_direct_error(exc); self._emit_direct_result(context, status=FAILURE, ...)`
- current `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` (L1344) — 无 protocol error variant

**问题**：

(a) **谁是 typed error 的构造者？** Plan §3.3 说 validator 是"三种 protocol error 的唯一构造点"，但 producer 的 typed queue item for protocol error 需要构造该 error。如果 producer code 内检测到 `FinsDirectStreamProtocolError`（来自 validator 在 async context 中抛出的异常传入了 producer thread），它是"传递已有 object"而非"构造新 error"。plan 未明确区分"透传"与"构造"，导致 owner boundary 模糊。

(b) **typed queue item 的类型设计未指定**：`_DirectStreamQueueItem` 需要新增 variant，但 plan 未给出精确的 type alias 变化。implementation agent 可能误将 typed error 放在与 event/done 不同 priority 的处理路径。

**owner-boundary fix**：在 plan §5.4 `ingestion_runtime.py` 条目中明确：(1) `_DirectStreamQueueItem` 新增 `FinsDirectStreamProtocolError` variant（不新增 `_DirectStreamProducerError` wrapper class），(2) producer `except FinsDirectStreamProtocolError as pe` 在 generic `except Exception` 之前，直接 queue-put 同一 object，(3) validator `_run_direct_stream` bridge 遇到 queue 中的 protocol error 时原样 re-raise，(4) 此路径不产生新的 `FinsDirectStreamProtocolError` 实例，仅保证 identity pass-through。

**verification**：S1 test `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity` 使用 `is` 断言（非 `==`）验证 object identity。

**blocking?**：否（plan 已有 test node 和 motiviation，但 type alias 和 exact 流程缺细节）。

---

### DS-F04 [accepted-candidate] [material] terminal_result 前置条件错误类型未指定

**直接证据**：
- plan §3.2："`terminal_result` 返回 validator 缓存的同一 result object，不重算、不复制、不从最后事件之外推断；只允许在 clean exhaustion 后读取，提前读取的状态前置条件错误仍由该 Fins owner 抛出。"
- plan §3.2 interface 未列出 `terminal_result` 可能抛出的异常类型。

**缺失**：提前读取 `terminal_result`（如在 RESULT_BUFFERED 或 OPEN 状态）应抛出什么 typed error？plan 说"由该 Fins owner 抛出"但未指定错误类（是 `RuntimeError`？`FinsDirectStreamProtocolError`？还是新的 typed state error？）。implementation agent 可能自由选择错误类型，导致 Service/CLI 的 error handling path 需要猜测。

**owner-boundary fix**：在 plan §3.2 或 §4 中明确 `terminal_result` 前置条件违反时的异常类型。建议使用 `RuntimeError("terminal_result is not available before stream exhaustion")`，因为这不是 stream protocol error（不是 missing/duplicate/event-after），而是 API contract violation。或者新增 `class _TerminalNotAvailableError(RuntimeError)` 作为内部 state guard。

**verification**：新增 owner test 直接断言 `terminal_result` 在 stream 未耗尽时抛出指定类型。

**blocking?**：否（不影响主流程，但类型安全要求 closure）。

---

### DS-F05 [accepted-candidate] [material] CLI error format change 与 root README decision 的边界缺少直接证据

**直接证据**：
- plan §5.4 CLI："`run_fins_direct_command` catch owner error时展示 `[{exc.reason.value}] {exc.message}`"
- plan §5.3 根 README："不修改：command、参数、成功/失败/取消 exit mapping、工作区位置和最终用户工作流均不变"
- 当前 CLI 代码 (L203-204)：`render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")`
- 变更后输出从 `dayu-cli download: Fins direct stream ended without RESULT` 变为 `dayu-cli download: [missing_result] Fins direct stream ended without RESULT`

**问题**：CLI error output 的用户可见格式确实发生变化（增加了 `[code]` 前缀）。根 README update trigger 包含"用户可见...命令参数、默认输出通道"。plan 的论据是"typed protocol code 只是既有 CLI error presentation 增加同源 code，根手册没有对应错误码章节"（§5.3）。这个论据逻辑自洽——根 README 如果当前没有错误格式章节，则无内容需要更新。但 plan 未验证根 README 当前是否确实不含错误格式描述，只是做了一个假设。

**owner-boundary fix**：在 plan §5.3 中补充一条直接证据——确认根 README 当前不包含 Fins CLI error message format 描述，或在完成时补充 gating check："根 README 无 Fins direct 错误格式章节 → 无更新"。

**verification**：implementation 完成后实际读取根 README，确认真无相关章节。

**blocking?**：否（大概率根 README 确实无此细节，但应补充证据）。

---

### DS-N01 [note] State machine 枚举值 "CLOSED" 与 validator aclose 语义小差异

plan §4 状态机使用 `CLOSED` 表示终态，但 `aclose()` 描述中说 "close raw source exactly once → discard buffered RESULT if not yielded → propagate source close error unchanged → CLOSED"。这里 `CLOSED` 既表示 clean exhaustion 后的正常关闭（RESULT_YIELDED → CLOSED），也表示异常/consumer 主动关闭。两种 "CLOSED" 在 behavior 上不同：clean CLOSED 已 yield 过 terminal，abortive CLOSED 未 yield terminal。plan 隐含了这种区别但未显式命名（如 `CLOSED_CLEAN` vs `CLOSED_ABORTED`）。不影响 correctess——只要 `terminal_result` 的正确性由 "是否 clean exhaustion" guard 保证而非由状态名。implementation 时需注意。

### DS-N02 [note] Operation kind 差异的 cutover 边界正确但需显式测试

plan §2.2 指出 Service `process_filing/material` 的 `operation_kind=FinsOperationKind.PROCESS_FILING` 与 runtime `PREPROCESS` 不同。当前代码验证：Service `process_filing()` L265-273 使用 `FinsOperationKind.PROCESS_FILING`，而 runtime `preprocess()` L2183-2217 使用 `FinsOperationKind.PREPROCESS`。plan 的修复是删除 Service 层 checker（含 operation_kind），使 runtime 的 `operation_kind` 成为 error 中唯一来源。代码正确但 plan §7.3 CLI tests 中 `test_fins_owned_missing_result_code_is_rendered_by_cli` 与 `test_fins_owned_duplicate_result_code_is_rendered_by_cli` 应显式验证 `operation_kind` 与 validator 来源一致（而非与 Service command 名一致）。

### DS-N03 [note] Coverage 命令中 `--fail-under=80` 对 6933 行 ingestion_runtime.py 的可行性

`dayu/fins/ingestion_runtime.py` 当前 6933 行。R09 只修改其中 direct stream 相关部分（约 150 行），但 plan §8.2 要求整个文件 coverage `>=80%`。该文件同时承载 download/preprocess/upload job、observed path、legacy runtime——这些都是 R09 不改的部分。如果当前文件 coverage 已低于 80%，R09 implementation 不能为了凑覆盖率而修改无关代码。plan §8.2 正确声明了"若 allowlist 中某 production file 最终无 diff，可从 changed-file coverage ledger 移除，但必须用 diff 证明"，但实际 `ingestion_runtime.py` 必然有 diff（删除 `_run_direct_stream` 内 result_event/duplicate/missing 分支）。Implementation 时应先 measure baseline，若旧代码覆盖率不足导致文件 <80%，需 Controller 裁决是否接受 partial（只要求新增行 >=80%）。

## 4. Controller §3 六问逐项回答

### Q1: async API cutover — code-generation-ready?

**结论: PARTIALLY READY — 需 DS-F01 fix 后达到 ready**

plan §3.2 的 `ValidatedFinsEventStream` interface（`__aiter__` / `__anext__` / `aclose` / `terminal_result`）是 code-generation-ready 的。但 production call site 的 exact `def`/`async def`/return type transition 在 §5.4 描述粒度不够——当前 `download/preprocess/upload` 是 `async def` with `async for ... yield` wrapper，plan 说"改为直接返回"但未给 exact new signature。implementation agent 需要从 §3.2 推导，这是可行的但增加了出错风险。

`ValidatedFinsEventStream` 实现 `AsyncIterator[FinsEvent]` protocol，因此在类型上兼容所有当前 consumer 的 `AsyncIterator[FinsEvent]` 参数/返回类型标注。Service protocol 和 CLI helpers 的标注改变是 mechanical 的（类型 narrowing from `AsyncIterator[FinsEvent]` to `ValidatedFinsEventStream`），不引入类型不兼容。

关键点：`FinsIngestionRuntime.download/preprocess/upload` 从 `async def`→`def` 的正确性是自证的——不再需要 `async for ... yield` wrapper，因为 validator 本身就是 async iterator。只需要构造 raw queue bridge + `ValidatedFinsEventStream(source=raw_generator, operation_kind=...)` 并 return。

### Q2: exception/close precedence — 是否唯一且可实现？

**结论: 基本可唯一确定 — 需 DS-F02 fix 后完全唯一**

当前 plan 的不变量 3 保证 "validator 不 catch 后转写 producer/upstream exception, 不把 cancel、close 或 protocol error 合成为 business RESULT"。这建立了基础优先级：上游错误 > buffered result > 无错误。

但 "close then raise protocol error" 场景中 close 自身的失败优先级需要补充（DS-F02a）。`aclose()` 幂等性需要显式保证（DS-F02b）。

技术上可实现：validator 内部维护 `_source_closed: bool` flag，在 `aclose()` 和 error-handling close 路径都检查并设置它；`__anext__` 在所有 raise 前先 `await self._source.aclose()` 并捕获其异常决定 propagate chain。

资源泄漏风险：如果 duplicate 路径的 `aclose()` 成功但后续 `raise FinsDirectStreamProtocolError` 前发生意外（如 event loop 关闭），raw source 已 close 完成、buffer 已 discard——无泄漏。如果 `aclose()` hang（底层 transport stall），需要外部 task cancellation。plan 依赖既有 cancellation infrastructure。

### Q3: producer protocol-error channel — speculative 或必要？

**结论: 必要，非 speculative — 但需 DS-F03 fix 精确化**

该 channel 解决的实际问题是：如果 validator 在 `_run_direct_stream` (async context) 抛出的 `FinsDirectStreamProtocolError` 以某种方式进入 producer thread（例如通过 cancellation propagation 或 shared state），producer 的 `except Exception` (L2803) 会把它转成 business failure RESULT，从而丢失 typed error identity。

但更直接的场景是：producer function 内部（`_produce_direct_download` 等）或其调用的代码可能间接触发 validator 逻辑（如果 validator 的某些检查被内联到 producer 路径），`FinsDirectStreamProtocolError` 会从 producer function 抛出并被 generic catch 吞掉。

typed queue item 的最小实现：在 `_DirectStreamQueueItem` union 中加入 `FinsDirectStreamProtocolError`，producer try/except 结构新增 `except FinsDirectStreamProtocolError as pe: _put_direct_queue(context, pe); return` 在 generic `except Exception` 之前。这样 typed error 的 object identity 完整保留到 validator bridge。

这不是第二构造点（producer 不 new error，只 pass-through），不违反 validator 唯一 owner。

### Q4: mechanical consumer — Service/CLI 是否最小且不引入不必要耦合？

**结论: 最小、正确**

Service 变更：
- 删除 `_ensure_result_event`（含所有 duplicate/missing/operation_kind/ticker/filing_kind 参数传递）
- 六个 public method 直接 `return self._runtime.download/preprocess/upload(...)`（保留 request 构造和日志）
- 返回类型从 `AsyncIterator[FinsEvent]` 变为 `ValidatedFinsEventStream`

Service 不对 stream 做任何 decision，纯机械组装 request 并透传 result。耦合方向正确：Service → Fins（向下），CLI → Service → Fins（向下），无反向依赖。

CLI 变更：
- `_consume_fins_direct_events` 改为渲染全部事件后 `return events.terminal_result`
- 删除 `_direct_operation_kind` 和 `operation_kind` 参数（仅在 fallback 中使用）
- SIGINT/cancellation 逻辑不变

CLI 的 `terminal_result` property 访问是 property read，不是 decision。它等价于 "给我那个已经证明的 terminal result"——不判断、不构造、不 fallback。

`ValidatedFinsEventStream` 的 concrete class dependency 是否最小？是的——Service/CLI 需要消费 validated stream 并访问 terminal result。如果只暴露 `AsyncIterator[FinsEvent]`，CLI 又需要从 last event 自行提取 result（这恰是旧方案的"分散 decision"问题）。`terminal_result` property 是同一个 typed contract 的一部分，不构成额外耦合。

### Q5: CLI reason.value 展示 — 是否 LLM/user safe 且有 README 裁决依据？

**结论: safe，有裁决依据**

`FinsDirectStreamProtocolErrorKind` 的三个值：`"missing_result"`、`"duplicate_result"`、`"event_after_result"`（新增）。这些都是业务可读的英文 enum 字符串：
- 不包含内部治理 ID、job ID、路径、secret
- 自解释（missing/duplicate/event after result）
- 是 typed error code，不是自然语言消息（message 单独提供用户可读说明）

CLI 是开发者/operator 工具，不是 LLM-facing surface。`reason.value` 不会进入 Memory/Compact/Trace/Prompt，只出现在 stderr error output。

plan §5.3 对根 README 的 no-update decision 基础是"根手册没有对应错误码章节"。这是合理的——如果根 README 当前不描述 CLI error format，无需为新增 `[code]` 前缀更新。但应补充验证证据（DS-F05）。

Service README 的更新（删除"Service 对 missing/duplicate 做 terminal result 收口"）是必须的——当前 `dayu/service/fins_direct.py` 模块 docstring (L1-8) 没有该声明，但 Service README 可能包含。

### Q6: tests/smokes — 是否真实可执行？

**结论: 真实可执行，区分清晰**

**Test execution**：plan §7 和 §8 提供的是 exact `pytest` commands with specific test nodes，全部已在 current tree 核验存在。命令格式可直接复制执行。

**Real smoke** (§9.1)：三条真实 `python -m dayu.cli` 命令使用临时 `workspace/tmp/` 目录、具体参数、明确通过网络/processor 依赖。download 依赖 SEC 网络，upload 依赖 Docling/processor。plan 正确声明"缺依赖、网络失败、skip 或未实际进入 producer 都阻塞 R09 completion"。

**Test-injected adversarial smoke** (§9.2)：missing/duplicate/event-after/result-then-error 无法通过真实场景产生（producer 不会故意违反协议），必须通过 test injection。plan 正确区分并给出 Fins/Service/CLI 三层各自的 injection 策略。

**Coverage** (§8.2)：per-file `--fail-under=80` 命令 exact、data file 独立。注意 DS-N03 对 `ingestion_runtime.py` 6933 行的覆盖风险。

**pyright/Ruff** (§8.3)：全量 pyright `0 errors` 和 scoped Ruff 零要求明确。

**结论**：可直接执行。

## 5. Cross-Cutting Checks

### 5.1 语义 owner 唯一性

| 语义 | plan owner | 当前 code owner（分散） | 唯一性 |
|---|---|---|---|
| "恰好一个且最后 RESULT" | `ValidatedFinsEventStream` | `_run_direct_stream` + `_ensure_result_event` + `_consume_fins_direct_events` | ✓ 收敛为 1 |
| `MISSING_RESULT` error | `ValidatedFinsEventStream` | 三层均可构造 | ✓ 收敛为 1 |
| `DUPLICATE_RESULT` error | `ValidatedFinsEventStream` | Runtime + Service | ✓ 收敛为 1 |
| `EVENT_AFTER_RESULT` error | `ValidatedFinsEventStream` | （当前无） | ✓ 新增 owner |
| raw source lifecycle (aclose) | `ValidatedFinsEventStream` | `_run_direct_stream` `finally` 只 cancel（非显式 close） | ✓ 初次明确 owner |
| terminal result 实例 | `ValidatedFinsEventStream` | Runtime 缓存, Service 再缓存, CLI 从 event 取 | ✓ 收敛为 1 |
| CLI exit code mapping | CLI `_wait_for_terminal_handling_sigint` | FinsResultSummary.exit_code | ✓ 仍是 CLI（property read, 非 decision） |

### 5.2 依赖方向检查

```
dayu.fins.direct_stream (新增, 唯一 validator)
    ↑ import (source AsyncGenerator, operation_kind)
dayu.fins.ingestion_runtime (构造 raw queue bridge + 装配 validator)
    ↑ import (typed contract)
dayu.service.fins_direct (构造 request, 返回 validated stream)
    ↑ import (typed contract)
dayu.cli.commands.fins (消费 stream, 渲染, exit mapping)
```

全部向下依赖，无反向 import。`direct_stream.py` 不依赖 Service/CLI。Service 不依赖 CLI。**PASS**。

### 5.3 过度设计 / 耦合检查

- `ValidatedFinsEventStream` 是单一职责 async state machine，不建立 framework/factory/profile。**PASS**。
- `terminal_result` property 是 generic 的 property，不引入 callback/event listener/observer 模式。**PASS**。
- 不新增 `__init__.py` re-export，不建立 compatibility wrapper。**PASS**。
- 新模块 `direct_stream.py` 仅承载一个类 + 私有状态枚举 + message 常量，不扩大 scope。**PASS**。
- producer protocol-error channel 不引入第二 error constructor。**PASS**（需 DS-F03 精确化）。

### 5.4 R06/R08 no-regression

R06 (transaction/publication)：不改 batch token、source publication、storage 文件。R08 (financial/XBRL)：不改 contract、processor、read runtime、`fact_count`。两组 focused tests 和 full Fins tests 全绿要求明确（§8.1）。**PASS**。

### 5.5 Security

plan §10.3 retained security 逐项：
- direct event safe-text/leakage guard：保留 ✓
- operation-scoped cancellation checker：保留 ✓
- storage containment/symlink：不修改 ✓
- CLI generic error handling：不放宽 ✓
- typed protocol code 来自 enum，不解析 raw payload：明确 ✓

### 5.6 Topic 8/9 / deferred scope / residual owner

plan §10.2 明确不实施 R10-R12、Issues 142/151/175/177/178、Web/WeChat/render、Topic 8/9。§13 stop conditions 中列出需 escalation 的场景。已知外部风险 "Fins thread-backed 长事务不可物理取消" 归 Issue 175，R09 只保证 close 后不发布 synthetic terminal。**PASS**。

### 5.7 Cumulative S1/S2 cutover

plan §6.3："任一可 accepted tree 均不得出现 zero-validator；也不得把 S2 删除 checker 的 commit 放在 S1 owner 之前"。S1 先建立 validator owner，S2 叠加删除 Service/CLI checker。Cumulative acceptance 要求 S1+S2 整树一次 accept，不出现"validator 存在但 checker 也同时存在"的中间 accept commit。这个顺序保证从"三处 decision"一步切换到"一处 validator + 两处 mechanical consumer"。**PASS**。

### 5.8 fixture 纪律

plan §7.4 fixture 纪律精确：
- raw invalid event sequence 仅允许在 Fins owner tests
- Service fake runtime 必须返回 `ValidatedFinsEventStream` 或抛 typed error（identity pass-through），不得重写 protocol check
- CLI fake Service 必须消费 Fins validator 产出，不得用裸 tuple 迫使 CLI 重建 missing
- 断言用 `reason is FinsDirectStreamProtocolErrorKind.*`、object identity、event 顺序、yield 计数

**PASS**。

## 6. Residual Risks (post plan acceptance)

| risk | severity | description | owner |
|---|---|---|---|
| ingestion_runtime.py 覆盖率基线 | moderate | 6933 行文件，R09 只改 ~150 行，旧代码可能 <80%。若基线不足，需 Controller 裁决是否接受 partial。 | R09 implementation gate |
| real download smoke 网络依赖 | moderate | SEC EDGAR 不可控；firewall/DNS/VPN 可能阻塞。需在 environment 可用的前提下运行。 | R09 completion gate |
| Docling/processor 环境依赖 | moderate | upload/preprocess smoke 需要 Docling 可用。若环境缺依赖，smoke 不可跳过。 | R09 completion gate |
| ValidatedFinsEventStream 与 asyncio task/event loop 交互 | low | async generator 的 `aclose()` 在某些 event loop 状态下行为与文档可能有差异（Python 3.11 specific）。owner tests 运行在 pytest-asyncio 下应覆盖。 | R09-S1 implementation |

## 7. Finding Disposition Summary

| ID | severity | disposition | blocks acceptance? |
|---|---|---|---|
| DS-F01 | material | accepted-candidate | no |
| DS-F02 | material | accepted-candidate | no |
| DS-F03 | material | accepted-candidate | no |
| DS-F04 | material | accepted-candidate | no |
| DS-F05 | material | accepted-candidate | no |
| DS-N01 | — | note | no |
| DS-N02 | — | note | no |
| DS-N03 | — | note | no |

## 8. Review Completion Metadata

- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-review-ds.md`
- **Target SHA-256**: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210` — **VERIFIED MATCH**
- **Second reviewer**: AgentMiMo（独立并发，不参考本 review）
- **No modifications made to**: plan target, control doc, code, tests, README, any other artifact
- **Git status unchanged**: no stage, commit, push, or PR
