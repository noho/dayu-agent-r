# Phase 12.1 Slice 3 实施报告

## Gate 与范围

- Gate：Slice 3 implementation
- Slice：ScenePrepare Schema and Scene Asset Migration
- Worker：Codex implementation worker
- 停止条件：只完成本 handoff 的实现、测试、README 同步和 implementation artifact；未 commit、未 push、未开 PR，未进入其它 gate。

## Dirty Worktree 分类

- 前序 out-of-scope dirty，未接管、未修改、未 revert：
  - `README.md`
  - `utils/smoke_host_public_multiturn.py`
- 本 Slice 接管范围：
  - `dayu/runtime/scene_prepare.py`
  - `dayu/config/prompts/manifests/*.json`
  - `dayu/config/prompts/scenes/*.md`
  - `tests/runtime/test_scene_prepare.py`
  - `tests/runtime/test_scene_tool_selection.py`
  - `tests/runtime/test_scene_assets_migration.py`
  - `dayu/config/README.md`
  - `dayu/README.md`
  - `tests/README.md`
  - `docs/reviews/phase12-1-slice3-implementation-codex-20260521.md`

## 迁移前 Scene Manifest 审计

- 包内 manifest 均使用旧 model 字段：
  - `model.default_name`
  - `model.temperature_profile`
- 包内 manifest 均包含旧 scene 外语义：
  - 顶层 `runtime`
  - 顶层 `conversation`
- `prompt_mt` 存在：
  - `dayu/config/prompts/manifests/prompt_mt.json`
  - `dayu/config/prompts/scenes/prompt_mt.md`
- 处理方式：
  - 所有保留 scene 迁移为 `model.default_model_id` 与 `model.runner_option_hint_id`。
  - 删除顶层 `runtime` 与 `conversation`。
  - 删除 `prompt_mt` manifest 与 fragment，不提供兼容 reader 或兼容测试。

## Schema 迁移清单

- Scene manifest 顶层字段固定为白名单：
  - `schema_version`
  - `scene`
  - `version`
  - `description`
  - `capability_tags`
  - `extends`
  - `model`
  - `agent_policy`
  - `tool_selection`
  - `defaults`
  - `fragments`
  - `context_slots`
- 未知顶层字段 fail fast；旧 `conversation` / `runtime` 由未知字段路径失败。
- `model` 只允许 `default_model_id` 与 `runner_option_hint_id`。
- `PreparedSceneInputs` 删除旧 `runtime_hints` / `conversation_hint`，保留 `model_hints`，新增 `agent_policy_override`。
- `agent_policy` 是可选 typed override block，只允许白名单字段：
  - `max_iterations`
  - `continuation_max_attempts`
  - `allow_tool_calls`
  - `tool_execution_timeout_seconds`
  - `fallback_mode`
  - `fallback_prompt`
  - `continuation_prompt`
  - `max_consecutive_failed_tool_batches`
- `fallback_mode` 只接受 `force_answer` / `raise_error`。
- `tool_selection` 保持已有 `all` / `none` / `select` 的 names / tags 选择语义。
- `extends` 保持单继承；fragment path 仍做 root containment 校验。
- `context_slots` 继续由调用方传入 values 后渲染进 system messages；缺 required slot fail fast。
- ScenePrepare 未读取 ConfigLoader、ToolsDiscovery 或 workspace fallback。

## Dedicated Smoke Scene 说明

- 新增普通 scene asset：
  - `dayu/config/prompts/manifests/smoke_host_public_multiturn.json`
  - `dayu/config/prompts/scenes/smoke_host_public_multiturn.md`
- 该 scene 通过普通 manifest 表达 system prompt fragments、tool selection、model hint、typed `agent_policy` override 与 context slots。
- `ScenePrepare` 中没有为 smoke scene 写 special case。

## README 同步

- `dayu/config/README.md`：补充 scene manifest 顶层字段白名单、新 model hint 字段、typed `agent_policy` override 和旧字段删除说明。
- `dayu/README.md`：同步 `scene_prepare` runtime 概览，删除旧 runtime / conversation hint 表述。
- `tests/README.md`：同步 runtime scene prepare 测试覆盖事实。
- 根目录 `README.md` 是前序 dirty，本 Slice 未接管。

## 验证命令与结果

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q`
  - 结果：38 passed
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：10 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过

## 剩余风险与延后项

- 本 Slice 未接管 `utils/smoke_host_public_multiturn.py`，后续 Slice 5 仍需把 smoke 脚本接入 dedicated ordinary scene。
- `PreparedSceneInputs.model_hints` 现在允许为空；Service / composition root 需要在后续 assembly helper / smoke rewrite 中把空值映射到 execution profile baseline。
- 本 Slice 不修改 Host public contract、不修改 Engine loop、不实现 Service workflow。

## Fix Addendum: P12.1-S3-F1

- Gate：Slice 3 code review fix
- Source review artifacts：
  - `docs/reviews/phase12-1-slice3-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-1-slice3-code-review-ds-20260521.md`
  - `docs/reviews/phase12-1-slice3-code-review-controller-adjudication-20260521.md`
- Accepted finding：P12.1-S3-F1
- Fix status：已修复

### 改动

- `dayu/runtime/scene_prepare.py`：`_require_scene_id` 的非法格式分支改为抛 `ScenePrepareError`，并同步 docstring 的异常契约。
- `tests/runtime/test_scene_prepare.py`：补三条 focused tests，覆盖 request scene id、manifest `scene` 字段、`extends` parent id 非法格式均抛 `ScenePrepareError`。

### 验证命令与结果

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q`
  - 结果：41 passed
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：10 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过

### 文档决策与剩余风险

- README：本 fix 只修 runtime 内部异常类型一致性并补测试，不改变用户接口、测试运行方式或稳定架构说明，未同步 README。
- 剩余风险：未发现新增 residual risk；原 Slice 中 `utils/smoke_host_public_multiturn.py`、Service baseline 映射和 Host / Engine 相关延后项仍按原报告归属后续 Slice。
