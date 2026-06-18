# Code Review — WU-CLI-ACTIVITY-01 Continuity Smoke Fix

## Scope

- Mode: current changes (uncommitted workspace)
- Branch: wu-cli-activity-01
- Base: main (committed HEAD = fa600dc2)
- Output file: docs/reviews/wu-cli-activity-01-continuity-smoke-fix-review-ds-20260618.md
- Included scope: 14 unstaged files（dayu/host/ 生产代码与 tests/host/ 测试）
- Excluded scope: committed-only 文件、docs/reviews/、CLI 层、Fins 层、Service 层
- Parallel review coverage: 无（单 reviewer 逐行走读）

## 结论：PASS

两个 smoke root cause 均已修复，无新增回归。以下一条 LOW 严重程度 finding 为既有代码问题，非本次 diff 引入，不阻塞合入。

---

## Findings

### 1-LOW-`_ref_summary_text` 在 USER_INPUT_ACCEPTED 降级路径仍可能泄漏内部 ref 到 LLM-facing 文本

- **入口/函数**: `_user_visible_text` → `_ref_summary_text`
- **文件(行号)**: `dayu/host/memory.py:2922-2944`
- **输入场景**: `USER_INPUT_ACCEPTED` projection event 的 `display_text` 字段缺失（payload 损坏或降级场景）
- **实际分支**: `_user_visible_text`（line 2929-2932）在 `display_text` 缺失时 fallback 到 `_ref_summary_text`，后者生成 `payload_ref=...; payload_digest=...` 或 `event_ref=...` 文本
- **预期行为**: 用户可见文本缺失时应返回中立占位文本（类似 `_selected_evidence_text` 的 "工具结果已接受；原始工具响应不可用。"），不应暴露内部治理标识
- **实际行为**: `event_ref=`/`payload_ref=`/`payload_digest=` 会作为 `UserMessage.content` 进入 LLM 上下文
- **直接证据**: `memory.py:1605` `_selected_user_item` 调用 `_user_visible_text(event)` → `memory.py:2929-2932` 分支 → `memory.py:2935-2944` 生成 `event_ref=` 文本 → `run_input.py:2393` 渲染为 `UserMessage`
- **影响**: 降级场景下内部治理标识泄漏到 LLM；normal path（`display_text` 存在）不受影响
- **建议改法和验证点**: 将 `_user_visible_text` 的 fallback 改为中立文本，例如 `"用户输入文本不可用。"`，与 `_selected_evidence_text` 的无 envelope 分支风格一致。验证点：在 `display_text` 缺失的 USER_INPUT_ACCEPTED fixture 上断言 `event_ref=`/`payload_ref=` 不出现在 selected recent window item text 中
- **修复风险（低）**: 仅影响降级路径，不改变 normal path 行为
- **严重程度（低）**: 非本次 diff 引入（`_ref_summary_text` 在本次 diff 中未被修改）；normal path 不受影响；但违反"禁止 event_ref/payload_ref/digest 作为 LLM-facing truth"的设计裁决

---

## 逐项检查结果

### 1. nested summary / summary_text / result_preview / event_ref / payload_ref / digest 是否进入 Conversation Memory 或 ordinary RunInput 的 LLM-facing 内容

**通过。** 本次 diff 正确移除了以下泄漏路径：

- **tool evidence 路径**：`memory.py:_selected_evidence_item`（line 1649-1668）从旧的三级 fallback（`display_text` → `content` → `_ref_summary_text`）改为新的 `_selected_evidence_text`（line 1671-1688），后者只从 accepted evidence envelope → `raw_tool_outcome` 读取，无 envelope 时返回中立 "工具结果已接受；原始工具响应不可用。"，不暴露任何内部 ref
- **final answer 路径**：`terminal_payload.py` 的 `assistant_final_answer_text_from_run_payload`（line 33-50）只读 `final_answer` 字段；`terminal_payload_content_text_from_payload`（line 53-71）只读 `content` 字段。两者都忽略 `summary_text`、nested `summary`、`preview`、`result_preview`
- **terminal artifact 写入**：`engine_ingest.py:_final_answer_plan`（line 4426-4431）的 `terminal_payload` 现在直接包含顶层 `content`/`finish_reason`/`filtered`/`degraded`，不再包裹 `{"summary": {...}}` 容器
- **evidence payload 读取**：`evidence.py:accepted_tool_raw_outcome_text_from_payload`（line 335-355）在发现 `result_preview` 字段时抛出 `ValueError`（fail closed）
- **system envelope 校验**：`run_input.py:_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS`（line 196-218）包含对 `payload_ref=`、`event_id=`、`compact_artifact_ref=` 等治理标识的阻断，在 `_normalize_ordinary_run_messages` 中对 system envelope 做最终防线校验

