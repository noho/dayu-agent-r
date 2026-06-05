# Code Review

## Scope

- Mode: current changes (design fix re-review)
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-rereview-mimo.md`
- Included scope: `docs/host/design.md`, `docs/host/issues-implementation-control.md`, `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md`, `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-controller-adjudication.md`
- Excluded scope: production code, tests, README — not changed by fix (verified via `git diff main --name-only -- 'dayu/' 'tests/' 'README.md'`)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

四个 accepted findings 的 fix 覆盖验证如下：

### 1. Section 4 / Section 8 evidence routing uniqueness — 已修复

- **入口/函数**: design.md §23 system envelope section table (line 2554) 与 evidence routing 规则 (line 2566)
- **文件(行号)**: design.md:2559, design.md:2563, design.md:2566
- **输入场景**: 任何 evidence material 需要路由到 system envelope section 时
- **实际分支**: §23 table row 4 (`Verified Evidence and Facts`) 明确定义内容来源为 "Evidence / Fact Memory、accepted evidence-backed facts，以及 memory / fact pipeline 已接受的 evidence material"；row 8 (`Recent Evidence`) 明确定义为 "未进入 memory / fact pipeline 的 recent-window fallback、wait-resume 或其它 evidence-like bounded material"
- **预期行为**: 同一条 evidence material 不得同时出现在两个 section
- **实际行为**: line 2566 明确写了 "同一条 evidence material 不得同时渲染到两个 section" 并补充了 pipeline 接受后的路由收敛规则
- **直接证据**: design.md:2566 — "已经作为 verified / accepted memory facts 或 memory / fact pipeline accepted evidence 的材料只能进入 `Verified Evidence and Facts`；未进入 memory / fact pipeline 的 recent-window fallback、wait-resume 或其它 evidence-like bounded material 只能进入 `Recent Evidence`；同一条 evidence material 不得同时渲染到两个 section。若某条 recent material 已被 memory / fact pipeline 接受，后续只能按 accepted memory / fact material 路由，不再按 recent fallback material 路由。"
- **影响**: fix 消除了 controller adjudication Finding 1 的设计歧义，实现 agent 不再需要自行发明路由规则
- **建议改法和验证点**: 无需改法。验证点：S7-R1-S1 实现时 focused tests 必须覆盖同一 evidence material 不会同时出现在两个 section
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 已修复

### 2. `tool` role legality authority — 已修复

- **入口/函数**: design.md selected recent window role preservation 段落 (line 2568)
- **文件(行号)**: design.md:2568
- **输入场景**: selected recent window 中包含 historical evidence，且该 evidence 不能保留为 `user` / `assistant` role
- **实际分支**: design.md 明确声明 "当前 Engine message contract 不支持 ordinary RunInput historical evidence 使用 `tool` role"
- **预期行为**: design 应声明当前 authority 和未来变更路径
- **实际行为**: line 2568 写明 "该选择会把原本夹在历史 user / assistant turn 中间的 evidence 提前到 system envelope 内，是被接受的 trade-off"，并指出 "未来如果 Engine contract 支持 historical evidence 使用 `tool` role，可在后续 work unit 中重新评估"
- **直接证据**: design.md:2568 — "当前 Engine message contract 不支持 ordinary RunInput historical evidence 使用 `tool` role，因此 selected recent evidence 和其它不能作为 `user` / `assistant` role 保留的 historical evidence 默认进入首条 system envelope"
- **影响**: fix 消除了 controller adjudication Finding 2 的 authority 不明确问题
- **建议改法和验证点**: 无需改法
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 已修复

### 3. Boundedness measurable sanity — 已修复

- **入口/函数**: design.md system envelope merge 段落 (line 2585)
- **文件(行号)**: design.md:2585
- **输入场景**: system envelope merge 完成后需要验证总大小
- **实际分支**: design.md 给出了精确的可测断言公式
- **预期行为**: design 应要求可测量的字符数 sanity assertion
- **实际行为**: line 2585 写明 "`len(merged_system_content) <= sum(len(candidate_system_content)) + deterministic_header_separator_overhead`"，并定义 overhead "只包含非空 section 的固定 Markdown header、header 与内容之间的固定换行，以及 section 间固定 separator"
- **直接证据**: design.md:2585 — 完整公式和 overhead 定义
- **影响**: fix 将模糊的 "size sanity" 要求转化为可直接编码和测试的断言
- **建议改法和验证点**: 无需改法。验证点：S7-R1-S1 实现时 focused tests 必须覆盖该断言
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 已修复

### 4. Section title single source — 已修复

- **入口/函数**: design.md §23 section table (line 2552) 与 §24 (line 3054)
- **文件(行号)**: design.md:2552, design.md:3054
- **输入场景**: 实现 agent 需要确定 section title 时
- **实际分支**: §23 明确声明 "下表是 section title、顺序和 Conversation Memory section 映射的唯一真源；其它章节只能引用本表的映射关系，不得重复硬编码完整 title 列表"
- **预期行为**: §24 应引用 §23 而非重复硬编码 title 列表
- **实际行为**: line 3054 写明 "23 节表格是 section title 与映射关系的唯一真源，本文不重复硬编码完整 title 列表"
- **直接证据**: design.md:2552 与 design.md:3054 的 cross-reference
- **影响**: fix 消除了 controller adjudication Finding 4 的维护风险，§23 和 §24 不再各自维护独立 title 列表
- **建议改法和验证点**: 无需改法
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 已修复

## Scope Compliance Check

### Fix 文件范围

controller adjudication 允许的文件：`docs/host/design.md`、`docs/host/issues-implementation-control.md`、`docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md`。

fix 实际修改的文件（via `git diff main --name-only`）：design.md、issues-implementation-control.md、fix-codex.md，以及 `docs/reviews/` 下的其他 review artifact。所有修改均在允许范围内。未修改任何 production code (`dayu/`)、tests (`tests/`) 或 README。

### LLM-facing 内部术语泄漏检查

fix diff 新增的内部术语：`RUNNER_CALL_INPUT_ASSEMBLED`、`runner_call_input_manifest`、`runner_call_projection_artifact`、`compactor_input_projection`、`tool_call_arguments_json`、`tool_call_semantic_query_text`、`ToolCallArgumentsAtom`、`RunnerCallInputAssemblyManifest`、`RunnerCallMessageEntry`、`CompactorRunnerCallIdentity`、`ProjectorMetadataSummary`、`RunnerCallReconstructionDiagnostic`。

这些术语全部出现在 EventLog canonical event payload contract、payload descriptor kind、artifact kind 或 durable reconstruction contract 定义中，属于 Host 内部治理标识，不出现在 LLM-facing material 中。LLM-facing 替换表 (line 2572–2583) 已明确要求删除这类内部标识并用业务可读文本替代。fix 未引入新的 LLM-facing 内部术语泄漏。

## Open Questions

无。

## Residual Risk

- S7-R1-S1 实现时必须用 focused tests 证明 evidence routing uniqueness、boundedness sanity assertion 和 section title single-source。当前 fix 是纯设计文档修改，不包含可运行验证。
- design.md 新增了大量 runner-call reconstruction contract 定义（§23.1、Tool Trace 消费边界、`ToolCallArgumentsAtom` 等），这些是 S7-R1-S1 实现的前置设计，但超出了本次 re-review 的 controller adjudication scope。它们的正确性将在 S7-R1-S1 实现 review 中验证。

## Final Verdict

**Accept.** 四个 controller adjudication accepted findings 均已在 design.md 中正确修复，fix 文件范围合规，未引入新的 LLM-facing 内部术语泄漏，未修改 production code、tests 或 README。design fix 可通过 S7-R1-S0 gate，允许进入 S7-R1-S1 production implementation。
