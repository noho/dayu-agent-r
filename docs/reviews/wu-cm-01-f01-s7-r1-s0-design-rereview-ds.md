# Design Re-Review — WU-CM-01-F01-S7-R1-S0 Design Fix

## Scope

- Mode: design re-review (current changes)
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Prior gate: S7-R1-S0 design review → controller adjudication → S7-R1-S0 design fix
- Fix artifact: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md`
- Prior controller adjudication: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-controller-adjudication.md`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-rereview-ds.md`
- Included scope:
  - `docs/host/design.md` (staged modification)
  - `docs/host/issues-implementation-control.md` (unstaged modification)
  - `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-fix-codex.md` (fix artifact)
  - `docs/reviews/wu-cm-01-f01-s7-r1-s0-design-review-controller-adjudication.md` (prior adjudication)
- Excluded scope: pre-existing dirty test files (`tests/README.md`, `tests/host/public_smoke_support.py`, `tests/host/test_public_compact_smoke.py`, `tests/host/test_public_open_host_multiturn_smoke.py`, `tests/host/test_public_tool_wiring_smoke.py`); these existed before the fix and were not modified by it.
- Parallel review coverage: 无

## Verification Targets

本次 re-review 只验证 controller adjudication 中接受的四个修复要求是否在设计文档中正确落地，以及两项边界约束是否成立。

## Findings

### 1. 接受修复 1: Section 4/8 evidence routing 唯一归属 — 已验证通过

- **入口/函数**: `docs/host/design.md` §23 新增 system envelope section table + evidence routing rule
- **文件(行号)**: design.md:2559 (section 4), design.md:2563 (section 8), design.md:2566 (唯一归属规则)
- **输入场景**: 一条 evidence material 同时满足 `Verified Evidence and Facts` 和 `Recent Evidence` 的内容来源描述
- **实际分支**: 新增路由规则明确规定：
  - Section 4 `Verified Evidence and Facts` 拥有 "memory / fact pipeline 已接受的 evidence material" (line 2559)
  - Section 8 `Recent Evidence` 拥有 "未进入 memory / fact pipeline 的 recent-window fallback、wait-resume 或其它 evidence-like bounded material" (line 2563)
  - "同一条 evidence material 不得同时渲染到两个 section" (line 2566)
- **直接证据**: line 2566 显式唯一归属语句 + line 2566 后半句 transition rule："若某条 recent material 已被 memory / fact pipeline 接受，后续只能按 accepted memory / fact material 路由，不再按 recent fallback material 路由"
- **裁决**: 修复满足 controller adjudication 要求。Section 4 和 Section 8 的内容来源描述互斥，唯一归属规则明确，transition rule 覆盖了 material 状态变化场景。

### 2. 接受修复 2: `tool` role legality authority — 已验证通过

- **入口/函数**: `docs/host/design.md` §23 selected recent window role preservation 段落
- **文件(行号)**: design.md:2568
- **输入场景**: 实现者需要决定被选入 selected recent window 的 historical evidence 使用什么 role
- **实际分支**: 设计明确写入："当前 Engine message contract 不支持 ordinary RunInput historical evidence 使用 `tool` role，因此 selected recent evidence 和其它不能作为 `user` / `assistant` role 保留的 historical evidence 默认进入首条 system envelope"
- **直接证据**: line 2568 显式声明当前 Engine contract 不支持 `tool` role + 明确 fallback 行为（进入 system envelope）+ 明确 trade-off（牺牲原始交错位置换取 one-system-message shape）+ 未来变更出口（"未来如果 Engine contract 支持 historical evidence 使用 `tool` role，可在后续 work unit 中重新评估"）
- **裁决**: 修复满足 controller adjudication 要求。当前 authority 边界明确，trade-off 记录完整，未来变更路径清晰。

### 3. 接受修复 3: Boundedness measurable sanity — 已验证通过

- **入口/函数**: `docs/host/design.md` §23 system envelope merge 段落
- **文件(行号)**: design.md:2585
- **输入场景**: 实现者需要验证 merge 后的 system envelope 大小是合理的
- **实际分支**: 设计写入可测断言：`len(merged_system_content) <= sum(len(candidate_system_content)) + deterministic_header_separator_overhead`
- **直接证据**: line 2585 显式定义三个量：
  - `merged_system_content` — merge 后的 system envelope 内容
  - `candidate_system_content` — 所有准备进入 system envelope 的 bounded rendered content
  - `deterministic_header_separator_overhead` — 只包含非空 section 的固定 Markdown header、header 与内容之间的固定换行，以及 section 间固定 separator
- **额外约束**: line 2585 显式要求 "若某 section 在 merge 前已超出其 provider cap，必须在 provider 边界 fail closed 或截断；merge helper 不得用新的全局截断掩盖上游 cap 失效" + "focused tests 必须覆盖 section cap preservation 或上述总字符数 sanity，并断言 merge 没有引入候选 system content 之外的新业务文本"
- **裁决**: 修复满足 controller adjudication 要求。公式各项定义明确，upstream cap 保护约束到位，测试要求具体。

### 4. 接受修复 4: Section title single source — 已验证通过

- **入口/函数**: `docs/host/design.md` §23 system envelope section table 头部 + §24.6 Prompt Assembly 段落
- **文件(行号)**: design.md:2553 (真源声明), design.md:3054 (引用声明)
- **输入场景**: 未来维护者修改 section title 时可能存在 §23 和 §24 两个列表需要同步
- **实际分支**: 设计写入两级约束：
  - §23 (line 2553): "下表是 section title、顺序和 Conversation Memory section 映射的唯一真源；其它章节只能引用本表的映射关系，不得重复硬编码完整 title 列表。"
  - §24.6 (line 3054): "Conversation Memory section header 必须使用 23 节 system envelope section table 中对应内容来源的固定 LLM-facing title；23 节表格是 section title 与映射关系的唯一真源，本文不重复硬编码完整 title 列表。"
- **直接证据**: 两次显式声明 §23 表格为唯一真源 + 两次显式禁止重复硬编码完整 title 列表
- **保留分析**: §24.6 (lines 3013-3022) 有一份 10 项中文描述的 Prompt Assembly 顺序列表，但该列表与 §23 表格职责不同——§24.6 描述完整 assembly 顺序（含 selected recent window 和 current input 这类 user/assistant role 材料，它们不在 system envelope section 范围内），使用中文描述而非 English section title，不构成 title 重复。该列表是一份已有的 assembly order 清单，不属于本次修复引入的重复。
- **裁决**: 修复满足 controller adjudication 要求。唯一真源声明明确、引用关系清晰、禁止重复规则到位。

### 5. 边界约束: No production/test/README changes — 已验证通过

- **入口/函数**: git diff 分析
- **文件(行号)**: N/A
- **输入场景**: 修复是否意外修改了生产代码、测试文件或 README
- **实际分支**: `git diff --name-only` 显示只有 `docs/host/design.md` 和 `docs/host/issues-implementation-control.md` 被修改
- **直接证据**: `git diff HEAD -- docs/host/design.md docs/host/issues-implementation-control.md` 返回完整 design doc diff；`git diff --name-only | grep -v 'docs/'` 返回的 test file 修改是本次修复之前的已有脏文件（git status 快照可确认这些文件在修复前已处于 modified 状态且未 staged）
- **裁决**: 修复未引入任何 production、test 或 README 变更。

### 6. 边界约束: No new LLM-facing internal term leak — 已验证通过

- **入口/函数**: `docs/host/design.md` §23 新增全部内容
- **文件(行号)**: design.md:2550–2618
- **输入场景**: 新增设计文本是否在 LLM-facing 内容中引入了内部术语泄漏
- **实际分支**: 
  - §23 section title 全部使用业务可读 English 标题（`Task Instructions`、`Execution Guidance`、`Conversation Summary`、`Verified Evidence and Facts`、`Prior Answer Anchors`、`Open Follow-up Context`、`Reference Continuity`、`Recent Evidence`、`Resume Guidance`），不包含 Python 类型名、projector id、policy ref、内部模块名或 Host 治理字段
  - 每个 section 的渲染规则显式禁止内部术语（如 line 2559: "不得写 tool_call_id、event id、payload ref、digest 或 cursor"）
  - 新增 internal ref replacement table (lines 2572-2583) 系统性地定义了内部标识 → LLM-facing 替代策略，是开发者契约而非 LLM-facing 内容
  - 这些内容是设计文档（Host 开发手册），目标是告诉实现者如何构造 LLM-facing 内容；设计文档本身不是 LLM-facing 材料
- **直接证据**: 设计文档中使用的 `AgentRunRequest.messages`、`RunInputBuilder`、`RunnerCallInputAssemblyManifest` 等内部术语仅出现在开发者契约描述中，不出现在 §23 table 的 section title 或渲染规则列中。AGENTS.md Agent 语义约束明确区分生产代码/artifact descriptor 中的内部术语使用（允许）与 LLM-facing 内容中的内部术语暴露（禁止）
- **裁决**: 未引入新的 LLM-facing 内部术语泄漏。设计文档作为开发者契约正确区分了内部术语使用和 LLM-facing 语义。

## Open Questions

无。

## Residual Risk

- **§24.6 已有 assembly order 列表 vs §23 table 的映射关系未显式化**: §24.6 (lines 3013-3022) 的 10 项中文描述列表与 §23 的 9-section English title table 之间的对应关系未逐项标注。当前不构成维护风险（两者职责不同，且 §24.6 已添加引用声明），但 S7-R1-S1 实现时若实现者仅读取 §24.6 列表而忽略 §23 table 的真源声明，可能使用错误的 section title。建议在 S7-R1-S1 implementation review 中额外确认实现代码是否实际引用了 §23 table 中的 English title。

## Final Verdict

**通过。** 四项接受修复全部正确落地，无新增设计缺陷。两条边界约束（无 production/test/README 变更、无新增 LLM-facing 内部术语泄漏）均成立。S7-R1-S0 design fix 已满足 controller adjudication 的全部修复要求，可进入下一 gate。
