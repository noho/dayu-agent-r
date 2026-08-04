# Interactive Conversation Memory closure F08–F10：Adversarial Plan Review (DS)

## Review identity

- **Reviewed target**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`
- **Review type**: 独立第二路 adversarial plan review；不依赖 MiMo 结论
- **Reviewer**: DS (adversarial pass)
- **Date**: 2026-08-04
- **Observation target**: `2e7a01678677817aafd22603f03f17605aa9e39c`
- **Base ref**: `github/main` → `113ea34d47b95812d79aa31705949bbb46bc6061`
- **Frozen evidence SHA-256**: `ad64315116c3940d9b0e7354c9e2a38aeff75fa179af723a82e696ff55658263`
- **Current branch**: `codex/interactive-oracle`

## Method summary

本 review 独立读取了以下真源：

- 根 `AGENTS.md`（含语义所有权、LLM-facing 约束、README 触发规则）
- Finding 真源：`docs/reviews/wu-interactive-memory-closure-f08-f10.md`
- Frozen evidence：`workspace/tmp/interactive-memory-observed-behavior.md` + freeze JSON
- Host design：`docs/host/design.md`
- Engine design：`docs/engine/design.md`
- CLI CI oracles：`docs/cli_ci_oracles.json`（F08–F10 clauses）
- CLI CI scenarios：`docs/cli_ci_scenarios.json`（五条 obligation）
- 生产代码真源：
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`（F08 owner）
  - `dayu/host/compaction.py`（typed contract，含 `CompactSegmentSelection`、`CompactionRequest`、`CompactRepairFeedbackV2`）
  - `dayu/host/compact_material.py`（selector、`RunInputMaterialBlock`、`select_compact_segment`、`is_turn_group_material_block`）
  - `dayu/host/compact_pipeline.py`（`build_normal_compact_request_plan`、`build_tier_recovery_request_plans`、`build_reactive_pass_queue_plan`、`_single_block_segment_selection`）
  - `dayu/host/context_governance.py`（`accept_compact_candidate_v2`、`build_compact_repair_feedback_v2`）
  - `dayu/host/compaction_operation.py`（`DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest`、`_run_compaction_operation`、`run_compaction_attempt`）
  - `dayu/host/dispatch.py`（`_execute_proactive_compaction`、feedback 传递逻辑）
  - `dayu/host/durable/tool_trace.py`（`_validated_runner_call_contract`、`_runner_call_signal_from_hot_row`、`read_runner_call_reconstruction_signals_by_run`、`resolve_runner_call_projection_from_signal`）
- README 更新约束：根 `README.md`、`dayu/host/README.md`、`dayu/config/README.md`、`tests/README.md`

每个 finding 均附带直接代码行号或 plan 段落引用。

## Assumptions tested

| # | Assumption | Verdict |
|---|---|---|
| A1 | F08 的 LLM-facing 规则只靠 prompt 自足，不需要 Host deterministic verifier | 成立；prompt 是目前唯一正确的 owner |
| A2 | `session_summary: null` 在现有 `CompactCandidateV2.session_summary` 类型中已是合法值 | 成立；`CompactSessionSummaryV2 \| None`（`compaction.py:1388`） |
| A3 | F09 的 EventLog `payload_ref=None` 是生产者 bug，不是 resolver 过严 | 成立；`compaction_operation.py:328-329` 显式写 `None`，resolver 的 strict equality check 在 `tool_trace.py:1039-1047` |
| A4 | F10 的 `turn_group_id` 已在 `RunInputMaterialBlock` 中存在且非空 | 成立；`compact_material.py:202` 定义，material builder 在 `compact_material.py:2406,2441,2496` 填入 `row.run_id` |
| A5 | `select_compact_segment` 对非 protected 区域不按 turn-group 做原子选择 | 成立；`compact_material.py:824-845` 的 budget 循环按单个 block 累计 |
| A6 | dispatcher 将 `next_repair_feedback` 无条件传递给下一 attempt | 成立；`dispatch.py:2325` 无 boundary check |
| A7 | accept barrier 只验证 reduced boundary 内部 coverage | 成立；`_run_compaction_operation` 的 root aggregate revalidation（`compaction_operation.py:1065-1070`）使用 `accept_compact_candidate_v2`，不验证 turn-group 完整性 |
| A8 | plan 的修复边界与语义 owner 表一致 | 待验证（见 Finding 1） |

