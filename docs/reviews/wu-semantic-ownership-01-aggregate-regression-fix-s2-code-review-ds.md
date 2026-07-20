# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 2 Code Review — AgentDS

## Review Identity

- 审查者：AgentDS（第二路独立 complete code review）。
- 日期：`2026-07-19`。
- 审查对象：Slice 2 完整 20-path target（12 production + 6 tests + 1 utility + 1 README）。
- Immutable base：`ba44bf877138235d53606d082341a7f7280af488`。
- Content manifest：`cb0d5f96da993dd7cbe65fe513d2432a25b5c4a091515e5f1a29f2ed8d303925`（由 Controller validation 记录）。
- 对应 Controller validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-controller-validation.md`。
- 对应 Implementation artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md`（SHA-256 `3cc7dc4c...ab5c`）。
- 写回 artifact：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-code-review-ds.md`。

## Scope

- Mode：current changes（uncommitted workspace changes relative to immutable base）。
- Branch：`phaseflow/host-issues-control`。
- Base：`ba44bf877138235d53606d082341a7f7280af488`（HEAD == base，所有变更为 working tree uncommitted）。
- Review target 精确 20 个路径：

Production（12）：

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
- Parallel review coverage：无（单路独立完整审查，不使用 subagent）。

## Design/Control Doc Reading Record

按要求的顺序完整读到 EOF：

| 文档 | 行数 | FULL_READ_TO_EOF |
| --- | ---: | --- |
| `AGENTS.md` | 128 | ✓ |
| `docs/host/issues-implementation-control.md` | 2325 | ✓（分段完整读取） |
| `docs/phaseflow-umbrella-optimization-control.md` | 302 | ✓ |
| `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` | 731 | ✓ |
| `docs/host/design.md` | 3704 | ✓（分段完整读取） |
| `docs/engine/design.md` | 553 | ✓ |
| `docs/tool/design.md` | 134 | ✓ |
| `docs/fins/design.md` | 123 | ✓ |
| `docs/ui/design.md` | 116 | ✓ |

随后按任务要求完整读到 EOF：

| 文档 | 行数 | FULL_READ_TO_EOF |
| --- | ---: | --- |
| Accepted plan `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`（SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`） | 696 | ✓ |
| Slice 2 authorization `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-controller-authorization.md` | 72 | ✓ |
| AgentCodex implementation artifact `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-implementation-codex.md`（SHA-256 `3cc7dc4c...ab5c`） | 461 | ✓ |
| Controller validation `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-controller-validation.md` | 89 | ✓ |
| Slice 1 fifth-stop Controller adjudication `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-fifth-stop-controller-adjudication.md` | 32 | ✓ |

## Review Method

1. 完整读取上述 14 个文档：9 个设计/控制真源文档、accepted plan、Slice 2 authorization、implementation artifact、Controller validation 与 Slice 1 fifth-stop adjudication，全部读到 EOF 并记录行数。
2. 获取 `git diff ba44bf87..` 完整 diff（54KB，覆盖全部 20 个授权路径）。
3. 逐文件走读所有 added/modified hunk，追踪每个 import 变更的 source → target 路径。
4. 读取新增模块 `dayu/fins/ingestion/awaiting_resolution.py`（64 行）全文。
5. 读取 `dayu/fins/direct_events.py`（735 行）全文，验证新增 `ValidatedFinsEventStream` 实现。
6. 读取 `dayu/fins/tools/_ingestion_tool_helpers.py`（250 行）全文，验证删除后残留正确性。
7. 对全部 15 个 consumer 执行 `grep -n` 验证 import target 精确性。
8. 执行 stale reference scan：`rg 'dayu\.fins\.direct_stream'`（exit 1，零命中）、`rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*AwaitingResolutionMode'`（exit 1，零命中）。
9. 执行 `direct_stream` 关键词 scan，区分模块引用与方法名 `_run_direct_stream` / `_open_direct_stream` / 测试文件名 `test_fins_direct_stream.py`——全部为合法使用，非对已删除模块的引用。
10. 验证 `dayu/fins/direct_stream.py` 物理删除（`ls` 确认文件不存在）。
11. 验证 protected paths 零 diff。
12. 沿真实代码路径走读 `ValidatedFinsEventStream` 状态机（OPEN → RESULT_BUFFERED → RESULT_YIELDED → CLOSED），检查 exactly-one terminal、duplicate/after-result typed error、close-at-most-once、异常/取消 identity 传播。
13. 走读 `parse_awaiting_resolution_mode` 输入校验链（缺失 → 非字符串 → 非闭集值），确认严格错误语义保留。
14. 执行 adversarial failure pass：检查 import cycle、语义 owner drift、compatibility/fallback shim、Service 分层 import boundary、public API 暴露、README 准确性、LLM-facing 文本影响、安全性面。
15. 独立验证测试覆盖：基于 Controller 已独立运行的 `321 passed` focused tests + `950 passed` Fins suite + `5182 passed` canonical + `5180 passed` coverage run 的证据链，确认 focused tests 覆盖 direct stream identity、exactly-one/last RESULT、missing/duplicate/after-result typed errors、clean exhaustion terminal identity、close-at-most-once、异常/取消 identity、awaiting closed mode/parser errors。

