# WU-TOOLS-01-F01-02-R3 Plan Review — Adversarial Pass

- **Review target**: `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`
- **Work unit**: `WU-TOOLS-01-F01-02-R3`
- **GitHub Issue**: #130 Retire legacy tool adapter
- **Current gate**: plan review
- **Reviewer**: AgentDS (adversarial plan review)
- **Timestamp**: 2026-06-10T17:40:38+08:00

---

## 1. Motivation and Scope Judgment

### 动机成立且证据同源

Plan 第 4 节给出的根因证据链是完整的：

- `dayu/contracts/tool_outcome.py:93-141`：`ToolCancelledOutcome` 已存在，`host_cancelled` reason 常量已定义。
- `dayu/tools/_legacy_adapter/definition_adapter.py:358-382`：`project_legacy_exception` 对所有 `ToolBusinessError` 无条件构造 `ToolFailedOutcome`。
- `dayu/tools/doc_tools.py:135-173`：`_raise_doc_cancelled` 抛出 `ToolBusinessError(code="tool_cancelled")`。
- `dayu/tools/web/web_tools.py:478-497`：`_raise_fetch_cancelled` 同样抛出 `ToolBusinessError(code="tool_cancelled")`。
- `tests/fins/test_fins_storage_provider.py:647-834`：Fins read 取消测试当前断言 `ToolFailedOutcome` + `error="tool_cancelled"`。

这些证据均经过本 review 直接核对，根因与数据路径同源。

### 范围边界正确

Plan 第 2 节明确排除 WU-TOOLS-01-F08、F04/F05/F06/F07 CI pipeline/smoke、Engine/Host 状态机变更、兼容 re-export/facade。这与 control doc `issues-implementation-control.md:223-227` 一致（R3 是 active planning work unit，F08 是后续 pending WU）。

### 额外生产依赖发现正确

Plan 第 4 节 "额外证据和范围修正" 发现除三个 provider 外，`doc_tools.py`、`web_tools.py`、`web_search_providers.py`、`fins_tools.py`、`read_runtime.py`、`read_runtime_helpers.py`、`search_engine.py` 也 import legacy adapter。本 review 通过 `rg "_legacy_adapter" dayu/` 独立验证，命中文件与 plan 列表一致。

**结论**：动机成立，范围边界正确，无 scope creep。

---

## 2. Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|---------|
| A1 | `ToolCancelledOutcome(host_cancelled)` 已是公共契约，不需要新 Engine 契约 | **成立** — `dayu/contracts/tool_outcome.py:42-46` 已定义 `TOOL_CANCELLED_REASON_HOST_CANCELLED`，`ToolCancelledOutcome` 是 `ToolExecutionOutcome` 联合成员 |
| A2 | 三个 provider 的 legacy adapter 迁移可独立切片 | **成立** — Doc/Web/Fins read 三类工具各自有独立 provider、独立测试、独立业务 IO 路径 |
| A3 | Slice 0 runtime helper 只依赖 `dayu.contracts`，不违反 `dayu.runtime` 边界 | **部分成立** — 依赖方向正确，但 helper 的具体边界需要更精确（见 Finding 1） |
| A4 | Doc/Web/Fins read 工具 schema 在迁移中不变 | **成立** — plan 明确不改变工具名称、参数、描述，仅改变内部 callable 实现 |
| A5 | 删除 adapter 后无隐藏生产依赖 | **部分成立** — plan 已发现额外 imports，但 Slice 4 的 rg 验证需要在各 slice 完成后增量执行（见 Finding 6） |
| A6 | 参数校验可以从 legacy adapter 干净抽取到 runtime helper | **有风险** — 见 Finding 1、Finding 3 |

---

## 3. Findings

### F1 — 高 — Slice 0 runtime helper 接口契约不够具体，不可直接交给 implementation agent