## Findings

### 1-HIGH-frozen-baseline-commit-boundary

- **位置**: Plan §1（工作区隔离）与 §10（提交边界）
- **问题类型**: 范围漂移 / 契约缺失
- **当前写法**:
  - §1 (line 13): "实现阶段必须将它们视为只读既有输入，不得覆盖、格式化或**纳入本 work unit 的提交**"（指 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、finding artifact）
  - §10 (line 404): "禁止把 frozen registry/finding/evidence 或用户既有 dirty changes 混入"
  - §10 列出的五个提交仅包含 plan artifact + F08/F09/F10 实现 + review/deepreview 修复，不包含三份 frozen baseline 或 plan-review artifact
- **反例/失败场景**: 用户明确要求 "accepted-plan checkpoint 与 plan/review artifacts 一并独立提交并保持 hash"。当前 plan 显式禁止纳入提交，导致 plan gate 接受后缺失必要的 registry checkpoint commit。Plan-review artifact（本文件）同样被遗漏。
- **为什么有问题**: 三份 frozen baseline（`docs/cli_ci_oracles.json` +541 lines、`docs/cli_ci_scenarios.json` +509 lines、`docs/reviews/wu-interactive-memory-closure-f08-f10.md`）是 work unit 的正式 registry entry，记录了 F08–F10 的 scenario obligations 与 observed behavior。它们必须在 implementation 开始前作为独立 checkpoint 提交。plan 的 §10 将它们与 "用户既有 dirty changes" 混为一谈，但它们是 work unit 的正式组成部分，不是偶然 dirty state。
- **直接证据**:
  - `git status --short` 显示 `M docs/cli_ci_oracles.json`、` M docs/cli_ci_scenarios.json`、`?? docs/reviews/wu-interactive-memory-closure-f08-f10.md`
  - Finding artifact §"Registry readiness" (line 154-158): "本次已经把上述五条 obligation 写入正式 scenario registry"
  - Plan §10 line 404 明确写 "禁止把 frozen registry/finding/evidence...混入"
  - 用户 system-reminder 明确: "用户明确要求 accepted-plan checkpoint 与 plan/review artifacts 一并独立提交并保持 hash"
- **影响**: plan gate 接受后无正确的 checkpoint commit，后续 gate 无法从 committed state 验证 plan acceptance 的 hash 一致性
- **建议改法和验证点**:
  - §10 增加一个 **commit 0**（在 plan artifact commit 之前或合并为一个 checkpoint commit）：将三份 frozen baseline + finding artifact + plan artifact + plan-review artifact（MiMo + DS）作为单一独立 checkpoint 提交
  - §1 的 "不得纳入本 work unit 的提交" 改为 "不得在 implementation gate 修改或覆盖"
  - 提交信息建议: `gateflow: accept plan checkpoint for interactive-memory-closure-f08-f10`
  - 验证：commit 包含全部上述文件，hash 可重现
- **修复风险**: 低
- **严重程度**: 高

### 2-MEDIUM-F08-prompt-self-sufficiency-underspecified

- **位置**: Plan §6 Slice F08 实施步骤 1
- **问题类型**: 不可直接实施
- **当前写法**: "summary 必须是 cap 内仍可独立理解的有意义业务摘要；若无法在明确 cap 内表达，则输出 JSON `null`；禁止占位符、孤立字符、无业务含义缩写或截断片段"
- **反例/失败场景**: implementation agent 拿到计划后，需要在 prompt 中写出 "有意义且可独立理解" 的具体判断规则。但 plan 只描述了目标语义，没有给出 LLM-facing 的、自足的判断边界。可能的失败：
  1. implementation agent 写出过于主观的规则（如 "摘要必须包含完整主谓宾"），LLM 在 cap=1 时仍尝试满足，输出 "A" 或 "。" 等
  2. implementation agent 写出过于宽松的规则，LLM 在 cap=50 时也输出 null
  3. 规则中出现隐式词表阈值（如 "至少5个中文字符"），违反 plan non-goal 的 "不增加基于字符、词表、语言或模式匹配的'有意义摘要' heuristic"
