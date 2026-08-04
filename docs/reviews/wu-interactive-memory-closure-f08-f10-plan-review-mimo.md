# Plan Review：Interactive Conversation Memory closure F08–F10

- **Reviewed target**: `docs/reviews/wu-interactive-memory-closure-f08-f10-plan-codex.md`
- **Review type**: Adversarial plan review（planreview）
- **Review timestamp**: `20260804-154201`
- **Reviewer**: AgentMiMo
- **Scope**: F08 summary null 选择规则、F09 manifest 同源修复、F10 turn-group 原子选择 / feedback binding / root accept barrier
- **References**:
  - `AGENTS.md`（根约束）
  - `docs/reviews/wu-interactive-memory-closure-f08-f10.md`（frozen finding）
  - `docs/host/design.md`（design truth）
  - `workspace/tmp/interactive-memory-observed-behavior.md` + `workspace/tmp/interactive-memory-report-freeze.json`（frozen evidence）
  - `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`（frozen registry）
  - 实际生产代码与测试（`dayu/host/compaction_operation.py`、`dispatch.py`、`compact_material.py`、`compact_pipeline.py`、`compaction.py`、`context_governance.py`、`tool_trace.py` 及对应测试文件）

---

## Assumptions Tested

| # | Assumption | 验证结果 |
|---|---|---|
| A1 | `select_compact_segment` 不按 turn-group 做原子选择 | **Confirmed**。代码 (`compact_material.py:824-846`) 逐个 block 累计 char/item cap，仅对 recent floor 使用 `turn_group_id` 保护，compactable 历史无原子分组。 |
| A2 | proactive dispatcher 无条件传递 `next_repair_feedback` 给下一 attempt | **Confirmed**。`dispatch.py:2325` 直接赋值 `repair_feedback = attempt_result.next_repair_feedback`，无 request/source boundary digest 校验。 |
| A3 | `_run_compaction_operation` 在 durable accept 前不验证 root turn-group 完整性 | **Confirmed**。现有校验覆盖 label/coverage/cap/budget，无 root group manifest 或 turn-group 二分校验。 |
| A4 | F09 的 `RUNNER_CALL_INPUT_ASSEMBLED` EventLog row 的 `payload_ref`/`payload_digest` 为 `None` | **Confirmed**。`compaction_operation.py:328-329` 显式 `payload_ref=None, payload_digest=None`。hot payload JSON 内含 `manifest_payload_ref` 和 `manifest_digest`，但 row 级字段为 null。 |
| A5 | Tool Trace formal resolver 要求 `signal.manifest_ref` 和 `signal.manifest_digest` 非 None | **Confirmed**。`tool_trace.py:362` 处 `resolve_runner_call_projection_from_signal` 在两者为 None 时抛 `HostDurableError`。 |
| A6 | `CompactRepairFeedbackV2` 无 `request_digest` / `source_boundary_digest` 字段 | **Confirmed**。`compaction.py:1629` 仅有 `previous_attempt_number`、`issues`、`additional_issue_count`。 |
| A7 | 现有 prompt 已允许 `session_summary: null` | **Confirmed**。`conversation_compaction_user.md` 已声明 `session_summary: null, or object`，但未显式禁止占位符或要求"cap 内无法表达有意义摘要时必须 null"。 |
| A8 | Memory projector 对 `session_summary=None` 的 replacement 已正确清空旧 summary | **Confirmed**。`test_memory_projection.py:1408` 有 `test_accepted_compact_without_summary_clears_prior_session_summary` 通过。 |
| A9 | frozen baseline files 在当前分支有未提交改动 | **Confirmed**。`git status` 显示 `docs/cli_ci_oracles.json`（staged）和 `docs/cli_ci_scenarios.json`（unstaged）有改动。 |
| A10 | F09 与 F10 的 allowed files 有重叠 | **Confirmed**。`compaction_operation.py` 和 `test_dispatch_scheduler.py` 同时出现在两个 slice 的 allowed files 中。 |

---

## Findings

### 01-未修复-低-Frozen baseline 提交边界未显式覆盖用户要求

