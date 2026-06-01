# WU-CTX-02 + WU-CTX-03 Slice A Fix — Codex

- Gate: WU-CTX-02 + WU-CTX-03 Slice A fix
- Source review artifact: `docs/reviews/wu-ctx-02-03-code-review-sliceA-ds-20260601.md`
- Controller adjudication: `docs/reviews/wu-ctx-02-03-code-controller-adjudication-sliceA-20260601.md`
- Accepted finding ids: `DS-F1`
- Fix artifact: `docs/reviews/wu-ctx-02-03-fix-sliceA-codex-20260601.md`

## Scope

本次 fix 只处理 controller accepted finding `DS-F1`。未新增 production code，未修改 schema，未修改 Service request shape，未进入 review、commit、push 或 PR。

## Per-Finding Fix Status

| Finding | 状态 | 修复说明 | 标题状态更新 |
|---|---|---|---|
| `DS-F1` workspace overlay fixture 使用旧默认值 `3` | 已修复 | 已将 `_write_execution_profile_overlay` helper 中 workspace overlay fixture 的 `max_compaction_attempts_per_operation` 从 `3` 改为 `7`，该值显著不同于 packaged default `5`，可表达 workspace override 与 packaged default 无关。 | Source review artifact 不在本 handoff 允许写文件内，未直接回写；本 artifact 记录为 `DS-F1-已修复`。 |

## Changed Files

- `tests/service/test_host_assembly.py`
- `docs/reviews/wu-ctx-02-03-fix-sliceA-codex-20260601.md`

## Validation

| 命令 | 结果 |
|---|---|
| `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q` | 通过，`74 passed in 0.37s` |
| `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/` | 通过，`0 errors, 0 warnings, 0 informations` |

## Docs Decision

本次只修改测试 fixture 的覆盖值，不改变测试分层、运行方式、维护规则、用户入口或架构说明；按 README 职责边界检查，无需更新 README。

## New Risks / Open Questions

- 新风险：无。
- Open questions：无。

## Residual Risk Classification

| 风险 | 分类 | 说明 |
|---|---|---|
| Workspace overlay fixture 旧默认值残留造成误读 | fixed in current slice before re-review | `max_compaction_attempts_per_operation` 已改为 `7`，不再残留旧 packaged default `3`，且明显不同于当前 packaged default `5`。 |

## Completion Status

Fix 完成，验证通过。停止于 fix artifact 输出点，等待 focused re-review。
