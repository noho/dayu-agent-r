# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Code Re-Review — AgentDS

## 1. Gate identity

- 审查者：AgentDS（第二路独立 complete code re-review，新 gate 但不是新 WU）。
- 日期：`2026-07-19`。
- WU：既有 `WU-SEMANTIC-OWNERSHIP-01` aggregate regression fix Slice 2 continuation。
- 上一 gate：Controller adjudication `PASS / ZERO_ACCEPTED_CODE_FINDING / READY_FOR_DUAL_COMPLETE_CODE_REREVIEW`。
- 审查对象：同一 unchanged 20-path target。自 initial review 起 zero code change。
- Immutable base：`ba44bf877138235d53606d082341a7f7280af488`。
- Content manifest：`cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925`（由 Controller validation §2 记录）。
- Deleted base blob SHA-256：`f724e51ca6ff5dd687dfe4709751b8f0e9bd440b4e02f0bfd343f598a1e50c53`（fresh 验证未漂移）。
- New owner SHA-256：`945ffedf2ab375afc24668db4c7a327fb2008c066a954d51046e3273b79ee481`（fresh 验证未漂移）。
- 写回 artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-rereview-ds.md`。
- 本 artifact 不修改任何其他文件，不 stage/commit/push/PR/subagent。
- 不依赖 MiMo 本轮 re-review；不依赖本 reviewer 初始 DS review（`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-ds.md`）的初审结论。

## 2. Scope

- Mode：current changes（uncommitted workspace changes relative to immutable base）。
- Branch：`phaseflow/host-issues-control`。
- Base：`ba44bf877138235d53606d082341a7f7280af488`（HEAD == base，所有变更为 working tree uncommitted）。
- Review target 精确 20 个路径：

Production（12，含 1 delete + 1 add）：

```text
M dayu/cli/commands/fins.py
M dayu/fins/direct_events.py
D dayu/fins/direct_stream.py
A dayu/fins/ingestion/awaiting_resolution.py
M dayu/fins/ingestion_runtime.py
M dayu/fins/tools/_ingestion_tool_helpers.py
M dayu/fins/tools/download_provider.py
M dayu/fins/tools/preprocess_provider.py
M dayu/fins/tools/upload_provider.py
M dayu/service/fins_direct.py
M dayu/service/fins_wait_adapter.py
M dayu/service/host_assembly.py
```

Tests（6）：

```text
M tests/cli/test_fins_commands.py
M tests/fins/test_fins_direct_stream.py
M tests/fins/test_fins_ingestion_tools.py
M tests/service/test_fins_direct.py
M tests/service/test_fins_wait_adapter.py
M tests/service/test_host_assembly.py
```

Validation utility + README（2）：

```text
M utils/smoke_host_public_awaiting_entrypoint.py
M dayu/fins/README.md
```

Protected zero-diff paths：`tests/service/test_import_boundary.py`、`dayu/fins/__init__.py`、`dayu/fins/ingestion/__init__.py`。

- Excluded scope：Controller/control/review artifacts 与 `docs/host/issues-implementation-control.md` 的 control-doc row 更新。
- Parallel review coverage：无（单路独立完整 re-review，不使用 subagent）。

## 3. Design / control doc reading record

按要求的顺序连续完整读到 EOF，记录准确 `wc -l` 与覆盖范围：

| 文档 | wc -l | FULL_READ_TO_EOF |
| --- | ---: | --- |
| `AGENTS.md` | 128 | ✓ 行 1–128 |
| `docs/host/issues-implementation-control.md` | 2326 | ✓ 行 1–2326（分段连续读取，无缺口） |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | ✓ 行 1–302 |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | ✓ 行 1–731 |
| `docs/host/design.md` | 3704 | ✓ 行 1–3704（分段连续读取，无缺口） |
| `docs/engine/design.md` | 553 | ✓ 行 1–553 |
| `docs/tool/design.md` | 134 | ✓ 行 1–134 |
| `docs/fins/design.md` | 123 | ✓ 行 1–123 |
| `docs/ui/design.md` | 116 | ✓ 行 1–116 |

随后完整读取到 EOF：

| 文档 | 行数 | FULL_READ_TO_EOF |
| --- | ---: | --- |
| Accepted plan `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`（SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`） | 696 | ✓ |
| Slice 2 authorization `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-controller-authorization.md` | 72 | ✓ |
| AgentCodex implementation `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md`（SHA-256 `3cc7dc4caee4cac8e6620e35f1373d252c0518f1218013027bb32a30810cab5c`） | 461 | ✓ |
| Controller validation `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-controller-validation.md` | 89 | ✓ |
| AgentMiMo initial review `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-mimo.md` | 183 | ✓ |
| AgentDS initial review `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-ds.md` | 326 | ✓ |
| Controller adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-controller-adjudication.md` | 65 | ✓ |
| Slice 1 fifth-stop adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md` | 32 | ✓ |

