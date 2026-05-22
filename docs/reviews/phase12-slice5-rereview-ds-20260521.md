# Phase 12 Slice 5 Re-Review — AgentDS

## Verdict: PASS

Blocking finding count: 0。P12-S5-F1 与 P12-S5-F2 均已修复；未发现新 blocker。

## 修复确认

### P12-S5-F1 — FIXED

**`{{fins_default_subject}}` 接入验证：**
- `base/agents.md:19`：`- 默认研究主体：{{fins_default_subject}}。`
- 全部 13 个声明 `fins_default_subject` 的 manifest 均直接引用 `base/agents.md`。
- `infer` 仅声明 `fins_default_subject`，引用 `base/agents.md` 但不引用 `base/fact_rules.md`，无 `{{base_user}}` 泄漏。
- `conversation_compaction` 声明空 `context_slots`，不引用含占位符的 base fragment。

**`{{base_user}}` 接入验证：**
- `base/fact_rules.md:4`：`- 用户原始任务：{{base_user}}。`
- 全部 12 个声明 `base_user` 的 manifest 均直接引用 `base/fact_rules.md`。

**测试覆盖验证：**
- `test_required_context_slots_are_consumed_by_migrated_fragments` 对每个 manifest 做两件事：
  1. 每个 required slot name 必须在直接装配 fragment 文本中找到 `{{slot_name}}` 占位符。
  2. `prepare_scene` 输出的 `system_messages` 必须包含注入的测试值。
- `conversation_compaction`（空 slots）与 `infer`（仅 `fins_default_subject`）均通过该测试。

**结论：** required context slot 声明与 fragment 占位符之间的语义环已闭合。无遗漏 slot，无跨 scene 泄漏。

### P12-S5-F2 — FIXED

**标记清理验证：**
- `grep '<when_tag\|</when_tag>\|<when_tool\|</when_tool>' dayu/config/prompts/` → 零结果。
- `base/tools.md` 保留 `## 财报工具指引`（fins）、`## 数据摄取工具指引`（ingestion）、`## 联网工具指引`（web）；已删除 `doc` 条件段与 `get_current_time` 工具条件段。
- 保留的三个 section 内部无任何 `<when_*>` 或 `</when_*>` 标记。

**测试覆盖验证：**
- `test_migrated_prompt_assets_exclude_legacy_conditional_markers` 遍历 `dayu/config/prompts` 下全部文件，断言不包含四种旧标记中的任何一种。

**结论：** 旧条件模板标记已从 `base/tools.md` 清理完毕，不再暴露给模型。

## 验证执行

| 验证项 | 命令 | 结果 |
|---|---|---|
| 资产装配 + slot 注入 + 标记清理测试 | `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` | 30 passed |
| import boundary + typing guard | `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 8 passed |
| pyright | `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| `{{placeholder}}` 清单 | `grep '{{' dayu/config/prompts/` | 2 处：`{{fins_default_subject}}` + `{{base_user}}`，均在 base fragment |
| 旧标记残留 | `grep '<when_tag\|</when_tag>\|<when_tool\|</when_tool>' dayu/config/prompts/` | 零结果 |

## 新发现检查

### 无新 blocker

- **Prompt asset 完整性**：18 个 fragment 文件内容均清洁，仅两个预期占位符，无意外残留。
- **迁移测试**：30 passed，覆盖 slot 消费验证、标记清理、碎片路径逃逸检查、禁止资产泄漏、happy path 装配。
- **Typing / import 边界**：pyright 0 errors，import boundary 8 passed。`test_scene_assets_migration.py` 新增 2 个测试函数，均只 import `dayu.contracts.JsonValue` 与 `dayu.runtime.scene_prepare` 公开符号，无越层依赖。
- **Docs / control 状态**：`docs/host/implementation-control.md` 当前 gate 为 "Phase 12 Slice 5 re-review"，下一 gate 为 "Slice 5 accepted local commit"。状态一致。

### 残余风险（非阻塞，非本次修复引入）

1. `base/tools.md` 保留的 fins/ingestion/web 指引是硬编码文本，不随 tool tag 动态变化。当前 ScenePrepare v1 不做条件模板，符合设计边界；若未来需按 scene 动态选择工具指引段落，应在 ScenePrepare 或 Service 侧引入 fragment 条件装配，而非在 prompt asset 中混入标记。
2. 迁移测试使用 fake 工具目录，不验证真实 Fins storage 或真实工具发现，后者仍在 Slice 5 范围外。

## 结论

P12-S5-F1 FIXED，P12-S5-F2 FIXED，无新增 blocker。Gate 可通过。
