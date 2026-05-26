# Gateflow Code Review：Public Memory Scenario Smoke S2

## Gate

- Work unit：Host public conversation memory scenario smoke
- 当前 gate：code review (S2)
- 复审目标：
  - `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`
  - `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`
  - `tests/runtime/test_scene_assets_migration.py`
  - `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s2-codex-20260526.md`
- 复审人：DS review worker
- Controller 已通过：`pytest tests/runtime/test_scene_assets_migration.py -q` → 6 passed，manifest inspection 确认 scene id / tag / allow_tool_calls / max_iterations / context_slots
- S1a accepted commit：`2c98662`
- S1b accepted commit：`b984460`
- 复审标准：manifest schema/fields 与现有 public smoke 风格一致、新 prompt 支持 DAYU_MEM_ASSERT 类核对行且不泄露 runtime/pressure 细节或嵌入答案、迁移 inventory 正确且不改变已有 scene 行为、S2 artifact 准确报告验证与残余风险

---

## 逐项核对

### 1. Manifest schema/fields 与现有 public smoke 风格一致

以 `smoke_host_public_conversation_memory.json` 为对照基线：

| 字段 | 基线值 | 新 manifest 值 | 判定 |
|------|--------|---------------|------|
| `schema_version` | 1 | 1 | PASS |
| `scene` | `smoke_host_public_conversation_memory` | `smoke_host_public_conversation_memory_scenarios` | PASS — 独立 scene id |
| `version` | `"v1"` | `"v1"` | PASS |
| `description` | 中文描述 | 中文描述，语义匹配 | PASS |
| `capability_tags` | `[scene_id]` | `[scene_id]` | PASS |
| `extends` | `[]` | `[]` | PASS |
| `model.default_model_id` | `"mimo-v2.5-pro-plan"` | `"mimo-v2.5-pro-plan"` | PASS |
| `model.runner_option_hint_id` | `"interactive"` | `"interactive"` | PASS |
| `agent_policy.max_iterations` | 20 | **32** | PASS — 场景 smoke 合理需要更多轮次 |
| `agent_policy.allow_tool_calls` | `true` | `true` | PASS |
| `tool_selection.mode` | `"select"` | `"select"` | PASS |
| `tool_selection.tool_tags_any` | `["manual-smoke"]` | `["manual-smoke"]` | PASS |
| `tool_selection.allow_empty` | `false` | `false` | PASS |
| `defaults` | `fail_closed` | `fail_closed` | PASS |
| `fragments` | base/agents + base/fact_rules + scene prompt | 完全同构，仅 scene prompt 指向新文件 | PASS |
| `context_slots` | `[]` | `[]` | PASS |

**额外检查**：
- 无 `conversation`、`runtime` 等旧 manifest 遗留字段。PASS。
- `model` 中无 `default_name`、`temperature_profile` 等旧字段。PASS。
- 顶层字段完全在 `_ALLOWED_MANIFEST_FIELDS` 内。PASS。

与 `smoke_host_public_multiturn.json` 对比：后者有非空 `context_slots`（`fins_default_subject`、`base_user`），新 manifest 为 `[]`，这与 conversation_memory 基线（同样为空 `context_slots`）一致。场景 smoke 不需要 context slot 注入。PASS。

### 2. Scene prompt 内容审查

逐行对比基线 prompt（`smoke_host_public_conversation_memory.md`）与新 prompt：

| 差异点 | 基线 | 新 prompt | 判定 |
|--------|------|-----------|------|
| Line 3 场景定位 | "smoke 验证场景" | "smoke" | PASS — 泛化为场景级用语 |
| Line 6 核对行标记 | `DAYU_FINANCE_MEMORY_ASSERT` | `DAYU_MEM_ASSERT` 或同类核对行 | PASS — 泛化 marker 名称，覆盖更宽 |
| Line 7 反幻觉 | 无 | "如果会话里没有确认过某个事实，明确说明没有确认，不要编造数值。" | PASS — 合理反幻觉防护 |
| 共有的指令 | 优先回答财务问题、按允许工具调用、不披露 smoke 细节、输出 Markdown | 完全一致 | PASS |

**Anti-cheat 逐项检查**：

- 无公司名、股票代码、财务数值或任何预先植入的答案。PASS。
- 无 `fins_default_subject`、`base_user` 或 context slot 占位符。PASS。
- 无 compaction pressure、token threshold、artifact 路径等 runtime 诊断泄露。PASS。
- 无 `context_slots` 注入路径（manifest `context_slots: []`）。PASS。
- "原样输出" 指令仅要求按用户给定字段回显，不隐含任何预置正确答案。PASS。