- **位置**: Plan §8 Slice 0 "Exact changes" (lines 183-188)
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**:
  > - 新增参数校验函数，输入为 `ToolCallRequest`、工具名、`ToolParametersSchema`，输出 typed success/failure 联合。
  > - 覆盖 object 顶层 schema、unknown field、missing required、default、string/integer/number/boolean/array/object、enum、min/max、minLength/maxLength、minItems/maxItems。
  > - 新增 outcome helper：`completed_outcome(...)`、`failed_outcome(...)`、`host_cancelled_outcome(...)`。
  > - 新增 current 内部异常类型或结果类型，用于业务错误和语义取消；签名不得使用 `Any` / `object` / untyped 参数。

- **反例/失败场景**:
  1. Implementation agent 看到 "覆盖 object 顶层 schema、unknown field..." 这段描述后，会自行设计校验函数的返回类型、错误表示、与 outcome helper 的集成方式。不同 agent 可能产出完全不同的 API shape。
  2. 若校验函数返回 typed union，但 plan 未指定 union 的成员类型（success 携带什么？failure 携带什么错误码？），implementation agent 可能选择不可扩展的设计。
  3. "新增 current 内部异常类型或结果类型" 没有说明这些类型放在哪个模块、与 `ToolBusinessError`/`ToolArgumentError`/`FileAccessError` 的替换关系。

- **为什么有问题**: plan 声称是 code-generation-ready，但 Slice 0 的核心交付物（helper 的 public API surface）缺少函数签名级别的规格。当前描述足够做 design discussion，但不够让 implementation agent 直接写出代码而不需要额外设计决策。

- **直接证据**: Plan §8 Slice 0 lines 183-188；`dayu/contracts/tool_declaration.py:38-64`（`ToolCallable` protocol）；`dayu/runtime/__init__.py:1-35`（runtime 包边界）。

- **影响**: 实施 Agent 自行设计 helper API → 后续 slice 消费时发现不匹配 → 返工 Slice 0 或各 slice 自行重复实现。

- **建议改法和验证点**:
  1. 至少给出参数校验函数的签名草案，例如：
     ```python
     def validate_and_project_arguments(
         call: ToolCallRequest,
         tool_name: str,
         schema: ToolParametersSchema,
     ) -> _ValidatedArguments | _ArgumentValidationFailure: ...
     ```
  2. 明确 `_ValidatedArguments` 承载什么（`dict[str, JsonValue]` 还是 typed mapping），`_ArgumentValidationFailure` 承载什么（error code + message + hint）。
  3. 明确 "内部异常类型" 是否放在 `dayu/runtime/tool_call_projection.py` 内部，以及它们与 `ToolExecutionOutcome` 的关系（是抛异常由 callable 捕获，还是直接返回 outcome）。
  4. 至少给出 `host_cancelled_outcome` 的签名草案，包括 `meta` 参数（`ToolResultMeta | None`，含 `tool_name`/`started_at`/`finished_at`）。

- **修复风险**: 低 — 只需要补充 API 规格，不改变架构方向。
- **严重程度**: 高 — 若 Slice 0 API shape 在 Slice 1-3 实施中才发现需要改动，会导致连锁返工。
- **Adjudication status candidate**: `accepted`

---

### F2 — 高 — 取消语义的异常-vs-返回值策略未收敛，存在实现不一致风险

- **位置**: Plan §7 决策 4 (lines 157-161)；§8 Slice 0 "Cancellation semantics" (lines 195-197)
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**:
  > - 工具内部 checkpoint 可抛私有 `ToolInvocationCancelled` 或直接返回 cancelled outcome；无论采用哪种，捕获路径必须在通用异常捕获前处理。