## 4. Review method

1. 完整读取上述 18 份文档：9 份设计/控制真源、accepted plan、Slice 2 authorization、implementation artifact、Controller validation、两份 initial reviews、Controller adjudication、Slice 1 fifth-stop adjudication——全部读到 EOF 并记录行数。
2. 完整获取 `git diff ba44bf87` 覆盖全部 20 个授权路径的 diff（275 insertions / 341 deletions）。
3. 获取旧 owner base blob：`git show ba44bf87:dayu/fins/direct_stream.py`（261 行），读取全文。
4. 读取新增模块 `dayu/fins/ingestion/awaiting_resolution.py`（65 行）全文。
5. 读取 `dayu/fins/direct_events.py`（736 行）全文，重点逐行对比新增 `ValidatedFinsEventStream` 实现与旧 base blob。
6. 读取 `dayu/fins/tools/_ingestion_tool_helpers.py`（250 行）全文，验证删除后残留正确性。
7. 逐文件走读全部 15 个 consumer 的 import 变更（3 production + 3 tests for `ValidatedFinsEventStream`；5 production + 3 tests + 1 utility for awaiting resolution）。
8. 执行 stale reference scan 四次：`rg 'dayu\.fins\.direct_stream'`（exit 1, zero match）、`rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*(?:Awaiting\|AWAITING\|parse_awaiting)'`（exit 1, zero match）、`rg 'from dayu\.fins\.direct_stream import'`（exit 1, zero match）、`rg 'hasattr\|getattr'` targeted files（zero match）。
9. 验证 `dayu/fins/direct_stream.py` 物理删除：`ls` 确认文件不存在。
10. 验证 protected paths 零 diff：`git diff ba44bf87 -- dayu/fins/__init__.py dayu/fins/ingestion/__init__.py tests/service/test_import_boundary.py` 零输出。
11. 沿真实代码路径走读 `ValidatedFinsEventStream` 状态机：逐一追踪 OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED 全部转换路径，与旧实现逐行比对。
12. 走读 `parse_awaiting_resolution_mode` 输入校验链：缺失字段 → ValueError、非字符串 → ValueError、非闭集值 → ValueError，与旧实现逐行比对。
13. 独立运行 focused tests：`321 passed, 3 warnings in 5.15s`（fresh 本 reviewer 独立执行，非沿用既有结果）。
14. 独立运行 pyright：`0 errors, 0 warnings, 0 informations`（fresh 本 reviewer 独立执行）。
15. 执行完整 adversarial failure pass：correctness、state/lifecycle、exception identity、semantic owner、import boundary/cycle、compatibility/fallback、security、LLM-facing text、test coverage、README accuracy、scope containment。

## 5. Byte-identical verification

### 5.1 `ValidatedFinsEventStream` 迁移（旧 `direct_stream.py` → 新 `direct_events.py`）

旧 base blob（261 行）与 `direct_events.py` 新增段落（行 367–582）逐行比对结果：

