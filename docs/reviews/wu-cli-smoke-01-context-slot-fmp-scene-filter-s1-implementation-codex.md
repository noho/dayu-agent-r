# WU-CLI-SMOKE-01 S1 Implementation Artifact

## Metadata

- Gate: implementation slice
- Work unit: WU-CLI-SMOKE-01 context slot / FMP / scene tool filtering follow-up
- Slice: S1
- Agent: AgentCodex
- Date: 2026-07-07
- Scope: ScenePrepare 条件块过滤、`base/tools.md` 暴露面拆分、相关 runtime / service 测试
- Commit policy: 用户要求不 commit、不 push、不创建 issue/PR；本 slice 仅保留 workspace changes

## Changed Files

- `dayu/runtime/scene_prepare.py`
- `dayu/config/prompts/base/tools.md`
- `tests/runtime/test_scene_prepare.py`
- `tests/runtime/test_scene_tool_selection.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_entrypoint_runtime_prompt_path.py`
- `tests/service/test_entrypoint_runtime_interactive_path.py`
- `docs/reviews/wu-cli-smoke-01-context-slot-fmp-scene-filter-s1-implementation-codex.md`

未修改 manifest。当前 packaged manifest 已满足 S1：`prompt` 只选择 `fins-read` / `web` / `utils`；`interactive` 与 `wechat` 选择 `fins-read` / `fins-download` / `fins-preprocess` / `web` / `utils`；upload 暴露面未扩大。

## Implemented Behavior

- `ScenePrepare.prepare()` 现在先根据 manifest `tool_selection` 与 `SceneToolCatalog` 计算实际 selected tool names，再基于这些工具的 catalog tags 聚合 selected tags。
- 每个 fragment 在 placeholder 替换前执行条件块过滤：
  - `<when_tool NAME>...</when_tool>` 仅在 `NAME` 属于实际 selected tool names 时保留 body。
  - `<when_tag TAG>...</when_tag>` 仅在 `TAG` 属于实际 selected tools 的 catalog tags 时保留 body。
  - `mode=all` 使用 catalog 全量工具名；`mode=none` 使用空集合；`mode=select` 使用既有白名单计算结果。
  - marker 不会进入 prepared `system_messages` 或 `system_prompt`。
  - 未闭合、错配、嵌套、空名/多参数等 malformed marker 均 fail closed，抛 `ScenePrepareError`。
- `base/tools.md` 删除 broad `<when_tag fins>`，改为：
  - 财报 read-only 指引：`<when_tag fins-read>`。
  - 下载长事务指引：`<when_tool start_fins_download>`。
  - 预处理长事务指引：`<when_tool start_fins_preprocess>`。
  - 未新增 upload 指引，未扩大 upload scene selection。
- prompt prepared output 包含 read-only Fins 指引与 `get_current_time` 指引，不包含 download / preprocess / upload 指引。
- interactive / wechat prepared output 包含 download / preprocess 与 `get_current_time` 指引，不包含 upload 指引。

## Tests And Validation

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py`
  - Result: 58 passed
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_prompt_path.py tests/service/test_entrypoint_runtime_interactive_path.py`
  - Result: 6 passed
  - Note: 3 third-party `edgar` deprecation warnings, unrelated to this slice.
- `source .venv/bin/activate && pyright`
  - Result: 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - Result: passed

## README Decision

- `dayu/config/README.md`: checked because `dayu/config/` changed. No update needed; existing docs already state packaged scenes use narrow Fins tags and do not select upload through broad `fins`.
- `tests/README.md`: checked because `tests/` changed. No update needed; current runtime/service test layer descriptions already cover scene prepare, scene asset migration, and Service assembly tests.

## Deviations From Plan

- No production manifest changes were needed. S1 state was already correct in `prompt.json`, `interactive.json`, and `wechat.json`.
- Long-transaction guidance uses precise `<when_tool start_fins_download>` and `<when_tool start_fins_preprocess>` blocks instead of `<when_tag ingestion>`, because current tools do not carry an `ingestion` tag. This follows the accepted plan's lower-risk option.
- `tests/service/test_entrypoint_runtime_interactive_path.py` corrected an old assertion that interactive required `fins_default_subject`. Current manifest and accepted plan say interactive/wechat do not need that slot; the fail-closed test now verifies missing `base_user`.

## Residual Risks / Manual Validation

- Real LLM prompt inspection is not run in this slice; covered by prepared prompt assertions and later smoke validation.
- Conditional blocks intentionally do not support nesting; nested markers are classified as malformed and fail closed.
- Upload remains available as a discovered tool in the broader system but is not selected by current non-upload scenes. Any future upload exposure needs separate product/security裁决.
- S2 remains responsible for FMP resolver and Service context slot semantics; this slice did not change those paths.
