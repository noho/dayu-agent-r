# P12.6 Slice 7 Code Review - AgentMiMo - 2026-05-24

## Verdict

**PASS** — 无 blocking findings。4 个 non-blocking findings（2 medium、2 low）。

## Review 范围

- Base: `a2114a2 gateflow: accept P12.6 slice 6`
- Diff: `dayu/host/dispatch.py`、`dayu/host/run_input.py`、`tests/host/fake_compaction.py`、`tests/host/test_public_compact_smoke.py`、`dayu/host/README.md`、`tests/README.md`
- 忽略: `docs/host/implementation-control.md` 总控状态改动

## Review 逐项结论

### 1. accepted TOOL_RESULT_ACCEPTED raw evidence 是否 bounded/deterministic 地进入 proactive pre-start compactor evidence_input

**PASS。**

`build_accepted_tool_evidence_material_blocks()` (`run_input.py:1101-1178`) 读取窗口为当前 Session 内 `before_event_sequence` 之前最近 N 条 `TOOL_RESULT_ACCEPTED`，固定上限 `_ACCEPTED_TOOL_EVIDENCE_MATERIAL_LIMIT = 8`。SQL 先 `ORDER BY event_sequence DESC LIMIT ?`，Python 端 `reversed(rows)` 恢复升序，保证 selection 与 prompt label 分配稳定。proactive path (`dispatch.py:3376-3388`) 调用同一 helper，传入 `run.input_event_sequence` 作为排他上界。

### 2. 是否恢复了 EventLog ledger dump、session 起点 unbounded range collector、result_preview，或把 event id/payload ref/digest/cursor/policy/artifact descriptor 暴露为 LLM semantic input

**PASS。**

未恢复任何上述有害模式。`build_accepted_tool_evidence_material_blocks` 复用 `collect_selected_compaction_request_evidence_inputs` 解析 accepted evidence，只取 `raw_result_text` 作为 material `text`；canonical refs 只写入 material block 内部 provenance 字段（`canonical_source_refs`、`accepted_evidence_id`、`tool_result_event_ref` 等），不进入 LLM-facing material JSON。测试断言 `result_preview not in material_text`、`payload: not in material_text`、`event-tool-result not in material_text`（`test_public_compact_smoke.py:212-214`、`241-243`）。

### 3. stable fact / compact artifact represented evidence refs 排除逻辑是否正确

**PASS。**

RunInputBuilder material path: `MemorySnapshotView.represented_evidence_refs` 由 `_memory_represented_evidence_refs(snapshot)` (`run_input.py:2369-2383`) 从 `snapshot.evidence_backed_facts` 提取。`CompactArtifactView.represented_evidence_refs` 由 `_preserved_canonical_evidence_refs(payload)` (`run_input.py:2673-2685`) 从 compact event payload 的 `preserved_fact_refs.canonical_evidence_refs` 提取。两者经 `_represented_evidence_refs(memory, compact)` (`run_input.py:2398-2415`) 合并去重后传入 `build_accepted_tool_evidence_material_blocks`，用 `frozenset` 查找跳过已表示 evidence。

Proactive path: `_proactive_represented_evidence_refs(transaction, run, policy_digest)` (`dispatch.py:3304-3335`) 独立读取最新 memory snapshot 的 stable fact evidence refs 和最新 compact event 的 preserved canonical evidence refs，合并去重。逻辑正确覆盖两个来源。

**注意**: proactive path 的排除集合构造与 RunInputBuilder path 的排除集合构造是独立实现（非共用同一 helper），但语义一致。见 Finding F2。

### 4. RunInputBuilder material path 与 dispatch proactive path 是否共用同一 accepted evidence helper

**PASS。**

两条路径都调用 `build_accepted_tool_evidence_material_blocks()` (`run_input.py:1101`)。proactive path 在 `dispatch._proactive_material_blocks()` (`dispatch.py:3372-3388`) 中调用；RunInputBuilder path 在 `DurableAcceptedToolEvidenceMaterialProvider._load_accepted_tool_evidence_materials_tx()` (`run_input.py:1091-1098`) 中调用。无重复解析逻辑。

### 5. public smoke 是否真正走 open_host(options)+mock business tool+deterministic compactor production path

**PASS。**

`test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` (`test_public_compact_smoke.py:150-243`):
- 使用真实 `open_host(_fake_compact_open_options(...))` public opener
- 第一轮通过 `ToolCallingWorkerFactory` + `_LongChapterMockTool`（真实 `HostToolingOptions` + `ToolBundle`）产生 accepted raw tool evidence
- 第二轮触发 proactive compact（soft threshold 90 tokens，长输入）
- `FakeCompactorRunAgent` monkeypatches `dayu.host.llm_compaction._run_agent_request`，记录生产 compactor 收到的 material JSON 并返回 label-only deterministic proposal
- 断言 fake compactor 收到的 material JSON 包含 `evidence_input` 且含 `_LONG_CHAPTER_MARKER`
- 断言后续第三轮 ordinary RunInput 包含 `Memory evidence-backed facts:` 且含 marker
- 手造 `_llm_material_with_long_tool_evidence()` 仅用于 helper-level 补充断言（`fake_compaction_proposal_from_material_json` 的 label-only 行为）

### 6. AGENTS 约束

**PASS（附 Finding F1、F3）。**

- 中文 docstring: 全部新增函数、类、dataclass 均有完整中文 docstring。
- 严格类型: 无 `Any`、无 `object` 签名。`cast(Mapping[str, JsonValue], value)` (`fake_compaction.py:385`) 用于 runtime JSON 类型收窄，符合约束。
- 无兼容 wrapper: 未引入兼容性 re-export 或 facade。
- README 职责: `dayu/host/README.md` 更新 Context Compaction 段落描述 proactive evidence 补入；`tests/README.md` 更新 public compact smoke 描述。均在职责范围内。

