# WU-TOOLS-01-F01-02 Slice 1 Implementation — AgentCodex

## 1. Context

- Work unit: WU-TOOLS-01-F01-02
- Gate: implementation
- Slice: Slice 1 — Fins Awaiting Tools Token Bridge
- Approved plan: `docs/host/wu-tools-01-f01-02-cancellation-plan.md`
- Accepted plan commit: `af3ac6b8`
- Control doc: `docs/host/issues-implementation-control.md`
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-slice1-implementation-codex.md`
- Date: 2026-06-08

## 2. First-principles Judgment

Slice 1 的动机成立。直接证据是 download / preprocess awaiting callable 原先接收 `BatchToolExecutionContext` 后 `del context`，导致 ToolRuntime 注入的 Host cancellation token 无法进入 Fins durable job start。runtime 原先在创建 queued job 后立即 submit executor，中间没有同步取消 checkpoint。修复根因应在工具 callable 与 Fins ingestion runtime 的启动边界完成；不需要改变 Host cancel 真源、Host / Engine contract，也不需要新增 Fins job 状态。

## 3. Implemented Changes

### Production

- `dayu/fins/tools/download_tools.py`
  - 删除 `del context`，读取 `context.cancellation_token`。
  - start 前 token 已取消时返回 `ToolCancelledOutcome(reason=host_cancelled)`，不创建 durable job。
  - 调用 `runtime.start_download(..., cancellation_token=...)`。
  - runtime 返回 `CANCELLING` / `CANCELLED` start record 时投影为 `ToolCancelledOutcome`。
  - `OSError` 仍返回 `fins_download_start_failed`，hint 指向 Fins workspace 存储权限。

- `dayu/fins/tools/preprocess_tools.py`
  - 与 download 对称：读取 token，start 前取消返回 `ToolCancelledOutcome`，传入 `runtime.start_preprocess(..., cancellation_token=...)`。
  - runtime 返回 cancelling / cancelled start record 时投影为 cancelled outcome。
  - `OSError` 仍返回 `fins_preprocess_start_failed`，hint 指向 Fins workspace 存储权限。

- `dayu/fins/ingestion_runtime.py`
  - `start_download` / `start_preprocess` 新增 keyword-only `cancellation_token: CancellationToken | None = None`。
  - normalize / request_summary 后、durable create 前执行同步 checkpoint；命中取消时抛出 `FinsIngestionStartCancelledError`，工具侧转为 cancelled outcome。
  - durable create 后、executor submit 前在 `_start_lock` 持有区间内执行同步 checkpoint；命中取消时调用 `request_cancel(job_id)`，返回与 durable record 一致的 `FinsIngestionJobStart`，且不 submit 后台 job。
  - create / checkpoint / submit 决策被同一个 `_start_lock` 覆盖，没有“checkpoint 已看到取消但仍 submit”的窗口。
  - submit 后不再使用 token；后台 job 继续只观察 job store durable cancel。
  - request_cancel 期间的 `OSError` 不吞掉，由工具侧按存储权限失败 outcome 收口。

### Tests

- `tests/fins/test_fins_ingestion_tools.py`
  - 新增 download start 前 token 已取消返回 `ToolCancelledOutcome` 且不创建 job。
  - 新增 preprocess start 前 token 已取消返回 `ToolCancelledOutcome` 且不创建 job。
  - 现有 awaiting outcome、参数错误、start failure、wait adapter 测试保持通过。

- `tests/fins/test_fins_ingestion_runtime.py`
  - 新增 download create 后、submit 前取消：job 为 `CANCELLING`、`cancellation_requested=True`，executor 未收到后台操作。
  - 新增 preprocess create 后、submit 前取消：同上。

## 4. README Decision

- `dayu/fins/README.md`: 已读取 `Agent更新约束【必须遵守】`。本次变更属于当前 `dayu.fins` package 已实现的 awaiting tool capability、runtime 接口和 durable cancel 关键机制，因此更新。
- `tests/README.md`: 已读取现有职责说明。新增测试属于 `tests/fins/` 当前测试分层和维护约定，因此更新。
- `docs/host/issues-implementation-control.md`: 工作区已有 controller bookkeeping 修改；本 slice 未修改。

## 5. Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed
  - Evidence: `48 passed, 3 warnings in 1.98s`
  - Warnings: edgar dependency deprecation warnings only。

- `source .venv/bin/activate && pyright`
  - Result: passed
  - Evidence: `0 errors, 0 warnings, 0 informations`
  - Note: pyright reported only a newer version notice。

## 6. Residual Risks / Uncovered Areas

| ID | Risk / uncovered area | Classification | Disposition |
|---|---|---|---|
| R1 | Host awaiting accept 前仍可能存在 orphan job 窗口；Slice 1 只处理 token 到 Fins start 边界的桥接。 | covered by later approved slice / later work unit | Approved plan 已将两阶段启动 deferred 到 WU-WAIT-03 或独立 follow-up。 |
| R2 | submit 后无法用 Host token 抢占已进入后台的同步 I/O。 | assigned to later work unit | 当前设计以 Fins job store durable cancel 为后台真源；物理 revoke 不属于 Slice 1。 |
| R3 | create 后、submit 前取消后 job 停在 `CANCELLING`，没有后台 runner 将其收口为 `CANCELLED`。 | fixed in current slice | 这是 plan 允许的 “cancelling/cancelled” durable cancel fact；不 submit 后台操作是本 slice 的核心 invariant。后续 wait adapter 对 `cancelling` 仍为 not-ready，外部 cleanup / terminalization 不在本 slice 范围。 |
| R4 | Web / Doc / Fins read tools token 传播未实现。 | covered by later approved slice | 属于后续 Slice 2 / 3 / 4。 |

## 7. Completion Status

Slice 1 implementation complete. 已完成实现、测试、pyright、README 触发判断和 implementation artifact。未执行 review、fix、commit、push、PR、merge 或其它 gate。