- **位置**: Section 10 提交边界
- **问题类型**: 契约缺失
- **当前写法**: Plan 声明 "Plan gate 本身不创建提交"，accepted plan artifact 单独提交，frozen baseline files 仅通过 SHA-256 验证完整性。
- **反例/失败场景**: 用户要求 "三份 frozen baseline 应在 accepted-plan checkpoint 与 plan/review artifacts 独立提交且后续 hash 不变"。当前 `git status` 显示 `docs/cli_ci_oracles.json`（staged）和 `docs/cli_ci_scenarios.json`（unstaged）有未提交改动。若 accepted-plan commit 不包含 baseline 状态，后续实现阶段的 diff 可能混入 baseline 变更，使 "hash 不变" 验证失去锚点。
- **为什么有问题**: Plan 的 SHA-256 验证能检测运行时篡改，但未在 git 历史中建立 baseline 的显式 checkpoint。若 baseline 在 plan gate 前已被修改（当前确实如此），缺少独立 commit 会使 baseline 的 "accepted state" 不可追溯。
- **直接证据**: `git status` 输出 `M docs/cli_ci_oracles.json`（staged）、` M docs/cli_ci_scenarios.json`（unstaged）；plan section 10 未提及 baseline commit。
- **影响**: 低。SHA-256 验证仍可在实现前后检测变更；但 git 历史中缺少 baseline checkpoint，增加审计难度。
- **建议改法和验证点**: 在 section 10 中增加：实现开始前，frozen baseline files（`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/reviews/wu-interactive-memory-closure-f08-f10.md`）的当前状态应作为独立 commit 提交，或确认它们已在 plan gate 前的 clean commit 中。验证：`git log` 可追溯 baseline 的 accepted state。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-F09 root cause 描述中 hot payload 语义略有歧义

- **位置**: Section 4.2 F09 数据流与根因
- **问题类型**: 其它（描述精度）
- **当前写法**: "hot payload 也使用该 descriptor"。Section 6 F09 步骤 1："hot payload 继续使用完全相同的 ref/digest；禁止二次计算另一份 manifest 或从投影反推。"
- **反例/失败场景**: 实际代码 (`compaction_operation.py:323-329`) 中 hot payload JSON 内含 `manifest_payload_ref` 和 `manifest_digest` 作为字段，同时 inlines 完整 manifest body。EventLog row 的 `payload_ref`/`payload_digest` 为 `None`。"使用该 descriptor" 的表述可能让 implementation agent 误以为 hot payload 通过 descriptor indirection 引用 manifest，而非 inlining。
- **为什么有问题**: hot payload 的实际结构是 `{manifest_payload_ref: ..., manifest_digest: ..., manifest_body: ...}`，不是 `{payload_ref: descriptor.ref, payload_digest: descriptor.digest}`。Implementation agent 需要明确知道 hot payload inlines manifest body，而 row 级 `payload_ref`/`payload_digest` 才是需要修复的字段。
- **直接证据**: `compaction_operation.py:323-327` 的 `_compactor_runner_call_hot_payload(manifest=manifest, manifest_payload_ref=manifest_descriptor.payload_ref, manifest_digest=manifest_digest)`；行 328-329 的 `payload_ref=None, payload_digest=None`。
- **影响**: 低。Implementation agent 读代码后可自行理解；但 plan 描述的歧义可能增加理解成本。
- **建议改法和验证点**: 将步骤 1 的 hot payload 描述改为："hot payload JSON 继续 inlines manifest body 并携带 `manifest_payload_ref` 和 `manifest_digest` 字段；同时将 EventLog row 的 `payload_ref` 设为 `manifest_descriptor.payload_ref`、`payload_digest` 设为 `manifest_digest`，消除 row 级 null 与 hot payload 内容的分裂。"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-F10 digest 变更对现有测试 fixture 的影响未量化

- **位置**: Section 12 Residual risks
- **问题类型**: 测试缺口
- **当前写法**: "给 selection 与 repair feedback 增加 internal canonical fields 会改变 request/selection digest；这些 digest 是治理 identity，不是 v2 schema，但相关 fixtures 必须从 owner helper 重新生成，禁止硬编码旧 digest。"
- **反例/失败场景**: `test_compact_material.py`、`test_compact_pipeline.py`、`test_compaction_operation.py`、`test_dispatch_scheduler.py` 中大量测试使用 `FakeContextCompactor` 和 factory helpers。若这些 helpers 内部硬编码了 selection digest 或 request digest 的预期值，F10 的 digest 组成变更会导致批量测试失败。Plan 未列出受影响的测试数量或具体 fixture。
- **为什么有问题**: Implementation agent 在 F10 实施时可能遇到大量测试失败，需要逐一判断是 expected digest change 还是 real regression。没有量化影响，agent 可能低估工作量或误修测试。
- **直接证据**: `compact_material.py:860-878` 的 `digest_input` dict 结构；`compaction.py` 的 `CompactionRequest.digest()` 和新增的 `source_boundary_digest()`。
- **影响**: 低。测试失败是 expected behavior，不会导致生产代码错误；但增加 implementation 时间和误判风险。
- **建议改法和验证点**: 在 section 7 测试矩阵或 section 12 中补充：F10 实施前先运行 `pytest tests/host -q` 记录 baseline，实施后对比失败列表；预期失败应全部与 digest 组成变更相关，可通过更新 fixture helpers 的 digest 生成逻辑修复。验证：所有失败测试的 error message 均包含 digest mismatch 而非 semantic regression。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 04-未修复-中-F08 prompt 修改的 LLM 遵从性边界未充分标记