- **反例/失败场景**:
  1. `ToolCallable` protocol (`dayu/contracts/tool_declaration.py:50-64`) 的返回类型是 `ToolExecutionOutcome`，docstring 说 "实现可透传业务异常；Host / ToolRuntime 负责把异常归一化为 ToolFailedOutcome"。如果 native callable 抛出 `ToolInvocationCancelled`，ToolRuntime 是否会把它当作普通异常归一化为 `ToolFailedOutcome`？如果是，那就保留了当前的 bug。
  2. 如果 Doc native callable 选择抛 `ToolInvocationCancelled` 而 Web native callable 选择直接返回 `ToolCancelledOutcome`，三个工具族的取消路径将不一致。
  3. Plan 说 "捕获路径必须在通用异常捕获前处理"，但未说明这个捕获发生在 callable 内部的 try/except 还是 ToolRuntime 层。

- **为什么有问题**: 取消是 correctness-critical 路径。两个策略 ("抛私有异常" vs "直接返回 outcome") 在 `ToolCallable` protocol 和 ToolRuntime 现有行为下有不同的控制流。plan 把选择权留给 implementation agent，但 protocol 边界和 ToolRuntime 行为是两个 agent 无法自行裁决的约束。

- **直接证据**:
  - `dayu/contracts/tool_declaration.py:50-64`：`ToolCallable.__call__` 返回 `ToolExecutionOutcome`，docstring 说异常由 Host/ToolRuntime 归一化。
  - `dayu/tools/_legacy_adapter/definition_adapter.py:130-137`：当前 `_AdaptedLegacyCallable.__call__` 在 `except Exception` 中调用 `project_legacy_exception`，不区分取消异常。
  - Plan §7 决策 4 的双选项表述。

- **影响**: Doc/Web/Fins 实施 agent 做出不同选择 → 取消行为不一致 → Slice 4 review 发现需要统一 → 返工。

- **建议改法和验证点**:
  1. Plan 必须明确选择一种策略并给出理由。推荐：**直接返回 `ToolCancelledOutcome`**，不抛异常。理由：(a) `ToolCallable` protocol 已定义 `ToolCancelledOutcome` 为合法返回值；(b) 避免 ToolRuntime 的异常归一化路径把取消异常误转为 `ToolFailedOutcome`；(c) 三个工具族的取消 checkpoint 代码只需 `return host_cancelled_outcome(...)` 即可，一致性强。
  2. 若必须保留抛异常路径，需要明确 ToolRuntime 是否已能区分 `ToolInvocationCancelled` 和普通异常，或是否需要在本 WU 中修改 ToolRuntime。
  3. 在 Slice 0 helper 中，`host_cancelled_outcome(...)` 的签名和文档必须明确说明它返回 `ToolCancelledOutcome`（不是抛异常）。

- **修复风险**: 低 — 只需做一个设计决策，不改变实现工作量。
- **严重程度**: 高 — 影响三个 slice 的取消正确性。
- **Adjudication status candidate**: `accepted`

---

### F3 — 中 — Slice 0 参数校验范围可能过度设计，缺少需求溯源

- **位置**: Plan §8 Slice 0 "Exact changes" (lines 184-186)
- **问题类型**: 过度设计
- **当前写法**:
  > - 覆盖 object 顶层 schema、unknown field、missing required、default、string/integer/number/boolean/array/object、enum、min/max、minLength/maxLength、minItems/maxItems。

- **反例/失败场景**:
  1. 当前 legacy adapter `project_tool_call_arguments` (`definition_adapter.py:147-`) 只做有限校验：类型检查、必填字段、默认值填充、路径参数投影。它不实现完整的 JSON Schema validation。
  2. 三个工具族的实际 schema 参数简单（Doc: 路径+pattern；Web: URL+query；Fins: ticker+document_id+section 等），大多只有 string 参数加 enum/required 约束。不需要 array item 校验、嵌套 object 校验、`minItems`/`maxItems`、数字 `min`/`max` 等完整 JSON Schema 能力。
  3. 如果 implement 了完整 JSON Schema validator，会增加大量测试负担（见 Finding 5）和未来维护成本，但实际只用其中一小部分。