| 组件 | 旧位置（base blob） | 新位置（direct_events.py） | 比对结果 |
| --- | --- | --- | --- |
| `_MISSING_RESULT_MESSAGE` | 行 23 | 行 54 | 逐字相同 |
| `_DUPLICATE_RESULT_MESSAGE` | 行 24–26 | 行 55–57 | 逐字相同 |
| `_EVENT_AFTER_RESULT_MESSAGE` | 行 27–29 | 行 58–60 | 逐字相同 |
| `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE` | 行 30–32 | 行 61–63 | 逐字相同 |
| `_ValidatedStreamState` enum | 行 35–41 | 行 160–167 | 四个成员值逐字相同 |
| `ValidatedFinsEventStream.__init__` | 行 53–74 | 行 378–405 | 逐行相同（仅类型标注 `AsyncGenerator`/`FinsOperationKind` 在模块内直接可见） |
| `ValidatedFinsEventStream.__aiter__` | 行 76–90 | 行 407–420 | 逐行相同 |
| `ValidatedFinsEventStream.__anext__` | 行 92–149 | 行 422–476 | 逐行相同。状态机完全一致：CLOSED→StopAsyncIteration、RESULT_YIELDED→CLOSED→StopAsyncIteration、try source.__anext__()、StopAsyncIteration→_finish_clean_exhaustion()、BaseException→_raise_primary_after_close()、OPEN/RESULT→缓存+continue、RESULT_BUFFERED→typed error |
| `ValidatedFinsEventStream.aclose` | 行 151–167 | 行 478–497 | 逐行相同 |
| `ValidatedFinsEventStream.terminal_result` | 行 169–183 | 行 499–515 | 逐行相同 |
| `ValidatedFinsEventStream._finish_clean_exhaustion` | 行 185–201 | 行 517–541 | 逐行相同 |
| `ValidatedFinsEventStream._raise_primary_after_close` | 行 203–219 | 行 543–563 | 逐行相同。primary error identity 保持、close failure 作为 `__cause__`、`asyncio.CancelledError` 身份完整 |
| `ValidatedFinsEventStream._close_source_once` | 行 221–233 | 行 565–581 | 逐行相同 |

唯一差异是 import 来源：旧模块通过 `from dayu.fins.direct_events import FinsDirectStreamProtocolError, ...` 导入类型，新位置这些类型已在同一模块内定义——这是物理合并的正常结果，语义无变化。新增 imports（`AsyncGenerator`、`AsyncIterator`、`NoReturn`）均为该类所需，无多余。

### 5.2 Awaiting resolution 迁移（旧 `_ingestion_tool_helpers.py` → 新 `awaiting_resolution.py`）

旧 base blob（`git show ba44bf87:dayu/fins/tools/_ingestion_tool_helpers.py` 行 22–61）与新 `awaiting_resolution.py`（行 1–64）逐行比对结果：

| 组件 | 比对结果 |
| --- | --- |
| `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` | 逐字相同：`Final[str]`，值 `"awaiting_resolution_mode"` |
| `AwaitingResolutionMode` enum | 逐字相同：`POLL="poll"`、`CALLBACK="callback"`、`MANUAL="manual"` |
| `parse_awaiting_resolution_mode` | 逐行相同：三步严格校验——(1) 字段缺失→ValueError，(2) 非字符串→ValueError，(3) `StrEnum` 构造+外层 catch 并附加友好消息 |
| `__all__` | 精确三符号导出 |

### 5.3 删除残留验证

`dayu/fins/tools/_ingestion_tool_helpers.py` 当前版本（250 行）：
- 已删除：`from enum import StrEnum`、`from typing import Final`、`AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode`、`parse_awaiting_resolution_mode`。
- 保留函数全部完整：`_awaiting_outcome_from_observation_handle`、`_failed_outcome`、`_required_text`、`_optional_text`、`_optional_nullable_text`、`_optional_text_tuple`、`_optional_bool`、`_optional_int`、`_required_int`。
- Docstring 更新准确：从"恢复模式解析、outcome 构造和 JSON 参数读取"改为"outcome 构造和 JSON 参数读取"。
- `StrEnum` 与 `Final` 在文件中无其他消费者（pyright `0 errors` 佐证）。

## 6. Adversarial verification

### 6.1 Correctness / state machine

沿真实代码路径逐一追踪 `__anext__` 全部分支：