## Findings

### F1 [Medium] `_text_tuple_from_mapping` 与 `_optional_text_list` 逻辑重复

**文件**: `dayu/host/dispatch.py:3375-3392` vs `dayu/host/run_input.py:2776-2792`

**证据**: `dispatch.py` 新增 `_text_tuple_from_mapping(mapping, field_name)` 与 `run_input.py` 已有 `_optional_text_list(payload, field_name)` 逻辑完全相同：读取 mapping 中指定 key，校验为 `list`，逐项过滤非空 `str`，返回 `tuple[str, ...]`。

**影响**: 违反"数据处理重复逻辑必须抽取"约束。后续修改排除逻辑时需同步两处。

**建议**: 删除 `_text_tuple_from_mapping`，从 `run_input.py` 导出 `_optional_text_list` 或在 `dispatch.py` 中直接调用。`dispatch.py` 已 import `run_input.py` 多个符号，增加一个私有 helper import 不引入新依赖方向。

### F2 [Medium] proactive represented evidence refs 构造未复用 `_preserved_canonical_evidence_refs`

**文件**: `dayu/host/dispatch.py:3326-3334` vs `dayu/host/run_input.py:2673-2685`

**证据**: `dispatch._proactive_represented_evidence_refs` 手动从 compact event payload 读取 `preserved_fact_refs` → `canonical_evidence_refs` 的两层嵌套逻辑，与 `run_input._preserved_canonical_evidence_refs(payload)` 完全相同。RunInputBuilder 的 `DurableCompactArtifactProvider` 已调用后者。

**影响**: 两处独立实现同一 payload 解析路径，后续 compact payload schema 变更需同步两处。

**建议**: `dispatch._proactive_represented_evidence_refs` 导入并调用 `run_input._preserved_canonical_evidence_refs(_payload_object(compacted))`，消除手动两层嵌套。

### F3 [Low] `fake_compaction.py` 导入 `_candidate_from_final_answer` 私有符号

**文件**: `tests/host/fake_compaction.py:14`

**证据**: `from dayu.host.llm_compaction import _candidate_from_final_answer`。下划线前缀表示模块私有。

**影响**: 测试对生产模块内部实现产生脆弱耦合。生产代码重命名或重构该函数时测试会静默失败。

**建议**: 当前可接受——fake compactor 需要复用生产 proposal parser 以保证 label→candidate 映射一致性，且该函数签名已由 `LLMContextCompactor` 调用路径稳定约束。如果后续 `_candidate_from_final_answer` 重构，需同步更新此导入。

### F4 [Low] `_latest_session_compacted_event_before_input` 新建 `EventLogStore()` 实例

**文件**: `dayu/host/dispatch.py:3369`

**证据**: `event = EventLogStore().read_event_by_id(transaction, event_id)`。同一函数的调用方 `_proactive_material_blocks` 已接收 `event_log_store` 参数，但 `_latest_session_compacted_event_before_input` 未接收该参数，自行新建实例。

**影响**: `EventLogStore` 是无状态包装器（方法只委托给模块级函数），功能正确。但风格上与调用方已有 `event_log_store` 参数不一致。

**建议**: 将 `event_log_store` 作为参数传入 `_latest_session_compacted_event_before_input`，与同文件其它 helper 保持一致。

## Tests Reviewed

| 测试 | 覆盖点 | 评估 |
|------|--------|------|
| `test_no_compaction_recent_raw_turns_continuity` | 无 compact 时 follow-up 保持 raw turn 连续性 | ✅ 走 public `open_host` + `FinalAnswerWorkerFactory` |
| `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | proactive compact 后 evidence→fact→后续 memory 复用 | ✅ 走 public `open_host` + mock tool + monkeypatched compactor；断言 evidence_input 存在、marker 透传、result_preview/payload/event-id 不泄漏 |
| `test_long_user_input_second_factor_survives_minimum_preserve` | 长输入 compact 后 minimum preserve 保留关键文本 | ✅ 断言第二因素 marker 和 `Memory minimum preserve continuity:` 出现 |
| `test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` | 多次 compact 后 prompt/memory 有界 | ✅ 断言 `max(prompt_lengths) <= 9000` 和 memory 长度上限 |
| `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` | 重复长 prompt 不因 material 重复超窗 | ✅ 断言 prompt 长度 ≤ 9000 |
| `test_real_compactor_public_opener_compacts_and_preserves_continuity` | 真实 compactor smoke | ✅ 默认 skip，需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` |
| `fake_compaction_proposal_from_material_json` helper | label-only proposal 不含 canonical refs | ✅ 测试中补充断言 |

### Tests Recommended

- 未来可考虑增加：proactive path 中已有 memory snapshot 和 compact event 同时存在时，evidence refs 排除交集正确性的 focused test。当前 smoke 通过多轮 compact 间接覆盖。

## Residual Risks

- proactive budget estimator 仍按当前输入估算触发条件；本次修复只补齐 compactor material evidence，不改变 context budget estimator 输入模型。
- accepted evidence 读取上限硬编码为 8；未来若需按 token budget 或 evidence priority 调整，需独立设计。
- 真实 provider compactor smoke 默认 skip，deterministic fake compactor 覆盖 public opener production path；真实 LLM 输出解析路径需 `DAYU_RUN_REAL_COMPACTOR_SMOKE=1` 单独验证。
- F1/F2 的重复逻辑当前不影响正确性，但增加后续维护成本。