## Findings

### 逐文件审查结果

**1. `dayu/fins/direct_events.py`（+217 行）**

变更性质：将 `ValidatedFinsEventStream` 及其私有 state/constants 从已删除的 `direct_stream.py` 物理迁入。

详细审查：
- 状态机 `_ValidatedStreamState`：OPEN → RESULT_BUFFERED（首个 RESULT 缓存）→ RESULT_YIELDED（clean exhaustion 后返回缓存结果）→ CLOSED。终态收敛路径完整无遗漏。
- `__anext__` 主循环：先检查 CLOSED / RESULT_YIELDED，再读 raw source。OPEN 态遇到 RESULT 缓存并 continue；RESULT_BUFFERED 态遇到任何事件产生 typed protocol error。raw source 正常耗尽时调用 `_finish_clean_exhaustion`；raw source 异常/取消时通过 `_raise_primary_after_close` 保持 primary error identity。
- `_finish_clean_exhaustion`：OPEN 态进入 = MISSING_RESULT；RESULT_BUFFERED 态进入 = 成功返回缓存 result。状态推进正确。
- `_raise_primary_after_close`：关闭 raw source 后重抛 primary_error；close error 作为 `__cause__` 链入，primary identity 不受污染。取消路径 `asyncio.CancelledError` 身份完整保留。
- `_close_source_once`：`_source_close_attempted` 标志保证至多一次 `aclose()`，幂等安全。
- `aclose`：CLOSED 态幂等直接返回；非 clean exhaustion 时清理缓存状态。
- `terminal_result` property：只有 `_clean_exhaustion=True` 且 `_terminal_result_value is not None` 时返回；否则 RuntimeError。正确守卫了"stream 尚未 clean exhaustion 时不应读取结果"的 invariant。
- `__all__` 新增 `"ValidatedFinsEventStream"`，正确反映公开 API。
- 新增 imports（`AsyncGenerator`, `AsyncIterator`, `NoReturn`）：全部为该类所需，无多余 import。
- 模块 docstring 更新：准确描述合并后的职责。

**结论：实现正确，无缺陷。**

**2. `dayu/fins/direct_stream.py`（已删除）**

变更性质：物理删除旧 owner 模块。

详细审查：
- 文件系统确认不存在（`ls` 返回 No such file or directory）。
- 全仓 `rg 'dayu\.fins\.direct_stream'` 零命中（exit 1）。
- 无 re-export、wrapper、lazy/dynamic/try import 或兼容路径残留。
- 旧模块的 `__all__` 不再存在，其唯一公开符号 `ValidatedFinsEventStream` 已迁移至 `direct_events.py`。

**结论：删除干净，无残留。**

**3. `dayu/fins/ingestion/awaiting_resolution.py`（新增，64 行）**

变更性质：新建 public owner 模块，唯一拥有 awaiting resolution 配置字段、closed typed enum 与严格 parser。

详细审查：
- `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`：`Final[str]`，值 `"awaiting_resolution_mode"`，与原私有定义完全一致。
- `AwaitingResolutionMode`：`StrEnum`，闭集 `POLL="poll"`, `CALLBACK="callback"`, `MANUAL="manual"`，与原私有定义完全一致。
- `parse_awaiting_resolution_mode`：严格三步校验——(1) 字段缺失 → ValueError，(2) 非字符串 → ValueError，(3) 非闭集值 → ValueError（通过 `StrEnum` 构造自动校验，外层 catch 并附加友好消息）。错误消息均为业务可读英文，不暴露内部模块名或实现细节。
- `__all__` 精确导出三个公开符号。
- 模块 docstring 准确描述 owner 职责。
- Import boundary：仅依赖 `dayu.contracts.json_value.JsonValue` 与标准库（`collections.abc.Mapping`、`enum.StrEnum`、`typing.Final`）。无 Service/Host/Engine 依赖，无循环依赖风险。
- `from __future__ import annotations`：与项目风格一致。

