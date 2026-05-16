# P1-P7 Design Goals Fix - Codex - 2026-05-16

## Gate

- Gate: fix
- Worker: AgentCodex
- Controller: AgentController
- Branch: `fix/host-p1-p7-awaiting-production-wiring`
- Source decision: `docs/reviews/p1-p7-design-goals-controller-decision-20260516.md`

## Changed Files

- `dayu/host/command.py`
- `dayu/host/dispatch.py`
- `dayu/host/waiting.py`
- `tests/host/test_active_cancel_dispatch.py`
- `tests/host/test_command_handle.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_resolve_wait_command.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## Per-Decision Fix Status

- D2 active worker registry 注入: fixed after follow-up. `HostCommandHandle` 现在持有构造期注入的 `ActiveWorkerRegistry`；`create_host_command_handle(..., active_registry=None)` 为当前 handle 创建 fresh registry；`HostDispatchScheduler.open(..., active_registry=None)` 为当前 scheduler 创建 fresh registry；command path 与 scheduler 不再通过任何模块级 mutable singleton 共享 registry。`dayu.host.dispatch` 已删除 `DEFAULT_ACTIVE_WORKER_REGISTRY`、`cancel_active_worker()` 与对应 export。生产 active cancel propagation 必须由 composition root 显式把同一个 `ActiveWorkerRegistry` 对象传给 command handle 与 scheduler。测试覆盖 custom registry 注入后 public cancel 能传播到 scheduler 注册的 active worker，也覆盖两个默认 command handle / 两个默认 scheduler 不共享 registry。
- D3 resolve_wait 幂等 digest: fixed. `_wait_resolution_digest` 只包含 `wait_id`、`idempotency_key` 与 typed outcome JSON；`source` / `observed_at` 继续保留在首次提交 payload / audit / diagnostic 中，不参与同 outcome conflict 判定。测试覆盖同 key + 同 outcome + 不同 `observed_at` replay 不追加 EventLog、不创建第二个 resume Attempt、不追加第二个 `TOOL_RESULT_ACCEPTED`；同 key + 不同 outcome 仍返回 `IDEMPOTENCY_CONFLICT`。
- D4 `TOOL_TERMINAL_RESULT` 设计口径: fixed in design. `docs/host/design.md` 明确 P1-P7 accepted waiting terminal result 使用 `TOOL_RESULT_ACCEPTED` 作为唯一 accepted tool result canonical event，通过 wait-specific payload fields 表达 wait completion 来源和状态，不要求独立 `TOOL_TERMINAL_RESULT`。
- D5 `FOLLOWUP_QUEUED` 设计口径: fixed in design. `docs/host/design.md` 明确 `submit_followup(queue)` 的 canonical 表达是 `USER_INPUT_ACCEPTED` + `RUN_ACCEPTED`，并按结果追加 `RUN_QUEUED` 或 `RUN_STARTED`，不要求独立 `FOLLOWUP_QUEUED`。
- D6 WAITING cancel stale docstring: fixed. `cancel_run` / `cancel_session_runs` docstring 已更新为当前实现支持 `WAITING` cancel，`RECOVERING` 仍由 Phase 11 负责。
- fetch_more cursor 内存决定: unchanged by scope. 本轮未恢复 durable cursor descriptor，也未把内存 cursor 作为偏离处理。

## Tests / Pyright / Diff Check

- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py::test_resolve_wait_same_key_same_outcome_replays_with_different_observed_at tests/host/test_resolve_wait_command.py::test_resolve_wait_same_key_different_outcome_conflicts tests/host/test_active_cancel_dispatch.py::test_cancel_run_active_worker_propagates_and_closes_cancelled tests/host/test_active_cancel_dispatch.py::test_cancel_session_replay_repropagates_active_without_new_facts -q`: passed, 4 tests.
- `source .venv/bin/activate && pytest tests/host/test_resolve_wait_command.py tests/host/test_active_cancel_dispatch.py tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_command_handle.py tests/host/test_wait_cancel_late_result.py -q`: passed, 39 tests.
- `source .venv/bin/activate && pytest tests/host -q`: passed, 392 tests.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: passed, 0 errors / 0 warnings / 0 informations.
- `git diff --check`: passed.

Follow-up D2 validation:

- `source .venv/bin/activate && pytest tests/host/test_command_handle.py::test_factory_default_active_registry_is_handle_local tests/host/test_dispatch_scheduler.py::test_default_active_registry_is_scheduler_local tests/host/test_active_cancel_dispatch.py::test_cancel_run_active_worker_propagates_and_closes_cancelled tests/host/test_active_cancel_dispatch.py::test_cancel_session_replay_repropagates_active_without_new_facts -q`: passed, 4 tests.
- `source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_dispatch_scheduler.py tests/host/test_active_cancel_dispatch.py tests/host/test_phase5_local_execution_integration.py tests/host/test_resolve_wait_command.py tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_wait_cancel_late_result.py -q`: passed, 65 tests.
- `source .venv/bin/activate && pytest tests/host -q`: passed, 394 tests.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: passed, 0 errors / 0 warnings / 0 informations.
- `git diff --check`: passed.

## Docs Decisions

- Updated `docs/host/design.md` only for D4/D5 accepted design goals; no fetch_more cursor text was changed.
- Updated `dayu/host/README.md` because `dayu/host/command.py` and `dayu/host/waiting.py` behavior changed at Host public command boundaries.
- Updated `tests/README.md` because Host test coverage wording changed for injected active cancel registry and resolve_wait observed_at replay.
- No root `README.md`, `dayu/README.md`, `dayu/engine/README.md`, `dayu/fins/README.md`, or `dayu/config/README.md` update was required: this fix did not change CLI/user workflow, global layer boundaries, Engine/Fins/Config behavior, or project-level usage.

## Residual Risks

- Active cancel propagation remains best-effort and in-process. The fix ensures command path and scheduler can share the same injected registry, but it does not add cross-process worker cancellation or durable physical cancel guarantees.
- No default registry is shared across command handles or schedulers. Callers that omit `active_registry` get isolated local registries; production composition must explicitly pass one registry to both command and scheduler when active cancel propagation is required.
- `resolve_wait` replay with changed `source` now follows the same semantic rule as changed `observed_at`: replay returns the first accepted payload for the same outcome. This matches the outcome-identity decision, but diagnostics intentionally preserve only the first accepted source / observed time for that idempotency key.

## Completion Status

Completed. No commit, push, or PR was performed.
