# Host Phase 7 P7-S1 Implementation Artifact

- slice: P7-S1 Public Contracts And Durable Wait Record
- branch: feat/host-phase7-tool-awaiting-resolve-wait
- status: completed
- date: 2026-05-16

## Motivation Judgment

动机成立，严重性没有被高估。当前 Phase 7 后续 awaiting accept、`resolve_wait`、WAITING cancel 与 poll/manual adapter 都依赖同一组公共等待结果 envelope 与 durable wait record truth。继续保留 `ResolveWaitRequest.outcome_ref: str` 或没有 `host_wait_records` 会把等待结果可信性、状态 CAS 和恢复边界推给后续实现切片，违反 Host strong ownership。

## Implemented Changes

- `dayu/host/api.py`
  - 删除 `ResolveWaitRequest.outcome_ref`，改为 `outcome: ResolveWaitOutcome`。
  - `observed_at` 改为 UTC-aware `datetime` 并在 dataclass 构造期校验 naive / non-UTC。
  - 新增 `ResolveWaitCompletedOutcome`、`ResolveWaitFailedOutcome`、`ResolveWaitCancelledOutcome`、`ResolveWaitLostOutcome`、`ResolveWaitOutcome`。
  - 新增 `WaitAdapterKey`、`WaitProviderStatusRef`、public `HostPayloadRef` 与 P7-S1 字符串长度常量。
- `dayu/host/__init__.py`
  - 导出 P7-S1 新公共构造类型与长度常量。
- `dayu/host/tool_runtime.py`
  - `HostPayloadRef` 改为从 `dayu.host.api` 导入，移除本地重复 dataclass。
  - 新增 `ToolFactKind.LOST`。
- `dayu/host/durable/schema.py`
  - `HOST_SCHEMA_VERSION` bump 到 `4`。
  - 新增 `host_wait_records` DDL、长度 `CHECK`、状态 / resume policy `CHECK`、FK 与三个索引。
- `dayu/host/durable/state.py`
  - 新增 `RunStartReason.RESUME`。
  - 新增 `WaitRecordStatus`、`WaitResumePolicy`、`WaitSnapshotRef`、`ExternalJobRef`、`WaitRecordRow`。
  - 新增 wait record status / policy / typed ref serialize / deserialize helper。
  - 新增 insert/read helper 与 resolved / failed / cancelled / lost / cancel-active CAS helper。
- tests
  - 更新 public contract、package export、schema、state codec 测试。
  - 新增 `tests/host/test_wait_record_state.py` 覆盖 wait record round-trip、DDL CHECK、unique active wait 与 CAS helper。
  - 按 controller 裁决，只在 `tests/host/test_public_run_api.py` 中把旧 `ResolveWaitRequest` 构造迁移到 typed outcome + UTC datetime，没有新增 P7-S3/P7-S4 行为测试。

## Validation

- `source .venv/bin/activate && pytest tests/host/test_public_contracts.py tests/host/test_import_boundary.py tests/host/test_package_exports.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_wait_record_state.py -q`
  - result: `73 passed in 0.58s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pytest tests/host/test_public_run_api.py -q`
  - result: `10 passed in 0.23s`
- `git diff --check`
  - result: passed

## Scope Notes

- 未实现 ToolRuntime awaiting accept 行为变更。
- 未实现 `resolve_wait` command path。
- 未实现 poller / callback / manual adapter。
- 未修改 Engine ingest 行为。
- 未添加旧 `outcome_ref` 兼容入口。

## Residual Risk

- 单条 wait record CAS helper 的 `CAS_LOST` 分支是并发事务竞态分支，当前单进程 deterministic 测试覆盖了 `UPDATED`、`NOT_FOUND`、`INVALID_STATE`，没有通过 sleep 或脆弱并发测试强造该分支。
- README 同步属于后续 P7-S5 文档切片；本 slice 文件 ownership 未包含 README。
