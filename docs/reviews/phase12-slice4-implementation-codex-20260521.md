# Phase 12 Slice 4 Implementation - AgentCodex

## Gate

- Current gate: Phase 12 Slice 4 implementation
- Work unit: ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Assigned scope: `dayu.runtime.ScenePrepare` typed manifest assembly helper
- Design source: `docs/host/design.md`
- Plan source: `docs/host/phase12-runtime-assembly-plan.md`

## 变更摘要

- 新增 `dayu.runtime.scene_prepare`：
  - 定义 `ScenePrepareRequest`、`PreparedSceneInputs`、`SceneToolCatalog`、`SceneToolInfo`、scene-specific `SceneSourceRef` / `SceneSourceKind`、model / runtime / conversation hints 与工具选择结果类型。
  - 显式读取 `scene_manifest_root/<scene_id>.json`，不猜 workspace 路径，不读取 ConfigLoader。
  - 校验第一版 scene manifest schema：`schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`runtime`、`conversation`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
  - 支持单继承；拒绝多继承、循环继承、父不存在、重复 fragment id / order；子 scene 只能追加 fragments；context slots 父优先去重；`runtime` / `conversation` / `tool_selection` 可由子显式覆盖；concrete scene 必须显式声明 `model`。
  - 从显式 `prompt_asset_root` 读取直接引用的 fragments，使用 `Path.resolve()` 后做 containment 校验，符号链接解析后逃逸 root 会失败。
  - 只支持 `value_type="string"` 的 context slots，执行确定性 `{{slot_name}}` 文本替换；缺 required slot、未知 placeholder、非字符串 slot value、残留 placeholder 均 fail fast。
  - 实现 `tool_selection` 的 `all` / `none` / `select` 语义；`select` 下显式 name 与 tag 命中结果取并集，未知 name 失败，tag 空匹配默认失败，`allow_empty=true` 时允许空选择。
  - 输出 `system_messages`、工具选择结果、model / runtime / conversation hints、fragment refs、scene-specific source refs、content digest 与 capability tags；digest 覆盖 manifest、fragment 内容、context slot values 与可用工具目录。
- 更新 `dayu.runtime.__init__` 模块说明，记录 `scene_prepare` 为层中立 runtime 能力，包根不 re-export。
- 新增 runtime focused tests：
  - `tests/runtime/test_scene_prepare.py`
  - `tests/runtime/test_scene_tool_selection.py`
- 更新 `tests/runtime/test_import_boundary.py`，确认 import boundary 扫描覆盖 `scene_prepare.py`。
- 按触发规则同步：
  - `dayu/README.md`
  - `dayu/config/README.md`
  - `tests/README.md`

## 架构边界

- `ScenePrepare` 只依赖标准库与 `dayu.contracts.ToolBundle` / `JsonValue`，未 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。
- 未修改 Host 公开接口、`SubmitFollowupRequest` 字段或 `open_host` options。
- 未读取 Fins storage，未访问财报仓储，未实现 workflow、Skill orchestration、parser、artifact store、replay / retry / stop policy 或 checkpoint / resume。
- 未迁移旧 `dayu-agent` scene assets；该事项仍属于 Slice 5。

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  - 21 passed
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 8 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

## README 同步

- `dayu/README.md`：补充 `scene_prepare` 已实现的 runtime 层中立职责与扩展入口。
- `dayu/config/README.md`：补充 scene manifest 第一版字段、ScenePrepare 输入输出与非 workflow 边界。
- `tests/README.md`：补充 runtime scene prepare 测试覆盖范围。

## 未覆盖风险

- 未覆盖旧项目真实 scene asset 迁移；按计划归 Phase 12 Slice 5。
- 未覆盖 Service 将 `PreparedSceneInputs` 映射到 `open_host` construction-time inputs 与 per-run request inputs；该映射不属于本 slice。
- 未覆盖真实财报工具目录；本 slice 只验证 `SceneToolCatalog` 的层中立 name / tags 选择语义。

## 完成状态

Slice 4 implementation 已完成，未进入 code review、commit、push、PR 或其它 gate。

## Fix Addendum

### Gate

- Current gate: Phase 12 Slice 4 narrow fix
- Source adjudication: `docs/reviews/phase12-slice4-code-review-controller-adjudication-20260521.md`
- Fix scope: only `tests/runtime/test_scene_prepare.py` and this implementation artifact
- Non-goals preserved:
  - 未修改 `PreparedSceneInputs` / `SceneFragmentRef` metadata shape。
  - 未修改 duplicate fragment order 错误消息。
  - 未迁移旧 `dayu-agent` assets。
  - 未修改 production `scene_prepare` 实现。

### Findings 收口

- P12-S4-F1 optional missing fragment skip branch: 已新增 `test_optional_missing_fragment_is_skipped`，覆盖 manifest 声明 `required=false` fragment 但文件不存在时装配成功，且 `system_messages` 与 `fragment_refs` 均不包含该 fragment。
- P12-S4-F2 symlink escape containment: 已新增 `test_fragment_symlink_escape_prompt_asset_root_fails`，覆盖 prompt root 内 fragment path 指向符号链接且链接目标在 `prompt_asset_root` 外时抛出 `ScenePrepareError`，错误消息匹配 `escapes root`。
- P12-S4-F3 inherited duplicate context slot parent-priority: 已新增 `test_inherited_duplicate_context_slot_keeps_parent_required_flag`，覆盖父子 manifest 声明同名 context slot 且 `required` 值不同，缺 slot 时仍按父 `required=true` 失败，证明子声明没有覆盖父 slot 语义。

### Fix 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q`
  - 24 passed
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 8 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - clean

### 残余风险

- DS finding 2 duplicate fragment order 错误消息增强按 controller 裁决 deferred，本次未处理。
- 旧 `dayu-agent` scene asset migration 仍归 Slice 5，本次未处理。
