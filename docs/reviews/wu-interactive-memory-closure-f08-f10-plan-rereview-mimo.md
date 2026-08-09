# Plan Re-Review：Interactive Conversation Memory closure F08–F10

- **Reviewed target**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`（plan-fix 修订版）
- **Review type**: MiMo 独立 plan re-review；逐项验证 accepted findings 已关闭
- **Review timestamp**: `20260804-160533`
- **Reviewer**: AgentMiMo
- **Scope**: baseline 单一 checkpoint、F08 无 heuristic 且 prompt/manifest/hash consumer 闭环、F09 row/hot 同源、F10 两阶段原子 selector、oversized raw retention、digest 新 schema 边界、feedback defensive failure 与 operation root barrier
- **References**:
  - `AGENTS.md`（根约束）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`（frozen finding）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`（修订 plan）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-mimo.md`（原 MiMo review）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-review-ds.md`（原 DS review）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-fix-codex.md`（plan fix）
  - 生产代码真源：`compaction_operation.py`、`compact_material.py`、`compact_pipeline.py`、`compaction.py`、`dispatch.py`、`tool_trace.py`、`conversation_compaction_user.md`、`context_governance.py` 及对应测试
  - `docs/cli_init_workspace_manifest_v1.json`、`tests/cli/test_smoke_cli_init_provider_matrix.py`

---

## 验证方法

独立读取修订 plan 全文、原 MiMo/DS review 全部 findings、plan-fix 裁决表、AGENTS.md 约束、以及直接 owner 代码行号级验证。逐项对照 accepted findings 是否在修订 plan 中有明确关闭；对 rejected findings 验证 plan 正确拒绝且未引入不合规内容。

---

## Accepted Findings 逐项关闭验证

### 1. DS F1 / MiMo F1：frozen baseline 提交边界

- **原问题**: §10 未将三份 frozen baseline 纳入 accepted-plan checkpoint commit；plan 显式排除 baseline 进入提交。
- **修订 plan 关闭方式**: §1 (line 13) 明确 "它们必须与本 plan、MiMo/DS 两份 plan review、plan fix、re-review、controller adjudication artifacts 一起进入同一个独立 accepted-plan checkpoint commit"。§10 (lines 436-444) 列出精确包含项并声明 "不得先拆出 baseline commit、plan commit 或 review commit"。
- **代码事实交叉验证**: `git status` 当前 `docs/cli_ci_oracles.json`（staged）和 `docs/cli_ci_scenarios.json`（unstaged）有未提交改动；`docs/reviews/wu-interactive-memory-closure-f08-f10.md` 为 untracked。§10 要求这些全部进入单一 checkpoint commit，后续 implementation 不改变其 SHA-256。
- **关闭状态**: ✅ 已关闭。

### 2. DS F2：F08 prompt 自足性不足

- **原问题**: plan 只描述语义目标，未给 implementation agent 提供足够具体的 LLM-facing 规则框架。
- **修订 plan 关闭方式**: §5.4 (lines 170-175) 增加四条业务判断维度——"完整、可独立理解的业务陈述"覆盖 "实际相关的当前目标、已建立的结论或进展、仍影响后续的关键约束或下一步"；明确 "cap 内无法形成至少一条完整业务陈述时必须输出 JSON null"；明确禁止 "占位符、孤立字符、孤立标点、无上下文缩写或任何截断片段"。F08 实施步骤 1 (lines 170-175) 将上述规则列为 "单一、自足、面向模型的动作要求"。
- **AGENTS.md 约束验证**: LLM-facing 约束要求 "只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"。修订 plan 的规则框架满足该要求——给出了判断维度（目标/结论/约束/下一步）、null 条件（无法形成至少一条）、禁止项（占位符/孤立字符/标点/缩写/截断），且不依赖内部类型名或 Host 实现术语。
- **关闭状态**: ✅ 已关闭。

### 3. MiMo F4：用 Host negative test 固化句点可接受（rejected）