- **为什么有问题**: AGENTS.md LLM-facing 约束要求 "只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"（line 41），并且 "结构化输出必须在当前 prompt 中自足说明"（line 42）。Plan 当前只给出了语义目标，但没有给 implementation agent 提供足够具体的 LLM-facing 规则框架。implementation agent 可能被迫自行设计规则的 precision/recall 边界，而这是 plan 应该收敛的。
- **直接证据**:
  - AGENTS.md LLM-facing 约束 §"只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"
  - Plan §2.3 Non-goals: "不增加基于字符、词表、语言或模式匹配的'有意义摘要' heuristic"
  - Plan §6 Slice F08 步骤1 只给了四条语义目标，没有 LLM-facing 措辞框架
  - 当前 prompt（`conversation_compaction_user.md:34-35`）已有 `null` 表示清除的说明，缺的是 "何时必须选择 null" 的判断规则
- **影响**: implementation agent 设计的 prompt 规则可能与 plan 意图偏离；或规则太模糊导致 LLM 仍输出占位符
- **建议改法和验证点**:
  - Plan 应给出 prompt 规则的具体框架措辞，例如：在 `session_summary` 字段说明末尾增加类似如下判断规则：*"若在给定的明确字符上限内，无法形成一句可独立理解的、包含实际业务进展的摘要（例如 cap 只能容纳1-2个无上下文的孤立字符时），则必须将 session_summary 设为 JSON null。不得输出单个字母、标点、空白字符或仅由停用词组成的片段当作摘要。"*
  - 或至少给出 implementation agent 必须覆盖的 LLM-facing 判断维度：cap 是否足以容纳 (a) 当前会话的核心任务识别 + (b) 至少一个具体已完成进展 + (c) 当前关键约束，三者任一不能满足即输出 null
  - Prompt contract test 应断言这些具体规则措辞存在
- **修复风险**: 低（调整 plan 措辞，不涉及代码）
- **严重程度**: 中

### 3-MEDIUM-F10-oversized-group-fallback-path-undefined

- **位置**: Plan §5.2 Turn-group selection 状态机 + §6 Slice F10 步骤 B
- **问题类型**: 不可直接实施
- **当前写法**: "单组本身超过 cap 时整组留在 raw/protected/fallback 路径，不允许'至少选一个 block'的 partial progress"
- **反例/失败场景**: 当 `turn_group_id` 为某 completed Run 的 group 总 size_units 超过 `max_selected_size_units` 时，`select_compact_segment` 会将其标记为 `budget_limit`。但 plan 没有说明：
  1. 这个 oversized group 如何进入 "raw/protected/fallback 路径"——是指 existing fallback mechanism（`RecentWindowFallbackSelection`）自动覆盖，还是需要 selector 返回特殊的 oversized-group 信号？
  2. 当前 `build_tier_recovery_request_plans`（`compact_pipeline.py:491-572`）使用同一 budget policy 调用 `select_compact_segment`，tier 1/2/3 均使用 fallback caps。如果 oversized group 在所有 tiers 都被 `budget_limit`，它最终落在哪里？
  3. 如果 oversized group 确实无法被任何 tier 容纳，是否会触发 `CONTEXT_COMPACTION_FAILED` terminal，还是静默降级到 raw-only RunInput？
- **为什么有问题**: 这是 F10 finding 的核心场景——completed Run 的 tool evidence + final answer 整体超过 fallback cap。Plan 描述了 "整组不选" 的 selector 行为，但没有闭环到 dispatcher/fallback 的衔接。Implementation agent 会困惑：selector 标记 `budget_limit` 后，上层如何区分 "普通预算用尽" 和 "原子组过大无法选择"？
- **直接证据**:
  - Plan §5.2 line 128: "单组本身超过 cap 时整组留在 raw/protected/fallback 路径"
  - `select_compact_segment`（`compact_material.py:780-880`）返回的 `CompactSegmentSelection` 只有 `excluded_reason_codes` 中的 `budget_limit` reason，没有 oversized-group 专用信号
  - `build_tier_recovery_request_plans` 对所有 tiers 使用同一 `select_compact_segment` 调用
  - MC32 evidence: attempt 3/4 的 tier recovery 截断了 completed Run，证明 fallback caps 确实可能落在 group 内部
