# WU-TOOLS-01 Slice S6 Code Review Controller Adjudication

Gate: code-review adjudication
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Status: FIX REQUIRED

## 输入

- `docs/reviews/wu-tools-01-slice6-implementation-codex.md`
- `docs/reviews/wu-tools-01-slice6-code-review-mimo.md`
- `docs/reviews/wu-tools-01-slice6-code-review-ds.md`

## 裁决

MiMo 与 DS 均裁决 `PASS-WITH-EXTERNAL-BLOCKER`。S6 自身覆盖 combined discovery、ToolRuntime accept、Service assembly、current `ToolTruncateSpec`、Host accept barrier、input / response projection、ScenePrepare tags 和 Web serial policy，未修改生产代码。

Broad validation 中 13 个 Host failures 经 review 复核不由 S6 引入。其中 import-boundary 两项可以在 S6 allowed `tests/host/` 范围内做窄修复；其余 11 个 Host 行为失败不属于 S6 修复范围，保留为 external blockers / separate Host follow-up。

## Accepted Finding

### A1 - Import boundary allowlist / owner test sync

- `test_fetch_more_token_stays_inside_toolruntime_owner_modules` 未区分 `_legacy_adapter` 中 reserved-name 防御性 `fetch_more` 引用和业务 provider 暴露 `fetch_more`。
- `test_host_engine_imports_stay_on_allowed_boundary_modules` 未包含已接受的 `compaction_operation.py` Host -> Engine contracts 依赖边界。
- 裁决：accepted for narrow test fix。只更新 `tests/host/test_import_boundary.py` 与必要 `tests/README.md`；不得修改 Host production code。
- 修复要求：allowlist 必须精确到文件；business provider 仍不得暴露 `fetch_more`；OLD fetch-more projection token 必须继续被禁止。

## External Blockers

- 7 个 proactive compaction failures：`accepted compaction is missing proposal manifest ref`。
- 2 个 effective execution config failures：one-system-message envelope 后测试仍期望 raw system prompt。
- 2 个 wait / resume failures：测试仍期望旧 `"Accepted wait result fact:"` 文本。

这些 failures 不由 S6 引入，不在当前 fix gate 中修改。
