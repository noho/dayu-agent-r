# Host Phase 8 Aggregate Deep Review

## Scope

- **Mode**: current changes (aggregate of P8-S1, P8-S2, P8-S3)
- **Branch**: feat/host-phase8-projection-core-event-stream
- **Base**: main (commit `52bba89` in control doc)
- **Output file**: docs/reviews/host-phase8-aggregate-review-ds-20260516.md
- **Aggregate review gate**: Phase 8 aggregate deepreview, covering all accepted slice commits through HEAD `8b538f5`
- **Included scope**:
  - Production files: `dayu/host/projection.py` (new), `dayu/host/read_model.py` (new), `dayu/host/durable/projection.py` (new), `dayu/host/durable/read_model.py` (new), `dayu/host/durable/schema.py` (modified), `dayu/host/_event_payload.py` (modified)
  - Test files: `tests/host/test_projection_checkpoint.py` (new), `tests/host/test_projection_runner.py` (new), `tests/host/test_projection_read_model.py` (new), `tests/host/test_public_event_stream.py` (modified), `tests/host/test_public_run_api.py` (modified), `tests/host/test_durable_schema.py` (modified), `tests/host/test_import_boundary.py` (modified)
  - Doc files: `docs/host/phase8-projection-core-event-stream-plan.md` (new plan), `docs/host/implementation-control.md` (modified Phase 8 entries), `dayu/host/README.md` (minor), `tests/README.md` (minor)
  - Previous slice review artifacts in `docs/reviews/`
- **Excluded scope**:
  - `dayu/engine/**`, `dayu/runtime/**`, `dayu/service/**`, `dayu/ui/**`, `dayu/fins/**` — not touched
  - `dayu/host/command.py`, `dayu/host/dispatch.py`, `dayu/host/admission.py`, `dayu/host/waiting.py` — not modified, per plan non-goal
  - `dayu/host/read_api.py`, `dayu/host/api.py`, `dayu/host/__init__.py` — were in plan's allowed-file list but were NOT modified
  - Audit / Tool Trace / Outbox / Memory / Recovery — Phase 8 non-goals
- **Truth docs**: `docs/host/design.md` §14 (Observer / Sink / Projection), §16 (Read Model / Host Event Stream / Outbox); `docs/host/implementation-control.md` Phase 8; `docs/host/phase8-projection-core-event-stream-plan.md`
- **Review method**: full path tracing of all six production files; adversarial failure pass on checkpoint/repair/conflict/payload/cursor invariants; import boundary audit; type strictness audit; test coverage audit
- **Verification**: pyright 0 errors; 73 tests pass; git diff --check clean

## Result

**PASS** — 无阻塞性 finding。Phase 8 projection core / Host event stream / minimal read model 实现符合 plan 规定的全部不变式与 contract，可进入后续 gate。

## Findings

### P8-AGG-F1-未修复-低-`run_once` 对非 consumer 异常缺少防御性 failure 记录

- **入口/函数**: `ProjectionRunner.run_once` → `_process_next_event` → `projection_event_view_from_row`
- **文件(行号)**: `dayu/host/projection.py:372` catch 子句只捕获 `_ProjectionApplyFailed`；`dayu/host/_event_payload.py:367-373` `payload_object` 对非法 JSON 抛出 `HostDurableError`
- **输入场景**: EventLog 中存在 `payload_json` 不是合法 JSON 对象（如裸数组、裸标量、或损坏的 JSON 文本）的 row。正常路径下 Host 只写合法 JSON 对象，故触发概率极低；但 corruption、手动 DB 修改或罕见的 `json.dumps` 缺陷可触发。
- **实际分支**: `payload_object` 抛出 `HostDurableError` → 经由 `_process_next_event` → `run_write` rollback 并 re-raise → `run_once` 中 `except _ProjectionApplyFailed` 不匹配 → `HostDurableError` 透传到 caller
- **预期行为**: 对不可修复的 EventLog row 写入 failure row 并继续（或不推进 checkpoint 但记录诊断），避免调用方收到不可重试的透传异常
- **实际行为**: 调用方收到 `HostDurableError`，checkpoint 未推进，无 failure row 写入；下次 `run_once` 重试同一条 corrupt row 再次失败，无限循环
- **直接证据**: `dayu/host/projection.py:367-375` 的 except 子句只捕获 `_ProjectionApplyFailed`（line 286-304 定义），而 `_event_payload.py:367-373` 抛出的 `HostDurableError` 不在捕获范围内；`dayu/host/durable/transaction.py:258-260` 确认 `HostDurableError` 在 rollback 后透传
- **影响**: 极低概率的静默无限循环；正常生产中不会触发（Host 只写合法 JSON 对象），但 corruption 或手动操作后缺乏防御
- **建议改法和验证点**: 在 `run_once` 中增加对 `HostDurableError` 的捕获（或扩大 `except` 范围），将 payload 解析失败建模为 projection failure 写 failure row 并 break；验证 corrupt `payload_json` 能写入 failure row、不推进 checkpoint、调用方不收到透传异常
- **修复风险（低）**: 改动范围小，仅增加一层 except 并复用现有 `_record_failure`
- **严重程度（低）**: 极低触发概率；正常数据路径已通过 73 测试验证

