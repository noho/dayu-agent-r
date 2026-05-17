# P9.5 S17 Documentation Review — AgentDS

**Review scope**: S17 Documentation And Control Tracking 未提交 diff
**Base**: `p9.5-pre-p10-hardening` vs HEAD unstaged changes
**Reviewer**: AgentDS
**Date**: 2026-05-17
**Verdict**: **PASS** — 7 findings, 0 blocking, 0 medium/high severity regressions

---

## Review methodology

逐文件逐行核对 diff 中的每处文档变更是否与当前代码事实一致，并检查 S1-S16 落地内容是否有稳定文档失准但未被 S17 触及的遗漏。所有证据来自直接代码阅读与工具验证（rg、pyright、git diff --check），不依赖间接推断。

---

## Finding 1: `dayu/engine/README.md` runner 装配描述校准

**Severity**: PASS

**Changed**: `dayu/engine/README.md:421`

**Old text**: "当前函数式入口创建的是内置 OpenAI-compatible Runner；接入其它 Runner 需要同步调整明确的 Runner 选择契约与装配代码。"

**New text**: "当前函数式入口通过私有默认装配点创建内置 OpenAI-compatible Runner；该私有装配点不是公共 factory、registry 或 runner 选择扩展点。"

**代码事实验证**:
- S1 创建了 `dayu/engine/_default_runner.py` 作为私有默认 runner 装配点，`_build_runner` 委托给该私有模块
- P9.5 design discussion 明确裁决 "runner 不做 factory / registry"（`docs/host/implementation-control.md:2036-2052`）
- `_default_runner.py` 为模块级 `_` 前缀私有模块，无公共导出

**修正价值**: 旧文本暗示存在一个"Runner 选择契约"（Runner selection contract），这与 P9.5 架构裁决直接矛盾。新文本准确描述了当前私有默认装配点的边界——它是当前 OpenAI-compatible runner 的私有实现细节，不是公共扩展点。去除了对不存在契约的误导性描述。

**Conclusion**: 精准反映 S1 后的代码事实与架构裁决。

---

## Finding 2: 工具边界 `tool_executor` 同源约束补齐

**Severity**: PASS

**Changed**: `dayu/README.md:221`, `docs/design.md:74-76`

**Old text**: "RunInputBuilder 投影给 Engine 的 `tool_schemas` 必须来自 effective ToolBundle。"

**New text**: "RunInputBuilder 投影给 Engine 的 `tool_schemas` 与 ToolRuntime 执行使用的 `tool_executor` 必须来自同一个 effective ToolBundle。"

**代码事实验证**:
- `ToolRuntimeHandle.effective_bundle` 同时提供 `tool_schemas` 与 `tool_executor`:
  - `handle.tool_schemas == handle.effective_bundle.tool_schemas`
  - `handle.tool_executor.effective_bundle is handle.effective_bundle`
- `test_business_bundle_projects_schema_and_callable_from_same_bundle` (`tests/host/test_toolruntime_effective_bundle.py:63`) 断言两者来自同一 `effective_bundle`
- `docs/design.md:84-87` 已描述"Host 接收业务 ToolBundle；ToolRuntime factory 生成 effective ToolBundle，把其中的 ToolSchema 投影给 Engine，并把 ToolCallable 包装进受治理的 ToolExecutor"

**修正价值**: 旧文本只强调了 `tool_schemas` 的来源，未提及 `tool_executor` 的同源约束。`tool_executor` 同样来自 effective ToolBundle 是 attempt-local isolation 的关键保证——如果 schema 来自 effective bundle 但 executor 来自别处，会导致 schema 与 callable 不同源，破坏同源 invariant。补齐后工具边界描述完整。

**Conclusion**: 补齐了 effective ToolBundle 同源约束中缺失的 `tool_executor` 侧。

---

## Finding 3: `dayu/host/README.md` catch-up failure 日志级别校准

**Severity**: PASS

**Changed**: `dayu/host/README.md:121`

**Old text**: "失败时记录 `dayu.host.projection` logger exception，并保留已提交的 durable command / accept 结果。"

**New text**: "失败时只记录 projection-local `WARNING` 与 `error_type`，并保留已提交的 durable command / accept 结果。"

**代码事实验证**:
- S15 在 `dayu/host/projection.py` 的 `catch_up_projection_best_effort` 中将:
  ```python
  LOGGER.exception("projection catch-up failed; continuing")
  ```
  改为:
  ```python
  LOGGER.warning("projection catch-up failed; continuing error_type=%s", type(exc).__name__)
  ```
- `LOGGER.exception()` → ERROR 级别 + 完整 traceback
- `LOGGER.warning()` → WARNING 级别 + 仅 `error_type`（不含 exception message 或 traceback）
- `tests/host/test_toolruntime_accept_barrier.py::test_tool_fact_accept_survives_projection_catchup_failure` 断言 `all(record.levelname == "WARNING")`
- `dayu/README.md:20` 定义 WARNING 为"汇报可恢复异常"——"Host projection catch-up 失败但 command 已提交"精确匹配此定义
- "保留已提交的 durable command / accept 结果"语义未变 ✓

