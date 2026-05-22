# Phase 12.1 Slice 3 Code Review

## Verdict: PASS

## Scope

- Mode: current changes (Phase 12.1 Slice 3)
- Branch: docs/phase12-design-discussion
- Base: main
- Output file: docs/reviews/phase12-1-slice3-code-review-ds-20260521.md
- Included scope:
  - `dayu/runtime/scene_prepare.py` — ScenePrepare 装配器
  - `dayu/config/prompts/manifests/*.json` — 14 个 scene manifest
  - `dayu/config/prompts/scenes/*.md` — 14 个 scene prompt fragment
  - `tests/runtime/test_scene_prepare.py` — 23 个 scene prepare 测试
  - `tests/runtime/test_scene_tool_selection.py` — 8 个工具选择测试
  - `tests/runtime/test_scene_assets_migration.py` — 7 个资产迁移验证测试
  - `tests/runtime/test_import_boundary.py` — import 边界测试
  - `tests/runtime/test_weak_typing_guard.py` — 弱类型守卫测试
  - `dayu/config/README.md` — 配置说明
  - `dayu/README.md` — 开发手册总览
  - `tests/README.md` — 测试手册
- Excluded scope:
  - `README.md` — 前序 dirty，本 Slice 未接管
  - `utils/smoke_host_public_multiturn.py` — 前序 dirty，本 Slice 未接管
  - 前序 slice review artifact 中的 trailing whitespace（非代码文件）
- Parallel review coverage: 无（单 reviewer 覆盖全部 scope）

## 逐条 Review Criteria 验证

### Criteria 1: Scene schema matches design/plan
**通过。** 全部 14 个 manifest 顶层字段均落在白名单内；无 `conversation`/`runtime` 字段；`model` 仅含 `default_model_id` 与 `runner_option_hint_id`；`prompt` scene 保留；`prompt_mt` manifest 与 fragment 均已删除。

直接证据：
- `dayu/runtime/scene_prepare.py:34-49` — `_ALLOWED_MANIFEST_FIELDS` 白名单
- `dayu/runtime/scene_prepare.py:50-52` — `_ALLOWED_MODEL_FIELDS` 白名单
- 脚本验证 14 个 manifest 均无越界字段
- `tests/runtime/test_scene_prepare.py:491-518` — `test_legacy_conversation_and_runtime_fields_fail_fast` 与 `test_legacy_model_field_names_fail_fast`

### Criteria 2: PreparedSceneInputs output
**通过。** `PreparedSceneInputs` 不包含 `runtime_hints`/`conversation_hint`；包含 `model_hints: SceneModelHints | None` 与 `agent_policy_override: SceneAgentPolicyOverride | None`。

直接证据：
- `dayu/runtime/scene_prepare.py:362-383` — `PreparedSceneInputs` dataclass 字段列表
- `grep runtime_hints\|conversation_hint scene_prepare.py` 无匹配
- 运行时检查确认 8 个字段均符合设计

### Criteria 3: agent_policy override
**通过。** `agent_policy` 为可选顶层 typed block，仅允许 8 个白名单字段；`fallback_mode` 为闭合枚举 `force_answer`/`raise_error`；未知字段与非法 fallback_mode 均 fail fast。

直接证据：
- `dayu/runtime/scene_prepare.py:53-64` — `_ALLOWED_AGENT_POLICY_FIELDS`
- `dayu/runtime/scene_prepare.py:77-79` — `_AGENT_FALLBACK_MODES`
- `tests/runtime/test_scene_prepare.py:555-585` — `test_agent_policy_unknown_field_fails_fast` 与 `test_agent_policy_fallback_mode_is_closed_enum`

### Criteria 4: ScenePrepare boundary clean
**通过。** `scene_prepare.py` 不 import `ConfigLoader`、`ToolsDiscovery`、`Host`、`Engine`、`Service`、`UI`、`Fins`，不做 workspace fallback。

直接证据：
- `grep ConfigLoader\|ToolsDiscovery\|from dayu\.\(engine\|host\|service\|ui\|fins\) scene_prepare.py` 仅在 docstring 中出现
- `tests/runtime/test_import_boundary.py` 全部通过

### Criteria 5: context_slots
**通过。** 确定性渲染进 system messages；required slot 缺失 fail fast；未知 placeholder fail fast；未解析 placeholder fail fast。

直接证据：
- `tests/runtime/test_scene_prepare.py:299-373` — `test_required_context_slot_missing_fails_fast`、`test_unknown_placeholder_fails_fast`、`test_unresolved_placeholder_fails_fast`
- `dayu/runtime/scene_prepare.py:1033-1068` — `_render_fragment_content`

### Criteria 6: tool_selection
**通过。** `all`/`none`/`select` 语义正确；names/tags 仅从 `SceneToolCatalog` 选取子集；未知名 fail fast；tag 无匹配 fail fast；`allow_empty` 放行。

直接证据：
- `tests/runtime/test_scene_tool_selection.py` 8 个测试全部通过
- `dayu/runtime/scene_prepare.py:1110-1143` — `_select_tools`

### Criteria 7: Scene assets migration
**通过。** 全部包内 manifest 可被新 schema 加载装配；`smoke_host_public_multiturn` 为普通资产，`ScenePrepare` 中无 special case；`prompt_mt` 已删除。