**结论：实现正确，无缺陷。**

**4. `dayu/fins/tools/_ingestion_tool_helpers.py`（-46 行）**

变更性质：删除三项 awaiting resolution 语义定义，更新 docstring。

详细审查：
- 删除项：`AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode`、`parse_awaiting_resolution_mode`。
- 删除的 imports：`from enum import StrEnum`、`from typing import Final`（仅被上述三项使用，无其他引用——由 pyright 零错误佐证）。
- 保留项：`_awaiting_outcome_from_observation_handle`、`_failed_outcome`、`_required_text`、`_optional_text`、`_optional_nullable_text`、`_optional_text_tuple`、`_optional_bool`、`_optional_int`、`_required_int`。全部完整保留，无意外删除。
- 保留 imports：`Mapping`、`datetime/timezone`、`JsonValue`、`ToolAwaitKind/ToolAwaitSnapshot/ToolAwaitSpec`、`ToolAwaitingOutcome/ToolFailedOutcome`、`ToolResultFailure/ToolResultMeta`、`FinsObservationHandle/observation_handle_id_to_resume_token`。全部仍被保留函数使用。
- Docstring 更新：从"恢复模式解析、outcome 构造和 JSON 参数读取"改为"outcome 构造和 JSON 参数读取"，准确反映删除后的剩余职责。
- 全仓扫描旧私有 helper import：`rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*AwaitingResolutionMode'` 零命中（exit 1）。

**结论：删除干净，残留代码正确，无缺陷。**

**5-7. 三个 provider consumer（`download_provider.py`、`preprocess_provider.py`、`upload_provider.py`）**

变更性质：各文件一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.tools._ingestion_tool_helpers import parse_awaiting_resolution_mode`
- 新 import：`from dayu.fins.ingestion.awaiting_resolution import parse_awaiting_resolution_mode`
- 使用点不变：三个 provider 均在 `discover_tools` 中调用 `parse_awaiting_resolution_mode(provider_config.config)` 并将返回值赋给本地变量。import 路径变更不影响调用语义。

**结论：正确，无缺陷。**

**8. `dayu/service/host_assembly.py`（+5/-5 行）**

变更性质：import block 重组。

详细审查：
- 旧 import：`from dayu.fins.tools._ingestion_tool_helpers import AWAITING_RESOLUTION_MODE_CONFIG_FIELD, AwaitingResolutionMode, parse_awaiting_resolution_mode`
- 新 import：`from dayu.fins.ingestion.awaiting_resolution import AWAITING_RESOLUTION_MODE_CONFIG_FIELD, AwaitingResolutionMode, parse_awaiting_resolution_mode`
- 三个符号的使用点不变：
  - `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`：用于 `provider_config.config` 的 key 存在性检查（行 1215）。
  - `AwaitingResolutionMode`：用于模式匹配（`is AwaitingResolutionMode.POLL`、`.CALLBACK`、`.MANUAL`，行 407、792、904、1360、2131）。
  - `parse_awaiting_resolution_mode`：用于解析 provider config（行 1223）。
- Service 层 import 来自 Fins ingestion 公共模块，符合 `UI -> Service -> Host -> Engine` 分层——Service 可以依赖 Fins 领域层。
- Import block 顺序：先 `dayu.contracts` 和 `dayu.engine`，再 `dayu.fins.ingestion.awaiting_resolution`，再 `dayu.fins.ingestion.observation_handle`，再 `dayu.service.fins_wait_adapter`，最后 `dayu.fins` 其余部分。符合项目 import 组织惯例。

**结论：正确，无缺陷。**

**9. `dayu/service/fins_wait_adapter.py`**

变更性质：一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode`
- 新 import：`from dayu.fins.ingestion.awaiting_resolution import AwaitingResolutionMode`
- 使用点：类型标注 `tool_modes: Sequence[tuple[str, AwaitingResolutionMode]]` 与 `mode is AwaitingResolutionMode.POLL` 等模式匹配。import 路径变更不影响类型语义。

**结论：正确，无缺陷。**

**10. `dayu/cli/commands/fins.py`**