### P8-AGG-F2-未修复-低-Schema 版本从 5 再 bump 到 6，与 plan "bump to 5" 文字不一致

- **入口/函数**: `dayu/host/durable/schema.py:24` `HOST_SCHEMA_VERSION`
- **文件(行号)**: `dayu/host/durable/schema.py:24`
- **输入场景**: 任何 fresh bootstrap；或 DB 在 P8-S1（版本 5）与 P8-S3（版本 6）之间创建
- **实际分支**: P8-S1 commit `80c12a2` 将版本从 4 bump 到 5；P8-S3 commit `d31803d` 将版本从 5 bump 到 6
- **预期行为**: Plan §3 规定 "fresh schema version bump 到 5"；若 implementation 前版本已变化应停止
- **实际行为**: 最终版本为 6。DB 在 S1 commit 与 S3 commit 之间以版本 5 创建后，运行 S3+ 代码会触发 `HostSchemaMismatchError`
- **直接证据**: `git show 80c12a2:dayu/host/durable/schema.py` 显示 `HOST_SCHEMA_VERSION = 5`；`git show d31803d:dayu/host/durable/schema.py` 显示 `HOST_SCHEMA_VERSION = 6`
- **影响**: Pre-production 状态，无实际部署影响；该偏差已在 P8-S3 code review 中通过 adjudication 接受
- **建议改法和验证点**: 可选回退到版本 5（S1 + S3 表均属于同一版本），或在 plan/control doc 中明确记录 sequential bump 为有意选择
- **修复风险（低）**: 改回版本 5 仅需改一行常量，且 `CREATE TABLE IF NOT EXISTS` 保证两 slice 的 DDL 在版本 5 下均正确执行
- **严重程度（低）**: 无 correctness 影响；仅与 plan 文字不一致，该偏差在 slice-level review 中已裁决

### P8-AGG-F3-已裁决-无修复-`get_run` 与 public read API 未消费 RunResult projection

- **入口/函数**: `dayu/host/read_api.py`（未修改）
- **文件(行号)**: 无代码变更
- **输入场景**: `get_run(run_id)` 调用
- **实际分支**: `get_run` 仍只读取 `host_runs` durable truth；不读取 `host_run_results` projection
- **预期行为**: Plan P8-S3 将其列为 "Optionally update `get_run` to use `host_run_results` for terminal summary refs while preserving durable Run status truth"
- **直接证据**: `git diff main...HEAD -- dayu/host/read_api.py` 无输出；`git diff main...HEAD -- dayu/host/api.py` 无输出
- **影响**: RunResult projection 已正确填充但无 public consumer；不影响 correctness（projection 仍可用于 Phase 9 Memory 和 Phase 15 hardening）
- **建议改法和验证点**: Phase 9 Memory owner 或 Phase 15 hardening owner 决定是否集成；建议 deferred
- **严重程度（已裁决）**: Plan 将其标记为 optional；实现 agent 选择不执行 optional 项属于正确判断

## Architecture Conformance

### 分层边界 ✅

- 所有 projection 模块（`projection.py`, `read_model.py`, `durable/projection.py`, `durable/read_model.py`）均不 import `dayu.engine`, `dayu.service`, `dayu.ui`, `dayu.fins`, `dayu.config`, `dayu.runtime`
- 均不 import `dayu.host.admission`, `dayu.host.waiting`, `dayu.host.engine_ingest`, `dayu.host.dispatch`, `dayu.host.recovery`
- `read_api.py` 不 import 任何 projection 模块、不包含 projection table 名称、不引用 repair helper — stream cursor 仍以 EventLog 为唯一真源
- `dayu.runtime` 未被修改
- `tests/host/test_import_boundary.py` 新增 `test_projection_modules_do_not_import_forbidden_layers_or_mutators` 和 `test_read_api_stream_does_not_reference_projection_or_fanout_truth` 共 2 个专项测试，均 PASS

