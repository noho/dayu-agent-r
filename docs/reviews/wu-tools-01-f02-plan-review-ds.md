# WU-TOOLS-01-F02 Plan Review

## Gate

- Work unit: `WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate: plan review
- Reviewer: AgentDS
- 日期: 2026-06-09
- Artifact path: `docs/reviews/wu-tools-01-f02-plan-review-ds.md`
- 设计真源: `docs/host/design.md`; `docs/engine/design.md`
- 总控真源: `docs/host/issues-implementation-control.md`
- Goal confirmation artifact: `docs/reviews/wu-tools-01-f02-goal-confirmation-controller.md`
- Plan artifact: `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Issue owner: GitHub Issue #120

## Verdict

**pass-with-findings**

Plan 已达到 code-generation-ready 水平。所有 finding 均可在 implementation 阶段就地解决，不要求 plan 重写或 scope 回退。无 blocking finding。

## Reviewed Scope

- Plan 目标与动机（第一性原理判断、成功信号、非目标）
- 范围边界与 allowed/forbidden files
- 设计真源对齐（Host/Engine/ToolsDiscovery/LLM-facing 语义）
- Adapter 方案：通过 current `ToolDefinition.callable` 调用 `fetch_web_page`
- 实现切片计划（Slice 1/2/3）
- Contract/Schema 变化与 utility JSON schema
- 测试边界（deterministic vs live diagnostics）
- AGENTS.md 约束覆盖（中文 docstring、强类型、README 触发规则）
- 用户补充授权处理
- Stop conditions 与 residual risks

## Findings

### Finding 1 — HIGH — CancellationToken 具体实现未指定

**Severity**: HIGH（不阻塞，但 implementation 必须先解决）

**Plan 行文证据**:
- 计划第 218 行: `cancellation_token=...)`，`...` 为占位符
- 计划第 216-217 行: 构造 `BatchToolExecutionContext(run_id="diagnose-web", session_id="diagnose-web", iteration_id="diagnose-web", timeout_seconds=tool_timeout_budget, cancellation_token=...)`

**代码证据**:
- `dayu/contracts/cancellation.py:21`: `CancellationToken` 是 `Protocol`，不是具体类
- `dayu/contracts/tool_call.py:136`: `BatchToolExecutionContext.cancellation_token` 字段类型为 `CancellationToken`
- 当前仓库中 `CancellationToken` 的具体实现仅存在于 `dayu/host/dispatch.py`（`_HostCancellationToken`、`_DurableRunCancellationToken`），均绑定 Host 内部状态，不适合 `utils/` 诊断脚本使用

**分析**: 计划正确识别了需要构造 `BatchToolExecutionContext` 并传入 `CancellationToken`，但占位符 `...` 意味着 implementation 需要自行设计一个诊断专用的 no-op token。这是 adapter 路径上唯一未闭合的契约缺口。

**裁决**: **accepted**。implementation 时需在 `utils/diagnose_web_access.py` 内定义一个私有 `_DiagnosticCancellationToken`（dataclass 或简单类），实现 `is_cancelled() -> False`、`cancel_reason() -> None`、`requested_at() -> None`。该实现约 10 行代码，不影响任何 production contract。

---

### Finding 2 — MEDIUM — adapter 路径中 `discover_tools` 语义歧义

**Severity**: MEDIUM（不阻塞，但 implementation 若选错函数会引入不必要的 dependency）

**Plan 行文证据**:
- 计划第 206 行: `实现 _build_fetch_web_page_definition(...)，用 dayu.tools.web.discover_tools(...) 与 ToolsDiscoveryProviderSpec 构造 current Web provider config`
- 计划第 214 行: `从返回 definitions 中选择 name 为 fetch_web_page 的 ToolDefinition`

**代码证据**:
- `dayu/tools/web/__init__.py:8`: `from .provider import discover_tools` — 这是 `provider.discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput`
- `dayu/runtime/tools_discovery.py:276`: 另有 `discover_tools(provider_specs: Sequence[ToolsDiscoveryProviderSpec]) -> ToolsDiscoveryResult` — 这是聚合器入口
- 两个函数签名不同，返回类型不同（`ToolsDiscoveryProviderOutput` vs `ToolsDiscoveryResult`）

**分析**: 计划使用的 `dayu.tools.web.discover_tools` 是 Web provider 的单 provider 入口，返回 `ToolsDiscoveryProviderOutput`，其 `.definitions` 字段即为 `tuple[ToolDefinition, ...]`。若 implementation 误用 `dayu.runtime.tools_discovery.discover_tools`，则需额外的 `ToolsDiscoveryProviderSpec` 列表和 `ToolsDiscoveryResult.tool_bundle.definitions` 解包。计划行文足够明确（`ToolsDiscoveryProviderSpec` + `.definitions`），但未在两个同名函数之间做显式区分。

