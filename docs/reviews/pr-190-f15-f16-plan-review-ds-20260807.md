# PR190 F15/F16 Plan Review — AgentDS Adversarial

- **Review target**: `docs/gateflow/pr-190-f15-f16-plan-20260807.md`
- **Binding Goal Confirmation**: `docs/gateflow/pr-190-f15-f16-goal-confirmation-20260807.md`
- **Reviewer**: AgentDS (adversarial, independent)
- **Timestamp**: 2026-08-07T08:57:41
- **Conclusion**: **pass-with-risks** — 发现 8 个需要修复的 findings，其中 2 个为高风险、4 个中风险、2 个低风险；无致命问题阻止进入 implementation gate，但必须在 implementation gate 前阅读本 review 并采纳或反驳每个 finding。

---

## Assumptions Tested

| # | Assumption | Verdict |
|---|-----------|---------|
| A1 | canonical projection 可以在 `run_input_material_block()` 之前完成一次归一化 | 成立，但 plan 未明确 `normalized_material_text()` 抛出 `ValueError`（空文本）时 canonical projection 如何处理 |
| A2 | `CompactAcceptedReplacementV4` 包含足够信息从 durable store 重建 byte-identical pair | 需要验证：replacement 的 answer_anchor 是否保存了 title/detail 的完整文本，还是已有截断/格式化 |
| A3 | EventLog `reason_json` 列可以作为 per-Run terminal reason 的唯一真源 | 部分成立，但 `reason_json` 是可选列；不同 terminal type 的 reason 可能存在于 event payload 而非 reason_json |
| A4 | EventLog 支持 cursor/sequence 分页读取 | 需要明确：EventLog 当前用 `event_sequence` 整数 + SQL ORDER/LIMIT，不存在独立 cursor API |
| A5 | workspace/tmp 脚本修改不影响 tracked helper contract | 成立，plan 明确了 boundary |
| A6 | recovery tier 在 canonical projection 后仍保持逻辑一致 | 需要验证：空 text 场景下 packed block 数量可能与 readable view item 数量不匹配 |

---

## Findings

### R01-未修复-高风险-F15 canonical projection 空文本边界未定义

- **位置**: §4.1 canonical projection 边界、§4.3 invariants
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: plan 规定每个文本叶子调用 `normalized_material_text()` 一次，沿用现有规则"去除 blank-only lines、折叠每行内部空白、保留非空行边界"
- **反例/失败场景**: `normalized_material_text()`（`compact_material.py:768-773`）在规范化后文本为空时抛出 `ValueError("text must be non-empty after normalization")`。如果 replacement 的某个 section（如 answer_anchor.detail、forward_intent.text）原始内容仅含空白行，canonical projection 会崩溃，导致整个 `_previous_compacted_view_pair_from_replacement()` 抛出 HostDurableError，阻塞所有 ordinary Run
- **为什么有问题**: plan 未规定 canonical projection 如何处理"某个 section 文本规范化后为空"的情况。当前代码中 `run_input_material_block()` 构造 ordinary material 时同样会触发此 ValueError，但这在普通 material 路径中本就是 invalid state。而在 previous view projection 路径中，compactor 可能合法地为某个 answer_anchor 产出了一个只有空白行的 detail，这应该被过滤而不是崩溃
- **直接证据**:
  1. `dayu/host/compact_material.py:768-773` — `normalized_material_text()` 对空规范化结果抛出 `ValueError`
  2. `dayu/host/compact_material.py:2433-2444` — answer anchor 直接调用 `run_input_material_block()` 传入 `previous_answer_anchor_block_text(anchor)` 作为 text
  3. `dayu/host/compact_material.py:833` — `run_input_material_block()` 内 `material_text = normalized_material_text(text)` 对非 evidence block 必然归一化
- **影响**: 实施 Agent 可能忽略此边界，导致 production 中 compactor 产出的合法但全空 detail section 在 ordinary Run 中崩溃；或实施 Agent 自行决定静默跳过（与 plan 的"不宽松比较"原则矛盾）
- **建议改法和验证点**:
  1. canonical projection 构造时必须对每个 section 独立处理：归一化后为空 → 跳过该 item，不创建 packed block，也不创建对应的 readable view item
  2. summary / answer_anchor 的 section 级空值必须由 plan 明确规定行为：summary 为空时 previous view 应整体为 None（已有逻辑），但个别 anchor 为空时不应拉垮整个 replacement
  3. 补充 deterministic test：`test_canonical_projection_skips_empty_normalized_section_without_crashing`
