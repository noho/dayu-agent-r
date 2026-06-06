# WU-CM-01-F03 Plan Re-Review — AgentDS

## Verdict

**pass** — 所有 6 个 accepted findings 均已在 plan artifact 中修复。无新增 blocking issue。

---

## Re-review Summary

本轮只复核 controller adjudication 中 accepted 的 6 个 finding 是否在 `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md` 中修复。不重新发明方案，不提出替代设计。

复核方法：逐条对照 adjudication 要求的修复内容与 plan artifact 当前文本，必要时用 `rg` 验证代码现状与 plan 假设一致。

---

## Accepted Finding Verification

### AF-1: Dead `run_input.py` helper chain 直接删除

**Controller 要求**: 在 implementation plan 中明确最终 grep 确认后直接删除，不保留条件迁移措辞。

**Plan 当前表述**:
- Decision #4 (line 128): "implementation gate 需在最终 grep 确认后直接删除三者，不保留窄化迁移版本，也不留下条件迁移措辞。"
- Slice 3 (line 198): "在最终 `rg` 确认后删除 dead helper 链：`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event`。不得保留只读 `final_answer` 的迁移版本。"
- Risks (line 294): "implementation 只做最终 grep 确认后删除，不再保留迁移选项。"
- Search validation (line 233): `rg` 确认 dead helper 链无残留。

**代码验证**: `rg "_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu` 确认该链仅存在于 `dayu/host/run_input.py:3412-3556`，无 production caller，与 plan 假设一致。

**状态**: **fixed**

---

### AF-2: `STRICT_ALLOW_EMPTY` 移除与 durable/inline non-empty 策略显式化

**Controller 要求**: `STRICT_ALLOW_EMPTY` 移除原因和影响显式说明；durable 和 inline 路径统一使用 non-empty 语义；空白 `final_answer` 不阻止 terminal artifact lookup。

**Plan 当前表述**:
- Decision #1 (line 106): "`STRICT_ALLOW_EMPTY` 策略明确删除，不保留兼容 alias；空白 `final_answer` / terminal `content` 不是有效 assistant continuity。"
- Decision #1 (line 107): "durable memory hydration 与 run input inline delta hydration 均使用 non-empty 语义；空白 `final_answer` 应被视为缺失，并继续尝试读取 digest-checked terminal summary artifact `content`。"
- Decision #2 (line 118): "空白 `final_answer` 不得阻止 terminal artifact `content` hydration；若 artifact `content` 非空且 digest 校验通过，应使用 artifact `content` 作为 transient `final_answer`。"
- Slice 2 (line 177): "durable projection 原 `STRICT_ALLOW_EMPTY` 路径迁移为 non-empty 语义；空白 `final_answer` 必须继续尝试 terminal artifact `content`，不得 early return。"
- Search validation (line 233): `rg "STRICT_ALLOW_EMPTY"` 确认无残留。

**代码验证**: `rg "STRICT_ALLOW_EMPTY" dayu` 确认当前仅在 `terminal_summary_payload.py:26,85` 定义/使用，`durable/memory.py:233,254` 两处引用。Plan 覆盖全部引用点。

**状态**: **fixed**

---

### AF-3: RUN payload early-return guard 只检查 `final_answer`

**Controller 要求**: `_payload_with_assistant_final_answer()` 的 early-return guard 只检查 `final_answer`，不检查 `content`/`summary_text`/nested `summary`。

**Plan 当前表述**:
- Decision #2 (line 117): "`_payload_with_assistant_final_answer()` 的 early-return guard 只检查 RUN payload 的非空 `final_answer`；不得因为 RUN payload 中存在 `content`、`summary_text` 或 nested `summary` 而跳过 terminal artifact lookup。"

**分析**: 该规则直接对应 DS BF-2 和 MiMo Finding 1 的核心关注点。表述精确无歧义。

**状态**: **fixed**

---

### AF-4: `_selected_assistant_item` caller guard for `None`

**Controller 要求**: `_selected_assistant_item` 返回 `None` 时 caller 必须 guard，跳过 replacement。