- **影响**: implementation agent 可能采用错误的下游补偿（如增大 cap 绕过），或 oversized group 静默丢失，未进入 raw material
- **建议改法和验证点**:
  - Selector 输出中增加 oversized-group block ids 的显式信号（如 `oversized_group_block_ids`），与普通 `budget_limit` 区分
  - 说明 oversized group 在 fallback 路径中的处理：是否进入 `RecentWindowFallbackBudgetResult` 的 excluded list？是否触发 diagnostic log？
  - 增加测试 case：三工具 completed Run 总 size 超过所有 tier caps 时，确认 oversized group 进入 raw material 而非被静默丢弃
- **修复风险**: 中（可能需要调整 selector 输出结构与 pipeline 衔接逻辑）
- **严重程度**: 中

### 4-MEDIUM-F10-selection-digest-stability

- **位置**: Plan §6 Slice F10 步骤 A2 + §12 Residual risks
- **问题类型**: 契约缺失
- **当前写法**: "Root selection constructor 校验 group membership 中 block id 全局唯一...Root selection digest 包含 group member order 与 disposition 相关字段" + §12: "给 selection 与 repair feedback 增加 internal canonical fields 会改变 request/selection digest"
- **反例/失败场景**: 当前 `CompactSegmentSelection.selection_digest` 的 digest input 在 `select_compact_segment`（`compact_material.py:860-869`）中定义，包含 `selected_block_ids`、`excluded_protected_ids`、`excluded_reason_codes`、`trigger_source`、`input_cursor`、`memory_snapshot_cursor`、`policy_digest`、`deterministic_reason_codes`。Plan 要求增加 group manifest 到 digest input。这会改变：
  1. 所有现有 durable stored `CompactSegmentSelection` 记录的 digest——但这些是治理内部字段，不进入 v2 schema，变更仅影响内部治理一致性
  2. 所有测试 fixture 中硬编码的 selection digests——但这些 fixture 按 plan 要求应 "从 owner helper 重新生成，禁止硬编码旧 digest"（§12）
  3. 然而 plan 没有讨论：如果某个现有 `CompactionRequest.digest()` 被存储在 durable EventLog 中作为历史 fact reference，修改 digest 计算是否会破坏历史记录的 referential integrity？当前 `CompactionRequest.to_json()`（`compaction.py:2099-2120`）包含 `segment_selection.to_json()`，而 `CompactionRequest.digest()` 使用 `sha256_digest_json(self.to_json())`——修改 selection digest 的输入会级联改变 request digest
- **为什么有问题**: Plan §12 将 digest 变化列为 residual risk，但未说明这是否会破坏现有 durable stores 中的 request digest 引用。如果 existing EventLog rows 中有 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 等引用旧 request digest 的 payload，这些历史 digest 与新代码计算的 digest 不同——这是否需要迁移或 backward reference？
- **直接证据**:
  - `CompactionRequest.to_json()`（`compaction.py:2106`）包含 `"segment_selection": self.segment_selection.to_json()`
  - `CompactionRequest.digest()`（`compaction.py:2097`）使用 `sha256_digest_json(self.to_json())`
  - Plan §12 line 435: "相关 fixtures 必须从 owner helper 重新生成，禁止硬编码旧 digest"
  - Plan 未讨论 durable store 中的历史 request digest
- **影响**: 历史 durable 记录中引用的 request digest 与新代码不匹配；或测试 fixture 更新遗漏导致 digest mismatch
- **建议改法和验证点**:
  - 明确声明：selection/request digest 是 Host internal governance identity，不承诺跨代码版本的稳定序列化；历史 EventLog 中的 digest 是当时代码版本的 fact，不与新代码 cross-verify
  - 或：限定 group manifest 进入新的专用 digest 字段（如 `root_selection_group_digest`），不改动现有 `selection_digest`
  - 验证所有引用 request digest 的 durable payload 不要求跨版本匹配
- **修复风险**: 中
- **严重程度**: 中

### 5-MEDIUM-F10-mixed-eligibility-group-per-block-vs-per-group

