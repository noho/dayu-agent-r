# Phase 12 Slice 4 Follow-up Re-review — AgentDS

## Scope

- Mode: role-scoped follow-up re-review
- Source finding: `docs/reviews/phase12-slice4-followup-controller-finding-20260521.md`
- Prior implementation artifact: `docs/reviews/phase12-slice4-implementation-codex-20260521.md`
- Design source: `docs/host/design.md`
- Plan source: `docs/host/phase12-runtime-assembly-plan.md`
- Reviewed files:
  - `dayu/runtime/scene_prepare.py`
  - `tests/runtime/test_scene_prepare.py`
- Verification boundary: ScenePrepare only; Host public interface、RunnerCallOptions mapping、allowed_names 不在本次 scope

## Fix Expectation Checklist

| # | Expectation | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `SceneModelHints` 有 typed optional `temperature_profile_id` 字段 | PASS | `scene_prepare.py:184` — `temperature_profile_id: str | None`，`__post_init__` 校验非 None 时非空 |
| 2 | `_parse_model_hints` 读取 `model.temperature_profile` | PASS | `scene_prepare.py:703` — `_optional_str_field(record, field_name="temperature_profile", ...)` |
| 3 | `PreparedSceneInputs.model_hints` 保留该值 | PASS | `scene_prepare.py:325` 声明 `model_hints: SceneModelHints`；`:461` 传入 `model_hints=resolved.model_hints` |
| 4 | content digest 对 `temperature_profile` 变化敏感 | PASS | `scene_prepare.py:1103` digest 覆盖 `manifest.raw`（含完整 model 字段）；test at `test_scene_prepare.py:271` 验证仅改 `temperature_profile` 时 digest 变化 |
| 5 | `temperature_profile_id` 有 focused test | PASS | `test_scene_prepare.py:251` — `test_model_temperature_profile_is_preserved`；`:271` — `test_content_digest_changes_when_temperature_profile_changes` |
| 6 | 未恢复 `allowed_names` 到 runtime output | PASS | `grep allowed_names scene_prepare.py` → 无匹配 |
| 7 | 未在 ScenePrepare 中映射 `RunnerCallOptions` | PASS | `RunnerCallOptions` 仅在 docstring 出现（`:180`），标明为 Service 职责；无代码引用 |
| 8 | 未修改 Host public interface | PASS | `scene_prepare.py` 无 `dayu.host` import |

## Findings

### 未发现实质性问题

所有 8 项 fix expectation 均通过。`SceneModelHints.temperature_profile_id` 已完整走通 **manifest JSON → `_parse_model_hints` → `_SceneManifest.model_hints` → `_ResolvedScene.model_hints` → `PreparedSceneInputs.model_hints`** 链路。content digest 通过 `manifest.raw` inclusion 覆盖 temperature_profile 变化，有独立 focused test 证明。

## Verification Commands

```bash
source .venv/bin/activate
pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q
# → 26 passed

source .venv/bin/activate
pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
# → 8 passed

source .venv/bin/activate
python -m pyright dayu/runtime/scene_prepare.py tests/runtime/test_scene_prepare.py
# → 0 errors, 0 warnings, 0 informations
```

## Verdict

**PASS** — Controller finding 已收口，无 new blocker。

## Open Questions

无

## Residual Risk

- `temperature_profile_id` 到 `execution_profiles.runner_options_profiles` 的映射由 Service / composition root 负责；该映射不属于 ScenePrepare scope，未经本 review 覆盖。
- 旧 `dayu-agent` scene asset migration（Slice 5）仍待实施；迁移 manifest 需要携带 `model.temperature_profile` 才能通过 `_parse_model_hints` 校验并被 digest 覆盖。
