# WU-TOOLS-01-F01-02 Plan Review — AgentMiMo

## Review Metadata

| 项目 | 值 |
|---|---|
| reviewer | AgentMiMo |
| artifact type | plan review gate |
| work unit | WU-TOOLS-01-F01-02 |
| plan artifact | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| design sources | `docs/host/design.md`；`docs/engine/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| review date | 2026-06-08 |

## Verdict

**Plan 可进入 implementation gate。无 blocking finding。**

Plan 整体质量高：root cause 判断基于直接代码证据、scope 边界清晰、non-goals 合理、implementation slices 可独立实现且可测试。以下 findings 按严重性排序，均为 non-blocking，但 implementation 时需逐一处理。

---

## Findings

### F-01: Slice 4 Fins read tools execution context 注入方案需确认是否需要改 `read_section` 的 `**_kwargs` 签名

**严重性**: low
**状态**: needs-more-evidence
**位置**: plan §8 Slice 4, `dayu/fins/tools/fins_tools.py:319-350`

**问题**: plan 提到 "`read_section` 若当前有 `**_kwargs`，实现时优先移除可避免的兼容"。但 plan 未给出 `read_section` 当前签名的直接证据。若 `**_kwargs` 存在且有外部调用方依赖，移除可能扩大 blast radius。

**证据**: `fins_tools.py:319` 处 `@tool` 声明存在，但 plan 未引用 `read_section` 函数签名的具体行号。

**建议**: implementation 时先读 `read_section` 函数签名，确认 `**_kwargs` 是否存在及其调用方，再决定移除或保留。plan 本身不做修改。

### F-02: Slice 2 `search_web` 添加 `execution_context` 后，`search_public_web` 签名变更可能影响非 tool 直接调用方

**严重性**: low
**状态**: deferred-with-owner
**位置**: plan §8 Slice 2, `dayu/tools/web/web_search_providers.py:134-149`

**问题**: plan 要求给 `search_public_web` 新增 `cancellation_token: CancellationToken | None = None` keyword-only 参数。该函数是模块级公共函数，可能有非 tool 的调用方。当前 plan 未审计 `search_public_web` 的所有调用方。

**证据**: `web_search_providers.py:134` 定义了 `search_public_web`，`web_tools.py:1092-1106` 是已知调用方。需确认是否还有其他调用方。

**建议**: implementation 时 grep `search_public_web` 确认调用方范围。新增 keyword-only 参数默认值为 `None`，向后兼容，但审计仍应做。owner = implementation agent。

### F-03: Slice 3 Doc tools 的 `_raise_doc_cancelled` 使用 `ToolBusinessError` 还是直接 raise 需明确 adapter 投影行为

**严重性**: low
**状态**: needs-more-evidence
**位置**: plan §8 Slice 3

**问题**: plan 提到 Doc tools 用 `_raise_doc_cancelled(...)` 使用 `ToolBusinessError` 或 "现有 adapter-compatible 业务异常"。但 plan §7 也说 "legacy Web / Doc / Fins read tools 因 adapter 当前会把异常投影为 `ToolFailedOutcome`，实现时优先沿用现有 Web `tool_cancelled` 业务错误模式"。需要确认 Web 的 `tool_cancelled` 模式具体是什么异常类/错误码。

**证据**: `web_tools.py:1186` 处 `fetch_web_page` 的 docstring 提到 `ToolBusinessError`。需确认 `ToolBusinessError(code="tool_cancelled")` 是否为 Web 当前使用的模式。

**建议**: implementation 时先确认 Web `tool_cancelled` 的具体实现（异常类、error code 字符串），然后 Doc / Fins read 统一沿用。plan 的意图清晰，只是缺少具体异常类名。

### F-04: Slice 1 Fins awaiting 工具 start 后 cancel 的 "return ToolCancelledOutcome" 与 "return awaiting with cancelled job" 两条路径需更明确

**严重性**: medium
**状态**: accepted
**位置**: plan §8 Slice 1, line 159

**问题**: plan 说 "start 后若 token 取消，调用 `runtime.request_cancel(job_id)` 并返回取消 outcome"。但这里存在两种合理实现：

1. 直接返回 `ToolCancelledOutcome`（不经过 legacy adapter，因为 Fins awaiting callable 是 direct callable）。
2. 仍然返回 `ToolAwaitingOutcome`，但 job 已进入 cancelling 状态，让 wait adapter 在下次 poll 时收口。

plan 在 §7 已明确 "direct Fins awaiting callable 可以直接返回 `ToolCancelledOutcome`，因为它不经过 legacy exception projection"，但 Slice 1 的具体描述未强调这一点。

**证据**: `wait_adapter.py:282-300` 已有 `_cancelled_outcome` 将 `CANCELLED` job 投影为 `ToolCancelledOutcome`。`download_tools.py:47` 的 `__call__` 返回 `ToolExecutionOutcome`，可以返回 `ToolCancelledOutcome`。

**建议**: implementation 时，Slice 1 的 direct callable 在 start 后 cancel 时应直接返回 `ToolCancelledOutcome`（路径 1），因为：
- job 已经进入 durable cancelling/cancelled。
- 返回 `ToolAwaitingOutcome` 后 Host 会建立 wait record，但 job 已取消，形成无意义的等待。
- direct callable 不经过 legacy adapter，可以直接返回 `ToolCancelledOutcome`。

Plan 不需要修改，implementation agent 按此路径实现即可。

### F-05: Slice 1 "executor.submit 前 checkpoint" 的实现细节需注意线程安全

**严重性**: low
**状态**: accepted
**位置**: plan §8 Slice 1, line 160-162

**问题**: plan 要求在 `_create_queued_job` 后、`executor.submit` 前做 token checkpoint。但 `start_download` / `start_preprocess` 方法内部的 `_create_queued_job` 和 `executor.submit` 是同步调用，中间没有 await 点。token checkpoint 如果是同步检查 `token.is_cancelled()` 则没问题；如果是异步检查则需要确认上下文。

**证据**: `ingestion_runtime.py:1008-1051` 的 `start_download` 是同步方法，无 await 点。`CancellationToken.is_cancelled()` 是同步方法（Engine design §13）。

**建议**: 使用同步 `token.is_cancelled()` 即可，无需 async checkpoint。plan 未明确是 sync 还是 async checkpoint，implementation 时需注意。Plan 不需要修改。

### F-06: Plan §6 两阶段启动评估的 residual risk R1 描述需补充 mitigation 时效

**严重性**: info
**状态**: accepted
**位置**: plan §11, R1

**问题**: R1 说 "awaiting accept 前 orphan job 窗口无法被 token checkpoint 完全关闭"。Plan 的 mitigation 是 "start 前/后 checkpoint 与 durable cancel bridge"。但未明确该 mitigation 能关闭多少比例的 orphan 窗口。

**分析**: 
- start 前 checkpoint：如果 token 在 job 创建前已取消，不创建 job → 完全关闭该路径。
- start 后 checkpoint：如果 token 在 job 创建后、awaiting accept 前取消，立即 request_cancel → job 进入 cancelling，但 Host wait record 尚未建立，wait adapter 无法 poll 收口。此时 orphan 窗口 = job 已创建但未被 Host 接受的时间窗口。
- 实际 mitigation：job 进入 durable cancelling 后，即使 Host 未 accept，下次任何 poller 或 cleanup 看到该 job 也会收口。所以 orphan 窗口的实际风险是 "job 已取消但 Host 不知道"，而非 "job 永远不会被取消"。

**建议**: plan 不需要修改。implementation report 应记录该 mitigation 的实际覆盖范围。

### F-07: 测试覆盖 — Slice 4 Fins read tools 至少 9 个工具，plan 只列了 4 个测试场景

**严重性**: low
**状态**: accepted
**位置**: plan §8 Slice 4 Tests

**问题**: plan 要求为 9 个 Fins read tools 注入 execution context，但测试只列了 4 个场景（`list_documents`、`search_document`、`read_section`、`query_xbrl_facts`）。其余 5 个工具（`get_document_sections`、`list_tables`、`get_table`、`get_page_content`、`get_financial_statement`）的 context 注入测试未列出。

**分析**: plan 在 §9 提到 "provider declaration tests assert all Fins read declarations have execution context injection metadata"，这可以覆盖所有 9 个工具的声明级断言。行为级测试只列了 4 个代表性场景，合理——不需要为每个工具都写独立的 cancel 测试。

**建议**: implementation 时，provider declaration test 应断言所有 9 个工具都有 `execution_context_param_name`。行为测试按风险类（list/search/read/query）各选一个代表即可。Plan 不需要修改。

### F-08: Plan §8 Slice 5 "source-level guard tests" 的标准需明确

**严重性**: info
**状态**: accepted
**位置**: plan §8 Slice 5

**问题**: plan 说 "Add source-level guard tests only if behavior tests cannot directly observe a boundary; prefer behavior tests。" 这是正确的原则，但 implementation agent 可能不确定何时需要 source-level guard。

**建议**: implementation 时，优先用 behavior test（mock token、触发 cancel、断言 outcome）。只有当某个 checkpoint 无法通过 behavior test 触发时（例如内部循环的中间 checkpoint），才考虑 source-level guard。Plan 不需要修改。

---

## Design Alignment Summary

| 设计约束 | Plan 对齐 | 备注 |
|---|---|---|
| Host 是 cancel 治理真源 | ✅ | Plan 只让工具观察 Host token，不创建工具私有 cancel 状态 |
| Fins job cancel 真源在 job store | ✅ | 复用 `request_cancel`，不新增状态机 |
| Engine 不拥有工具治理 | ✅ | 变更在 ToolRuntime / tool callable 层 |
| 财报文档存取通过 `dayu.fins.storage` | ✅ | Plan 不绕过仓储 |
| 不改 Host/Engine public contract | ✅ | 只新增工具内部可选参数 |
| 不改 legacy adapter-wide contract | ✅ | 只用已有 `execution_context_param_name` |
| `execution_context` 不暴露给 LLM | ✅ | 非 LLM-facing schema 参数 |

## Scope / Over-Design Assessment

- **无过度设计**: plan 未新增 Host/Engine contract、未新增 durable schema、未新增状态机。按工具风险分级加 checkpoint，最小化变更。
- **无 scope 膨胀**: non-goals 清晰，两阶段启动明确 deferred，不伪装成 bug fix。
- **无缺失**: 4 个 implementation slices + 1 个 audit/validation slice 覆盖所有已迁移工具族。

## Residual Risks / Uncovered Areas

| ID | 风险 | Owner / Destination |
|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口：job 可能已 submit 但 Host 未 accept。Mitigation：start 后立即 request_cancel，job 进入 durable cancelling，下次 poller 收口。 | WU-WAIT-03 或 WU-TOOLS-01-F01-02-follow-up |
| R2 | synchronous `requests` / filesystem / processor 调用无法被 token 强制中断。 | 当前 WU implementation report 记录 |
| R3 | Legacy adapter 把 cancellation 投影为 `ToolFailedOutcome` 而非 `ToolCancelledOutcome`。 | 后续独立 tool adapter contract WU |
| R4 | Fins read runtime 内部 search/XBRL helper 深层 checkpoint 需 implementation 时裁决。 | 当前 WU implementation owner |

## Gate Decision

**Plan is code-generation-ready. No blocking findings.**

- F-04 (medium) 为 accepted finding，implementation agent 按 direct callable 返回 `ToolCancelledOutcome` 路径实现即可。
- 其余 findings 均为 low/info，implementation 时逐一对齐。
- Plan 可进入 implementation gate。
