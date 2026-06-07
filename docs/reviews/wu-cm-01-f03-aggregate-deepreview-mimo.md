# Aggregate Deep Review — WU-CM-01-F03 Assistant Final Answer Continuity Fidelity Closeout

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-cm-01-f04-closeout`
- Base: `main`
- Output file: `docs/reviews/wu-cm-01-f03-aggregate-deepreview-mimo.md`
- Included scope:
  - WU-CM-01-F03 implementation code: `terminal_summary_payload.py`, `_terminal_answer.py`, `run_input.py`, `durable/memory.py`, `memory.py`, `compaction_evidence.py`
  - WU-CM-01-F03 tests: `test_terminal_summary_payload.py`, `test_memory_projection.py`, `test_run_input_builder.py`, `test_compaction_operation.py`, `test_compact_material.py`
  - WU-CM-01-F03 plan: `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`
  - WU-CM-01-F03 review artifacts: `wu-cm-01-f03-code-review-mimo.md`, `wu-cm-01-f03-code-review-ds.md`, `wu-cm-01-f03-code-review-controller-adjudication.md`, `wu-cm-01-f03-implementation-codex.md`
  - Control doc: `docs/host/issues-implementation-control.md`
  - README: `dayu/host/README.md`
- Excluded scope: WU-CM-01-F04 closeout code (shares this branch, already completed, no F03 interaction risk identified)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Hard Constraint 验证

#### 1. LLM-facing Trace / Answer material 只接受 `final_answer` 或 digest-checked terminal summary artifact `content`

- `terminal_summary_payload.py:26-39` — `assistant_final_answer_text_from_run_payload` 只读 `_PAYLOAD_FIELD_FINAL_ANSWER`（即 `"final_answer"`），`_text_field` 不搜索 `content`、`summary_text` 或 nested `summary`。
- `terminal_summary_payload.py:42-55` — `terminal_summary_content_text_from_payload` 只读 `_PAYLOAD_FIELD_CONTENT`（即 `"content"`），且只在 digest-checked resolver 中被调用。
- `_terminal_answer.py:21-66` — `assistant_final_answer_continuity_text` 读取顺序固定为 `final_answer` → digest-checked terminal summary artifact `content`。第 32-33 行 docstring 明确："裸 `RUN_SUCCEEDED.content`、`summary_text` 或 nested `summary` 均不是 assistant final answer 来源"。
- `memory.py:1616-1630` — `_selected_assistant_item` 只调用 `assistant_final_answer_text_from_run_payload`（纯 field reader，只读 `final_answer`），缺失时返回 `None`，不 fallback 到 `_ref_summary_text`。
- `run_input.py:3005-3036` — `_payload_with_assistant_final_answer` 通过 `assistant_final_answer_continuity_text` 获取文本，合并进 transient payload 的 `final_answer` 字段（非 `content`）。
- `durable/memory.py:213-243` — 同上逻辑。
- `compaction_evidence.py:401-430` — `_assistant_history_materials` 通过 `assistant_final_answer_continuity_text` 获取文本，无时返回空 tuple。

直接测试证据：
- `test_run_payload_summary_fields_are_not_final_answer_sources`（`test_terminal_summary_payload.py:69`）— content/summary_text/nested summary 均不被读取。
- `test_terminal_summary_payload_summary_fields_are_not_content_sources`（`test_terminal_summary_payload.py:111`）— artifact 的 summary_text/nested summary 均不被读取。
- `test_run_succeeded_summary_only_does_not_materialize_assistant_window`（`test_memory_projection.py:323`）— summary-only 不生成 assistant window item。
- `test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded`（`test_compaction_operation.py:2157`）— summary-only 不生成 history material。
- `test_inline_delta_uses_terminal_content_and_ignores_summary_fallback`（`test_run_input_builder.py:1214`）— inline delta 只用 final_answer/terminal content，忽略 summary/ref。

#### 2. `summary_text` 和 nested `summary` 不作为 assistant final answer fallback

所有受影响文件 `rg summary_text` 结果：
- `run_input.py:150,2282,2284,3200,3217` — 均属于 session summary 渲染路径，非 assistant final answer。
- `memory.py:76,510,517,530,535,536,1138,1704,1716,2353,2368,2912` — 均属于 session summary memory、snapshot 序列化、或 evidence/user `_ref_summary_text` fallback，非 assistant final answer。
- `durable/memory.py:623,753,776` — 均属于 snapshot session summary 检查或序列化路径。
- `compaction_evidence.py` — 无 `summary_text` 残留。

`_ref_summary_text`（`memory.py:2915`）仅在 `_selected_evidence_item`（line 1656，TOOL_RESULT_ACCEPTED）和 `_user_visible_text`（line 2912，display_text fallback）中使用，不在 assistant final answer 路径中。

#### 3. `RUN_SUCCEEDED.content`、payload ref、digest、event id 不作为 assistant final answer fallback

- `_selected_assistant_item`（`memory.py:1616-1630`）缺失 final answer 时返回 `None`，不 fallback 到 `_ref_summary_text`。
- `project_conversation_memory_event`（`memory.py:1238-1240`）在 `_selected_assistant_item` 返回 `None` 时跳过 `_replace_item_by_id`，不注入 ref/digest/event_id 文本。
- 直接测试证据：`test_run_succeeded_payload_refs_do_not_materialize_assistant_window`（`test_memory_projection.py:349`）— 空 payload 加 ref/digest 不生成 assistant window。

#### 4. Session Summary Memory 只来自 accepted compact `session_summary`

- `_session_summary_from_accepted_event`（`memory.py:1690-1721`）untouched，只从 `accepted_candidate.session_summary.summary_text` 读取。
- 直接测试证据：`test_accepted_compact_materializes_vnext_memory_sections`（`test_memory_projection.py:291`）断言 session_summary_memory 来自 compact session_summary。
- `test_conversation_compact_input_vnext_does_not_map_session_summary_to_answer`（`test_compact_material.py:589`）验证 session_summary block 不进入 answer_material。

#### 5. 无 compatibility alias/wrapper/re-export

- `rg -n "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests` — 无匹配。
- `rg -n "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu tests` — 无匹配。
- `_terminal_answer.py` 不是旧接口 wrapper：旧 `assistant_summary_from_payload` 已删除，新模块从零建立。
- `_payload_with_assistant_final_answer` 在 `run_input.py` 和 `durable/memory.py` 中各有一份，分别适配 `EventLogRow` 和 `ProjectionEventView`，不是 compatibility re-export。

