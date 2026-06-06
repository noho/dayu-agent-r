# WU-CM-01-F03 Plan Review — AgentDS

## Verdict

**pass-with-findings** — 计划整体方向正确，code-generation-ready 程度高，但有两个 blocking finding 和一个 non-blocking finding 需在 implementation 前澄清或裁决。

---

## Review Summary

计划目标明确：收窄 LLM-facing Trace / Answer material 中 assistant final answer 文本来源，移除 `summary_text` / nested `summary` fallback，只保留 `final_answer` 和 digest-checked terminal summary artifact `content`。

计划基于直接代码证据定位了所有 `assistant_summary_from_payload` 调用点（7 处），对设计真源对齐正确，对 Engine final answer → terminal summary artifact 的写入关系理解准确。

发现两个 blocking finding：一个涉及 dead code 链的计划精确性，一个涉及两个 `_payload_with_terminal_summary` 副本的 text_policy 分歧未处理。

---

## Blocking Findings

### BF-1: `_successful_run_continuity_messages` 调用链为 dead code，计划措辞过于保守

**严重性**: Medium（不影响正确性，但影响 Slice 3 的精确性）

**直接证据**:

```
$ rg -n "successful_run_continuity" dayu
dayu/host/run_input.py:3513:def _successful_run_continuity_messages(
```

`_successful_run_continuity_messages`（line 3513）在 `dayu/` 和 `tests/` 下均无任何 production 调用。其内部调用链为：

- `_successful_run_continuity_messages` (line 3513)
- → `_successful_run_message_pair` (line 3543)
- → `_continuity_message_from_event` (line 3412)

全链均为 dead code。

**计划当前表述**（line 124）:
> `_continuity_message_from_event()` 若仍保留，只能读取 `final_answer`；缺失时返回 `None`。实现前再次确认其 production 使用点；若仍是未使用 helper，优先删除，避免旧 summary 语义残留。

**问题**: Plan review 阶段已可通过直接证据判定该链为 dead code，无需等到 "实现前再次确认"。当前计划留下了模糊空间，implementation agent 可能选择"保留并迁移"而非删除，导致旧语义残留风险。

**建议改法**: 在 Implementation Decision #4 中明确：确认 `_successful_run_continuity_messages` 无 production 调用，一并删除 `_successful_run_continuity_messages`、`_successful_run_message_pair` 和 `_continuity_message_from_event` 三个 dead function，不保留迁移版本。Slice 3 的 allowed files 中加入删除确认说明。

**验证点**: 删除后 `rg "successful_run_continuity|_continuity_message_from_event" dayu` 无残留。

**建议裁决**: 用户裁决 — 删除三个 dead function 还是保留 `_continuity_message_from_event` 做窄化迁移。

---

### BF-2: 两个 `_payload_with_terminal_summary` 副本使用不同的 `text_policy`，计划未处理分歧

**严重性**: Medium（合并时策略不一致会导致 durable vs inline delta 路径行为分歧）

**直接证据**:

`dayu/host/durable/memory.py:228-237`:
```python
if (
    assistant_summary_from_payload(
        event.payload,
        text_policy=PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY,  # ← 允许空字符串
    )
    is not None
):
    return event.payload
```

`dayu/host/run_input.py:3018-3028`:
```python
if (
    assistant_summary_from_payload(
        payload,
        text_policy=PayloadSummaryTextPolicy.STRICT_NON_EMPTY,  # ← 空字符串按缺失处理
    )
    is not None
):
    return payload
```

同一逻辑检查（"payload 是否已有 assistant 文本"），两个副本使用不同策略。Durable path 允许空字符串绕过 terminal summary lookup，inline delta path 不允许。

**计划当前表述**: 新增 `PayloadTextReadPolicy` 只保留 `STRICT_NON_EMPTY` 与 `LENIENT_NON_EMPTY`，删除了 `STRICT_ALLOW_EMPTY`。但计划未显式说明：
- `STRICT_ALLOW_EMPTY` 被移除的原因和影响
- durable path 是否应迁到 `STRICT_NON_EMPTY` 或 `LENIENT_NON_EMPTY`
- 统一策略后的行为差异（空 `final_answer` 从"视为已有文本"变为"视为缺失，触发 terminal summary lookup"）

