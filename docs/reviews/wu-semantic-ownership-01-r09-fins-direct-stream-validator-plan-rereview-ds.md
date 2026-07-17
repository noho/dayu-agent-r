# WU-SEMANTIC-OWNERSHIP-01 R09 Fixed Plan Complete Re-Review — AgentDS

## 0. Gate identity 与结论

- umbrella: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation
- sub-WU: `R09 — Fins direct-stream terminal validator`
- gate: Controller-ordered adversarial fixed-plan complete re-review（非 diff-only）
- review target: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`
- target SHA-256: `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`
- target line count: 773
- re-review 结论：**PASS** — 无新 finding；R09-PR-F01..F06 全部确认关闭；plan 与 current code evidence 一致且 code-generation-ready

## 1. Target identity lock

| metric | value | verified |
|---|---|---|
| target SHA-256 | `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` | `shasum -a 256` ✓ |
| target lines | 773 | `wc -l` ✓ |
| original plan SHA-256 | `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210` | plan §1.4 ✓ |
| Controller adjudication SHA-256 | `f615eccf7b2b8db387b5dc1125b95ef5a479c5420cd3c42dff469779a5070643` | verified ✓ |
| AgentCodex fix artifact SHA-256 | `b735f4f2990c8ddbb6896aaa8d84d63cfb79be318a31f00579a002cc9dc55c2c` | plan-fix-codex artifact ✓ |
| AgentMiMo review SHA-256 | `d220c1dd7637d560c835f059841c7effaafe1027b3deb7fe5b1e0919a80b57ac` | verified ✓ |
| AgentDS original review SHA-256 | `0434e4766729d2d85c1ade31c767a88ffd47781e7b49b4b734d86ae8a0a53ad9` | verified ✓ |
| Controller validation artifact | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-controller-validation.md` | verified ✓ |
| git diff --check | PASS (empty) | verified ✓ |
| staged tree | empty | verified ✓ |

## 2. Current evidence source locks 验证

所有 §1.3 current evidence locks 经 `shasum -a 256` 重新验证均匹配：

| evidence | plan SHA-256 | actual SHA-256 | match |
|---|---|---|---|
| `dayu/fins/direct_events.py` | `b34cb82d...` | `b34cb82d...` | ✓ |
| `dayu/fins/ingestion_runtime.py` | `176d8ab9...` | `176d8ab9...` | ✓ |
| `dayu/service/fins_direct.py` | `875d5396...` | `875d5396...` | ✓ |
| `dayu/cli/commands/fins.py` | `666d9dc2...` | `666d9dc2...` | ✓ |
| `tests/fins/test_fins_ingestion_runtime.py` | `6480be57...` | `6480be57...` | ✓ |
| `tests/service/test_fins_direct.py` | `9c533d7e...` | `9c533d7e...` | ✓ |
| `tests/cli/test_fins_commands.py` | `525414da...` | `525414da...` | ✓ |
| `docs/fins/design.md` | `97033cf1...` | `97033cf1...` | ✓ |
| umbrella remediation plan | `30c27562...` | `30c27562...` | ✓ |

`docs/host/issues-implementation-control.md` current SHA (`0de2c21c...`) 与 plan lock (`3d9403bc...`) 不同——这是 Controller 在 plan fix 后推进 gate transition 的预期行为，plan §0 已明确记录。不构成 source drift。

所有 README SHA 均与 plan §5.3 fresh scan 完全匹配：
- `README.md`: `2f5cebfd...` ✓
- `dayu/README.md`: `16bbdc87...` ✓
- `dayu/fins/README.md`: `50c07ae6...` ✓
- `dayu/service/README.md`: `8d7d7680...` ✓
- `tests/README.md`: `6c0614af...` ✓

## 3. R09-PR-F01..F06 逐个 closure 验证

### R09-PR-F01 — exact signature and call-site cutover

**plan fix**: §3.4 exact old/new signature table + call-site contract

