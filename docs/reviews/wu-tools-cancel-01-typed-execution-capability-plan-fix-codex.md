# WU-TOOLS-CANCEL-01 Typed Execution Capability Plan Fix — AgentCodex

## Artifact

- **Agent**: AgentCodex
- **Gate**: fix
- **Plan under fix**: `docs/host/wu-tools-cancel-01-typed-execution-capability-plan.md`
- **Review inputs**:
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-ds.md`
  - `docs/reviews/wu-tools-cancel-01-typed-execution-capability-plan-review-mimo.md`
- **Allowed scope**: plan artifact 与本 fix report

## Scope Control

本次只修改 plan 文档并新增 fix report；未修改生产代码、测试、总控文档或设计文档。

Preflight：

- Branch: `phase/wu-tools-cancel-01`
- Dirty scope before fix: plan 与两份 review artifact 均为未跟踪文档，落在本次文档 gate 范围内

## First-principles Judgment

accepted findings 的动机成立。原 plan 的核心方向正确：execution capability 应作为 `ToolDefinition` 公共契约进入 `dayu.contracts`，Host 从声明同源选择 capsule，Engine 不消费 capability。

但原 plan 对 process-backed 的返回契约、context 投影和 S1 runtime `JsonValue` 边界留下二义性，会把实现决策推迟到 S2A，增加返工风险。因此本次 fix 不改变总体方向，只收窄契约、拆小基础设施 slice，并把 stop / validation 条件写入 plan 本体。

## Fix Summary

- **DS F01 / MiMo**: 将 `ProcessBackedToolTarget.__call__` 从返回 `ToolExecutionOutcome` 改为返回 `JsonValue` JSON 信封；明确子进程只允许表达 completed / failed，`awaiting`、`cancelled`、`host_cancelled`、approval、timeout 均不得由子进程返回。
- **DS F02 / MiMo**: 增加 `ProcessBackedToolContext` 草案，Host 从 `BatchToolExecutionContext` 投影出可序列化字段后再调用 factory；明确排除 `cancellation_token`、lock、runtime、repository、session 与 Host internals。
- **DS F03 + MiMo M01/M02**: 明确选择与 S1 `InterruptibleProcessTarget.__call__() -> JsonValue` 对齐的方案；删除“允许扩展 `dayu.runtime.interruptible_process` 返回 `ToolExecutionOutcome`”的方向，改为 Host capsule 解析 JSON 信封并映射 tool outcome。
- **DS F04**: 将 S2A 拆成 `S2A1: contract / declaration / digest` 和 `S2A2: Host factory wiring`，并分别写入 stop condition。
- **DS F07**: 补全直接 `ToolDefinition` 构造站点要求，至少覆盖 `dayu/fins/tools/download_tools.py`、`upload_tools.py`、`preprocess_tools.py`、`dayu/host/tool_runtime.py` framework `fetch_more`，并要求用 `rg -n "ToolDefinition\\(" dayu tests` 扫描全量构造站点。
- **DS F05/F06/F08/F09/F10/F11 + MiMo M03**: 将 provider lock 语义、thread_backed guard、Fins spawned-child pre-check、digest JSON shape、Web async_direct close 标准、timeout 父进程归属、pickle round-trip 纳入 plan 的 process entrypoint、validation matrix、stop conditions 与 residual risks。

## Validation

- `git diff --check`: PASS

## Decision

Plan fix 已覆盖 controller accepted findings；可进入 re-review。