- **原建议**: 在 F08 测试矩阵中增加 negative case 证明 Host deterministic validator 接受 `"."`。
- **plan-fix 裁决**: rejected。明确禁止 Host 自然语言 heuristic，也禁止新增 "句点/占位符可接受" 的 negative acceptance test。
- **修订 plan 体现**: F08 步骤 3 (line 177): "不得新增'句点或其它不合规占位符可被 Host 接受'的 negative acceptance test"。§11 adversarial checklist (line 458): "是否新增了 Host 接受句点/占位符的 negative test？若是，拒绝"。
- **约束合规验证**: AGENTS.md 禁止在下游消费者用 fallback/特例补救错误语义。Host 接受句点的 negative test 会把不合规 LLM 输出固化为可接受 contract，违反 LLM-facing 约束。Plan 正确拒绝。
- **关闭状态**: ✅ 正确拒绝，plan 未引入不合规内容。

### 4. DS F6 / controller F08 consumer：config README 证据与 prompt publication digest

- **原问题**: F08 修改 `dayu/config/` 下文件但 §9 未读取 `dayu/config/README.md` 更新约束；prompt 修改缺少 publication manifest digest 同步。
- **修订 plan 关闭方式**: F08 allowed files (line 162) 新增 `docs/cli_init_workspace_manifest_v1.json` 与 `tests/cli/test_smoke_cli_init_provider_matrix.py`。§9 (line 426) 明确 "已读取开篇职责并判定不更新：该 README 只拥有默认配置、workspace 覆盖关系与 prompts 目录职责"。F08 步骤 5 (line 179) 指定 prompt raw bytes SHA-256 → manifest asset SHA → manifest raw SHA → `FROZEN_MANIFEST_SHA256` 的同步链。
- **代码事实交叉验证**:
  - `docs/cli_init_workspace_manifest_v1.json` line 40 含 `conversation_compaction_user.md` 的 `content_sha256`。
  - `tests/cli/test_smoke_cli_init_provider_matrix.py` line 95-97 含 `FROZEN_MANIFEST_SHA256`。
  - Focused validation (lines 347-351) 包含 `sha256sum` 核对与 JSON tool 验证。
- **关闭状态**: ✅ 已关闭。prompt → manifest → frozen hash 闭环完整。

### 5. MiMo F2：F09 hot payload 描述歧义

- **原问题**: plan "hot payload 也使用该 descriptor" 表述让 implementation agent 可能误以为 hot payload 通过 descriptor indirection 引用 manifest。
- **修订 plan 关闭方式**: §4.2 (lines 87-89) 明确 "hot JSON inline 完整 manifest body，并携带该 descriptor 的 manifest_payload_ref/manifest_digest；EventLog row descriptor 同时使用完全相同的 ref/digest"。F09 步骤 1 (line 209) 明确 "hot JSON 继续 inline 完整 manifest body"。
- **代码事实交叉验证**: `compaction_operation.py:323-327` 调用 `_compactor_runner_call_hot_payload(manifest=manifest, manifest_payload_ref=..., manifest_digest=...)`，hot payload 内含 manifest body + ref/digest 字段。EventLog row 的 `payload_ref=None, payload_digest=None`（lines 328-329）是待修复 bug。Plan 修复方向正确：将 row 级设为同一 ref/digest。
- **关闭状态**: ✅ 已关闭。

### 6. MiMo F5：F09/F10 allowed files 重叠 sequencing

- **原问题**: 两个 slice 共享 `compaction_operation.py` 和 `test_dispatch_scheduler.py`，plan 未说明合并策略。
- **修订 plan 关闭方式**: F10 开头 (line 230) 明确 "实施顺序固定为先 F09、后 F10；F10 从已接受的 F09 checkpoint 继续，不执行 rebase，不回写或拆改 F09 commit"。
- **约束合规验证**: controller 明确禁止 rebase。Plan 不建议 rebase，使用固定顺序 checkpoint 隔离。
- **关闭状态**: ✅ 已关闭。

### 7. DS F3：oversized group fallback 路径未闭环

