# Phase 13 Slice 1 Code Review — AgentDS

## Gate

Phase 13 Slice 1 code review.

## Review Target

当前分支 `feat/phase-13-audit-trace-outbox` 相对 HEAD (`11c218b`) 的未提交 Slice 1 diff。

Implementation artifact: `docs/reviews/phase13-slice1-implementation-codex-20260529.md`
Accepted plan: `docs/host/phase13-audit-tool-trace-outbox-plan.md`
Controller adjudication: `docs/reviews/phase13-plan-rereview-controller-adjudication-20260529.md`

## Changed Files (Slice 1 scope)

| File | Status |
|---|---|
| `dayu/host/audit.py` | new |
| `dayu/host/durable/audit.py` | new |
| `dayu/host/durable/schema.py` | modified (v10 → v11) |
| `dayu/host/open_host.py` | modified |
| `tests/host/test_audit_sink.py` | new |
| `tests/host/test_durable_schema.py` | modified |
| `docs/reviews/phase13-slice1-implementation-codex-20260529.md` | new |
| `docs/host/implementation-control.md` | gate status only |

## Review Criteria Coverage

### C1: LogAuditSink 只消费 committed canonical EventLog

**PASS.**

`LogAuditSink.event_filter` (`audit.py:200-207`) 返回 `ProjectionEventFilter` 仅包含 `EventClass.CANONICAL_FACT`，不消费 `PREVIEW`、`DIAGNOSTIC` 或 `PROJECTION_SIGNAL`。测试 `test_jsonl_line_contains_required_audit_fields` 追加了一条 `PREVIEW` EventLog row，验证 JSONL 输出只有 1 行（canonical fact），preview 未被消费。

`apply_event` 通过 `read_event_by_id(transaction, event.event_id)` 在同一个 SQLite write transaction 内补读 `EventLogRow` 的 `actor`/`source`/`client_request_id` 字段。实现 artifact 已说明原因：`ProjectionEventView` 不暴露这些 durable-only 字段（检查 `projection.py:146-175` 确认属实）。读取的是 typed `EventLogRow`，不读取 raw `EngineEvent` 或 Service/UI state。

### C2: host_audit_sink_markers 只是 sink-local idempotency marker

**PASS.**

`durable/audit.py` 模块 docstring 明确声明："本模块只维护 `LogAuditSink` 的本地幂等 marker，用于避免普通 retry 重复写同一个 logical audit event。marker 不是 audit event store，不是 Host governance truth，也不提供 audit 查询能力。"

表结构（`schema.py:820-829`）仅包含 `event_id`（PK）、`event_sequence`、`line_digest`、`written_at`。不复制 audit 内容，不替代 JSONL 文件，不提供查询入口。

表命名为 `host_audit_sink_markers`（非 `host_audit_events` 或 `host_audit_records`），常量名为 `TABLE_HOST_AUDIT_SINK_MARKERS`，归类为 `AUDIT_PROJECTION_TABLES`。命名与结构均与计划中 "Optional `host_audit_sink_markers`" 一致。

### C3: JSONL append + marker/checkpoint 顺序

**PASS.** 跨介质原子性缺口是 accepted residual。

执行顺序（`audit.py:209-250` 的 `apply_event`）：

1. 读 marker → 已存在则返回 `DUPLICATE`（不写 JSONL）
2. 读 EventLog row → 缺失则抛 `HostDurableError`（transaction rollback）
3. 构建 audit line → 纯计算
4. **写 JSONL 文件**（在 SQLite transaction 内，但在 SQLite 介质外）
5. 写 marker（在 SQLite transaction 内）
6. ProjectionRunner 推进 checkpoint（在同一 SQLite transaction 内，`projection.py:598-606`）

**Normal retry 场景**：marker 存在 → DUPLICATE → checkpoint 仍推进（runner 对 DUPLICATE 也推进 checkpoint），不重复 append。

**File write 成功后 crash（步骤 4 成功，步骤 5-6 随 SQLite transaction rollback）**：marker 不存在 → retry 时重新 append → 物理 JSONL 出现重复 `event_id` 行。这是计划中明确接受的 P1 residual："JSONL 与 SQLite checkpoint 无法形成真正跨介质原子事务"。实现不假装解决 exactly-once，marker 只防 normal retry。

**File write 失败后**：异常传播 → `_ProjectionApplyFailed` → SQLite transaction rollback → `_record_failure` 在新 transaction 写 projection failure row → checkpoint 不推进。测试 `test_file_write_failure_records_projection_failure_without_checkpoint` 直接验证。

`insert_audit_sink_marker_if_absent` 内含 digest 冲突检测：若既有 marker 的 `event_sequence` 或 `line_digest` 与新行不一致，抛 `HostDurableError`。这是防御性 double-check，防止同一 `event_id` 在 retry 时 canonical encoding 不同导致的数据不一致。

### C4: File write / lock failure 只走 projection failure

**PASS.**

`_append_line` 内部可能抛出的异常类型：
- `OSError`：目录创建、文件打开或写入失败
- `RuntimeFileLockError` / `RuntimeFileLockTimeoutError`：lock acquire/release 失败

