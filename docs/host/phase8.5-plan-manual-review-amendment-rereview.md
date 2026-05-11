# P8.5 Plan Manual Review Amendment Re-Review

- **review gate name**: manual-review amendment re-review
- **reviewed target**: `docs/host/phase8.5-plan.md`
- **source amendment artifact**: `docs/host/phase8.5-plan-manual-review-amendment-report.md`
- **related artifacts**:
  - `docs/host/phase8.5-plan-review.md`
  - `docs/host/phase8.5-plan-fix-report.md`
  - `docs/host/phase8.5-plan-rereview.md`
- **source-of-truth docs**:
  - `docs/host/design.md`
  - `docs/host/migration-plan.md`
- **work-unit name**: P8.5 - P8 Stabilization / ToolRuntime Event Model
- **artifact path**: `docs/host/phase8.5-plan-manual-review-amendment-rereview.md`
- **reviewer conclusion**: **pass**

## Scope

本轮只 re-review 用户人工 review 后的 plan amendment 是否正确、是否引入 blocker。未修改 plan、生产代码、测试代码，
未进入 implementation、commit、PR 或 closeout。

## Summary

- Finding 数量：0。
- Blocking open questions：0。
- 结论：pass。

## Amendment Verification

### 1. Corrupt snapshot row root-cause research

- **evidence**:
  - `docs/host/phase8.5-plan.md:152-158` 固定 P8.5 immediate behavior：missing row 自动修复；corrupt snapshot
    row 不自动覆盖；返回 typed diagnostic 并记录 WARNING；根因研究由 GitHub issue #41 跟踪。
  - `docs/host/phase8.5-plan.md:499-507` 在 Slice 2 implementation instructions 中要求新增 typed diagnostic，
    corrupt / schema mismatch / type invalid row 不覆盖，继续其它 session repair；若 implementation 发现 corrupt
    row 可由当前写路径正常产生，必须 stop and report。
  - `docs/host/phase8.5-plan.md:896-897` 将 immediate behavior 归属 P8.5 Slice 2，将 root-cause /
    long-term repair policy 归属 GitHub issue #41。
  - `docs/host/migration-plan.md:141` 记录 split-owner：P8.5 做 typed diagnostic + WARNING + no overwrite，
    issue #41 研究运维介入和长期 policy。
  - `gh issue view 41` 确认 issue #41 存在且 open，标题为 “Investigate corrupt durable memory snapshot row origin
    and repair policy”，body 明确不阻塞 P8.5 typed diagnostic + WARNING 行为。
- **judgment**: pass。该 amendment 保留了 P8.5 的保守 immediate behavior，同时把用户挑战的 root-cause /
  long-term policy 移入可追踪 issue；未把 research 留给 implementation agent 自行决定。

### 2. Trace analyzer coverage for truncate / fetch_more diagnostics

- **evidence**:
  - `docs/host/phase8.5-plan.md:286-290` 将 `utils/analyze_tool_trace_host.py` 与
    `tests/utils/test_analyze_tool_trace_host.py` 纳入 trace / memory affected files。
  - `docs/host/phase8.5-plan.md:177-180` 明确 analyzer 必须随 trace schema 调整，并继续从 ordinary tool payload /
    trace record 识别 truncation 未续读、`fetch_more` unknown cursor / wrong scope、重复 `fetch_more`、失败 outcome
    与 provider partial 诊断。
  - `docs/host/phase8.5-plan.md:548-564` 在 Slice 3 allowed files 与 implementation instructions 中要求更新
    analyzer，不得依赖旧 `TOOL_RESULT_TRUNCATED` / `TOOL_CURSOR_*` 专属字段。
  - `docs/host/phase8.5-plan.md:579-593` 将 `pytest tests/utils/test_analyze_tool_trace_host.py -q` 加入 Slice 3
    validation，并把 truncation / `fetch_more` 错误诊断作为 expected assertion。
- **judgment**: pass。用户要求的 analyzer 跟随 trace schema 变化已成为 Slice 3 实施与验收条件。

### 3. SSE partial tool-call diagnostic analyzer visibility

- **evidence**:
  - `docs/host/phase8.5-plan.md:206-210` 明确 SSE partial tool-call diagnostic 是 Engine-owned diagnostic data、
    Host-owned persistence；主要验收入口是 `utils/analyze_tool_trace_host.py`；summary 不驱动 tool execution，
    不进入 memory。
  - `docs/host/phase8.5-plan.md:621-624` 将 `utils/analyze_tool_trace_host.py` 纳入 Slice 4 allowed files。
  - `docs/host/phase8.5-plan.md:655-660` 要求 provider/protocol failure data 增加 bounded
    `partial_tool_calls` summary，并要求 analyzer 在 `provider_protocol_error` 报告中展示该 summary。
  - `docs/host/phase8.5-plan.md:664-679` 将 analyzer test 纳入 Slice 4 validation，并要求输出中可见 bounded
    partial tool-call summary。
  - `docs/host/migration-plan.md:156` 将 “SSE 中途失败导致 partial tool call 缺少完整 trace 语义” 的主要验收入口
    记录为 analyzer 可显示 bounded partial tool-call summary。
- **judgment**: pass。amendment 把用户的真实目标收敛成明确验收信号：人工通过 analyzer 看到 SSE partial summary，
  且该 summary 不进入 execution / memory。

### 4. Prior F01-F07 fixes and design / payload policy consistency

- **evidence**:
  - `docs/host/phase8.5-plan.md:122-136` 仍保留 F01 的 Host-private schema provider / Engine-visible schemas
    投影裁决。
  - `docs/host/phase8.5-plan.md:138-148` 仍保留 F02 的 memory / RunInput capability ingestion policy。
  - `docs/host/phase8.5-plan.md:180-198`、`:628-646` 仍保留 F04 的 RunInput raw payload side-store schema、
    writer / reader owner 与 transaction 边界。
  - `docs/host/phase8.5-plan.md:167-175`、`:565-575` 仍保留 F06 的 non-required trace sink at-least-once /
    checkpoint 语义。
  - `docs/host/design.md:1173-1195` 与 `docs/host/migration-plan.md:46-49` 均保持 local-agent payload policy：
    EventLog / trace ordinary payload 默认保留，只窄 scrub `API_KEY` / 明确凭证；cursor / `scope_token` 不因字段名被遮蔽。
- **judgment**: pass。manual-review amendment 没有破坏前次 F01-F07 fix，也没有回退新版 design / payload policy。

## Findings

No findings.

## Open Questions And Residual Risk

- Blocking open questions: none.
- Non-blocking note: `docs/host/migration-plan.md` 的当前 gate 状态仍由 controller 在下一次 accepted plan checkpoint
  前统一更新更合适；该状态文字不影响本次 amendment 的 handoff readiness。

## Conclusion

本次 manual-review amendment 正确吸收用户三条人工 review 意见，且未引入 blocker。P8.5 plan 可回到 user
confirmation / accepted plan checkpoint gate。
