# WU-TOOLS-01-F01-02-R3 PR Review — AgentMiMo

## Scope

- Mode: PR Review
- PR: https://github.com/noho/dayu-agent-r/pull/135
- Title: WU-TOOLS-01-F01-02-R3 retire legacy tool adapter
- Author: noho
- Head: phaseflow/wu-tools-r3-f08
- Base: main
- Review date: 2026-06-10
- Output file: `docs/reviews/wu-tools-01-f01-02-r3-pr-review-mimo.md`

## PR Diff Overview

PR diff 包含 22526 行，涵盖以下类别：

| 类别 | 文件数 | 说明 |
|---|---|---|
| 生产代码 | 12 | Doc/Web/Fins provider、tools、read_runtime、search_engine、runtime helper |
| 删除文件 | 8 | `dayu/tools/_legacy_adapter/**` 全部删除 |
| 测试代码 | 8 | 新增 projection tests、更新 provider tests、删除 legacy adapter tests |
| Plan / review artifacts | 30+ | R3 plan、各 Slice 实现/review/rereview/controller adjudication、aggregate deepreview 全套 |
| 控制文档 | 1 | `docs/host/issues-implementation-control.md` 状态更新 |
| README | 2 | `dayu/fins/README.md`、`tests/README.md` |

## PR Body Accuracy

PR body 准确描述了三项核心变更：

1. ✅ Retires `dayu/tools/_legacy_adapter` and migrates Doc, Web, and Fins read tools to native `ToolDefinition` / `ToolCallable` providers.
2. ✅ Fixes Host cancellation projection so migrated read tools return `ToolCancelledOutcome(host_cancelled)` instead of legacy `ToolFailedOutcome(error="tool_cancelled")`.
3. ✅ Removes WU-TOOLS-01-F04/F05/F06/F07 from the host control doc; SEC/Fins plus CN/HK Docling CI pipeline/smoke ownership remains with GitHub Issues 121 and 122.

Validation 部分与实际验证一致。

## PR Diff vs Local Accepted R3 Scope

核对 PR diff 与本地 accepted R3 scope：

| 检查项 | 结果 |
|---|---|
| R3 plan artifact (`docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`) | ✅ 在 PR diff 中 |
| Slice 0 implementation + code review + fix + rereview artifacts | ✅ 全部在 PR diff 中 |
| Slice 1 implementation + code review + fix + rereview artifacts | ✅ 全部在 PR diff 中 |
| Slice 2 implementation + code review + fix + rereview artifacts | ✅ 全部在 PR diff 中 |
| Slice 3 implementation + code review + fix + rereview artifacts | ✅ 全部在 PR diff 中 |
| Slice 4 implementation + code review + fix + rereview artifacts | ✅ 全部在 PR diff 中 |
| Aggregate deepreview + fix + rereartifacts | ✅ 全部在 PR diff 中 |
| Controller adjudication artifacts | ✅ 全部在 PR diff 中 |
| 总控 `issues-implementation-control.md` 状态更新 | ✅ gate → PR review，active WU → R3，next entry point → PR review gate |

无遗漏 pushed commit，无 PR-only drift。

## Legacy Adapter Deletion

| 检查项 | 结果 |
|---|---|
| `dayu/tools/_legacy_adapter/` 目录 | ✅ 全部 8 个文件以 `deleted file mode 100644` 删除 |
| `tests/tools/test_legacy_tool_adapter.py` | ✅ 以 `deleted file mode 100644` 删除 |
| 生产代码中 `_legacy_adapter` 引用 | ✅ 无残留（rg 验证） |
| 测试代码中 `_legacy_adapter` 引用 | ✅ 无残留（rg 验证） |
| `LegacyToolDeclarationCollector` 引用 | ✅ 无残留 |
| `adapt_collected_tools` 引用 | ✅ 无残留 |
| `ToolBusinessError(code="tool_cancelled")` 生产代码引用 | ✅ 无残留 |

## Cancellation Outcome Fix

| 工具域 | 旧行为 | 新行为 | 验证 |
|---|---|---|---|
| Doc | `ToolBusinessError(code="tool_cancelled")` → `ToolFailedOutcome(error="tool_cancelled")` | `host_cancelled_outcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` | Doc provider tests 断言 `ToolCancelledOutcome` |
| Web | `ToolBusinessError(code="tool_cancelled")` → `ToolFailedOutcome(error="tool_cancelled")` | `host_cancelled_outcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` | Web provider tests 断言 `ToolCancelledOutcome` |
| Fins read | `ToolBusinessError(code="tool_cancelled")` → `ToolFailedOutcome(error="tool_cancelled")` | `host_cancelled_outcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED)` + `FinsReadCancelledError` | Fins provider tests 断言 `ToolCancelledOutcome` |

