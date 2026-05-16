# Code Review

## Scope

- Mode: current changes
- Branch: `feat/host-phase8-projection-core-event-stream`
- Base: P8-S2 accepted commit `c891792`
- Output file: `docs/reviews/host-phase8-code-review-s3-mimo-20260516.md`
- Included scope: P8-S3 uncommitted workspace changes for minimal RunResult / Session timeline read model and repair helper
- Excluded scope: Engine, runtime, Service, UI, Fins, command path, dispatch, admission, waiting, recovery
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Detailed Analysis

### Schema / Store Invariants

- `HOST_SCHEMA_VERSION` 从 5 bump 到 6，与 P8-S2 accepted commit 一致。每新增一组表递增版本，符合 fresh schema 起库约定。
- `host_run_results` DDL 与 plan §3.3 完全一致：PK `run_id`、UNIQUE `terminal_event_id`、CHECK `terminal_status` 枚举、CHECK ref/digest 成对、FK 到 `host_runs`/`host_sessions`/`event_log`。
- `host_session_timeline_items` DDL 与 plan §3.4 完全一致：PK `timeline_item_id`、UNIQUE `event_id`、CHECK payload_ref/digest 成对、FK 到 `host_sessions`/`host_runs`/`event_log`。
- 三个索引与 plan 匹配：`host_run_results_session_terminal_sequence`、`host_session_timeline_items_session_sequence`、`host_session_timeline_items_run_sequence`（partial）。
- `PROJECTION_TABLES` 和 `HOST_DURABLE_TABLES` 正确包含新表。`HOST_DURABLE_DDL` 顺序正确：先表 DDL，后索引 DDL。
- Schema 测试覆盖新表创建、PK、索引存在性、invalid `terminal_status` 和 incomplete ref/digest pair 约束拒绝。

### Projection Consumer Idempotency / Conflict Behavior

- `insert_run_result_if_absent` 采用 read-then-insert 模式：先按 `run_id` 读取既有 row，不存在则 INSERT；存在且 terminal identity 匹配返回 DUPLICATE；存在但 terminal identity 不同抛出 `HostDurableError`。未使用 `INSERT OR REPLACE` 或静默 `ON CONFLICT DO UPDATE`。符合 plan §3.3 幂等不变量。
- `insert_session_timeline_item_if_absent` 按 `timeline_item_id` 读取，存在返回 DUPLICATE，不存在则 INSERT。符合 plan §3.4 幂等不变量。
- `MinimalReadModelProjectionConsumer.apply_event` 先投影 timeline item，若为 terminal event 再投影 RunResult。APPLIED/DUPLICATE 状态由两个 store 写入结果综合判定。

### Repair Two-Phase Batch Semantics

- `repair_minimal_read_models` 的 `reset_checkpoint=True` 路径先执行一个短 `run_write` 事务调用 `reset_minimal_read_model_projection`（清空 read model rows + checkpoint + failure），提交后再从 cursor 0 分批 replay。符合 plan §6 两阶段要求。
- Batch 循环：每批调用 `runner.run_once(consumer_id, limit=batch_size)`，失败或扫描不足 `batch_size` 时停止。已提交批次的 checkpoint 保留，下次 repair 从该 cursor 继续。符合 plan §6 中途失败不变量。
- Repair 不读取 RunResult / Session timeline 作为输入，只通过 `ProjectionRunner` 读取 EventLog。符合 plan §6 "Repair 不得读取 Session timeline 或 RunResult 作为输入"。

### display_text Typed Fallback

- `_display_text` 函数只对 `USER_INPUT_ACCEPTED` 调用 `optional_payload_text`；其它 event type 返回 `None`。
- `optional_payload_text` 在字段缺失或 `null` 时返回 `None`；字段存在但不是非空文本时抛出 `HostDurableError`。不会从 raw payload 拼接展示文本。符合 plan §2.5 P8-S3 payload stop check。

### Public Read Truth Boundaries

- `dayu/host/read_api.py` 未修改（diff 中无此文件）。`stream_run_events` 和 `get_run` 保持 EventLog / durable truth。
- 新增测试 `test_stream_run_events_ignores_missing_minimal_read_model` 和 `test_get_run_uses_durable_status_when_minimal_read_model_is_missing` 验证 read model 缺失不影响 public read API。
- 未新增 public timeline facade。`repair_minimal_read_models` 和 `MinimalReadModelProjectionConsumer` 不在 `dayu/host/api.py` 或 `dayu/host/__init__.py` 导出。

### Docs Sync

- `dayu/host/README.md`：新增 Phase 8 projection / minimal read model 说明段落；durable foundation 不实现列表删除了 `projection`（因为已实现）；测试覆盖列表新增 projection checkpoint / failure、minimal RunResult / Session timeline 投影、terminal 冲突失败、display_text 缺失 fallback、repair reset / replay / resume。符合 README 触发规则。
- `tests/README.md`：投影核心测试命令新增 `test_projection_read_model.py`；测试覆盖描述新增 minimal read model 相关条目。符合 README 触发规则。

### Type Strictness / Import Boundaries

- 新增文件 `dayu/host/durable/read_model.py` 和 `dayu/host/read_model.py` 使用 `from __future__ import annotations`，无 `Any`/`object`/裸容器注解。
- `test_import_boundary.py` 已将 `read_model.py` 和 `durable/read_model.py` 加入 `PROJECTION_MODULES`，确保不导入 Engine/Service/UI/Fins/Config。
- pyright 报告 39 errors，全部为 pre-existing `reportMissingImports`（pytest），与 P8-S3 无关。无新增类型错误。
- `read_model.py` 的 `__all__` 只导出 `MINIMAL_READ_MODEL_CONSUMER_ID`、`MinimalReadModelProjectionConsumer`、`ProjectionRepairResult`、`repair_minimal_read_models`，不暴露 `RunResultRow`/`SessionTimelineItemRow` 等 durable row 类型。

### Scope Creep

- `_event_payload.py`：仅新增 `optional_payload_text` typed helper，无 UI 展示逻辑。
- `durable/schema.py`：仅新增 read model 表 DDL、索引、常量、DDL tuple 更新。未修改已有表。
- 新增测试全部在 plan 允许的文件范围内。未修改 `dayu/host/api.py`、`dayu/host/__init__.py`、`dayu/host/read_api.py`（因 P8-S3 不需要新增 public type）。

## Open Questions

- 无。

## Residual Risk

- `test_public_event_stream.py` 和 `test_public_run_api.py` 各自定义了相同的 `_delete_minimal_read_model_rows` helper。未来若有第三个测试文件需要相同功能，建议抽取到共享 fixture。当前两个文件不构成阻塞问题。
- Repair batching 依赖 `ProjectionRunner.run_once(..., limit=batch_size)` 的现有 per-row transaction 语义。Implementation artifact 已记录该约束：P8-S3 未修改 `dayu/host/projection.py`，每条 EventLog row 独立 commit。长 consumer 场景留待 Phase 13 sink owner 关注。

## Conclusion

**PASS**。P8-S3 实现与 plan §3.3/§3.4/§6 的 schema、幂等、repair 不变量一致；public read truth 边界未被突破；display_text typed fallback 正确；import 边界和类型严格性通过；README 同步已完成。未发现阻塞性问题。