**已知残余**：Finding 1-LOW 中描述的 `_ref_summary_text` 降级路径，非本次 diff 引入。

### 2. terminal_summary_ref 字段名保留是否只是 durable/public 字段名保留

**通过。** `terminal_summary_ref` / `terminal_summary_digest` 在当前代码中有三类出现位置：

- **durable schema / engine ingest**：`engine_ingest.py:1123-1124` 作为 `TerminalCloseoutInput` 的字段，写入 RUN_SUCCEEDED EventLog event 的 inline payload。此时它指向 terminal payload artifact 的 descriptor，不再指向旧 `summary` 容器
- **public read API / outbox**：`read_api.py:809-810` 透传到 `OutboxTerminalItem`；`read_api.py:_succeeded_host_event`（line 900-916）用它们读取 terminal payload artifact 的顶层 `content`/`filtered`/`degraded` 字段，构造 `HostFinalAnswerView`
- **continuity resolver**：`_terminal_answer.py:44-48` 把 `terminal_summary_ref`/`terminal_summary_digest` 当作 artifact descriptor，用 `sqlite_payload_object` 做 digest 校验后只读取 terminal artifact 顶层 `content`

三个层次均未把 `terminal_summary_ref` 字段名重新当作 summary 真理源。字段名保留只是 durable contract 兼容，不改变语义。

### 3. accepted tool evidence 是否真正从 accepted envelope 指向的 digest-checked payload 读取 raw_tool_outcome

**通过。** 四个消费点共享同一证据读取链路，均 fail closed：

| 消费点 | 函数 | 文件:行号 | 读取路径 |
|--------|------|-----------|----------|
| Memory projection | `_selected_evidence_text` | `memory.py:1671-1688` | envelope → `accepted_tool_raw_outcome_text_from_payload(event.payload)` → `raw_tool_outcome` |
| Memory projection (durable) | `_tool_result_memory_payload` | `durable/memory.py:380-409` | envelope → `event_payload_object_for_result_ref(payload_ref, payload_digest)` → digest-checked |
| Compaction evidence | `_tool_result_evidence_materials` | `compaction_evidence.py:199-247` | envelope → `_accepted_tool_result_payload` → digest-checked → `accepted_tool_raw_outcome_text_from_payload` |
| RunInput material | `build_accepted_tool_evidence_material_blocks` | `run_input.py:1393-1472` | 复用 `collect_selected_compaction_request_evidence_inputs` → 同上 |

**fail-closed 路径**：
- `accepted_tool_raw_outcome_text_from_payload`（`evidence.py:350-351`）：`result_preview` 存在时抛 `ValueError`
- `_selected_evidence_text`（`memory.py:1685-1687`）：有 envelope 但 `raw_tool_outcome` 缺失时抛 `ValueError`
- `_tool_result_evidence_materials`（`compaction_evidence.py:219-223`）：`result_preview` 或缺失 `raw_tool_outcome` 时抛 `HostDurableError`
- `_accepted_tool_result_payload`（`compaction_evidence.py:250-270`）：`payload_ref`/`payload_digest` 不匹配时由 `event_payload_object_for_result_ref` 抛 `HostDurableError`

### 4. durable projection、inline repair、compact material、compaction evidence 是否共享同一语义，是否存在逻辑漂移

**通过。** 四个路径均导入并调用相同的两个基础 helper：

- `dayu.host.terminal_payload`：`assistant_final_answer_text_from_run_payload`、`terminal_payload_content_text_from_payload`、`PayloadTextReadPolicy`
- `dayu.host.evidence`：`accepted_evidence_envelope_from_payload`、`accepted_tool_raw_outcome_text_from_payload`
- `dayu.host._terminal_answer`：`assistant_final_answer_continuity_text`（统一 descriptor-backed fallback 逻辑）

策略差异是 design-intent：
- Memory projection selected window 使用 `LENIENT_NON_EMPTY`（容忍缺失，不阻塞 projection）
- Compaction material / compaction evidence 使用 `STRICT_NON_EMPTY`（缺失时抛错）
- 这一差异在 `_terminal_answer.py:8-16` 的模块 docstring 中明确说明