### Projection 不成为治理真源 ✅

- `host_projection_checkpoints` / `host_projection_failures` table 仅由 `ProjectionRunner` 写入；不被 command path、admission、recovery、RunInputBuilder 读取
- `host_run_results` / `host_session_timeline_items` table 仅由 `MinimalReadModelProjectionConsumer` 写入；不被任何治理路径读取
- `stream_run_events` 仍直接读 EventLog；P8-S2 测试证明 projection lag / failure / missing read model 均不影响 stream 结果
- `get_run` 仍读 `host_runs` durable truth；未切换到 projection
- `repair_minimal_read_models` 只从 EventLog 重建；不读取 projection 作为输入 truth

### Checkpoint / 幂等 / 失败不变量 ✅

1. EventLog append 与 Run terminal 是 upstream truth；projection 只在 commit 后读取 ✅
2. Checkpoint cursor 为 `event_sequence`；幂等 identity 为 `event_id` ✅
3. Checkpoint advance 与 projection write 处于同一 `HostTransactionRunner.run_write()` transaction ✅
4. Duplicate event replay 通过 `event_id` / `terminal_event_id` identity upsert 防御 ✅
5. Consumer apply 失败时写 `host_projection_failures`，不推进 checkpoint ✅
6. Projection failure 不回滚 EventLog，不更新 Run/Attempt ✅
7. Projection lag 不改变 `stream_run_events` ✅
8. Read model stale/missing 时 public API 降级使用 durable state ✅
9. Repair helper 只从 EventLog replay ✅
10. Projection modules 不 import 禁止模块 ✅

### RunResult 冲突处理 ✅

- `insert_run_result_if_absent` (`dayu/host/durable/read_model.py:133-187`) 不使用 `INSERT OR REPLACE` 或会覆盖 terminal identity 的 `ON CONFLICT DO UPDATE`
- 同一 `run_id` 不同 `terminal_event_id` 时 raise `HostDurableError`，checkpoint 不推进
- 测试 `test_conflicting_terminal_event_records_failure_without_overwrite` 明确验证既有 RunResult 不被覆盖

### 空 display_text / 非字符串 display_text 防御 ✅

- `optional_payload_text` (`dayu/host/_event_payload.py:393-412`) 对非字符串、空字符串的 `display_text` 值抛出 `HostDurableError`
- `_display_text` (`dayu/host/read_model.py:320-333`) 只有 `USER_INPUT_ACCEPTED` 事件才读取 typed `display_text`；字段缺失返回 `None`
- 测试覆盖数字 display_text（`test_numeric_user_input_display_text_records_projection_failure`）和空字符串 display_text（`test_empty_user_input_display_text_records_projection_failure`）均记录 failure 且不写 timeline item

### Repair 路径 ✅

- `repair_minimal_read_models` (`dayu/host/read_model.py:163-221`) 两阶段执行：`reset_checkpoint=True` 时先用一个短事务清空 projection rows + checkpoint + failure；再分批 replay
- Each batch 使用独立 write transaction；checkpoint 在每批内推进
- Repair 中途失败后，已提交批次的 checkpoint 保留；下一次 repair 从该 checkpoint 继续（`test_repair_failure_resumes_from_last_committed_checkpoint` 验证）
- Repair 只接收 `HostTransactionRunner`，不持有 `HostCommandHandle`
- `ProjectionRepairResult` 强类型，包含 `consumer_id`, `started_cursor`, `finished_cursor`, `events_scanned`, `events_applied`, `duplicates`, `failures`

### SQLite FK 合规 ✅

- `event_log(event_sequence)` 为 `INTEGER PRIMARY KEY AUTOINCREMENT`，满足 SQLite FK parent key 要求（PRIMARY KEY 隐含 UNIQUE）
- `event_log(event_id)` 有 `UNIQUE` 约束，满足 FK parent key 要求
- DDL 中所有新增 FK 引用均指向 `event_log(event_id)` 或 `event_log(event_sequence)` 或 `host_runs(run_id)` 或 `host_sessions(session_id)`，均为已有 PRIMARY KEY 或 UNIQUE 列
- Plan §3 P8-S1 schema stop check 已在 S1 implementation 中验证通过