**为什么旧文本"记录 logger exception"是错误的**: Python `logger.exception()` 专有名词指的是 ERROR 级别 + `exc_info=True`（完整 traceback）。S15 后实际语义是 WARNING 级别 + 仅 `error_type` 字符串。旧文本在两个维度上均失准：级别（ERROR→WARNING）和内容（exception+traceback→error_type）。

**Conclusion**: 精准反映 S15 后的日志级别与字段语义。

---

## Finding 4: `tests/README.md` import boundary 描述补齐 S16 guard

**Severity**: PASS

**Changed**: `tests/README.md:65,79,104,96`（共 4 处）

逐项验证：

| 分层 | 旧文本缺失项 | 新文本 | 代码证据 |
|---|---|---|---|
| runtime | Host | "Engine、Host、Service、UI、Fins" | `RUNTIME_FORBIDDEN_PREFIXES` 含 `dayu.host`（既有，文档补漏） |
| contracts | Host, runtime implementation | "Engine、Host、runtime implementation、Service、UI、Fins" | S16 新增 `dayu.runtime`；`dayu.host` 既有 |
| engine | Host, memory, 工具声明 owner | "Host、Service、UI、Fins、memory、工具声明 owner、..." | `dayu.host` 既有（文档补漏）；memory 由 `dayu.host` 前缀覆盖；S16 新增 `ToolCallable` + `tool_declaration` module ban |
| host | business tool scanner, fetch_more owner | "阻止 Host 使用动态模块扫描能力扫描业务工具模块...并确认 fetch_more 只留在 ToolRuntime / tooling owner" | S16 新增 `test_host_does_not_import_business_tool_scanners` + `test_fetch_more_token_stays_inside_toolruntime_owner_modules` |

**关于"既有，文档补漏"项**: runtime 禁止 Host、Engine 禁止 Host、contracts 禁止 Host 均为 S16 前已存在的测试 guard。旧 `tests/README.md` 未列出这些层，属于历史文档遗漏。S17 一并补齐，不区分新增与补漏——这符合"以代码为准"的文档原则。

**Fins 大小写统一**: 旧文本混用 "fins"（小写）与 "Fins"，新文本统一为 "Fins"（专有名词大写）。

**Conclusion**: 四层 import boundary 描述均与当前测试 guard 的实际禁止列表一致，无夸大、无遗漏。

---

## Finding 5: 未更新 `docs/host/implementation-control.md` 与 `docs/host/design.md` 的合理性

**Severity**: PASS

**`docs/host/implementation-control.md`**:
- 当前已记录 S10-S16 accepted slice entries，包含 validation evidence、review artifacts、commit hash 与 gate transition（`implementation-control.md:2036-2081`）
- S16 entry 末尾明确写 "当前 gate 为 P9.5 S17 Documentation And Control Tracking implementation"（line 2055-2056）
- S17 自身 completion record 由 controller 在 S17 accepted 后写入（与 S10-S16 既有模式一致）
- S17 本轮未发现新的 residual risk 需要 disposition，未发现未关闭 tracking item
- **结论**: 无需在 S17 diff 中更新；controller post-accept 写入符合既有流程

**`docs/host/design.md`**:
- 包含 ToolRuntime effective bundle、`fetch_more` 普通工具路径、Host 不扫描业务工具模块、Engine 不理解工具声明 owner、memory projection / catch-up 边界等设计真源
- S17 的 README 修正未改变任何设计语义——设计真源与代码事实之间无偏差
- **结论**: 设计未变，无需更新

**`docs/design.md`** 已在 diff 中同步更新（Finding 2），属于仓库级设计文档的正常触发更新。

---

## Finding 6: 无未来承诺、过程流水、实现细节或 README 职责越界

**Severity**: PASS

**逐文件检查**:

| 文件 | 未来承诺 | 过程流水 | 实现细节 | 职责越界 |
|---|---|---|---|---|
| `dayu/README.md` | 无；"必须来自"是当前约束 | 无 | 无；只说"同一个 effective ToolBundle"，不说如何构建 | 无；工具边界属于架构总览职责 |
| `dayu/engine/README.md` | 无；"不是"是当前否定约束 | 无 | 无；只说"私有默认装配点"，不说 `_default_runner.py` 路径或函数名 | 无；扩展点属于 Engine 开发手册职责 |
| `dayu/host/README.md` | 无 | 无 | 无；只说 WARNING + error_type，不说 `LOGGER.warning(...)` 代码 | 无；memory catch-up 属于 Host 关键机制职责 |
| `docs/design.md` | 无 | 无 | 无 | 无；工具边界属于仓库级设计职责 |
| `tests/README.md` | 无 | 无 | 无；只说"阻止...导入"，不说 AST 扫描实现 | 无；测试分层描述属于测试手册职责 |