无逻辑漂移。

### 5. 是否无 Host / Engine public API/contract drift

**通过。** 本次 diff 的内部重命名不影响 public contract：

- `_TerminalPlan.terminal_summary` → `terminal_payload`：`_TerminalPlan` 是 `engine_ingest.py` 内部 dataclass，不导出
- `_write_terminal_summary` → `_write_terminal_payload`：EngineEventIngestor 私有方法
- terminal artifact schema 变更：从 `{"summary": {"content": ..., ...}}` 变为 `{"content": ..., "finish_reason": ..., ...}`（顶层字段），但 `_succeeded_host_event`（`read_api.py:917-928`）已同步改为读取顶层字段
- Public `HostFinalAnswerView`、`OutboxTerminalItem`、`HostEvent` 的字段名与类型不变
- `terminal_summary_ref` / `terminal_summary_digest` 在 public contract 中的字段名不变

### 6. 测试是否覆盖两个 smoke root cause，是否还需要补测试

**通过。** 现有测试覆盖充分：

- **Smoke root cause 1（final answer continuity）**：
  - `test_terminal_payload.py:test_run_payload_summary_fields_are_not_final_answer_sources` — 验证 `content`/`summary_text`/nested `summary` 不被读取
  - `test_terminal_payload.py:test_terminal_payload_summary_preview_fields_are_not_content_sources` — 验证 terminal artifact 的 `summary_text`/`preview`/`result_preview`/nested `summary` 不被读取
  - `test_terminal_payload.py:test_continuity_resolver_reads_digest_checked_terminal_content` — 验证 digest-checked artifact content fallback
  - `test_terminal_payload.py:test_continuity_resolver_prefers_run_final_answer_over_artifact` — 验证优先级
  - `test_public_tool_wiring_smoke.py:test_mock_tool_result_feeds_same_run_and_later_run_continuity` — 端到端验证后续 run 能拿到 prior content

- **Smoke root cause 2（tool evidence 内部 ref 泄漏）**：
  - `test_public_tool_wiring_smoke.py:84-88` — 反向断言：`assert "event_ref=" not in joined`、`assert "payload_ref=" not in joined`、`assert "payload_digest=" not in joined`、`assert "result_preview" not in joined`
  - `test_memory_projection.py` — 133 行新增测试，覆盖 memory projection 的 evidence item 构造

**建议补测**：`_user_visible_text` 降级路径（`display_text` 缺失时）应增加测试，确保不泄漏 `event_ref=`/`payload_ref=`。这是 Finding 1-LOW 的对应测试缺口。

### 7. README 触发边界是否合理

**通过。** 本次改动：
- 未改变 Host / Engine public API 形状（字段名保留，类型不变）
- 未改变用户可见安装、初始化、CLI / Web / WeChat 入口、命令参数
- 未改变分层关系、装配方式、`UI / Service / Host / Agent` 边界
- `dayu/host/terminal_payload.py` 是新增内部 helper，不改变 `dayu/host/README.md` 的模块边界描述

按照 `CLAUDE.md` 的 README 更新触发规则，`dayu/host/` 修改需检查 `dayu/host/README.md`。但 `dayu/host/README.md` 描述的是 Host 整体架构与公共 API surface；本次改动是 internal continuity helper 重构与 evidence 读取收敛，不改变 Host 对外 contract。README 无需更新。

---

## Open Questions

- `outbox.py:_final_answer_json`（line 363）读 `_PAYLOAD_FIELD_FINAL_ANSWER` 从 RUN_SUCCEEDED inline payload，但 inline payload 中 `final_answer` 字段可能不存在（仅在 `_payload_with_assistant_final_answer` 的 transient merge 中存在）。这可能导致 outbox 的 `final_answer_json` 列在某些路径下为 `None`。此行为是 outbox projection 的既有设计，非本次 diff 引入，但值得在后续 outbox 专项 review 中确认其正确性。

## Residual Risk

