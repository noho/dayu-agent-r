# WU-PROJ-01 Slice 4 Code Review - AgentMiMo

## 元数据

- Work unit: `WU-PROJ-01`
- Slice: Slice 4 accepted compact -> Conversation Memory -> ordinary RunInput regression
- Gate: code review
- 日期: 2026-06-11
- 执行者: AgentMiMo
- 分支: `wu-proj-01`

## Preflight

- `git branch --show-current`: `wu-proj-01` ✓
- `git status --short`: 仅修改 `tests/host/test_dispatch_scheduler.py`、`tests/host/test_memory_projection.py`、`tests/host/test_run_input_builder.py`，新增 `docs/reviews/wu-proj-01-slice4-implementation-codex.md`。生产代码未改动 ✓

## 测试验证

```
tests/host/test_memory_projection.py              14 passed
tests/host/test_run_input_builder.py::test_run_input_memory_messages_include_context_compacted_projection  1 passed
tests/host/test_dispatch_scheduler.py::test_pre_start_governance_compact_failure_is_attempt_free  1 passed
────────────────────────────────────────────────────────
18 passed, 0 failed

pyright: 0 errors, 0 warnings, 0 informations
```

## 审查结论: PASS-WITH-FINDINGS

### 1. accepted compact 经 durable ProjectionRunner 物化五类 memory section

**结论: PASS**

`test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot` 已从单薄断言扩展为覆盖五类 memory section 的完整回归：

| Section | 断言 |
|---|---|
| session_summary_memory | `summary_text == "用户关注收入增速和毛利率变化。"` |
| evidence_fact_memory | `evidence_backed_facts[0].claim_text == "收入增长。"` |
| answer_anchor_memory | `anchors[0].anchor_title == "收入口径"` |
| forward_intent_memory | `intents[0].text == "下一轮继续核对费用率。"` |
| trace_memory | `reference_continuity_items[0].text == "..."` |

该测试通过 durable `ProjectionRunner.run_once()` 路径执行，不是只测 builder helper。checkpoint 同步推进断言证明了 snapshot 与 checkpoint 在同一事务内提交：

```python
assert checkpoint.checkpoint_event_sequence == 1
assert checkpoint.checkpoint_event_id == "compact-1"
assert latest.snapshot.cursor.checkpoint_event_sequence == checkpoint.checkpoint_event_sequence
assert latest.snapshot.cursor.checkpoint_event_id == checkpoint.checkpoint_event_id
```

### 2. ordinary RunInput 读取五类业务 section

**结论: PASS**

`test_run_input_memory_messages_include_context_compacted_projection` 已扩展，断言 system envelope 包含五个 section header：

```python
assert "## Conversation Summary" in system_content
assert "## Verified Evidence and Facts" in system_content
assert "## Prior Answer Anchors" in system_content
assert "## Open Follow-up Context" in system_content
assert "## Reference Continuity" in system_content
```

`_single_system_content()` helper 同时校验了 one-system-message contract 与内部标识符不泄漏。section header 断言是业务可读的，不是内部实现术语。

### 3. failed compact negative regression

**结论: PASS**

新增 `test_projection_consumer_skips_failed_compact_without_memory_snapshot` 在 durable store 层证明：

- `CONTEXT_COMPACTION_FAILED` 被 ProjectionRunner 扫描（`events_scanned == 1`）
- 不命中 memory consumer（`events_matched == 0`、`events_applied == 0`）
- 不写 snapshot（`latest is None`）
- 不写 memory items（`item_count == 0`）
- checkpoint 仍推进到 failed event（`checkpoint_event_sequence == 1`）

与已有 `test_failed_compaction_event_does_not_materialize_memory_sections`（纯函数层，测试 `project_conversation_memory_event` 返回空 sections）形成互补：旧测试证明投影函数行为，新测试证明 durable store 行为。

dispatch scheduler test 的 `assert _compact_artifact_files(compact_artifact_root) == ()` 证明 failed compact fallback 不生成 compact artifact 文件。

### 4. 测试质量问题

**Finding 1 (低严重度): accepted compact test 断言与 fixture 字符串紧耦合**

`test_projection_consumer_applies_event_and_writes_durable_vnext_snapshot` 的五类 section 断言精确匹配 `_accepted_compact_payload()` fixture 中的硬编码字符串。例如 `"用户关注收入增速和毛利率变化。"` 必须与 fixture 的 `session_summary.summary_text` 完全一致。

这使得测试断言与 fixture 数据形成单源耦合。若 fixture 修改，断言也会跟着变，但断言本身不证明投影逻辑独立于 fixture 值。这是当前仓库 regression test 的常见模式（类似 `test_accepted_compact_materializes_vnext_memory_sections`），不阻塞当前 slice。

**Finding 2 (低严重度): RunInput test 混合 section header 断言与 content 断言**

`test_run_input_memory_messages_include_context_compacted_projection` 同时断言：
- system envelope 中的 section header（`## Conversation Summary`）
- message tuple 中的 content fragment（`any("summary=episode navigation only" in content ...)`）

section header 断言证明 RunInputBuilder 正确渲染 section 结构；content 断言证明 memory 数据被注入。两种断言覆盖不同维度，是互补而非冗余。但 content 断言使用 `any(... in content for content in contents)` 匹配整个 message tuple，不如 section header 断言精确。

**Finding 3 (信息级): `_memory_item_count` helper 作用域**

新增的 `_memory_item_count` helper 仅被 `test_projection_consumer_skips_failed_compact_without_memory_snapshot` 一个测试使用。当前无需提取为共享 helper，但若后续测试需要断言 memory item 数量，可复用。

### 5. S3-R1 未覆盖是否可接受

**结论: 可接受**

`WU-PROJ-01-S3-R1` 是 dispatch before-worker catch-up happy path 独立集成测试缺口。该 residual risk 在实现 artifact 中已明确标记为 `deferred-with-owner`，理由是"当前 slice 未硬造脆弱 dispatch catch-up happy path"。

Slice 4 的定位是 projection 和 RunInput regression safety net，不是 dispatch integration 测试。S3-R1 的覆盖应由后续 Host dispatch test hardening 承接。

### 6. 其它审查项

- 生产代码未改动，符合 implementation artifact 声明 ✓
- pyright 0 errors ✓
- 测试 docstring 更新准确反映了测试意图 ✓
- `_compact_artifact_files` helper 设计合理，使用 `rglob` 递归扫描 ✓
- `_memory_item_count` helper 使用参数化表名 `TABLE_HOST_MEMORY_ITEMS`，不硬编码 ✓

## 残余风险

- `WU-PROJ-01-S3-R1`：仍为 deferred-with-owner，当前 slice 未覆盖。
- 本次未运行完整 `tests/host/test_dispatch_scheduler.py` 全文件，implementation artifact 已声明可作为后续更大范围 gate 验证。