**影响**: 如果 durable path 改用 `STRICT_NON_EMPTY`，则空 `final_answer: ""` 会触发 terminal summary artifact lookup（而旧行为是直接返回空字符串 payload）。这很可能是正确的行为修正（空 final answer 不应阻止 terminal content 查询），但需要在 plan 中作为显式决策记录，以便 implementation agent 正确实现和测试。

**建议改法**: 在 Implementation Decision #1 或 #2 中显式增加一条："`STRICT_ALLOW_EMPTY` 策略移除，原 durable path 的 `_payload_with_terminal_summary` 改用 `STRICT_NON_EMPTY`；空 `final_answer` 不再阻止 terminal summary artifact lookup。行为变更进入对应 test case。"

**验证点**: durable memory projection test 需覆盖 "空 `final_answer` + 有效 terminal content → assistant item 使用 terminal content"。

**建议裁决**: 确认策略统一方向；如需保留 durable path 的空字符串特殊处理，应在 plan 中给出理由。

---

## Non-blocking Findings

### NF-1: Import cycle 风险分析可在 plan 阶段完成

**严重性**: Low

计划 line 284-285 承认风险但推迟到 implementation：
> `terminal_summary_payload.py` 若引入 `HostTransaction` / `sqlite_payload_object` 出现 import cycle，应停止并把高阶 resolver 放入新的 Host-internal helper module

当前依赖图：

- `terminal_summary_payload.py` → `dayu.host.durable.errors`（仅错误类型）
- `payload_resolution.py` → `dayu.host.durable.{codec,errors,event_log,payload,schema,transaction}`

需新增的依赖路径：`terminal_summary_payload.py` → `payload_resolution.py`（for `sqlite_payload_object`）→ `durable.*`

当前 import chain 分析：`terminal_summary_payload` 被 `run_input.py`、`compaction_evidence.py`、`memory.py`、`durable/memory.py` 导入；这些模块均不被 `payload_resolution.py` 或其依赖链反向导入，初步判断无 cycle 风险。但 plan 没有做这个分析，implementation agent 需要自行排查。

**建议**: Plan 可补充一行静态分析结论，或标记为 implementation gate 的第一个检查项。

### NF-2: `test_terminal_summary_payload.py` 文件不存在

计划 Slice 1 allowed files 列出 `tests/host/test_terminal_summary_payload.py`，但该文件不存在：

```
$ ls tests/host/test_terminal_summary_payload.py
No such file or directory
```

其它测试文件均存在。实现时需新建此文件，不影响 plan 正确性，但应标注为"新建"。

### NF-3: 两个 `_payload_with_terminal_summary` 合并后的 text_policy 参数传递方式未设计

计划将 `_payload_with_terminal_summary` 重命名为 `_payload_with_assistant_final_answer`，并改用新 helper。但两个副本（run_input.py 和 durable/memory.py）当前向 `assistant_summary_from_payload` 传递不同的 text_policy，且 durable path 还额外向 terminal artifact 读取也传递了 text_policy。新 `assistant_final_answer_continuity_text` 的参数签名里 text_policy 应用到哪个层面（仅 read final_answer？还是也影响 terminal content read？）未在 plan 中明确。

**建议**: 在 Slice 2 描述中补充 `_payload_with_assistant_final_answer` 的 text_policy 参数传递规则。

---

## Over-design / Under-design 检查

**Over-design**: 无。计划不新增 memory category、state machine、schema 或 recall subsystem。新 helper 的拆分由字段来源的不同 truth owner 驱动，符合单一路径原则。

**Under-design**: BF-1（dead code 链保留模糊性）和 BF-2（text_policy 分歧未处理）属于轻微 under-design，可在 plan 内修复，无需重新设计。

---

## Design Source Alignment

- `docs/host/design.md:2915` — trace_material 只包含用户输入、助手最终回答和用户可见 Run 状态。计划与之一致：summary 不进入 trace material。
- `docs/host/design.md:3026` — Trace Memory 来源包括 `RUN_SUCCEEDED.final_answer`。计划与之一致：只从 `final_answer` 或 terminal artifact `content`（由 Engine final answer 写入）读取。
- `docs/host/design.md:3030` — Session Summary Memory 只来自 `CONTEXT_COMPACTED`。计划与之一致：Session Summary 不改源（Decision #6）。
- `docs/host/design.md:3040-3042` — compact 前/后的生产者不同，不能互相 fallback。计划与之一致：summary_text 不进入 assistant final answer continuity。
- `docs/host/design.md:3196` — answer_material 不得作为 evidence-backed fact source。计划与之一致。
- `docs/engine/design.md` — Engine 不拥有 Host memory。计划与之一致：不修改 Engine contract。

