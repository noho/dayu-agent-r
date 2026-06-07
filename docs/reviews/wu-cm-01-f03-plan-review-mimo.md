# WU-CM-01-F03 Plan Review — AgentMiMo

## Verdict

**pass-with-findings**

Plan is code-generation-ready with minor gaps. No blocking findings that require returning to design; all findings can be resolved at implementation time with explicit decisions.

## Blocking Findings

无。

## Non-blocking Findings

### Finding 1: `_payload_with_terminal_summary` 早返逻辑语义变化未显式说明

**严重性**: medium

**证据**:

- `run_input.py:3021`-`3028` 当前早返逻辑：`assistant_summary_from_payload(payload, STRICT_NON_EMPTY)` 检查 `final_answer`、`content`、`summary_text` 三个字段，任一非空即跳过 terminal artifact 读取。
- `durable/memory.py:231`-`237` 同样逻辑但用 `STRICT_ALLOW_EMPTY`。
- Plan Decision 2 说"当 helper 从 terminal artifact 读到 `content` 时，合并到 transient projection payload 的 `final_answer` 字段"，但没有显式说明早返 guard 应改为只检查 `final_answer`。
- 当前 `RUN_SUCCEEDED` canonical payload（`run_transition.py:4227`-`4235`）不内联 `final_answer`，只存 `terminal_summary_ref` / `terminal_summary_digest`，所以实践中两个 guard 都会 fall through 到 terminal artifact 读取。但若未来有人在 payload 中加 `content` 字段，旧代码会跳过 terminal artifact，新代码不会。

**影响**: 行为差异在当前 canonical payload 下不可触发，但若不显式说明，implementation agent 可能保留旧的多字段早返逻辑。

**建议改法**: 在 Decision 2 中显式说明早返 guard 只检查 `final_answer` 字段，不检查 `content` 或 `summary_text`。`durable/memory.py` 的 `_payload_with_terminal_summary` 同理。

**验证点**: 实现后 `rg -n "assistant_summary_from_payload|summary_text" dayu/host/run_input.py dayu/host/durable/memory.py` 应无残留。

**建议裁决**: non-blocking，implementation 时显式处理。

---

### Finding 2: `STRICT_ALLOW_EMPTY` 策略移除未显式讨论

**严重性**: medium

**证据**:

- `durable/memory.py:233` 使用 `PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY` 检查 RUN payload 是否已有文本。
- `durable/memory.py:254` 使用同一策略检查 terminal artifact。
- Plan Decision 1 说新 `PayloadTextReadPolicy` 只保留 `STRICT_NON_EMPTY` 与 `LENIENT_NON_EMPTY`，`STRICT_ALLOW_EMPTY` 被静默移除。
- `STRICT_ALLOW_EMPTY` 的语义是"空字符串也算有效摘要"；移除后，空字符串 `final_answer` 在 strict 下会被当作非法类型抛错，在 lenient 下返回 `None`。

**影响**: 当前 `engine_ingest.py:4282` 已过滤空 `data.content`，所以 terminal artifact `content` 不会是空字符串。但 `RUN_SUCCEEDED` payload 中若存在空 `final_answer`（hypothetical），strict 策略会抛错而非返回空字符串。

**建议改法**: 在 Decision 1 中显式说明 `STRICT_ALLOW_EMPTY` 被移除的理由（Engine 已过滤空 content，空 final answer 不应作为有效 continuity），并确认 `durable/memory.py` 的两个调用点迁移为 `STRICT_NON_EMPTY`。

**验证点**: 实现后 `rg -n "STRICT_ALLOW_EMPTY" dayu/host` 应无残留。

**建议裁决**: non-blocking，implementation 时显式迁移。

---

### Finding 3: `_selected_assistant_item` 返回 `None` 后调用方处理未展开

**严重性**: low

**证据**:

- `memory.py:1241` 当前调用 `_selected_assistant_item(event)` 并直接传入 `_replace_item_by_id`。
- Plan Decision 3 说改为返回 `SelectedRecentWindowItem | None`，但未说明 `_replace_item_by_id(selected, None)` 的行为。
- 需要确认 `_replace_item_by_id` 是否接受 `None`（若不接受，需要在调用方加 `if item is not None` guard）。

**影响**: 若 `_replace_item_by_id` 不接受 `None`，实现时会遇到类型错误。

**建议改法**: 在 Decision 3 中补充：调用方需加 `None` guard，`None` 时跳过 `_replace_item_by_id` 调用。

**验证点**: pyright 通过即可。

**建议裁决**: non-blocking，pyright 会捕获。

---

### Finding 4: `_continuity_message_from_event` 和 `_successful_run_continuity_messages` 的处理策略应前置决策

**严重性**: low

**证据**:

- `grep` 确认 `_successful_run_continuity_messages`（`run_input.py:3513`）无任何调用方，是 dead code。
- `_continuity_message_from_event`（`run_input.py:3412`）只被 `_successful_run_message_pair`（`run_input.py:3556`）调用，而 `_successful_run_message_pair` 只被 `_successful_run_continuity_messages` 调用。
- 整条调用链都是 dead code。
- Plan Slice 3 说"若 `_continuity_message_from_event()` 仍有生产调用，迁移为只读 `final_answer`；无生产调用则删除连带 dead helper"。