变更性质：一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.direct_stream import ValidatedFinsEventStream`
- 新 import：`from dayu.fins.direct_events import ValidatedFinsEventStream`
- 使用点：`_open_direct_stream` 函数返回类型标注与实例化。import 路径变更不影响类型或运行时行为。

**结论：正确，无缺陷。**

**11. `dayu/fins/ingestion_runtime.py`**

变更性质：一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.direct_stream import ValidatedFinsEventStream`
- 新 import：`from dayu.fins.direct_events import ValidatedFinsEventStream`
- 使用点：`run_download_stream`、`run_preprocess_stream`、`run_upload_stream` 三个方法的返回类型标注与 `ValidatedFinsEventStream(...)` 构造。import 路径变更不影响类型或运行时行为。

**结论：正确，无缺陷。**

**12. `dayu/service/fins_direct.py`**

变更性质：一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.direct_stream import ValidatedFinsEventStream`
- 新 import：`from dayu.fins.direct_events import ValidatedFinsEventStream`
- 使用点：多个方法的返回类型标注。Service 现在直接从 Fins public owner 消费，不再经过已删除的中间模块。符合 `docs/fins/design.md` §7 的 direct stream terminal contract 要求。

**结论：正确，无缺陷。**

**13-18. 六个 test consumer**

变更性质：各文件一到数行 import owner 迁移。

详细审查（逐文件）：

- `tests/cli/test_fins_commands.py`：`ValidatedFinsEventStream` 从 `direct_stream` → `direct_events`。使用点仅类型引用，不变。
- `tests/fins/test_fins_direct_stream.py`：`ValidatedFinsEventStream` 从 `direct_stream` → `direct_events`。测试文件仍使用模块级常量 `_TERMINAL_RESULT_NOT_AVAILABLE_MESSAGE`（与 production 常量文本相同），用于验证 `terminal_result` property 的 RuntimeError 消息。测试逻辑不变。
- `tests/fins/test_fins_ingestion_tools.py`：`AwaitingResolutionMode` 和 `parse_awaiting_resolution_mode` 从 `_ingestion_tool_helpers` → `awaiting_resolution`。新增 import block 正确插入在 `dayu.fins.ingestion` 导入区域。
- `tests/service/test_fins_direct.py`：`ValidatedFinsEventStream` 从 `direct_stream` → `direct_events`。
- `tests/service/test_fins_wait_adapter.py`：`AwaitingResolutionMode` 从 `_ingestion_tool_helpers` → `awaiting_resolution`。
- `tests/service/test_host_assembly.py`：`AwaitingResolutionMode` 从 `_ingestion_tool_helpers` → `awaiting_resolution`；新增 import 行正确插入，旧 import 行正确删除。

所有测试的断言逻辑、fixture 构造和 owner-contract oracle 未变。import 迁移是纯机械替换。

**结论：全部正确，无缺陷。**

**19. `utils/smoke_host_public_awaiting_entrypoint.py`**

变更性质：精确一行 import owner 迁移。

详细审查：
- 旧 import：`from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode`
- 新 import：`from dayu.fins.ingestion.awaiting_resolution import AwaitingResolutionMode`
- 九个业务/类型 uses 与其它全部行 byte-identical。仅 import 来源变更。

**结论：正确，无缺陷。**

**20. `dayu/fins/README.md`**

变更性质：两处更新——awaiting resolution owner 说明与文件树。

详细审查：
- 行 178-179：`Fins 私有共享 helper` → `` `dayu.fins.ingestion.awaiting_resolution` ``，准确反映新 public owner。
- 行 453：`direct_events.py` 描述从"direct 事件、类型化协议错误与结果契约所有者"更新为"direct 事件、结果、类型化协议错误与 ValidatedFinsEventStream 公共 owner"，准确反映合并后的职责。
- 行 455：`ingestion` 目录描述从"direct stream、legacy job helper 与 lightweight observation contract"更新为"awaiting resolution、legacy job helper 与 lightweight observation contract"，准确反映 direct stream owner 已迁出、awaiting resolution owner 已迁入。
- 删除行：旧 `direct_stream.py` 文件树条目。
- README 自身更新约束（`Agent更新约束【必须遵守】`）已满足：仅同步现行文件树与 owner 说明，不承诺旧路径兼容。
- 其他 README 判定：`dayu/service/README.md`、`tests/README.md`、根 `README.md`、`dayu/README.md` 均为 `NO_UPDATE`——经独立核实，本次变更确实不触及这些 README 的职责范围。

**结论：正确，无缺陷。**

### Adversarial Verification Summary

| 检查面 | 方法 | 结果 |
| --- | --- | --- |
| Import cycle | 追踪新增模块的全部 import 链 | 零 cycle；`awaiting_resolution.py` 仅依赖 `dayu.contracts` |
| Compatibility shim | `rg` 扫描 `re-export`、`wrapper`、`lazy`、`dynamic`、`try`、`importlib` | 零命中 |
| Stale old reference | `rg 'dayu\.fins\.direct_stream'` dayu/ tests/ utils/ | exit 1，零命中 |
| Stale old private import | `rg 'from dayu\.fins\.tools\._ingestion_tool_helpers import.*(?:Awaiting|AWAITING|parse_awaiting)'` | exit 1，零命中 |
| Service boundary | 验证 `host_assembly.py` / `fins_wait_adapter.py` import 来源 | 正确从 Fins public owner 导入，符合分层 |
| Protected paths | `git diff` 验证 `__init__.py` 文件和 `test_import_boundary.py` | 零 diff |
| Deleted file | `ls dayu/fins/direct_stream.py` | 文件不存在 |
| LLM-facing text | `direct_events.py` 错误消息文本未变；`awaiting_resolution.py` 错误消息为业务可读英文 | 无需变更 |
| Security surface | 无新增 secret/path/network/process 操作 | 零新增风险 |
| Live-browser node | 历史不存在 node 已由 prior Controller 裁决用 current owner；current owner `test_playwright_live_browser_cleanup_smoke_is_manual_and_best_effort` 真实 PASS | 无需当作新 finding |
| README accuracy | 对比文件树实际状态 | 准确 |

### 未发现实质性问题

经过完整 20-path 逐文件走读、15-consumer import 追踪、stale reference 扫描、状态机 adversarial 验证、import boundary 检查与 README 准确性核实，本审查未发现任何 correctness、stability、maintainability、semantic ownership、over-coupling、compatibility/fallback、public API、LLM-facing、security 或 test coverage 层面的实质缺陷。

本次变更是一个机械的、行为不变的语义 owner 物理迁移：

1. `ValidatedFinsEventStream` 从独立模块 `direct_stream.py` 迁入其事件契约所在的 `direct_events.py`，消除"同一 public contract 拆成两个 owner"的原始问题。
2. Awaiting resolution 语义从 tools 私有 helper 迁入独立 public module `dayu.fins.ingestion.awaiting_resolution`，消除"Service composition 依赖工具适配层私有 owner"的原始问题。
3. 所有 consumer（12 production + 6 tests + 1 utility）精确更新 import target，无 re-export、wrapper、compatibility shim 或行为变更。

## Open Questions

无。

## Residual Risk

- **`tests/fins/test_fins_direct_stream.py` 文件名：NO_ACTION。** 该测试文件是 accepted plan 中的合法 consumer，其 import 已正确迁至 `dayu.fins.direct_events`；文件名含 `direct_stream` 仅反映其测试对象（direct stream 终态协议验证），不造成业务或维护风险。Accepted plan 未授权重命名测试文件，且本 umbrella 禁止为无 owner 的 cleanup 偏好创建新 slice、WU 或 issue。裁决为 NO_ACTION，不作为 residual risk 遗留。
- 外部代码若有 `from dayu.fins.direct_stream import ValidatedFinsEventStream` 会在升级后 break。这是语义 owner 迁移的可接受 breaking change；`AGENTS.md` 明确"默认按全新设计处理，不为旧实现、旧接口、旧测试保留兼容逻辑"。README 已更新新 owner 位置。
- Coverage：Slice 2 owners 分别为 `direct_events.py 94.14%` 与 `awaiting_resolution.py 100%`，满足 `>=80%` 要求。
- Deferred issues（142、151、175、177、178）与 Web/WeChat/render trackers 均未受本 Slice 影响，仍由原 owner 追踪。

## Verdict

```text
PASS / NO_MATERIAL_DEFECTS_FOUND / READY_FOR_CONTROLLER_ADJUDICATION
```

Findings 数量：**0**（未发现实质性问题）。

审查覆盖：20 个授权路径全部逐文件走读完成；15 个 consumer 全部 import 追踪验证；adversarial 14 面全部检查通过；stale reference 扫描全部零命中；状态机全部路径验证正确。