- ~~`memory.py:_ref_summary_text`（line 2935-2944）在 `_user_visible_text` 的 `display_text` 缺失降级路径中仍可能向 LLM 暴露 `event_ref=`/`payload_ref=`/`payload_digest=`。Normal path（`display_text` 存在）不受影响。建议后续单独修复。~~ → **已由 Codex 增量修复，见下方 Incremental Review。**
- 旧 nested `summary` terminal artifact 不做兼容读取。如果存在未迁移的旧 durable 数据（`engine_ingest` metadata kind 为 `"engine_terminal_summary"` 的旧 payload），`read_api._succeeded_host_event` 会在 `_sqlite_payload_object` 读不到顶层 `content` 字段时抛 `HostDurableError`（fail closed）。这是设计意图，但运维侧需确认无存量旧格式数据。
- ~~未覆盖 `_user_visible_text` 降级路径的测试（见 Finding 1-LOW）。~~ → **已由增量测试覆盖，见下方 Incremental Review。**

---

## Incremental Review — Codex fix for Finding 1-LOW（`_ref_summary_text` removal）

### Scope

- Mode: 增量复核（基于原 review artifact Finding 1-LOW 的 Codex 修复）
- 增量文件：`dayu/host/memory.py`、`tests/host/test_memory_projection.py`

### 结论：PASS

所有三个复核点均通过，原 Finding 1-LOW 已完全解决。无新增 regression。

### 增量审查

#### 1. `_ref_summary_text` 删除与 USER_INPUT fallback

**通过。** `_ref_summary_text` 函数（原 `memory.py:2935-2944`）已完全删除，零残余引用（`grep -rn '_ref_summary_text' dayu/host/ tests/` 无结果）。`_user_visible_text`（`memory.py:2922-2931`）的新 fallback 行为：

```python
display_text = _optional_payload_str(event.payload, _PAYLOAD_FIELD_DISPLAY_TEXT)
if display_text is not None:
    return display_text
return _USER_INPUT_TEXT_UNAVAILABLE
```

`_USER_INPUT_TEXT_UNAVAILABLE = "用户输入文本不可用。"` 是模块级私有常量（`memory.py:81`），不含任何内部治理标识（event_id、event_ref、payload_ref、payload_digest、sha256 digest）、不含伪装的业务事实、不暗示系统状态。文案与 `_selected_evidence_text` 的无 envelope 分支 "工具结果已接受；原始工具响应不可用。" 风格一致——诚实声明信息不可用，不捏造内容。

#### 2. 新测试覆盖

**通过。** 增量增加了三个测试，覆盖关键场景：

| 测试 | 文件:行号 | 覆盖场景 | 断言 |
|------|-----------|----------|------|
| `test_user_input_missing_display_text_does_not_expose_refs` | `test_memory_projection.py:406` | USER_INPUT_ACCEPTED payload 为空 (`{}`)，但携带 `payload_ref` 与 `payload_digest` | `event_ref=`、`payload_ref=`、`payload_digest=`、`sha256:`、原始 event/payload id 均不出现在 selected recent window text 中 |
| `test_accepted_tool_evidence_uses_raw_outcome_not_preview_or_refs` | `test_memory_projection.py:556` | TOOL_RESULT_ACCEPTED 同时携带 `display_text`、`content`、accepted evidence envelope、`raw_tool_outcome` | only `raw_tool_outcome` 的文本进入 memory；`display_text`、`content`、event id、payload ref 均不出现 |
| `test_accepted_tool_evidence_rejects_result_preview` | `test_memory_projection.py:627` | TOOL_RESULT_ACCEPTED 同时携带 `raw_tool_outcome` 和旧 `result_preview` | `pytest.raises(ValueError, match="result_preview")` — fail closed |

`test_user_input_missing_display_text_does_not_expose_refs` 精确覆盖原 Finding 1-LOW 描述的降级场景：`display_text` 缺失 + 有 `payload_ref`/`payload_digest`。其断言列表（line 422-429）禁止所有内部治理标识泄漏。

#### 3. 无 public API/contract drift 或不合理语义

**通过。** 所有变更均为模块内部：

- `_ref_summary_text`：已删除的模块私有函数，不在 `__all__` 中
- `_user_visible_text`：模块私有函数，行为变更仅限于已不可达的 fallback 分支
- `_selected_evidence_text`：新增模块私有函数
- `_USER_INPUT_TEXT_UNAVAILABLE`：模块私有常量
- `dayu/host/memory.py` 的 `__all__` 未变更
- 无新增 import 穿透到上层模块
- 占位文本不伪装为业务事实、不暴露系统内部状态

### 更新的 Residual Risk

- 原 Finding 1-LOW 已解决，原 Residual Risk 中对应条目已消除
- 其余 Residual Risk（旧 durable 数据兼容、outbox `final_answer_json` Open Question）不变