**Plan 当前表述**:
- Decision #3 (line 122): "`_selected_assistant_item()` 改为返回 `SelectedRecentWindowItem | None`。"
- Decision #3 (line 123): "`project_conversation_memory_event()` 调用 `_selected_assistant_item()` 后必须显式 guard `None`；在 `RUN_SUCCEEDED` 且无 final answer continuity text 时跳过 `_replace_item_by_id(...)`，不替换 selected recent window。"

**代码验证**: `_replace_item_by_id` (memory.py:2131-2144) 不处理 `None` 输入（会因 `item.item_id` 引发 AttributeError），证实 caller guard 为必需。架构路径验证：`_selected_assistant_item` 通过 `MemoryProjectionEvent` 接收已由上游 `_payload_with_terminal_summary()` 解析的 payload，可使用 `assistant_final_answer_text_from_run_payload()` 读取已合并的 `final_answer`，无需 transaction。

**状态**: **fixed**

---

### AF-5: `test_terminal_summary_payload.py` 标记为新建

**Controller 要求**: plan 中标注该文件为新建测试文件。

**Plan 当前表述**:
- Slice 1 (line 149): "`tests/host/test_terminal_summary_payload.py`（新建测试文件）"

**文件验证**: `ls tests/host/test_terminal_summary_payload.py` 确认文件不存在。所有其他 referenced test files 均存在。

**状态**: **fixed**

---

### AF-6: Import-cycle fallback 具体化

**Controller 要求**: 静态无 cycle 证据或具体 fallback 模块名；禁止 callback indirection 和 duplicate field policy。

**Plan 当前表述**:
- Risks (line 295): "静态分析显示 `terminal_summary_payload.py` 当前是轻量 reader module，`payload_resolution.py` / durable transaction 依赖链未反向导入它，可先尝试把 transaction-aware resolver 放在 `terminal_summary_payload.py` 并用 import smoke 验证；若出现 import cycle，则把 `assistant_final_answer_continuity_text(...)` 移入 `dayu/host/_terminal_answer.py`，`terminal_summary_payload.py` 只保留两个纯 field reader。不得使用 callback indirection，也不得复制字段读取策略。"

**代码验证**:
- `terminal_summary_payload.py` 仅 import `dayu.host.durable.errors`，不依赖 `payload_resolution.py`。
- `payload_resolution.py` 不 import `terminal_summary_payload.py`。
- `terminal_summary_payload.py` 的 consumers（`durable/memory.py`, `compaction_evidence.py`, `memory.py`, `run_input.py`）均不被 `payload_resolution.py` 反向依赖。
- 静态分析结论与代码一致，无 cycle 风险。
- `dayu/host/_terminal_answer.py` 不存在，为 plan 指定的 contingency 模块。

**状态**: **fixed**

---

## New Findings

无 blocking finding。

### NF-R1: `_selected_assistant_item` 使用哪个新 helper 未显式指定

**严重性**: Low（可从代码上下文推断）

`_selected_assistant_item` (memory.py:1614) 没有 `HostTransaction` 参数，只能使用 `assistant_final_answer_text_from_run_payload(event.payload, text_policy=...)` 读取已由上游 `_payload_with_assistant_final_answer()` 合并的 `final_answer`。plan Decision #3 未显式写出用哪个 helper，但 implementation agent 可从代码上下文（无 transaction、payload 已解析）自然推出。

**建议**: 不影响 plan 正确性，implementation 时自然明确。

### NF-R2: `_selected_assistant_item` 的 `text_policy` 参数未在 plan 中指定

**严重性**: Low（原代码使用 `LENIENT_NON_EMPTY`，语义一致）

原代码 `_selected_assistant_item` 使用 `PayloadSummaryTextPolicy.LENIENT_NON_EMPTY`。新 helper `assistant_final_answer_text_from_run_payload` 接收 `text_policy` 参数。plan 未显式指定该调用点的 text_policy 取值，但 `LENIENT_NON_EMPTY` 语义（非法类型或空白→None）与该场景需求一致。implementation agent 可自行选择。

---

## Over-design / Under-design 检查

