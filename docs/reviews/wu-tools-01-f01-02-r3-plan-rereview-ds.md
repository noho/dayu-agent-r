# WU-TOOLS-01-F01-02-R3 Plan Re-Review — AgentDS

- **Reviewed target**: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- **Fix artifact**: `docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`
- **Prior reviews**: `wu-tools-01-f01-02-r3-plan-review-mimo.md`, `wu-tools-01-f01-02-r3-plan-review-ds.md`
- **Controller adjudication**: `wu-tools-01-f01-02-r3-plan-review-controller-adjudication.md`
- **Work unit**: WU-TOOLS-01-F01-02-R3
- **Current gate**: plan re-review
- **Reviewer**: AgentDS
- **Timestamp**: 2026-06-10T18:02:45+0800

---

## 1. Re-Review Scope

本次是聚焦 re-review：仅验证 PF-01 到 PF-09 在 plan 中的修复状态，判断 plan 是否达到 code-generation-ready。不重新审查已接受的 plan 方向，不引入新一轮完整 review，不修改 plan 或生产代码。

## 2. Evidence Sources

- Plan artifact: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`（全文已重读）
- Fix artifact: `docs/reviews/wu-tools-01-f01-02-r3-plan-fix-codex.md`
- Code facts verified:
  - `dayu/contracts/tool_outcome.py:93-115` — `ToolCancelledOutcome` 含 `meta: ToolResultMeta | None`
  - `dayu/contracts/tool_result.py` — `ToolResultMeta(tool_name, started_at, finished_at)`
  - `dayu/tools/_legacy_adapter/definition_adapter.py:80-137` — `_AdaptedLegacyCallable` 的 lock / exception projection
  - `dayu/tools/_legacy_adapter/definition_adapter.py:358-389` — `project_legacy_exception` 转换逻辑
  - `dayu/tools/_legacy_adapter/argument_validator.py:27-53` — 当前 typed result 模式
  - `dayu/tools/web/web_tools.py:235-290` — Web `ToolBusinessError` 子类含 `url`/`next_action`/`http_status`/`internal_diagnostics`
  - `tests/fins/test_fins_storage_provider.py:1160-1191` — `_discover_definitions` / `_definitions_by_name` fixture helpers 当前经 legacy adapter
  - `tests/tools/test_legacy_tool_adapter.py` — 805 行 legacy adapter 测试
  - `rg "_legacy_adapter" dayu/` — 10 个生产文件命中
  - `rg "TOOL_CANCELLED_REASON_HOST_CANCELLED" dayu/` — 7 个文件已使用该常量
- Design sources: `docs/engine/design.md:270-421`（工具调用协议与取消），`docs/host/design.md:71`（ToolsDiscovery 边界）、`docs/host/design.md:2020-2129`（ToolRuntime）
- Control doc: `docs/host/issues-implementation-control.md:223`（R3 是 active plan re-review work unit）

## 3. PF Verification

### PF-01 — 错误类型迁移表与目标模块

**Status: 已修复**

Plan §7 决策 5 新增完整迁移表，覆盖 7 种旧类型→新表达→新位置→outcome 投影：

| 旧类型 | 新表达 | 新位置 |
|---|---|---|
| `ToolArgumentError` | `ToolArgumentValidationFailure` | `dayu.runtime.tool_call_projection` |
| 普通 `ToolBusinessError` | `ToolBusinessFailure` | `dayu.runtime.tool_call_projection` |
| `ToolBusinessError(code="tool_cancelled")` | `host_cancelled_outcome(...)` | `dayu.runtime.tool_call_projection` |
| `FileAccessError` | `DocPathFailure` | `dayu.tools.doc_tools` |
| Web `ToolBusinessError` 子类 | `WebToolFailure` | `dayu.tools.web.web_tools` |
| Fins `ToolArgumentError` | typed validation failure | `dayu.runtime.tool_call_projection` + `dayu.fins.tools.read_runtime_helpers` |
| Fins 普通 `ToolBusinessError` | `FinsReadFailure` 或通用 `ToolBusinessFailure` | `dayu.fins.tools.read_runtime` / `dayu.fins.tools.search_engine` |

表明确区分了通用错误、领域本地错误和取消 outcome，给出了文件级位置。Web `internal_diagnostics` 不进入 LLM-facing outcome 已明确。Fins 不跨包导入 `dayu.tools` 错误类型已明确。可直接指导 implementation agent 在 10 个生产文件中逐文件替换。

**证据**：Plan §7 决策 5 迁移表；`dayu/tools/web/web_tools.py:235-290`（Web 子类额外字段）；`dayu/fins/tools/read_runtime.py` 的 `ToolArgumentError` 使用点。

---

### PF-02 — 取消策略收敛为直接 ToolCancelledOutcome

**Status: 已修复**

Plan §7 决策 4 明确选择：

> 本 WU 选择直接返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` 作为 native callable 的主路径；不得把私有 cancellation exception 作为跨 helper、跨 callable 或 ToolRuntime 边界的主路径。