三个域的 `host_cancelled_outcome` 均携带 `ToolResultMeta(tool_name, started_at, finished_at)`，meta 不含 Host governance 字段。

## Schema Boundary

| 检查项 | 结果 |
|---|---|
| Doc 工具 schema 不含 `execution_context` / `cancellation_token` | ✅ |
| Web 工具 schema 不含 `execution_context` / `cancellation_token` | ✅ |
| Fins read 工具 schema 不含 `execution_context` / `cancellation_token` | ✅ |
| 工具名称未改变 | ✅ |
| LLM-facing 参数字段、required、enum、description 未改变 | ✅ |
| Truncate specs 保持 | ✅ |

## Doc / Web / Fins Cancellation and Schema 符合 Aggregate Re-Review

- Doc: `_DocToolArgumentError` 为 Doc-local 类型，不从 legacy adapter 导入。取消通过 `host_cancelled_outcome` 返回。
- Web: `ToolBusinessError` 为 Web-local 类型（定义在 `web_tools.py` 内），不从 legacy adapter 导入。取消通过 `host_cancelled_outcome` 返回。
- Fins: `FinsReadArgumentError` / `FinsReadBusinessError` / `FinsReadCancelledError` 为 Fins-local 类型（定义在 `read_runtime_helpers.py` 内），不从 legacy adapter 导入。取消通过 `FinsReadCancelledError` → `host_cancelled_outcome` 返回。

## Control Doc Bookkeeping

| 检查项 | 结果 |
|---|---|
| gate 状态更新为 `PR review` | ✅ |
| implementation status 记录 draft PR 135 URL | ✅ |
| active work unit 更新为 `WU-TOOLS-01-F01-02-R3` | ✅ |
| next entry point 更新为 PR review gate | ✅ |
| R3 work unit 行记录 plan/slice/deepreview commits 和 PR URL | ✅ |
| F04-F07 条目已从 work units 表移除 | ✅（rg 验证 0 命中） |
| F04-F07 在 residual risk 表中无残留 | ✅ |
| default next work unit 更新为 F08 | ✅ |

## Runtime Helper (`dayu/runtime/tool_call_projection.py`)

新增层中立 runtime helper，仅依赖标准库与 `dayu.contracts`：

- `validate_and_project_arguments()` — 参数 schema 校验
- `completed_outcome()` / `failed_outcome()` / `host_cancelled_outcome()` — outcome 构造
- `ToolArgumentValidationFailure` — 参数校验失败 typed result
- 不导入 Host / Engine / Service / UI / Fins / Doc / Web

符合 R3 plan Slice 0 设计约束。

## Adversarial Failure Pass

| 风险面 | 结果 |
|---|---|
| 取消 exception 逃逸到 ToolRuntime 通用异常归一化 | ✅ Doc/Web/Fins 三个域均在 callable 边界内捕获取消并返回 cancelled outcome，不抛出 cancellation exception |
| 阻塞 IO 前未检查 token | ✅ 三个域均在进入 provider_lock 前和 `asyncio.to_thread` 前检查 `is_cancelled()` |
| Provider lock 不当共享或不共享 | ✅ 每个 `build_*_tool_definitions()` 函数内创建一把 `asyncio.Lock()`，同域 callable 共享 |
| Fins storage 边界被绕过 | ✅ Fins read 仍通过 `DefaultFinsRuntime` → `FinsReadRuntime` → storage 仓储边界 |
| `del cancellation_token` 模式 | ℹ️ `_cancelled_from_token` 和 `raise_fins_cancelled` 接受 token 参数后立即 `del`；调用方已检查 `is_cancelled()`，token 仅为未来扩展保留参数位，`del` 避免 linter 警告。非功能问题。 |
| PR diff 包含不相关变更 | ✅ PR diff 中的 docs/reviews/ 文件均为 R3 流程 artifact，plan 也在 diff 中，属 bookkeeping 范围 |

## Open Questions

无。

## Residual Risk

- Web live / real network smoke 未在本次 PR 中运行，仍由 GitHub Issues #121 / #122 追踪。PR body 已记录。
- Physical interruption of already-running synchronous HTTP/browser work 仍 deferred to WU-WAIT-03 / GitHub Issue #92。PR body 已记录。

## Conclusion

未发现实质性问题。

PR diff 与本地 accepted R3 scope 完全一致：Slice 0-4 实现、plan、deepreview、bookkeeping 全部包含。Legacy adapter 已完整删除，生产/测试代码无残留引用。Cancellation outcome 修复正确覆盖 Doc/Web/Fins 三个域。Schema 边界保持不变。总控文档已更新至 PR review gate 状态，F04-F07 已移除。所有验证命令（pytest 115 passed、pyright 0 errors、git diff --check、rg legacy symbols）已通过。

**Verdict: PASS**