- **位置**: Plan §5.2 Turn-group selection 状态机 + §6 Slice F10 步骤 B2
- **问题类型**: 不可直接实施
- **当前写法**: "若 group 任一成员命中 current-input、recent-floor、already-represented 等非 compactable 条件，整个 group 使用同一确定性 exclusion disposition；不得选择其余成员"
- **反例/失败场景**: 当前 `select_compact_segment` 的循环（`compact_material.py:824-845`）对每个 block 单独调用 `_block_exclusion_reason`。对于同一 `turn_group_id` 的 group，如果 member A 的 `already_represented=True` 而 member B 的 `already_represented=False`，当前代码会给 A `already_represented` 而 B 可能 selected。Plan 要求在循环中完成 per-group aggregation——但这需要：
  1. 在循环**之前**先做 group 归并（按 `turn_group_id` 分组）
  2. 对每个 group 的所有成员做 collective exclusion check
  3. 然后整体决定 selected 或 excluded
  4. 这意味着现有多 pass 循环结构需要重构为 two-pass（先 group → 再 singleton）
  5. 但 plan 的步骤 B 只说 "用模块级私有 helper 将已排序 blocks 归并为原子 units"，没有详细说明 this two-pass 结构
- **为什么有问题**: 当前 selector 的 budget 循环是单 pass 的 prefix-bounded 迭代。引入 group-aware pre-pass 会实质性改变 selector 的控制流结构。Plan 没有充分说明两个 pass 的交互：group pre-pass 的 exclusion 后，remaining eligible units 如何进入 budget 循环？budget 循环中 group 的 size 如何影响 `budget_blocked` flag（当前仅当 `max_selected_item_count is not None` 时为 True）？
- **直接证据**:
  - `select_compact_segment` 循环体（`compact_material.py:824-845`）是纯 per-block 单 pass
  - `_block_exclusion_reason`（`compact_material.py:1802-1824`）检查 `already_represented`、`protected_recent_raw_turn` 等 per-block flags
  - Plan §5.2 line 123-127 描述了 group-aware exclusion，但 §6 步骤 B 没有展开 two-pass 实现结构
- **影响**: implementation agent 可能采用低效或错误的 two-pass 实现（如在循环内回访已遍历的 blocks）；或 group exclusion 与 singleton exclusion 的交互出现边界 bug
- **建议改法和验证点**:
  - Plan 步骤 B 明确描述 two-pass 结构：Pass 1 归并 units + 计算每个 unit 的 collective exclusion reason；Pass 2 budget 循环在 unit 粒度上执行 prefix policy
  - 增加测试 case：同 group 内三个 blocks 分别 `already_represented=(True, False, True)` + `protected_recent_raw_turn=(False, False, True)`，验证整组 exclusion reason 取最高优先级（protected > current > already_represented）
  - 验证 exclusion reason precedence 不依赖 dict iteration order
- **修复风险**: 中
- **严重程度**: 中

### 6-LOW-F08-config-readme-trigger

- **位置**: Plan §9 README / design 触发判定表
- **问题类型**: 范围漂移
- **当前写法**: "`dayu/config/README.md`：已检查，不触发内容更新。F08 只澄清现有 scene prompt 的业务动作，不改变 config 目录职责、装载方式或 schema。"
- **反例/失败场景**: CLAUDE.md 的 README 触发规则明确：`dayu/config/` 修改 → "检查并按需更新 `dayu/config/README.md`"。Plan 修改的文件包括 `dayu/config/prompts/scenes/conversation_compaction_user.md`，该文件位于 `dayu/config/` 下。Plan 的 "不触发内容更新" 可能是正确的结论（如果 README 确实不需要更新），但 "已检查" 的措辞不够——需要明确读过了 `dayu/config/README.md` 的更新约束并确认不触发。
- **为什么有问题**: CLAUDE.md 要求 "修改 README 前必须先阅读目标 README 的该约束"——plan 应引用已读的具体 README 章节和判定依据，而非仅写 "已检查"。
- **直接证据**:
  - CLAUDE.md §README 更新触发: "`dayu/config/` 修改 -> 检查并按需更新 `dayu/config/README.md`"
  - Plan §6 F08 allowed files 明确包含 `dayu/config/prompts/scenes/conversation_compaction_user.md`
  - `dayu/config/README.md` 的更新约束（line 11-19）定义其职责为 "配置层级、覆盖关系与 prompts 目录职责"——prompt 内容的业务语义澄清确实不属于该 README 职责，因此 "不触发" 结论正确