- **修复风险**: 低（只需在 canonical projection 中加空值过滤，不改变 normalizer 语义）
- **严重程度**: 高风险

### R02-未修复-高风险-F16 terminal reason 真源 single-column vs payload contract 不精确

- **位置**: §5.1 tracked reusable helper、§3.2 F16 owner
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: helper "从 canonical terminal event 的 `reason_json` 按 strict typed contract 读取 reason"
- **反例/失败场景**:
  1. `reason_json` 是 `EventLogRow` 的可选列（`dayu/host/durable/event_log.py:146`），不同 terminal type 的 reason 可能定义在 event payload JSON 内，而不是 `reason_json` 列
  2. 例如 `COMPACT_MATERIAL_BUILD_FAILED` 等 diagnostic 事件的 reason 在 payload 的 `reason` 字段；`TOOL_RESULT_ACCEPTED` 可能携带 policy decision reason
  3. `RUN_FAILED` 的失败 reason 可能在 payload（如 `runner_candidate_invalid`）而不一定在 `reason_json` 列
- **为什么有问题**: 如果 helper 只读 `reason_json` 列而实际 reason 在 event payload 中，则所有 terminal 的 reason 都将是 `None`，dependency gate 只能判断 terminal type 而无法提供可审计的 reason
- **直接证据**:
  1. `dayu/host/durable/event_log.py:146` — `reason_json: str | None`，可选
  2. `dayu/host/audit.py:1234` — `_reason_value()` 同时检查 `event.payload` 和 `event_row.reason_json`
  3. `dayu/host/context_events.py:680` — `or row.reason_json is not None` 表明 reason_json 可以不存在
  4. `dayu/host/compact_material.py:3378` — `reason_json=_optional_host_row_text(row, field_name="reason_json")`，可选
- **影响**: 实施 Agent 可能实现后发现在 production 中所有 reason 都为 null，导致 dependency gate 无法区分 `runner_candidate_invalid` 与真正的 provider failure
- **建议改法和验证点**:
  1. 明确 reason 读取 contracts：优先从 `reason_json` 列读取 canonical reason；若为 None，按 typed event payload contract 从 payload 提取 reason
  2. 至少需要定义 `RUN_FAILED`、`RUN_CANCELLED`、`RUN_LOST` 三种 terminal type 的 reason 真源 contract
  3. 补充 test：`test_terminal_reason_reads_from_payload_when_reason_json_is_null`
- **修复风险**: 低（只需扩展 reason 读取逻辑，不改变 Host durable schema）
- **严重程度**: 高风险

### R03-未修复-中风险-F16 pagination 使用 EventLog API 与 "cursor/sequence" 语义不匹配

- **位置**: §5.1 tracked reusable helper 职责第 1 条
- **问题类型**: 不可直接实施
- **当前写法**: "以 EventLog cursor/sequence 分页读取指定 observation window，直到穷尽；page size 只是读取批次"
- **反例/失败场景**: EventLog 当前没有 cursor API。内部代码使用 `event_sequence` 整数 + `ORDER BY event_sequence ASC` + `LIMIT/OFFSET` 进行分页（如 `compact_material.py:2247-2263`）。但 EventLog 的 row 可能跨多个 session，helper 需要按 session_id + event_sequence range 读取，而非全局 cursor。`OFFSET` 分页在并发写入下有错过或重复新行的风险
- **为什么有问题**: plan 用 "cursor/sequence" 抽象未落在具体 EventLog API 上，implementation agent 需要自行设计分页方案，可能引入 off-by-one、skip、或与 Host durable reader API 不一致的实现
- **直接证据**:
  1. `dayu/host/compact_material.py:2247-2263` — 使用 SQL `event_sequence < ?` + `ORDER BY event_sequence ASC` 无 LIMIT
  2. 没有独立的 cursor/page API
  3. `dayu/host/durable/event_log.py` — `EventLogStore.read_event_by_id()` 单条读取，不提供 range scan