深层同步 helper 的取消信号通过 typed `ToolBusinessCancelled` result 返回，由 callable 映射为 `host_cancelled_outcome(...)`。取消了 `ToolBusinessError(code="tool_cancelled")` 的异常抛掷路径。

Plan §7 callable 模板中展示了具体代码：`token.is_cancelled()` → `return host_cancelled_outcome(...)`，以及 `isinstance(business_result, ToolBusinessCancelled)` → `return host_cancelled_outcome(...)`。

**证据**：Plan §7 决策 4；§7 callable 模板第 215-220 行、第 261-266 行。

---

### PF-03 — per-provider asyncio.Lock 创建/共享与获取时机

**Status: 已修复**

Plan §7 决策 3 明确：

- 每个 `build_*_tool_definitions(...)` 在函数体内创建一把 `asyncio.Lock()`
- 该 builder 返回的所有 `ToolDefinition.callable` 通过闭包共享同一 lock 实例
- Lock 获取时机：完成参数校验、路径/URL/workspace 校验、pre-cancel checkpoint 之后，进入阻塞业务逻辑或 `asyncio.to_thread(...)` 之前
- `async with provider_lock:` 保证释放
- 禁止模块级全局单例，禁止同一 provider 内每个 callable 独立 lock

Slice 1/2/3 Exact changes 各自重复此要求。Plan §7 callable 模板第 237 行展示了 `async with provider_lock:` 位置。

**证据**：Plan §7 决策 3；§8 Slice 1/2/3 Exact changes；`dayu/tools/_legacy_adapter/definition_adapter.py:124`（当前 `async with self.lock` 模式作为对照）。

---

### PF-04 — 代表性 native callable 模板

**Status: 已修复**

Plan §7 新增约 90 行代表性 `build_doc_tool_definitions` / `read_file_callable` 模板，覆盖：

- 闭包捕获 `limits`、`allowed_roots`、`provider_lock`
- `validate_and_project_arguments(...)` 参数校验
- `context.cancellation_token` 读取
- pre-cancel checkpoint
- `project_doc_path(...)` 路径校验
- `async with provider_lock:` 后二次 cancel checkpoint
- `asyncio.to_thread(read_file_business, ...)` 执行同步业务
- `ToolBusinessFailure` → `failed_outcome(...)`、`ToolBusinessCancelled` → `host_cancelled_outcome(...)`、成功 → `completed_outcome(...)`

模板附注说明是实现约束而非逐字复制要求。

**证据**：Plan §7 callable 模板第 188-272 行。

---

### PF-05 — Slice 0 helper API 签名、typed result 字段、invalid_argument 与校验范围

**Status: 已修复**

Plan §8 Slice 0 新增完整 helper API 草案：

- 4 个 typed result 类型：`ValidatedToolArguments`、`ToolArgumentValidationFailure`、`ToolBusinessFailure`、`ToolBusinessCancelled`
- `INVALID_ARGUMENT_ERROR_CODE: Final = "invalid_argument"` 固定常量和 `ToolArgumentValidationResult` 联合
- 4 个 outcome helper 函数签名：`validate_and_project_arguments`、`completed_outcome`、`failed_outcome`、`host_cancelled_outcome`
- 每个 typed result 的字段语义完整说明（`field_name`、`error`、`message`、`hint`、`reason`）
- 校验范围从 legacy adapter 行为和 Doc/Web/Fins read 工具实际 schema 倒推，覆盖 `type` 为 `string`/`integer`/`number`/`boolean`/`array`/`object` 的当前使用形态、`required`、`enum`、`minimum`/`maximum`、`minLength`/`maxLength`、`minItems`/`maxItems`、数组 `items.type` 和 `items.enum`
- 显式排除当前未使用的 JSON Schema 高级特性：`pattern`、`format`、`uniqueItems`、`multipleOf`、`oneOf`/`anyOf`/`allOf`/`not`、`if`/`then`/`else`、`$ref`/`$defs`、深层 required/nested object validation
- `integer` 必须拒绝 `bool`；`number` 必须拒绝非有限浮点