#### 6. README 只同步稳定实现

`dayu/host/README.md:296` 准确描述新语义：只接受 `final_answer` 和 digest-checked terminal summary `content`，不接受 `summary_text` / nested `summary` / ref / digest / event id。无过程状态、无未来设计、无旧术语残留。

### Import 边界验证

- `terminal_summary_payload.py` — 纯 field reader，无 transaction 依赖，无 import cycle 风险。
- `_terminal_answer.py` — transaction-aware resolver，import `durable.transaction` 和 `payload_resolution`。消费方均为 Host 内部模块：`run_input.py`、`durable/memory.py`、`compaction_evidence.py`、`tests/`。
- `run_input.py` — 已移除 `sqlite_payload_object` import（diff 确认），已移除 `_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST` 常量。
- `durable/memory.py` — 已移除 `sqlite_payload_object` import，已移除 `_optional_str` helper 和旧常量。

### 代码路径走读

#### `_payload_with_assistant_final_answer`（run_input.py:3005-3036 和 durable/memory.py:213-243）

两条实现逻辑一致：
1. 非 `RUN_SUCCEEDED` → 原样返回 payload。
2. `assistant_final_answer_text_from_run_payload` 读 `final_answer`（STRICT_NON_EMPTY）→ 非空则原样返回。
3. `assistant_final_answer_continuity_text` 读 `final_answer` + digest-checked terminal artifact `content` → 非空则合并进 transient `final_answer`。
4. 均为 `None` → 原样返回。