- **影响**: 实施 Agent 可能设计出与现有 Host read pattern 不一致的 pagination，或在并发 Session 下读到不一致 snapshot
- **建议改法和验证点**:
  1. 明确 helper 使用 `HostTransaction.fetchall()` + `event_sequence` range + `session_id` filter + `ORDER BY event_sequence ASC` + `LIMIT/OFFSET`，page size 为纯读取批次大小
  2. 在 page advance 前校验上一页最大 sequence < 下一页最小 sequence，sequence 不前进时 fail closed
  3. 补充 test：`test_terminal_reader_paginates_by_event_sequence_range_not_cursor_api` 已覆盖（plan §7.2）
- **修复风险**: 低
- **严重程度**: 中风险

### R04-未修复-中风险-F15 recovery tier 在 canonical projection 后的成对过滤一致性未证明

- **位置**: §4.2 实现约束第 7 条、§4.3 invariants
- **问题类型**: 状态机漏洞 / 契约缺失
- **当前写法**: "recovery tier 只做现有的成对过滤，不改变剩余 atom 文本"
- **反例/失败场景**: 如果 canonical projection 跳过了规范化后为空的 section（参见 R01），则 packed block 数量与 readable item 数量可能与 replacement 原始 item 数量不同。Recovery 的 `transform_previous_compacted_view_pair_for_recovery()` 依赖 block label 与 readable item 的 `source_label` 匹配。如果某个 answer_anchor 因 detail 为空被跳过，其后 anchor 的 label 会移位，与 replacement 中的 ordinal 不再对应
- **为什么有问题**: plan 没有考虑 R01 的空文本场景，也就没有说明 recovery tier 在这个场景下的行为。如果空 section 被跳过，label 连续性被破坏，recovery sort/filter 可能映射错误的 readable item 到 packed block
- **直接证据**:
  1. `dayu/host/compact_material.py:1117-1136` — `_ordered_answer_anchor_items_for_blocks()` 按 `block.block_label` 匹配 `item.source_label`
  2. `dayu/host/compact_material.py:1077-1088` — `transform_previous_compacted_view_pair_for_recovery()` 过滤后重新校验 pair
  3. Label 由 `material_label(section, ordinal)` 生成，ordinal 基于 position 而非 identity
- **影响**: recovery 后 pair 验证失败（label mismatch），导致 `HostDurableError`，Run 进入 `RUN_FAILED`
- **建议改法和验证点**:
  1. canonical projection 中跳过空 section 时，保留 ordinal 空洞（不重新编号），保持 label 与 replacement 序号的对应关系
  2. 或明确规定空 section 不产生 packed block/readable item 对，且 recovery 按 identity 匹配而非 label
  3. 补充 test：`test_recovery_preserves_pair_when_canonical_projection_skips_empty_sections`
- **修复风险**: 低
- **严重程度**: 中风险

### R05-未修复-中风险-F16 dependency gate 的 dependency 声明格式未定义

- **位置**: §5.4 dependent-chain stop 与 isolation
- **问题类型**: 不可直接实施
- **当前写法**: "例如 typed action 字段或 `run-success-gate:<absolute accepted ordinal>` trigger"
- **反例/失败场景**: plan 只给出了 trigger 字符串格式草案（`run-success-gate:<ordinal>`），但没有定义：
  1. 这是 PtyAction 的新字段还是现有 trigger 字段的扩展？
  2. absolute accepted ordinal 如何与 EventLog 中的 Run identity 关联——accepted ordinal 是跨所有 scenario 的全局递增还是 per-scenario？
  3. 如果一个 scenario 有多个上游 dependency（如 dependency chain 中第 N 个 Run 依赖第 N-1 和第 N-2 两个 Run），格式如何表达？
  4. `workspace/tmp/prompt_observe_calibration.py` 和 `workspace/tmp/f14_real_cli_observation.py` 的 action schema 需要显式修改