- **原问题**: plan 描述 "整组不选" 但未闭环到 dispatcher/fallback 衔接；DS 建议增加 `oversized_group_block_ids` 信号。
- **plan-fix 裁决**: finding accepted, proposed signal rejected。不增加 special signal。
- **修订 plan 关闭方式**: §5.2 (lines 128-129) 明确 "不新增 oversized_group signal，也不增加 selector/public schema 分支。全部 raw blocks 始终保留在同一个 frozen source_snapshot.material_blocks canonical snapshot；tier 1–3 只消费其原子 selection 视图，全部 compact recovery 未接受时，既有 build_fallback_decision_input 从完整 snapshot 构造 tier 4/5 raw-window selection 或 fail closed。不得在 selector、pipeline 或 dispatcher 静默删除该组"。
- **代码事实交叉验证**: `compact_pipeline.py:491-572` 的 `build_tier_recovery_request_plans` 三个 tier 使用同一 `select_compact_segment` 调用。Frozen `source_snapshot.material_blocks` 在整个 pipeline 中不被修改——selector 只产出 selection view，不修改输入 snapshot。
- **关闭状态**: ✅ 已关闭。oversized group 通过 budget_limit + frozen snapshot + 既有 tier 4/5 owner 闭环，无需新信号。

### 8. DS F5：selector two-pass 欠规格

- **原问题**: plan 只说 "用模块级私有 helper 将已排序 blocks 归并为原子 units"，未说明 two-pass 结构。
- **修订 plan 关闭方式**: §5.2 (lines 122-127) 明确两阶段——阶段一 "使用现有 `_sorted_material_blocks` 稳定排序，再归并原子 units" 并 "同时计算 collective exclusion"；阶段二 "仅处理阶段一留下的 eligible units，按 unit 执行现有 prefix budget"。Reason precedence 固定为 "current-input → protected recent floor → already-represented → previous-compacted-view → not-in-segment"。
- **代码事实交叉验证**: 当前 `select_compact_segment`（`compact_material.py:824-846`）是单 pass per-block 循环。`_block_exclusion_reason`（`compact_material.py:1802-1824`）的 reason precedence 与 plan 一致。Plan 的 two-phase 改造在此基础上增加 group-aware pre-pass。
- **关闭状态**: ✅ 已关闭。

### 9. DS F7：group typed surface 不明确

- **原问题**: `CompactSegmentSelection` 已有 11 fields，plan 未明确是扩展还是新建类型。
- **修订 plan 关闭方式**: F10 步骤 A (lines 253-256) 明确 "TurnGroupMembership 是最小独立严格类型，只包含非空 turn_group_id 与按 material 顺序排列的非空唯一 member_block_ids；selection scope 是 root/transient 闭集严格类型。二者作为 CompactSegmentSelection 同一个不可分割 canonical contract 的直接字段，不另建 public schema、root-proof facade 或 God helper"。
- **AGENTS.md 约束验证**: "禁止 God dataclass"。Plan 的方案是将两个最小类型作为现有 contract 的直接字段，不增加 God helper 或 builder hierarchy，符合约束。
- **关闭状态**: ✅ 已关闭。

### 10. DS F4 / MiMo F3：digest 变化与历史 durable fact

- **原问题**: selection/request digest 组成变更可能破坏 durable store 中的历史 digest 引用。
- **修订 plan 关闭方式**: §12 (lines 479-480) 明确 "给 selection 与 repair feedback 增加 typed canonical fields 会自然改变新 request/selection digest。该变更按全新当前 schema 起库，不提供旧库兼容、旧记录重解析或 digest fallback"。"历史 EventLog 中已写入的 request/selection digest 是产生时的 immutable fact，新代码不得加载历史 payload 后重算并覆盖或要求其等于当前版本 digest。运行时 binding 只比较本次冻结 schedule/current request 与由该 request 产生的 feedback；不跨代码版本验证历史 digest"。
- **AGENTS.md 约束验证**: "一律按全新 schema 起库处理；禁止旧库兼容读取、兼容测试"。Plan 的 fresh schema + historical immutable 策略完全符合。
- **关闭状态**: ✅ 已关闭。

### 11. DS F8：mismatch 只在 operation 抛错会使 Run 崩溃

