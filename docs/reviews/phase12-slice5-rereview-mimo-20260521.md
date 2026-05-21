# Phase 12 Slice 5 Re-Review - AgentMiMo

## Summary

- 当前 gate：Phase 12 Slice 5 re-review。
- Review scope：P12-S5-F1（required context slot 接线）与 P12-S5-F2（旧条件模板标记清理）的修复验证；新增 blocker 扫描。
- 结论：**PASS**。P12-S5-F1 与 P12-S5-F2 均已修复，无新增 blocker。

## Fix Verification

### P12-S5-F1: required context slots must be consumed by migrated fragments

**状态：已修复。**

- `base/agents.md` 第 19 行包含 `{{fins_default_subject}}` 占位符。
- `base/fact_rules.md` 第 4 行包含 `{{base_user}}` 占位符。
- 独立验证：14 个 manifest 中所有声明的 required context slot（`fins_default_subject`、`base_user`）均在直接装配 fragment 中找到对应 `{{slot_name}}` 占位符。
- `infer` 仅声明 `fins_default_subject`，不声明 `base_user`，符合迁移设计意图。
- 测试 `test_required_context_slots_are_consumed_by_migrated_fragments` 覆盖了 slot 占位符存在性与 `prepare_scene` 输出包含 slot 值两个断言。

### P12-S5-F2: remove legacy conditional prompt markers

**状态：已修复。**

- `base/tools.md` 中 `<when_tag>`、`</when_tag>`、`<when_tool>`、`</when_tool>` 标记已全部清除。
- `doc` 条件段与 `get_current_time` 工具条件段已删除；保留的 `fins`、`ingestion`、`web` 指引已被 migrated manifest 通过 tool tags 选择。
- 独立 `grep` 扫描 `dayu/config/prompts/` 下全部文件：无任何旧条件模板标记残留。
- 测试 `test_migrated_prompt_assets_exclude_legacy_conditional_markers` 覆盖全目录扫描。

## New Blocker Scan

| 检查项 | 结果 |
|---|---|
| prompt asset 完整性 | 通过。所有 manifest 引用的 fragment 存在且未逃逸 prompt root |
| 迁移测试覆盖 | 通过。30 passed，覆盖装配、slot 消费、旧标记清理、旧文件排除 |
| import boundary / typing | 通过。8 passed，pyright 0 errors |
| 分层架构边界 | 通过。修复仅涉及 config prompt assets 与迁移测试，未触及 runtime/host/engine 公共接口 |
| docs/control 状态 | 通过。implementation-control.md 已标记当前 gate 为 Slice 5 re-review |

**新增 blocker 数量：0。**

## Validation Run

| 检查项 | 结果 |
|---|---|
| `pytest tests/runtime/test_scene_assets_migration.py tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` | 30 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 8 passed |
| `python -m pyright dayu/runtime tests/runtime` | 0 errors, 0 warnings, 0 informations |
| 独立 slot 占位符验证脚本 | 14 manifest × all required slots = 全部 OK |
| `grep` 旧条件标记扫描 | 无残留 |

## Verdict

**PASS**。P12-S5-F1 已修复，P12-S5-F2 已修复，无新增 blocker。可进入下一 gate。
