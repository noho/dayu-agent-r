# WU-DUR-01-02 Implementation Slice 3 Report

- **Gate**: WU-DUR-01 + WU-DUR-02 implementation
- **Work unit**: Durable Bootstrap / Concurrency
- **Slice**: Slice 3 - Durable Concurrency Matrix Gap Tests
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Stop status**: completed

## Scope 判断

动机成立。Approved plan 的直接证据已经把 EventLog append、ensure_session 与 liveness 标为 closed-by-evidence，同时指出 idempotency 多进程、projection checkpoint lost CAS、memory snapshot + checkpoint CAS rollback 仍缺直接测试证据。本 slice 只补这些 gap tests；未修改 EventLog append、ensure_session、liveness，也未引入 memory snapshot row CAS 或 rollback failure policy。

## Changed Files

- `tests/host/test_durable_concurrency_matrix.py`
  - 新增 durable concurrency matrix 缺口测试模块。
  - 模块 docstring 明确列出 EventLog append、ensure_session、liveness closed-by-evidence，不重复测试的理由。
  - 新增 top-level multiprocess worker 与 result-file helper，使用 start gate，固定 4 个 worker，不依赖裸 sleep 判断成功顺序。
- `tests/README.md`
  - 因新增测试文件，按测试手册触发规则同步 Host durable 缩窄运行命令与 durable concurrency matrix 覆盖说明。

## Implemented Items

- idempotency same scope/key/same digest multiprocess：
  - 所有 worker 使用同一 semantic digest、不同候选 result ref。
  - 断言所有 worker 返回同一 winning digest/result ref，无 conflict。
  - 断言 durable `idempotency_records` 只有一条 row。
- idempotency same scope/key/different digest multiprocess：
  - 所有 worker 使用同一 scope/key、不同 semantic digest。
  - 断言只有一个 winner，其余 worker 结果为 `HostIdempotencyConflictError` 分类。
  - 断言 durable DB 只有一条 winning row。
- projection checkpoint lost CAS synthetic direct test：
  - 先真实推进 checkpoint 到 sequence 1。
  - monkeypatch `ensure_projection_checkpoint` 返回 stale sequence 0。
  - 推进到 sequence 2 时断言抛出 `HostDurableError("projection checkpoint advance lost CAS race")`，且持久化 checkpoint 仍停在 sequence 1。
- memory snapshot + checkpoint stale CAS direct test：
  - 先真实推进 checkpoint 到 sequence 1。
  - 构造 cursor sequence 2 的 `ConversationMemorySnapshot`。
  - 用同一 stale checkpoint monkeypatch 触发 `write_memory_snapshot_with_checkpoint()` CAS failure。
  - 断言目标 snapshot 未持久化，checkpoint 仍停在 sequence 1。

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_durable_concurrency_matrix.py -q`
  - Result: `4 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q`
  - Result: `81 passed`

## Pyright Result

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`

## README Decision

已更新 `tests/README.md`。原因是本 slice 新增 `tests/host/test_durable_concurrency_matrix.py`，测试手册原 Host durable 缩窄运行命令和覆盖事实未包含该文件；更新内容仅限测试入口与当前覆盖事实。

## Production Fixes

无。新增 tests-first 覆盖未暴露 `dayu/host/durable/idempotency.py`、`dayu/host/durable/projection.py` 或 `dayu/host/durable/memory.py` 的真实行为问题。

## Plan Deviations

无实质偏离。采用 preferred 新文件 `tests/host/test_durable_concurrency_matrix.py` 集中承载矩阵缺口；未把测试分散进既有单元测试文件。README 更新是新增测试文件触发的计划内文档同步。

## Residual Risks Classification

- **fixed in current slice before review**: idempotency same/different digest 多进程、projection checkpoint lost CAS、memory snapshot + checkpoint CAS rollback 均已有直接测试覆盖。
- **covered by existing evidence**: EventLog append、ensure_session、liveness 继续由既有测试和 plan evidence 覆盖，本 slice 不重复。
- **out of scope by approved plan**: rollback failure policy、memory snapshot row CAS、EventLog append / ensure_session / liveness production changes 未纳入。
- **remaining test-environment risk**: 多进程 smoke 仍可能在极端慢机器上受进程启动影响；当前使用 start gate、result files、固定小 worker 数和 bounded timeout，且断言不依赖 acquire ordering。无需新增 issue。

## Completion Signal

Slice 3 required tests-first items 已完成；验证命令与 pyright 均通过；没有 production fix、forbidden file change、commit、push 或 PR 动作。