| 路径 | 初始状态 | 触发条件 | 状态推进 / 返回值 | 比对结果 |
| --- | --- | --- | --- | --- |
| 正常 progress + RESULT | OPEN | event_type=PROGRESS → return；event_type=RESULT → buffer + continue；raw source StopAsyncIteration | OPEN→RESULT_BUFFERED→RESULT_YIELDED→CLOSED；先返回 progress，clean exhaustion 后返回 buffered RESULT | 与旧实现完全一致 |
| 仅有 RESULT（无 progress） | OPEN | event_type=RESULT → buffer + continue；raw source StopAsyncIteration | OPEN→RESULT_BUFFERED→RESULT_YIELDED；返回 buffered RESULT | 与旧实现完全一致 |
| 无 RESULT（missing） | OPEN | raw source StopAsyncIteration 时 state==OPEN | OPEN→CLOSED；`FinsDirectStreamProtocolError(MISSING_RESULT)` | 与旧实现完全一致 |
| 重复 RESULT（duplicate） | RESULT_BUFFERED | event_type=RESULT | `FinsDirectStreamProtocolError(DUPLICATE_RESULT)`；`_raise_primary_after_close` 关闭 source → CLOSED | 与旧实现完全一致 |
| RESULT 后 progress | RESULT_BUFFERED | event_type=PROGRESS | `FinsDirectStreamProtocolError(EVENT_AFTER_RESULT)`；`_raise_primary_after_close` 关闭 source → CLOSED | 与旧实现完全一致 |
| Upstream exception | OPEN | `self._source.__anext__()` raise BaseException | `_raise_primary_after_close(primary_error)`：CLOSED、清缓存、关闭 source、重抛同一 primary_error | 与旧实现完全一致 |
| Upstream cancellation | OPEN | `self._source.__anext__()` raise `asyncio.CancelledError` | 同上，`CancelledError` 身份完整保留 | 与旧实现完全一致 |
| Duplicate + close failure | RESULT_BUFFERED | duplicate RESULT 且 `aclose()` raise OSError | primary=`FinsDirectStreamProtocolError(DUPLICATE_RESULT)`、`__cause__=OSError` | 与旧实现完全一致 |
| 显式 aclose（中途） | OPEN | `await stream.aclose()` | OPEN→CLOSED、清缓存、调用 `_close_source_once` | 与旧实现完全一致 |
| 显式 aclose（已 CLOSED） | CLOSED | `await stream.aclose()` | 幂等直接返回，不重试 `aclose()` | 与旧实现完全一致 |

所有 10 条路径均与旧实现行为一致，无漂移。

### 6.2 State / lifecycle

- `_ValidatedStreamState` 转换图：`OPEN ↔ RESULT_BUFFERED ↔ RESULT_YIELDED ↔ CLOSED`。终态 CLOSED 为 absorbing——进入后 `__anext__` 立即 `StopAsyncIteration`，`aclose` 幂等返回。与旧实现完全一致。
- `_source_close_attempted` 标志保证至多一次 `aclose()` 调用。`_close_source_once` 内使用 `if self._source_close_attempted: return` + `self._source_close_attempted = True` 模式，无竞态窗口（async 单线程执行）。
- `_clean_exhaustion` 只在 `_finish_clean_exhaustion`（唯一 clean path）设为 `True`；`_raise_primary_after_close` 与 `aclose`（非 clean）不清除 `_clean_exhaustion`（因为状态已推进到 CLOSED，`terminal_result` 的 `_clean_exhaustion` 检查配合 `_terminal_result_value is None` 双重守卫）。

### 6.3 Exception identity