- **为什么有问题**: 实施 Agent 需要自行设计 dependency 声明 schema，可能与 plan 意图不同，也可能在两个临时 harness 之间不一致
- **直接证据**: plan §5.4 中 trigger 格式仅为草案 `run-success-gate:<absolute accepted ordinal>`，未形成 typed schema
- **影响**: 两个临时脚本可能各自解释 dependency，导致 F16 的核心目标（dependent chain stop）实现不一致
- **建议改法和验证点**:
  1. 在 PtyAction dataclass 中增加显式 `success_dependency: int | None` 字段（上游 Run 的绝对 accepted ordinal）
  2. 明确绝对 accepted ordinal 是跨所有 scenario 的全局 RUN_ACCEPTED 顺序号
  3. 多个 upstream dependency 使用 tuple 或 list
  4. 补充 test：`test_dependency_gate_with_multiple_upstream_runs`
- **修复风险**: 低
- **严重程度**: 中风险

### R06-未修复-中风险-duplicate/conflicting terminal 的定义不精确

- **位置**: §5.1 tracked reusable helper 职责第 4 条
- **问题类型**: 契约缺失
- **当前写法**: "duplicate/conflicting terminal...均 fail closed"
- **反例/失败场景**:
  1. Run 可以经历 `RUN_CANCELLING`（lifecycle event）再进入 `RUN_CANCELLED`（terminal event），这是合法状态迁移，不是 duplicate
  2. `RUN_LOST` 可能与 `RUN_FAILED` 在相同 Run 上出现（如果先 failed 后 recovery 判定为 lost），需要确定哪个是 canonical terminal
  3. Attempt 也有 terminal events（`ATTEMPT_SUCCEEDED` 等），helper 需要区分 Run terminal 与 Attempt terminal
- **为什么有问题**: 不精确的 "duplicate" 定义可能导致合法状态迁移被误判为 invalid，整个 observation window 被错误标记为 invalid
- **直接证据**:
  1. `dayu/host/lifecycle_events.py:133-138` — `HOST_RUN_TERMINAL_EVENT_TYPES` 包含 4 种 terminal type
  2. `dayu/host/lifecycle_events.py:33-34` — `RUN_CANCELLING` 是 lifecycle event 不是 terminal
  3. 一个 Run 的事件序列可能为 `RUN_ACCEPTED -> RUN_STARTED -> RUN_CANCELLING -> RUN_CANCELLED`，其中 lifecycles 与 terminal 共存
- **影响**: helper 可能把正常 Run lifecycle 误判为 duplicate terminal，导致 false positive invalid
- **建议改法和验证点**:
  1. 明确定义 "duplicate terminal"：同一 run_id 上出现 2+ 个 `HOST_RUN_TERMINAL_EVENT_TYPES` 中的事件
  2. "conflicting terminal" 定义为同一 run_id 上有 2+ 个不同类型的 terminal event
  3. 非 terminal 的 lifecycle events（`RUN_CANCELLING`, `RUN_RECOVERING` 等）不参与 duplicate 判断
  4. 补充 test：`test_lifecycle_events_not_mistaken_for_duplicate_terminals`
- **修复风险**: 低
- **严重程度**: 中风险

### R07-未修复-低风险-F15 plan 未验证 reopen/reconnect byte-identical 的前提条件

- **位置**: §4.3 invariants "reopen/reconnect 不依赖内存缓存；从 durable strict replacement 重建时得到 byte-identical pair"
- **问题类型**: 契约缺失
- **当前写法**: 断言 reopen/reconnect 重建得到 byte-identical pair
- **反例/失败场景**: 需要验证 `CompactAcceptedReplacementV4` 的 answer_anchor 是否以原始文本（未经 normalizer）存储 title 和 detail。如果 replacement 本身已经截断或格式化过，则重建的 canonical projection 文本将与首次构建不同
- **为什么有问题**: plan 的 invariant 依赖于 `CompactAcceptedReplacementV4` 字段的 fidelity 假设，但未提供验证证据
- **直接证据**: `dayu/host/compact_material.py:2501-2506` — `ReadableAnswerAnchorItemVNext(display_text=anchor.detail)` 直接从 replacement 读取 detail，假设其为原始文本
- **影响**: 低 — 如果 replacement 字段确实保存了原始文本（从 compactor LLM output 直接解析），则 invariant 成立。这是一个需要 implementation gate 验证的假设，而非 plan 设计缺陷
- **建议改法和验证点**:
  1. 在 implementation gate 的第一时间验证 `CompactAcceptedReplacementV4` 的 answer_anchor.detail 是否保存完整原始文本（不含 normalizer 预处理）
  2. 如果发现 replacement 字段已经过 normalize，需要先修复 compactor schema/replacement 保存路径，再修复 projection