**code verification**（逐行比对 current tree）:

| plan claim | current code | evidence |
|---|---|---|
| runtime `download` 是 `async def -> AsyncIterator[FinsEvent]`，方法体含 `async for ... yield` | `ingestion_runtime.py:2146-2181` | ✓ 一致 |
| runtime `preprocess` 同上 pattern | `ingestion_runtime.py:2183-2217` | ✓ 一致 |
| runtime `upload` 同上 pattern | `ingestion_runtime.py:2219-2253` | ✓ 一致 |
| raw bridge `_run_direct_stream` 是 `async def`，含 terminal checker（`result_event`, duplicate/missing） | `ingestion_runtime.py:2696-2781` | ✓ 一致 |
| Service protocol `download/preprocess/upload` 是 plain `def -> AsyncIterator[FinsEvent]` | `fins_direct.py:54-101` | ✓ 一致 |
| Service public methods 是 plain `def -> AsyncIterator[FinsEvent]` | `fins_direct.py:167-472` | ✓ 一致 |
| Service `_preprocess` 接受 `operation_kind` 并通过 `_ensure_result_event` 包装 | `fins_direct.py:429-472` | ✓ 一致 |
| CLI opener `_open_direct_stream` 和 6 路 stream helpers 是 plain `def -> AsyncIterator[FinsEvent]` | `fins.py:363-601` | ✓ 一致 |
| CLI `_wait_for_terminal_handling_sigint` 是 `async def` 且有 `operation_kind` param | `fins.py:604-659` | ✓ 一致 |
| CLI `_consume_fins_direct_events` 有 `operation_kind` param 和尾部 fallback `MISSING_RESULT` | `fins.py:662-694` | ✓ 一致 |
| `_DirectStreamQueueItem = FinsEvent \| _DirectStreamProducerDone` | `ingestion_runtime.py:1344` | ✓ 一致 |
| `FinsDirectStreamProtocolErrorKind` 仅含 `MISSING_RESULT` 和 `DUPLICATE_RESULT`（无 `EVENT_AFTER_RESULT`） | `direct_events.py:81-85` | ✓ 一致 |

**new signature table 可实施性**: 所有 old shape 均与 current tree 精确匹配；所有 new shape 在类型系统内一致（`ValidatedFinsEventStream` 是 `AsyncIterator[FinsEvent]` 子类型，Service/CLI 保持 plain `def` 无新增 `await`）。

**verdict**: **CLOSED** — plan §3.4 给出的 exact old/new signature table 与 current code 100% 一致，无虚构、无遗漏。

### R09-PR-F02 — error/close precedence and idempotence

**plan fix**: §4 完整状态机 + §7.1 18 个 exact owner tests

**code verification**:
- 当前 raw bridge `finally: cancellation_state.request_cancel()` (L2780-2781) 只做本地状态标记，不抛异常，不干扰 primary error 传播 ✓
- 当前 producer `finally: _put_direct_queue(context, _DirectStreamProducerDone())` (L2813) 确保 done sentinel 始终入队 ✓
- 当前无任何代码路径让 cleanup close failure 覆盖 semantic error

**contract 完整性检查**:
- primary semantic error 优先级: upstream exception/cancellation identity 或 duplicate/event-after typed error → 始终是最终传播的 type/object/reason/operation_kind/message ✓
- cleanup failure chaining: `raise primary from cleanup_error`，`primary.__cause__ is cleanup_error` ✓
- 无 primary 的显式 close: 同一 close error object 原样传播 ✓
- close-at-most-once: private guard 保证，重复 `aclose()` 不重试；覆盖 close success 与 close failure 两种情况 ✓
- 不引入 `CLOSED_CLEAN/CLOSED_ABORTED` 新状态；terminal availability 由单独 clean-exhaustion flag 表达 ✓