### 类型严格性 ✅

- 所有新增 dataclass 均为 `frozen=True, slots=True`
- 无 `Any`, `object`, 裸 `dict`/`list`/`tuple`/`set` 注解
- `ProjectionEventView.payload` 使用 `Mapping[str, JsonValue]`（来自 `dayu.contracts.json_value`）
- Consumer Protocol 使用 `Protocol` 而非 ABC，类型完整标注
- pyright: 0 errors, 0 warnings, 0 informations

### 无过度耦合 ✅

- Projection core 与 read model consumer 解耦：`ProjectionRunner` 通过 `ProjectionConsumer` Protocol 消费任意 consumer；`MinimalReadModelProjectionConsumer` 独立实现该 Protocol
- Checkpoint/failure store 与 read model store 分离为 `durable/projection.py` 和 `durable/read_model.py`
- Runner 不持有 SQLite connection；通过注入的 `HostTransactionRunner` 操作
- Phase 8 projection 不依赖 Phase 9 Memory、Phase 11 Recovery、Phase 13 sinks 的实现细节
- 无跨层穿透调用、双向依赖、共享可变状态

## Open Questions

- 无。所有 plan 规定的 contract 与不变式均已实现并通过测试验证。

## Residual Risk

1. **Corrupt EventLog payload 无防御性处理**（见 P8-AGG-F1）：极低触发概率，但缺少防御层。建议 Phase 15 production hardening 中补齐。
2. **RunResult / Session timeline 无 public consumer**：projection 数据已正确生成但无消费路径。Phase 9 Memory 或 Phase 15 需要决定集成方式。当前不影响 correctness。
3. **Automatic after-commit projection catch-up 未实现**：deferred 给 Phase 9 Conversation Memory composition。当前 projection 只能通过显式调用 `run_once`/`run_all_once`/`repair_minimal_read_models` 推进。Phase 9 需要将 after-commit hook 接到 runner wakeup port。
4. **Phase 9 Memory 若从 RunResult/timeline 读取数据，需重新验证 projection lag 不改变 memory truth**：当前已证明 projection 不成为 governance truth，但后续 phase 需要保持该约束。
5. **No audit/tool-trace/outbox consumers yet**：投影基础设施已就绪（checkpoint、typed consumer protocol、runner），但具体 sink 实现属于 Phase 13。Phase 13 必须在写入各自 projection table 前复用相同的 checkpoint/idempotency/failure invariant。
6. **`reset_minimal_read_model_projection` 使用 `DELETE FROM table`（无 WHERE 子句）**：`dayu/host/durable/read_model.py:292-293` 清理 `host_session_timeline_items` 和 `host_run_results` 时无 session-level filter。在多 Session 场景下，repair 的 reset 阶段会清空所有 Session 的 read model。若未来需要 per-session repair，需增加 session_id filter。当前 single-tenant local Host 场景下不影响 correctness。

## Deferred Items

| Item | Owner | Notes |
|------|-------|-------|
| `get_run` 消费 RunResult terminal summary | Phase 9 / Phase 15 | Plan 标记为 optional |
| Public timeline read API | Service / UI owner | Plan 明确禁止 Phase 8 新增 |
| After-commit wakeup for auto catch-up | Phase 9 Memory owner | Phase 8 提供 reusable runner primitive |
| Corrupt payload 防御处理 | Phase 15 hardening | 见 P8-AGG-F1 |
| Per-session repair filter | Phase 15 hardening | 见 Residual Risk #6 |

## Slice Review Coverage Summary

本 aggregate review 整合了以下 slice-level 双路 review 的结论：

- **P8-S1** (Projection Runner / Checkpoint / Typed Consumer Contracts): S1 code review (MiMo + DS) → fix → re-review → controller adjudication PASS
- **P8-S2** (Host Event Stream Cursor Truth): S2 code review (MiMo + DS) → controller adjudication PASS
- **P8-S3** (Minimal RunResult / Session Timeline / Repair): S3 code review (MiMo + DS) → fix → re-review → controller adjudication PASS

Aggregate review 未发现 slice-level review 遗漏的 blocking finding；已发现的 slice-level finding 均已通过 adjudication 接受或修复。