所有变更描述当前代码事实，使用现在时态，不写"将会""计划""后续"等未来措辞。不记录 slice 实施过程或决策历史（这些属于 `docs/reviews/` 和 `implementation-control.md` 的职责）。

---

## Finding 7: 示例命令核对

**Severity**: PASS

**验证结果**:
- 本轮 diff 未修改任何 Python import 示例、pytest 命令、pyright 命令或 CLI 调用示例
- `dayu/engine/README.md` 中 `run_agent_messages`、`AgentRunRequest`、`EngineEvent` 等公共入口仍对应 `dayu/engine/__init__.py` 的实际导出
- `tests/README.md` 引用的测试目录（`tests/runtime/`、`tests/contracts/`、`tests/host/`、`tests/engine/`）均存在且包含对应测试文件
- `git diff --check` clean，无 trailing whitespace、无 conflict markers

---

## Adversarial completeness check: S1-S16 落地但稳定文档仍失准的遗漏扫描

对 S1-S16 每项可能触发 README 更新的变更做反向扫描：

| Slice | 可能触发 README 的变更 | 当前文档状态 |
|---|---|---|
| S1 | Engine runner 协议解耦，`_default_runner.py` 私有装配点 | `dayu/engine/README.md` 已更新 ✓ |
| S2 | Engine parser 内部 hardened | 无稳定接口变更，无需文档更新 |
| S3 | Host public error taxonomy（内部翻译，public API 不变） | 无稳定接口变更，无需文档更新 |
| S4 | Host durable helper API 收紧（内部） | 无稳定接口变更 |
| S5 | Schema CHECK hardened（内部） | 无稳定接口变更 |
| S6 | Read API enum mapping（内部） | 无稳定接口变更 |
| S7 | LocalProxy close/events race（内部） | 无稳定接口变更 |
| S8 | Engine wait confirmation ref hardened（内部） | 无稳定接口变更 |
| S9 | Runtime lane hardened（内部） | `dayu/README.md` runtime 节未变，lane 行为文档已在 `tests/README.md` |
| S10 | Dispatch lifecycle（内部） | 无稳定接口变更 |
| S11 | ToolRuntime boundary cleanup（内部模块拆分） | 无 public API 变更 |
| S12 | ToolRuntime truncation/duplicate hardened（内部） | 无稳定接口变更 |
| S13 | Size governance（内部，无新 error code） | 无稳定接口变更 |
| S14 | Memory cleanup / catch-up wiring | `dayu/host/README.md` S14 时已更新；S17 校准日志级别 |
| S15 | Logging（非 API，日志非真源） | `dayu/host/README.md` 日志级别校准 ✓；`dayu/README.md` 日志语义无需变更 |
| S16 | Contract Ownership audit（纯测试 guard） | `tests/README.md` import boundary 补齐 ✓ |

**未发现需要更新但未触及的稳定文档失准**。

关于 `dayu/host/README.md` 中 memory 段是否应同步 S14 的 `current_goal` first-write-wins：`current_goal` 是 `PinnedStateView` 的内部字段实现细节，first-write-wins 是纯内存投影逻辑，不构成公共 API、稳定边界或架构契约。按 CLAUDE.md"不写实现细节"约束，不应进入 README。

---

## Summary

| # | Finding | Severity | Verdict |
|---|---|---|---|
| F1 | `dayu/engine/README.md` runner 装配描述校准 | — | PASS |
| F2 | 工具边界 `tool_executor` 同源约束补齐 | — | PASS |
| F3 | `dayu/host/README.md` catch-up failure 日志级别校准 | — | PASS |
| F4 | `tests/README.md` import boundary 描述补齐 | — | PASS |
| F5 | 未更新 implementation-control.md / design.md 的合理性 | — | PASS |
| F6 | 无未来承诺/过程流水/实现细节/职责越界 | — | PASS |
| F7 | 示例命令仍对应当前代码 | — | PASS |

**Evidence**:
- `python -m pyright dayu tests` → 0 errors, 0 warnings, 0 informations
- `git diff --check` → clean
- 5 files changed, 10 insertions, 9 deletions

**Overall verdict**: PASS — S17 以最小变更量（+10/-9 行）精准校准了 S1-S16 落地后稳定文档中的 5 处失准：(1) Engine runner 装配点描述（S1 后未同步），(2) `tool_executor` 同源约束缺失（`dayu/README.md` 与 `docs/design.md`），(3) memory catch-up failure 日志级别（S15 后未同步），(4) `tests/README.md` 四层 import boundary 描述滞后（S16 guard 未反映 + 历史遗漏 Host 层）。无过度更新，无未来承诺，无职责越界。