这些异常从 `apply_event` 未捕获，直接传播到 `ProjectionRunner._process_next_event` → 被 `run_once` 的 `except _ProjectionApplyFailed` 捕获 → SQLite write transaction rollback → `_record_failure` 在独立 write transaction 写入 projection failure row → checkpoint 不推进。

测试 `test_file_write_failure_records_projection_failure_without_checkpoint` 验证：
- `result.failures == 1`
- checkpoint 仍为 0（未推进）
- failure row 存在且 `failed_event_id` 正确
- marker 为 None

确认不写 command facts、不更新 Run/Attempt、不影响 EventLog。

### C5: open_host 接线

**PASS.** 未新增 `OpenHostOptions` public fields。

**未修改的部分**：
- `open_host(options)` public 签名不变
- `OpenHostOptions` 无新字段
- `HostCommandHandleOptions` 无新字段
- `HostLocalExecutionOptions` 无新字段
- Scheduler 仍接收 `memory_projection_catchup_port`（不变）
- Command path、admission、EventLog append、Run/Attempt state、terminal transaction、`watch_session_events` 代码零修改

**新增部分**：
- `_LogAuditProjectionCatchupPort`：模块私有，消费 `LogAuditSinkOptions`，从 `options.artifact_root` 派生默认路径
- `_CompositeProjectionCatchupPort`：模块私有，按序执行多个 catch-up port
- `_log_audit_sink_options_from_open_host_options`：模块私有 helper，不新增 public 参数
- `_default_audit_jsonl_path` / `_default_audit_lock_path`：模块私有路径派生函数

**Close flush 变更**：`_PublicHostHandle.close()` → `_CompositeProjectionCatchupPort` 按序执行 memory catch-up → audit catch-up。任一 port 失败会中断后续 port（直接透传异常）。这是 close 阶段的 best-effort flush，不影响 command path 成功条件。

**路径派生**：`artifact_root / "audit" / "host-audit.jsonl"`，与计划一致。lock 路径为同级 `.lock` 文件。

### C6: Schema bump to 11

**PASS.** Fresh-schema consistent。

- `HOST_SCHEMA_VERSION` 从 10 → 11
- `bootstrap_host_durable_store` 只接受 `user_version ∈ {0, 11}`
- 新增 `TABLE_HOST_AUDIT_SINK_MARKERS` 常量与 DDL
- 新增 `AUDIT_PROJECTION_TABLES` / `AUDIT_PROJECTION_DDL` tuple
- `HOST_DURABLE_TABLES` 和 `HOST_DURABLE_DDL` 包含 audit marker table
- Tests 覆盖：table 创建、PK (`event_id`)、FK constraint（引用 `event_log`）、CHECK constraint（`event_sequence > 0`）、schema version 确认
- `test_schema_does_not_create_unowned_future_sink_tables` 更新 docstring，仍验证不存在 `outbox`/`purge` 前缀表

### C7: 编码规范

**PASS.**

- 所有函数和模块均有中文 docstring，包含 `:param:` / `:returns:` / `:raises:`。
- 无 `object`、`Any`、无类型参数、无类型返回值。
- 无 `hasattr` / `getattr` 使用。
- 字段名使用模块级私有常量（`_AUDIT_FIELD_*`），无裸魔法字符串。
- `_PRINCIPAL_CLAIM_NAMES` 和 `_OPERATION_CONTEXT_REF_FIELDS` 为模块级常量。
- `cast` 仅用于 JSON 解析边界（`_json_value_from_text`、`_optional_mapping`），有充分理由。
- `AuditSinkMarkerWriteStatus` 使用 `StrEnum`。
- `LogAuditSinkOptions.__post_init__` 统一校验路径字段。

### C8: 测试覆盖

**PASS** with observations (see findings below).

覆盖项：
- JSONL 行完整字段集合（22 fields）+ line_digest 自洽性
- Preview 事件被 filter 排除
- Marker 去重防止 checkpoint replay 重复 append
- File write 失败 → projection failure + checkpoint 不推进 + marker 不写
- Audit sink 不修改 Run/Attempt/EventLog row count
- 默认路径派生
- Schema table 创建 / PK / FK / CHECK 约束
- Future sink table 不存在（`outbox`/`purge`）

## Findings

### DS-F1-未修复-[Minor]-lock 路径文件写测试缺失

**Evidence**: 所有 `LogAuditSink` 测试均使用 `lock_path=None`（`test_audit_sink.py:131,294,329`）。生产路径 `_default_audit_lock_path` 会设置 lock（`open_host.py:794`），但 `_append_line` 的 file lock context manager 分支（`audit.py:266-271`）从未在测试中被触发。

**Impact**: 若 `file_lock` 的 `create_parent_dirs`、`timeout`、或 lock release 行为有 regression，测试不会发现。对当前实现的影响有限，因为 `_append_line` 的 lock/no-lock 分支逻辑简单。

**Required change**: 不为阻塞项。建议 Slice 2 或后续补充至少一个 `lock_path` 非 None 的集成级测试。