- **影响**: 低——结论正确但证据链不完整
- **建议改法和验证点**: 在 §9 中增加一行引用 `dayu/config/README.md` 的更新约束章节，明确说明已核实 F08 的 prompt 修改不触及该 README 的职责范围
- **修复风险**: 低
- **严重程度**: 低

### 7-LOW-F10-group-manifest-typed-surface-ambiguity

- **位置**: Plan §6 Slice F10 步骤 A1
- **问题类型**: 不可直接实施
- **当前写法**: "在 `dayu/host/compaction.py` 为内部 selection contract 增加严格类型：root boundary 与 reactive transient pass 的闭集 scope；稳定的 turn-group membership 项，字段至少包含 `turn_group_id` 与按 material 顺序排列的非空唯一 `member_block_ids`"
- **反例/失败场景**: `CompactSegmentSelection`（`compaction.py:1766-1844`）已有 11 个 fields + `to_json()` 15 个 keys。Plan 要求增加 group membership 到 selection contract，但没说清楚：
  1. 是直接给 `CompactSegmentSelection` 增加 `group_memberships: tuple[GroupMembership, ...]` 字段，还是创建新的 `RootSelectionProof` 独立类型？
  2. 如果是新类型，它如何与 `CompactSegmentSelection` 关联？——作为 companion 字段？还是替代 `CompactSegmentSelection` 在 operation root path 中的角色？
  3. `CompactSegmentSelection` 同时被 proactive 和 reactive 路径使用——group manifest 是否只在 root 路径有意义？
- **为什么有问题**: AGENTS.md 编码约束禁止 God dataclass。`CompactSegmentSelection` 已有 11 fields，直接加 group manifest 使其进一步膨胀。implementation agent 若自行设计独立类型，可能与 plan 意图偏离。
- **直接证据**:
  - `CompactSegmentSelection`（`compaction.py:1766-1844`）当前 fields: `selected_block_ids`, `excluded_protected_ids`, `trigger_source`, `input_cursor`, `memory_snapshot_cursor`, `policy_digest`, `deterministic_reason_codes`, `selection_digest`, `excluded_reason_codes`
  - AGENTS.md §编码硬约束: "禁止 God object、God function、God dataclass、god bag、god builder"
  - Plan §6 步骤 A1 只说 "增加严格类型" 未指定是扩展现有类型还是新建
- **影响**: implementation agent 设计选择与 plan 意图偏离；或 `CompactSegmentSelection` 过度膨胀
- **建议改法和验证点**:
  - 明确 group manifest 是 `CompactSegmentSelection` 的新字段，还是独立的 `RootSelectionGroupManifest` 类型
  - 若独立，说明如何在 `CompactionRequest` 或 operation root path 中关联
  - 若合并，说明这 11→13+ fields 的扩展不违反 god-object 约束（因为它们是同一 selection contract 的不可分割部分）
- **修复风险**: 低
- **严重程度**: 低

### 8-LOW-F10-feedback-request-digest-test-gap

- **位置**: Plan §7 测试矩阵 + §6 Slice F10 步骤 D5
- **问题类型**: 测试缺口
- **当前写法**: §7 测试矩阵 row "operation / 直接注入 mismatch feedback" 断言 "provider 未调用，明确 contract failure"
- **反例/失败场景**: Plan step D5 说 `_run_compaction_operation` 在准备 proposal 前校验 non-null initial feedback 的双 digest binding，不匹配时抛出 contract error。测试矩阵只覆盖了 operation-level 的直接注入。但缺少：
  1. dispatcher 层测试：证明 proactive dispatcher 在 tier boundary 变化时确实清空了 feedback（而非只在 operation 层报错）
  2. 若 dispatcher 有 bug 未清空 feedback，operation 的 contract error 是否会导致整个 proactive compact fail 而非 graceful fallback？