- **原问题**: `_run_compaction_operation` 的 feedback digest mismatch 若以异常抛出，可能逃逸 scheduler 导致 Run 崩溃。
- **修订 plan 关闭方式**: F10 步骤 D5 (lines 280-281) 明确 "operation 复用既有 non-repairable PROPOSAL_FAILED result/diagnostic transport，返回 accepted_truth=None、next_repair_feedback=None；不得把异常抛出 scheduler 使 Run 崩溃"。步骤 E4 (line 287) 明确 "使用既有 non-repairable operation failure transport"。§11 checklist (line 470): "feedback mismatch 是否以异常逃逸 scheduler、造成 Run 崩溃或产生多个 terminal？若是，不接受"。
- **代码事实交叉验证**: `dispatch.py:2325` 当前无条件传递 `next_repair_feedback`，无 digest 校验。Plan 在 dispatcher 增加双 digest 比较（步骤 D4），operation 增加 defensive 检查（步骤 D5），两者配合确保 mismatch 不逃逸。
- **测试覆盖**: 测试矩阵 (lines 328-329) 包含 "直接注入 mismatch feedback" 和 "通过 test seam 让 mismatch feedback 到达 operation" 两个 defensive case。
- **关闭状态**: ✅ 已关闭。

---

## Residual Findings 验证

### MiMo F01（低）：baseline 提交边界

- **状态**: 已被 DS F1 合并处理，plan-fix accepted，修订 plan 已关闭。

### MiMo F03（低）：F10 digest fixture 影响

- **修订 plan 体现**: §12 (line 479): "fixture 必须从 production owner helper 重新生成，禁止硬编码旧 digest"。测试矩阵 (line 324) 有 "digest" case 覆盖同输入重复构造与 boundary 变化。
- **状态**: 已充分记录，不阻塞 implementation。

### MiMo F05（低）：F09/F10 文件重叠

- **状态**: 已被 MiMo F5 合并处理，修订 plan 固定顺序 F09→F10。

---

## Controller 裁决合规验证

| 裁决点 | plan 体现 | 合规 |
|---|---|---|
| 不采纳或要求 Host 固化接受句点等不合规 candidate | F08 步骤 3 禁止 negative acceptance test；§11 checklist 拒绝 | ✅ |
| 不建议 rebase | F10 开头 "不执行 rebase"；plan-fix 假设证伪 rebase 需求 | ✅ |
| oversized group 不新增专用信号 | §5.2 "不新增 oversized_group signal" | ✅ |
| feedback mismatch 不以异常逃逸 | F10 步骤 D5 "不得把异常抛出 scheduler" | ✅ |
| 历史 digest 为 immutable fact | §12 "历史 EventLog digest 保持产生时 immutable" | ✅ |

---

## Plan Review Checklist 再验证

| Checklist Item | 结果 |
|---|---|
| 是否有人尝试用 `len(text) <= 1`、ASCII、词表或正则把 F08 伪装成 deterministic semantic validation？ | **否**。Plan 明确禁止 heuristic，§5.4 不变量 #2 固化。 |
| 是否新增了 Host 接受句点/占位符的 negative test？ | **否**。Plan 明确禁止（F08 步骤 3、§11 checklist）。 |
| `null` 是否真正删除旧 summary？ | **是**。既有测试 `test_accepted_compact_without_summary_clears_prior_session_summary`（`test_memory_projection.py:1408`）通过。 |
| F09 是否只让 synthetic projector test 通过？ | **否**。Plan 要求 durable recorder → EventLog → projector → formal resolver 完整链路 integration test。 |
| F09 是否通过放松 mismatch check 通过？ | **否**。Plan 明确禁止修改 `tool_trace.py` resolver identity 条件。 |
| group selector 是否把一个 group 计作一个 item？ | **否**。§5.2 "item cap 按真实 block 数计数"。 |
| selector 是否在大组放不下后跳过它选择更晚小组？ | **否**。§5.2 "首个放不下的 eligible unit 及后续均标记 budget_limit"。 |
| oversized group 是否触发专用 signal 或从 source snapshot 删除？ | **否**。§5.2 明确 "不新增 oversized_group signal"、"不得在 selector、pipeline 或 dispatcher 静默删除该组"。 |
| already-represented/protected 是否导致同组成员不同 disposition？ | **否**。§5.2 "group 任一成员命中时全组采用最高优先级的同一 reason"。 |
| feedback 是否按 stage 名而非双 digest 绑定？ | **否**。§5.1 使用 `request_digest` + `source_boundary_digest` 双 digest。 |
| repair feedback 的治理 digest 是否被投影进 LLM prompt？ | **否**。F10 步骤 D2 "治理 digest 不暴露为业务事实"。 |
| reactive pass 是否因 root atomic contract 被错误禁止？ | **否**。§5.3 "reactive multi-pass selection 明确标记为 operation-private transient pass"。 |
| operation guard 是否只验证 reduced tier boundary 而没有验证 root group proof？ | **否**。§5.3 与 F10 步骤 E 增加 root-boundary validator 双重防线。 |
| feedback mismatch 是否以异常逃逸 scheduler？ | **否**。F10 步骤 D5/E4 使用 non-repairable failed result transport。 |
| accepted artifact、Memory、Tool Trace 与 RunInput 是否仍可能各自重算同一事实？ | **否**。§5.4 不变量 #8 "均从 accepted root truth 和 canonical manifest 真源派生"。 |

