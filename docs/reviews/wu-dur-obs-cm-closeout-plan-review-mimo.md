# WU-DUR / WU-OBS / WU-CM Closeout Plan — Adversarial Review

## Review Stance

adversarial plan review。重点挑战 plan 是否 code-generation-ready，是否违反设计真源和 AGENTS.md，是否让 EventLog 退化成 messages dump store，是否让 Tool Trace / memory snapshot 反向成为 truth，是否在 LLM-facing prompt/material 暴露内部实现术语，是否存在 schema/state/public contract 未先写入 design.md 的风险，是否有测试和 README 缺口。

## Review Metadata

- **Reviewed artifact**: `docs/host/wu-dur-obs-cm-closeout-plan.md`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Reviewer**: AgentMiMo (adversarial stance)
- **Date**: 2026-06-05

---

## Findings (按严重度排序)

### F-01 [BLOCKING] Slice 0 design contract writeback 缺乏具体字段定义，无法作为稳定真源

**证据**: plan.md L228-251 (Slice 0)。Slice 0 的 "Exact changes" 只列出章节标题级描述："在 EventLog / canonical event matrix 中增加或扩展 runner-call input manifest contract"、"扩展 TOOL_CALL_REQUESTED payload contract，写明 arguments ref/digest 与 semantic query atom"。没有给出任何字段名、类型、必填性、允许值或校验规则。

**为什么阻塞**: Slice 0 是整个计划的前置条件（plan.md L11: "implementation 前必须先完成 WU-DUR-P01 的设计真源回写"）。如果 Slice 0 只产出空壳章节标题，implementation agent 必须自行发明字段定义，导致后续 Slice 1-7 的实现缺乏统一真源。这不是 plan-ready，是 design-debt-forwarding。

**对照 design.md**: design.md L1501-1523 的 canonical event contract matrix 已经有严格的字段定义格式（必需 scope、必需 payload、状态副作用、Resume/memory、Audit/Host event stream）。Slice 0 必须产出同等级别的具体度。

**建议修正方向**: 在 Slice 0 的 "Exact changes" 中至少给出：
1. `RunnerCallInputAssemblyManifest` 的完整字段列表（字段名、类型、必填/可选、语义）。
2. `TOOL_CALL_REQUESTED` 扩展字段（`arguments_payload_ref` vs inline 的判定阈值、`semantic_query` 字段类型）。
3. `IterationStartedData` 新增字段的类型与可选性。
4. 新增 canonical event 或 artifact 的存储位置决策。

### F-02 [BLOCKING] RunnerCallInputAssemblyManifest 缺少 typed shape 定义

**证据**: plan.md L157 (Contract Changes) 列出 "Add a typed RunnerCallInputAssemblyManifest contract"，但只描述了语义目的，没有给出字段 shape。L162 列出 per-message manifest entries 的字段名（role、content_digest、source_refs、projection_artifact_ref、projector_id/schema_version/projector_digest），但没有类型、必填性或嵌套关系。

**为什么阻塞**: 这是 plan 声称要新增的核心 contract。没有 typed shape，implementation agent 无法判断哪些字段是 manifest 必需的、哪些是可选的、如何校验、如何序列化。对比 design.md L2602-2677 对 `ConversationCompactInputVNext` 的完整字段定义，manifest 的定义度远远不够。

**建议修正方向**: 在 plan 的 Contract Changes 或 Slice 0 中给出 manifest 的 typed dataclass shape，至少包含：
- `runner_call_kind` 枚举值列表（plan 已列出 5 种，确认是否穷举）
- `message_count`、`role_sequence_digest`、`source_cursor` 的类型
- per-message entry 的嵌套结构与必填字段
- `projector_metadata` 的子结构

### F-03 [BLOCKING] arguments inline vs payload ref 的判定阈值未定义

**证据**: plan.md L160: "either small canonical arguments inline under typed field, or arguments_payload_ref + arguments_payload_digest"。L273: "大 arguments 走 payload descriptor"。但"小"与"大"的阈值没有定义。