- **为什么有问题**: 这是 F10 三个根因之一（根因 #2: dispatcher 跨 boundary 传递 feedback）。Plan 在 dispatcher 层的修改是 "每次 attempt 前比较 feedback binding 与 attempt_plan.request 的双 digest"——这个比较逻辑没有对应的 scheduler 层测试 case。测试矩阵中 "scheduler / root repair → tier 1" 只断言 "feedback 为 None"，但没有覆盖 "scheduler 错误地传递了 mismatched feedback，operation 应 fail closed 但不导致 Run 崩溃" 的 defensive case
- **直接证据**:
  - `dispatch.py:2292-2325`: `repair_feedback` 在 attempt loop 中无条件从 `attempt_result.next_repair_feedback` 赋值
  - Plan §6 步骤 D4: "dispatcher 每次 attempt 前比较 feedback binding"
  - Plan §7 测试矩阵 scheduler rows 只覆盖 happy path，无 dispatcher defensive failure case
- **影响**: 若 dispatcher 的 digest comparison helper 有 bug（如比较时使用了错误的 digest 源），可能导致 feedback 仍跨 boundary 传递，而 operation 的 contract error 可能导致整个 proactive compact fail
- **建议改法和验证点**:
  - 测试矩阵增加: "scheduler / dispatcher 错误传递 mismatched feedback → operation contract error → 单一 failed terminal/fallback（不导致 Run 崩溃）"
  - 或明确说明 operation contract error 的 catch 策略：是抛异常中止整个 proactive compact，还是转为 rejected attempt 继续 schedule？
- **修复风险**: 低
- **严重程度**: 低

## PASS items

以下方面经独立审查后确认 plan 处理正确，无需修改：

### PASS-F09-canonical-manifest-同源修复

- Plan 识别的 F09 根因准确：`DurableCompactorProposalManifestRecorder.record_compactor_proposal_manifest` 在 `compaction_operation.py:328-329` 将 `EventLogAppendRequest` 的 `payload_ref` 与 `payload_digest` 显式写为 `None`，而同一 transaction 内 `_compactor_runner_call_hot_payload`（line 323）已正确使用 `manifest_descriptor.payload_ref` 和 `manifest_digest`。
- 修复方案在正确的 owner boundary：将 `payload_ref=manifest_descriptor.payload_ref, payload_digest=manifest_digest` 填入 EventLog append request，实现 EventLog row、hot payload、Tool Trace hot row、formal resolver 四端同源。
- Plan 明确不放松 resolver strict identity check（`tool_trace.py:1039-1047` 的 `==` 比较保持不变）——正确。
- Integration test 覆盖 successful compact + invalid→repair/fallback 路径——正确。
- 不修改 `dayu/host/durable/tool_trace.py`——正确，bug 不在 resolver。

### PASS-F08-null-clear-replacement-contract

- Plan 正确识别 `CompactCandidateV2.session_summary: CompactSessionSummaryV2 | None` 已支持 null（`compaction.py:1388`）。
- Plan 明确 Memory projector 必须在 accepted `null` 后清除旧 summary，不得 fallback 到 previous summary——正确。
- Plan 正确拒绝在 Host 侧增加 deterministic natural-language validator——这符合 AGENTS.md LLM-facing 约束。
- Plan 的 Memory owner test（含非空 summary → accepted null → 其它四类保留 → reload 一致）覆盖了 replacement contract 的关键路径。

### PASS-F10-invariant-design

- Plan §5.4 的八个不变量完整且与 F10 finding 的根因一一对应。
- 不变量 #4（任一 root request 对一个 `host_run_id` 的 turn blocks 要么全选要么全不选）直接针对根因 #1。
- 不变量 #6（repair feedback 仅满足双 digest 匹配时可消费）直接针对根因 #2。
- 不变量 #7（operation 最多产生一个 aggregate accepted/failed terminal；reactive pass 永不单独 durable accept）直接针对根因 #3。

### PASS-F09-F10-owner-table

- Plan §3 的语义 owner 表正确且与代码事实一致。
- 每个语义的唯一 owner 与实际代码位置匹配（经独立代码审查验证）。

### PASS-F08-F10-non-goal-boundary