**test coverage**: §7.1 的 18 个 owner tests 精确覆盖：
- close success/failure（tests 6-10: `_stays_primary_when_cleanup_close_fails` ×4）
- duplicate/event-after primary + cleanup chaining
- upstream error/cancel identity + cleanup chaining
- explicit consumer close（tests 12-14）
- repeated close after success/failure（tests 13-14）
- result-then-error（test 11）

**verdict**: **CLOSED** — error precedence contract 完整且可测试；close idempotence guard 不引入新状态；所有 test assertions 指定到 object identity / `is` / `__cause__` 级别。

### R09-PR-F03 — remove speculative producer protocol-error path

**plan fix**: 从 root cause、状态机、file changes、tests、scans、residual 全面删除 producer protocol-error channel

**code verification**:
- `_run_direct_stream_producer` (L2783-2813): 只 catch generic `Exception` → bounded business failure `RESULT`，**不构造** `FinsDirectStreamProtocolError` ✓
- `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` (L1344): **不含** protocol error variant ✓
- producer callees (`_produce_direct_download/preprocess/upload`): 通过 `_emit_direct_result` / `_emit_context_progress` 投递 event，**无** protocol error origin ✓
- 所有 `FinsDirectStreamProtocolError` 构造点只在 consumer-side：`_run_direct_stream` (L2765-2768, L2774-2777) 和 `_ensure_result_event` (L499-510) ✓

**plan 中 producer channel 相关内容的删除确认**:
- §2.3 明确 `_DirectStreamQueueItem` 不变 ✓
- §4 invariant 6: generic producer exception mapping 保持，raw bridge native propagation 保持 ✓
- §5.4: `_DirectStreamQueueItem` 与 producer 都不修改 ✓
- §5.6 不得改清单包含 producer/queue ✓
- §8.4 scans: runtime 和 Service 中 `FinsDirectStreamProtocolError` 预期零命中 ✓
- §7.1: 无 producer protocol-error test ✓

**verdict**: **CLOSED** — speculative producer protocol-error channel 已从 plan 所有层面删除；既有 generic business-failure mapping 原样保留。

### R09-PR-F04 — terminal-result availability contract

**plan fix**: §3.2/§4 固定 `terminal_result` 为普通 `RuntimeError` + module-owned constant；§7.1 四个 availability tests

**contract 验证**:
- 提前读取 = programmer-contract violation，不是 stream protocol error ✓
- 使用普通 `RuntimeError`（不新增 public/private error class）✓
- message 使用 module-owned `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE` ✓
- 四类 availability: OPEN / RESULT_BUFFERED / abortive close / clean exhaustion ✓
- clean exhaustion: `terminal_result is buffered_result`（同一 object）✓
- 不引入 `CLOSED_CLEAN/CLOSED_ABORTED` 子状态（与 F02 一致）✓

**test 验证**: §7.1 tests 15-18 覆盖全部四种情况，断言精确到 `is` 和 module constant ✓

**verdict**: **CLOSED** — availability contract 完整；四个 exact tests 覆盖全部状态；无 overdesign。

### R09-PR-F05 — retain existing CLI presentation

**plan fix**: §3.3 CLI keeps `dayu-cli {command}: {exc.message}` + `EXIT_FAILURE=1`；§5.3 README fresh scan + no-update/update decision

**code verification**:
- 当前 CLI `run_fins_direct_command` L203-205: `render_cli_error(f"dayu-cli {args.command_name}: {exc.message}")` + `EXIT_FAILURE` ✓
- 当前 CLI 不展示 raw `reason.value` ✓
- 当前根 README 无 Fins direct protocol error-code format 章节 ✓

**plan 验证**:
- §3.3: CLI 不 import/枚举 typed reason、不读取 `reason.value`、不解析 message 判断 reason ✓
- §5.4: CLI catch owner error 时严格沿用既有 prefix/message ✓
- §5.3: 根/dayu README no-update（有 fresh SHA + rationale），Fins/Service/tests README update required ✓
- §7.3: CLI presentation tests 只断言 prefix/message + exit 1，不展示 raw reason ✓

