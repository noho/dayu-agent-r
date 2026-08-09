# Interactive Conversation Memory closure F08–F10：DS 第二路独立 Re-review

## Re-review identity

- **Reviewed target**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`（经 plan-fix 修订后）
- **Plan-fix artifact**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-fix-codex.md`
- **Original DS review**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-ds.md`
- **Original MiMo review**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-mimo.md`
- **Re-review type**: 独立第二路 adversarial plan re-review；基于原始 DS findings 与全部 controller decisions 逐项复核
- **Re-reviewer**: DS
- **Date**: 2026-08-04
- **Observation target**: `2e7a01678677817aafd22603f03f17605aa9e39c`
- **Base ref**: `github/main` → `113ea34d47b95812d79aa31705949bbb46bc6061`
- **Current branch**: `codex/interactive-oracle`

## Method summary

本 re-review 独立复核了以下材料：

- 修订后的 target plan：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`
- Plan-fix artifact：`docs/reviews/wu-interactive-memory-closure-f08-f10-plan-fix-codex.md`（含十一项 controller adjudication 映射）
- 原始 DS review 全部 8 条 findings（1 HIGH + 4 MEDIUM + 3 LOW）
- 原始 MiMo review 全部 5 条 findings
- 用户十一项 controller decisions
- 直接代码真源：
  - `dayu/config/prompts/scenes/conversation_compaction_user.md`（F08 prompt owner）
  - `docs/cli_init_workspace_manifest_v1.json`（publication manifest，line 40：`conversation_compaction_user.md` entry `content_sha256`）
  - `tests/cli/test_smoke_cli_init_provider_matrix.py`（line 95-97：`FROZEN_MANIFEST_SHA256`；line 387-409：`test_frozen_manifest_matches_fresh_real_publication_tree`）
  - `dayu/host/compaction_operation.py`（line 306-341：`DurableCompactorProposalManifestRecorder`；line 328-329：`payload_ref=None, payload_digest=None`）
  - `dayu/host/durable/tool_trace.py`（line 362-389：`resolve_runner_call_projection_from_signal`，line 376-379：strict null check）
  - `dayu/host/compact_material.py`（line 202：`turn_group_id`；line 780-879：`select_compact_segment` per-block budget loop；line 1788-1799：`is_turn_group_material_block`；line 1802-1824：`_block_exclusion_reason` precedence）
  - `dayu/host/compaction.py`（line 1629-1673：`CompactRepairFeedbackV2`；line 1765-1844：`CompactSegmentSelection`；line 2080-2120：`CompactionRequest.digest()`/`to_json()`）
  - `dayu/host/context_governance.py`（line 59-114：`accept_compact_candidate_v2`；line 117-166：`build_compact_repair_feedback_v2`）
  - `dayu/host/compact_pipeline.py`（line 491-572：`build_tier_recovery_request_plans`；line 741-840：`build_fallback_decision_input`）
  - `dayu/host/dispatch.py`（line 2292-2325：proactive attempt loop，line 2325：unconditional `repair_feedback = attempt_result.next_repair_feedback`）
- 根 `AGENTS.md`

每个复核项均附带直接 plan 段落引用与代码行号反例验证。

---

## 逐项复核：原始 DS HIGH/MEDIUM findings

### DS F1 (HIGH)：frozen baseline checkpoint 边界 → 已修复

- **原始 finding**: Plan §1/§10 禁止将 frozen baseline 纳入提交，导致 plan gate 接受后缺失必要 checkpoint
- **Plan-fix 裁决**: accepted；§1、§10 改为单一独立 accepted-plan checkpoint
- **修订后 plan 证据**:
  - §1 (line 13): "它们必须与本 plan、MiMo/DS 两份 plan review、plan fix、re-review、controller adjudication artifacts 一起进入同一个独立 accepted-plan checkpoint commit"
  - §10 (line 436-445): 精确列出 accepted-plan checkpoint 内容：三份 frozen baseline + plan + MiMo/DS reviews + plan-fix + re-review + controller adjudication
  - §10 (line 443): "提交信息固定使用 `gateflow: accept plan for interactive-memory-closure-f08-f10`"
  - §10 (line 444): "commit 前以精确 pathspec 核对上述 artifacts，并记录三份 baseline digest；implementation 后任何 commit 都不得改变这三个 digest"
- **直接代码验证**: `git status --short` 确认三份 baseline 存在未提交改动（`M docs/cli_ci_oracles.json`、` M docs/cli_ci_scenarios.json`、`?? docs/reviews/wu-interactive-memory-closure-f08-f10.md`），plan-fix §"Validation" (line 73-77) 已记录其三份 baseline SHA-256
- **反例测试**: 若 accepted-plan checkpoint 仅包含 plan 而不包含 baseline，则后续 implementation 无法从 committed state 验证 baseline digest。修订后 plan 已消除此 gap。
- **结论**: **PASS**

### DS F2 (MEDIUM)：F08 prompt 自足性不足 → 已修复

- **原始 finding**: Plan 只给语义目标，未给 LLM-facing 自足判断规则框架
- **Plan-fix 裁决**: accepted with controller refinement；改成无阈值业务判断维度
- **修订后 plan 证据**:
  - §6 F08 步骤 1 (line 170-176): prompt 规则现包含四条完整自足规则：
    1. "完整、脱离原会话也可独立理解的业务陈述，表达当前用户目标、已经建立的结论或进展，以及仍影响后续的关键约束或下一步；只写本次会话中实际存在且后续需要的维度"
    2. "在明确 cap 内无法形成至少一条完整业务陈述时，必须输出 JSON `null`"
    3. "禁止用占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段冒充 summary"
    4. "`null` 表示完整 replacement 中清除当前 summary，不表示保留旧 summary；其它四类 semantic sections 仍按本次 candidate 独立输出，不得因 summary 为 null 一并清空"
  - §6 F08 步骤 2 (line 177): "不加入字符数/词数阈值、语言词表、停用词、正则或 Host semantic acceptance；不使用内部 Python 类型名要求模型推断行为"
  - §6 F08 步骤 3 (line 178): "不得新增'句点或其它不合规占位符可被 Host 接受'的 negative acceptance test"
  - Prompt contract test 断言上述业务判断维度、`null` 条件、禁止项与 replacement 语义均存在
- **直接代码验证**:
  - 当前 prompt (`conversation_compaction_user.md:34-35`): `session_summary` 已有 `null` 语义说明（"null 表示本次完整 replacement 不包含 session summary；candidate 被接受后，当前会话摘要变为空，包括清除先前已接受的摘要"），但缺少"何时必须选择 null"的强制判断规则
  - AGENTS.md LLM-facing 约束 (line 45): "只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"
  - 修订后 plan 的规则框架满足 AGENTS.md 约束：有判断维度（目标/结论/约束）、有强制条件（cap 内无法形成至少一条完整陈述）、有禁止项（占位符/孤立字符/标点/截断片段）、有 replacement 语义（null 清除旧 summary，不影响其它四类）
- **反例测试**: 若 implementation agent 在 prompt 中写入 `len(text) <= 1` 或 "至少5个中文字符" 等阈值，违反 plan §6 F08 步骤 2。修订后 plan 明确禁止此类 heuristic，prompt contract test 会断言不存在。
- **结论**: **PASS**

### DS F3 (MEDIUM)：oversized group fallback 未闭环 → 已修复

- **原始 finding**: oversized group 标记 `budget_limit` 后，与 fallback 路径衔接不明确
- **Plan-fix 裁决**: finding accepted, proposed signal rejected；明确不增加 special signal
- **修订后 plan 证据**:
  - §5.2 (line 129-130): "单组本身超过 cap 时不新增 `oversized_group` signal，也不增加 selector/public schema 分支。全部 raw blocks 始终保留在同一个 frozen `source_snapshot.material_blocks` canonical snapshot；tier 1–3 只消费其原子 selection 视图，全部 compact recovery 未接受时，既有 `build_fallback_decision_input` 从完整 snapshot 构造 tier 4/5 raw-window selection 或 fail closed。不得在 selector、pipeline 或 dispatcher 静默删除该组。"
  - §6 F10 步骤 B5 (line 264): "selector 输出完整 root memberships；selection digest 包含 membership 顺序、selected/excluded disposition、scope 与 root binding"
  - §7 测试矩阵新增: "oversized group 在 tier 1–3 均为 budget_limit → 每个 selection 不 partial；原始 source_snapshot.material_blocks 仍逐项包含完整 raw group"；"oversized group + tier 1–3 全耗尽 → failed terminal 唯一；fallback owner 收到的 canonical snapshot 仍含全组 raw blocks"
- **直接代码验证**:
  - `build_fallback_decision_input` (`compact_pipeline.py:741-840`): 接收完整 `source_snapshot`，调用 `_fallback_material_blocks(source_snapshot)` 获取 full material blocks（line 771），不消费 tier 1–3 的任何 selection-filtered 视图
  - `build_tier_recovery_request_plans` (`compact_pipeline.py:491-572`): tier 1/2/3 均使用同一 `select_compact_segment` 调用从完整 `source_snapshot.material_blocks` 构造 selection，不修改 snapshot
  - 因此 oversized group 在 tier 1–3 被 `budget_limit` 后，完整 raw blocks 仍在 snapshot 中，fallback owner 可直接消费——不需要 special signal
- **反例测试**: 若有人试图在 selector 中 `del material_blocks[oversized_index]` 或构造删减版 snapshot → 违反 plan "不得在 selector、pipeline 或 dispatcher 静默删除该组"。测试矩阵的 raw-retention 与 fallback terminal owner tests 会捕获。
- **结论**: **PASS**

### DS F4 (MEDIUM)：selection digest 稳定性 / 历史 durable fact → 已修复

- **原始 finding**: 新增 group manifest 字段会改变 selection/request digest，plan 未讨论历史 durable store 中的旧 digest 引用
- **Plan-fix 裁决**: accepted；明确全新当前 schema、无旧库兼容；历史 EventLog digest 保持 immutable
- **修订后 plan 证据**:
  - §12 (line 479-484): "该变更按全新当前 schema 起库，不提供旧库兼容、旧记录重解析或 digest fallback；fixture 必须调用 production owner helper 生成当前 digest，禁止硬编码旧值"
  - §12 (line 480-481): "历史 EventLog 中已写入的 request/selection digest 是产生时的 immutable fact，新代码不得加载历史 payload 后重算并覆盖或要求其等于当前版本 digest。运行时 binding 只比较本次冻结 schedule/current request 与由该 request 产生的 feedback；不跨代码版本验证历史 digest"
  - Plan-fix §"Assumptions tested" (line 56): "新代码需要重算历史 EventLog digest保证一致 → 证伪。历史 digest 是当时产生的 immutable fact；只对当前 request做 binding"
- **直接代码验证**:
  - `CompactionRequest.digest()` (`compaction.py:2091-2097`): 使用 `sha256_digest_json(self.to_json())`，其中 `to_json()` 包含 `segment_selection.to_json()`（line 2113）。若 `CompactSegmentSelection.to_json()` 新增 `turn_group_memberships`/`scope` 字段，新代码产生的 digest 将与历史不同。
  - 修订后 plan 明确不要求跨版本匹配：历史 digest 保留为 immutable fact，新代码只比较当前 frozen schedule 下的 digest。
  - 这符合 AGENTS.md 语义所有权约束 (line 26-28)：digest 是 Host internal governance identity，其稳定性承诺是"同一代码版本、同一输入"。
- **反例测试**: 若测试 fixture 硬编码旧 digest 值而不用 production owner helper 重新生成 → 违反 plan §12。修订后 plan 明确要求 fixture 从 owner helper 重新生成。
- **结论**: **PASS**

### DS F5 (MEDIUM)：selector two-pass 欠规格 → 已修复

- **原始 finding**: group-aware pre-pass 与 budget pass 的交互未充分展开
- **Plan-fix 裁决**: accepted；明确阶段一 stable merge + collective exclusion，阶段二 eligible-only prefix budget
- **修订后 plan 证据**:
  - §5.2 (line 122-129): 完整两阶段规范：
    - 阶段一："先使用现有 `_sorted_material_blocks` 稳定排序，再归并原子 units：所有 `is_turn_group_material_block(block)` 且具有同一非空 `turn_group_id` 的 blocks 形成一个原子 unit...unit 放置在其首个成员的稳定位置"
    - 阶段一 exclusion："依次按 current-input、protected recent floor、already-represented、previous-compacted-view、not-in-segment 的既有优先级检查成员；group 任一成员命中时，全组采用最高优先级的同一 reason"
    - 阶段二："仅处理阶段一留下的 eligible units，按 unit 执行现有 prefix budget：以 unit 全部成员的 `size_units` 总和与真实 block 数一次性检查 char/item cap；完整 unit 能放入才整体选择"
  - §6 F10 步骤 B1-B3 (line 258-264): 实施步骤与两阶段对应
  - §7 测试矩阵新增: "同组成员分别命中 recent/protected/already represented，且输入顺序变化 → 阶段一按固定 precedence 得到整组统一 reason；阶段二不再检查该组，结果顺序无关"
- **直接代码验证**:
  - `_block_exclusion_reason` (`compact_material.py:1802-1824`): 已有固定优先级（current_input → protected_recent → already_represented → previous_compacted_view → not_in_segment），与 plan 精确一致
  - `_sorted_material_blocks` (`compact_material.py`): 已有稳定排序
  - `is_turn_group_material_block` (`compact_material.py:1788-1799`): 定义 turn-group 成员为 USER_INPUT / ASSISTANT_FINAL_ANSWER / ACCEPTED_TOOL_EVIDENCE
  - 当前 `select_compact_segment` (`compact_material.py:824-845`): 纯 per-block 单 pass 循环。修订后 plan 的两阶段结构是对此的实质性重构，但规格已充分明确
- **反例测试**: 若 implementation 使用 dict iteration order 而非 stable sort 确定 unit 顺序 → 测试矩阵 "输入顺序变化 → 结果顺序无关" 会捕获
- **结论**: **PASS**

### DS F7 (LOW)：group typed surface 不明确 → 已修复

- **原始 finding**: group manifest 是扩展 `CompactSegmentSelection` 还是新类型未说明
- **Plan-fix 裁决**: accepted；选择 `TurnGroupMembership` + root/transient selection scope 两个最小严格类型
- **修订后 plan 证据**:
  - §5.3 (line 133-135): "`TurnGroupMembership` 是最小独立严格类型，只包含非空 `turn_group_id` 与按 material 顺序排列的非空唯一 `member_block_ids`；selection scope 是 root/transient 闭集严格类型。二者作为 `CompactSegmentSelection` 同一个不可分割 canonical contract 的直接字段，不另建 public schema、root-proof facade 或 God helper"
  - §6 F10 步骤 A1-A2 (line 253-256): "在 `dayu/host/compaction.py` 增加最小独立严格类型 `TurnGroupMembership`"；"将 `scope`、`turn_group_memberships` 与 transient-only `root_selection_digest` 作为 `CompactSegmentSelection` 同一不可分割 contract 的直接字段"
  - §6 F10 步骤 A4 (line 257): "不实现自定义 equality/hash 兼容层；frozen dataclass 的直接字段自然参与当前对象相等性"
- **直接代码验证**:
  - `CompactSegmentSelection` (`compaction.py:1765-1844`): 当前 9 fields，均为 selection contract 的不可分割部分。新增 `scope` + `turn_group_memberships` + `root_selection_digest` 三个字段（其中 `root_selection_digest` 仅 transient 场景非空），不会使其成为 God object——它们是同一 selection contract 的直接组成
  - `TurnGroupMembership` 仅两字段（`turn_group_id: str` + `member_block_ids: tuple[str, ...]`），符合"最小独立严格类型"
- **反例测试**: 若有人创建 `RootSelectionProof` 独立 facade 类或 builder hierarchy → 违反 plan §5.3 和 §6 A。修订后 plan 明确禁止。
- **结论**: **PASS**

### DS F8 (LOW)：feedback mismatch 测试缺口 → 已修复

- **原始 finding**: dispatcher 层 mismatched feedback 的 defensive test 缺失
- **Plan-fix 裁决**: accepted；dispatcher 正常按双 digest 清空；operation mismatch 返回 failed result 不抛异常
- **修订后 plan 证据**:
  - §6 F10 步骤 D5 (line 280): "`_run_compaction_operation` 在准备 proposal 前校验任何 non-null initial feedback 的 binding；不匹配时 provider 不得调用，feedback 不得进入 prompt/input projection。operation 复用既有 non-repairable `PROPOSAL_FAILED` result/diagnostic transport，返回 `accepted_truth=None`、`next_repair_feedback=None`；不得把异常抛出 scheduler 使 Run 崩溃"
  - §6 F10 步骤 D4 (line 279): "dispatcher 每次 attempt 前比较 feedback binding 与 `attempt_plan.request` 的双 digest：都相同才传递，否则置 `None`。比较逻辑放在单一 typed helper 中，禁止按 `ROOT_REPAIR`/tier 名称硬编码"
  - §7 测试矩阵新增两行:
    - "直接注入 mismatch feedback → provider 未调用；返回 non-repairable failed result，无 next feedback、无异常逃逸"
    - "通过 test seam 让 mismatch feedback 到达 operation → operation fail closed 后 schedule 停止；只写一个 `CONTEXT_COMPACTION_FAILED`，随后走既有 raw-window dispatch 或 fail closed；Run 不因未捕获异常崩溃"
- **直接代码验证**:
  - 当前 `dispatch.py:2325`: `repair_feedback = attempt_result.next_repair_feedback` 无条件传递
  - 当前 `_run_compaction_operation` (`compaction_operation.py:743-756`): 接收 `initial_repair_feedback` 参数，但无 binding digest 校验
  - 修订后 plan 的 defensive 设计覆盖了 dispatcher 层（digest comparison helper）和 operation 层（provider 前校验），并确保 operation 返回 failed result 而非抛异常 → dispatcher 停止 schedule 走既有 `_append_compaction_failed_with_proactive_fallback` → 单一 terminal/fallback
- **反例测试**: 若 operation 对 mismatch feedback 抛出 `ValueError`/`HostDurableError` → 异常可能逃逸 `_execute_proactive_compaction` 的 attempt loop，绕过 `_append_compaction_failed_with_proactive_fallback`，导致 Run 崩溃或无 terminal。测试矩阵的 defensive scheduler test 会捕获。
- **结论**: **PASS**

---

## 逐项复核：Controller decisions

| Controller decision | Plan-fix 映射 | 修订后 plan 证据 | 复核结论 |
|---|---|---|---|
| DS F1 / MiMo F1: baseline checkpoint | accepted | §1 + §10 单一 accepted-plan checkpoint | PASS |
| DS F2: F08 prompt 自足性 | accepted with refinement | §6 F08 步骤 1-3 完整业务维度规则 | PASS |
| MiMo F4: 句点 negative test | rejected | §6 F08 步骤 3 明确禁止 | PASS |
| DS F6 / controller F08 consumer: manifest + init smoke | accepted | §6 F08 步骤 5 + allowed files + validation commands | PASS |
| MiMo F2: F09 hot payload 描述歧义 | accepted | §4.2 + §6 F09 步骤 1 明确 inline | PASS |
| MiMo F5: F09/F10 sequencing | accepted in part (rebase rejected) | §6 Slice F10 开头 + §10: 固定先 F09 后 F10，不执行 rebase | PASS |
| DS F3: oversized group fallback | finding accepted, proposed signal rejected | §5.2 + §6 B/C: 不增加 signal，snapshot 保留完整 raw blocks | PASS |
| DS F5: selector two-pass | accepted | §5.2 + §6 B: 阶段一 stable merge + collective exclusion，阶段二 eligible-only prefix budget | PASS |
| DS F7: group typed surface | accepted | §5.3 + §6 A: `TurnGroupMembership` + scope 作为 `CompactSegmentSelection` 直接字段 | PASS |
| DS F4 / MiMo F3: digest 变化 | accepted | §12: 全新当前 schema，历史 immutable fact | PASS |
| DS F8: mismatch defensive | accepted | §6 D5: operation failed result 不抛异常，dispatcher 停止 schedule → 单一 terminal | PASS |

全部十一项 controller decisions 均在修订 plan 中有精确对应。

---

## 重点逐项复核

### 1. 单一 accepted-plan checkpoint 精确范围

- **Plan §10 (line 436-445)**: checkpoint 精确包含 (1) 三份 frozen baseline、(2) plan、(3) MiMo/DS reviews、(4) plan-fix、(5) re-review + controller adjudication artifacts
- **Plan §1 (line 13)**: 明确 "implementation 开始后这三份 baseline 的 SHA-256 永不改变，也不得被覆盖或格式化"
- **Plan §10 (line 444)**: "implementation 后任何 commit 都不得改变这三个 digest"
- **反例**: 若有人将 baseline 与 implementation 混入同一 commit → baseline digest verification 失去独立锚点。修订后 plan 的独立 checkpoint + 后续不变承诺消除了此风险。
- **结论**: **PASS**

### 2. F08 业务陈述规则自足但无字符/词表 heuristic

- **Plan §6 F08 步骤 1 (line 170-176)**: 四条完整自足规则覆盖业务判断维度（当前目标、已建立结论/进展、仍影响后续的关键约束/下一步）、null 条件（cap 内无法形成至少一条完整陈述）、禁止项（占位符/孤立字符/标点/截断片段）、replacement 语义（null 清除旧 summary，不影响其它四类）
- **Plan §6 F08 步骤 2 (line 177)**: "不加入字符数/词数阈值、语言词表、停用词、正则或 Host semantic acceptance"
- **Plan §2.3 Non-goal 1 (line 35-36)**: "不增加基于字符、词表、语言或模式匹配的'有意义摘要' heuristic；Host 不承担自然语言意义判定"
- **反例**: 若 prompt 中出现 "至少5个中文字符"、"不得少于10个字符"、"必须包含动词" 等 → 违反 plan §6 F08 步骤 2 和 §2.3 Non-goal 1。Prompt contract test 断言不存在此类规则。
- **结论**: **PASS**

### 2b. Publication manifest SHA 与 init smoke consumer

- **Plan §6 F08 步骤 5 (line 179)**: "对最终 prompt raw bytes 计算 SHA-256，只更新 `docs/cli_init_workspace_manifest_v1.json` 中 `config/prompts/scenes/conversation_compaction_user.md` 的唯一 `content_sha256`；再计算 manifest raw SHA-256，并只更新 `tests/cli/test_smoke_cli_init_provider_matrix.py` 的 `FROZEN_MANIFEST_SHA256`。不得改其它 asset entry、目录集合、manifest schema 或动态生成 expected"
- **直接代码验证**:
  - `docs/cli_init_workspace_manifest_v1.json:40`: `conversation_compaction_user.md` 的 `content_sha256` 为 `"a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce"`——prompt 修改后必须更新
  - `tests/cli/test_smoke_cli_init_provider_matrix.py:95-97`: `FROZEN_MANIFEST_SHA256 = "fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c"`——manifest 修改后必须更新
  - `test_frozen_manifest_matches_fresh_real_publication_tree` (line 387-409): 验证冻结 manifest 与真实 package 副本完全匹配——确保 manifest SHA 与 actual tree 一致
  - 这个 consumer chain 是: prompt raw bytes → manifest asset `content_sha256` → manifest raw `FROZEN_MANIFEST_SHA256` → init smoke test 断言。Plan 正确识别并只更新这两个值。
- **反例**: 若 implementation 只改 prompt 但忘记更新 manifest SHA → `test_frozen_manifest_matches_fresh_real_publication_tree` 断言 `report.valid` 会失败（digest mismatch）。若只更新 manifest 但忘记更新 `FROZEN_MANIFEST_SHA256` → `test_checked_in_manifest_digest_is_stable_across_validation` (line 725-748) 断言 `digest_before == FROZEN_MANIFEST_SHA256` 会失败。
- **结论**: **PASS**

### 3. F09 EventLog row descriptor 同源

- **Plan §4.2 (line 89-90)**: 直接根因为 `compaction_operation.py:328-329` 显式写 `payload_ref=None, payload_digest=None`，而 hot JSON（line 323-326）已正确使用 `manifest_descriptor.payload_ref` 与 `manifest_digest`
- **Plan §6 F09 步骤 1 (line 206-209)**: 修复为 `payload_ref` 使用 `manifest_descriptor.payload_ref`，`payload_digest` 使用 `manifest_digest`；hot JSON 继续 inline 完整 manifest body 并携带相同 ref/digest；禁止二次计算另一份 manifest
- **Plan §6 F09 步骤 3 (line 211)**: "保持 Tool Trace projector 机械投影、formal resolver 严格 equality check 和 payload descriptor 校验不变"
- **直接代码验证**:
  - `compaction_operation.py:323-326`: hot payload 已含 `manifest_payload_ref=manifest_descriptor.payload_ref, manifest_digest=manifest_digest`
  - `compaction_operation.py:328-329`: `payload_ref=None, payload_digest=None` ← 根因
  - `tool_trace.py:376-379`: `resolve_runner_call_projection_from_signal` 严格检查 `signal.manifest_ref is None` 和 `signal.manifest_digest is None` 时抛 `HostDurableError`
  - 修复后四端同源: manifest descriptor → EventLog row descriptor → hot JSON → Tool Trace hot row → formal resolver
- **反例**: 若有人改为 hot JSON 只存 descriptor ref（indirection）而不 inline manifest body → 违反 plan §6 F09 步骤 1。若有人放松 resolver 的 `==` check → 违反 plan §6 F09 错误路径。
- **结论**: **PASS**

### 4. F10 typed surface 最小

- **Plan §5.3 (line 133-135)**: `TurnGroupMembership` 只含两字段（`turn_group_id: str` + `member_block_ids: tuple[str, ...]`），scope 是 `root`/`transient` 二值闭集。二者作为 `CompactSegmentSelection` 直接字段，不新建 public schema、root-proof facade、builder hierarchy 或 God helper
- **Plan §6 F10 步骤 A4 (line 257)**: "不实现自定义 equality/hash 兼容层；frozen dataclass 的直接字段自然参与当前对象相等性"
- **直接代码验证**:
  - `CompactSegmentSelection` (`compaction.py:1765`): 当前 9 个 frozen fields，均为 selection contract 不可分割部分。新增 3 个字段（`scope`、`turn_group_memberships`、`root_selection_digest`）不会使其成为 God object
  - AGENTS.md §编码硬约束 (line 85): "禁止 God object、God function、God dataclass、god bag、god builder" — 12 个字段的 frozen dataclass 不违反此约束，因为所有字段都是同一 selection contract 的直接组成
- **反例**: 若有人创建 `RootSelectionProof` 独立类 + `RootSelectionProofBuilder` + `ProofValidator` 三层 hierarchy → 违反 plan §5.3。修订后 plan 明确禁止。
- **结论**: **PASS**

### 5. F10 两阶段 group selection

- **Plan §5.2 (line 122-129)**: 阶段一 stable sort → merge atomic units → collective exclusion per unit；阶段二 eligible-only prefix budget
- **Plan §6 F10 步骤 B1-B4 (line 258-264)**: 实施步骤明确对应两阶段，使用私有 helper 而非嵌套函数
- **Plan §7 测试矩阵**: 覆盖 group 内成员不同 exclusion 状态的顺序无关测试
- **直接代码验证**:
  - `_block_exclusion_reason` (`compact_material.py:1802-1824`): 固定优先级 current_input → protected_recent → already_represented → previous_compacted_view → not_in_segment，与 plan 精确一致
  - `is_turn_group_material_block` (`compact_material.py:1788-1799`): USER_INPUT / ASSISTANT_FINAL_ANSWER / ACCEPTED_TOOL_EVIDENCE 三类
  - `_sorted_material_blocks` 已提供稳定排序
  - 现有 `select_compact_segment` 的单 pass 循环需重构为两阶段，但现有 helper 可复用
- **反例**: 若 implementation 在阶段二使用 dict iteration order 确定 unit 顺序 → 测试矩阵的 "输入顺序变化 → 结果顺序无关" 会捕获
- **结论**: **PASS**

### 6. F10 strict prefix cap

- **Plan §5.2 (line 127-128)**: "首个放不下的 eligible unit（包括自身大于 cap 的首组）全部成员标记 `budget_limit`，selection 保持空或保持此前已选 prefix；随后所有 eligible units 也标记 `budget_limit`"
- **Plan §5.2 (line 128)**: "不得为了'至少选一项'突破 cap、增大 cap、拆 group 或绕过大组选择后续小组"
- **Plan §5.2 (line 129)**: "char/item cap 仍是上限：item cap 按真实 block 数计数"
- **直接代码验证**:
  - 当前 `select_compact_segment` (`compact_material.py:832-836`): `if max_selected_size_units is not None and selected_units + block.size_units > max_selected_size_units and (len(selected) > 0 or max_selected_item_count is not None)` — 当 `max_selected_item_count is None` 且 `len(selected) == 0` 时，首个 block 可越过 size cap（首项豁免）
  - 修订后 plan 删除此豁免空间：首个 group 自身超过 cap 时同样不选
- **反例**: 若 implementation 保留首项豁免 → 单个 oversized block 可越过 char cap 进入 selection，违反 plan strict prefix cap。测试矩阵 "首个完整 group 超过 char 或 item cap → selection 为空" 会捕获。
- **结论**: **PASS**

### 7. F10 oversized raw snapshot retention 到既有 fallback

- **Plan §5.2 (line 129-130)**: "全部 raw blocks 始终保留在同一个 frozen `source_snapshot.material_blocks` canonical snapshot；tier 1–3 只消费其原子 selection 视图...不得在 selector、pipeline 或 dispatcher 静默删除该组"
- **Plan §6 F10 步骤 C5 (line 264)**: "tier 1–3 即使反复将 oversized group 标为 `budget_limit`，完整 raw group 仍在 snapshot 中；compact recovery 耗尽后只能把同一 snapshot 交给现有 tier 4/5 raw-window/fail-closed owner，不能构造删减 snapshot"
- **直接代码验证**:
  - `build_tier_recovery_request_plans` (`compact_pipeline.py:508-517`): 从 `source_snapshot.material_blocks` 调用 `select_compact_segment`，不修改 snapshot
  - `build_fallback_decision_input` (`compact_pipeline.py:741-840`): 接收完整 `source_snapshot`，调用 `_fallback_material_blocks(source_snapshot)`（line 771），消费完整 material blocks，不依赖 tier selection
  - 因此 oversized group 在 tier 1–3 全部 `budget_limit` 后，fallback owner 仍可访问完整 raw blocks
- **反例**: 若有人将 tier 1–3 的 filtered selection 传为 fallback input → oversized group 的 raw blocks 丢失。测试矩阵 "fallback owner 收到的 canonical snapshot 仍含全组 raw blocks" 会捕获。
- **结论**: **PASS**

### 8. F10 fresh schema digest

- **Plan §12 (line 479-484)**: "该变更按全新当前 schema 起库，不提供旧库兼容、旧记录重解析或 digest fallback；fixture 必须调用 production owner helper 生成当前 digest，禁止硬编码旧值"
- **Plan §12 (line 480-481)**: "历史 EventLog 中已写入的 request/selection digest 是产生时的 immutable fact，新代码不得加载历史 payload 后重算并覆盖或要求其等于当前版本 digest"
- **直接代码验证**:
  - `CompactionRequest.digest()` (`compaction.py:2091-2097`): 使用 `sha256_digest_json(self.to_json())`。`to_json()` 包含 `segment_selection.to_json()`（line 2113）。新字段加入 `to_json()` 后 digest 自动变化——这是预期行为
  - `CompactRepairFeedbackV2` 当前 `to_json()` (`compaction.py:1662-1673`): 不含 `request_digest`/`source_boundary_digest`。新字段加入 `to_json()` 后序列化变化——plan 明确按全新 schema 起库
- **反例**: 若测试 fixture 硬编码 `"selection_digest": "abc123..."` 旧值而不从 production owner helper 实时生成 → 违反 plan §12。修订后 plan 明确要求 fixture 从 owner helper 重新生成。
- **结论**: **PASS**

### 9. F10 feedback 双 digest

- **Plan §5.1 (line 112-118)**: 每个 attempt plan 冻结 `request_digest` 与 `source_boundary_digest`；下一 attempt 双 digest 均与 feedback 完全相同时才可传入；tier 名称不能替代 digest 比较
- **Plan §6 F10 步骤 D1-4 (line 276-279)**:
  - D1: `CompactionRequest.source_boundary_digest()` 只对 immutable `compact_input.source_boundary` 的 canonical JSON 计算 SHA-256
  - D2: `CompactRepairFeedbackV2` 增加非空 `request_digest` 与 `source_boundary_digest`，纳入 `to_json()`；治理 digest 不暴露为 LLM 业务事实
  - D3: `build_compact_repair_feedback_v2` 显式接收当前 request 的双 digest
  - D4: dispatcher 比较双 digest 后才传递 feedback；比较在单一 typed helper 中，不按 tier 名称硬编码
- **直接代码验证**:
  - `CompactionRequest.compact_input` property (`compaction.py:2130-2131`): 返回 `CompactInputV2`，其 `source_boundary` 是 immutable tuple
  - `dispatch.py:2292` (`repair_feedback: CompactRepairFeedbackV2 | None = None`): 当前在 attempt loop 中无条件赋值
  - 修订后 plan 的 typed helper 比较双 digest 后决定清空/传递，消除了当前无条件传递的根因
- **反例**: 若 dispatcher 按 `ROOT_REPAIR` stage 名称硬编码 feedback 传递 → 违反 plan §6 D4。测试矩阵 "root repair → tier 1；tier 1 → section-degraded tier 2" 验证 feedback 为 None。
- **结论**: **PASS**

### 10. F10 mismatch 不异常逃逸

- **Plan §5.1 (line 117-118)**: "operation 收到非空 feedback 时再次验证双 digest；不匹配视为 caller contract violation，禁止把 feedback 投影给 LLM 或写入 proposal input projection"
- **Plan §6 F10 步骤 D5 (line 280)**: "不匹配时 provider 不得调用，feedback 不得进入 prompt/input projection。operation 复用既有 non-repairable `PROPOSAL_FAILED` result/diagnostic transport，返回 `accepted_truth=None`、`next_repair_feedback=None`；不得把异常抛出 scheduler 使 Run 崩溃"
- **Plan §6 F10 步骤 E4 (line 287)**: "boundary invariant failure 不新增 durable terminal/schema 分支：使用既有 non-repairable operation failure transport"
- **直接代码验证**:
  - `_run_compaction_operation` (`compaction_operation.py:743`): 返回值类型为 `CompactionOperationResult`，其中 `accepted_truth=None` 表示失败
  - `_execute_proactive_compaction` (`dispatch.py:2280`): 在 attempt loop 中调用 `run_compaction_attempt`（line 2294），loop 结束后通过 `_operation` 闭包写 terminal（line 2339+）
  - 若 operation 抛出未捕获异常 → `_execute_proactive_compaction` 的 attempt loop 中断 → `_operation` 闭包不执行 → 无 terminal，Run 崩溃
  - 修订后 plan 的 defensive design：operation 返回 failed result（不抛异常）→ dispatcher 识别 non-repairable → 停止 schedule → 走 `_append_compaction_failed_with_proactive_fallback` → 单一 terminal
- **反例**: 若 operation 对 mismatch feedback 抛出 `ValueError("feedback digest mismatch")` → 异常逃逸 attempt loop → `accepted_result is None` → `raise RuntimeError("proactive attempt execution produced no result")` at line 2328-2329 → Run 崩溃。测试矩阵的 defensive test 会捕获。
- **结论**: **PASS**

### 11. F10 operation root durable guard

- **Plan §5.3 (line 133-140)**: 完整 root selection contract 含 `TurnGroupMembership` 与 scope；root selection 验证每个 group 全部成员二分（全部 selected 或全部 excluded），不得交叉；reactive transient pass 标记为 operation-private，绑定 root selection digest；aggregate 后再次验证 root boundary 完整性；失败复用既有 non-repairable transport
- **Plan §6 F10 步骤 E1-4 (line 284-287)**:
  - E1: 单一 root-boundary validator，验证 root scope、memberships 完整二分、selected ids 同源、turn-group 不 partial
  - E2: 构造期 + durable accept 前双重验证
  - E3: 有 reactive pass queue 时只验证原始 root request；pass truths 为 transient
  - E4: boundary invariant failure 使用既有 non-repairable transport；不产生 semantic repair feedback；不持久化 accepted artifact/Memory；dispatcher 停止 schedule → 单一 failed terminal/fallback
- **直接代码验证**:
  - 当前 `_run_compaction_operation` 的 aggregate revalidation 使用 `accept_compact_candidate_v2`（line 991-995），该函数验证 label/kind/coverage/duplicate/contradiction/information/policy，但**不验证** turn-group 完整性——这正是 F10 根因 #3
  - 修订后 plan 在 aggregate revalidation 前增加独立的 root-boundary validator，关闭此 gap
- **反例**: 若 validator 只检查 `selected_block_ids` 内部 coverage 而不验证 turn-group membership 二分 → F10 未关闭。测试矩阵 "伪造 partial root selection proof → root guard 阻止 durable acceptance" 会捕获。
- **结论**: **PASS**

---

## 全文 adversarial checklist 复核

对照 plan §11 (line 455-471) 逐项复核：

| # | Checklist item | Plan 自身答复 | DS 独立复核 |
|---|---|---|---|
| 1 | 是否有人尝试用 `len(text) <= 1`、ASCII、词表或正则把 F08 伪装成 deterministic semantic validation？ | 否 | **确认**：§6 F08 步骤 2 明确禁止字符/词表/停用词/正则/Host semantic acceptance |
| 2 | 是否新增了 Host 接受句点/占位符的 negative test？ | 否 | **确认**：§6 F08 步骤 3 明确禁止 "句点或其它不合规占位符可被 Host 接受" 的 negative acceptance test |
| 3 | `null` 是否真正删除旧 summary？ | 是（Memory owner test） | **确认**：§6 F08 步骤 4 的 Memory owner test（prior summary + accepted null + 四类保留 + reload 一致）覆盖 replacement contract |
| 4 | F09 是否只让 synthetic projector test 通过？ | 否 | **确认**：§6 F09 步骤 4 使用 durable recorder → EventLog → projector → formal resolver 完整链路 |
| 5 | F09 是否通过放松 mismatch check 通过？ | 否 | **确认**：§6 F09 错误路径明确 "resolver 继续抛 `HostDurableError`，测试不得软化" |
| 6 | group selector 是否把一个 group 计作一个 item？ | 否 | **确认**：§5.2 "item cap 按真实 block 数计数，char cap 按成员 size_units 求和；不得把 group 算成一个 item" |
| 7 | selector 是否在大组放不下后跳过它选择更晚小组？ | 否 | **确认**：§5.2 "首个放不下的 eligible unit...随后所有 eligible units 也标记 budget_limit" |
| 8 | oversized group 是否触发专用 signal、新 cap、group 拆分或从 source snapshot 删除？ | 否 | **确认**：§5.2 "不新增 `oversized_group` signal，也不增加 selector/public schema 分支" |
| 9 | already-represented/protected 状态是否导致同组成员不同 disposition？ | 否 | **确认**：§5.2 "group 任一成员命中时，全组采用最高优先级的同一 reason" |
| 10 | feedback 是否按 stage 名而非双 digest 绑定？ | 否 | **确认**：§6 D4 "禁止按 ROOT_REPAIR/tier 名称硬编码" |
| 11 | repair feedback 的治理 digest 是否被投影进 LLM prompt？ | 否 | **确认**：§6 D2 "治理 digest 不暴露为业务事实" |
| 12 | reactive pass 是否因 root atomic contract 被错误禁止？ | 否 | **确认**：§5.3 "Reactive multi-pass selection 明确标记为 operation-private transient pass" |
| 13 | operation guard 是否只验证 reduced tier boundary？ | 否 | **确认**：§6 E 增加 root group proof 验证 |
| 14 | feedback mismatch 是否以异常逃逸 scheduler？ | 否 | **确认**：§6 D5 "不得把异常抛出 scheduler 使 Run 崩溃" |
| 15 | accepted artifact/Memory/Tool Trace/RunInput 是否可能各自重算？ | 否 | **确认**：§5.4 不变量 #8 "均从 accepted root truth 和 canonical manifest 真源派生" |

全部 15 项 checklist 均通过独立复核。

---

## 新增 material findings

经对修订 plan 的完整独立复核，**未发现新的 material finding**。原 DS review 的全部 HIGH/MEDIUM findings 均已在 plan-fix 中正确修复，所有 controller decisions 均已精确映射到修订 plan 的具体段落。

---

## Final re-review conclusion

**PASS**

修订 plan 已覆盖全部 accepted findings 和 controller decisions；F08 业务规则自足且无字符/词表 heuristic、publication manifest SHA 与 init smoke consumer 链正确；F09 EventLog row descriptor 同源修复在正确的 owner boundary；F10 typed surface 最小、两阶段 group selection 规格完整、strict prefix cap 无首项豁免、oversized raw snapshot 通过既有 fallback 闭环、fresh schema digest 无旧库兼容、feedback 双 digest 绑定 typed helper、mismatch 不异常逃逸、operation root durable guard 双重防线。

每项复核均有直接 plan 段落引用与代码行号反例验证。未发现可给出直接反例的 plan defect。