- Plan §2.3 non-goals 清晰：不增加 heuristic、不修改 v2 schema、不新增第六类 memory、不下游补偿、不增大 cap 掩盖、不修改 Engine。
- Non-goal #3（"不修改五类 memory 的定义"）与 F08 的 replacement contract 一致——null 是清除 summary，不是增加第六类。

### PASS-F09-resolver-not-relaxed

- Plan §6 Slice F09 错误路径明确：event row 与 hot payload identity 不一致时 "formal resolver 继续抛 `HostDurableError`，测试不得软化"。
- 直接对应 `_validated_runner_call_contract`（`tool_trace.py:1039-1047`）的 strict equality check。

## Open questions

| # | 问题 | 上下文 |
|---|---|---|
| Q1 | Plan 承诺 F08 prompt 不加 "具体语言词表或长度阈值"，但 implementation agent 如何在不加阈值的情况下让 LLM 在 cap=1 时稳定输出 null？如果 prompt 只说 "若无法形成有意义的摘要则输出 null"，LLM 可能在 cap=50 时也认为 "不够有意义" 而输出 null。Prompt 需要同时说清楚 "有意义" 的**下限**——这本身是否构成一种隐式阈值？ | F08 prompt 自足性 |
| Q2 | Plan §5.2 定义 group unit 的排序是 "首个成员在现有稳定排序中的位置"。但如果 group A 的最后一个成员在 stable sort 中位于 group B 的第一个成员之前，group 归并后的 unit 顺序可能与原始 block 顺序不完全一致。是否需要在 unit 排序中明确 "取最小 sequence" 以避免跨 group 的意外重排？ | F10 group ordering |
| Q3 | Plan §6 Slice F10 步骤 C4 说 "在 request plan 构造时验证 root selection 的 selected block ids 与从同一 source_snapshot.material_blocks 投影出的 group proof 一致"。这个校验是否也需要在 dispatcher 侧做（`_execute_proactive_compaction` 在调用 `build_normal_compact_request_plan` 之后），还是仅在 operation 内部做？ | F10 validation placement |

## Residual risks

| # | 风险 | Plan 是否已记录 | 建议跟踪 |
|---|---|---|---|
| R1 | F08 的 "自然语言有意义" 仍需 real-provider Agent-in-the-loop 观察 | §12 已记录 | 后续 formal CLI scenario |
| R2 | Group-atomic policy 可能导致超大 completed Run 完全不进入 compactor | §12 已记录 | fallback regression tests |
| R3 | 给 selection/feedback 增加 internal fields 会改变 digest | §12 已记录 | fixture 从 owner helper 重新生成 |
| R4 | F09 的 provider/model identity 需后续 formal CLI scenario 证明 | §12 已记录 | 后续 formal CLI scenario |
| R5 | 当前 `select_compact_segment` 在 budget 循环中，`budget_blocked` flag 仅在 `max_selected_item_count is not None` 时设为 True（`compact_material.py:838-839`）。group-aware 改造后，oversized group 的 `budget_limit` 不应触发 `budget_blocked`（否则会错误阻止后续 singleton units）。Plan 未讨论这一点 | 未记录 | 步骤 B 实现时注意 |

## Plan review conclusion

**PASS-WITH-FIXES**

Plan 的根因分析、语义 owner 判定、架构边界和八条不变量设计是正确的。F09 修复在准确的 owner boundary 且覆盖完整路径。F10 状态机设计（§5.1–§5.3）对三个根因均有对应的 invariant 防护。

需要在 plan gate 接受前修复：

1. **Finding 1 (HIGH)**：修正 §1 和 §10 的提交边界，将三份 frozen baseline + finding artifact + plan artifact + plan-review artifacts 纳入独立 checkpoint commit
2. **Finding 2 (MEDIUM)**：补充 F08 prompt 规则的 LLM-facing 具体措辞框架或判断维度，使 implementation agent 可直接执行
3. **Finding 3 (MEDIUM)**：明确 oversized group 与 fallback 路径的衔接机制
4. **Finding 4 (MEDIUM)**：明确 selection digest 变更对 durable store 中历史 digest 引用的影响
5. **Finding 5 (MEDIUM)**：明确 selector two-pass（group-aware pre-pass + budget pass）的实现结构

Finding 6–8 为 LOW 严重程度，建议修复但不阻塞 plan gate。
