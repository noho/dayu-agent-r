# Gateflow Implementation Artifact: Host Public Conversation Memory Scenario Smoke S2

## Gate 与范围

- 当前 gate：implementation。
- 角色：implementation worker，不是 controller。
- Work unit：Host public conversation memory scenario smoke。
- Slice：S2 scene assets。
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`。
- Accepted S1 commits：`2c98662`、`b984460`。
- 分支：`feat/phase-12-5-conversation-memory-optimize`。
- 非目标：不启动 gateflow controller，不提交，不推送，不开 PR，不修改最小 smoke 文件，不提前进入 S3/S4。

## 动机与方案判断

S2 动机成立。新增脚本需要独立 scene id 与 prompt asset，不能复用或改写现有最小 smoke scene，否则会改变已接受的 S1 行为边界。当前 slice 的最佳做法是只新增独立 manifest / scene prompt，并把声明了 `agent_policy.max_iterations` 的 scene 同步进迁移测试 inventory。

## Changed Files

- `dayu/config/prompts/manifests/smoke_host_public_conversation_memory_scenarios.json`
  - 新增 scene id `smoke_host_public_conversation_memory_scenarios`。
  - 复用 public smoke manifest 风格：`manual-smoke` tag、`allow_tool_calls=true`、`max_iterations=32`、`runner_option_hint_id=interactive`。
  - 引用 `base/agents.md`、`base/fact_rules.md` 和新 scene prompt。
- `dayu/config/prompts/scenes/smoke_host_public_conversation_memory_scenarios.md`
  - 新增短 scene prompt。
  - 支持 `DAYU_MEM_ASSERT` 或同类核对行，要求按用户给定字段原样输出。
  - 明确不披露 smoke 运行、装配、上下文压力或 runtime 诊断，不包含测试答案、公司数值或 marker。
- `tests/runtime/test_scene_assets_migration.py`
  - 将 `smoke_host_public_conversation_memory_scenarios` 加入 `_OLD_SCENE_MAX_ITERATIONS`，期望值 `32`。

## Implemented Plan Items

- 新增独立 scene asset，不修改 `smoke_host_public_conversation_memory` 最小 smoke asset。
- Manifest 字段按 approved S2 决策实现：
  - `scene`: `smoke_host_public_conversation_memory_scenarios`
  - `capability_tags`: `["smoke_host_public_conversation_memory_scenarios"]`
  - `model.default_model_id`: `mimo-v2.5-pro-plan`
  - `model.runner_option_hint_id`: `interactive`
  - `agent_policy.max_iterations`: `32`
  - `agent_policy.allow_tool_calls`: `true`
  - `tool_selection.tool_tags_any`: `["manual-smoke"]`
  - `tool_selection.allow_empty`: `false`
  - `context_slots`: `[]`
- Scene prompt 保持短小通用，只声明执行契约，不泄漏内部 runtime 细节。
- 迁移测试 inventory 与新增 manifest 的 `max_iterations=32` 保持一致。

## Validation

### Required migration test

Command:

```bash
source .venv/bin/activate && pytest tests/runtime/test_scene_assets_migration.py -q
```

Output:

```text
......                                                                   [100%]
6 passed in 0.21s
```

### Lightweight scene prepare check

Command:

```bash
source .venv/bin/activate && python -c 'from pathlib import Path; from dayu.runtime.scene_prepare import ScenePrepareRequest, SceneToolCatalog, SceneToolInfo, prepare_scene; root=Path.cwd(); result=prepare_scene(ScenePrepareRequest(scene_id="smoke_host_public_conversation_memory_scenarios", scene_manifest_root=root/"dayu/config/prompts/manifests", prompt_asset_root=root/"dayu/config/prompts", context_slot_values={}, available_tools=SceneToolCatalog(tools=(SceneToolInfo(name="fake_smoke_fact", tags=frozenset({"manual-smoke"})),)))); print(result.capability_tags); print(result.agent_policy_override.max_iterations if result.agent_policy_override else None); print(tuple(sorted(result.tool_selection.tool_names)) if result.tool_selection.tool_names is not None else None)'
```

Output:

```text
('smoke_host_public_conversation_memory_scenarios',)
32
('fake_smoke_fact',)
```

说明：该检查直接证明新 scene manifest 可加载，`max_iterations=32` 生效，且 `manual-smoke` tag 能选择到工具。迁移测试本身也会遍历所有 manifest 并执行 `prepare_scene`，因此它已经覆盖 S2 的主要装配风险；额外单 scene 检查只是提供更聚焦的证据。

### Type check

Command:

```bash
source .venv/bin/activate && pyright
```

Output:

```text
0 errors, 0 warnings, 0 informations
```

## Docs Decision

- 本 slice 未更新 README。
- 原因：S2 只新增 scene asset 与迁移 inventory，尚未新增用户可运行脚本入口；README 更新属于 approved plan 的 S4，且当前 handoff 明确禁止修改 allowed files 之外的 README/tests。

## Residual Risks

- 场景脚本尚未接入该 scene id：已由 approved plan S1/S3/S4 后续 slice 覆盖，不属于 S2。
- 新 prompt 对具体 assertion marker 的行为只能由后续 scenario smoke 或 assembly tests 进一步验证：归属 S3/S4。
- 未运行真实 LLM smoke：S2 的目标是 scene asset 装配，不是 runtime 行为验证；真实 smoke 归属后续 gate/slice。

## Stop Status

- S2 implementation complete。
- 已完成要求的迁移测试、轻量 scene prepare 检查与 pyright。
- 未提交、未推送、未开 PR。
- 停止在 implementation artifact 完成状态，等待 controller 进入 code review gate。
