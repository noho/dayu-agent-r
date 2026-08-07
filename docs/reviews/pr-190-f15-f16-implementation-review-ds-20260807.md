# PR190 F15/F16 Implementation Review（DeepSeek 独立审查）

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `580b1427` (HEAD)
- Output file: `docs/reviews/pr-190-f15-f16-implementation-review-ds-20260807.md`
- Included scope: 全部 10 个 diff 文件 + 2 个 untracked 生产文件 + 2 个 workspace/tmp 临时消费者
- Excluded scope: `docs/gateflow/pr-190-f15-f16-implementation-20260807.md`（implementation artifact，已阅读但作为 reference 而非 review target）
- Parallel review coverage: 无；本审查为主 reviewer 单线 deep walk

## Pre-review baseline checks

- `git diff HEAD -- dayu/host/durable/run_transition.py` → **empty**（Controller 纠正后的 writer 撤回审计通过）
- `HOST_RUN_TERMINAL_EVENT_TYPES` = `(RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED, RUN_LOST)`，不含 `RUN_CANCELLING`、Attempt terminal 及其他 lifecycle event（`dayu/host/lifecycle_events.py:133-138`）
- `CancelMode` 仅含 `GRACEFUL = "graceful"`，无 `FORCE`（`dayu/host/api.py:462-468`）
- `validate_previous_compacted_view_pair` 未修改（`dayu/host/compaction.py:3591-3609`）
- `normalized_material_text` 已存在且 raise `ValueError` on empty（`dayu/host/compact_material.py:837-852`）
- F14 `compacted_source_refs` 无 diff 改动

## Findings

### 1-PASS-F15-canonical-single-projection

- **入口/函数**: `_canonical_previous_replacement_projection()` → `_previous_compacted_view_pair_from_replacement()`
- **文件(行号)**: `dayu/host/compact_material.py:2674-2726`（projection factory）、`:2596-2672`（pair builder）
- **验证结果**: **PASS**

**五区同源证据链：**

1. `_canonical_previous_replacement_projection(replacement)` 一次遍历 `CompactAcceptedReplacementV4` 的全部 text leaf：`session_summary.text`、`evidence_facts[*].claim`、`answer_anchors[*].title`、`answer_anchors[*].detail`、`forward_intents[*].text`、`reference_continuity[*].text`，每个 leaf 恰好调用一次 `_canonical_material_text()` → `normalized_material_text()`（`:2685-2722`）。
2. Packed blocks 全部经 `_previous_block_from_canonical_text()` → `_run_input_material_block_from_canonical_text(text=canonical_text, ...)` 消费 canonical atoms，`text.value` 直接成为 block text，不经二次 normalizer（`:2777-2814`）。
3. Readable view 由 `_readable_previous_view_from_canonical_projection(projection, ...)` 消费同一 `projection` 的 `session_summary.value`、`fact.claim.value`、`intent.text.value`、`reference.text.value`（`:2851-2926`）。
4. Answer anchor 先经 `_readable_answer_anchor_from_canonical(anchor, index=index)` 构造 typed `ReadableAnswerAnchorVNext`（`:2731-2757`），再经 `_canonical_answer_anchor_block_text(anchor)` 正向渲染 packed text（`:2760-2774`）；禁止从 rendered string 逆向解析。
5. `evidence_facts[*].canonical_evidence_refs`、`forward_intents[*].intent_type/status`、`references[*].reason` 等非文本 typed field 均原样从 projection 携带，不经 normalizer。

**反例检查：** 无。不存在任何 `replacement.xxx.text` 直接进入 packed block 或 readable view 的路径；不存在从 `previous_answer_anchor_block_text()` 返回值拆 bullet/ordinal/title/detail 的代码。

### 2-PASS-F15-whitespace-markdown-table-exact

- **入口/函数**: `_canonical_material_text()` → `normalized_material_text()` → `_normalized_material_line()`
- **文件(行号)**: `dayu/host/compact_material.py:865-872`、`:837-852`、`:855-862`
- **验证结果**: **PASS**

**格式矩阵证据链：**

