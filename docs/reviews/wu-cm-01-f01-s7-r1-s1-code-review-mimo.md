# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-dur-obs-cm-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f01-s7-r1-s1-code-review-mimo.md`
- Included scope: `dayu/host/run_input.py`、`tests/host/test_run_input_builder.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_public_tool_wiring_smoke.py`、`tests/host/test_public_open_host_multiturn_smoke.py`、`tests/host/public_smoke_support.py`、`dayu/host/README.md`、`tests/README.md`、`docs/host/design.md` §23 / §24.6、`docs/host/wu-cm-01-f01-s7-r1-one-system-message-rescope-plan.md`、`docs/reviews/wu-cm-01-f01-s7-r1-s1-implementation-codex.md`
- Excluded scope: Engine / Runner / Service 层、durable schema、Host public API dataclass
- Parallel review coverage: 无

## Findings

未发现实质性问题。

以下是对 review 重点的逐项 evidence-based 裁决：

### 1. ordinary public AgentRunRequest.messages 至多一条 system 且位于首位

**裁决: PASS**

- `run_input.py:2487-2531`：`_normalize_ordinary_run_messages()` 从候选 messages 全局抽取所有 `SystemMessage`，按 section 归类后合并为单条 `SystemMessage`，放在 `non_system_messages` 之前。
- `run_input.py:2528-2531`：返回值为 `(SystemMessage(...), *tuple(non_system_messages))`，保证 system 位于 index 0。
- `tests/host/test_run_input_builder.py:3732-3746`：`_single_system_content()` 断言 `len(system_messages) == 1` 且 `messages[0] is system_messages[0]`，覆盖所有 focused RunInputBuilder 测试。
- `tests/host/public_smoke_support.py:175-205`：`assert_at_most_one_system_message()` 断言至多一条 system 且位于 index 0。
- `tests/host/test_public_tool_wiring_smoke.py`、`test_public_open_host_multiturn_smoke.py`：在所有 public smoke runner call 后调用 `assert_at_most_one_system_message()`。

### 2. compactor proposal 未被错误纳入 ordinary contract

**裁决: PASS**

- `run_input.py:2487` 的 `_normalize_ordinary_run_messages` 只在 `RunInputBuilder.build()` 的 ordinary path 调用（`run_input.py:1924`）。
- compactor proposal 使用独立的 `CompactorRunInputBuilder`（`run_input.py:2055` 附近），不经过 `_normalize_ordinary_run_messages`。
- `docs/host/design.md:2550`：明确定义 "Host-owned compactor proposal call 不属于该 ordinary RunInput contract，而受 24.2 compact I/O 边界约束"。
- `tests/host/test_public_compact_smoke.py`：compactor manifest 的 `runner_call_kind == "compactor_proposal"` 与 ordinary path 分离。

### 3. RUNNER_CALL_INPUT_ASSEMBLED manifest 记录 normalized final messages

**裁决: PASS**

- `run_input.py:1924-1937`：`_normalize_ordinary_run_messages(candidate_messages)` 在 manifest recorder 调用之前执行，`RunnerCallManifestRecordInput.messages=messages` 传入的是归一化后的最终 messages。
- `run_input.py:3386-3416`：manifest body 的 `message_count`、`message_entries`、`role_sequence_digest` 均从 `record_input.messages` 计算。
- `tests/host/test_run_input_builder.py:360-402`：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 断言 `hot_payload["message_count"] == len(request.messages)` 且 `role_sequence_digest` 与 request messages 同源。

### 4. section 标题和顺序符合设计 §23 并与 §24.6 assembly-order 概念一致

**裁决: PASS**

- `run_input.py:161-179`：`_SYSTEM_ENVELOPE_SECTION_ORDER` 固定为：
  1. `Task Instructions`
  2. `Execution Guidance`
  3. `Conversation Summary`
  4. `Verified Evidence and Facts`
  5. `Prior Answer Anchors`
  6. `Open Follow-up Context`
  7. `Reference Continuity`
  8. `Recent Evidence`
  9. `Resume Guidance`
- `docs/host/design.md:2554-2564`：§23 section table 的顺序与代码完全一致。
- `docs/host/design.md:3009-3023`：§24.6 Prompt Assembly 的 assembly-order 概念与 §23 一致（§24.6 的编号 9 replay/resume guidance 对应 §23 的 `Resume Guidance`，§24.6 的编号 10 tool schema snapshot 不进入 system envelope 而是作为 Engine request 独立字段）。
- `run_input.py:2534-2602`：`_system_envelope_section_and_body()` 的 prefix routing 将每种 material 正确映射到对应 section。
- `run_input.py:2623-2638`：`_non_empty_system_section_blocks()` 按 `_SYSTEM_ENVELOPE_SECTION_ORDER` 固定顺序输出非空 section。

### 5. accepted evidence、recent fallback、resume guidance 唯一归属且不双重渲染

**裁决: PASS**

- `run_input.py:2590-2594`：`_ACCEPTED_TOOL_EVIDENCE_PREFIX` 路由到 `_SYSTEM_SECTION_RECENT_EVIDENCE`（未进入 memory/fact pipeline 的 evidence）。
- `run_input.py:2560-2564`：`_MEMORY_EVIDENCE_FACT_HEADER` 路由到 `_SYSTEM_SECTION_VERIFIED_EVIDENCE`（已进入 memory/fact pipeline 的 evidence）。
- `docs/host/design.md:2566`：设计明确定义 "已经作为 verified / accepted memory facts 的材料只能进入 Verified Evidence and Facts；未进入 memory / fact pipeline 的 recent-window fallback 只能进入 Recent Evidence；同一条 evidence material 不得同时渲染到两个 section"。
- `run_input.py:2596-2600`：`_RESUME_GUIDANCE_PREFIX` 路由到 `_SYSTEM_SECTION_RESUME_GUIDANCE`，与 evidence sections 分离。
- 代码中无路径将同一 material 同时路由到两个 section。