**verdict**: **CLOSED** — CLI presentation 保持既有 contract；README trigger 决策有 fresh SHA 证据支持。

### R09-PR-F06 — operation-kind provenance propagation

**plan fix**: §3.4/§7.2/§7.3/§7.4 增加 Fins `reason/operation_kind/message/object` 同源传播与 identity tests

**code verification — 关键反例**:
- 当前 `process_filing` (L245-273) 传 `FinsOperationKind.PROCESS_FILING` 给 `_preprocess` → `_ensure_result_event`
- 当前 `process_material` (L275-303) 传 `FinsOperationKind.PROCESS_MATERIAL` 给 `_preprocess` → `_ensure_result_event`
- 当前 runtime `preprocess` (L2207) 始终用 `FinsOperationKind.PREPROCESS`
- 当前 Service wrapper `_ensure_result_event` 用调用方传入的 `operation_kind` 构造 error——**这是当前 bug 的一部分**：`process_filing` 触发的 missing/duplicate error 会带 `PROCESS_FILING` 而非 `PREPROCESS`

plan 中 fix 后：runtime validator 始终用 `PREPROCESS`，Service/CLI 通过 identity pass-through 传播同一 error object。provenance tests 验证 error 的 `operation_kind is PREPROCESS` 而非 `PROCESS_FILING`/`PROCESS_MATERIAL`。

**test 验证**:
- §7.2: `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance` + `test_process_material_keeps_runtime_preprocess_protocol_error_provenance` ✓
- §7.3: CLI 对应 `_through_cli` provenance tests ✓
- §7.4: fixture 纪律 — fake Service 不得重写 protocol algorithm ✓

**verdict**: **CLOSED** — provenance propagation contract 完整；process alias vs runtime PREPROCESS 反例有精确 test coverage。

### 闭集总览

| Finding | Plan section | Controller validation | Re-review verdict |
|---|---|---|---|
| R09-PR-F01 | §3.4 signature table | closed | **CLOSED** — 与 current tree 100% 一致 |
| R09-PR-F02 | §4 state machine + §7.1 tests | closed | **CLOSED** — contract 完整可测试 |
| R09-PR-F03 | §2.3/§4/§5.4/§8.4 | closed | **CLOSED** — producer channel 已彻底删除 |
| R09-PR-F04 | §3.2/§4/§7.1 | closed | **CLOSED** — availability contract 完整 |
| R09-PR-F05 | §3.3/§5.3/§5.4/§7.3 | closed | **CLOSED** — CLI presentation + README trigger |
| R09-PR-F06 | §3.4/§7.2/§7.3/§7.4 | closed | **CLOSED** — provenance propagation + 反例 tests |

## 4. 六大维度深度挑战

### 4.1 exact signatures vs current code

逐项比对 plan §3.4 的每一行与 current tree：

**runtime 层**:
- `download`: current `async def` L2146, body `async for ... yield` L2168-2181 → plan plain `def -> ValidatedFinsEventStream` ✓
- `preprocess`: current `async def` L2183, body `async for ... yield` L2205-2217 → plan plain `def -> ValidatedFinsEventStream` ✓
- `upload`: current `async def` L2219, body `async for ... yield` L2241-2253 → plan plain `def -> ValidatedFinsEventStream` ✓
- `_run_direct_stream`: current `async def` L2696, terminal checker L2752-2779 → plan `async def -> AsyncGenerator[FinsEvent, None]` raw bridge ✓

**Service 层**:
- Protocol `download/preprocess/upload`: current plain `def -> AsyncIterator[FinsEvent]` (L54, L70, L86) → plan plain `def -> ValidatedFinsEventStream` ✓
- 6 个 public methods: current plain `def -> AsyncIterator[FinsEvent]` → plan plain `def -> ValidatedFinsEventStream` ✓
- `_preprocess`: current plain `def` L429, 经 `_ensure_result_event` L466 → plan plain `def -> ValidatedFinsEventStream`，直接 return ✓