**证据**：Plan §8 Slice 0 API 草案第 300-359 行；参数校验范围第 370-376 行；`dayu/tools/_legacy_adapter/argument_validator.py:27-53`（当前 typed result 模式作为对照）。

---

### PF-06 — legacy adapter 测试行为迁移覆盖

**Status: 已修复**

Plan §8 Slice 4 新增行为迁移清单表，涵盖 7 类 legacy 测试行为：

| legacy 行为 | 迁移目标 | 删除条件 |
|---|---|---|
| 参数 schema validation | Slice 0 `test_tool_call_projection.py` | Slice 0 helper tests 通过后删除 |
| exception-to-outcome mapping | Slice 0 + 各领域 provider failure tests | completed/failed helper + 领域测试通过后删除 |
| `tool_cancelled` → failed outcome | **不迁移 — 本 WU 要删除的错误行为** | cancellation tests 全部改断言 `ToolCancelledOutcome(host_cancelled)` 后删除 |
| path projection / allowed roots | Slice 1 Doc provider tests | Doc 白名单/文件不存在/list-search path 覆盖后删除 |
| per-tool/per-provider serialization | Slice 1/2/3 concurrency tests | 三个 provider 共享 lock 证明后删除 |
| truncate/display/tags/schema | Slice 1/2/3 provider discovery + combined acceptance | native `ToolDefinition` 等价后删除 |
| collector/decorator OLD metadata | **不迁移 — adapter-only 实现细节** | 所有生产 provider 使用 native builder 后删除 |

此外，Slice 1/2/3 各自的 Tests 节均增加了 concurrency 覆盖、AST import 边界断言和 path projection 等价覆盖要求。Slice 4 completion signal 要求逐项关闭行为迁移清单。

**证据**：Plan §8 Slice 4 行为迁移清单第 654-664 行；`tests/tools/test_legacy_tool_adapter.py`（805 行测试）。

---

### PF-07 — Fins fixture 迁移路径

**Status: 已修复**

Plan §8 Slice 3 Exact changes 新增：

> 更新 `tests/fins/test_fins_storage_provider.py` 中的 fixture helper：`_discover_definitions(...)`、`_definitions_by_name(...)` 或同等 helper 不再依赖 `LegacyToolDeclarationCollector` / `adapt_collected_tools`，改为通过 provider `discover_tools(...)` 的 native output 或直接调用 `build_fins_read_tool_definitions(...)` 获取 definitions。

Slice 3 Tests 增加 "Fins fixture helper 不再调用 legacy collector / adapter；测试 source 或 AST 断言无 `_legacy_adapter`" 和 "AST import boundary 断言 Fins / Engine / runtime 边界不反向依赖"。

Slice 3 Completion signal 增加 "`tests/fins/test_fins_storage_provider.py` 的 definitions fixture 已迁移到 native provider / builder，且仍通过 `dayu.fins.storage` 仓储边界准备财报材料"。

**证据**：Plan §8 Slice 3 Exact changes 第 580-581 行；`tests/fins/test_fins_storage_provider.py:1160-1191`（当前 `_discover_definitions` 经 `discover_tools` → legacy adapter）。

---

### PF-08 — Web live smoke 残余追踪

**Status: 已修复**

Plan §8 Slice 2 Completion signal 新增详细残余追踪要求：

> 若没有运行真实网络 / Playwright live smoke，Slice 2 closeout 必须记录未验证场景、未验证原因、owner / destination。至少记录：真实网络搜索 provider fallback、Playwright browser 启动后取消、真实页面 fetch truncate 与 storage state / channel 组合。

> 若存在本地 fixture / offline 模式，优先运行 `utils/smoke_web_ci.py --external-limit 0` 或项目实际支持的等价命令，并在 closeout 中记录结果。