- **为什么有问题**: CLAUDE.md 编码硬约束要求 "禁止过度设计"、"不做过度设计，以最小化满足需求为标准"。Plan §13 声称 "runtime helper 的边界很窄"，但如果实现完整的 JSON Schema validation，边界并不窄。

- **直接证据**:
  - `dayu/tools/_legacy_adapter/definition_adapter.py:147-`：当前参数校验的实际范围。
  - Doc/Web/Fins 工具 schema（通过 provider 代码可推断参数复杂度低）。
  - `CLAUDE.md` 架构硬约束第 2 条。

- **影响**: 实施 Agent 花时间实现用不到的校验规则 → 测试矩阵膨胀 → 后续维护负担。

- **建议改法和验证点**:
  1. Plan 应明确说明 Slice 0 的校验范围是从三个工具族的实际 schema 需求倒推的，而非 JSON Schema 规范的子集。
  2. 列出三个工具族实际需要的校验类型清单，只实现那些。
  3. 在 stop condition 中增加：若未来工具需要更多校验规则，由该工具的 WU 扩展 helper，不在 R3 提前实现。

- **修复风险**: 低 — 缩小范围不增加风险。
- **严重程度**: 中 — 不阻塞实施，但可能导致浪费和偏离 "最小化" 原则。
- **Adjudication status candidate**: `accepted`

---

### F4 — 中 — 并发 lock 的创建和共享机制未指定

- **位置**: Plan §7 决策 3 (lines 152-154)
- **问题类型**: 契约缺失
- **当前写法**:
  > - 并发策略从 legacy adapter 的 per-provider lock 迁移为 provider / builder 创建的 `asyncio.Lock`，由 native callable 显式共享。不得把 lock 藏在兼容 adapter。

- **反例/失败场景**:
  1. 当前 legacy adapter 在 `_AdaptedLegacyCallable.__init__` 接收一个外部 `lock: asyncio.Lock | None`，多个 callable 共享同一个 lock 实例。
  2. 在 native 方案中，`build_doc_tool_definitions(...)` 需要创建 lock 并传给五个 Doc callable。但 plan 只说 "由 native callable 显式共享"，没说 lock 在哪里创建、如何注入。
  3. 如果每个 callable 创建自己的 lock，则串行化失效。如果 lock 作为 `build_*_tool_definitions` 的隐式副作用创建，则是 hidden coupling。

- **为什么有问题**: Doc provider 使用 `SERIAL_PER_PROVIDER` 策略，五个 Doc 工具需要共享一个 lock。如果 implementation agent 不理解这个设计意图，可能错误地给每个 callable 独立 lock。

- **直接证据**:
  - `dayu/tools/doc_provider.py:244-246`：当前 `_adapt_doc_declarations` 设置 `LegacyToolConcurrencyPolicy.SERIAL_PER_PROVIDER`。
  - `dayu/tools/_legacy_adapter/definition_adapter.py:86-88`：`_AdaptedLegacyCallable` 接收外部 lock。
  - Plan §7 决策 3 lines 152-154 的模糊表述。

- **影响**: 实施 Agent 实现错误的并发策略 → Doc 工具并发行为退化 → Slice 4 发现 → 返工。

- **建议改法和验证点**:
  1. 明确 lock 由 `build_doc_tool_definitions(...)` 在函数内部创建（一个 `asyncio.Lock()` 实例），然后作为闭包或参数传给每个 callable。
  2. 在 Slice 1 tests 中增加并发串行化断言：两个并发 callable 调用应按序执行，不是交错。
  3. Web provider 同理（当前也设 `SERIAL_PER_PROVIDER`）。

- **修复风险**: 低 — 只需在设计上明确 lock 的创建位置。
- **严重程度**: 中 — Doc/Web 当前使用串行策略，实现错误会导致并发行为变化。
- **Adjudication status candidate**: `accepted`