### DS-F2-未修复-[Minor]-policy_decision_json 与 reason_json fallback 路径未覆盖

**Evidence**: `build_audit_json_line` 中 `_policy_decision_summary`（`audit.py:456-471`）和 `_reason_value`（`audit.py:474-487`）均有 fallback 逻辑：当 EventLog row 的 `policy_decision_json` / `reason_json` 为 `None` 时，从 payload 读取。当前测试 `test_jsonl_line_contains_required_audit_fields` 使用的 `_append_event` helper 始终传入 `policy_decision={"decision": "accepted"}` 和 `reason={"reason": "test"}`，两个 canonical JSON 字段非 None。payload fallback 路径未被覆盖。

**Impact**: 若既有 EventLog row 的 `policy_decision_json=None` 且 payload 中 `policy_decision_summary` 类型非法，该路径的错误处理未被测试验证。

**Required change**: 不为阻塞项。建议补充一条测试：EventLog row `policy_decision_json=None` + payload 包含 `policy_decision_summary` 字段。

### DS-F3-未修复-[Minor]-authorization_claims 多 claim type 未覆盖

**Evidence**: `test_jsonl_line_contains_required_audit_fields` 仅测试 `authorization_claims` 中 `{"name": "principal", "value": "analyst-1"}` 一条 claim。`_PRINCIPAL_CLAIM_NAMES` 包含 `{"principal", "subject", "user"}` 三种 claim name，但 `subject` 和 `user` 路径未测试。"第一个匹配 claim" 的优先级行为未显式验证。

**Impact**: 若实际 claims 数组中包含多条匹配 claim（如 `principal` 和 `subject` 同时出现），第一条被选取的行为无显式测试保护。

**Required change**: 不为阻塞项。建议补充测试 `authorization_claims` 包含多条 claim（含 `subject`、`user`）的 principal 抽取。

### DS-F4-未修复-[Minor]-catch_up_log_audit_sink_projection 无独立单元测试

**Evidence**: `catch_up_log_audit_sink_projection`（`audit.py:333-385`）是 `open_host` close flush 的入口函数，但无独立单元测试。现有测试均直接使用 `ProjectionRunner.run_once()`。

**Impact**: batch_size 边界、max_event_sequence 截断、多批次循环终止条件（`events_scanned < batch_size`）未被测试覆盖。

**Required change**: 不为阻塞项。当前 `open_host` close flush 走 single-batch call（`batch_size=128`），未触发多批次循环。若未来改用更大 batch_size 或 catch-up 需要多批，建议补充测试。

## Adversarial Failure Pass

### 场景 1: 并发 Process 写同一 audit JSONL

两个 Host process（如 recovery scan + live opener）同时写同一 `host-audit.jsonl`。file lock（通过相邻 `.lock` 文件）提供互斥，timeout 5 秒。若第二个进程超时，`RuntimeFileLockTimeoutError` → projection failure → checkpoint 不推进 → 后续 catch-up 重试。JSONL 行物理顺序不可预期（append on different fd），但每行 `event_id` 唯一，且 line_digest 可校验完整性。**不影响 Host truth**。

### 场景 2: File append 后进程 SIGKILL

File append 成功，marker + checkpoint SQLite transaction 未 commit。WAL 模式下未提交的写入不可见。下次 open_host 或 catch-up 时，marker 不存在，同一 `event_id` 重新 append → 物理 JSONL 出现两个相同 `event_id` 行。**这是 accepted residual**，计划明确声明 analyze/query 必须按 `event_id` 逻辑去重。

### 场景 3: Marker table 被外部删除

若运维误删 `host_audit_sink_markers` 行，checkpoint 仍在。catch-up 从 checkpoint cursor 开始，但所有 `event_sequence <= checkpoint` 的 EventLog row 已被扫描过（不在 `event_sequence > cursor` 范围内）。已写入 JSONL 的行不会丢失（JSONL 是 append-only），但新 open_host instance 的 close flush 可能遗漏。**影响有限**：catch-up 从 checkpoint 开始而非从头开始，已写的数据不丢，新数据正常 append。

### 场景 4: JSONL 文件权限变更

运行中文件被 `chmod` 为不可写。下次 `apply_event` → `OSError` → projection failure → checkpoint 不推进。后续所有 canonical fact 均卡在同一 failure point。**符合设计**：sink failure 不影响 command path，但 audit lag 会累积。需要外部监控 / 告警。

## Verdict

**PASS.**

Slice 1 实现严格遵循 accepted plan。无 blocking findings。四个 Minor findings 均为测试覆盖补充建议，不影响 correctness 和 architecture boundary enforcement。

Core guarantees 全部满足：
- LogAuditSink 只消费 committed canonical facts
- Marker 是 sink-local idempotency guard，不是 audit truth
- 跨介质 append 不假装 exactly-once
- File/lock failure 走 projection failure，不影响 command path
- open_host 不新增 OpenHostOptions 字段，不修改 governance
- Schema bump fresh-schema consistent

无 stop condition 触发。
