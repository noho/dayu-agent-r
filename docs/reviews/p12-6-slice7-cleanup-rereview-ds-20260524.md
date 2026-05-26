# P12.6 Slice 7 Cleanup Re-review - AgentDS - 2026-05-25

## 基本信息

- Gate: code review（cleanup re-review）
- Work-unit: P12.6 conversation memory redesign
- Slice: Slice 7 review cleanup
- Reviewer: AgentDS
- 日期: 2026-05-25
- Base checkpoint: `a2114a2 gateflow: accept P12.6 slice 6`
- 原始 review artifacts:
  - MiMo: `docs/reviews/p12-6-slice7-code-review-mimo-20260524.md`
  - DS: `docs/reviews/p12-6-slice7-code-review-ds-20260524.md`
- Cleanup artifact: `docs/reviews/p12-6-slice7-cleanup-codex-20260524.md`
- 审查范围: `dayu/host/compact_payload.py`（新增）、`dayu/host/dispatch.py`、`dayu/host/run_input.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/fake_compaction.py`、`tests/host/test_public_compact_smoke.py`、`tests/host/test_run_input_builder.py`

## Verdict

**PASS** — cleanup 正确修复了所有目标 findings，未引入新问题。

---

## 逐项 Fix 验证

### MiMo F1 [Medium] — `_text_tuple_from_mapping` 与 `_optional_text_list` 逻辑重复

**Verdict: FIXED。**

证据：
- `dispatch.py` 中 `_text_tuple_from_mapping` 已删除，替换为 `from dayu.host.compact_payload import preserved_canonical_evidence_refs`（dispatch.py:131）。
- `run_input.py` 中 `_preserved_canonical_evidence_refs`（旧私有 helper）已删除，替换为 `from dayu.host.compact_payload import preserved_canonical_evidence_refs`（run_input.py:48）。
- `run_input.py` 中 `_optional_text_list`（旧私有 helper）已删除，替换为 `from dayu.host.compact_payload import optional_text_list_field`（run_input.py:47）。
- `run_input.py` 中 `_preserved_fact_refs_text`（旧私有 helper）已删除，替换为 `from dayu.host.compact_payload import preserved_fact_refs_summary`（run_input.py:49）。
- `_PAYLOAD_FIELD_PRESERVED_FACT_REFS`、`_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS`、`_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS` 常量已从 `run_input.py` 移除，这些常量现在只在 `compact_payload.py` 中定义。
- dispatch 与 run_input 均无新增私有 parser、无交叉导入对方私有 helper。

### MiMo F2 [Medium] — proactive represented evidence refs 构造未复用 `_preserved_canonical_evidence_refs`

**Verdict: FIXED。**

证据：
- `dispatch._proactive_represented_evidence_refs`（dispatch.py:3304-3336）中 compact event payload 的 canonical evidence refs 提取已改为 `preserved_canonical_evidence_refs(_payload_object(compacted))`（line 3335），不再手动两层嵌套读取 `preserved_fact_refs` → `canonical_evidence_refs`。
- `run_input.py` 的 `CompactArtifactView` 构造（run_input.py:1267）同样使用 `preserved_canonical_evidence_refs(payload)`，与 dispatch 路径同一实现。

### DS Finding 1 / MiMo F4 [Low] — `_latest_session_compacted_event_before_input` 新建 `EventLogStore()` 实例

**Verdict: FIXED。**

证据：
- `_latest_session_compacted_event_before_input` 签名已改为 `(transaction: HostTransaction, event_log_store: EventLogStore, *, run: RunRow)`（dispatch.py:3339-3341）。
- `_proactive_represented_evidence_refs` 签名已加入 `event_log_store: EventLogStore` 参数（dispatch.py:3306），并透传给 `_latest_session_compacted_event_before_input`（line 3331-3332）。
- 调用方 `HostDispatchScheduler` 使用 `self._event_log_store`（dispatch.py:1377、1382），完整传递链：`self._event_log_store` → `_proactive_material_blocks` → `_proactive_represented_evidence_refs` → `_latest_session_compacted_event_before_input` → `event_log_store.read_event_by_id(...)`。
- 不再存在局部 `EventLogStore()` 构造。

---

## 新增模块审查：`dayu/host/compact_payload.py`

| 检查项 | 结果 |
|--------|------|
| 模块中文 docstring | PASS — 清晰说明模块目的与使用方 |
| `optional_text_list_field` 中文 docstring | PASS — 含 `:param`/`:returns` |
| `preserved_canonical_evidence_refs` 中文 docstring | PASS — 含 `:param`/`:returns` |
| `preserved_fact_refs_summary` 中文 docstring | PASS — 含 `:param`/`:returns` |
| 严格类型（无 `Any`/`object`） | PASS — 全部使用 `Mapping[str, JsonValue]`、`tuple[str, ...]` |
| 分层约束 | PASS — 仅依赖 `dayu.contracts.json_value`，无上层/反向依赖 |
| 模块级常量命名 | PASS — `_FIELD_*` 前缀私有常量 |

---

## 分层与导入审查