**为什么阻塞**: 这直接影响 schema 设计和测试断言。如果阈值不明确，implementation agent 可能：
1. 全部 inline（EventLog 膨胀）
2. 全部走 payload ref（小 tool call 丧失 inline 可读性）
3. 使用 ad-hoc 判定（不同 slice 逻辑不一致）

design.md L1437 只说"大 payload 应外移"，没有给具体字节数。plan 应该在 Slice 0 或 Slice 1 中明确这个阈值。

**建议修正方向**: 定义明确阈值（例如 `arguments_json_bytes <= 512` inline，否则 payload ref），或定义判定规则（例如"含二进制内容或超过 N 字段时走 ref"）。

### F-04 [BLOCKING] TOOL_CALL_REQUESTED 扩展的存储位置决策未明确

**证据**: plan.md L160: "Extend TOOL_CALL_REQUESTED canonical payload with accepted arguments durable atom"。但没有明确是：
- (a) 扩展 canonical event payload 的字段（类似 `normalized_arguments_digest` 的同级字段）
- (b) 新增 payload descriptor kind（类似 tool result 的 payload ref）
- (c) 两者结合（小 inline、大 ref）

plan.md L262 说 "为 TOOL_CALL_REQUESTED 写入 arguments payload ref/digest 或 bounded inline arguments"，暗示 (c)，但没有明确 canonical payload 的字段名和 payload descriptor 的 kind 命名。

**为什么阻塞**: 这决定了 Slice 1 的 schema 迁移方向、EventLog 写入路径和 payload_resolution 的消费路径。三种方案的实现复杂度和测试策略完全不同。

**建议修正方向**: 在 Slice 0/1 中明确：
- canonical payload 新增字段名（如 `arguments_payload_ref`、`arguments_inline`）
- payload descriptor kind 命名（如 `tool_call_arguments`）
- 判定逻辑（inline 阈值 + fallback to ref）

### F-05 [BLOCKING] "limited-signal diagnostic" 的结构未定义

**证据**: plan 在多处引用 "limited-signal"：
- L218: "Analyzer output can say complete, limited_signal, or mismatch"
- L219: "mismatch must name which check failed"
- L379: "缺失 durable atom 时输出 structured limited-signal"
- L474: "tool-loop continuation、compact 后 follow-up、compactor internal call 都有 manifest 或 limited-signal"

但从未定义 limited-signal 的数据结构：是枚举值？是 dataclass？包含哪些字段？如何在 smoke 断言中匹配？

**为什么阻塞**: 5 个 slice 都依赖这个概念作为 fallback path。没有结构定义，implementation agent 在每个 slice 中会发明不同的 diagnostic 形式，导致测试无法统一断言、smoke 无法统一解析。

**建议修正方向**: 在 Slice 0 或 Contract Changes 中定义 `LimitedSignalDiagnostic` 的 typed shape，至少包含 `signal_kind: Literal["complete", "limited_signal", "mismatch"]`、`mismatch_reason?: str`、`missing_atom_kind?: str`。

### F-06 [BLOCKING] RunnerCallInputAssemblyManifest 的存储形式未决策

**证据**: plan.md L172-173: "New runner-call manifest event, if added as canonical event, must have no Run terminal side effect"。关键词 "if added as canonical event" 表明 plan 没有决定 manifest 是 canonical event 还是 artifact。

**为什么阻塞**: 这是 schema 设计的根本分歧：
- 如果是 canonical event：需要新增 event class、写入 EventLog、参与 sequence ordering
- 如果是 artifact：需要定义 artifact kind、写入 artifact store、通过 ref 关联

两种路径的实现、测试和 recovery 语义完全不同。plan 不能把这个决策留给 implementation agent。

**建议修正方向**: 在 Slice 0 中明确决策。建议：manifest 作为 artifact（因为它是 derived assembly record，不是 Host 治理事实），通过 `CONTEXT_COMPACTED` 或 `RUN_STARTED` 等 canonical event 的 payload ref 关联。