**CLI 层**:
- `_open_direct_stream` + 6 helpers: current plain `def -> AsyncIterator[FinsEvent]` → plan plain `def -> ValidatedFinsEventStream` ✓
- `_wait_for_terminal_handling_sigint`: current `async def` L604, 有 `operation_kind` param L610 → plan 删除 `operation_kind` ✓
- `_consume_fins_direct_events`: current `async def` L662, 有 `operation_kind` param L665 + fallback L690-694 → plan 删除两者，读 `terminal_result` ✓

**结论**: 所有签名 call out 均与 current code 精确一致；new signature 在类型系统内兼容（`ValidatedFinsEventStream` 是 `AsyncIterator[FinsEvent]` 子类型）；Service/CLI 调用链无新增 `await` 的点已逐行确认。

### 4.2 state machine realizability — 无隐藏状态矛盾

**完整遍历 §4 状态机**:

| 触发 | 起始状态 | 终止状态 | 验证 |
|---|---|---|---|
| PROGRESS | OPEN | OPEN (yield event) | ✓ |
| first RESULT | OPEN | RESULT_BUFFERED | ✓ |
| clean EOF | OPEN | CLOSED (MISSING_RESULT error) | ✓ |
| upstream error/cancel | OPEN | CLOSED (error propagated) | ✓ |
| second RESULT | RESULT_BUFFERED | CLOSED (DUPLICATE_RESULT error + close source) | ✓ |
| any PROGRESS | RESULT_BUFFERED | CLOSED (EVENT_AFTER_RESULT error + close source) | ✓ |
| upstream error/cancel | RESULT_BUFFERED | CLOSED (discard buffer, propagate error) | ✓ |
| clean EOF | RESULT_BUFFERED | RESULT_YIELDED (yield buffered RESULT) | ✓ |
| next `__anext__` | RESULT_YIELDED | CLOSED (StopAsyncIteration) | ✓ |
| consumer `aclose()` | OPEN | CLOSED (close source, discard nothing) | ✓ |
| consumer `aclose()` | RESULT_BUFFERED | CLOSED (close source, discard buffer) | ✓ |
| consumer `aclose()` | RESULT_YIELDED | CLOSED (source already exhausted) | ✓ |

**关键不变量验证**:

1. **result → error 不发布 success**: RESULT_BUFFERED + upstream error → discard buffer, propagate error. 测试 `test_validated_stream_result_then_error_propagates_same_error_without_result`. ✓

2. **primary semantic error 优先级**: upstream exception/cancellation identity 或 typed duplicate/event-after → primary. cleanup failure → `__cause__`. Tests 6-10. ✓

3. **cleanup close failure 不覆盖 primary**: `raise primary from cleanup_error`. Tests 6-10 的 exact assertion: `captured.value is primary` 且 `captured.value.__cause__ is close_error`. ✓

4. **close-at-most-once**: private guard, 首次成功或失败后重复 `aclose()` 不重试. Tests 13-14. ✓

5. **producer generic exception → bounded business RESULT 不变**: `_DirectStreamQueueItem` 不变, producer 不变. ✓

6. **raw bridge native async error/cancel 自然传播**: `_run_direct_stream` 改为 raw `AsyncGenerator`, 异常自然穿透. ✓

7. **terminal_result availability**: 只在 clean exhaustion 可读. Tests 15-18. ✓

8. **CLI SIGINT 不变**: 仍由 operation token + event task cancel 驱动. ✓

**潜在并发/时序问题检查**:
- producer 线程与 async event loop 的 queue 通信不变（`asyncio.to_thread` + `Queue`）✓
- `finally: cancellation_state.request_cancel()` 在 raw bridge 的 `finally` 保留，确保资源清理 ✓
- `aclose()` 的 GeneratorExit 注入 raw generator 时 `finally` 仍执行 ✓
- producer 线程 `finally: _put_direct_queue(context, _DirectStreamProducerDone())` 确保 done sentinel 始终入队 ✓