| 检查项 | 结果 |
|--------|------|
| `dispatch → compact_payload` | PASS — Host 内部横向依赖，方向正确 |
| `run_input → compact_payload` | PASS — Host 内部横向依赖，方向正确 |
| `compact_payload → contracts` | PASS — 仅依赖底层契约 |
| 无 `compact_payload → dispatch/run_input/engine/fins/service/ui` | PASS |
| 无新 lazy import | PASS |
| 无新胶水 seam | PASS |

---

## 测试变更审查

| 文件 | 变更 | 评估 |
|------|------|------|
| `tests/host/test_run_input_builder.py` | `_preserved_fact_refs_text` → `preserved_fact_refs_summary`（导入与断言） | PASS — 测试追踪共享 helper，未引入兼容 re-export |
| `tests/host/fake_compaction.py` | 无变更（MiMo F3 accepted as non-blocking） | PASS — `_candidate_from_final_answer` 导入保持原样 |
| `tests/host/test_public_compact_smoke.py` | 无变更 | PASS — smoke 断言不变 |

测试结果：`292 passed, 1 skipped`；pyright：`0 errors, 0 warnings, 0 informations`。

---

## README 审查

| 文件 | 评估 |
|------|------|
| `dayu/host/README.md` | PASS — Context Compaction 段落已含 proactive pre-start evidence 描述，cleanup 不改变已文档化的行为 |
| `tests/README.md` | PASS — 无变化需求 |

---

## 未修复项（非本次 cleanup 目标）

| Finding | 状态 |
|---------|------|
| MiMo F3 — `fake_compaction.py` 导入 `_candidate_from_final_answer` | Accepted non-blocking，未修复 |
| DS Finding 2 — `_required_row_text` / `_required_host_row_text` 重复 | LOW，未修复 |
| DS Finding 3 — evidence id 跨模块标识符链 | INFO，未修复 |
| DS Finding 4 — no-tool scenario 冗余 EventLog 查询 | INFO，未修复 |

---

## New Findings

无 blocking 或 medium 新 finding。

### NF1 [LOW] — `context_events._optional_text_list` 与 `compact_payload.optional_text_list_field` 语义差异

- 文件: `dayu/host/context_events.py:773-794` vs `dayu/host/compact_payload.py:19-36`
- 证据: `context_events._optional_text_list` 对非法类型 raise `ValueError`，要求每项为非空文本；`compact_payload.optional_text_list_field` 宽容返回空 tuple，过滤空字符串。两者语义不同（strict vs tolerant），不是重复实现。
- 影响: 无功能影响。但同一项目中两个"读取文本列表"的 helper 使用不同的错误处理策略，后续维护者可能误用。
- 建议: 暂不修复。`compact_payload` 版的宽容语义是其设计意图（compact payload 字段可能缺失或格式不完整）。两模块职责不同，语义差异有合理性。

---

## Slice 7 Success Signal 验证

原始 success signal：**public proactive accepted evidence 在 production path 下正确进入 compactor `evidence_input`**。

验证结果：
| 指标 | 状态 |
|------|------|
| `test_post_compaction_fact_reuse_uses_raw_accepted_tool_evidence` | PASS |
| `test_no_compaction_recent_raw_turns_continuity` | PASS |
| `test_long_user_input_second_factor_survives_minimum_preserve` | PASS |
| `test_multi_compact_public_path_keeps_memory_and_compactor_input_bounded` | PASS |
| `test_proactive_compact_duplicate_prompt_does_not_exceed_compactor_window` | PASS |
| `test_real_compactor_public_opener_compacts_and_preserves_continuity` | SKIP（预期） |
| Pyright clean | 0 errors |
| 全部 host 测试 | 292 passed, 1 skipped |

**Success signal 仍成立。**

---

## Residual Risks

1. **`_required_row_text` / `_required_host_row_text` 重复**（DS Finding 2）— 已知 LOW，未在本次 cleanup 修复。两个模块级私有 helper 功能等价，后续若统一错误消息格式需同步两处。
2. **Evidence id 跨模块标识符链**（DS Finding 3）— 已知 INFO。`fact.evidence_refs` → `accepted_evidence_id` → `canonical_evidence_refs` 三者同源前提无显式 contract test。
3. **`context_events._optional_text_list` vs `compact_payload.optional_text_list_field`**（NF1）— 语义差异有合理性，但需注意两者不可互换。
4. **真实 compactor smoke 默认 skip** — 真实 LLM 输出解析路径仅按需手动验证（`DAYU_RUN_REAL_COMPACTOR_SMOKE=1`）。

---

## 总结

Cleanup 正确修复了 MiMo F1/F2（compact payload 解析去重）和 DS Finding 1 / MiMo F4（EventLogStore 参数注入）。新增 `compact_payload` 模块设计干净，分层正确，中文 docstring 完整，类型严格。dispatch 与 run_input 均无残留旧私有 parser，无交叉导入。全部测试通过（292 passed, 1 skipped），pyright 零错误。Slive 7 public proactive accepted evidence success signal 保持成立。无 blocking 新 findings。