- `_raise_primary_after_close` 始终重抛同一个 `primary_error` 对象。close failure 作为 `__cause__` 链入，不替换 primary identity。`asyncio.CancelledError` 身份完整保留——不包装、不转换。
- `terminal_result` property 在非 clean exhaustion 时 `RuntimeError`；消息 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE` 与测试模块常量相同（非类型耦合，而是 owner contract 的对齐断言）。

### 6.4 Semantic owner

迁移完成后每个语义事实均回到唯一 public owner：

| 语义事实 | 旧 owner | 新 owner | 迁移方式 |
| --- | --- | --- | --- |
| `ValidatedFinsEventStream` 状态机与 close 生命周期 | `dayu.fins.direct_stream`（独立 public module） | `dayu.fins.direct_events`（与事件契约同一 module） | 物理迁入 + 旧模块删除 |
| Direct stream 四消息常量 | `dayu.fins.direct_stream` | `dayu.fins.direct_events` | 物理迁入 |
| `_ValidatedStreamState` | `dayu.fins.direct_stream` | `dayu.fins.direct_events` | 物理迁入 |
| `AWAITING_RESOLUTION_MODE_CONFIG_FIELD` | `dayu.fins.tools._ingestion_tool_helpers`（tools 私有） | `dayu.fins.ingestion.awaiting_resolution`（Fins public） | 物理迁入 |
| `AwaitingResolutionMode` | 同上 | 同上 | 物理迁入 |
| `parse_awaiting_resolution_mode` | 同上 | 同上 | 物理迁入 |

无 duplicate enum/protocol/validator、无 Service 字符串重算、无第二套 parser。

### 6.5 Import boundary / cycle

- `awaiting_resolution.py` 依赖链：`dayu.contracts.json_value.JsonValue`（稳定 contracts 层）+ 标准库（`collections.abc.Mapping`、`enum.StrEnum`、`typing.Final`）。无 Service/Host/Engine/Storage 依赖。
- `direct_events.py` 新增 imports（`AsyncGenerator`、`AsyncIterator`、`NoReturn`）均为标准库，无新增域依赖。
- Service layer (`host_assembly.py`、`fins_wait_adapter.py`、`fins_direct.py`) 全部从 Fins public modules 导入，不 import `_ingestion_tool_helpers`（tools 私有）。符合 `UI → Service → Host → Engine` 分层。
- 无循环依赖：`awaiting_resolution.py` 不 import `direct_events`、不 import `tools`、不 import `service`。`direct_events.py` 新增代码不 import `awaiting_resolution` 或 `tools`。
- `dayu/fins/__init__.py` 与 `dayu/fins/ingestion/__init__.py` 零 diff——无 package-root re-export。

### 6.6 Compatibility / fallback

四次 staleness scan 全部 zero match：
- `rg 'dayu\.fins\.direct_stream' dayu tests utils`：exit 1，zero match
- `rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*(?:Awaiting\|AWAITING\|parse_awaiting)'`：exit 1，zero match
- `rg 'from dayu\.fins\.direct_stream import' dayu tests utils`：exit 1，zero match
- `ls dayu/fins/direct_stream.py`：No such file or directory

无 `hasattr`/`getattr` fallback、无 `importlib` lazy import、无 re-export wrapper、无 `try/except ImportError` 兼容路径、无 duplicate enum/protocol。

### 6.7 Security

- 无新增 secret、path、network、process、file 或 subprocess 操作。
- Config/Host internal SQLite/EventLog 保持 `ACCEPTED_TRUSTED_INTERNAL`。
- Tool Trace、audit、public、LLM-facing、logs、outputs、diff/review 保持 `ZERO_REQUIRED`。
- 无引入 secret storage/redaction infrastructure 或统一 tool authorization framework。
- 现有 containment、symlink、DNS/peer、resource-budget、atomic-write、process-fencing 均未削弱。

### 6.8 LLM-facing text

- `awaiting_resolution.py` 的 ValueError 消息为业务可读英文（`"config.awaiting_resolution_mode is required"`、`"must be a string"`、`"must be one of: poll, callback, manual"`），不暴露内部模块名或实现细节。
- `direct_events.py` 的 `FinsDirectStreamProtocolError` 消息（`_MISSING_RESULT_MESSAGE` 等）为程序化 typed error，面向 Service/CLI consumer 而非 LLM。文本未变。
- 无 LLM-facing prompt、schema 或 tool description 变更。

### 6.9 Tests / coverage

本 reviewer 独立运行：

- Focused tests：`321 passed, 3 warnings in 5.15s`（全部 8 个授权测试文件 + import boundary）。
- pyright：`0 errors, 0 warnings, 0 informations`。

Controller 已验证（本 reviewer 未重复，但确认为同一 target）：
- Full Fins suite：`950 passed, 1 skipped`。
- Canonical non-coverage：`5182 passed, 0 failed`。
- Single-node coverage：`5180 passed, 0 failed`。
- Slice 2 owners coverage：`direct_events.py 94.14%`、`awaiting_resolution.py 100%`。
- 五条 real Fins/Host smokes：全部 PASS。

测试覆盖的关键契约行为（全部 test oracle 未变）：
- Direct stream：progress→buffered result、missing RESULT typed error、duplicate RESULT typed error、event-after-RESULT typed error、upstream exception identity、cancellation identity、duplicate+close-failure primary/cause 链、event-after+close-failure primary/cause 链、RESULT+upstream error 丢弃 result、显式 aclose 传播 close failure、重复 aclose 不重试 source、close-failure 后重复 aclose 不重试、terminal_result 在各状态的 RuntimeError。
- Awaiting resolution：有效值 → 正确 enum member、缺失字段 → ValueError、非字符串 → ValueError、未知值 → ValueError。

### 6.10 README