---

### F5 — 中 — 错误类型迁移的目标模块未指定

- **位置**: Plan §7 决策 5 (lines 163-167)
- **问题类型**: 契约缺失
- **当前写法**:
  > - 将 `ToolBusinessError`、`ToolArgumentError`、`FileAccessError` 等从 legacy adapter 内部类型替换为 current helper 或领域本地私有类型。
  > - 不从 `dayu.tools._legacy_adapter` re-export 新类型。
  > - Web/Fins 业务模块需要的错误类型应从新 current helper 或本领域模块导入。

- **反例/失败场景**:
  1. `ToolArgumentError` 当前在 `dayu/tools/_legacy_adapter/exceptions.py`，被 `doc_tools.py`、`read_runtime.py`、`read_runtime_helpers.py`、`search_engine.py` 导入。替换后，这些文件从哪里导入新类型？
  2. `ToolBusinessError` 当前在 `dayu/tools/_legacy_adapter/tool_errors.py`，被 `doc_tools.py`、`web_tools.py`、`web_search_providers.py`、`fins_tools.py`、`read_runtime.py`、`search_engine.py` 导入。替换后，Web domain error 和 Fins domain error 是否各自独立定义？
  3. "从新 current helper 或本领域模块导入" 给了 implementation agent 两个选项，没有明确什么情况下用哪个。

- **为什么有问题**: 错误类型是模块间 import 依赖的锚点。如果错误类型位置不明确，implementation agent 可能创建不必要的跨包依赖（例如 Fins 模块 import `dayu/tools/` 下的类型）。

- **直接证据**:
  - `rg "_legacy_adapter" dayu/` 输出显示 `ToolBusinessError` 被 6 个文件导入，`ToolArgumentError` 被 3 个文件导入，`FileAccessError` 被 1 个文件导入。
  - Plan §7 决策 5 的双选项表述。

- **影响**: 实施 Agent 选择不一致的导入路径 → 产生不必要的跨包依赖 → 违反架构边界。

- **建议改法和验证点**:
  1. 明确分类：
     - 通用错误类型（如参数校验错误、通用业务错误基类）放 Slice 0 runtime helper。
     - 领域特定错误类型（如 Web fetch 失败、Fins storage 访问失败）放各自领域模块。
  2. 给出错误类型迁移表：旧类型 → 新类型 → 新位置。
  3. 在 Slice 4 import boundary 测试中增加跨包依赖检查。

- **修复风险**: 低 — 只需明确分类决策。
- **严重程度**: 中 — 影响 import 结构和架构边界。
- **Adjudication status candidate**: `accepted`

---

### F6 — 低 — Fins 测试 fixture 迁移路径不够具体

- **位置**: Plan §8 Slice 3 "Tests" (lines 397-404)
- **问题类型**: 测试缺口
- **当前写法**: plan 列出 Fins tests 要覆盖的行为（cancellation、error handling 等），但没有说明测试 fixture 如何从当前 `_discover_definitions(workspace_root)`（经过 legacy adapter）迁移到 native definition builder。

- **反例/失败场景**:
  - 当前 Fins 取消测试（如 `test_list_documents_pre_cancel_returns_tool_cancelled`，`tests/fins/test_fins_storage_provider.py:647`）使用 `_definitions_by_name(_discover_definitions(workspace_root))` 获取 definition，而 `_discover_definitions` 调用 `discover_tools(spec)` → `_adapt_fins_declarations(...)` → `adapt_collected_tools(...)`。删除 adapter 后，这些 helper 也需要改为使用 `build_fins_read_tool_definitions(...)`。
  - 如果 Slice 3 implementation agent 只是改了 production code 但没有同步更新测试 fixture helper，测试可能编译失败或静默地继续测试旧路径。

- **为什么有问题**: 测试是 plan 的关键验收信号。如果测试 fixture 迁移不明确，Slice 3 的 completion signal 可能误报。