### 6. LLM-facing 内容不暴露内部治理标识

**裁决: PASS**

- `run_input.py:1730-1751`：`build_scene_messages()` 删除 `policy_snapshot_ref` 参数，使用 Host-neutral 业务说明 "Use the available context and tools under the current run limits."。
- `run_input.py:2301-2311`：`_memory_evidence_fact_message()` 只投影 `claim_text` 和 `evidence_kind`，不投影 `event_id`、`event_sequence`、`extraction_operation_ref` 或 `evidence_refs`。
- `run_input.py:2786-2809`：`_accepted_tool_evidence_content()` 只投影 `readable_tool_name`、`readable_query_text`、`readable_source_text`，不投影 `tool_call_id`。
- `run_input.py:3475-3487`：resume guidance 使用 `tool_name`、`resolution_kind`、`tool_fact_kind` 和 `result`，不投影 `tool_call_id` 或 wait id。
- `run_input.py:191-210`：`_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` 包含 20 个内部标识模式。
- `run_input.py:2673-2677`：`_validate_system_envelope_content()` 对 envelope 内容做 forbidden fragment 检查。
- `tests/host/test_run_input_builder.py:643-648`：focused 测试断言 `evidence_refs=`、`extraction_operation_ref=`、`event_id=`、`event_sequence=`、`digest_ref=` 不出现在 system envelope 中。
- `tests/host/test_run_input_builder.py:3757-3772`：`_assert_system_content_has_no_internal_refs()` 在所有 `_single_system_content()` 调用中自动执行。

### 7. boundedness sanity 是否真实

**裁决: PASS**

- `run_input.py:2680-2694`：`_system_envelope_overhead()` 精确计算 `len("## ") + len(section) + 1` 每个 header 加 `len("\n\n") * (n-1)` separator。
- `run_input.py:2671-2672`：`len(content) > source_system_chars + overhead` 时抛出 `HostDurableError`。
- `source_system_chars` 在 `run_input.py:2508` 累加每条候选 system message 的 `len(content.strip())`。
- overhead 计算与 `_render_system_envelope()` 的实际渲染格式 `f"## {section}\n{body}"` + `"\n\n".join(...)` 严格一致。
- `tests/host/test_run_input_builder.py:360-402`：大输入测试断言 manifest 不内联完整 message text（`len(manifest_text) < 5000`），验证 manifest 有界。

### 8. 测试覆盖 public path 且没有放松

**裁决: PASS**

- `tests/host/test_run_input_builder.py`：focused 测试覆盖 memory rendering、section order、forbidden fragments、manifest bounds、role preservation、deterministic output。
- `tests/host/test_public_tool_wiring_smoke.py`：tool wiring smoke 在每个 runner call 后调用 `assert_at_most_one_system_message()`。
- `tests/host/test_public_open_host_multiturn_smoke.py`：multiturn smoke 在每个 request 后调用 `assert_at_most_one_system_message()`。
- `tests/host/test_public_compact_smoke.py`：compact smoke 保留 `_FORBIDDEN_COMPACTOR_PROMPT_TERMS` 检查和 compactor material instruction contract 断言。
- 实现 artifact 报告 `56 passed, 1 skipped`，未删除或削弱任何既有断言。

### 9. README 只同步稳定职责

**裁决: PASS**

- `dayu/host/README.md`：新增 RunInputBuilder manifest recorder 和 one-system envelope 说明，属于 Host 开发手册职责范围。
- `tests/README.md`：同步 public smoke helper 的首位 system contract 和 RunInputBuilder envelope 覆盖范围，属于测试手册职责范围。
- 根目录 `README.md` 和 `dayu/README.md` 未修改，符合预期（CLI、安装、trace/render 入口和分层边界未变）。

## Open Questions

无。

## Residual Risk

- `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`（生产代码 20 项）与 `_assert_system_content_has_no_internal_refs`（测试代码 12 项）的 forbidden fragment 列表存在差异。测试列表缺少 `manifest_payload_ref=`、`manifest_digest=`、`projector_metadata`、`attempt_id=`、`execution_id=`、`runner_call_index=`、`projection_checkpoint`、`manifest_payload_ref=` 等模式。当前无风险，因为这些模式不会出现在 system envelope 内容中；但如果未来渲染路径变更，测试可能无法及时捕获泄漏。建议将测试 forbidden 列表与生产列表对齐。
- real provider matrix 仍为 environment-gated，不在本轮 deterministic shape slice 范围内。
- historical evidence 使用 `tool` role 的 Engine contract 扩展属于后续 work unit。

## Conclusion

**PASS**

WU-CM-01-F01-S7-R1-S1 production implementation 正确实现了 ordinary public RunInput 的 one-system-message hard contract。所有 review 重点均有直接代码证据支撑：normalization 函数在 manifest recorder 之前执行、section 顺序与设计 §23 / §24.6 一致、evidence material 唯一归属无双重渲染、LLM-facing 内容不暴露内部治理标识、boundedness sanity 检查真实有效、测试覆盖 public path 且未放松断言、README 只同步稳定职责。未发现 correctness、stability 或 maintainability 级别的实质性缺陷。