**结论**: 状态机所有转换路径可实施，无不变量冲突，无并发/时序矛盾。

### 4.3 speculative producer protocol-error channel — 彻底删除确认

**plan 中全部删除点扫描**:

| 位置 | 内容 | status |
|---|---|---|
| §2.2 root cause table | producer channel 不在三处分散 decision 中 | ✓ 已删除 |
| §2.3 反例 | 明确 `_DirectStreamQueueItem` 已完整表达真实 producer 数据流 | ✓ 已删除 |
| §4 invariant 6 | `_DirectStreamQueueItem` 不变，raw bridge native propagation 不变，validator 唯一 owner | ✓ 已删除 |
| §5.4 `ingestion_runtime.py` | producer control flow 不修改 | ✓ 已删除 |
| §5.6 不得改清单 | producer/queue 在不得改清单 | ✓ 已删除 |
| §7.1 test nodes | 无 producer protocol-error test | ✓ 已删除 |
| §8.4 scans | runtime/Service 中 `FinsDirectStreamProtocolError` 零命中 | ✓ 已删除 |

**既有 generic business-failure mapping 保留确认**:
- `_run_direct_stream_producer` L2801-2813: catch `Exception` → `_classify_direct_error` → `_emit_direct_result(status=FAILURE)` ✓
- `_DirectStreamQueueItem = FinsEvent | _DirectStreamProducerDone` L1344: 不变 ✓
- shared observed path（`prepare_observed_*` / `activate_observation`）: 只做既有 failed snapshot 映射 ✓

**结论**: speculative producer protocol-error channel 已从 plan 所有层面删除；既有 generic business-failure mapping 原样保留。

### 4.4 Service/CLI provenance identity tests — 可执行性

**fixture 可执行性验证**:

plan §7.4 规定三层 fixture 纪律：
1. Fins owner tests: raw sequence injection → assert enum code + object identity ✓
2. Service tests: fake runtime 返回同一 `ValidatedFinsEventStream` 或预构造 typed error → assert identity pass-through ✓
3. CLI tests: fake Service 返回同一 production validator stream/error → assert identity + Fins fields（internal consumer）OR prefix/message + exit 1（public presentation）✓

**关键约束**: fake/helper 不得自行检查、缓存、排序或构造 missing/duplicate/event-after error。Service/CLI provenance test 的 error 必须由 Fins owner test fixture 预先取得。✓

**反例 test 设计**（process_filing/material vs runtime PREPROCESS）:
- Service test: `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance` — 注入 error，assert `operation_kind is PREPROCESS`，not `PROCESS_FILING` ✓
- CLI test: `test_process_filing_keeps_runtime_preprocess_protocol_error_provenance_through_cli` — 同样 assertion 经 CLI consumer ✓

这些 tests 不重写 owner 算法——它们只在 production `ValidatedFinsEventStream` 边界注入/传播已由 owner test 验证的 error。✓

**结论**: provenance identity tests 在不重写 owner 算法的情况下可执行；fixture 纪律明确。

### 4.5 CLI presentation / README / coverage / pyright / Ruff / smoke — 完整性

**CLI presentation**:
- `run_fins_direct_command` L203-205 保持 `dayu-cli {command}: {exc.message}` + `EXIT_FAILURE=1` ✓
- CLI 不新增 raw `reason.value` display ✓
- CLI tests 的 presentation assertion 只检查 prefix/message + exit 1 ✓

**README triggers**:
- 根 `README.md`: no-update（无 Fins direct raw error-code format 章节）✓
- `dayu/README.md`: no-update（分层边界不变）✓
- `dayu/fins/README.md`: implementation 必须更新（validator owner + event-after）✓
- `dayu/service/README.md`: implementation 必须更新（删除 Service-owned checker 叙述）✓
- `tests/README.md`: implementation 必须更新（owner/consumer test narrative）✓

