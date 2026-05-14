# Gateflow Implementation Artifact: Host P3-S6 Multiprocess Tests And Documentation Sync

- **gate**: implementation
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S6 Multiprocess Tests And Documentation Sync
- **approved plan**: `docs/host/phase3-session-run-attempt-admission-plan.md` § P3-S6
- **implementation date**: 2026-05-14

## Scope

本 slice 只修改测试、Host README、tests README 与本 implementation artifact；未修改生产代码。

允许文件：

- `tests/host/test_admission_multiprocess.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p3-s6-multiprocess-docs-20260514.md`

非目标：

- 不实现 Engine dispatch、scheduler、lane、WorkerProxy、EngineEvent ingest、ToolRuntime、wait/resolve、steer、retry/replay 或 recovery。
- 不修改 `dayu/host/admission.py` 或其它生产代码。
- 不做性能压测。

## Implemented Plan Items

- 新增 `tests/host/test_admission_multiprocess.py`。
- 使用 `multiprocessing.Process`，每个子进程独立打开 Host durable store connection。
- 使用文件 gate 让多进程竞争尽量同时进入 SQLite write path；断言以 durable rows 与 EventLog 为准，不依赖进程调度顺序。
- 覆盖同 slot 并发 `ensure_session` 只返回一个 Session binding。
- 覆盖同 Session 并发 start/follow-up 至多一个 active Run。
- 覆盖重复 `(session_id, client_request_id)` 跨进程返回同一 Run，变更 semantic digest 返回 `idempotency_conflict`。
- 覆盖 queued follow-up 释放 active 后按 accepted `event_sequence` FIFO promotion。
- 覆盖 queued cancel 与 promotion 的 first-committer-wins：最终只能是 queued cancel 成功或 promotion 成功之一，失败方不追加对应事实。
- 覆盖 admission 多进程写入后的 EventLog `event_sequence` 全局唯一、递增且连续。
- 同步 `dayu/host/README.md` 的 internal admission 当前事实。
- 同步 `tests/README.md` 的 Host admission 多进程测试命令与覆盖范围。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_admission_multiprocess.py -q
source .venv/bin/activate && pytest tests/host/test_admission_multiprocess.py tests/host -q
source .venv/bin/activate && python -m pyright dayu/host tests/host
git diff --check
```

结果：

- `pytest tests/host/test_admission_multiprocess.py -q`: 6 passed
- `pytest tests/host/test_admission_multiprocess.py tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors, 0 warnings
- `git diff --check`: passed

## Documentation Decision

- `dayu/host/README.md` 触发更新：P3-S6 新增 Host admission 多进程 durable invariant 测试事实，属于 Host 开发手册职责。
- `tests/README.md` 触发更新：新增 Host admission 多进程测试文件与运行命令，属于测试手册职责。
- 根目录 `README.md` 未触发：未改变 CLI、render、项目级使用方式或配置入口。
- `dayu/README.md` 未触发：未改变分层关系、装配方式或 Host 公共边界。
- Engine / Fins / Config README 未触发。

## Plan Gaps

未发现需要返回 controller 的 blocking gap。P3-S6 的测试范围可以在不修改生产代码的前提下完成。

## Residual Risks

- 多进程测试仍依赖本机 SQLite 文件锁与调度；已通过 modest process count、较宽 busy timeout 和 write retry 降低偶发 busy 风险。
- cancel queued vs promotion 测试使用低层 transition helper 构造“active slot 已释放但尚未自动 promotion”的竞争窗口，用于直接验证 queued row 的 first-committer-wins；public facade 阶段仍需覆盖最终 API 入口。
- 本 slice 不覆盖真实 dispatch、lane acquire、WorkerProxy cancel propagation 或 EngineEvent ingest；这些仍属于后续 phase。

## Completion Status

Implementation completed for P3-S6. Required validation passed.