- `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact`（`tests/host/test_compact_material.py:2062-2242`）覆盖：leading/trailing/repeated whitespace、blank lines、multiline prose、Markdown bullet list（`- bullet   one`）、numbered list（`1. numbered   item`）、Markdown table（`| year | value | ...`）。
- 该测试的 anchor title 从 `"  FY2025   conclusion  "` → `"FY2025 conclusion"`；detail 从多行含空白 Markdown → 归一化后 packed/readable exact 一致。
- Packed block text 最终为 `"FY2025 conclusion\n- first paragraph\n- bullet one\n1. numbered item\n| year | value |\n| --- | ---: |\n| 2025 | 21.7% |"`，与 `previous_answer_anchor_block_text(ReadableAnswerAnchorVNext(...))` 渲染结果一致。
- Validator（`:3650-3653`）对 answer anchor 执行 `previous_answer_anchor_block_text(item)` 与 block text 的 exact 比较，不改。

**空行/首尾/重复空白：** `normalized_material_text()` 的 `"\n".join(line for line in normalized_lines if line != "")` 去除 blank-only lines；`_normalized_material_line()` 的 `" ".join(text.split())` 折叠行内空白。均为既有逻辑，未修改。

### 3-PASS-F15-accepted-tool-evidence-exact-path

- **入口/函数**: `run_input_material_block()`
- **文件(行号)**: `dayu/host/compact_material.py:1002-1048`
- **验证结果**: **PASS**

**证据链：**

- `accepted_tool_evidence is not None` 分支（`:1002-1030`）：`text=text`（原样，不经 normalizer），`size_units=len(text)`，`content_digest=_text_digest(text)`。
- 该分支不调用 `_canonical_material_text()`，不经过 `_run_input_material_block_from_canonical_text()`，不经过 typed wrapper。
- 旧实现行为 `material_text = text if accepted_tool_evidence is not None else normalized_material_text(text)` 与新实现语义等价。

**反例检查：** `accepted_tool_evidence is not None` 时没有代码路径会调用 `normalized_material_text(text)` 或 `_canonical_material_text(text)`。

### 4-PASS-F15-strict-validator-unchanged

- **入口/函数**: `validate_previous_compacted_view_pair()`
- **文件(行号)**: `dayu/host/compaction.py:3591-3609`；caller `dayu/host/compact_material.py:2668`
- **验证结果**: **PASS**

**证据：**

- `validate_previous_compacted_view_pair` 函数体无 diff。
- 所有 caller（`:533`、`:1225`、`:1232`、`:1262`、`:1422`、`:2668`）均保留。
- 无 loose compare、raw fallback、`try/except` 吞异常或 whitespace-tolerant 分支引入。
- 恢复路径 `transform_previous_compacted_view_pair_for_recovery()` 保持"先验证 → 同步过滤 → 再验证"流程不变。

### 5-PASS-F15-durable-reopen-byte-exact

- **入口/函数**: `build_pre_dispatch_compact_material_view()` via reopen
- **文件(行号)**: `tests/host/test_compact_material.py:2107-2147`（reopen 段）
- **验证结果**: **PASS**

**证据链：**