- `dayu/fins/README.md`：文件树删除 `direct_stream.py`、更新 `direct_events.py` 描述（含 `ValidatedFinsEventStream`）、更新 `ingestion` 目录描述（"awaiting resolution"）。inline text 更新指向新 public owner。符合其自身 `Agent更新约束【必须遵守】`。
- `dayu/service/README.md`、`tests/README.md`、根 `README.md`、`dayu/README.md`：均正确判定 `NO_UPDATE`——本 reviewer 独立阅读各 README 的职责范围约束，确认本次变更不触及。

### 6.11 Scope containment

- 20 个授权路径全部在 allowlist 内。
- 3 个 protected 路径零 diff。
- 无新增 mutable path、无 import cycle 导致扩域。
- Staged tree：empty。
- `git diff --check`：exit 0。
- 未偷带 deferred issues（142、151、175、177、178）实施。
- Topic 8/9 零 diff。
- `AR-F06` 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07` 保持 `PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE`。

## 7. Findings

### 未发现实质性问题

经过完整 20-path 逐文件走读、新旧实现逐行比对（状态机全部 10 条路径 + awaiting parser 全部 3 条校验分支）、15-consumer import 追踪、四次 staleness 扫描、import cycle/boundary 分析、security/LLM/README surface 验证，以及独立 focused tests + pyright 通过确认，本 re-review 未发现任何 correctness、state/lifecycle、exception identity、semantic owner、import boundary、compatibility/fallback、security、LLM-facing、test coverage、README 或 scope containment 层面的实质缺陷。

本次变更是一个机械的、行为不变的语义 owner 物理迁移：

1. `ValidatedFinsEventStream` 从独立 public module `direct_stream.py` 迁入其事件契约所在的 `direct_events.py`，旧模块物理删除。消除"同一 public contract 拆成两个 public module"的 `AR-F02` 原始问题。
2. Awaiting resolution 语义从 tools 私有 helper `_ingestion_tool_helpers.py` 迁入新建 public module `dayu.fins.ingestion.awaiting_resolution`。消除"Service composition 依赖 tools 适配层私有 owner"的 `AR-F02` 原始问题。
3. 全部 15 个 consumer（direct stream: 3 production + 3 tests；awaiting resolution: 5 production + 3 tests + 1 utility）精确更新 import target。无 re-export、wrapper、compatibility shim 或行为变更。

Controller accepted code finding 为 0，review 证据修正已关闭；本 re-review 确认 unchanged target 上无新 finding。

## 8. Open Questions

无。

## 9. Residual Risk

- `tests/fins/test_fins_direct_stream.py` 文件名含 `direct_stream`，但这是 accepted plan 合法 consumer，其 import 已正确迁至 `dayu.fins.direct_events`。文件名表达被测试的 direct stream 协议语义，不造成业务风险。Controller adjudication 已裁决 `NO_ACTION / NOT_A_RESIDUAL`。
- 外部代码若有 `from dayu.fins.direct_stream import ValidatedFinsEventStream` 会在升级后 break。这是 `AGENTS.md` 明确授权的语义 owner 迁移 breaking change：`"默认按全新设计处理，不为旧实现、旧接口、旧测试保留兼容逻辑"`。
- `AR-F05`：Slice 3 九路径 coverage `<80%`，由序列边界 (`OPEN_BY_SEQUENCE`) 控制。
- `AR-F06`：scheduler close / terminal promotion coordination 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`。
- `AR-F07`：real remote Windows 保持 `PENDING_RELEASE_BLOCKER`。
- Gemini test account quota：`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`。
- Deferred issues（142、151、175、177、178）与 Web/WeChat/render trackers 仍由原 owner 追踪。

## 10. Verdict

```text
READY_FOR_CONTROLLER_ADJUDICATION
```

Findings 数量：**0**（未发现实质性问题）。

审查覆盖：20 个授权路径全部逐文件走读完成；新旧实现全部 10 条状态机路径 + 3 条 parser 校验分支逐行比对；15 个 consumer 全部 import 追踪验证；adversarial 11 面全部独立重新检查；四次 staleness 扫描全部 zero match；独立 focused tests + pyright 通过。

Target unchanged：deleted base blob SHA `f724e51c...` 与 new owner SHA `945ffedf...` 均 fresh 验证未漂移。Content manifest `cb0d5f96...` 未漂移。Immutable base `ba44bf87` 未漂移。
