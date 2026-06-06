# WU-CM-01-F03 Plan Re-Review — AgentMiMo

## Verdict

**pass**

所有 accepted findings 均已在 plan artifact 中修复；无新增 blocking issue。

## Reviewed Target and Scope

- Work unit: WU-CM-01-F03 Assistant final answer continuity fidelity closeout
- Gate: plan re-review
- Plan artifact: `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md`
- Controller adjudication: `docs/reviews/wu-cm-01-f03-plan-review-controller-adjudication.md`
- Plan fix artifact: `docs/reviews/wu-cm-01-f03-plan-fix-codex.md`
- 原 review artifacts: `docs/reviews/wu-cm-01-f03-plan-review-mimo.md`, `docs/reviews/wu-cm-01-f03-plan-review-ds.md`

## Accepted Finding Verification

### Finding 1: Dead `run_input.py` helper chain 直接删除

**要求**: `_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event` 在最终 grep 确认后直接删除；不得保留条件迁移措辞。

**Plan 当前表述**:

- Decision 4（plan line 128）: "review 阶段直接 grep 已确认 `_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event` 整条链无 production caller；implementation gate 需在最终 grep 确认后直接删除三者，不保留窄化迁移版本，也不留下条件迁移措辞。"
- Slice 3（plan line 198）: "在最终 `rg` 确认后删除 dead helper 链：`_successful_run_continuity_messages`、`_successful_run_message_pair`、`_continuity_message_from_event`。不得保留只读 `final_answer` 的迁移版本。"
- Risks（plan line 294）: "run_input.py 中历史 successful run pair helper 链已由 review grep 判定为 dead code；implementation 只做最终 grep 确认后删除，不再保留迁移选项。"
- Slice 5 search validation（plan line 233）: `rg` 命令包含 `_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event`。

**Code evidence**: grep 确认 `run_input.py` 中三个函数（lines 3412, 3513, 3543）仍存在但无 production caller，与 plan 判定一致。

**Status**: **fixed**

---

### Finding 2: `STRICT_ALLOW_EMPTY` removal 与 durable/inline non-empty policy

**要求**: `STRICT_ALLOW_EMPTY` 明确移除；durable 和 inline 路径均使用 non-empty 语义；空白 `final_answer` 不得阻止 terminal artifact `content` hydration。

**Plan 当前表述**:

- Decision 1（plan lines 106-107）: "`STRICT_ALLOW_EMPTY` 策略明确删除，不保留兼容 alias；空白 `final_answer` / terminal `content` 不是有效 assistant continuity。durable memory hydration 与 run input inline delta hydration 均使用 non-empty 语义；空白 `final_answer` 应被视为缺失，并继续尝试读取 digest-checked terminal summary artifact `content`。"
- Decision 2（plan lines 117-118）: "空白 `final_answer` 不得阻止 terminal artifact `content` hydration；若 artifact `content` 非空且 digest 校验通过，应使用 artifact `content` 作为 transient `final_answer`。"
- Slice 2（plan line 177）: "durable projection 原 `STRICT_ALLOW_EMPTY` 路径迁移为 non-empty 语义；空白 `final_answer` 必须继续尝试 terminal artifact `content`，不得 early return。"
- Slice 1 tests（plan line 158）: "run payload 空白 `final_answer` 返回 `None`，不算有效 continuity。"
- Slice 1 tests（plan line 161）: "terminal artifact payload 空白 `content` 返回 `None`，不算有效 continuity。"
- Slice 5 search validation（plan line 233）: `rg` 命令包含 `STRICT_ALLOW_EMPTY`。

**Code evidence**: 当前 `terminal_summary_payload.py:26` 仍定义 `STRICT_ALLOW_EMPTY`，`durable/memory.py:233,254` 仍使用它，与 plan 判定需要移除一致。

**Status**: **fixed**

---

### Finding 3: RUN payload early-return guard 只检查 `final_answer`

**要求**: `_payload_with_terminal_summary`（改名为 `_payload_with_assistant_final_answer`）的 early-return guard 只检查 RUN payload 的非空 `final_answer`，不得因 `content`、`summary_text` 或 nested `summary` 存在而跳过 terminal artifact lookup。

**Plan 当前表述**:

- Decision 2（plan line 117）: "`_payload_with_assistant_final_answer()` 的 early-return guard 只检查 RUN payload 的非空 `final_answer`；不得因为 RUN payload 中存在 `content`、`summary_text` 或 nested `summary` 而跳过 terminal artifact lookup。"
- Decision 2（plan line 116）: "`_payload_with_terminal_summary()` 应改名为 `_payload_with_assistant_final_answer()` 或等价语义名。"

**Code evidence**: 当前 `run_input.py:3007-3051` 的 `_payload_with_terminal_summary()` 使用 `assistant_summary_from_payload(payload, STRICT_NON_EMPTY)` 检查 `final_answer`、`content`、`summary_text` 三个字段。Plan 正确收窄为只检查 `final_answer`。

**Status**: **fixed**

---

### Finding 4: `_selected_assistant_item` caller guard for `None`