- **直接证据**: `tests/fins/test_fins_storage_provider.py:647-664` 使用 `_definitions_by_name(_discover_definitions(...))` 模式。

- **影响**: 测试编译失败 → Slice 3 无法完成 → 需要额外 fix 轮次。

- **建议改法和验证点**:
  1. Plan 在 Slice 3 "Exact changes" 中增加一条：更新 `tests/fins/test_fins_storage_provider.py` 中的测试 fixture helper（如 `_discover_definitions`、`_definitions_for_read_runtime`）以使用 native `build_fins_read_tool_definitions(...)`。
  2. Slice 3 completion signal 中增加：Fins 测试 fixture helper 不再调用 `LegacyToolDeclarationCollector` 或 `adapt_collected_tools`。

- **修复风险**: 低 — 只需补充测试迁移说明。
- **严重程度**: 低 — 实施 agent 在 Slice 3 编码时自然会遇到此问题并处理，但提前规划可减少试错。
- **Adjudication status candidate**: `accepted`

---

### F7 — 低 — Web live smoke 验证缺口未充分说明

- **位置**: Plan §8 Slice 2 "Stop condition" (line 352); §9 "Tests / Validation Matrix" (lines 480-500)
- **问题类型**: 测试缺口
- **当前写法**:
  > - 若 Web live smoke 需要真实网络，不在本 slice 强跑；只运行 deterministic pytest。若 deterministic 测试无法覆盖 provider config / cancellation，先补测试替身再继续。

- **反例/失败场景**:
  - 当前 `utils/smoke_web_ci.py` 是 Web 工具的关键集成验证入口。如果 Web native callable 迁移引入了只能在真实 Playwright/网络环境下暴露的问题（如 cancellation 在 Playwright 启动后的行为），deterministic pytest 可能无法捕获。
  - Plan 的 stop condition 允许跳过 live smoke，但没有在 Slice 2 completion signal 中要求记录 "哪些场景只能在 live smoke 中验证"。

- **为什么有问题**: 如果 Slice 2 声称完成但未记录 live smoke 覆盖缺口，Slice 4 closeout 时无法判断 Web native 迁移是否引入了只能在集成环境发现的 regression。

- **直接证据**:
  - `tests/tools/web/test_smoke_web_ci.py:1-` 是 deterministic smoke 判定测试。
  - `utils/smoke_web_ci.py` 是 live smoke 脚本，不在默认 pytest 中运行。

- **影响**: Web native 迁移的集成风险未被显式追踪 → 后续发现 → 返工或回归。

- **建议改法和验证点**:
  1. Slice 2 completion signal 中增加：若未运行 live smoke，记录未覆盖的 live smoke 场景清单（如 Playwright cancellation、真实网络 fallback），并在 Slice 4 closeout 前运行或明确 deferred。
  2. 或者：在 Slice 2 validation commands 中增加 `utils/smoke_web_ci.py --external-limit 0` 的本地 fixture 模式运行（不需要真实网络），验证 native callable 路径。

- **修复风险**: 低 — 补充验证步骤不改变实现。
- **严重程度**: 低 — 不阻塞核心取消修复和 adapter 删除目标。
- **Adjudication status candidate**: `accepted`

---

### F8 — 低 — `ToolCancelledOutcome.meta` 字段在 Slice 0 helper 中缺少规格

- **位置**: Plan §8 Slice 0 "Cancellation semantics" (lines 195-197) vs `dayu/contracts/tool_outcome.py:93-115`
- **问题类型**: 契约缺失
- **当前写法**:
  > - Slice 0 只提供 cancelled outcome 构造，不主动观察 token。
  > - `host_cancelled_outcome` reason 固定为 `TOOL_CANCELLED_REASON_HOST_CANCELLED`，message / hint 不暴露 Host 内部字段。