Plan §11 Residual risk closeout expectation 增加 "Web live smoke 若未运行，R3 closeout 必须保留有 owner 的 residual tracking，至少列明未验证网络 / Playwright 场景、未运行原因、下一步 owner；不得以 deterministic pytest 通过替代真实网络 / browser fallback 的覆盖声明"。

**证据**：Plan §8 Slice 2 Completion signal；§11 residual risk closeout expectation。

---

### PF-09 — ToolCancelledOutcome.meta 构造与测试

**Status: 已修复**

Plan §6 Outcome 明确：

> cancelled outcome 必须和 completed / failed outcome 一样携带 `ToolResultMeta(tool_name, started_at, finished_at)`；`meta` 只承载中性执行元信息，不承载 `run_id`、`session_id`、`correlation_id`、`cancellation_token` 或其它 Host governance 字段。

Plan §8 Slice 0 `host_cancelled_outcome(...)` 签名草案中 `tool_name`、`started_at`、`finished_at` 作为必填参数，reason 固定 `TOOL_CANCELLED_REASON_HOST_CANCELLED`。

Slice 0 Tests 要求 "cancelled outcome meta 非空，`tool_name` / `started_at` / `finished_at` 与输入一致"。

Slice 1/2/3 Tests 各自要求 "取消 outcome 的 `meta.tool_name`、`started_at`、`finished_at` 存在且不暴露 governance 字段"。

代码事实确认：`dayu/contracts/tool_outcome.py:115` — `meta: ToolResultMeta | None` 字段已存在；`dayu/contracts/tool_result.py` — `ToolResultMeta(tool_name, started_at, finished_at)` 已定义。

**证据**：Plan §6 Outcome；§8 Slice 0 API 草案 `host_cancelled_outcome` 签名与 Tests；`dayu/contracts/tool_outcome.py:115`。

---

## 4. Code-Generation-Readiness Assessment

逐项检查 plan 是否满足 implementation agent 直接编码要求：

| 维度 | 评估 | 说明 |
|---|---|---|
| Slice 0 helper API | **充分** | 函数签名、typed result 类型、校验范围、outcome 构造均有明确规格 |
| Slice 0 依赖边界 | **充分** | 只依赖 `dayu.contracts` + 标准库，与现有 `dayu/runtime/cancellation.py` 模式一致 |
| Slice 1 Doc migration | **充分** | 五工具、provider lock、路径投影、取消 checkpoint 均有模板和具体要求 |
| Slice 2 Web migration | **充分** | 二工具、Web 错误类型、Playwright 取消映射、live smoke 残余追踪均覆盖 |
| Slice 3 Fins migration | **充分** | 九工具、storage 边界、fixture 迁移、read runtime helper 迁移均有具体要求 |
| Slice 4 adapter deletion | **充分** | 行为迁移清单、rg 验证、import boundary 更新、README 触发规则均覆盖 |
| 错误类型迁移 | **充分** | 7 种旧类型 → 新表达 → 新位置 → outcome 投影完整映射 |
| 取消语义 | **充分** | 单一策略：直接返回 `ToolCancelledOutcome(host_cancelled)`，无异常路径歧义 |
| 并发策略 | **充分** | lock 创建位置、共享方式、获取时机、禁止模式均有明确要求 |
| 测试覆盖 | **充分** | 每个 slice 有独立测试文件、验证命令和 completion signal |
| Stop condition | **充分** | 每个 slice 有明确 stop condition，防止偷改契约或绕过边界 |

**结论**：Plan 当前达到 code-generation-ready。Implementation agent 可直接按 Slice 0→1→2→3→4 顺序编码，无需额外设计决策。

---

## 5. New Findings

本次 re-review 在 PF-01 到 PF-09 范围内未发现未修复项。在完整审查 plan 修复后内容时，也未发现 fix 引入的新 concrete blocker。

以下为两个低严重度观察（非 blocking），供 implementation agent 参考：

### NR-01 — 低 — WebToolFailure 额外字段的最终落点未完全收敛

