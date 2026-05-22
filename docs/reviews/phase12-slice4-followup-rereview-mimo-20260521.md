# Phase 12 Slice 4 Follow-up Re-review — AgentMiMo

## Scope

- Mode: follow-up fix re-review
- Branch: `docs/phase12-design-discussion`
- Finding source: `docs/reviews/phase12-slice4-followup-controller-finding-20260521.md`
- Fix scope: `SceneModelHints` 保留 `model.temperature_profile`
- Output file: `docs/reviews/phase12-slice4-followup-rereview-mimo-20260521.md`

## Fix 预期逐项验证

### 1. SceneModelHints 有 typed optional temperature profile 字段

**PASS**

`dayu/runtime/scene_prepare.py:174-198`：`SceneModelHints` 新增 `temperature_profile_id: str | None`，`__post_init__` 校验非空非 None 时 `_require_non_empty_text`。类型签名与校验完整。

### 2. _parse_model_hints 读取 model.temperature_profile

**PASS**

`dayu/runtime/scene_prepare.py:685-708`：`_parse_model_hints` 通过 `_optional_str_field(record, field_name="temperature_profile", context=...)` 读取 manifest `model.temperature_profile`，映射到 `SceneModelHints.temperature_profile_id`。当字段不存在或为 `None` 时返回 `None`，存在时校验非空字符串。

### 3. PreparedSceneInputs.model_hints 保留该值

**PASS**

`dayu/runtime/scene_prepare.py:461`：`PreparedSceneInputs(model_hints=resolved.model_hints, ...)` 直接传递继承解析后的 `SceneModelHints`，包含 `temperature_profile_id`。

### 4. content digest 对 temperature_profile 变化敏感，有 focused test

**PASS**

- digest 计算 `dayu/runtime/scene_prepare.py:1098-1122`：`_prepared_scene_digest` 的 payload 包含 `"manifests": [manifest.raw for manifest in resolved.manifests]`，raw manifest JSON 包含 `model.temperature_profile`，因此该字段变化会改变 digest。
- focused test `tests/runtime/test_scene_prepare.py:271-303`：`test_content_digest_changes_when_temperature_profile_changes` 先用 `"analytical"` profile 装配，再用 `"creative"` profile 装配，断言 `first.content_digest != second.content_digest`。同时验证两个不同 profile id 均能正确读取。

### 5. 非目标确认

- **未恢复 allowed_names 到 runtime output**：grep `allowed_names` 在 `scene_prepare.py` 中 0 命中。PASS
- **未在 ScenePrepare 中映射 RunnerCallOptions**：`RunnerCallOptions` 仅出现在 docstring 说明映射归属（line 180），无 import、无映射逻辑。PASS
- **未修改 Host public interface**：`scene_prepare.py` 不 import `dayu.host`，不修改 `SubmitFollowupRequest`、`OpenHostOptions` 或 Host public exports。PASS

## 测试验证

- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py -q` — 26 passed
- `pyright dayu/runtime/scene_prepare.py` — 0 errors, 0 warnings, 0 informations

## Findings

未发现实质性问题。

## Open Questions

- 无

## Residual Risk

- 旧 `dayu-agent` scene asset migration 仍归 Slice 5，本次不涉及。
- Service 将 `model_hints.temperature_profile_id` 映射到 execution profile 的 `runner_options_profile_id` 不属于本 follow-up fix，由后续 Service / composition root 负责。

## Verdict

**PASS**

controller-discovered follow-up fix 已完整收口。所有五项预期均已满足，无 new blocker。