- **位置**: Section 6 Slice F08 错误路径
- **问题类型**: 状态机漏洞
- **当前写法**: "provider 仍输出超 cap summary：继续由现有 deterministic cap validator reject，进入既有 bounded repair/fallback。provider 输出 cap 内占位符：Host 不假装能可靠判断自然语言意义；正式 real-provider scenario 由 Agent-in-the-loop 裁决。"
- **反例/失败场景**: Plan 在 prompt 中增加 "禁止占位符、孤立字符、无业务含义缩写或截断片段"。但 LLM 可能忽略该禁止，输出如 `"."`、`"N/A"`、`"..."` 等 cap 内非空文本。Host deterministic validator 不检查语义，会接受这些值。Plan 正确识别了这个边界，但未在测试矩阵中覆盖此类 adversarial case——即使是 negative test 证明 Host 不检查，也应有测试固化这个设计边界。
- **为什么有问题**: 若未来有人误以为 Host 能检测占位符，可能删除 prompt 中的禁止规则或放松 prompt 要求。没有测试固化 "Host 不检查自然语言语义" 这个设计决策，该边界可能被隐式削弱。
- **直接证据**: Section 6 F08 错误路径第二点；Section 5.4 不变量 #2 "Host 不对自然语言'有意义'做任意 heuristic"；test matrix 中 F08 negative case 仅覆盖 "oversize summary"，未覆盖 "cap 内占位符被 Host 接受"。
- **影响**: 中。不阻塞当前实现，但设计边界未被测试固化，增加未来 regression 风险。
- **建议改法和验证点**: 在 F08 测试矩阵中增加一个 negative case：构造 `session_summary.text="."` 的 candidate，断言 Host deterministic validator 接受它（shape/cap/coverage 通过），同时断言 prompt contract test 包含占位符禁止规则。该测试固化 "Host 不检查语义，依赖 prompt 引导 LLM" 的设计边界。验证：测试明确记录该行为是 design boundary 而非 bug。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 05-未修复-低-F09 与 F10 allowed files 重叠未说明合并策略

- **位置**: Section 6 Slice F09 / Slice F10 allowed files
- **问题类型**: 切片过粗
- **当前写法**: F09 allowed files 包含 `compaction_operation.py` 和 `test_dispatch_scheduler.py`；F10 allowed files 也包含这两个文件。Section 10 提交边界将 F09 和 F10 作为独立 commits。
- **反例/失败场景**: F09 修改 `record_compactor_proposal_manifest` 方法（行 306-331 区域），F10 修改 `_run_compaction_operation` 的 feedback validation 和 root accept guard（行 743+ 区域）。两者修改同一文件不同区域，但若 F09 的 commit 改变了 F10 依赖的上下文（如 import、helper 函数签名），F10 可能需要 merge conflict resolution。
- **为什么有问题**: `test_dispatch_scheduler.py` 是 9300+ 行的大文件。F09 增加 formal resolver integration test，F10 增加 feedback binding 和 root accept boundary tests。两个 slice 的 test additions 可能在同一文件中交织。
- **直接证据**: F09 allowed files 列表与 F10 allowed files 列表的交集为 `{compaction_operation.py, test_dispatch_scheduler.py}`。
- **影响**: 低。两个 slice 的修改区域不重叠，implementation agent 可自行处理；但 plan 未显式说明合并策略。
- **建议改法和验证点**: 在 section 10 中增加注释：F09 和 F10 共享 `compaction_operation.py` 和 `test_dispatch_scheduler.py`，F09 commit 应先于 F10；F10 实施前 rebase 到 F09 commit 以避免冲突。验证：F10 的 focused tests 在 F09 commit 之上运行通过。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

---

## Open Questions

