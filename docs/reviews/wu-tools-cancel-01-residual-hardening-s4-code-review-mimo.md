# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `98cdc872` (WU-TOOLS-CANCEL-01: accept residual hardening S3)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-code-review-mimo.md`
- Included scope: workspace unstaged changes since `98cdc872`，即 S4 `Docs, Control State, And Final Validation` slice 的三个 changed files 和一个 untracked implementation artifact。
- Excluded scope: S1/S2A/S2B/S3 已 accepted 的 production/test code changes；untracked `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md` 为 implementation artifact，非 production code。
- Parallel review coverage: 无。

## Findings

### 1-未修复-中-Fins README 缺少结构化 hint 字段说明，S3 行为变更未被文档覆盖

- **入口/函数**: `dayu/fins/README.md` 的"Read tool 结果与截断"章节（约 L690-692）
- **文件(行号)**: `dayu/fins/README.md:690-692`
- **输入场景**: 开发者阅读 Fins README 以了解 process-backed read tools 失败时的 envelope 行为。
- **实际分支**: S4 implementation 判断 `dayu/fins/README.md` 不需要更新（`docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md:26-27`："checked; no new change needed because current Fins README already describes read tools as process-backed, explains process target serialization boundaries, and no S4 change alters Fins behavior beyond tests."）。
- **预期行为**: S3 将 Fins process target 从"hint 拼入 message"迁移到 `dayu.contracts` 结构化 envelope helper，failed envelope 的 `hint` 现在是独立字段，由 Host 映射为 `ToolResultFailure.hint`。Fins README 作为 Fins 包的开发手册，应反映该行为变更，使开发者知道 Fins process target 不再需要自行拼接 hint 到 message。`dayu/host/README.md:373` 已明确记录"failed 信封的 `hint` 会映射到结构化 `ToolResultFailure.hint`，不拼入 `message`"，Fins README 应保持一致。
- **实际行为**: Fins README 的"Read tool 结果与截断"章节（L690-692）只提到 process-backed 执行边界和 ToolRuntime 治理，未提及 envelope 字段、hint 结构化映射或 `dayu.contracts` helper。Fins README 全文无 `hint` 出现（grep 确认）。
- **直接证据**:
  - `dayu/fins/README.md:690-692`：只说"生产默认执行由 ToolRuntime 根据 `ToolDefinition.execution` 进入 process-backed 边界"，未提 envelope 字段。
  - `dayu/host/README.md:373`：已记录结构化 hint 映射。
  - `dayu/README.md:175`：已记录 `dayu.contracts` envelope helper。
  - S3 diff（已 accepted）：Fins tools 迁移到 `dayu.contracts` envelope helper，不再拼接 hint 到 message。
- **影响**: 开发者阅读 Fins README 时会误认为 Fins process target 仍自行拼接 hint 到 message，与 Host README 和 dayu/README 的描述不一致。不会导致 runtime 行为错误，但会造成文档层面的事实不一致。
- **建议改法和验证点**:
  - 在 `dayu/fins/README.md` 的"Read tool 结果与截断"章节补充：Fins process target 使用 `dayu.contracts` envelope helper 构造完成/失败信封；failed envelope 的 `hint` 为独立结构化字段，由 Host 映射为 `ToolResultFailure.hint`，不拼入 `message`。
  - 验证：更新后 grep `dayu/fins/README.md` 确认 `hint` 出现且描述与 Host README 一致。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中——文档不一致不会导致 runtime 错误，但 process-backed envelope 是本次 residual hardening 的核心契约之一，三个 README（dayu/README、host/README、fins/README）应保持一致。

## Open Questions

- 无。

## Residual Risk

- Fins README 的 `hint` 字段文档缺失（Finding 1）是一个文档覆盖 gap，源自 S3 行为变更未被 S4 docs judgment 覆盖。不影响 runtime correctness，但需要补充以保持跨 README 一致性。
- S4 implementation artifact 引用了额外 evidence checks（`test_import_boundary.py`、`test_tool_declaration.py`），这些不在 S4 plan 的 validation commands 中但增强了置信度。artifact 正确记录了这些检查的来源和结果。
- S4 plan 要求的 validation commands 全部被 S4 implementation artifact 覆盖，且扩展到 import-boundary 和 contracts declaration 测试。AgentCodex reported validation 结果与 artifact 记录一致。

## Review Summary

S4 的三个 changed files 和一个 implementation artifact 整体准确：

1. **`dayu/README.md`**：新增 `process_tool_completed_envelope(...)` / `process_tool_failed_envelope(...)` / `parse_process_tool_envelope(...)` 条目，措辞准确表达 public contract 边界（"只表达子进程完成或失败结果，不进入 LLM-facing tool schema，也不承载 Host cancel / timeout / awaiting 状态机"），符合 dayu/README 的 Agent 更新约束。
2. **`dayu/host/README.md`**：ToolRuntime 段落准确更新 process-backed envelope 来源（`dayu.contracts`）、hint 结构化映射和 schema 边界，符合 host/README 的 Agent 更新约束。
3. **`docs/host/issues-implementation-control.md`**：gate 从 `implementation` 更新为 `implementation completed`，next entry point 更新为 `aggregate / final review`，WU-TOOLS-CANCEL-01 status 更新为 `implementation completed`。未提前写 final-closeout-pass，未改 PR/issue 状态。控制状态准确。
4. **S4 implementation artifact**：记录了完整的 validation matrix（Host tests 89、runtime 19、Web 34/1 skip、Fins 33、Service 52、pyright 0 errors、import-boundary 25、contracts 10、git diff --check），grep 证据确认无重复 envelope 常量、无残留 magic constants。residual risk 归属准确（live browser Chromium cleanup 环境依赖、Web cold-start 性能延迟）。

**结论: PASS_WITH_FINDINGS** — Finding 1 为文档覆盖 gap，需 controller 裁决是否在当前 slice 补充或作为 follow-up。