### 3. 迁移 inventory 正确性与已有 scene 不变性

`tests/runtime/test_scene_assets_migration.py` 变更：

```diff
+    "smoke_host_public_conversation_memory_scenarios": 32,
```

| 检查项 | 结果 |
|--------|------|
| 新增条目 key 与 manifest `scene` 字段完全一致 | PASS |
| 新增条目 value `32` 与 manifest `agent_policy.max_iterations` 完全一致 | PASS |
| 已有条目未做任何修改（逐行比对 `_OLD_SCENE_MAX_ITERATIONS` 其余 15 项） | PASS |
| `_COMPACTOR_POLICY_SCENES` 未修改 | PASS |
| 其他测试辅助常量（`_ALLOWED_MANIFEST_FIELDS` 等）未修改 | PASS |
| 所有 6 个测试函数的断言逻辑未修改 | PASS |
| 新 manifest 通过 `test_all_migrated_scene_assets_prepare_successfully`（`prepare_scene` 全量遍历） | PASS |
| 新 manifest 通过 `test_migrated_scene_manifest_schema_excludes_legacy_fields` | PASS |
| 新 manifest 通过 `test_scene_manifest_agent_policy_carries_old_max_iterations_only`（`max_iterations=32`、无 `tool_timeout_seconds`/`tool_execution_timeout_seconds`） | PASS |

已有 smoke asset 不变性确认（`git status` 快照）：
- `smoke_host_public_conversation_memory.json` 未修改
- `smoke_host_public_conversation_memory.md` 未修改
- `smoke_host_public_multiturn.json` 未修改
- `smoke_host_public_multiturn.md` 未修改

### 4. S2 implementation artifact 准确性

| artifact 声称 | 核查结果 |
|---------------|----------|
| "新增独立 scene asset，不修改 smoke_host_public_conversation_memory 最小 smoke asset" | 确认 — 已有文件未修改 |
| Manifest 字段逐项声明（model / agent_policy / tool_selection / context_slots 等） | 逐项与 manifest 文件比对，全部一致 |
| `pytest tests/runtime/test_scene_assets_migration.py -q` → "6 passed" | 确认 |
| 轻量 scene prepare 检查输出 `max_iterations=32, tool_names=('fake_smoke_fact',)` | 确认 — 与 manifest 一致 |
| `pyright` → "0 errors, 0 warnings, 0 informations" | 确认 |
| Docs Decision：本 slice 未更新 README，原因 S4 | 确认合理 — S2 无用户入口 |
| 残余风险 1："场景脚本尚未接入该 scene id" | 确认合理 — 归属 S3/S4 |
| 残余风险 2："新 prompt 对具体 assertion marker 的行为只能由后续验证" | 确认合理 |
| 残余风险 3："未运行真实 LLM smoke" | 确认合理 — S2 目标是资产装配 |
| Stop Status："未提交、未推送、未开 PR" | 确认 |

---

## 发现

### Finding 1 — [INFO] S2 artifact 未记录 `_OLD_SCENE_MAX_ITERATIONS` 的新增条目为唯一测试文件变更

**位置**：`docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s2-codex-20260526.md` Changed Files 节

**描述**：artifact 的 Changed Files 和 Implemented Plan Items 节准确描述了三个文件变更，但未显式说明 `test_scene_assets_migration.py` 的变更范围仅限于在 `_OLD_SCENE_MAX_ITERATIONS` 中新增一行条目，未修改任何测试函数逻辑。虽不影响 review 结论，但明确此点有助于后续 gate 快速确认 migration test 本身未被意外改动。

**严重程度**：信息性，非缺陷。

---

## Residual Risk（新增）

- **max_iterations=32 的业务合理性**：32 是当前所有 smoke scene 中最高的 max_iterations。场景 smoke 的多轮结构可能确实需要更多迭代，但尚未有 S3/S4 运行数据验证该值是否过约束或浪费。归属 S3/S4 实测后确认。
- **Scene prompt 泛化程度**：新 prompt 将 marker 从 `DAYU_FINANCE_MEMORY_ASSERT` 泛化为 `DAYU_MEM_ASSERT` 或同类核对行，并新增反幻觉指令。这些变更与 S1b 场景脚本中的实际 marker 使用是否对齐，需 S3 验证。

---

## Verdict

**PASS**

Manifest schema/fields 与现有 public smoke 基线完全一致（除 max_iterations=32 为场景合理差异）。Scene prompt 正确支持 DAYU_MEM_ASSERT 类核对行，不泄露 runtime/pressure 细节，不嵌入答案。迁移 inventory 新增条目正确，已有 scene 行为未改变。S2 artifact 准确报告验证结果与残余风险。

无 blocking finding。