| # | 问题 | 当前状态 | 建议跟踪 |
|---|---|---|---|
| OQ1 | frozen baseline files 的当前 dirty state 是否应在 plan gate 前独立 commit？ | Plan 未明确。SHA-256 验证可检测变更，但 git 历史缺少 baseline checkpoint。 | Accepted-plan commit 前确认 baseline 状态；若 dirty，先 commit baseline。 |
| OQ2 | F10 的 `source_boundary_digest()` 方法是否需要纳入 `CompactionRequest` 的 `__eq__` / `__hash__`？ | Plan 未提及。`CompactionRequest` 是 frozen dataclass，新增方法不影响 equality，但需确认。 | Implementation 时确认 frozen dataclass 行为。 |
| OQ3 | F10 的 group atomic selection 是否影响 `build_reactive_pass_queue_plan` 的 pass 拆分逻辑？ | Plan section 6C 步骤 3 说 "保留现有逐 block provider pass"，但 F10 的 group atomic policy 可能改变 pass 的输入。 | Implementation 时验证 reactive pass queue 的 pass 拆分仍正确。 |

---

## Residual Risks

| # | 风险 | 影响 | 缓解措施 | 跟踪目的地 |
|---|---|---|---|---|
| RR1 | F08 的 prompt 禁止规则可能被 LLM 忽略 | cap 内占位符被接受 | Agent-in-the-loop scenario 裁决；prompt contract test 固化边界 | CLI scenario `interactive.g06.summary-null` |
| RR2 | F10 group atomic policy 导致超大 Run 完全不进入 compactor | 更早进入 raw-window/fail-closed | fallback regression tests 确认 terminal 行为 | 测试矩阵 F10 selector/prefix case |
| RR3 | F10 digest 组成变更导致大量 fixture 更新 | implementation 时间增加 | 先记录 baseline，对比失败列表，区分 expected vs regression | Section 12 已记录 |
| RR4 | F09 的 real provider/model/response identity 最终需 CLI scenario 证明 | 本 work unit 仅提供 resolver contract | 后续 CLI scenario `interactive.g06.tool-trace-formal` | CLI scenario registry |
| RR5 | F08/F09/F10 实施后五条 CLI scenario 尚未补跑 | readiness proof 不完整 | 独立 evidence/readiness 阶段 | CLI scenario obligations |

---

## Plan Review Checklist Verification

| Checklist Item | 结果 |
|---|---|
| 是否有人尝试用 `len(text) <= 1`、ASCII、词表或正则把 F08 伪装成 deterministic semantic validation？ | **否**。Plan 明确禁止 heuristic，依赖 prompt + deterministic validator 分工。 |
| `null` 是否真正删除旧 summary？ | **是**。现有测试 `test_accepted_compact_without_summary_clears_prior_session_summary` 证明。 |
| F09 是否只让 synthetic projector test 通过？ | **否**。Plan 要求 integration test 使用 durable recorder → EventLog → projector → formal resolver 完整链路。 |
| F09 是否通过放松 mismatch check 通过？ | **否**。Plan 明确禁止放松 resolver identity check。 |
| group selector 是否把一个 group 计作一个 item？ | **否**。Plan 明确要求 "item cap 按真实 block 数计数，char cap 按成员 size_units 求和；不得把 group 算成一个 item"。 |
| selector 是否在大组放不下后跳过它选择更晚小组？ | **否**。Plan 要求 "首个放不下的 eligible unit 及后续 eligible units 均标记 budget_limit"。 |
| feedback 是否按 stage 名而非双 digest 绑定？ | **否**。Plan 使用 `request_digest` + `source_boundary_digest` 双 digest 绑定。 |
| repair feedback 的治理 digest 是否被投影进 LLM prompt？ | **否**。Plan 明确 "治理 digest 不暴露为业务事实"。 |
| reactive pass 是否因 root atomic contract 被错误禁止？ | **否**。Plan 允许 transient pass 局部分片，但要求 root digest binding。 |
| operation guard 是否只验证 reduced tier boundary？ | **否**。Plan 增加 root group proof 验证。 |

---

## Final Plan Review Conclusion

**PASS**

Plan 整体质量高，动机成立，root cause 基于直接代码证据，owner 判定准确，allowed files 边界清晰，sequencing 合理，测试矩阵覆盖面充分。四个 findings 均为低/中严重程度，不阻塞 implementation。五个 open questions 均可在 implementation 阶段解决。residual risks 已被 plan 正确识别并有缓解措施。

Plan 可以交给 implementation agent 执行。