**coverage ≥80%**:
- §8.2 逐文件 coverage 命令覆盖 5 个 changed production files ✓
- 每个文件单独 `--fail-under=80` ✓
- `direct_stream.py`（新增）: 18 个 owner tests 覆盖全部状态机路径 ✓
- `ingestion_runtime.py`（6932 行）: 依赖 full Fins test suite (859 tests) + focused tests，DS-N03 已确认不降低目标 ✓

**pyright/Ruff/source scans**:
- §8.3: full pyright `0 errors`，scoped Ruff 覆盖所有 changed files ✓
- §8.4: 四组 production scans（`_ensure_result_event`、`FinsDirectStreamProtocolError`、enum literals、`ValidatedFinsEventStream`）预期命中清晰 ✓
- 第五组兼容/弱类型 scan: 预期零命中 ✓

**真实 smoke**:
- §9.1: download → process → upload_filing 全链路 ✓
- 要求真实 SEC 网络 + Docling/processor，失败阻塞 completion ✓
- §9.2: injected adversarial smoke（missing/duplicate/event-after/result-then-error）分栏记录 ✓

**结论**: CLI presentation/README/coverage/pyright/Ruff/smoke 的 plan 要求完整且可执行。

### 4.6 no overdesign / no fallback / security / no Topic8/9 / deferred Issue scope

**overdesign 检查**:
- 不新增 factory、wrapper、facade、compatibility re-export ✓
- 不新增 parallel error schema 或 second validator ✓
- 不新增 `CLOSED_CLEAN/CLOSED_ABORTED` 状态（已由 Controller 在 DS-N01 明确拒绝）✓
- 不新增 `terminal_result` 的 public error class ✓
- `direct_stream.py` 只承载一个状态机及其私有状态，不建 framework ✓

**fallback 检查**:
- 不保留 Service/CLI fallback、旧 checker、compatibility wrapper ✓
- 不保留旧 schema、旧导入路径 ✓
- 不新增 `hasattr/getattr` close probing ✓
- cumulative cutover 一次从旧分散 decision 切到新唯一 validator ✓

**security 检查**:
- §10.3 保留: event safe-text/leakage guard、operation-scoped cancellation、consumer-close cancellation state、queue backpressure、late publication、storage containment/symlink、R06 transaction、Host/ToolRuntime authorization、process fencing ✓
- CLI 不展示 raw enum、不解析 message、不回显 provider payload ✓

**scope 检查**:
- §10.2 明确不实施: Topic 8/9、R10-R12、Issues 142/151/175/177/178、Web/WeChat/render、process isolation、线程强杀、Host wait/schema redesign、旧 schema/兼容路径 ✓
- §5.1 production allowlist 闭集: 5 个文件 ✓
- §5.2 test allowlist 闭集: 4 个文件 ✓
- §5.6 不得改清单: 明确排除文件/目录 ✓

**结论**: no overdesign/no fallback/security/no Topic8/9/deferred Issue scope 全部确认。

## 5. Assumptions tested

| assumption | verification method | result |
|---|---|---|
| 三处分散 decision 的实际形态与 plan §2.2 描述一致 | 逐行比对 current `_run_direct_stream`、`_ensure_result_event`、`_consume_fins_direct_events` | ✓ 完全一致 |
| current evidence locks 未漂移 | `shasum -a 256` 重新验证全部 §1.3 locks | ✓ 全部匹配（除 control doc 预期变化） |
| Service/CLI 是 plain `def` 且不新增 `await` | 逐函数检查 current signatures | ✓ 全部 plain `def` |
| `_DirectStreamQueueItem` 无 protocol error variant | 读取 L1344 定义 | ✓ 只有 `FinsEvent \| _DirectStreamProducerDone` |
| producer callees 无 `FinsDirectStreamProtocolError` origin | grep 全文件 | ✓ 只在 consumer-side |
| README SHA 与 plan fresh scan 一致 | `shasum -a 256` 全部 5 个 README | ✓ 完全匹配 |
| existing test nodes 与 plan §7 列出的一致 | grep test names | ✓ 全部在当前 tree 存在 |
| plan 的 new signature 在类型系统内兼容 | `ValidatedFinsEventStream` 是 `AsyncIterator[FinsEvent]` 子类型 | ✓ |
| 状态机所有转换路径无矛盾 | 逐路径遍历 §4 状态机 | ✓ 无不变量冲突 |
| close-at-most-once 可实现 | private guard flag，不引入新状态 | ✓ |

