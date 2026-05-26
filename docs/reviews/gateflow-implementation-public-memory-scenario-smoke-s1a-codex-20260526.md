# Gateflow Implementation Artifact: Host Public Conversation Memory Scenario Smoke S1a

## Gate

- 当前 gate：implementation。
- 角色：implementation worker，不是 controller。
- 状态：只完成 S1a，不进入 code review、fix、commit、push、PR 或其它 gate。

## Work Unit

- Work unit：Host public conversation memory scenario smoke。
- 当前 slice：S1a pure script foundations。
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`。
- Controller adjudication：`docs/reviews/gateflow-plan-controller-adjudication-public-memory-scenario-smoke-20260526.md`。
- Accepted plan commit：`6f5adc1`。

## Scope / Non-goals / Allowed Files

- 本 slice 只建立 standalone 脚本基础，不实现完整 Host `open_host` / `ensure_session` / `submit_followup` flow。
- 本 slice 避免 `dayu.host` imports，不读取 sqlite、EventLog、memory table、durable store 或 compact payload。
- 本 slice 不新增 scene、tests、README，不修改 `utils/smoke_host_public_conversation_memory.py`。
- Allowed files：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1a-codex-20260526.md`

## Changed Files

- `utils/smoke_host_public_conversation_memory_scenarios.py`
  - 新增 Host public conversation memory scenario smoke 的 standalone skeleton。
- `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1a-codex-20260526.md`
  - 新增本 S1a implementation artifact。

## Implemented Items

- 新增中文模块、类、函数 docstring，并保持严格类型签名。
- 新增 CLI parsing：
  - `--suite core|long|all`
  - `--long-rounds`，范围 `20..25`
  - `--pressure-mode auto|off`
  - 保留 common args：`--workspace-root`、`--scene-id`、`--execution-profile-id`、`--host-runtime-id`、`--model-id`、`--runner-option-hint-id`、`--log-level`、`--reuse-session`、`--keep-workspace`
- 新增基础类型：
  - `SmokeArgs`
  - `SuiteMode`
  - `PressureMode`
  - `RoundSpec`
  - `LongRoundTemplate`
  - `MockFactRecord`
  - `MockFinanceMemoryTool`
- 固化 mock fact constants、markers、assertion lines 与 stdout prefix。
- 新增 C2 deterministic long input builder，包含固定 anchors：
  - `DAYU_LONG_INPUT_FACTOR_1_EXPORT_MIX`
  - `BATTERY_PRICE_PRESSURE_FACTOR_2`
  - `DAYU_LONG_INPUT_FACTOR_3_SCALE_EFFECT`
- 新增 L01-L25 long templates，并实现 `core` / `long` / `all` spec selection。
- 新增 calls_by_key formatter。
- 新增 answer normalization 与 required / forbidden assertion helper。
- `__main__` 解析真实 CLI 参数，并打印 `SMOKE SCENARIO SKELETON READY`。
- S1b 延后项保持未实现：Host lifecycle、scene assembly、tool discovery provider、watcher、session/run public assertions。

## Validation

已按 S1a 要求验证：

```text
source .venv/bin/activate && python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：

```text
passed
```

```text
source .venv/bin/activate && python utils/smoke_host_public_conversation_memory_scenarios.py --suite core --pressure-mode off
```

结果：

```text
exited 0
SMOKE PRESSURE disabled
SMOKE SCENARIO SKELETON READY suite=core rounds=14 scene_id=smoke_host_public_conversation_memory_scenarios provider_id=host-public-conversation-memory-scenarios-smoke provider_spec_id=host-public-conversation-memory-scenarios-smoke provider_import=__main__:discover_smoke_tools tool=get_mock_finance_memory_fact tag=manual-smoke default_user=manual-smoke-user slot_prefix=manual-smoke-conversation-memory-scenarios client_prefix=manual-smoke-conversation-memory-scenarios probe_known=True probe_key=maotai_revenue preview=DAYU_MEM_MAOTAI_REV_2024H1_V1
```

Controller supplied additional validation status:

```text
rg private-read check only matched module docstring, no dayu.host private imports or sqlite/EventLog/memory table reads.
```

Additional local type validation performed during S1a:

```text
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## Docs Decision

- 本 slice 不更新 README。
- 原因：S1a 只是纯脚本骨架，完整可用 smoke 入口、scene asset、assembly tests 和用户文档属于后续 slices；当前 README 若描述该入口为完整 Host smoke 会提前承诺未实现行为。

## Residual Risks

- S1b later slice：完整 Host public flow 尚未实现，包括 `open_host`、`ensure_session`、`submit_followup`、`watch_session_events`、`get_session` 与 terminal event assertion。
- S2 later slice：scene manifest 与 scene prompt 尚未新增，当前 skeleton 不能被真实 scene assembly 使用。
- S3 later slice：assembly tests 尚未新增，CLI 边界、long template selection、mock tool、pressure 和 normalization 仍需自动化测试覆盖。
- S4 later slice：README / tests README 同步尚未执行，需等真实入口和测试落地后更新。
- Work-unit inherent risk：public smoke 仍只能通过用户可见回答代理验证 memory continuity，不能直接证明内部 pinned_state、episode、compaction material 或 durable schema 状态。

## Stop Status

- S1a implementation complete。
- 已停止在 S1a 边界内。
- 未启动 `$gateflow` / `/gateflow`。
- 未进入 code review、fix、re-review、aggregate deepreview、commit、push、PR 或其它 gate。