空白 `final_answer` 的处理正确：old code 使用 `STRICT_ALLOW_EMPTY`（空白 final_answer 视为有效，阻止 terminal artifact lookup），new code 使用 `STRICT_NON_EMPTY`（空白 final_answer 视为缺失，继续 terminal artifact lookup）。符合 plan 决策 #2。

#### `_selected_assistant_item`（memory.py:1616-1630）

只读 `final_answer`，缺失时返回 `None`。调用方 `project_conversation_memory_event`（line 1238-1240）显式 guard `None` 后跳过 `_replace_item_by_id`。生产路径 caller（`run_input.py:1211`、`durable/memory.py:174`）在调用前已通过 `_payload_with_assistant_final_answer` 完成 hydration。

#### `assistant_final_answer_continuity_text`（_terminal_answer.py:21-66）

1. 读 `final_answer` → 非空则返回。
2. 读 `terminal_summary_ref` / `terminal_summary_digest` → 任一缺失则返回 `None`。
3. 调用 `sqlite_payload_object(transaction, payload_ref, payload_digest, "terminal summary")` 校验 digest。
4. 从 artifact payload 读 `content` → 返回。

`_optional_descriptor_text`（line 69-87）对非字符串 descriptor 抛 `HostDurableError`，空白按缺失处理。这是正确的：空白 ref/digest 不应触发 artifact lookup。

#### `_assistant_history_materials`（compaction_evidence.py:401-430）

通过 `assistant_final_answer_continuity_text` 获取文本，无时返回空 tuple。只在读到文本时返回 `InitialHistoryMaterial(kind=ASSISTANT_FINAL_ANSWER)`。

### 测试覆盖矩阵

| Hard Constraint | 测试 | 文件:行 |
|---|---|---|
| final_answer 可读 | `test_run_payload_final_answer_is_read` | test_terminal_summary_payload.py:45 |
| 空白 final_answer = None | `test_blank_run_payload_final_answer_is_missing` | test_terminal_summary_payload.py:57 |
| content/summary_text/nested 不读 | `test_run_payload_summary_fields_are_not_final_answer_sources` | test_terminal_summary_payload.py:69 |
| artifact content 可读 | `test_terminal_summary_payload_content_is_read` | test_terminal_summary_payload.py:87 |
| 空白 artifact content = None | `test_blank_terminal_summary_content_is_missing` | test_terminal_summary_payload.py:99 |
| artifact summary_text/nested 不读 | `test_terminal_summary_payload_summary_fields_are_not_content_sources` | test_terminal_summary_payload.py:111 |
| strict/lenient 策略 | `test_allowed_non_string_field_strict_raises_and_lenient_returns_none` | test_terminal_summary_payload.py:128 |
| disallowed 字段不触发 strict | `test_disallowed_summary_text_type_does_not_trigger_strict_error` | test_terminal_summary_payload.py:159 |
| digest-checked resolver 端到端 | `test_continuity_resolver_reads_digest_checked_terminal_content` | test_terminal_summary_payload.py:178 |
| summary-only = 无 assistant window | `test_run_succeeded_summary_only_does_not_materialize_assistant_window` | test_memory_projection.py:323 |
| ref/digest 不泄漏 | `test_run_succeeded_payload_refs_do_not_materialize_assistant_window` | test_memory_projection.py:349 |
| durable hydration terminal content | `test_projection_consumer_hydrates_terminal_content_as_final_answer` | test_memory_projection.py:367 |
| inline delta 用 terminal content | `test_inline_delta_uses_terminal_content_and_ignores_summary_fallback` | test_run_input_builder.py:1214 |
| compaction 用 terminal content | `test_compaction_request_evidence_inputs_collect_terminal_content` | test_compaction_operation.py:2091 |
| summary-only = 空 history material | `test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded` | test_compaction_operation.py:2157 |
| session_summary 不进 answer_material | `test_conversation_compact_input_vnext_does_not_map_session_summary_to_answer` | test_compact_material.py:589 |

### Controller Validation Baseline

- focused pytest → 197 passed ✓
- full pyright → 0 errors ✓
- `rg assistant_summary_from_payload|PayloadSummaryTextPolicy` → no matches ✓
- `rg STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event` → no matches ✓
- `rg summary_text` in affected files → 仅属于 accepted compact session_summary / snapshot 序列化 / evidence fallback ✓

