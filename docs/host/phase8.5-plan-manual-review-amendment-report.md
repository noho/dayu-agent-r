# P8.5 Plan Manual Review Amendment Report

- **work gate name**: manual-review amendment
- **work-unit name**: P8.5 — P8 Stabilization / ToolRuntime Event Model
- **amended plan path**: `docs/host/phase8.5-plan.md`
- **artifact path**: `docs/host/phase8.5-plan-manual-review-amendment-report.md`

## Scope

本轮根据用户人工 review 意见修正 plan / migration registry，不进入 implementation，不改生产代码或测试代码。

Changed files:

- `docs/host/phase8.5-plan.md`
- `docs/host/migration-plan.md`

## Amendments

### A1 — Corrupt snapshot row root-cause research

- P8.5 Slice 2 仍固定 immediate behavior：snapshot row 存在但 payload corrupt / schema mismatch / type invalid 时，不自动覆盖；返回 typed diagnostic，记录 WARNING，继续其它 session repair。
- 根因研究与长期 repair policy 不在 P8.5 直接裁决，已创建 GitHub issue #41：
  `https://github.com/noho/dayu-agent-r/issues/41`
- Plan 与 migration registry 已把该问题拆分为：
  - P8.5 Slice 2：capacity helper + typed diagnostic + WARNING + no automatic overwrite。
  - GitHub issue #41：为什么会产生 corrupt row、是否需要运维手工介入、是否需要 quarantine / operator command / 自动覆盖策略。

### A2 — Trace analyzer must follow trace schema changes

- `utils/analyze_tool_trace_host.py` 与 `tests/utils/test_analyze_tool_trace_host.py` 已加入 P8.5 affected files。
- Slice 3 明确要求 analyzer 随 generic tool-call trace schema 更新。
- Analyzer 必须继续提供 truncate / `fetch_more` 相关错误诊断，包括 truncation 未续读、`fetch_more` unknown cursor / wrong scope、重复 `fetch_more`、tool failure patterns 与 provider protocol failure。
- Slice 3 validation 增加 `pytest tests/utils/test_analyze_tool_trace_host.py -q`。

### A3 — SSE partial diagnostic analyzer visibility

- Slice 4 明确：SSE partial tool-call diagnostic 的主要人工验收入口是 `utils/analyze_tool_trace_host.py`。
- 当 SSE 中途失败且已有 bounded partial tool-call summary 时，trace/analyzer 输出必须能显示该 summary。
- partial summary 不驱动 tool execution，不进入 memory。
- Slice 4 validation 增加 analyzer 测试与 expected assertion。

## Validation

未运行 pytest / pyright；本轮只改 plan / migration 文档。

Manual checks performed:

- `rg "#41|analyze_tool_trace_host|partial tool-call|corrupt snapshot|WARNING|GitHub issue" docs/host/phase8.5-plan.md docs/host/migration-plan.md`
- `git diff -- docs/host/phase8.5-plan.md docs/host/migration-plan.md`

## Open Questions

No blocking open questions.