**裁决**: **accepted**。implementation 应使用 `dayu.tools.web.provider.discover_tools(spec)` 或等价的 `dayu.tools.web.discover_tools(spec)`，直接获取 `ToolsDiscoveryProviderOutput.definitions`。如需额外诊断能力（如记录 provider metadata），可在 `_build_fetch_web_page_definition` 内部封装。

---

### Finding 3 — MEDIUM — 测试要求与 CLAUDE.md `utils/` 豁免之间的张力未说明

**Severity**: MEDIUM（不阻塞，但可能引起 implementation 时对测试边界的误判）

**Plan 行文证据**:
- 计划 Slice 3（第 328-349 行）: 要求完整的 deterministic tests，覆盖 parser/classifier/adapter/batch summary
- 计划第 364 行: `pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`

**CLAUDE.md 证据**:
- CLAUDE.md 第 93 行: `dayu/render/ 和 utils/ 下的脚本默认无需测试、无覆盖率要求`

**分析**: 计划要求的测试覆盖超出了 CLAUDE.md 对 `utils/` 脚本的最低要求。这不是问题——计划正确地认识到 diagnostics adapter 逻辑（parser、classifier、current contract adapter）的复杂性需要测试保护。但计划未引用 CLAUDE.md 的豁免条款，也未说明为何在此处主动选择更高标准。若 implementation 严格按 CLAUDE.md 豁免，可能省略部分测试；若严格按计划执行，则测试投入高于 CLAUDE.md 要求。

**裁决**: **accepted**。implementation 应保守执行：parser/classifier/adapter 的 deterministic tests 是必要的工程保护（这些逻辑有非平凡的分支和边界条件），不应因 CLAUDE.md 豁免而省略。但 shell wrapper 语法检查（`bash -n`）和 corpus 解析的纯格式测试属于低风险项，可按 CLAUDE.md 豁免灵活处理。Implementation report 应说明测试取舍依据。

---

### Finding 4 — LOW — Diagnostic JSON schema 稳定性的跨 work unit 契约未定义

**Severity**: LOW（不影响 F02 implementation，但 F03 消费者需要明确约定）

**Plan 行文证据**:
- 计划第 164 行: `Diagnostic JSON 是 utility artifact，不是 Host/Engine public contract，但需要足够稳定供 F03 消费`
- 计划第 408 行: `diagnostic JSON 是 utility-level schema；F03 可能需要进一步裁决哪些字段进入 Web smoke evidence`

**分析**: 计划正确地将 diagnostic JSON 定位为 utility artifact 而非 public contract，但同时承认 F03 需要消费它。这两者之间存在张力：如果 schema 在 F02 和 F03 之间发生变化，F03 需要知道哪些字段是稳定承诺、哪些可能调整。计划将此风险列为 residual risk（第 408 行），但未提出最小稳定字段子集或版本协商策略。

**裁决**: **accepted**。F02 implementation 应在 diagnostic JSON 中明确 `schema_version: "web-diagnostics-v1"`，并确保 `comparison_bucket`、`url`、per-path `ok`/`elapsed_seconds`/`error_code` 等 F03 smoke 判定必需的最小字段集合保持稳定。F03 plan 应显式声明它依赖哪些 F02 字段，并处理 schema 不匹配时的 skip/fail 策略。

---

### Finding 5 — LOW — comparison bucket 分类算法未定义

**Severity**: LOW（implementation 时需设计，但不影响 plan 整体正确性）

**Plan 行文证据**:
- 计划第 234-248 行: 列出 12 个 bucket 名称
- 计划第 249 行: `bucket 只描述访问路径对比，不表达网页内容的业务事实`

**OLD 代码证据**:
- OLD `utils/diagnose_web_access.py` 的 bucket 分类逻辑是旧实现的一部分，但分类规则与 OLD `ToolRegistry`/OLD outcome shape 耦合

**分析**: 计划列举了 bucket 名称但未给出分类算法。当前 outcome shape（`ToolCompletedOutcome`/`ToolFailedOutcome`/`ToolCancelledOutcome`/`ToolAwaitingOutcome`）与 OLD outcome 不同，classification logic 需要重写。这不是 plan 的缺陷——plan gate 不需要实现级细节——但 implementation 需要注意：
- `ToolAwaitingOutcome` 和 `ToolCancelledOutcome` 在诊断场景中可能不会出现（诊断使用 no-op CancellationToken），但代码应处理
- `ToolFailedOutcome.result.error` 是错误码字符串，需要映射到 bucket（如 `fetch_only_failure` vs `all_failed`）

**裁决**: **accepted**。implementation 应定义明确的分类决策树，并以 deterministic tests 覆盖所有 OLD 12 bucket 的 synthetic profile 组合。

---

### Finding 6 — INFO — 用户补充授权处理正确，但边界描述可强化

**Severity**: INFO（不阻塞，当前处理已足够）

