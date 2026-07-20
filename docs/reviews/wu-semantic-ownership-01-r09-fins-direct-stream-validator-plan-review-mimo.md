# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Review — AgentMiMo

## 0. Review Identity

- Reviewer: AgentMiMo
- Review type: adversarial plan review
- Immutable target: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
- Expected SHA-256: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`
- Actual SHA-256: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210` ✓
- Plan lines: 689 ✓
- Controller entry: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-entry-controller-validation.md`
- Review base: R08 completion accepted commit `a31ded764da0621b6e7a6c7c6a083b4bb6593d21`
- Staged tree: empty (verified: only plan + control transition uncommitted)

## 1. Verdict

**PASS — code-generation-ready**

Zero material blocking findings. Three accepted-candidate improvements (non-blocking), one rejected/note. Six high-risk questions answered below with direct evidence.

## 2. Adversarial Review Dimensions

### 2.1 目标/非目标

- **目标成立**: 第一性原理根因在 plan §2.2 有直接代码证据支撑。`_run_direct_stream` (line 2696)、`_ensure_result_event` (line 475)、`_consume_fins_direct_events` (line 662) 三处各自独立判定 missing/duplicate terminal，与 Topic 6.5 描述完全吻合。
- **非目标明确**: §10.2 列出 R10-R12、Issues 142/151/175/177/178、Web/WeChat/render、Topic 8/9、observed/legacy lifecycle。这些与 R09 scope 无交集。
- **严重性正确**: 三处分散 decision 可以独立判定或掩盖同一协议事实，属于 production-high。plan 没有高估。
- **Verdict**: PASS

### 2.2 唯一语义 owner

- **owner 定义明确**: `ValidatedFinsEventStream` 在 `dayu.fins.direct_stream` 中独占 §3.1 列出的六项职责。
- **data contract 分离**: `direct_events.py` 只拥有事件/结果/error data contract (496 行)；`ingestion_runtime.py` 负责 producer/queue 接入 (6933 行)。新模块只承载一个状态机与其私有状态，不过度设计。
- **新模块证据充分**: §3.1 说明 `direct_events.py` 已 495 行纯契约、`ingestion_runtime.py` 已 6932 行 God runtime；新模块理由成立。
- **no second owner**: Service/CLI 不构造 protocol error、不判定 terminal。§5.4 明确删除 `_ensure_result_event`、CLI `_direct_operation_kind`、CLI missing fallback。
- **Verdict**: PASS

### 2.3 状态机反例

- **OPEN + clean EOF → MISSING_RESULT**: 正确。当前 `_run_direct_stream` (line 2774) 在 `break` 后检查 `result_event is None`，行为一致。
- **RESULT_BUFFERED + second RESULT → DUPLICATE_RESULT**: 正确。当前 `line 2767` 检查 `result_event is not None`。
- **RESULT_BUFFERED + progress → EVENT_AFTER_RESULT**: 新增。当前 runtime 会在 RESULT 后继续 yield progress（§2.3 反例 1），validator 修正此问题。
- **result → error**: §4 不变量 2 说"buffered result 被丢弃，原 error 传播"。正确：消费者不能先看到 success 再看到 error。
- **upstream cancellation in RESULT_BUFFERED**: §4 说"丢弃 buffered RESULT，原 object 原样传播"。正确。
- **aclose 幂等**: §4 状态机最后一行确认。正确。
- **反例**: 发现一个 plan 未显式处理的边界（见 §3 F-MINOR-01）。
- **Verdict**: PASS（有一个 minor 需要澄清，不 blocking）

### 2.4 typed error identity

- **唯一 error object**: `FinsDirectStreamProtocolError` 在 `direct_events.py` 定义，§3.3 确认不另建 parallel schema。
- **唯一构造点**: validator 是三种 protocol error 的唯一构造点（§3.1）。Service 不 catch/rebuild（§5.4）。CLI 只 catch 并展示（§5.4）。
- **新增 EVENT_AFTER_RESULT**: §3.3 明确枚举增加 `event_after_result`，既有 code 保持。
- **canonical code**: `exc.reason.value`。§3.3 确认不增加 alias/property。
- **identity 传播**: Service 透传同一 object（§5.4），CLI catch 同一类型（§5.4）。
- **Verdict**: PASS

### 2.5 async iterator / aclose / cancel / exception lifecycle

- **source 类型**: `AsyncGenerator[FinsEvent, None]`，§3.2 明确声明。支持 `aclose()`。
- **aclose 幂等**: §4 状态机确认。validator 内部跟踪 closed 状态。
- **consumer aclose**: §4 "any non-CLOSED state + consumer aclose() → close raw source exactly once, discard buffered RESULT if not yielded, propagate source close error unchanged"。
- **task cancellation**: §4 不变量 6 确认 validator 的 cancellation/close 只负责 raw stream lifecycle，不新增 Host 治理。
- **exception in aclose**: plan 没有显式说明 close 失败时 protocol error 与 close error 的优先级（见 §3 F-MINOR-01）。
- **Verdict**: PASS（有一个 minor 需要澄清）

### 2.6 S1/S2 cumulative cutover

- **cumulative acceptance**: §6.3 明确 "R09 采用 cumulative single sub-WU acceptance，不是独立 slice acceptance"。
- **zero-validator 防线**: §6.3 "任何可 accepted tree 均不得出现 zero-validator；也不得把 S2 删除 checker 的 commit 放在 S1 owner 之前"。
- **S1 checkpoint**: S1 结束时 Service checker 可能仍重复观察已验证流，但 validator 必须存在。
- **S2 叠加**: S2 必须在同一 S1 tree 上。
- **Verdict**: PASS

### 2.7 allowed files

- **production allowlist (§5.1)**: 5 个文件，与 umbrella §7.4 R09 entry 完全一致。
- **test allowlist (§5.2)**: 4 个文件。
- **README allowlist (§5.3)**: 3 个文件，trigger decision 有明确依据。
- **不得修改清单 (§5.6)**: 完整且正确。
- **Verdict**: PASS

### 2.8 接口与依赖方向

- **依赖方向**: `direct_stream.py` → `direct_events.py`（数据 contract）。`ingestion_runtime.py` → `direct_stream.py`（构造 validator）。`service/fins_direct.py` → `ingestion_runtime.py`（消费 stream）。`cli/commands/fins.py` → `service/fins_direct.py`（消费 stream）。
- **无反向依赖**: validator 不依赖 Service/CLI。Service/CLI 不依赖 `direct_stream.py` 内部。
- **Protocol 更新**: `FinsDirectIngestionRuntime` protocol 返回类型从 `AsyncIterator[FinsEvent]` 改为 `ValidatedFinsEventStream`（plan §3.2 提及，§5.4 已覆盖，签名保持 `def`——见 §3 F-CANDIDATE-01）。
- **Verdict**: PASS

### 2.9 过度设计/耦合

- **新模块规模**: 只承载一个状态机与其私有状态，不建立 framework/factory/profile/兼容层（§3.1）。
- **不增加 wrapper**: §3.2 "不增加仅透传构造器的 factory/wrapper，不在 `dayu.fins.__init__` 做兼容 re-export"。
- **Service/CLI 最小化**: 删除 checker 后只做 mechanical pass-through/presentation。
- **Verdict**: PASS

### 2.10 tests / coverage / pyright / Ruff / scans / README / real smoke

- **test nodes**: §7 区分 current 与新增/替换 node，未冒充已存在。
- **coverage**: §8.2 逐文件 `>=80%`，命令可直接执行。
- **pyright**: §8.3 full pyright `0 errors`。
- **Ruff**: §8.3 scoped Ruff 覆盖所有 changed Python files。
- **scans**: §8.4 四组 rg scan，判定规则明确。
- **README**: §5.3 trigger decision 有明确依据。
- **real smoke**: §9.1 真实 download/process/upload smoke 命令可执行，依赖 SEC 网络和 Docling 环境。
- **injected smoke**: §9.2 明确区分 test injection 与 real smoke。
- **Verdict**: PASS

### 2.11 R06/R08 no-regression

- **R06**: §10.1 确认不改 storage/pipeline 文件。
- **R08**: §10.1 确认不改 financial/XBRL contract。
- **回归测试**: §8.1 包含 R06/R08 no-regression pytest 命令。
- **Verdict**: PASS

### 2.12 安全

- **retained security**: §10.3 完整列出不弱化的安全防线。
- **typed protocol code**: 来自 enum，不解析或回显 raw provider payload。
- **event leakage guard**: 不变。
- **Verdict**: PASS

### 2.13 Topic 8/9 / deferred scope / residual owner

- **Topic 8**: §10.2 明确不实施。
- **Topic 9**: §10.2 明确不实施。
- **deferred Issues**: §10.2 明确列出。
- **residual owner**: §13 stop conditions 表格完整。
- **Verdict**: PASS

## 3. Findings

### F-CANDIDATE-01 — runtime async-generator → plain def cutover 的签名语义未在 §5.4 显式列出

- **Severity**: LOW
- **Type**: accepted-candidate (plan 补充)
- **Evidence**:
  - 当前 `FinsIngestionRuntime.download` (line 2146): `async def download(...) -> AsyncIterator[FinsEvent]`，方法体含 `yield event`，是 async generator。调用它返回一个 async generator 对象，可直接用于 `async for`。
  - 当前 `FinsDirectIngestionRuntime.download` (line 54): `def download(...) -> AsyncIterator[FinsEvent]`，protocol 是普通 `def`。
  - 当前 `FinsDirectCommandService.download` (line 167): `def download(...) -> AsyncIterator[FinsEvent]`，普通 `def`，`return self._runtime.download(...)` 透传 async generator 对象。
  - 移除 `yield` 后，runtime 方法不再需要 `async`——变为 `def download(...) -> ValidatedFinsEventStream`，直接返回具体对象。Service protocol 和 public method 保持 `def`，只改返回类型。CLI call-site 无 `await` 变更。
  - plan §3.2 说返回类型改为 `ValidatedFinsEventStream`；§5.4 说 protocol 和 public methods 改返回类型。但 §5.4 未显式说明 runtime 方法从 `async def` 含 `yield` 改为 plain `def`（移除 yield 后 `async` 无意义）。
- **Root cause**: plan 覆盖了类型变更，但未显式说明 async generator → plain def 的语义切换：runtime 方法签名从 `async def` 变为 `def`。
- **Owner-boundary fix**: AgentCodex 在 plan §5.4 `dayu/fins/ingestion_runtime.py` 改动中补充："`download`/`preprocess`/`upload` 从 `async def` 含 `yield`（async generator）改为 plain `def` 返回 `ValidatedFinsEventStream` 对象；Service protocol 和 public method 保持 `def`，只改返回类型；CLI call-site 无 `await` 变更"。
- **Verification**: plan §3.2 意图明确，§5.4 只需补充签名语义。
- **Blocking**: 否。

### F-CANDIDATE-02 — close 失败时 protocol error 与 close error 的优先级未显式说明

- **Severity**: LOW
- **Type**: accepted-candidate (plan 补充)
- **Evidence**: plan §4 "duplicate/event-after 时先关闭 source，再从本模块构造 typed protocol error"；§4 "any non-CLOSED state + consumer aclose() → ... propagate source close error unchanged"。当 validator 在 duplicate/event-after 时关闭 source 且 close 失败，plan 没有显式说明 protocol error 与 close error 哪个传播。
- **Root cause**: §4 状态机的两处规则（"先关闭再抛 protocol error" 与 "propagate source close error unchanged"）在 close 失败场景下有潜在冲突。
- **Owner-boundary fix**: AgentCodex 在 plan §4 不变量中补充："duplicate/event-after 时 close 失败，protocol error 仍为最终传播的异常；close error 作为 `__context__` 附带，不覆盖 protocol error 的 reason/message/code"。或补充 §4 状态机对应转换的注释。
- **Verification**: 当前代码 `_run_direct_stream` 的 `finally` 块只调用 `cancellation_state.request_cancel()`，不调用 raw source 的 `aclose()`。新 validator 需要直接 close raw source，因此 close 失败是新的边界场景。
- **Blocking**: 否。implementation agent 大概率会选择 protocol error 优先（因为它是业务语义错误），但 plan 应显式说明。

### F-CANDIDATE-03 — RESULT_YIELDED 后 upstream error 丢失的边界未显式说明

- **Severity**: LOW
- **Type**: rejected/note
- **Evidence**: plan §4 RESULT_YIELDED 状态："next __anext__ → StopAsyncIteration → CLOSED"。如果 upstream 在 RESULT 被 yield 后、clean EOF 前产生 error（理论上不应该，因为 RESULT 只在 clean EOF 后 yield），该 error 会被 StopAsyncIteration 覆盖。
- **Root cause**: §4 不变量 1 说 "只有 clean upstream EOF 能证明首个 RESULT 唯一且最后，进而允许 yield"。这意味着 RESULT 只在 clean EOF 后 yield，因此 RESULT_YIELDED 后不应有 upstream error。这不是 plan 的缺陷，而是状态机的正确保证。
- **Rejection reason**: 状态机不变量 1 已保证 RESULT_YIELDED 只在 clean EOF 后进入，因此不存在 RESULT_YIELDED 后 upstream error 的场景。这不是需要补充的缺陷。
- **Blocking**: 否

### F-CANDIDATE-04 — producer protocol-error queue channel 应删除（speculative dead path）

- **Severity**: MEDIUM
- **Type**: accepted-candidate (plan 删除)
- **Evidence**: `FinsDirectStreamProtocolError` 在 `ingestion_runtime.py` 中只有两处 `raise`（line 2765, 2774），均在 `_run_direct_stream`（consumer side）。Producer callees (`_produce_direct_download`, `_execute_download_request`, pipelines, downloaders) 均不 import 或 raise 该异常。Validator 是唯一协议错误构造 owner，位于 queue consumer 侧，其 error 不会进入 producer thread。
- **Plan 引用**: §4 不变量 5 要求在 `_run_direct_stream_producer` 的 generic catch 前增加 `except FinsDirectStreamProtocolError` + typed queue item。§5.4 `ingestion_runtime.py` 改动列出 "为 `FinsDirectStreamProtocolError` 增加严格 typed queue item" 和 "producer 在 generic catch 前原样投递该 typed error"。§7.1 新增 `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity`。
- **Root cause**: plan §2.3 第 4 点基于假设性推理（"如果 protocol error 进入 producer 则会被吞掉"），但 direct source scan 证明 producer callees 无 protocol-error origin。新增 catch/queue/test 是 speculative dead path。
- **Owner-boundary fix**: AgentCodex 删除 plan §4 不变量 5 中 producer protocol-error queue 整段；删除 §5.4 `ingestion_runtime.py` 中 typed queue item 和 producer catch 相关改动；删除 §7.1 中对应 test。保留 producer 的 generic `except Exception → business failure RESULT` 不变。Raw bridge 的 native async error、cancel、clean EOF 通过 queue 和 async generator 自然传播。
- **Verification**: source scan 确认 producer callees 无 `FinsDirectStreamProtocolError` origin。
- **Blocking**: 否。删除 speculative 设计不影响 validator 唯一 owner 的正确性。

## 4. Controller §3 六个高风险问题回答

### Q1: async API cutover — exact def/async def/type/call-site cutover 是否 code-generation-ready

**结论: PASS — runtime async generator → plain def，Service/CLI 无签名变更**

- **当前签名（直接证据）**:
  - `FinsIngestionRuntime.download` (line 2146): `async def download(...) -> AsyncIterator[FinsEvent]`，方法体含 `yield event`（async generator）。调用返回 async generator 对象。
  - `FinsDirectIngestionRuntime.download` (line 54): `def download(...) -> AsyncIterator[FinsEvent]`，protocol 是普通 `def`。
  - `FinsDirectCommandService.download` (line 167): `def download(...) -> AsyncIterator[FinsEvent]`，普通 `def`，`return self._runtime.download(...)` 透传。
  - CLI `_open_direct_stream` (line 363): `stream = service.download(...)` 后 `async for event in stream`。无 `await`。
- **cutover 语义**: runtime 方法移除 `yield` 后不再需要 `async`——变为 `def download(...) -> ValidatedFinsEventStream`，直接返回具体对象。这不是 async def coroutine，而是 plain def 返回可迭代对象。
- **call-site 影响**: Service protocol 和 public method 保持 `def`，只改返回类型标注为 `ValidatedFinsEventStream`。`return self._runtime.download(...)` 继续透传。CLI 的 `stream = service.download(...)` 和 `async for event in stream` 不变——`ValidatedFinsEventStream` 实现 `__aiter__`/`__anext__`，与当前 async generator 对象的消费方式相同。
- **type propagation**: plan §3.2 覆盖了全链路类型变更。F-CANDIDATE-01 记录了 runtime `async def` → `def` 的签名语义补充。
- **结论**: cutover 是 code-generation-ready 的。runtime 从 async generator 变为 plain def 返回具体对象；Service 和 CLI 无 def/async def 切换、无 `await` 新增。`ValidatedFinsEventStream` 实现 `AsyncIterator[FinsEvent]` 接口，消费方式不变。

### Q2: exception/close precedence — close 与原错误的优先级/identity 是否唯一、无资源泄漏

**结论: PASS（有一个 low 需要澄清）**

- **state machine 规则**: §4 明确了 duplicate/event-after 时 "先关闭 source，再构造 typed protocol error"。upstream error/cancellation 时 "原 object 原样传播"。
- **资源释放**: §4 "aclose() 幂等关闭 source；不 yield/synthesize result"。finally 块确保关闭。
- **close 失败边界**: plan 没有显式说明 close 失败时 protocol error 与 close error 的优先级（F-CANDIDATE-02）。这不是 blocking 问题，但 plan 应补充说明。
- **identity 唯一性**: protocol error 由 validator 唯一构造（§3.1），Service 不 catch/rebuild（§5.4），CLI 只 catch 并展示（§5.4）。同一 object 从构造到消费全链路保持 identity。
- **无资源泄漏**: raw source 在所有路径上都被关闭（protocol error 路径先关闭再抛、upstream error 路径 finally 关闭、consumer aclose 路径关闭）。

### Q3: producer protocol-error queue — 是否 speculative、是否违反 validator 唯一构造 owner

**结论: 应删除 — speculative dead path，validator 是唯一协议错误构造 owner**

- **直接代码证据**:
  - `FinsDirectStreamProtocolError` 在 `ingestion_runtime.py` 中只有两处 `raise`：line 2765 (`DUPLICATE_RESULT`) 和 line 2774 (`MISSING_RESULT`)，均在 `_run_direct_stream` 内。该方法是 async generator，运行在 consumer 侧（async event loop），不在 producer thread 内。
  - `_run_direct_stream_producer` (line 2801) 调用 `producer(context)`。Producer callees (`_produce_direct_download` line 2815, `_execute_download_request` line 3667, 以及 `dayu/fins/pipelines/*.py` 和 `dayu/fins/downloaders/*.py`) 均不 import `FinsDirectStreamProtocolError`，无任何 `raise FinsDirectStreamProtocolError`。
  - Producer thread 与 validator（queue consumer）在不同线程。Validator 的 protocol error 在 consumer 侧 `__anext__` 中抛出，不会进入 producer thread 的 call stack。
- **plan §2.3 第 4 点复核**: "producer 当前 except Exception 会把包括 typed stream protocol error 在内的异常转换为业务 failure RESULT"。Direct source scan 证明 producer callees 无 protocol-error origin。该描述基于假设性推理，不是直接证据。
- **plan §4 不变量 5**: "必须在该 generic catch 前单独识别 `FinsDirectStreamProtocolError`，通过 typed queue item 传给 raw direct source"。在当前 call chain 下这是 dead code——producer thread 内永远不会抛出该异常。
- **应删除而非保留**: 新增 `except FinsDirectStreamProtocolError` + typed queue item + 对应 test 是 speculative dead path。Validator 位于 consumer side，是 protocol error 的唯一构造 owner；producer 的 generic `except Exception → business failure RESULT` 保持不变。Raw bridge 的 native async error、cancel 和 clean EOF 通过 queue 和 async generator 自然传播，不需要额外 channel。
- **Owner-boundary fix**: AgentCodex 删除 plan §4 不变量 5 中关于 producer protocol-error queue 的整段；删除 §5.4 `ingestion_runtime.py` 改动中 "为 `FinsDirectStreamProtocolError` 增加严格 typed queue item" 和 "_run_direct_stream_producer 在 generic execution-to-failure-result catch 前原样投递该 typed error"；删除 §7.1 中 `test_direct_stream_typed_producer_error_after_result_is_propagated_by_identity` 测试。

### Q4: mechanical consumer boundary — Service/CLI 是否必须依赖 concrete class + terminal_result

**结论: PASS — 最小机械消费、不形成不必要耦合**

- **concrete class 依赖**: `ValidatedFinsEventStream` 实现 `AsyncIterator[FinsEvent]`，Service/CLI 可以用 `async for` 消费，不需要知道内部状态机。依赖是类型层面的，不是行为层面的。
- **terminal_result property**: 只在 clean exhaustion 后可读（§3.2）。CLI 消费完 stream 后读取 `terminal_result` 获取已验证的 `FinsResultSummary`。这比当前 CLI "遇首个 result 即返回" 更安全，因为 validator 保证了 result 的唯一性和终态性。
- **不形成第二 owner**: Service 不读取 `terminal_result`（§5.4 说 "六个 public method 直接返回 runtime stream"）。只有 CLI 在消费完 stream 后读取。
- **最小性**: Service 删除 `_ensure_result_event` 后只剩 request 构造 + stream 透传。CLI 删除 missing fallback 后只剩 event 渲染 + terminal result 读取。这是最小机械消费。

### Q5: CLI reason.value 展示 / README 是否有裁决依据且 LLM/user safe

**结论: PASS — 有裁决依据、LLM/user safe**

- **裁决依据**: Topic 6.5 用户裁决 "One shared stream validator/typed terminal owner should decide it once; upper layers should only map the resulting typed success/error to their presentation"。CLI 展示 `reason.value` 是 presentation mapping 的一部分。
- **LLM/user safe**: CLI 展示格式为 `[{exc.reason.value}] {exc.message}`（plan §5.4）。
  - `reason.value` 是 `missing_result`、`duplicate_result`、`event_after_result` 三个封闭 enum 字面量值（`direct_events.py` line 81-85），不含内部实现细节、路径、payload 或敏感信息。
  - `message` 由 validator 构造时使用模块级常量字符串（如 "Fins direct stream ended without RESULT"），不是用户输入或 provider raw payload。`FinsDirectStreamProtocolError.__init__` (line 122-133) 只检查 `isinstance(reason)` / `isinstance(operation_kind)` / `message.strip()` 非空；不调用 `_validate_safe_text`。安全性来源是 validator 的 constant message，不是 constructor 的 safe text 校验。
- **README trigger**: §5.3 说 fins/service/tests README 必须更新，根/dayu README 不更新。trigger decision 有明确依据：CLI error presentation 增加同源 code，但 command、参数、exit mapping、工作区位置和用户工作流不变。

### Q6: real download→process、upload smoke 及测试/coverage 命令是否真实可执行

**结论: PASS — 命令真实可执行，但依赖外部环境**

- **real smoke 命令**: §9.1 给出三条 `python -m dayu.cli` 命令，使用 `--base workspace/tmp/r09-real-*` 隔离目录。
- **依赖**: download 依赖 SEC 网络（`--ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31`）；upload 依赖 Docling 环境（`tests/fins/fixtures/aapl_xbrl/...`）；preprocess 依赖已有 source doc。
- **通过信号**: 三条 command exit `0`，各输出 progress 与 terminal success，无 protocol error。
- **不可 skip**: §9.1 明确 "缺依赖、网络失败、skip 或未实际进入 producer 都阻塞 R09 completion"。
- **test injection**: §9.2 明确 missing/duplicate/event-after 只能通过 test injection，不伪称真实运行。
- **测试命令**: §7 的 pytest 命令直接可执行。§8.1 的 complete-tree validation 命令覆盖所有 owner/consumer/adversarial tests。
- **coverage 命令**: §8.2 的 coverage 命令使用 `workspace/tmp/.coverage-r09` 数据文件，逐文件 `--include` 和 `--fail-under=80`。
- **唯一风险**: Docling 环境不可用时 upload smoke 会 skip/fail，但这在 R08 已有 precedent（"1 existing Docling environment skip"）。plan 要求真实成功，不接受 skip。

## 5. Umbrella Alignment Check

### 5.1 umbrella §7.3 gate 流程

plan §12 完整列出了与 umbrella §7.3 一致的 gate 流程。artifact naming stem 固定为 `wu-semantic-ownership-01-r09-fins-direct-stream-validator-*`，与 umbrella 要求一致。

### 5.2 umbrella §7.4 closed affected-module manifest

R09 production allowlist: `direct_events.py`, `direct_stream.py` (new), `ingestion_runtime.py`, `fins_direct.py`, `fins.py` CLI。与 umbrella §7.4 R09 entry 完全一致。

### 5.3 umbrella §7.5 per-slice verification

R09-S1 scan: "terminal protocol decision only in validator scan"。R09-S2 scan: "Service/CLI no duplicate/missing construction scan"。与 umbrella §7.5 R09 row 一致。

### 5.4 umbrella §16 R09 design

- §16.1 owner: "dayu.fins typed stream validator exclusively owns 'exactly one and last RESULT'"。plan §3.1 一致。
- §16.2 state machine: umbrella 给出简化版，plan §4 给出完整版。plan 版本增加了 RESULT_YIELDED 状态和 aclose 规则，是对 umbrella 的细化而非偏离。
- §16.3 slices: S1 validator owner + S2 mechanical consumer。plan §6 一致。
- §16.4 smoke/README/stop: plan §9/§5.3/§13 一致。

### 5.5 Topic 6.5 裁决

plan 完全实现 Topic 6.5 的用户裁决："Make exactly-one direct-stream terminal a single Fins-owned validator contract; Service and CLI mechanically consume it"。

## 6. Code Evidence Verification

### 6.1 三处分散 decision 的实际形态验证

| plan §2.2 claim | code evidence | match |
|---|---|---|
| runtime `_run_direct_stream` 缓存首个 RESULT | line 2763: `result_event: FinsEvent | None = None` + line 2767: `if result_event is not None: raise DUPLICATE` | ✓ |
| runtime missing check | line 2774: `if result_event is None: raise MISSING` | ✓ |
| Service `_ensure_result_event` 重复缓存 | line 481: `result_event: FinsEvent | None = None` + line 486: `if result_event is not None: raise DUPLICATE` | ✓ |
| CLI 遇首个 result 即返回 | line 686: `if event.result is not None: return event.result` | ✓ |
| CLI missing fallback | line 691: `raise FinsDirectStreamProtocolError(MISSING_RESULT, ...)` | ✓ |
| CLI 无 duplicate checker | code 确认：`_consume_fins_direct_events` 没有 duplicate 检查 | ✓ |

### 6.2 source locks 验证

plan §1.3 的 source locks SHA-256 与当前代码一致（已通过 plan entry validation 确认）。

### 6.3 current test nodes 验证

plan §7 标为 "current" 的 test node 在当前代码中全部存在（通过 Explore agent 确认）。标为 "新增/替换" 的 node 正确标注为 implementation 必须创建。

## 7. Residual Risks

| risk | owner | destination |
|---|---|---|
| Fins thread-backed 长事务不可物理取消 | GitHub Issue 175 | 不属于 R09 accepted contract |
| Docling 环境不可用导致 upload smoke skip | R09 completion gate | 不接受 skip，必须真实成功 |
| SEC 网络不可用导致 download smoke fail | R09 completion gate | 不接受 skip，必须真实成功 |
| close 失败时 error 优先级 | R09 Fins owner | F-CANDIDATE-02，plan 补充后 implementation 自行处理 |
| R10-R12 / Issues / Topic 8/9 | 各既有 owner | 不属于 R09 scope |

## 8. Conclusion

plan 是 code-generation-ready 的。目标/非目标明确，唯一语义 owner 定义清晰，状态机完整且有直接代码证据支撑，typed error identity 唯一，async iterator/aclose/cancel/exception lifecycle 合理，S1/S2 cumulative cutover 设计正确，allowed files 与 umbrella 一致，接口与依赖方向无反向依赖，无过度设计，tests/coverage/pyright/Ruff/scans/README/real smoke 命令真实可执行，R06/R08 no-regression 有保障，安全防线不弱化，deferred scope 明确。

三个 accepted-candidate findings（F-CANDIDATE-01 LOW, F-CANDIDATE-02 LOW, F-CANDIDATE-04 MEDIUM）不 blocking implementation。F-CANDIDATE-04 要求删除 producer protocol-error speculative dead path，是 MEDIUM 因为它涉及删除 plan 中已写入的代码/测试设计。AgentCodex 可在 plan fix 阶段一并处理。

---

AgentMiMo verdict: **PASS**
