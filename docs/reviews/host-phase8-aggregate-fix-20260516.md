# Host Phase 8 Aggregate Fix - 2026-05-16

## Gate

当前 gate：Phase 8 aggregate fix。

Fix truth：

- `docs/reviews/host-phase8-aggregate-review-controller-adjudication-20260516.md`

Review inputs：

- `docs/reviews/host-phase8-aggregate-review-mimo-20260516.md`
- `docs/reviews/host-phase8-aggregate-review-ds-20260516.md`

## Scope

允许写入并实际修改：

- `dayu/host/projection.py`
- `dayu/host/durable/schema.py`
- `tests/host/test_projection_runner.py`
- `tests/host/test_durable_schema.py`
- `docs/reviews/host-phase8-aggregate-fix-20260516.md`

未修改：

- Engine、runtime、service、ui、fins。
- command path、admission、waiting、dispatch、recovery。
- public read API shape 与 `get_run` / `RunResult` 行为。
- control doc、commit、push、PR、next gate。

## Motivation Check

两项 accepted finding 动机成立。

- P8-AGG-F1 的根因是 `ProjectionRunner._process_next_event()` 在构造 `ProjectionEventView` 时会先解析 `payload_json`，该点抛出的 `HostDurableError` 不属于 consumer apply failure，因此旧代码会回滚并透传到 caller，无法写入 `host_projection_failures`。这会让 corrupt / 手工修改的 EventLog row 卡住 projection 且缺少 durable 诊断。
- P8-AGG-F2 的根因是多 slice 中间 schema bump 泄漏到最终状态。Phase 8 plan 明确 fresh schema version 应从 4 bump 到 5；当前分支没有独立 schema 5 变更需要保留空洞版本。

## Fix Status

### P8-AGG-F1-已修复-ProjectionRunner payload parsing failure should record failure row

修复：

- 在 `ProjectionRunner` 内新增 `_ProjectionEventViewFailed` 内部控制流，只在 `projection_event_view_from_row(row)` 抛出 `HostDurableError` 时触发。
- `run_once()` 捕获该内部异常后写入 `host_projection_failures`，failure row 指向失败 EventLog row 的 `event_sequence` / `event_id`。
- 该路径不推进 checkpoint，不调用 consumer，不向 caller 透传 payload parsing `HostDurableError`。
- `_record_failure()` 改为接收 EventLog sequence / id，因此 consumer apply failure 与 view 构造 failure 复用同一个 durable failure 写入路径。

验证：

- 新增 `test_payload_parsing_failure_records_failure_without_advancing_checkpoint`，覆盖 `payload_json` 为非 object JSON 与非法 JSON 两种 EventLog row。
- 测试断言 `result.failures == 1`、checkpoint 保持 `0`、consumer 未被调用、failure row 指向失败 EventLog row，且错误码 / 错误消息来自 payload parse `HostDurableError`。

### P8-AGG-F2-已修复-Final Phase 8 schema version should align with plan version 5

修复：

- 将 `HOST_SCHEMA_VERSION` 从 `6` 改为 `5`。
- 更新 schema bootstrap 测试期望，fresh DB `PRAGMA user_version` 与 `HOST_SCHEMA_VERSION` 均为 `5`。
- 保留 Phase 8 projection / read model tables 在 `PROJECTION_TABLES` 与 `HOST_DURABLE_TABLES` 中，fresh bootstrap 仍创建 checkpoint、failure、RunResult、Session timeline tables 与对应 indexes。
- 同步修正 `dayu/host/durable/schema.py` 模块概览中关于当前 DDL 包含 Phase 8 projection / read model tables 的事实描述。

验证：

- `test_fresh_db_creates_foundation_and_phase8_tables` 继续断言 fresh bootstrap 创建 foundation、Phase 3 state、Phase 8 projection / read model tables。
- `test_projection_checkpoint_and_failure_tables_are_created` 继续断言 Phase 8 projection / read model tables、primary keys 与 indexes 存在。

## Documentation Decision

未更新 README。`rg` 检查未发现 README 或手册中存在 `HOST_SCHEMA_VERSION = 6`、`HOST_SCHEMA_VERSION == 6` 或 `PRAGMA user_version == 6` 的事实性陈旧描述；本次仅修正了 `schema.py` 模块概览中的代码内事实描述。

## Validation

已运行：

```bash
source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_public_event_stream.py tests/host/test_public_run_api.py tests/host/test_public_session_api.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

结果：`75 passed in 0.90s`。

```bash
source .venv/bin/activate && python -m pyright dayu/host tests/host
```

结果：`0 errors, 0 warnings, 0 informations`。

```bash
git diff --check
```

结果：通过，无输出。

补充窄验证：

```bash
source .venv/bin/activate && pytest tests/host/test_projection_runner.py tests/host/test_durable_schema.py -q
```

结果：`19 passed in 0.26s`。

## Residual Risks

- `get_run` 未消费 RunResult projection：按 controller adjudication，当前 fix gate rejected / deferred，owner 为 Phase 9 / Phase 15 或后续 public read enhancement owner。
- Automatic after-commit projection catch-up：deferred to Phase 9 owner。
- Heavy sink / batch-transaction runner：deferred to Phase 13 / Phase 15 owner。
- Per-session repair filter：deferred to Phase 15 owner。

## Completion

Phase 8 aggregate fix 的两个 accepted findings 均已修复并通过指定验证。本 artifact 只记录当前 fix gate 结果，不推进 commit、push、PR 或下一 gate。