**Plan 行文证据**:
- 计划第 262-264 行: `用户补充授权不改变 F02 非目标...若 implementation 发现已有 diagnostics CI entry 可在不启用 live network/browser 的前提下增强 opt-in 效果，可在 implementation report 中提出；不得在 F02 自行改变默认 CI workflow`

**Goal confirmation 证据**:
- Goal confirmation 第 81 行: `plan 可以基于代码证据评估是否需要修改当前 repo 的 CI / diagnostics 相关代码来增强 CI 效果`

**分析**: 计划正确处理了用户补充授权：允许评估和提出增强建议，但不自行实施 CI workflow 变更。这保持了 F02 的窄 scope，同时尊重了用户的授权意图。

**裁决**: **accepted**。implementation report 可包含 CI enhancement 观察，但任何 CI workflow 变更必须作为独立的 Controller 裁决项，不进入 F02 implementation。

---

### Finding 7 — INFO — `utils/` 强类型与中文 docstring 要求已在计划中覆盖

**Severity**: INFO（无行动项，确认覆盖）

**Plan 行文证据**:
- 计划第 252-255 行: 明确要求 `utils/diagnose_web_access.py` 提供中文 docstring、禁止 `Any`/`object`/无类型签名
- 计划第 255 行: `对 Playwright 动态对象，优先使用本地 private Protocol 或窄 wrapper`

**AGENTS.md 证据**:
- CLAUDE.md 第 61-63 行: 中文 docstring + 禁止 `Any`/`object`/无类型签名
- CLAUDE.md 第 65 行: `使用 hasattr、getattr 必须有充分理由`

**分析**: 计划正确覆盖了 AGENTS.md 的编码硬约束。特别是对 Playwright 动态对象建议使用 Protocol/wrapper 而非 `getattr`/`hasattr` 逃逸，这与 CLAUDE.md 的意图一致。

**裁决**: **accepted**。无额外行动项。

---

## Missing Evidence / Open Questions

1. **Batch subprocess isolation 机制**: 计划第 318 行提到"batch 子进程失败是 batch-level error"，暗示 batch mode 可能使用 subprocess 做 per-URL 隔离。若使用 subprocess，需确认 `python -m utils.diagnose_web_access` 可在子进程中独立运行（依赖 `.venv`、`PYTHONPATH` 等环境假设）。此细节可留待 implementation 决定。

2. **Shell wrapper 跨平台兼容性**: 计划未说明 `diag_web.sh` / `diag_web_batch.sh` 是否需要支持非 macOS/Linux 环境，或是否需要 Python venv 自动激活。

3. **`asyncio.run` 与现有 event loop 冲突**: 计划第 215 行指定 `asyncio.run(...)` 调用 async callable。CLI 脚本场景下这是标准做法，但若未来诊断脚本被嵌入已有 event loop 的上下文（如 pytest-asyncio），可能需要 `await` 变体。此风险在 residual risk 中未被提及。

## Residual Risks（计划已识别，review 确认）

- live network 结果天然不稳定 → F02 通过 explicit opt-in + evidence-only 输出缓解（confirmed）
- Playwright 安装差异 → 缺失记录为 diagnostic profile failure（confirmed）
- `fetch_web_page` internals 变化 → `ToolDefinition.callable` 比 private import 耦合更低（confirmed）
- diagnostic JSON schema 稳定性 → F03 需进一步裁决（confirmed, see Finding 4）
- 敏感 header/storage-state path 泄露 → implementation 必须脱敏且不内联（confirmed）

## Recommendation for Next Gate

**进入 implementation gate，条件如下**:

1. Implementation 开始前，先解决 Finding 1（实现 `_DiagnosticCancellationToken`）和 Finding 2（确认 `discover_tools` 调用路径）。
2. Implementation 按 Slice 1 → Slice 2 → Slice 3 顺序推进，每个 slice 完成后运行该 slice 的 local validation。
3. Slice 2 先验证 adapter 路径可用（单 URL 模式调用 current `fetch_web_page` 并产出有效 outcome），再实现批量模式。
4. 若 Slice 2 遇到 stop condition（current `fetch_web_page` 无法通过 `ToolDefinition.callable` 调用），立即停止并报告 Controller，不得绕过。
5. Implementation closeout 时，所有 MEDIUM/HIGH finding 必须在 implementation report 中说明处置结果。

## Review Methodology

- 阅读计划全文、goal confirmation、control doc、GitHub Issue #120
- 审查 current contract chain: `ToolDefinition.callable` → `_AdaptedLegacyCallable.__call__` → `ToolCallRequest` + `BatchToolExecutionContext` → `ToolExecutionOutcome`
- 审查 import chain: `dayu.tools.web.discover_tools` → `provider.discover_tools` → `register_web_tools` → `_create_fetch_web_page_tool` → `web_playwright_backend`（lazy playwright import）
- 审查 `CancellationToken` Protocol 与现有实现的可用性
- 对 plan 的每个 claim 做了代码证据或文档证据的交叉验证
- 未修改任何 plan artifact 或生产代码