直接证据：
- `tests/runtime/test_scene_assets_migration.py` 7 个测试全部通过
- `grep smoke_host_public_multiturn scene_prepare.py` 无匹配
- `prompt_mt.json` 与 `prompt_mt.md` 已确认删除

### Criteria 8: Tests and README
**通过。** 未引入兼容 reader/wrapper/test；README 反映当前代码事实。

### Criteria 9: Project rules
**通过。** pyright 0 errors；弱类型守卫通过；公开函数均有中文 docstring；无 `Any`/`object` 注解。

## Findings

### 1-未修复-低-`_require_scene_id` 异常类型不一致

- **入口/函数**: `_require_scene_id`
- **文件(行号)**: `dayu/runtime/scene_prepare.py:1751`
- **输入场景**: scene_id 包含非法字符（如空格、中文等），不匹配 `^[A-Za-z][A-Za-z0-9_.-]*$`
- **实际分支**: `_SCENE_ID_PATTERN.fullmatch(text) is None` 分支（行 1750）
- **预期行为**: 与模块内其他所有 validator 一致，抛出 `ScenePrepareError`
- **实际行为**: 抛出 `ValueError`
- **直接证据**: `dayu/runtime/scene_prepare.py:1751` — `raise ValueError(...)`；对比同模块的 `_require_context_slot_name` 行 1766 抛出 `ScenePrepareError`
- **影响**: 调用方若只 catch `ScenePrepareError` 会漏掉此异常。影响三条调用路径：
  1. `ScenePrepareRequest.__post_init__`（行 225）— 非法 scene_id 的请求构造失败时抛 `ValueError`
  2. `_parse_manifest`（行 702）— manifest 内 `scene` 字段非法格式时抛 `ValueError`
  3. `_parse_extends`（行 738）— extends 内 parent id 非法格式时抛 `ValueError`
  注意 `ScenePrepareError` 继承自 `ValueError`（行 88），所以 catch `ValueError` 仍可捕获，但 catch `ScenePrepareError` 不可。
- **建议改法和验证点**: 将行 1751 的 `raise ValueError` 改为 `raise ScenePrepareError`；为三条路径各补一个非法 scene_id 格式的 fail-fast 测试；验证 pyright 与已有测试通过。
- **修复风险（低）**: 仅改异常类型，不改变控制流
- **严重程度（低）**: 实际触发概率极低（scene_id 通常在配置/代码中写死），且 `ValueError` 是 `ScenePrepareError` 的父类，大多数通用异常处理不受影响

### 2-已确认无问题-`_dedupe_context_slots` 父优先语义

本 reviewer 审核了 `test_inherited_duplicate_context_slot_keeps_parent_required_flag`（行 729-756），确认该行为符合设计：子 manifest 不能通过重复声明同名 slot 来放宽父级 required 约束。`_dedupe_context_slots`（行 1406-1420）采用父优先去重，语义正确。

### 3-已确认无问题-`smoke_host_public_multiturn` 为普通资产

- `ScenePrepare` 中无 `smoke_host_public_multiturn` special case（grep 确认）
- manifest 使用标准 schema v1，与其他 scene asset 无区别
- fragment 路径为标准 `scenes/smoke_host_public_multiturn.md`

## Open Questions

1. **子 manifest 是否应该能够放宽父级 required slot？** 当前 `_dedupe_context_slots` 父优先去重意味着子不能将父级 required slot 改为 optional。如果未来有 scene 需要这种语义，需要在设计文档中明确。当前所有 manifest 均为平铺（无继承），不影响现有功能。

## Residual Risk

1. **ScenePrepare 不读取 ConfigLoader/ToolsDiscovery** — 已通过 import boundary 测试验证。后续 Slice 4/5 在 Service/composition 边界组装时需确保不把这些依赖回灌到 `dayu.runtime`。
2. **smoke scene 尚未被实际 smoke 脚本消费** — 已创建 `smoke_host_public_multiturn.json` 与对应 fragment，但 `utils/smoke_host_public_multiturn.py` 是前序 dirty 文件，本 Slice 未接管。Sliver 5 需要确保脚本通过普通装配路径使用该 scene。
3. **`test_required_context_slots_are_consumed_by_migrated_fragments` 只检查直接引用的 fragment** — 对平铺 manifest（无继承）足够，但对多继承 scene，父级 required slot 可能只在父级 fragment 中引用。当前所有 manifest 均为平铺，无实质风险。
4. **`Smoke_host_public_multiturn` scene 缺少 `agent_policy` 完整覆盖** — 其 `agent_policy` 仅设置 `allow_tool_calls: true`，其他字段依赖 execution profile baseline。这是有意设计（scene 只 override 需要不同于 baseline 的字段），但容易遗漏必需覆盖项。后续 Slice 5 smoke 验证时会自然暴露此类缺口。

## Tests Run and Results

```
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q
→ 38 passed in 0.26s

pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
→ 10 passed in 0.76s

python -m pyright dayu/runtime tests/runtime
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ 通过（trailing whitespace 仅存在于前序 doc 文件，非代码文件）
```