1. `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 先在 writable store 构造数据并读取 view（`:2088-2106`），再关闭 store。
2. 通过 `open_host_durable_read_store(...)` 物理只读 reopen（`:2110-2114`），重新从 durable accepted event/artifact 构造 view。
3. 断言 `reopened_readable.to_json() == readable.to_json()`（`:2133`）。
4. 断言每个 block 的 `(text, size_units, content_digest)` byte-exact 相等（`:2136-2143`）。
5. `test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run`（`tests/host/test_dispatch_scheduler.py:9031-9099`）进一步使用 writable store → reopen writable store → scheduler dispatch → worker accept 的真实闭环，不依赖 direct Host smoke。

### 6-PASS-F15-F14-frontier-zero-drift

- **验证结果**: **PASS**

**证据：**

- `git diff HEAD -- dayu/host/compact_material.py | grep compacted_source_refs` → 无输出。
- canonical projection（`_CanonicalPreviousReplacementProjection`）不包含 `compacted_source_refs` 字段。
- `_canonical_previous_replacement_projection()` 不读取或写入 F14 frontier。
- 实现 artifact 明确声明 `compacted_source_refs` / frontier 实现无改动。

### 7-PASS-F16-EventLog-window-keyset-session-run-pairing

- **入口/函数**: `_read_filtered_window()` → `_project_terminal_rows()`
- **文件(行号)**: `utils/cli_ci_run_observation.py:399-438`（keyset reader）、`:441-516`（projection）
- **验证结果**: **PASS**

**证据链：**

1. Filter 只含 `RUN_ACCEPTED` + `HOST_RUN_TERMINAL_EVENT_TYPES`（`:37-48`），由 `EventLogReadClassFilter(event_class=CANONICAL_FACT, ...)` 限定。
2. Keyset 推进：`cursor = window.start_event_sequence`，每页 `read_events_after_matching(cursor, ..., max_event_sequence=window.end_event_sequence)`（`:419-426`）。
3. No-progress（`covered_event_sequence <= cursor`，`:427-430`）和 overrun（`covered_event_sequence > window.end_event_sequence`，`:431-432`）均 fail closed。
4. 每个 row 的 `event_sequence` 必须在 `(cursor, window.end_event_sequence]` 范围内（`:434-435`）。
5. 无 OFFSET；`page_size` 仅控制 `limit` 参数（`:423`）。
6. `session_id` 透传至 `read_events_after_matching`（`:425`）。
7. `RUN_ACCEPTED` 按 `event_sequence` 升序投射为 `accepted_ordinal`（`:478`），terminal 按 `run_id` 配对（`:484-490`）。

### 8-PASS-F16-exact-order-offset-role

- **入口/函数**: `_project_terminal_rows()` + `observe_run_terminals()`
- **文件(行号)**: `utils/cli_ci_run_observation.py:478-515`
- **验证结果**: **PASS**

**证据：**

- Accepted ordinal 分配：`accepted_ordinal = accepted_ordinal_offset + local_ordinal`（`:479`），`local_ordinal` 由 `enumerate(accepted_rows, start=1)` 确定，完全由真实 accepted event sequence 驱动（`:478`）。
- Role 校验：`role = roles_by_accepted_ordinal.get(accepted_ordinal)`，不是 `RunObservationRole` 实例则 raise（`:481-483`）。
- Role 完备性：`set(roles_by_accepted_ordinal) != expected_role_ordinals` 时 raise（`:514-515`），防止 role mapping 与被观察 accepted ordinals 不 exact 对齐。
- 事实 identity 保留：`session_id`、`run_id`、`accepted_event_id`、`accepted_event_sequence`、`terminal_event_id`、`terminal_event_sequence` 均在 `RunTerminalObservation` 中独立保存（`:496-512`）。

### 9-PASS-F16-terminal-reason-unique-owner

- **入口/函数**: `_terminal_reason()`
- **文件(行号)**: `utils/cli_ci_run_observation.py:564-620`
- **验证结果**: **PASS**

**证据链：**

1. Reason 唯一源：`row.reason_json` → `json.loads()` → `decoded[_REASON_KEY]`（`:577-617`）。
2. `reason_json is None` → `RunObservationError("terminal reason_json is missing")`（`:577-578`）。
3. `json.loads()` 失败 → `RunObservationError("terminal reason_json is malformed")`（`:581-582`）。
4. 结果不是 `dict` → `RunObservationError("terminal reason_json must be object")`（`:583-584`）。
5. `reason` 不是 non-empty `str` → `RunObservationError("terminal reason must be non-empty string")`（`:617-619`）。
6. **禁止 payload fallback**：`_terminal_reason` 不读取 `row.payload_json`；`observe_run_terminals` 不访问 `host_runs` 表。测试 `test_terminal_reason_rejects_missing_extra_blank_or_wrong_typed_object` 参数化覆盖：`None`（missing）、wrong key（`{"why":"wrong-key"}`）、extra key（`{"reason":"ok","extra":"forbidden"}`）、blank（`{"reason":"   "}`）、wrong type（`{"reason":3}`）、non-object（`["reason","wrong-shape"]`）→ 全部 `RunObservationError`（`tests/cli/test_cli_ci_run_observation.py:151-217`）。

### 10-PASS-F16-cancel-lost-extras-fail-closed

- **入口/函数**: `_terminal_reason()`
- **文件(行号)**: `utils/cli_ci_run_observation.py:586-616`
- **验证结果**: **PASS**

**Cancel（`:586-598`）：**
- 合法 key set：`{"reason"}` 或 `{"reason", "mode"}`；其他 → `"unknown canonical keys"`。
- `mode` 存在时：必须是 `str` 且在 `CancelMode` 枚举值集合中（当前只有 `"graceful"`）；`"force"` → `"mode is invalid"`。
- 与 `CancelMode(StrEnum)` 定义一致（`:462-468`），仅 `GRACEFUL = "graceful"`。

**Lost（`:599-612`）：**
- 合法 key set：`{"reason"}` 或 `{"reason", "orphan_proof"}`；其他 → `"unknown canonical keys"`。
- `orphan_proof` 存在时：必须是非空 `str`（`orphan_proof.strip() == ""` → `"orphan_proof is invalid"`）。

**Succeeded/Failed（`:613-616`）：**
- 必须 exact `{"reason"}`；任何 extra key → `"exact reason key"`。

**Producer 侧锁定：**
- `test_startup_orphan_run_lost_keeps_canonical_orphan_proof_reason_shape`（`tests/host/test_run_attempt_transitions.py:2781-2826`）：`RUN_LOST` reason = `{"reason": "startup_orphan_attempt_lost", "orphan_proof": "owner_pid_missing"}`。
- `test_cancel_run_cancels_waiting_run_without_resume_attempt`（`tests/host/test_wait_cancel_late_result.py:95-110`）：`RUN_CANCELLED` reason = `{"reason": "user_cancel", "mode": "graceful"}`。
- `test_scheduler_close_writes_active_cancel_closeout_terminal`（`tests/host/test_active_cancel_dispatch.py:1760-1766`）：`RUN_CANCELLED` reason 包含 `"reason"` 且为 non-empty str。
- `test_dispatch_scheduler.py` 多处断言：`RUN_FAILED` reason = `{"reason": "stream_ended_without_terminal"}`、`RUN_LOST` reason = `{"reason": "worker_lost_before_terminal"}` 等 exact object（`:4396-4399`、`:4438-4441`、`:5112-5115`）。

### 11-PASS-F16-duplicate-missing-stale-window

- **入口/函数**: `_project_terminal_rows()`
- **文件(行号)**: `utils/cli_ci_run_observation.py:441-516`
- **验证结果**: **PASS**

**Duplicate（`:488-489`）：**
- `len(terminal_rows) > 1` → `RunObservationError("accepted Run has duplicate terminal facts")`。
- 同 Run 两条不同 terminal type（如 FAILED + LOST）同样触发。
- Attempt terminal（`ATTEMPT_SUCCEEDED` 等）和 `RUN_CANCELLING` 不在 filter 中，不参与 duplicate 判断。
- 测试 `test_second_same_or_different_run_terminal_is_invalid`（`tests/cli/test_cli_ci_run_observation.py:220-276`）：FAILED → LOST duplicate → `RunObservationError`。

**Missing terminal（`:486-487`）：**
- `len(terminal_rows) == 0` → `RunObservationError("accepted Run has no terminal in frozen window")`。

**Terminal 不跟随 accepted（`:494-495`）：**
- `terminal.event_sequence <= accepted.event_sequence` → `RunObservationError("Run terminal does not follow RUN_ACCEPTED")`。

**Terminal 无 accepted（`:474`）：**
- `set(terminals_by_run).difference(accepted_run_ids)` 非空 → `RunObservationError`。

**Stale window（keyset reader，`:427-432`）：**
- cursor 不前进或超过 frozen end → `RunObservationError`。

### 12-PASS-F16-process-outcome-separation

- **入口/函数**: `prompt_observe_calibration.py:_run_scenario()` → `command.json`
- **文件(行号)**: `workspace/tmp/prompt_observe_calibration.py:2744-2752`
- **验证结果**: **PASS**

**证据：**

- Process outcome 字段为 `process_outcome.kind ∈ {exited, timed_out, harness_error}`、`exit_code`、`timed_out`（`:2744-2752`）。
- `test_process_exit_zero_does_not_satisfy_failed_run_dependency`（`tests/cli/test_cli_ci_run_observation.py:414-472`）：`exit_code=0` 的 failed Run → `evaluate_success_dependency` 返回 `STOPPED`，不因 process exit 0 而 proceed。
- `evaluate_success_dependency()` 不读取任何 process 相关参数；只读取 `RunTerminalObservation` 的 `terminal_class`。
- 旧 `execution_outcome=success` 字段已删除，被 `process_outcome` 替代。
- `f14_real_cli_observation.py:_segment_terminal_facts` 从 `run-terminals.json` 读取 terminal facts，不查询 `command.json` 的 process outcome。

### 13-PASS-F16-dependency-stop-isolation

- **入口/函数**: `evaluate_success_dependency()`、`_run_pty()` dependency gate
- **文件(行号)**: `utils/cli_ci_run_observation.py:342-396`（pure function）、`workspace/tmp/prompt_observe_calibration.py:1199-1244`（PTY harness）
- **验证结果**: **PASS**

**证据链：**

1. `evaluate_success_dependency()` 只有 `terminal_class is SUCCEEDED` → `PROCEEDED`；`FAILED/CANCELLED/LOST` → `STOPPED`（`:387-396`）。
2. Ordinal 不匹配 → `INVALID`（`:378-385`）。
3. `observation is None` + deadline 未到 → `PENDING`；deadline 已到 → `INVALID`（`:364-375`）。
4. PTY harness：dependent action 发送前调用 helper + dependency gate（`:1199-1244`）。Non-proceeded 记录 `dependency_stopped` 且跳过发送。
5. Chain segment 级：`f14_real_cli_observation.py:_run_segment` 在 `chain.upstream_succeeded is False` 时返回 `not_run`（`:422-430`）。
6. Independent work 不短路：`_run_pty` 的 cleanup（EOF/signal）、`_run_scenario` 的 evidence 固化、`run-terminals.json` 写入、public evidence 收集均在 dependency stop 后继续执行。

### 14-PASS-F16-evidence-index-no-scenario-PASS

- **入口/函数**: `f14_real_cli_observation.py:main()` index construction
- **文件(行号)**: `workspace/tmp/f14_real_cli_observation.py:628-657`
- **验证结果**: **PASS**

**证据：**

- Index 字段：`target_commit`、`scenario_count`、`run_terminal_summary`、`dependency_gate`、`evidence_status`、`harness_invalid_count`、`rows`、`public_evidence`、`oracle_status`（`:630-656`）。
- 无 `scenario_success`、`success`、`passed`、`execution_outcome` 字段。
- `oracle_status` 固定为 `"pending_user_adjudication"`（`:655`）。
- `evidence_status` 仅基于 `harness_status == "invalid"` 判定（`:642-648`），不推导业务正确性。

### 15-PASS-F16-public-contract-schema-no-change

- **验证结果**: **PASS**

**证据：**

- `CompactAcceptedReplacementV4`、schema 5 未修改。
- `run_transition.py` zero diff。
- Durable DDL、EventLog payload 字段、lifecycle enum 未修改。
- Engine contract 未修改。
- CLI public command/options 未修改。
- `docs/cli_ci_scenarios.json`、`docs/cli_ci_oracles.json`、prompt 目录未修改。
- Formal scenario matrix predicate/expected behavior 未修改。

### 16-P2-run-input-material-block-duplicated-construction

- **入口/函数**: `run_input_material_block()`
- **文件(行号)**: `dayu/host/compact_material.py:1002-1048`
- **输入场景**: `accepted_tool_evidence is not None` 分支
- **实际分支**: 直接构造 `RunInputMaterialBlock(...)`（`:1012-1030`），字段与 `_run_input_material_block_from_canonical_text` 中的构造（`:934-960`）高度重复
- **预期行为**: 两分支复用同一 low-level block builder，仅 text/size/digest 差异化
- **实际行为**: `RunInputMaterialBlock` 构造字段在 `run_input_material_block`（21 个参数位置）和 `_run_input_material_block_from_canonical_text`（21 个参数位置）中各出现一次。若 `RunInputMaterialBlock` 增删字段，需同步修改两处
- **直接证据**: 对比 `:1012-1030`（accepted_tool_evidence 分支）与 `:934-960`（canonical builder），除 `text`/`size_units`/`content_digest` 三字段外其余 18 个字段完全一致的赋值
- **影响**: 维护风险 — future `RunInputMaterialBlock` 字段变更可能只在一条路径更新，导致另一路径行为异常；当前语义正确
- **建议改法和验证点**: accepted_tool_evidence 分支也可委托 `_run_input_material_block_from_canonical_text`，但需先将 raw text 包装为 `_CanonicalMaterialText(value=text)`（不调用 normalizer）。此改动需确认 `_CanonicalMaterialText` 的 contract 允许"已知 raw text 不经 normalizer 进入 wrapper"。若不希望 subvert canonical wrapper contract，至少应抽取 shared keyword-arg dict 或 shared factory 减少重复字段
- **修复风险**: 低（仅重构，不改语义）
- **严重程度**: 低（P2）

### 17-P3-test-whitespace-rejection-boundary-coverage-gap

- **入口/函数**: `CompactAcceptedReplacementV4` typed constructor / strict persisted parser
- **文件(行号)**: N/A（已有 owner boundary，非新增代码）
- **输入场景**: whitespace-only title/detail/text 的 accepted candidate 或 persisted payload
- **实际分支**: reject at typed accept/read boundary（`CompactAcceptedReplacementV4` 构造器 / strict parser）
- **预期行为**: Plan 要求 `test_whitespace_only_replacement_candidate_is_rejected_at_accept_boundary` 和 `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary` 测试存在
- **实际行为**: 此二测试未在本次 diff 中新增。实现 artifact 声明"accepted candidate / strict persisted parser 对 blank required text 的既有 owner contract未增加 projector skip、default或 renumber"，即既有边界已覆盖。但无显式 focused test 证明 projector fail-closed（不 skip、不 renumber）
- **直接证据**: `tests/host/test_compact_material.py` diff 仅含 `test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact`，不含 plan 中列出的 whitespace rejection 测试名
- **影响**: 低 — `normalized_material_text()` 已 raise `ValueError` on empty（`:850-851`），且 `_canonical_material_text` 委托该函数，形成纵深防御。但缺少显式 owner-level test
- **建议改法和验证点**: 建议补充至少一个 projector-level test：构造 `CompactCandidateV4` 其中 title 为 `"   "`，经 accept boundary 断言 reject；或构造 whitespace-only `CompactAcceptedReplacementV4`（若能绕过 typed constructor），断言 projector path fail closed
- **修复风险**: 低（仅补充测试）
- **严重程度**: 低（P3）

### 18-P3-temporary-harness-ordinal-offset-naming

- **入口/函数**: `_run_observation_roles()` in `prompt_observe_calibration.py`
- **文件(行号)**: `workspace/tmp/prompt_observe_calibration.py:862-866`
- **输入场景**: `required_success_accepted_ordinal` 语义为 upstream ordinal，但 `_run_observation_roles` 中 `+ 1` 转换为 dependent ordinal
- **实际分支**: `dependent_ordinals = {action.required_success_accepted_ordinal + 1 ...}`
- **预期行为**: 字段名与使用方式语义一致
- **实际行为**: 字段 `required_success_accepted_ordinal` 语义为"我依赖的 upstream Run 的 accepted ordinal"，但 `_run_observation_roles` 中 `+ 1` 将其转换为"我是 dependent Run 的 accepted ordinal"。代码行为正确（经 trace 验证），但字段名与转换逻辑之间的间接性容易导致未来维护者误读
- **直接证据**: `:863` 的 `action.required_success_accepted_ordinal + 1` 与 `:868-873` 的 `accepted_ordinal_offset + local_ordinal`比较，正确但间接
- **影响**: 低 — 仅在临时 harness 中，不影响 tracked helper contract
- **建议改法和验证点**: 考虑在 `_run_observation_roles` docstring 或行内注释中说明 `+ 1` 的语义转换；或引入 `upstream_ordinal` / `dependent_ordinal` 区分命名
- **修复风险**: 低（仅临时文件注释）
- **严重程度**: 低（P3）

## LLM-facing / schema / public contract / README / design boundaries 检查

- **LLM-facing**: 无 prompt、tool schema、compactor prompt/LLM schema 修改。✅
- **Schema**: `CompactAcceptedReplacementV4`、schema 5、durable DDL、EventLog payload 字段未修改。✅
- **Public contract**: Engine contract、CLI public command/options 未修改。✅
- **README**: `dayu/host/README.md` 更新了 previous-pair 全 section canonical projection 描述（`:772`）；`docs/host/design.md` 增加了 canonical projection owner contract（`:3526-3527`）；`docs/cli_ci.md` 重写了 process/per-Run/dependency/evidence 分离与 event-specific reason shape（`:1358-1430`）；`tests/README.md` 增加了 CLI CI helper test 入口（`:407`）。均与实现一致。✅
- **Design boundaries**: Engine 不拥有 accepted replacement 或 previous pair；Host 是唯一 projection owner；helper 只读不写 Host state。✅

## Loose parsing / getattr / fallback / 第二真源 检查

- 无 `hasattr`/`getattr` 新增。
- 无 `try/except` 吞并 validator 异常。
- F16 helper 的 `_terminal_reason` 不读取 `payload_json`、`host_runs.status`、日志文本或文件时间戳。
- Reason 唯一源：`reason_json.reason`。✅
- 无字符串逆向解析（packed block → typed anchor 方向不存在）。✅

## Tests owner contract 检查

- F15 tests：`test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 断言 packed/readable exact、reopen byte-exact、format matrix。✅
- F15 dispatch test：`test_durable_reopen_previous_pair_freezes_and_dispatches_next_ordinary_run` 经 scheduler → candidate freeze → worker accept 真实验证。✅
- F16 helper tests：参数化覆盖 reason shape、malformed JSON、duplicate terminal、event-specific extras、dependency gate、process separation。✅
- Producer tests：`test_dispatch_scheduler.py`、`test_active_cancel_dispatch.py`、`test_run_attempt_transitions.py`、`test_wait_cancel_late_result.py` 分别覆盖 succeeded/failed/cancelled/lost 的 exact `reason_json` object。✅
- 既有 strict mismatch/recovery tests 保留并通过。✅
- `workspace/tmp/` 脚本无 typed contract 真源要求，其关键决策由 tracked helper tests 覆盖。✅