### F-07 [NON-BLOCKING] compactor prompt 的内部术语清理范围需更精确

**证据**: plan.md L404-405 列出要清理的术语："Host-owned context compaction"、"ConversationCompactOutputVNext"、"vNext 字段"。

代码直接证据：
- `conversation_compaction.md:3`: "你是 Host-owned context compaction 组件" — 确认存在
- `conversation_compaction.md:14`: "输出必须完全符合 ConversationCompactOutputVNext schema" — 确认存在
- `conversation_compaction_user.md:53`: "不要输出 vNext 字段" — 确认存在，且该行还提到 `candidate_id`、`episode_summary_candidate` 等旧字段名

plan 没有列出 `conversation_compaction_user.md:53` 中的旧字段名清理项。这些旧字段名也是内部实现术语。

**为什么非阻塞**: 范围遗漏不影响架构正确性，implementation agent 大概率会在 Slice 6 中自行发现。但 plan 应该完整。

**建议修正方向**: 在 Slice 6 的 Exact changes 中补充 `conversation_compaction_user.md:53` 的旧字段名清理。

### F-08 [NON-BLOCKING] Test list 包含不存在的测试文件但未标注

**证据**: plan.md L278 列出 `tests/host/test_toolruntime_accept_barrier.py` 作为 Slice 1 的测试。Grep 搜索未找到该文件（但 `test_durable_schema.py` 存在）。

**为什么非阻塞**: 可能是需要新建的测试文件。但 plan 没有区分"已有测试需更新"和"需新建测试"，implementation agent 可能误以为该文件已存在。

**建议修正方向**: 标注哪些测试文件是新建的。

### F-09 [NON-BLOCKING] Slice 2 对 Engine IterationStartedData 的扩展可能违反 Engine 不理解 Host recovery 的边界

**证据**: plan.md L292-293: "扩展 IterationStartedData，加入 runner_call_index 与 role/message digest verification fields"。design.md L40: "Engine 不读取 Host durable store，不理解 Host policy，不管理 Session / Run / Attempt"。

`runner_call_index` 是 Host 治理概念（第几次 runner call），不是 Engine 执行概念。Engine 只知道 `iteration_index`（当前 iteration 序号）。

**为什么非阻塞**: plan 本身在 L304 说 "Engine 不理解 Host recovery truth"，说明已意识到边界。但 `runner_call_index` 如果由 Engine emit，就等于让 Engine 理解了 Host runner call 语义。

**建议修正方向**: 明确 `runner_call_index` 由 Host ingest 层计算并写入 manifest，不由 Engine emit。Engine `IterationStartedData` 只扩展 message digest 相关字段（这些是 Engine 执行态可观测的）。

### F-10 [NON-BLOCKING] plan 对 "四个 Host public smoke 入口" 的计数与 control doc 不完全对齐

**证据**: plan.md L487-492 列出 4 个入口：
1. `test_public_tool_wiring_smoke.py`
2. `test_public_open_host_multiturn_smoke.py`
3. `test_public_compact_smoke.py`
4. 4 个 `utils/smoke_host_public_*.py` 脚本

但 control doc L460 列出的审计范围是：`smoke_host_public_conversation_memory.py`、`smoke_host_public_diagnostics.py`、`smoke_host_public_conversation_memory_scenarios.py`、`smoke_host_public_multiturn.py`。

plan 把 4 个 utils 脚本算作"一个入口"，而 control doc 把它们算作 4 个。这不是错误，但计数方式不一致可能导致验收遗漏。

**为什么非阻塞**: 不影响实现正确性，但可能导致 smoke 覆盖报告不准确。

**建议修正方向**: 统一计数口径，或明确"入口"的定义（test file vs smoke script）。

### F-11 [NON-BLOCKING] Residual risks 中 "Provider-specific assistant tool_calls projection" 缺乏处置计划

**证据**: plan.md L513: "Provider-specific assistant tool_calls projection 可能涉及 reasoning_content / provider state，必须沿 Engine provider contract 做 typed 扩展，不能用 dict bag"。