## 6. New finding ledger

经完整 adversarial re-review，未发现新的 material finding。

以下为 review 中检验但判定为 non-finding 的候选点：

| candidate | 判定 | 理由 |
|---|---|---|
| `ingestion_runtime.py` 6932 行，80% 覆盖有风险 | non-finding | DS-N03 已记录此风险，plan 未降低目标，依赖 full Fins test suite |
| 真实 smoke 依赖外部 SEC/Docling | non-finding | plan §9.1 已明确此依赖并设为 completion blocker |
| `_preprocess` 的 `operation_kind` 参数保留/删除不明确 | non-finding | plan §3.4 用"如保留"表达可选性；`_preprocess` 是私有方法，不构成 public contract 歧义 |
| `_run_direct_stream` 的 `direct_operation_kind` 参数在新 raw bridge 中仅用于 execution context | non-finding | `_emit_direct_result` (L4544) 用 `context.direct_operation_kind` 构造 event 的 `operation_kind` 字段，producer 仍需要此值；raw bridge 保留此参数是必要的 |
| `_consume_fins_direct_events` 改后所有事件（含 RESULT）进入 `render_fins_direct_event` | non-finding | `render_fins_direct_event` 已处理 RESULT 事件；当前代码中 RESULT 也经过此函数（L677-678），只是随后 early return |

## 7. Residual risks and owner/destination

| risk | owner | destination |
|---|---|---|
| `ingestion_runtime.py` 单文件 80% coverage 可能依赖 full Fins suite | R09 Controller | DS-N03 — implementation entry 先测 fresh baseline |
| 真实 smoke 缺 SEC/Docling 环境阻塞 completion | R09 Controller | §9.1 — completion blocker，不可 skip |
| `issues-implementation-control.md` current transition 漂移 | Controller | plan §1.2 temporal rule — 若语义 owner/dep/contract 实质变化则 stop 回 Controller |
| R09 后仍有 R10-R12 未实施 | umbrella Controller | §10.2 — 明确不实施 |

以上 risk 均不属于 R09 accepted finding，不阻塞 plan gate 推进。

## 8. Final verdict

**PASS** — 固定 plan `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d` (773 行) 经完整 adversarial re-review：

- R09-PR-F01..F06 全部确认关闭，每个 finding 的 closure evidence 均与 current tree direct evidence 一致
- 六大维度深度挑战（signature matching、state machine realizability、producer channel deletion、provenance test executability、CLI/README/coverage/pyright/Ruff/smoke 完整性、no overdesign/no fallback/security/scope）全部通过
- 状态机所有转换路径可实现，无不变量冲突，无并发/时序矛盾
- exact old/new signature table 与 current code 100% 一致
- 所有 current evidence locks、README SHA、原 review SHA 验证通过
- 无新 material finding
- residual risks 均有 owner/destination 且不阻塞 plan gate

plan 是 code-generation-ready，可安全进入 Controller accepted-plan decision。

## 9. Artifact metadata

| field | value |
|---|---|
| artifact path | `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-rereview-ds.md` |
| artifact line count | 420 |
| git diff --check | PASS (empty) |
| staged tree | empty |
| review timestamp | 2026-07-17T14:00:48+08:00 |
| reviewer | AgentDS |
