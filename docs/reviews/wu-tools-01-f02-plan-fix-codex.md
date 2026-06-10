# WU-TOOLS-01-F02 Plan Fix

## Gate

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 当前 gate：plan fix
- Fix agent：Codex
- 日期：2026-06-09
- Plan artifact：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- Controller adjudication：`docs/reviews/wu-tools-01-f02-plan-review-controller-adjudication.md`

## Scope

本次只修 plan，不做 implementation、review、commit、push、PR，也不进入 re-review。

已修改：

- `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`

已新增：

- `docs/reviews/wu-tools-01-f02-plan-fix-codex.md`

未修改 implementation code、tests、README、controller artifacts 或 review artifacts。

## Fixed Findings

1. 已明确 sync-to-async bridge：CLI 入口保持同步；只在 current async `ToolDefinition.callable` 边界使用 `asyncio.run(...)`；Playwright 继续使用 sync API 并封装在 optional browser helper；F02 不支持嵌入已有 event loop 的 API。
2. 已明确 raw requests headers 选择规则：优先复用 current Web helper 且不得扩大 production public surface；否则使用本地 diagnostic headers，并在输出中标注 raw diagnostic path。
3. 已补充 CLI args 到 current `WebToolsConfig` / `ToolsDiscoveryProviderSpec.config` 的字段映射和 JSON value 类型，包括未暴露 CLI flag 的 current 默认字段处理。
4. 已明确 batch child process crash 传播：使用 `child_process_error` 或等价非 comparison status，保留 `return_code`、有界 stderr/stdout prefix、`diagnostic_path=null`，并且不混入普通 comparison bucket。
5. 已明确私有 `_DiagnosticCancellationToken`：实现 current `CancellationToken` protocol，采用 never-cancelled semantics。
6. 已消除 `discover_tools` 歧义：指定使用 `dayu.tools.web.provider.discover_tools(spec)` 或等价 provider entry，读取 `ToolsDiscoveryProviderOutput.definitions`，不得使用 runtime aggregate discovery。
7. 已说明 deterministic tests 的必要性：parser、classifier、current-contract adapter 逻辑非平凡且会产出 F03 可能消费的 evidence；shell wrapper/corpus 可轻量检查。
8. 已明确 F03 最小稳定 utility schema 子集：`schema_version`、`url`、`comparison_bucket`、per-path `sampled` / `ok` / `elapsed_seconds` / `status` / `error`，schema mismatch behavior 留给 F03。
9. 已补充 comparison bucket deterministic decision tree，覆盖 current outcome shapes、Playwright skip/failure、non-success outcomes 与 batch child process crash。
10. 已保持用户补充授权边界和 `utils/` 强类型 / 中文 docstring 约束；未扩大 F02 scope。

## Validation

计划执行：

```bash
git diff --check
```

未运行 pytest / pyright。原因：本次只修改 plan artifact 并新增 plan fix artifact，没有修改 implementation code、tests 或 README；用户指定此场景不需要 pytest / pyright。

## Blocking Open Questions

无。

## Residual Risk

当前 plan/review artifacts 在工作区中显示为未跟踪文件；`git diff --check` 对未跟踪文件不产生内容 diff。后续 accepted-plan commit 前应由提交方确认新增 artifact 已纳入提交范围。