全部对齐。无设计真源冲突。

---

## Plan Slice 完整性检查

| Slice | 描述 | 完整性 | 备注 |
|-------|------|--------|------|
| 1. Helper Contract Replacement | 正确 | 完整 | 覆盖了新 helper、旧 helper 删除、test |
| 2. Memory Projection Narrowing | 正确 | 需补充 | BF-2 text_policy 分歧待裁决 |
| 3. RunInput / History / Fallback | 需修正 | BF-1 dead code 链待裁决 | 如裁决删除，Slice 3 简化为"删除三个 dead function" |
| 4. Compaction History / Answer Material | 正确 | 完整 | 验证 compact_material.py 已正确映射 ASSISTANT_FINAL_ANSWER → ANSWER_MATERIAL |
| 5. Imports, Dead Names, README | 正确 | 完整 | rg 命令正确 |

---

## Residual Risks / Open Questions

1. **旧 durable data 中的 `summary_text` 残留**: 计划明确按 fail-closed / 全新 schema 处理，不做旧库兼容。已有 durable data 中仅含 `summary_text` 的历史 RUN_SUCCEEDED 在 assistant continuity 中会被跳过。风险可接受。
2. **`_ref_summary_text` 的 evidence path 仍在使用**: `_selected_evidence_item`（memory.py:1652）对 TOOL_RESULT_ACCEPTED 也使用 `_ref_summary_text` fallback。本 work unit 只处理 assistant final answer path，不处理 evidence path。但两处使用同一 fallback 函数的语义一致性需后续 work unit 关注。
3. **Test fixture 迁移量**: 计划 line 285 提到旧 fixture 可能把 `display_text`/`content`/`summary_text` 当作 RUN_SUCCEEDED assistant 文本，implementation 需迁移。迁移量未知，但计划已明确"不在生产代码里保留兼容读取"。

---

## Reviewed Files / Commands

```text
Read:
  docs/host/wu-cm-01-f03-assistant-final-answer-continuity-plan.md (full)
  docs/host/design.md (L2900-L3100, L3180-L3210)
  dayu/host/terminal_summary_payload.py (full)
  dayu/host/engine_ingest.py (L4275-L4320)
  dayu/host/run_input.py (L2970-L3060, L3410-L3565)
  dayu/host/memory.py (L1610-L1720, L2911-L2932)
  dayu/host/compaction_evidence.py (L395-L430)
  dayu/host/durable/memory.py (L200-L270)
  dayu/host/durable/run_transition.py (L4209-L4250)
  dayu/host/compact_material.py (L978-L985, L1888-L1896)
  dayu/host/payload_resolution.py (L161-L176, imports)

Grep:
  rg "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests
  rg "_continuity_message_from_event" dayu
  rg "_successful_run_continuity" dayu
  rg "_payload_with_terminal_summary" dayu/host
  rg "PayloadTextReadPolicy" dayu
  rg "from dayu\.host\." dayu/host/terminal_summary_payload.py
  rg "from dayu\.host\." dayu/host/payload_resolution.py
  rg "HostTransaction" dayu/host/terminal_summary_payload.py

Bash:
  ls tests/host/test_terminal_summary_payload.py (不存在)
  ls tests/host/test_*(全部5个target test files均存在，仅 test_terminal_summary_payload.py 需新建)
```

---

## Review Verdict Summary

| 维度 | 评价 |
|------|------|
| 动机判断 | 成立。当前 helper 名称和行为确实混淆了 summary 与 final answer 语义 |
| 设计真源对齐 | 全部对齐 docs/host/design.md 和 docs/engine/design.md |
| 代码证据 | 基于直接代码阅读，非间接迹象 |
| 契约/ schema / state-machine 变更 | 无。仅内部 helper 替换 |
| Over-design | 无 |
| Under-design | BF-1（dead code 措辞保守）、BF-2（text_policy 分歧未处理） |
| 可实施性 | 通过。BF-1 和 BF-2 均为 plan 层面可修复的问题，不影响设计方向 |
