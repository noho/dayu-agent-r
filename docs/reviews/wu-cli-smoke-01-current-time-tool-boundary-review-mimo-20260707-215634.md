# Code Review

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-current-time-tool-boundary-review-mimo-20260707-215634.md`
- Included scope: `current_time` context slot 与 `get_current_time` 工具的语义边界修正，覆盖 prompt/interactive/wechat manifest、scene prompt、tools.md、provider.py、scene_context.py、README 与测试
- Excluded scope: 与 current_time / get_current_time 无关的其它改动（thinking renderer、activity renderer、arg parsing 重构等）

## Findings

未发现实质性问题。

### 逐项审查结果

#### 1. prompt manifest 是否不再选择 get_current_time；interactive / wechat 是否仍选择

**prompt.json**（`dayu/config/prompts/manifests/prompt.json:20-23`）：
```json
"tool_tags_any": ["fins-read", "web"]
```
无 `"utils"` tag。`get_current_time` 工具 tags 为 `("utils", "time")`，不命中。✅

**interactive.json**（`dayu/config/prompts/manifests/interactive.json:20-26`）：
```json
"tool_tags_any": ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]
```
有 `"utils"` tag。✅

**wechat.json**（`dayu/config/prompts/manifests/wechat.json:20-26`）：
```json
"tool_tags_any": ["fins-read", "fins-download", "fins-preprocess", "web", "utils"]
```
有 `"utils"` tag。✅

其它 scene（audit、confirm、decision、fix、infer、overview、regenerate、repair、write）均只有 `["fins-read", "web"]`，不选 `get_current_time`。✅

`conversation_compaction` 使用 `mode: "none"`，无任何工具。✅

#### 2. current_time 渲染文本是否纯 LLM-facing

`dayu/service/scene_context.py:90-96`：
```
# 当前时间
现在是 2026年7月7日 23:08（Asia/Shanghai，星期二）。
这是对话开始时的当前时间；回答"现在/今天/当前时间"默认使用它；该时间不会自动更新。
```

- 无 Host、run input、context slot、scene、tool selection 等内部术语。✅
- 明确说明"对话开始时"、"不会自动更新"、"默认使用它"。✅

#### 3. get_current_time tool description 和 tools.md 指引

**provider.py tool description**（`dayu/tools/utils/provider.py:100-105`）：
```
获取调用这一刻的当前时间。只有用户明确要求获取此刻最新时间，或要求在等待、查询、
下载、上传、处理等动作完成后再确认时间时才调用。普通"现在/今天/当前时间"问题如果
不需要重新确认，就使用已给出的当前时间，不调用本工具。仅支持 timezone=Asia/Shanghai；
返回 time、timezone、weekday、iso。
```
- 明确调用边界：明确要求此刻最新时间 / 等待/查询/下载/上传/处理后确认时间。✅
- 明确禁止：普通时间问题不调用。✅
- 无内部术语。✅

**tools.md**（`dayu/config/prompts/base/tools.md:90-98`）：
`<when_tool get_current_time>` 条件块内容与 tool description 一致。只在 scene 选中 `get_current_time` 工具时才渲染。✅

#### 4. 是否破坏 fins_default_subject、长事务工具选择、when_tool 过滤或其它 scene

- **fins_default_subject**：prompt manifest 仍声明 `fins_default_subject` 为 required context slot（`prompt.json:65-69`）。prompt scene prompt 仍渲染 `{{fins_default_subject}}`。prompt command 通过 `build_entrypoint_context_slot_values()` 生成该 slot。✅
- **长事务工具**：interactive/wechat 通过 `fins-download` / `fins-preprocess` tag 选择 `start_fins_download` / `start_fins_preprocess`。prompt 不选这两个 tag。✅
- **when_tool 过滤**：`scene_prepare.py` 的 `_filter_condition_blocks()` 基于实际 selected tools 和 tags 过滤。prompt 不选 `get_current_time`，所以 `<when_tool get_current_time>` 块被删除。interactive/wechat 选中，所以保留。✅
- **其它 scene**：所有 scene 都声明 `current_time` context slot（除 conversation_compaction），并在 scene prompt 末尾渲染 `{{current_time}}`。✅

#### 5. 测试覆盖

- `test_scene_assets_migration.py:test_get_current_time_tool_is_selected_only_for_interactive_wechat_scenes` — 覆盖 prompt 不选、interactive/wechat 仍选。✅
- `test_scene_assets_migration.py:test_current_time_rendering_explains_static_boundary_without_internal_terms` — 覆盖文本无内部术语。✅
- `test_scene_assets_migration.py:test_get_current_time_tool_description_explains_refresh_boundary` — 覆盖 tool description 调用边界。✅
- `test_scene_assets_migration.py:test_prompt_prepared_output_filters_long_transaction_guidance` — 覆盖 prompt scene 不暴露 download/preprocess/upload 指引。✅
- `test_scene_assets_migration.py:test_interactive_and_wechat_prepared_output_keep_download_preprocess_guidance` — 覆盖 interactive/wechat 保留 download/preprocess/get_current_time 指引。✅
- `test_scene_prepare.py:test_condition_blocks_use_actual_selected_tools_and_tags` — 覆盖 when_tool/when_tag 条件过滤。✅
- `test_utils_tools_provider.py` — 覆盖工具声明、时间返回、非法时区拒绝。✅
- `test_entrypoint_runtime.py:test_scene_context_formats_subject_and_current_time` — 覆盖 slot 文本生成。✅
- `test_prompt_command.py:test_prompt_command_outputs_fast_live_terminal_and_converts_requests` — 覆盖 prompt command 生成 `current_time` 和 `fins_default_subject` slot。✅
- `test_interactive_command.py:test_interactive_label_reuses_host_slot_and_fills_context_slots` — 覆盖 interactive 只生成 `current_time` slot。✅

#### 6. README 更新

- `dayu/config/README.md`：新增 utils-tools provider 说明、tool_selection tag-only 迁移说明、`current_time` context slot 语义说明、prompt/interactive/wechat 工具暴露差异说明。在 config README 职责范围内。✅
- `tests/README.md`：更新测试覆盖描述。在 tests README 职责范围内。✅

## Open Questions

无。

## Residual Risk

- `base_user` slot 已从所有 manifest 和代码中移除。如果有外部调用方或 workspace manifest 仍依赖该 slot，会在 ScenePrepare 阶段因 unknown slot 被拒绝。但按全新 schema 设计原则，这是预期行为。
