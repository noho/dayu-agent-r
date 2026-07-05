# Code Review — S4 Targeted Re-Review

## Scope

- Mode: current changes (targeted re-review of S4 review fixes)
- Branch: `phase/wu-tools-cancel-01`
- Base: `98cdc872` (WU-TOOLS-CANCEL-01: accept residual hardening S3)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s4-rereview-mimo.md`
- Included scope: workspace changes addressing three accepted review findings:
  - MiMo-01 MEDIUM: Fins README 缺少 structured hint / `dayu.contracts` envelope helper 说明
  - DS-01 LOW: control doc gate/status 使用未定义的 `implementation completed`
  - DS-02 LOW: S4 artifact 对 Fins/tests README 决策缺少直接证据
- Excluded scope: S1/S2A/S2B/S3 production/test code; unchanged files from initial S4 review
- Parallel review coverage: 无。

## Findings

未发现实质性问题。三项 accepted fixes 均验证通过。

---

## Fix Verification

### MiMo-01 (中): Fins README 新增 structured hint / envelope helper 说明 — 已修复 ✓

**变更**: `dayu/fins/README.md:692` 新增一句：
> Fins process target 使用 `dayu.contracts` 的 process-backed envelope helper 构造 completed / failed 信封；failed 信封的 `hint` 是结构化字段，由 Host 映射为 `ToolResultFailure.hint`，不得拼接进 `message`。

**准确性验证**:

| 声明 | 代码证据 | 结论 |
|---|---|---|
| "使用 `dayu.contracts` 的 process-backed envelope helper" | `dayu/contracts/tool_execution.py:86,99,125` 定义 helpers；`dayu/fins/tools/fins_tools.py:25-26` 通过 `dayu.contracts` import；grep 确认无本地 `_FINS_PROCESS_*` 常量残留 | ✓ |
| "`hint` 是结构化字段" | `dayu/contracts/tool_execution.py:100,120-121`: `hint: str \| None`，仅 non-None/non-blank 时写入信封 | ✓ |
| "由 Host 映射为 `ToolResultFailure.hint`" | `dayu/host/tool_runtime.py:6582-6586`: `_tool_outcome_from_process_envelope` → `_tool_failed_outcome(hint=parsed.hint)` → `ToolResultFailure(hint=hint)` (L7359) | ✓ |
| "不得拼接进 `message`" | grep 确认 `dayu/fins/tools/fins_tools.py` 中 hint 与 message 为独立字段，无拼接逻辑 | ✓ |

**Fins README Agent 更新约束合规性**:
- "只写当前代码已实现的能力" ✓ — envelope helpers 已实现并在 Fins process targets 中使用
- "代码真源高于历史 plan" ✓ — 描述与代码一致
- "不写未来计划" ✓ — 无未来承诺
- 新增文本位于已有的 "Read tool 结果与截断" 章节（该章节已描述 process-backed 执行边界和 ToolRuntime 治理），未扩展 README 职责边界 ✓
- 无过度承诺：不声称 Fins 拥有 envelope contract、不承诺未来能力 ✓

**与 Host README / dayu/README 一致性**:
- Host README L373: "failed 信封的 `hint` 会映射到结构化 `ToolResultFailure.hint`，不拼入 `message`"
- Fins README L692: "failed 信封的 `hint` 是结构化字段，由 Host 映射为 `ToolResultFailure.hint`，不得拼接进 `message`"
- dayu/README L175: "process_tool_completed_envelope(...)、process_tool_failed_envelope(...)、parse_process_tool_envelope(...) 与 process-backed target 类型"
- 角度不同（Host 侧强调映射、Fins 侧强调构造约束、dayu 侧强调公共契约导出），语义一致 ✓

---

### DS-01 (低): Control doc gate/status 使用已定义的 `review` — 已修复 ✓

**变更**: `docs/host/issues-implementation-control.md`:
- `gate` L158: `implementation` → `review`
- WU-TOOLS-CANCEL-01 status L261: `implementation` → `review`

**验证**:

| 检查项 | 证据 | 结论 |
|---|---|---|
| `review` 是已定义的 gate/status 值 | 控制文档状态约定中 `review` 定义为 "正在进行 code review、re-review 或 aggregate deepreview" | ✓ |
| 未提前 claim final-closeout-pass | WU-TOOLS-CANCEL-01 行仍写 "PR #170 不得 mark ready 或 merge，直到 reopened gates 再次到达 final-closeout-pass" | ✓ |
| next entry point 正确 | "Aggregate / final review for WU-TOOLS-CANCEL-01 residual hardening after Slice S4" — review 完成后的下一步 | ✓ |
| 无 stale `implementation completed` 残留 | `grep -n "implementation completed" docs/host/issues-implementation-control.md` 返回空 | ✓ |
| PR/issue 状态未变 | 仍声明 "Keep PR #170 draft"、"Do not mark ready, merge, close #87 directly" | ✓ |

---

### DS-02 (低): S4 artifact 记录 accepted fixes、直接证据和 pytest/pyright 未重跑理由 — 已修复 ✓

**变更**: S4 implementation artifact (`docs/reviews/wu-tools-cancel-01-residual-hardening-s4-implementation-codex.md`) 新增/更新：
- "Changed" 节新增 `dayu/fins/README.md` 更新记录（L20）
- 新增 "Review Fixes" 节（L23-27）记录三项 accepted fixes
- "Docs Decision" 节 Fins README 条目补充直接证据（L33）：章节归属和 S3 行为描述
- "Docs Decision" 节 tests README 条目补充直接证据（L35）：S4 review fixes 未引入新测试文件/夹具/marker/规则
- "Verified" 节新增 "S4 review-fix validation" 子节（L48-52）

**验证**:

| 检查项 | 证据 | 结论 |
|---|---|---|
| Accepted fixes 已记录 | "Review Fixes" 节列出 MiMo-01、DS-01、DS-02 及其修复状态 | ✓ |
| Fins README 直接证据 | "that section already owned Fins read tool schema, Host ToolRuntime truncation, direct callable fallback, and production process-backed execution; the new sentence documents the S3 behavior at the same responsibility boundary" | ✓ |
| tests README 直接证据 | "S4 review fixes changed README/control/artifact text only, introduced no test file, no fixture category, no marker, and no test running rule" | ✓ |
| pytest/pyright 未重跑理由 | "the accepted fixes are README / control / artifact text only and do not change Python code, config schema, tests, or runtime behavior" — 逻辑自洽 | ✓ |
| diff/status validation | `git diff --check`: passed；`git status --short` 列出修改和未跟踪文件，无意外文件 | ✓ |

---

## Docs Consistency 检查

| 检查项 | 结果 |
|---|---|
| Fins README 与 Host README 的 hint 描述是否一致 | ✓ 语义一致（角度不同但无冲突） |
| Fins README 与 dayu/README 的 envelope helper 描述是否一致 | ✓ 均指向 `dayu.contracts` 中的 helper |
| Control doc 是否在任何地方提前 claim final-closeout-pass | ✓ 否；仅描述历史状态和其他 WU |
| S4 artifact 的 review fix 记录是否与 MiMo/DS review finding 匹配 | ✓ MiMo-01、DS-01、DS-02 均有对应 fix 记录 |
| S4 artifact 的 changed files 列表是否与实际 diff 一致 | ✓ dayu/README.md, dayu/fins/README.md, dayu/host/README.md, control doc |
| 是否有 review artifact 路径引用错误 | ✓ 无 |

## Open Questions

无。

## Residual Risk

- 无新增。原 S4 review 的 residual risk（live browser Chromium cleanup 环境依赖、Web cold-start 性能延迟）不变。
