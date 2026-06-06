# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-cm-01-f04-closeout`
- Base: `main` (workspace diff)
- Output file: `docs/reviews/wu-cm-01-f03-code-review-mimo.md`
- Included scope:
  - `dayu/host/terminal_summary_payload.py`
  - `dayu/host/_terminal_answer.py`
  - `dayu/host/run_input.py`
  - `dayu/host/durable/memory.py`
  - `dayu/host/memory.py`
  - `dayu/host/compaction_evidence.py`
  - `dayu/host/README.md`
  - `tests/host/test_terminal_summary_payload.py`
  - `tests/host/test_memory_projection.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_compact_material.py`
  - `docs/reviews/wu-cm-01-f03-implementation-codex.md`
- Excluded scope: `docs/host/issues-implementation-control.md` (controller metadata, not implementation)
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 审查记录

以下按用户硬约束逐项记录审查结论：

**1. `summary_text` / `content` / nested `summary` / ref / digest / event id 是否仍可能被当作 assistant final answer continuity**

- `terminal_summary_payload.py:26-38` — `assistant_final_answer_text_from_run_payload` 只读 `_PAYLOAD_FIELD_FINAL_ANSWER`（即 `"final_answer"`），不读 `content`、`summary_text` 或 nested `summary`。
- `terminal_summary_payload.py:42-55` — `terminal_summary_content_text_from_payload` 只读 `_PAYLOAD_FIELD_CONTENT`，且只在 `_terminal_answer.py` 的 digest-checked resolver 中被调用。
- `_terminal_answer.py:21-66` — `assistant_final_answer_continuity_text` 的读取顺序固定为 `final_answer` → digest-checked terminal summary artifact `content`。裸 `RUN_SUCCEEDED.content`、`summary_text`、nested `summary` 均不是来源。
- `memory.py:1616-1630` — `_selected_assistant_item` 使用 `assistant_final_answer_text_from_run_payload`（只读 `final_answer`），缺失时返回 `None`，不再 fallback 到 `_ref_summary_text`。
- 直接证据：`test_run_payload_summary_fields_are_not_final_source`（`test_terminal_summary_payload.py:69-84`）、`test_terminal_summary_payload_summary_fields_are_not_content_sources`（`test_terminal_summary_payload.py:111-125`）、`test_run_succeeded_summary_only_does_not_materialize_assistant_window`（`test_memory_projection.py:386-409`）、`test_compaction_request_evidence_inputs_ignore_summary_only_run_succeeded`（`test_compaction_operation.py:2143-2180`）。

**2. terminal artifact `content` 是否只在 digest-checked resolver 后进入 transient `final_answer`**

- `_terminal_answer.py:49-66` — 只在 `final_answer` 缺失时，读取 `terminal_summary_ref` / `terminal_summary_digest`，调用 `sqlite_payload_object`（含 digest 校验），再从 artifact payload 读取 `content`。
- `run_input.py:3027-3035` — `_payload_with_assistant_final_answer` 调用 `assistant_final_answer_continuity_text` 获取 digest-checked content，合并进 transient payload 的 `final_answer` 字段（非 `content`）。
- `durable/memory.py:234-243` — 同上，durable projection 也合并进 `final_answer`。
- 直接证据：`test_continuity_resolver_reads_digest_checked_terminal_content`（`test_terminal_summary_payload.py:178-216`）、`test_projection_consumer_hydrates_terminal_content_as_final_answer`（`test_memory_projection.py:367-405`）、`test_inline_delta_uses_terminal_content_and_ignores_summary_fallback`（`test_run_input_builder.py:1214-1310`）。

**3. Session Summary Memory 是否仍只来自 accepted compact session_summary**

- 本次变更未触及 `session_summary` 路径。`compact_material.py:1490-1497` 的 `_snapshot_summary_text` 仍只读 `snapshot.session_summary_memory.summary_text`。
- `compaction_operation.py:1248` 仍读 `candidate.session_summary.summary_text`。
- 直接证据：`test_conversation_compact_input_vnext_does_not_map_session_summary_to_answer`（`test_compact_material.py:391-441`）验证 session summary block 不进入 answer_material。

**4. `_terminal_answer.py` 是否为合理依赖边界**

- `_terminal_answer.py` 存在的原因是 `terminal_summary_payload.py` 无法 import `HostTransaction`（会导致 import cycle）。该模块把 transaction-aware 的 digest-checked resolver 隔离出来，`terminal_summary_payload.py` 保持为纯字段 reader。
- 不是兼容 seam：没有保留旧 API 转发；不是过度设计：只有一个 public function，职责单一。
- `__all__` 只导出 `assistant_final_answer_continuity_text`，符合内部模块定位。

**5. tests 是否覆盖用户硬约束和 regression**

- `test_terminal_summary_payload.py`：覆盖 `final_answer` 读取、空白处理、`summary_text`/`content`/nested `summary` 不被读取、strict/lenient 策略、digest-checked resolver。
- `test_memory_projection.py`：覆盖 summary-only 不生成 assistant window、ref-only 不生成 assistant window、durable projection hydrate terminal content。
- `test_run_input_builder.py`：覆盖 inline delta 只用 final_answer / terminal content，忽略 summary fallback。
- `test_compaction_operation.py`：覆盖 terminal content 进入 history material、summary-only 不生成 answer material。
- `test_compact_material.py`：覆盖 session summary 不映射为 answer material。
- 旧 helper 链（`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event`）已完全删除，grep 确认无残留。

**6. README 是否只同步稳定实现**

- `dayu/host/README.md:296` 准确描述了新语义：只接受 `final_answer` 和 digest-checked terminal summary `content`，不接受 `summary_text` / nested `summary` / ref / digest / event id。
- 无过程状态、无未来设计、无旧术语残留。

## Open Questions

无。

## Residual Risk

- `_text_field`（`terminal_summary_payload.py:58-82`）的 error message 不区分调用来源（`final_answer` vs `content`），若未来有人误用不同 payload 类型调用错误函数，error message 会模糊。当前调用链正确，风险极低。
- `test_terminal_summary_payload.py` 未单独测试 `_optional_descriptor_text` 对非字符串 descriptor 字段的 strict error 路径。该路径由 `_terminal_answer.py:83-84` 覆盖，但仅通过 `sqlite_payload_object` 的间接调用验证。风险低。