**影响**: 无功能影响，但 implementation agent 需要额外 `rg` 验证。

**建议改法**: 在 Decision 4 中明确：`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event` 均为 dead code，implementation 直接删除，不需要迁移。

**验证点**: 删除后 `rg -n "_continuity_message_from_event|_successful_run_message_pair|_successful_run_continuity_messages" dayu/host` 应无残留。

**建议裁决**: non-blocking，implementation 时直接删除。

---

### Finding 5: 测试文件名可能不存在

**严重性**: low

**证据**:

- Plan Slice 2 引用 `tests/host/test_memory_projection.py`，Slice 3 引用 `tests/host/test_run_input_builder.py`。
- 这些可能是假设文件名。Plan 已注明"or existing equivalent focused test file"。

**影响**: implementation agent 需要确认实际测试文件名。

**建议改法**: 无需修改 plan，implementation agent 按实际情况创建或定位测试文件。

**验证点**: 测试通过即可。

**建议裁决**: non-blocking。

---

### Finding 6: import cycle 风险缺少具体 fallback 路径

**严重性**: low

**证据**:

- Plan Risks 提到 `terminal_summary_payload.py` 若引入 `HostTransaction` / `sqlite_payload_object` 出现 import cycle，应停止并把高阶 resolver 放入新的 Host-internal helper module。
- 当前 `terminal_summary_payload.py` 只依赖 `dayu.contracts.json_value` 和 `dayu.host.durable.errors`，不依赖 `HostTransaction`。
- 新 helper `assistant_final_answer_continuity_text(transaction, ...)` 需要 `HostTransaction` 来解析 terminal artifact，这会引入对 `dayu.host.durable` 的依赖。

**影响**: `terminal_summary_payload.py` 当前是 leaf module，引入 `HostTransaction` 可能 create cycle（取决于 `dayu.host.durable` 是否反向依赖 `terminal_summary_payload`）。

**建议改法**: Plan 已有正确方向（放入新的 Host-internal helper module）。建议在 Decision 1 中补充：若 import cycle 发生，`assistant_final_answer_continuity_text` 放入 `dayu/host/_terminal_answer.py` 或类似 Host-internal module，`terminal_summary_payload.py` 只保留两个纯函数 reader。

**验证点**: `python -c "from dayu.host.terminal_summary_payload import assistant_final_answer_continuity_text"` 不报 ImportError。

**建议裁决**: non-blocking，implementation 时验证。

## Over-design / Under-design Check

**Over-design**: 无。Plan 只拆分一个混合语义 helper，不新增 memory category、state machine 或 schema。三个新 helper 的职责边界清晰：两个 field-specific reader + 一个 composite orchestrator。

**Under-design**: 无明显不足。Plan 覆盖了所有 6 个调用点（`terminal_summary_payload.py`、`run_input.py` × 2、`durable/memory.py`、`memory.py`、`compaction_evidence.py`），并明确了 Session Summary Memory 不改源。

## Design Source Alignment

- `design.md:2915` — `trace_material` / `answer_material` 语义：Plan 正确对齐，只允许 final answer / terminal content 进入 assistant continuity。
- `design.md:3026` — Trace Memory 来源：Plan 正确对齐，`RUN_SUCCEEDED.final_answer` 是唯一 assistant 来源。
- `design.md:3030` — Session Summary 只来自 accepted compact：Plan Decision 6 正确保持不变。
- `design.md:3040`-`3042` — compact 前 / 后 producer 不同：Plan 正确不互相 fallback。
- `design.md:3196` — `answer_material` 不作为 evidence-backed fact source：Plan Non-goals 正确排除。
- `engine_ingest.py:4301`-`4306` — terminal summary `content` 来源：Plan 正确引用，`data.content` 写入 terminal artifact `content` 字段。

## Residual Risks / Open Questions

1. **现有 durable data 兼容性**: Plan Risks 已明确按 fail-closed 处理，不做旧库兼容读取。正确。
2. **`_ref_summary_text` 在 `_selected_evidence_item` 中的使用**: Plan scope 正确限于 assistant final answer，evidence item 的 ref fallback 不在本次范围内。
3. **`compact_material.py` 无需改动**: Plan Decision 5 正确确认 `ASSISTANT_FINAL_ANSWER` block 到 `answer_material` 的映射已正确。

## Reviewed Files / Commands

读取：
- `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`
- `docs/host/design.md`（lines 2900-3060, 3180-3220）
- `dayu/host/terminal_summary_payload.py`
- `dayu/host/run_input.py`（lines 2990-3060, 3415-3565）
- `dayu/host/durable/memory.py`（lines 205-265）
- `dayu/host/memory.py`（lines 1600-1720）
- `dayu/host/compaction_evidence.py`（lines 390-430）
- `dayu/host/engine_ingest.py`（lines 4265-4315）
- `dayu/host/durable/run_transition.py`（lines 4195-4245）

验证命令：
- `grep -rn "assistant_summary_from_payload" dayu/host` — 6 个调用点确认。
- `grep -rn "STRICT_ALLOW_EMPTY" dayu/host` — 2 个调用点确认。
- `grep -rn "_continuity_message_from_event\|_successful_run_message_pair\|_successful_run_continuity_messages" dayu/host` — dead code 确认。
- `grep -rn "_ref_summary_text" dayu/host/memory.py` — 3 个调用点确认。