- **修复风险**: 低
- **严重程度**: 低风险

### R08-未修复-低风险-README 触发决策缺少直接证据

- **位置**: §6.1 Slice 1 README 决策、§6.2 Slice 2 README 决策
- **问题类型**: 不可直接实施
- **当前写法**: "默认不修改两份 README；若 implementation review 发现实际 stable boundary/测试运行方式发生变化，必须先停下重新按 README 约束裁决"
- **反例/失败场景**: `AGENTS.md:113-116` 明确要求：
  - `dayu/host/` 修改 → 检查并按需更新 `dayu/host/README.md`
  - `tests/` 修改 → 检查并按需更新 `tests/README.md`
  - plan 在 §7.1 中新增 6 个 test function，在 §7.2 中新增整个 test file `tests/cli/test_cli_ci_run_observation.py`。这些是 tests/ 下的实际修改
- **为什么有问题**: plan 声称"默认不修改 README"，但没有说明为何 `tests/README.md` 不需要更新（新增了 CLI test layer 文件 `tests/cli/test_cli_ci_run_observation.py`）。`tests/README.md` 的更新约束需要实际阅读 README 内容后才能判断，plan 的简化判断可能在 implementation review 时被推翻
- **直接证据**:
  1. `AGENTS.md:113-116` — README 更新触发规则
  2. plan §7.2 — 明确新增 `tests/cli/test_cli_ci_run_observation.py`
  3. plan §6.1 — README 决策："默认不修改两份 README"
- **影响**: 低 — plan 保留了"若 implementation review 发现变化则停下裁决"的 escape hatch。但 implementation agent 可能忽略此 check
- **建议改法和验证点**:
  1. 在 implementation gate 开始前，实际阅读 `tests/README.md` 并判断新增测试文件是否需要被记录
  2. 或 plan 中明确当前 `tests/README.md` 的更新约束内容，并给出判断理由
- **修复风险**: 低
- **严重程度**: 低风险

---

## Open Questions

1. **F15 canonical projection 是否需要处理 `normalized_material_text()` 的 `ValueError`？**（关联 R01）如果不需要（即 compactor schema 保证不会产出全空白 section），这个保证在哪里定义的？
2. **F16 helper 的 observation window 如何界定？** plan 说 "指定 observation window"，但未说明 window 的边界如何表达：是时间范围、EventLog sequence range、还是按 scenario 边界？
3. **F16 `run-terminals.json` 由谁写入？** plan §5.3 说 "每个 scenario/segment 写独立 `run-terminals.json`"，但 tracked helper `utils/cli_ci_run_observation.py` 是只读 projection，写入责任应该属于 `workspace/tmp/` 的临时消费者 — plan 未显式说明

---

## Residual Risks

| Risk | Severity | Suggested Tracking |
|------|----------|--------------------|
| canonical projection 跳过空 section 后 recovery label 映射错位 | 中 | 在 implementation gate 中作为 R01/R04 的验证项 |
| `reason_json` 为空时无法获取 terminal reason | 中 | 在 implementation gate 中作为 R02 的验证项 |
| reopen/reconnect byte-identical 假设未经 schema 验证 | 低 | 在 implementation gate 第一时间验证 |
| README 更新遗漏 | 低 | implementation review 时按 AGENTS.md 约束逐项核实 |

---

## Final Plan Review Conclusion: **pass-with-risks**

Plan 的 root cause 分析正确，设计方案总体合理，owner boundary 清晰，且 stop conditions 为 public contract change 提供了硬安全边界。

8 个 findings 中：
- **R01**（空文本边界）和 **R02**（terminal reason 真源）是高风险的 missing contract，必须在 implementation gate 启动前明确设计决策
- **R03–R06** 是中风险的 specification gap，应在 implementation 开始时参照本 review 建议的契约补充到设计或 code comment 中
- **R07–R08** 是低风险的验证/流程项，可在 implementation 过程中按建议逐项检查

没有发现阻止进入 implementation gate 的致命缺陷。