---

## Residual Risks

修订 plan §12 已完整记录所有 residual risks，与 plan-fix 裁决一致：

| Risk | 状态 |
|---|---|
| F08 prompt 仍可能被真实 provider 违反 | 记录于 §12，由后续 CLI scenario 覆盖 |
| Group-atomic policy 可能使超大 Run 更早进入 fallback | 记录于 §12，owner tests 必须证明 raw-window 行为 |
| typed fields 改变新 request/selection digest | §12 明确 fresh schema + historical immutable |
| F09 real provider/model identity 需后续 CLI scenario | 记录于 §12 |

无新增 residual risk。

---

## Open Questions

原 MiMo review 的 OQ2（`source_boundary_digest()` 是否需纳入 `__eq__`/`__hash__`）和 OQ3（group atomic 是否影响 reactive pass 拆分）在修订 plan 中已有明确答案：

- OQ2: §6 F10 步骤 A4 (line 256) "frozen dataclass 的直接字段自然参与当前对象相等性，canonical request/selection digest 由 owner serialization 生成"。`source_boundary_digest()` 是独立方法，不改变 frozen dataclass 的 `__eq__`/`__hash__`。
- OQ3: §5.3 (line 136) "reactive multi-pass selection 明确标记为 operation-private transient pass，并绑定 root selection digest"。§6 F10 步骤 C3 (line 270) "build_reactive_pass_queue_plan 保留现有逐 block provider pass"。

无未收敛 open question。

---

## Final Plan Re-Review Conclusion

**PASS**

修订 plan 已关闭原 MiMo review 和 DS review 的全部 accepted findings：

1. **Baseline 单一 checkpoint**: §1 + §10 明确单一独立 commit 包含 frozen baselines + plan + reviews + fix + re-review + controller adjudication。
2. **F08 无 heuristic 且 prompt/manifest/hash 闭环**: §5.4 不变量 #2 禁止 Host heuristic；F08 步骤 1 给出完整 LLM-facing 判断维度；步骤 5 建立 prompt → manifest asset SHA → manifest raw SHA → `FROZEN_MANIFEST_SHA256` 闭环。
3. **F09 row/hot 同源**: §4.2 + F09 步骤 1 明确 hot JSON inline manifest body + row descriptor 同一 ref/digest；resolver/projector 不变。
4. **F10 两阶段原子 selector**: §5.2 明确阶段一归并 units + collective exclusion、阶段二 prefix budget；reason precedence 固定且顺序无关。
5. **Oversized raw retention**: §5.2 明确不新增信号、budget_limit、frozen snapshot 保留全组、tier 4/5 owner 消费或 fail closed。
6. **Digest 新 schema 边界**: §12 明确 fresh schema、historical immutable、runtime binding 只比较当前 request。
7. **Feedback defensive failure**: F10 步骤 D5/E4 明确 operation 返回 failed result 而非抛异常、dispatcher 停止 schedule、单一 failed terminal。
8. **Operation root barrier**: §5.3 + F10 步骤 E 明确 root-boundary validator 在构造期与 durable accept 前双重验证。

Controller 裁决全部合规：不采纳 Host 接受句点的不合规 candidate、不建议 rebase、不新增 oversized 信号、feedback mismatch 不以异常逃逸。

Plan 可以交给 implementation agent 执行。
