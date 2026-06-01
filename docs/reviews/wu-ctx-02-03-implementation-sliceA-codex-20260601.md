# WU-CTX-02 + WU-CTX-03 implementation Slice A

## Gate / Slice

- Gate: WU-CTX-02 + WU-CTX-03 implementation Slice A。
- Slice: 默认 policy / config / model 对齐。
- Approved plan: `docs/host/wu-ctx-02-03-compact-failure-overflow-plan.md`。
- Accepted plan commit: `9d89db3`。
- Worker role: implementation worker；未启动 `$gateflow` controller workflow，未进入 review、commit、push 或 PR。

## Scope

Allowed production/config files:

- `dayu/host/context_policy.py`
- `dayu/config/execution_profiles.json`
- `dayu/config/prompts/manifests/conversation_compaction.json`
- `dayu/service/host_assembly.py` 仅允许诊断或测试支撑；本次未修改。

Allowed test files:

- `tests/host/test_context_policy.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_host_assembly.py`

Allowed docs:

- `dayu/config/README.md`
- `tests/README.md`

## Changed Files

- `dayu/host/context_policy.py`
- `dayu/config/execution_profiles.json`
- `dayu/config/prompts/manifests/conversation_compaction.json`
- `tests/host/test_context_policy.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_scene_assets_migration.py`
- `tests/service/test_host_assembly.py`
- `docs/reviews/wu-ctx-02-03-implementation-sliceA-codex-20260601.md`

## Implemented Plan Items

- 将 `DEFAULT_MAX_COMPACTION_ATTEMPTS_PER_OPERATION` 从 `2` 对齐为 `5`。
- 将包内四个 execution profile 的 `context_budget_policy.max_compaction_attempts_per_operation` 从 `3` 对齐为 `5`。
- 将 `conversation_compaction` scene manifest 的 `model.default_model_id` 从 high-spec 模型改为默认 execution profile compactor 模型 `deepseek-v4-flash`。
- 更新 Host fallback 默认测试，显式断言默认 compaction operation attempt budget 为 `5`。
- 更新 runtime config loader 测试，断言包内所有 execution profiles 的 attempt budget 均为 `5`。
- 更新 scene asset 测试，断言 `conversation_compaction.model.default_model_id` 与默认 execution profile 的 `compactor_baseline.model_id` 一致。
- 更新 Service assembly 测试，断言默认 packaged profile 装配出的 Host `context_budget_policy.max_compaction_attempts_per_operation` 为 `5`。

## State-machine / Payload Changes

- State machine changes: 无。
- Event payload changes: 无。
- Schema changes: 无。
- Public request shape changes: 无。
- Service `host_assembly.py` production logic changes: 无；现有实现已直接从 execution profile 映射 `ContextBudgetPolicy`，本 Slice 只补测试断言。

## Validation

已在 `source .venv/bin/activate` 后运行：

```bash
pytest tests/host/test_context_policy.py tests/runtime/test_config_loader.py tests/runtime/test_scene_assets_migration.py tests/service/test_host_assembly.py -q
```

Result:

```text
74 passed in 0.37s
```

已在 `source .venv/bin/activate` 后运行：

```bash
python -m pyright dayu/ tests/ utils/
```

Result:

```text
0 errors, 0 warnings, 0 informations
```

## Docs Decision

- 触发检查: 修改了 `dayu/config/` 和 `tests/`，按 AGENTS.md 检查 `dayu/config/README.md` 与 `tests/README.md`。
- Decision: 不更新 README。
- Rationale: `dayu/config/README.md` 未写死旧 `max_compaction_attempts_per_operation` 值或旧 `conversation_compaction` 默认模型；`tests/README.md` 仍只描述测试分层与维护规则，本次是在既有测试层内增加一致性断言，没有新增测试层级、运行方式或维护规则，也没有形成旧术语、旧路径或旧入口不一致。

## Invariants Checked

- Host fallback 默认 `max_compaction_attempts_per_operation == 5`。
- 包内 execution profiles 默认 `max_compaction_attempts_per_operation == 5`。
- Service assembly 使用默认 packaged profile 装配出的 Host policy 默认 `max_compaction_attempts_per_operation == 5`。
- `conversation_compaction` scene default model 与默认 execution profile `compactor_baseline.model_id` 一致。
- 未改变普通 scene 默认模型。
- 未新增 high-spec allow-list。
- 未新增 scene inheritance 防御测试。
- 未改变 config schema、public API 或 Service public request shape。

## Residual Risks

- Slice A 范围内无未覆盖风险。
- `CONTEXT_COMPACTION_FAILED` payload 诊断补足、deterministic recent-window fallback、proactive / reactive compact failure E2E、连续 reactive overflow dispatch-loop E2E 仍由 approved plan 的后续 slices 覆盖；本 Slice 未提前实现。

## Stop Status

- Stop conditions: 未触发。
- 当前状态: Slice A implementation complete，按 handoff 要求停止，不进入 review、commit、push 或 PR。
- Artifact path: `docs/reviews/wu-ctx-02-03-implementation-sliceA-codex-20260601.md`。