- **反例/失败场景**:
  - `ToolCancelledOutcome` 有 `meta: ToolResultMeta | None` 字段，其中 `ToolResultMeta` 包含 `tool_name`、`started_at`、`finished_at`。其他 outcome（completed/failed）都填充 meta。
  - Plan 的 `host_cancelled_outcome(...)` 描述没有提到 meta 参数。如果 helper 不接收 meta，callable 需要在返回后手动构造完整的 `ToolCancelledOutcome`，降低了 helper 的价值。

- **为什么有问题**: 如果 Doc/Web/Fins callable 需要在取消路径上手动填充 meta，helper 的价值降低，且容易出现不一致（某个 callable 填了 meta，另一个没填）。

- **直接证据**: `dayu/contracts/tool_outcome.py:93-115`；`dayu/contracts/tool_result.py` 中 `ToolResultMeta` 定义。

- **影响**: 取消 outcome 的 meta 不一致 → LLM 收到的取消消息缺少上下文 → 轻微。

- **建议改法和验证点**:
  1. `host_cancelled_outcome` 签名增加 `started_at: datetime` 和 `finished_at: datetime` 参数（或 `meta: ToolResultMeta | None`），在 helper 内部构造完整 `ToolCancelledOutcome`。
  2. Slice 0 tests 增加 meta 字段非空断言。

- **修复风险**: 低 — 增加一个参数。
- **严重程度**: 低 — 不影响正确性，只影响一致性。
- **Adjudication status candidate**: `accepted`

---

## 4. Architecture Boundary Verification

### 4.1 `dayu.runtime` 依赖方向

Plan 将 Slice 0 helper 放在 `dayu/runtime/tool_call_projection.py`，依赖范围是标准库 + `dayu.contracts`。对照 `dayu/runtime/__init__.py` 的硬约束（不得 import engine/host/service/ui/fins），该依赖方向正确。

`dayu.contracts` 包含 `ToolCallRequest`、`ToolParametersSchema`、`ToolExecutionOutcome`、`ToolCancelledOutcome`、`ToolResultMeta` 等 helper 需要的类型，都在公共契约层，不违反分层。

**结论**：架构边界正确，无反向依赖风险。

### 4.2 Host / Engine 分层

Plan 明确不改 Host admission、dispatch、EventLog、ToolRuntime accept barrier 或 Engine 状态机。`ToolCancelledOutcome` 已被 Engine `tool_result_accepted` 路径接受（`docs/engine/design.md:320-329`），不需要 Engine 侧改动。

**结论**：分层边界保持，无泄漏。

### 4.3 Fins storage 边界

Plan §8 Slice 3 明确 "Fins read provider 继续通过 `DefaultFinsRuntime.create(workspace_root=...)` 获取 read runtime；不得绕过 storage 直接拼路径读取财报文件"。Stop condition 要求 "若 native migration 需要改变 Fins read runtime 或 storage public contract，停止"。

**结论**：Fins storage 边界保持。

### 4.4 LLM-facing schema 语义

Plan §6 明确不改变工具名称、LLM-facing 参数，不新增 `execution_context`、`cancellation_token`、`run_id` 等治理字段。Slip 1-3 的 tests 均要求验证 schema 不暴露 governance fields。

**结论**：LLM-facing schema 语义正确。

---

## 5. Slice Sequencing and Independence

Slice 顺序 (0 → 1 → 2 → 3 → 4) 合理：

- Slice 0 产出 helper，被 Slice 1-3 依赖。
- Slice 1-3 之间相互独立（Doc/Web/Fins），可以并行实施，但顺序执行也合理。
- Slice 4 严格依赖 Slice 1-3 全部完成。

每个 slice 有独立 completion signal 和 validation commands，满足 "可独立验证的行为闭环" 约束。

---

## 6. Test Coverage and Pyright Plan

### 覆盖范围

