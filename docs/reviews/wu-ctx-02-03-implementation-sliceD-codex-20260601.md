# WU-CTX-02 + WU-CTX-03 implementation Slice D artifact

## Scope

- 当前 gate：WU-CTX-02 + WU-CTX-03 implementation Slice D。
- Objective：reactive compact final failure 后按 deterministic recent-window fallback policy 创建 recovery Attempt 或 fail closed。
- 未修改 SQLite durable schema，未修改 `dayu/host/durable/run_transition.py`，未新增 Service-facing public API、EngineEvent schema、ContextBudgetPolicy public field 或 execution profile schema。
- 未提交 commit，工作区保留变更供 controller review gate。

## Changed Files

- `dayu/host/engine_ingest.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/test_dispatch_scheduler.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/wu-ctx-02-03-implementation-sliceD-codex-20260601.md`

## Implemented Behavior

- reactive compaction operation final failure 现在复用 Slice C 的 deterministic recent-window fallback helper、预算重估、failed payload 字段与 EventLog fallback provider 语义。
- `compactor_or_artifact_store_missing`、LLM compaction operation final failure、accepted candidate / quality result 缺失等 reactive final failure 分支，会基于 overflow 时冻结的 ordinary material blocks 构造 fallback selection，并重新估算 selected view 预算。
- fallback 预算通过时写入 `CONTEXT_COMPACTION_FAILED`，字段包含：
  - `fallback_action=dispatch`
  - `fallback_policy_decision=deterministic_recent_window`
  - `fallback_input_window`
  - `fallback_input_digest`
  - `fallback_budget_result`
- fallback dispatch 不写 `CONTEXT_COMPACTED`，不写 compact artifact，不触发 memory projection materialization；随后在同一 Run 上创建新的 recovery Attempt，生成新的 `attempt_id` / `execution_id`。
- fallback over-budget 或 selection / estimate failure 时写入 `CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed)`，然后将 `RECOVERING` Run 收口为 `FAILED`。
- reactive compact failure 不写 `RUN_LOST`；`RUN_LOST` 仍保留给 recovery / positive orphan proof 语义。
- `StartRecoveryRunInput.context_compacted_event_id` 已支持 `None`，本 Slice 不需要伪造 non-null compact event id，因此未触发 stop condition。

## State Machine

- reactive compact success：
  `RUNNING -> CONTEXT_COMPACTION_REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTED -> RUN_STARTED(start_reason=recovery) -> ATTEMPT_STARTED`
- reactive compact final failure + fallback dispatch：
  `RUNNING -> CONTEXT_COMPACTION_REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=dispatch) -> RUN_STARTED(start_reason=recovery) -> ATTEMPT_STARTED`
- reactive compact final failure + fallback fail closed：
  `RUNNING -> CONTEXT_COMPACTION_REQUESTED -> ATTEMPT_FAILED -> RUN_RECOVERING -> CONTEXT_COMPACTION_FAILED(fallback_action=fail_closed) -> RUN_FAILED`
- reactive count limit / unreadable count / precondition failure 仍按既有 fail-closed 路径处理，不启动 fallback dispatch。

## Tests

- `tests/host/test_engine_ingest_mapping.py`
  - 覆盖 reactive compactor missing / artifact store missing equivalent failure + fallback budget pass：创建第二个 Attempt，新 current attempt，不写 `CONTEXT_COMPACTED`，不写 `RUN_FAILED` / `RUN_LOST`，failed payload 为 `fallback_action=dispatch`。
  - 覆盖 reactive fallback over-budget：failed payload 为 `fallback_action=fail_closed`，Run `FAILED`，`RUN_LOST` count 为 0，不创建第二个 recovery Attempt。
- `tests/host/test_dispatch_scheduler.py`
  - 覆盖 scheduler 组合路径：reactive compact failure fallback 创建第二个 recovery dispatch，第二个 request 不依赖 compact artifact，并继续使用当前输入完成 Run。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_dispatch_scheduler.py -q`
  - result：`100 passed in 1.24s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - result：`0 errors, 0 warnings, 0 informations`

## README Decision

- 已更新 `dayu/host/README.md`：同步 reactive compact failure fallback 的当前稳定语义，明确 fallback 不是 compact success、reactive fallback dispatch 创建 recovery Attempt、fail closed 收口为 `FAILED` 且不写 `RUN_LOST`。
- 已更新 `tests/README.md`：同步新增 engine ingest / scheduler 对 reactive fallback dispatch 与 over-budget fail closed 的测试覆盖。
- 未更新根 README、`dayu/README.md`、Engine / Fins / Config README；本 Slice 未改变 public 使用方式、分层关系、配置入口或其它包职责。

## Residual Risks

- RR-CTX-SLICEB-01：本 Slice 未修改 reactive `context_budget_policy_missing` / `input_event_missing` precondition 逻辑。当前实现仍由 `_fail_reactive_recovery_without_request` 关闭旧 Attempt、写 failed fact 并 fail closed；没有进入 fallback dispatch，也不会写 `RUN_LOST`。本 Slice 的新增路径发生在 request 已写入、旧 Attempt 已进入 `RECOVERING` 后的 compaction operation final failure；precondition 集成覆盖仍建议留给 aggregate review 聚合裁决，避免通过破坏 durable input_event invariant 构造脆弱测试。
- reactive frozen material list 目前沿用既有 `_frozen_reactive_material_blocks` 输入边界；若后续把 accepted tool evidence 或 richer continuity 纳入 reactive frozen material，fallback selection 会自然复用同一 material list，但需要补更强的 RunInputBuilder filtered-view 组合断言。
- fallback dispatch 后真实 provider 仍可能再次 overflow；该行为由既有 `max_reactive_compactions_per_run` 上限与后续 Slice E 的 repeated-overflow E2E 收口。

## Stop Status

- 未发现需要伪造 `context_compacted_event_id` 才能启动 recovery 的 blocker。
- 未触碰禁止文件与禁止 public schema。
- 未写 `CONTEXT_COMPACTED`、compact artifact 或 memory materialization 来启动 fallback recovery。
- 未将 proactive failure 推入 `RECOVERING`，未将 reactive compact failure 推入 `LOST`。