### Adversarial Failure Pass

**Source fallback regression**：已验证。所有 assistant final answer 路径只读 `final_answer` 或 digest-checked artifact `content`。`summary_text`、nested `summary`、`content`（裸 RUN payload）、ref、digest、event id 均不是 fallback source。197 个测试覆盖正向和负向场景。

**Import boundary**：已验证。`terminal_summary_payload.py` 是纯 field reader（无 transaction 依赖），`_terminal_answer.py` 是 transaction-aware resolver（隔离 import cycle）。无反向 import，无 Host 外部 import。`run_input.py` 和 `durable/memory.py` 已移除旧 `sqlite_payload_object` import。

**Direct projection hydration 假设**：已验证。生产路径 caller（`run_input.py:1211`、`durable/memory.py:174`）在调用 `project_conversation_memory_event` 前通过 `_payload_with_assistant_final_answer` 完成 hydration。`_selected_assistant_item` 读取的 payload 已包含 hydrated `final_answer`。非 hydration caller 目前不存在（DS residual risk note 确认）。

**Durable projection `STRICT_ALLOW_EMPTY` → `STRICT_NON_EMPTY` 迁移**：已验证。old code 的 `STRICT_ALLOW_EMPTY` 使空白 `final_answer` 被视为有效，阻止 terminal artifact lookup。new code 的 `STRICT_NON_EMPTY` 使空白 `final_answer` 视为缺失，继续 terminal artifact lookup。符合 plan 决策 #2："空白 `final_answer` 不得阻止 terminal artifact `content` hydration"。

**Dead code 删除完整性**：已验证。`_continuity_message_from_event`、`_successful_run_continuity_messages`、`_successful_run_message_pair` 已从 `run_input.py` 物理删除。grep 无残留。`_optional_str` helper 已从 `durable/memory.py` 删除（不再需要 terminal summary descriptor 读取）。旧常量 `_PAYLOAD_FIELD_CONTENT`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF`、`_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST` 已从 `run_input.py` 和 `durable/memory.py` 删除。

**Tests 证明真实行为**：已验证。测试覆盖 final_answer 读取、空白处理、summary/ref 不泄漏、digest-checked resolver、durable hydration、inline delta、compaction material、session summary 隔离。测试不依赖旧 helper 或旧 enum。

## Open Questions

无。

## Residual Risk

- `_selected_assistant_item`（`memory.py:1616-1630`）只读 inline `final_answer`，不通过 `assistant_final_answer_continuity_text` 解析 terminal artifact content。这是因为该路径无 `HostTransaction` 引用。生产路径 caller 在调用前已通过 `_payload_with_assistant_final_answer` 完成 hydration，故此限制不在生产路径触发。若未来出现新的非 hydration caller，需确保其也执行 prior hydration 或迁移为 transaction-aware 路径。风险低。
- `_payload_with_assistant_final_answer` 在 `run_input.py` 和 `durable/memory.py` 中存在两份近似实现，分别适配 `EventLogRow` 和 `ProjectionEventView`。当前差异仅在一行 payload 提取方式，属轻量重复。若未来该逻辑继续增长，应考虑提取共享 helper。风险低。
- `_text_field`（`terminal_summary_payload.py:58-82`）的 error message 不区分调用来源（`final_answer` vs `content`）。当前调用链正确，风险极低。
- `test_terminal_summary_payload.py` 未单独测试 `_optional_descriptor_text` 对非字符串 descriptor 字段的 strict error 路径。该路径由 `_terminal_answer.py:83-84` 覆盖，通过 `sqlite_payload_object` 间接验证。风险低。

## Verdict

**pass** — 0 blocking findings，0 non-blocking findings。实现忠实执行 plan 全部 5 项决策与 5 个 slice。6 项 hard constraint 全部通过直接代码证据和测试验证。adversarial failure pass 未发现 source fallback regression、import boundary violation 或 hydration 假设失效。197 个测试通过，pyright 0 errors，旧 helper/enum/dead chain 无残留，README 对齐当前实现。