Plan §8-§9 的测试计划覆盖：
- Slice 0: 参数校验合法/非法、cancelled outcome 构造、治理字段不泄露
- Slice 1: 五工具 provider discovery、schema 无 governance、取消转 `ToolCancelledOutcome`、路径白名单、AST import 边界
- Slice 2: Web schema、truncate、取消转 `ToolCancelledOutcome`、AST import 边界
- Slice 3: 九工具 provider discovery、取消转 `ToolCancelledOutcome`、storage 边界、AST import 边界
- Slice 4: 全局 `rg` 验证、import boundary、combined acceptance

### 覆盖率要求

新增 runtime helper ≥ 80% 合理；大幅改写的 Doc/Web/Fins read tool 文件 "优先以现有 provider tests 覆盖主要 public callable 路径" 合理。

### Pyright

每个 slice 后要求 pyright 通过。最终 Slice 4 要求全量 pyright。

**结论**：测试和 pyright 计划充分，无明显缺口（除 Finding 6 的 Fins test fixture 迁移和 Finding 7 的 Web live smoke）。

---

## 7. README Trigger Decisions

Plan §10 的 README 触发判断正确：

- `dayu/fins/` 修改 → 需检查 `dayu/fins/README.md`
- `tests/` 修改 → 需检查 `tests/README.md`（当前 `tests/README.md:134-138` 仍描述 legacy adapter，删除后大概率需更新）
- 新增 `dayu/runtime` helper → 仅内部实现时可不改 `dayu/README.md`
- 不改 `docs/engine/design.md` 或 `docs/host/design.md`

---

## 8. Residual Risks Not Covered by Plan

Plan §11 已列出 5 个风险并给出缓解措施。本 review 认为以下额外 residual risk 值得追踪：

| # | 风险 | 建议追踪 |
|---|------|---------|
| RR1 | Slice 0 helper 参数校验实现过宽，成为未来不必要的依赖 | 在 Slice 0 completion 时由 review agent 验证 helper 的 public API surface |
| RR2 | Doc/Web/Fins 工具 schema digest 可能因声明构造方式变化而改变 | Plan 已覆盖（§11 Low risk），但建议在 Slice 4 显式验证 digest |
| RR3 | 删除 adapter 后，`dayu/tools/_legacy_adapter` 目录下可能有被非 tools 代码 import 的子模块（如 `tool_errors.py` 被 `web_search_providers.py` 使用）| Slice 1-3 各自验证，Slice 4 全局 rg 验证 |

---

## 9. Open Questions

无 blocking open questions。以下为非阻塞问题：

1. **Q1**: Slice 0 helper 中的参数校验是否需要处理 `$ref` / `$defs` 等 JSON Schema 高级特性？建议：不需要，三个工具族的 schema 均不使用这些特性。
2. **Q2**: Web `search_web` 和 `fetch_web_page` 的 Playwright fallback 中的 `CancelledError` 映射（Plan §8 Slice 2 line 322）是 Playwright 库自身的 `CancelledError` 还是 `asyncio.CancelledError`？建议在 Slice 2 实施时确认具体异常类型。

---

## 10. Final Verdict

**Overall verdict: pass-with-findings**

Plan 的动机、范围、架构方向、slice 切分和验证计划在结构上是正确的。8 条 findings 中：

- **F1（高）** 和 **F2（高）** 需要在 plan fix 中解决：Slice 0 helper API 签名需具体化，取消语义需收敛为单一策略。
- **F3-F5（中）** 建议在 plan fix 中解决，但不阻塞进入 implementation gate：参数校验范围可缩小、lock 创建位置需明确、错误类型迁移目标需分类。
- **F6-F8（低）** 可在 implementation 过程中自然解决，但提前在 plan 中明确更佳。

**Blocking open questions: none.**

**Plan can proceed to fix gate or accepted plan gate after addressing F1 and F2.** 建议先进入 plan fix gate 处理 F1-F5，再回到 plan re-review。