**要求**: `_selected_assistant_item()` 返回类型改为 `SelectedRecentWindowItem | None`；调用方在 `RUN_SUCCEEDED` 且无 final answer continuity text 时必须显式 guard `None` 并跳过 `_replace_item_by_id(...)`。

**Plan 当前表述**:

- Decision 3（plan lines 122-123）: "`_selected_assistant_item()` 改为返回 `SelectedRecentWindowItem | None`。`project_conversation_memory_event()` 调用 `_selected_assistant_item()` 后必须显式 guard `None`；在 `RUN_SUCCEEDED` 且无 final answer continuity text 时跳过 `_replace_item_by_id(...)`，不替换 selected recent window。"

**Code evidence**: 当前 `memory.py:1614` 返回类型为 `SelectedRecentWindowItem`（非 Optional），`memory.py:1241` 调用 `_replace_item_by_id(selected, _selected_assistant_item(event))` 无 `None` guard。Plan 正确要求两处修改。

**Status**: **fixed**

---

### Finding 5: `tests/host/test_terminal_summary_payload.py` 标记为新建

**要求**: Plan 应明确该文件为新建测试文件。

**Plan 当前表述**:

- Slice 1 allowed files（plan line 149）: "`tests/host/test_terminal_summary_payload.py`（新建测试文件）"

**Evidence**: `ls` 确认该文件不存在，与 plan 标注"新建"一致。`test_memory_projection.py` 已存在，无需标注新建。

**Status**: **fixed**

---

### Finding 6: Import-cycle fallback 有具体模块/方向，禁止 callback indirection / duplicate field policy

**要求**: Plan 应给出具体 fallback module 名称和依赖方向；禁止 callback indirection 和 duplicate field policy。

**Plan 当前表述**:

- Risks（plan lines 295-296）: "import-cycle 处理采用明确 fallback：静态分析显示 `terminal_summary_payload.py` 当前是轻量 reader module，`payload_resolution.py` / durable transaction 依赖链未反向导入它，可先尝试把 transaction-aware resolver 放在 `terminal_summary_payload.py` 并用 import smoke 验证；若出现 import cycle，则把 `assistant_final_answer_continuity_text(...)` 移入 `dayu/host/_terminal_answer.py`，`terminal_summary_payload.py` 只保留两个纯 field reader。不得使用 callback indirection，也不得复制字段读取策略。"

**Code evidence**: 当前 `terminal_summary_payload.py` 只依赖 `dayu.contracts.json_value` 和 `dayu.host.durable.errors`（leaf module）。Plan 给出了具体 fallback module `dayu/host/_terminal_answer.py` 和依赖方向（transaction-aware resolver 与 pure field reader 分离），并明确禁止 callback indirection 和 duplicate field policy。

**Status**: **fixed**

---

## New Findings

无新增 blocking issue。

无新增 non-blocking finding。Plan artifact 经 fix 后的表述具体且 self-contained，implementation agent 可直接执行。

## Residual Risks

1. **旧 test fixture 迁移**: Plan Risks（line 296）提到旧 fixture 可能把 `display_text`/`content`/`summary_text` 当作 assistant 文本，implementation 需迁移。这是 implementation gate 的正常工作量，非 plan 层面问题。
2. **现有 durable data 兼容性**: Plan Risks（line 297）明确 fail-closed 处理，不做旧库兼容读取。风险可接受。
3. **`_ref_summary_text` evidence path**: DS review 指出 `_selected_evidence_item` 对 `TOOL_RESULT_ACCEPTED` 仍使用 `_ref_summary_text` fallback，不在本 WU 范围内。正确。
4. **Import smoke 验证**: Implementation 需在 `terminal_summary_payload.py` 中验证 transaction-aware resolver 不引入 cycle；若有 cycle 则按 plan fallback 执行。

以上 residual risks 均已在 plan 中有明确处理方向或 scope 边界，不构成 blocking issue。

## Reviewed Files / Commands

Read:
- `docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md` (full)
- `docs/reviews/wu-cm-01-f03-plan-review-mimo.md` (full)
- `docs/reviews/wu-cm-01-f03-plan-review-ds.md` (full)
- `docs/reviews/wu-cm-01-f03-plan-review-controller-adjudication.md` (full)
- `docs/reviews/wu-cm-01-f03-plan-fix-codex.md` (full)
- `docs/host/issues-implementation-control.md` (WU-CM-01-F03 section)
- `dayu/host/terminal_summary_payload.py` (full)
- `dayu/host/memory.py` (lines 1230-1260, 1610-1650)
- `dayu/host/run_input.py` (grep for dead helper chain)

Grep:
- `rg "_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu/host/run_input.py` — dead code chain confirmed
- `rg "STRICT_ALLOW_EMPTY" dayu/host` — 2 call sites in `durable/memory.py` confirmed
- `rg "_selected_assistant_item" dayu/host/memory.py` — call site at line 1241, definition at line 1614

Bash:
- `ls tests/host/test_terminal_summary_payload.py` — file does not exist (correct: plan marks as new)
- `ls tests/host/test_memory_projection.py` — file exists
- `date +%Y%m%d-%H%M%S` — timestamp for artifact filename