**Over-design**: 无。plan fix 未引入新 module、新 abstraction 或新 state。

**Under-design**: 无。所有 accepted findings 修复到位，NF-R1/NF-R2 为 implementation detail 级别，可在代码中自然解决。

---

## 与原始 Review 的 Cross-check

| 原 Review 关注点 | 修复后状态 |
|---|---|
| DS BF-1: dead code 措辞保守 | Decision #4 / Slice 3 / Risks 均改为直接删除，无条件措辞 |
| DS BF-2: text_policy 分歧未处理 | Decision #1/#2 + Slice 2 显式统一为 non-empty |
| DS NF-1: import cycle 推迟 | Risks 已补充静态分析结论 + 具体 fallback 模块 |
| DS NF-2: test 文件不存在 | Slice 1 标记为新建 |
| DS NF-3: text_policy 参数传递 | Decision #2 已覆盖（见 AF-3） |
| MiMo Finding 1: early-return 字段 | Decision #2 显式只检查 final_answer（见 AF-3） |
| MiMo Finding 3: caller guard | Decision #3 显式要求（见 AF-4） |

---

## Residual Risks / Open Questions

1. **旧 durable data 中的 `summary_text` 残留**: plan 按 fail-closed / 全新 schema 处理，风险可接受（与原始 review 一致）。
2. **`_ref_summary_text` 在 evidence path 仍在使用**（`_selected_evidence_item` line 1652, `_user_visible_text` line 2908）: 本 work unit 正确处理为 out-of-scope。函数不会变为 dead code。
3. **两个 `_payload_with_terminal_summary` 副本未合并**: `run_input.py` 和 `durable/memory.py` 各自保留副本，改名后逻辑相同。这是合理的模块边界保持，不引入新风险。
4. **NF-R1/NF-R2**: `_selected_assistant_item` 的 helper 选择和 text_policy 为 implementation detail，不影响 plan 正确性。

---

## Reviewed Files / Commands

```text
Read:
  docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md (full)
  docs/reviews/wu-cm-01-f03-plan-review-ds.md (full)
  docs/reviews/wu-cm-01-f03-plan-review-controller-adjudication.md (full)
  docs/reviews/wu-cm-01-f03-plan-fix-codex.md (full)
  dayu/host/terminal_summary_payload.py (L18-L94)
  dayu/host/memory.py (L948-L998, L1195-1254, L1614-1660, L2131-2144, L2895-L2920)
  dayu/host/durable/memory.py (L193-L260)
  dayu/host/run_input.py (L2983-L3060, L3412-L3565)
  dayu/host/compaction_evidence.py (L395-L430)
  dayu/host/payload_resolution.py (L11-L25)

Grep:
  rg "_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu
  rg "STRICT_ALLOW_EMPTY" dayu
  rg "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu
  rg "_payload_with_terminal_summary" dayu/host
  rg "from dayu\.host\." dayu/host/terminal_summary_payload.py
  rg "from dayu\.host\." dayu/host/payload_resolution.py
  rg "import.*terminal_summary_payload|from.*terminal_summary_payload" dayu/host
  rg "MemoryProjectionEvent\(" dayu/host
  rg "_selected_assistant_item" dayu/host/memory.py
  rg "_ref_summary_text" dayu/host/memory.py

Bash:
  ls tests/host/test_terminal_summary_payload.py (不存在)
  ls tests/host/test_memory_projection.py (存在)
  ls tests/host/test_run_input_builder.py (存在)
  ls tests/host/test_compaction_operation.py (存在)
  ls tests/host/test_compact_material.py (存在)
  ls dayu/host/_terminal_answer.py (不存在 — contingency 模块)
```

---

## Re-review Verdict Summary

| 维度 | 评价 |
|---|---|
| Accepted findings 修复 | 6/6 fixed |
| 新增 blocking finding | 0 |
| 新增 non-blocking finding | 2 (NF-R1, NF-R2 — implementation detail 级别) |
| 设计真源对齐 | 保持与原始 review 一致的全部对齐 |
| Over-design | 无 |
| Under-design | 无 |
| Plan 可实施性 | ready for implementation gate |
