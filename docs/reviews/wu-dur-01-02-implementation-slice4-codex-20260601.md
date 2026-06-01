# WU-DUR-01 + WU-DUR-02 Slice 4 Implementation Handoff

## Gate / Scope

- **Gate**: implementation
- **Work unit**: WU-DUR-01 + WU-DUR-02 durable bootstrap concurrency
- **Slice**: Slice 4 - Documentation Sync, Validation, And Handoff Artifacts
- **Approved plan**: `docs/host/wu-dur-01-02-durable-bootstrap-concurrency-plan.md`
- **Branch**: `feat/wu-dur-bootstrap-concurrency`
- **Role boundary**: implementation specialist handoff only；未重启完整 Gateflow，未进入 aggregate deepreview，未提交、未 push、未创建 PR。

## Motivation Check

Slice 4 的动机成立：Slices 1-3 已触及 Host durable schema / transaction / concurrency tests，按照项目 README 同步规则，需要确认 Host durable 内部事实与测试手册是否已准确反映当前代码，并补齐完整验证证据。该 slice 不需要新增 feature，也不应修生产或测试代码。

## Allowed Files Compliance

本轮只修改允许范围内文件：

- `tests/README.md`
- `docs/reviews/wu-dur-01-02-implementation-slice4-codex-20260601.md`

未修改：

- production source
- test source
- root `README.md`
- `dayu/host/README.md`

## README Decision

- `dayu/host/README.md`: 已准确反映当前 Host durable 边界，未修改。现有低层 / diagnostic 段落已经说明：
  - schema 按 fresh current version 起库，版本不匹配要求重建 durable DB；
  - SQLite 连接启用 WAL 与 auto-checkpoint；
  - read transaction 使用 SQLite snapshot 语义，新的短读事务读取最新 committed truth；
  - 内部 WAL checkpoint primitive 只服务显式 diagnostic / test entry，不属于 public maintenance API，也不是 EventLog 或状态正确性的前置条件。
- `tests/README.md`: 已修改。原因是常用收窄命令仍未完整反映当前 Host durable Slice 4 验证集合；已同步为 schema、connection/transaction、durable concurrency matrix + idempotency/projection/memory，以及 multiprocess/liveness 四组命令。
- root `README.md`: 未修改。未发现 CLI、render、config entry 或项目级用户工作流变化。

## Changed Files

- `tests/README.md`
  - 将 Host durable 收窄测试命令更新为当前 Slice 4 指定验证集合。
- `docs/reviews/wu-dur-01-02-implementation-slice4-codex-20260601.md`
  - 新增本 handoff artifact。

## Validation Results

所有命令均在 `source .venv/bin/activate` 后运行：

```text
pytest tests/host/test_durable_schema.py -q
28 passed in 0.31s
```

```text
pytest tests/host/test_durable_connection.py tests/host/test_durable_transaction.py -q
22 passed in 0.31s
```

```text
pytest tests/host/test_durable_concurrency_matrix.py tests/host/test_idempotency_store.py tests/host/test_projection_checkpoint.py tests/host/test_memory_projection.py -q
81 passed in 1.11s
```

```text
pytest tests/host/test_event_log_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_host_instance_liveness.py -q
27 passed in 3.46s
```

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## Residual Risks

- 未运行完整 `tests/host` 或全仓测试；本 slice 按 controller 指定验证集合执行。
- Slice 4 handoff 未进入 aggregate deepreview；aggregate deepreview 仍是 Slice 4 review / acceptance 之后的下一个 controller gate。
- 本轮未审查或修改 Slices 1-3 的 production/test 实现；只做 README 同步检查、指定验证和 handoff 记录。

## Stop Status

Slice 4 implementation handoff complete。未触发验证失败、README 触发范围不清或 forbidden file 修改需求。等待 controller 进入后续 code review gate。