## Open Questions

1. Plan 要求 `test_whitespace_only_replacement_candidate_is_rejected_at_accept_boundary` 与 `test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary` 作为显式 focused tests。当前实现依赖 `normalized_material_text()` 的 ValueError + `CompactAcceptedReplacementV4` typed constructor 的既有校验作为纵深防御，未增加 projector-level 显式 boundary test。若 Controller 认为既有边界已足够，可明确 defer；否则应在后续 gate 补充。
2. `_run_input_material_block_from_canonical_text` 的 21 个参数中，`source_labels`、`turn_group_id`、`already_represented`、`protected_recent_raw_turn`、`tool_result_event_ref`、`tool_call_event_ref`、`payload_refs`、`artifact_refs` 在 previous-block 路径中均为空/None/False。这是否暗示 previous-block builder（`_previous_block_from_canonical_text`）的抽象层次可以更低（不暴露这些与 previous context 无关的参数）？当前实现遵循 plan 的模块级私有辅助函数原则，但参数列表长度值得关注。

## Residual Risk

1. **Fresh production real rerun 未执行**：Plan 要求在 clean committed target 上执行真实 provider/AAPL rerun。当前 implementation gate 未 commit，因此 rerun 未启动。这是 plan 明确分配给 subsequent post-commit validation gate 的工作。Real evidence（28 个 Run → 8 个 `RUN_SUCCEEDED` 是否修复为全部 `RUN_SUCCEEDED`）尚未验证。
2. **Secret scan 未执行**：依赖 fresh rerun。
3. **Format matrix 仅覆盖 answer anchor**：`test_pre_dispatch_answer_anchor_format_matrix_keeps_packed_and_readable_exact` 的 candidate 覆盖所有五个 section，但 packed/readable exact 断言的显式验证集中在 answer anchor（`:2179-2191`）。Summary/fact/intent/reference 的 exact 文本通过 `reopened_readable.to_json() == readable.to_json()` 间接覆盖，但未逐 section 展开显式断言。
4. **`_previous_block_from_canonical_text` 的 `event_sub_index` 计算依赖 `len(blocks)` 在追加时的实时值**：这是确定性行为（`:2609`、`:2620`、`:2640`、`:2651`），但若未来重构改变了 blocks 的追加顺序，可能引入 label misalignment。当前正确。
5. **Temporary harness 的 `_run_observation_roles` 与 `_scenario` 之间的 ordinal offset 一致性**：由 `accepted_ordinal_offset` 统一驱动，但 harness 无 typed contract 强制校验 offset 与 `PtyAction.required_success_accepted_ordinal` 的一致性边界。这在临时脚本中可接受，tracked helper 不受影响。