- **位置**: Plan §7 迁移表 Web 行
- **问题类型**: 契约轻微歧义
- **当前写法**: 迁移表定义 `WebToolFailure(error, message, hint, url, next_action, http_status, internal_diagnostics)` 为 frozen dataclass，outcome 投影列说明 `error`/`message`/`hint` 保持 LLM-readable 语义，`internal_diagnostics` 不进入 LLM-facing outcome
- **观察**: `url`、`next_action`、`http_status` 三个字段在 outcome 投影中的最终落点未显式说明——是进入 `ToolResultFailure` 的某个字段、记录到日志、还是仅保留在领域类型中供 diagnostic 使用？
- **为什么不是 blocking**: `error`/`message`/`hint` 的 LLM-facing 语义已明确保持；额外字段的具体落点是实现细节，不影响取消修复和 adapter 删除目标。Implementation agent 在编码 Web callable 时按现有 Web 业务错误语义处理即可
- **建议**: Slice 2 implementation agent 编码时自行裁决；若选择将 `url`/`next_action`/`http_status` 放入 `message` 或 `hint` 文本中以保持 LLM 可见性，不算偏离 plan
- **严重程度**: 低

### NR-02 — 低 — `host_cancelled_outcome` 的 `message` 参数默认值

- **位置**: Plan §8 Slice 0 helper API 草案 `host_cancelled_outcome` 签名
- **问题类型**: 契约轻微歧义
- **当前写法**: `message: str | None = None`
- **观察**: `ToolCancelledOutcome.__post_init__`（`tool_outcome.py:131`）校验 `message.strip() != ""`。若 helper 接收 `message=None`，必须提供非空默认值才能通过 `ToolCancelledOutcome` 构造期校验
- **为什么不是 blocking**: 这是 Slice 0 helper 的实现细节，默认值如 `"Tool cancelled by host"` 可自然满足要求。Implementation agent 在编码 helper 时会自然遇到并处理
- **建议**: Slice 0 implementation agent 在 `host_cancelled_outcome` 内部将 `None` message 映射为非空默认字符串
- **严重程度**: 低

---

## 6. Open Questions

无 blocking open questions。

---

## 7. Residual Risks

Plan §11 已列出 5 个风险并给出缓解措施。本次 re-review 确认这些缓解措施在 plan 修复后仍然有效。额外追踪：

| # | 风险 | 严重度 | 建议追踪 |
|---|------|--------|---------|
| RR1 | Slice 0 helper 实际实现可能偏离 API 草案 | 低 | Slice 0 completion 时 review agent 对照 plan API 草案验证 |
| RR2 | Web live smoke 未运行时的残余追踪可能被遗漏 | 中 | Slice 2 / Slice 4 closeout 必须显式报告 PF-08 追踪状态 |
| RR3 | `test_legacy_tool_adapter.py` 行为迁移清单的逐项关闭可能不完整 | 中 | Slice 4 closeout 必须逐项确认，不能以 "adapter 测试已删除" 替代等价覆盖证据 |

---

## 8. Final Verdict

**Overall verdict: pass**

所有 9 个 accepted PF 均已修复。Plan 当前达到 code-generation-ready：implementation agent 可按 Slice 0→1→2→3→4 顺序直接编码，每个 slice 有独立 API 规格、测试要求、completion signal 和 stop condition。

Plan 可以进入 accepted plan gate，随后进入 implementation gate。

## 9. PF Status Summary

| PF | 来源 | 简述 | 状态 |
|---|---|---|---|
| PF-01 | MiMo 01 / DS F5 | 错误类型迁移表与目标模块 | **已修复** |
| PF-02 | DS F2 | 取消策略收敛为直接 ToolCancelledOutcome | **已修复** |
| PF-03 | MiMo 02 / DS F4 | per-provider asyncio.Lock 创建/共享/获取时机 | **已修复** |
| PF-04 | MiMo 03 | 代表性 native callable 模板 | **已修复** |
| PF-05 | MiMo 04 / DS F1 / DS F3 | Slice 0 helper API 签名、typed result 字段、invalid_argument、校验范围 | **已修复** |
| PF-06 | MiMo 05 | legacy adapter 测试行为迁移覆盖 | **已修复** |
| PF-07 | DS F6 | Fins fixture 迁移路径 | **已修复** |
| PF-08 | DS F7 | Web live smoke 残余追踪 | **已修复** |
| PF-09 | DS F8 | ToolCancelledOutcome.meta 构造与测试 | **已修复** |

New findings: 2 条低严重度（NR-01, NR-02），非 blocking，供 implementation agent 参考。