这是一个已知风险，但 plan 没有指定哪个 slice 处理它。Slice 2 的 "assistant tool_calls message 重建" 可能涉及，但没有明确覆盖 `reasoning_content` 的 durable atom。

**为什么非阻塞**: 可以在 implementation 中通过 Slice 0 design contract 决定是否纳入。但 plan 应该明确 owner。

**建议修正方向**: 在 Slice 0 或 Slice 2 中明确 `reasoning_content` 和 provider state 的 durable atom 策略。

---

## Verdict Assessment

### Blocking Findings: 6

| ID | Summary | Required Action |
|---|---|---|
| F-01 | Slice 0 缺乏具体字段定义 | 补充 manifest/payload 字段 shape |
| F-02 | RunnerCallInputAssemblyManifest 无 typed shape | 定义完整 dataclass shape |
| F-03 | inline vs payload ref 阈值未定义 | 明确字节/字段阈值 |
| F-04 | TOOL_CALL_REQUESTED 扩展存储位置未决策 | 选定 canonical payload / payload descriptor / 混合 |
| F-05 | limited-signal diagnostic 结构未定义 | 定义 typed diagnostic shape |
| F-06 | Manifest 存储形式未决策 | 选定 canonical event vs artifact |

### Non-blocking Findings: 5

| ID | Summary |
|---|---|
| F-07 | compactor prompt 清理范围不完整 |
| F-08 | 测试文件新建/更新未标注 |
| F-09 | runner_call_index 归属层需明确 |
| F-10 | smoke 入口计数口径不一致 |
| F-11 | reasoning_content durable atom 无 owner |

### Residual Risks / Open Questions

1. **Manifest 字段膨胀风险**: plan 列出的 manifest 字段（runner_call_index、iteration_id、message_count、role_sequence_digest、per-message source refs、source cursor、RunInput projector id/schema version/digest、tool schema snapshot refs、compact artifact refs、memory snapshot cursor refs、continuity refs、context fallback decision refs、projector metadata）数量过多。如果不严格压缩，manifest 本身会变成变相的 messages dump。Slice 0 必须做字段必要性审计。

2. **Compactor internal call 的 rejected attempt manifest 归档**: plan.md L324 提到 "rejected/failed attempt 通过 diagnostic/canonical attempt event 引用相应 manifest"，但没有明确 rejected attempt 的 manifest 是否和 accepted 共享同一 artifact store，还是各自独立。这在多 retry compaction 场景下可能产生 artifact 碎片。

3. **Digest 同源校验的测试策略**: plan 要求 "校验 durable arguments 与 normalized_arguments_digest 同源"（L263），但没有说明测试如何构造校验 fixture：是用真实 Engine emit 的 arguments 计算 digest，还是用 mock 数据？如果用 mock，digest 算法必须和 ToolRuntime 完全一致。

4. **Public smoke 脚本的 provider 依赖**: plan.md L514 承认 "Public smoke 脚本可能受真实 provider 稳定性影响"，但没有说明 deterministic focused tests 能否完全替代 smoke 的验证能力。如果 focused tests 只测 mock path，真实 provider 路径的 prompt assembly 可能未被覆盖。

---

## Completion Report

- **artifact path**: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-mimo.md`
- **verdict**: fail
- **blocking findings count**: 6
- **non-blocking findings count**: 5
- **residual risks / open questions**: 4

### Verdict Rationale

plan 的架构判断正确（四个 WU 可组合推进、Slice 0 必须先行、EventLog 不能退化为 messages dump、Tool Trace 不能反向成为 truth），但作为 code-generation-ready plan 还不够：6 个 blocking findings 全部指向同一个根因——plan 在 contract/schema 层面停留在语义描述，没有给出足够的 typed shape 定义让 implementation agent 可以直接落代码。这不是"plan 不对"，而是"plan 不够具体"。总控需要在进入 implementation 前要求 plan owner 补齐 F-01 到 F-06 的具体定义，或在 Slice 0 的 design review gate 中把这些定义作为 hard requirement。
