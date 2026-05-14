# Host Phase 2 Durable Store / EventLog / Payload Foundation — Plan Review

## Review Gate Name

Phase 2 plan review — adversarial evidence-based review。

## Reviewed Target

`docs/host/phase2-durable-store-eventlog-plan.md`

## Design Truth / Context

| Artifact | Path | Role |
| --- | --- | --- |
| Host 架构真源 | `docs/host/design.md` §10 Durable Store, §13 EventLog, §13.1 Payload, §27 Host Lifecycle / Recovery | 架构语义真源 |
| 实施总控 | `docs/host/implementation-control.md` Phase 2 条目、已确认 durable foundation 决策、当前状态与追踪区 | Phase 边界与已确认决策 |
| Controller adjudication | `docs/reviews/gateflow-phase-design-re-review-host-p2-controller-adjudication-20260514.md` | BQ1-BQ5 裁决结果 |
| AgentMiMo re-review | `docs/reviews/gateflow-phase-design-re-review-host-p2-mimo-20260514.md` | BQ 修复验证 |
| AgentDS re-review | `docs/reviews/gateflow-phase-design-re-review-host-p2-ds-20260514.md` | BQ 修复验证 + 两个 observation |
| 术语真源 | `dayu/README.md` | 术语定义 |
| Phase 1 代码边界 | `dayu/host/__init__.py`, `dayu/host/api.py`, `dayu/host/tooling.py`, `tests/host/test_import_boundary.py`, `tests/host/test_package_exports.py` | 当前公共导出与 import boundary |

## Reviewer Conclusion

**Ready for plan re-review / user confirmation.**

Plan 是 handoff-ready 且 code-generation-ready 的。所有 material schema / transaction / storage policy / EventLog / idempotency / payload / liveness 决策均已明确到可直接生成 typed API、DDL、error types 和 tests。Phase 2 scope 严格停留在 durable foundation，未夹带 Session / Run / Attempt 状态机、Host command path、Engine dispatch、Projection、Memory、ToolRuntime、Remote transport、Recovery classifier、lease / fencing / takeover 或旧库兼容 migration。`dayu.runtime` 边界未被污染。Slices 有序、file-bounded、可独立验证。

发现 6 个 findings：0 blocker、0 high、0 medium、4 low、2 info。4 个 low findings 涉及 event_body_digest 字段集合、register 幂等措辞、heartbeat 错误语义和 WAL journal_mode 持久化验证；2 个 info findings 涉及 artifact temp 命名策略和 EventLog payload_ref FK 测试覆盖。这些问题均不阻塞 implementation agent 开始 Slice 1；建议在进入对应 slice 前确认或由 implementation agent 在 slice 内按 design.md 真源合理选择。

---

## Findings

### F1-未修复-LOW-event_body_digest 计算字段集合未显式枚举

**证据：**

- Plan §EventLog Row Typed Contract: "Append computes canonical JSON for structured fields and event_body_digest before insert." 和 §Risks: "Review should verify the digest input is canonical and excludes only database-assigned fields."
- Plan 未列出哪些 `EventLogAppendRequest` 字段进入 `event_body_digest` 的 canonical JSON 结构。
- Design.md §13 未定义 event_body_digest 的计算字段集合（design.md 未提及此字段）。

**分析：**

`event_body_digest` 用于区分 "duplicate event_id + same body → 返回既有行" 与 "duplicate event_id + different body → `HostEventIdentityConflictError`"。如果实现 agent 自行选择字段集合（例如包含或排除 `payload_json`、`policy_decision_json`、`reason_json`），不同实现选择会导致同一 event_id 在不同部署中被判定为 conflict 或 idempotent。

当前 plan 只说了 "excludes only database-assigned fields"（即 `event_sequence`、`appended_at`），这暗示所有 `EventLogAppendRequest` 字段都参与。实现 agent 大概率会以此为准，但显式列出字段集合可消除全部歧义。

**建议：**

Plan 应在 `EventLogAppendResult` 附近显式列出 `event_body_digest` 的输入字段集合，或明确声明"所有 `EventLogAppendRequest` 字段（排除 `event_sequence`、`appended_at` 两个 DB-assigned 字段）经 canonical JSON 序列化后计算 digest"。

**Controller Decision Status:** `pending-controller-decision`

---

### F2-未修复-LOW-register_current_instance 幂等语义使用非确定性措辞 "may"

**证据：**

- Plan §Host Instance Liveness Primitive Behavior: "if the same host_instance_id and same process_start_token already exists, it **may** idempotently refresh heartbeat_at and status running"

**分析：**

"may" 给实现 agent 两种选择：(a) 重复 register 是幂等 refresh，(b) 重复 register 报错。这两个选择语义不同：若选择 (b)，调用方必须在 register 前检查是否已存在。若选择 (a)，register 可用作启动时的无条件幂等注册。

host instance liveness 的调用方（后续 Phase 11 recovery）需要在启动时无条件 register。若此处不明确，后续 phase 可能需要对 register 做额外检查。

同一段落随后又说 "if same id exists with different process token, raise HostUniqueConstraintError or dedicated non-retryable conflict" — "or dedicated" 也给实现 agent 留下了在两个错误类型间选择的余地。

**建议：**

将 "may" 改为 "MUST"，明确 register 对同 identity 是幂等 refresh。同时统一错误类型选择（建议用专用错误如 `HostInstanceIdentityConflictError` 而非复用 `HostUniqueConstraintError`）。

**Controller Decision Status:** `pending-controller-decision`

---

### F3-未修复-LOW-heartbeat_current_instance 对缺失/不匹配行的错误语义未指定

**证据：**

- Plan §Host Instance Liveness Primitive: `heartbeat_current_instance(transaction, identity, now) -> HostInstanceRow`
- 返回类型是 `HostInstanceRow` 而非 `HostInstanceRow | None`，暗示缺失时必抛异常。
- Plan Behavior 段只说 "Heartbeat updates only row matching current host_instance_id and process_start_token; it must never refresh another instance." 未说明行不存在时是抛异常、返回 None 还是静默跳过。
- 对比 `mark_current_instance_stopping` 和 `mark_current_instance_stopped` 的返回类型是 `HostInstanceRow | None`，并明确 "if row is absent, return None rather than inventing a record."

**分析：**

heartbeat 和 mark_stopping/mark_stopped 对缺失行的语义不同是合理的（heartbeat 缺失意味着调用方未先 register，是编程错误；mark_* 缺失可能是因为实例已通过其他路径被清理）。但 plan 未显式说明 heartbeat 缺失行的行为，实现 agent 需要自行判断。

**建议：**

在 heartbeat behavior 段明确：行不存在或不匹配时抛 `HostDurableError` 子类错误（或复用 `HostUniqueConstraintError` 等）；不得返回 None 或静默跳过。

**Controller Decision Status:** `pending-controller-decision`

---

### F4-未修复-LOW-WAL 启用后未要求验证 journal_mode 持久化

**证据：**

- Plan §Transaction Runner Typed API: "write transaction uses `BEGIN IMMEDIATE`"
- Plan §Schema Convention: "启用 WAL"
- Plan §Slice 1 tests: "connection has `foreign_keys=ON` and WAL enabled"
- Plan 未要求测试验证 `PRAGMA journal_mode=wal` 在连接重开后仍然生效。

**分析：**

`PRAGMA journal_mode=wal` 是持久化设置（设置在 DB 文件头中），一旦设置永久生效。但如果 connection.py 的实现使用了 `PRAGMA journal_mode=wal` 而非检查已有设置，问题不大。但如果实现只在每次连接时设置而不验证，且某些边界条件下 WAL 被关闭（例如 VACUUM 后），可能导致静默回退到 DELETE journal mode。

测试 "connection has WAL enabled" 覆盖了连接后检查。但建议同时覆盖"第二个独立连接打开同一 DB 后 journal_mode 仍为 wal"以确保是持久化设置而非 per-connection 设置。

**建议：**

在 `test_durable_schema.py` 中增加一个断言：用第二个独立连接打开同一 DB 文件，验证 `PRAGMA journal_mode` 返回 `wal`。

**Controller Decision Status:** `pending-controller-decision`

---

### F5-未修复-INFO-artifact temp 文件命名策略未指定

**证据：**

- Plan §Artifact write ordering: "Write temp file under artifact root temp area."
- Plan 未指定 temp 文件命名策略（UUID？hash？timestamp+pid？）。
- Plan 未指定 artifact root 下的 temp 目录结构（`<artifact_root>/.tmp/`？`<artifact_root>/tmp/`？）。

**分析：**

这是实现细节，不影响架构正确性。但如果多个 Host 进程共享同一 artifact root（例如测试中），temp 文件命名冲突可能导致非确定性测试失败。实现 agent 使用 `tempfile.mkstemp` 或 UUID 是合理的默认选择。Plan 级别的 `PayloadStoragePolicy` 已经有 `artifact_root` 注入，temp 目录可约定为 `<artifact_root>/.tmp/`。

**建议：**

非阻塞。实现 agent 可在 `LocalArtifactStore` 文档中说明 temp 命名策略，并在 multi-process 测试中验证无冲突。

**Controller Decision Status:** `pending-controller-decision`

---

### F6-未修复-INFO-EventLog.payload_ref FK 约束违规缺少显式测试

**证据：**

- Plan §Slice 3 tests for payload: "descriptor with missing sqlite payload FK fails as foreign key error."
- Plan §Slice 3 tests for payload: "EventLog append can reference an existing descriptor and payload digest."
- Plan 未要求测试 "EventLog append 引用了不存在的 payload_ref"。

**分析：**

`event_log.payload_ref` 有 `FOREIGN KEY(payload_ref) REFERENCES payload_descriptors(payload_ref)`。如果 append EventLog 时传入不存在的 `payload_ref`，SQLite 应抛出 foreign key 错误并被包装为 `HostForeignKeyError`。当前测试只覆盖了 `payload_descriptors.sqlite_payload_id` 的 FK，未覆盖 `event_log.payload_ref` 的 FK。这属于同一类错误路径，覆盖度略低但不影响正确性设计。

**建议：**

在 `test_payload_store.py` 或 `test_event_log_store.py` 中增加一条测试：append EventLog 时引用不存在的 payload_ref，断言抛 `HostForeignKeyError` 且不被 transaction runner retry。

**Controller Decision Status:** `pending-controller-decision`

---

## Scope Enforcement

对 plan 逐项检查是否夹带 Phase 3+ 内容：

| 检查项 | 是否出现 | 证据 |
| --- | --- | --- |
| Session / Run / Attempt 状态机 | 否 | Schema 不含 Session/Run/Attempt tables；Non-goals 显式排除 |
| Host command path | 否 | Non-goals 显式排除 `start_run`、`submit_followup` 等 |
| Engine dispatch | 否 | Non-goals 显式排除 |
| Projection / Observer / Sink | 否 | Non-goals 显式排除 |
| Memory | 否 | Non-goals 显式排除 |
| ToolRuntime / TruncationManager | 否 | Non-goals 显式排除 |
| Remote transport | 否 | Non-goals 显式排除 |
| Recovery classifier / positive orphan proof | 否 | Liveness primitive 显式标注只做 register/heartbeat/mark/read；不做 orphan classifier |
| Lease / fencing / takeover | 否 | Liveness primitive 显式标注无 lease/fencing/takeover；Non-goals 再次确认 |
| 旧库兼容 migration | 否 | Schema convention 显式 fresh bootstrap only |
| `dayu.runtime` 承载 Host durable truth | 否 | Plan §Namespace And Public Boundary 显式声明 `dayu.runtime` 不承载 Host durable truth |
| `dayu.host` 包根新增 durable 导出 | 否 | Plan §Namespace And Public Boundary 显式声明不修改 `dayu.host.__all__` |

无 Phase 3+ scope creep。

## Architecture Boundary Verification

### UI -> Service -> Host -> Engine 分层

- `dayu.host.durable` 是 Host 内部子包，不向 `dayu.host` 包根导出。✓
- 不修改 `dayu.runtime`。✓
- 不修改 `dayu.engine`。✓
- 不修改 `dayu.service`、`dayu.ui`、`dayu.fins`。✓
- 禁止修改文件列表与 Non-goals 一致。✓

### dayu.runtime 边界

- Plan §Namespace And Public Boundary: "`dayu.runtime` 不承载 Host durable truth。`dayu.runtime.lane` 继续只表达 runtime capacity claim；`dayu.runtime.filelock` 继续只用于普通文件互斥，不用于 SQLite / EventLog truth。" ✓
- Plan §Non-Goals: "将 Host durable truth、EventLog ordering、idempotency、payload descriptor 或 host liveness 放入 `dayu.runtime`" 明确不做。✓
- Plan §Stop Conditions: "Stop if transaction runner requires moving code to `dayu.runtime`" 和 "Stop if multi-process append requires using `dayu.runtime.lane` or file locks for EventLog ordering" 有明确的停止护栏。✓

### Host durable truth ownership

- Durable truth 在 `dayu.host.durable` 内部。✓
- EventLog 的 `event_sequence` 是 Host 分配的全局 cursor，不由远端或 runtime 替代。✓
- Host instance liveness 明确标注不是 lease/fencing/Attempt owner。✓

### 现有约束兼容性

- `tests/host/test_import_boundary.py` 使用 AST 扫描所有 `dayu/host/` 下的 `.py` 文件，检查不得 import `dayu.engine`/`dayu.fins`/`dayu.service`/`dayu.ui`。新增 `dayu/host/durable/` 模块自动被覆盖。✓
- `tests/host/test_package_exports.py` 验证 `dayu.host.__all__` 不变。Plan 要求修改此测试确认 durable foundation 不进入 `dayu.host.api.__all__`。✓

## Schema / Contract / API Readiness Assessment

### 可直接生成代码的部分

| 组件 | DDL | Typed Dataclass | Typed Function | Error Types | Tests |
| --- | --- | --- | --- | --- | --- |
| Schema bootstrap | ✓ (完整 table DDL + PRAGMA) | — | ✓ (bootstrap/validate) | ✓ (HostSchemaMismatchError) | ✓ |
| Transaction runner | — | ✓ (StoragePolicy, Transaction, Runner) | ✓ (run_write) | ✓ (BusyError, RetryExhaustedError, AfterCommitError) | ✓ |
| EventLog | ✓ (event_log table) | ✓ (AppendRequest, Row, Result) | ✓ (append_event, read_event_by_id, read_events_after) | ✓ (EventIdentityConflictError) | ✓ (含 multi-process) |
| Idempotency | ✓ (idempotency_records table) | ✓ (Scope, ResultRef, Record) | ✓ (record, read) | ✓ (IdempotencyConflictError) | ✓ |
| Payload descriptor | ✓ (sqlite_payloads + payload_descriptors tables) | ✓ (Kind, Format, WriteRequest, Descriptor) | ✓ (write_sqlite_payload, write_for_artifact, read) | ✓ (DigestMismatchError, PayloadReferenceError) | ✓ (含 artifact orphan window) |
| Artifact | — | ✓ (LocalArtifactRef) | ✓ (write_artifact_bytes) | ✓ (DigestMismatchError, ArtifactWriteError) | ✓ (含 crash window) |
| Host instance liveness | ✓ (host_instances table) | ✓ (Status, Identity, Row) | ✓ (register, heartbeat, mark, read) | — (见 F2, F3) | ✓ |
| Codec | — | — | ✓ (canonical_json_dumps, format_utc_timestamp, sha256_digest_*) | — | ✓ |

### 实现 agent 仍需自行决定的点

1. `event_body_digest` 字段集合（见 F1）— 风险低，design.md 和 plan 给出了"排除 DB-assigned 字段"的方向。
2. `register_current_instance` 幂等性措辞（见 F2）— 风险低，意图清晰。
3. `heartbeat_current_instance` 缺失行错误类型（见 F3）— 风险低，可从返回类型推断。
4. Artifact temp 命名策略（见 F5）— 实现细节，非架构决策。
5. `HostDurableStore` 的完整字段（持有 connection、transaction runner、各 store）— plan 已给出 `open_host_durable_store` 工厂函数签名和各 store 的依赖关系。

## Slice 切分验证

### Slice 1: Schema + Transaction Runner

- **Bounded**: 7 production files + 2 test files。Schema DDL 覆盖全部 5 个 foundation tables，但行为测试仅限于 schema 和 transaction 层面。✓
- **Ordered**: 后续 slices 依赖 transaction runner 和 schema。✓
- **Independent verification**: 可以通过 bootstrap tests、transaction atomicity tests、error classification tests 独立验证。✓
- **Stop conditions**: 明确（schema 需要 Session/Run/Attempt tables、transaction runner 需要移到 runtime、retry 分类不能区分 busy vs integrity errors）。✓

### Slice 2: EventLog + Idempotency

- **Bounded**: 2 production files + 3 test files。✓
- **Ordered**: 依赖 Slice 1 的 transaction runner 和 schema。✓
- **Independent verification**: 可以通过 append/read tests、idempotency tests、multi-process smoke 独立验证。✓
- **Stop conditions**: 明确（appender 需要 Run/Attempt state indexes、idempotency scope 需要 command path、multi-process 需要 lane/filelock）。✓

### Slice 3: Payload + Artifact + Liveness + README

- **Bounded**: 3 production files + 3 test files + 2 README files。Payload 和 artifact 紧密耦合，liveness 独立但小。✓
- **Ordered**: 依赖 Slice 2 的 EventLog（payload_ref 引用）和 transaction runner。✓
- **Independent verification**: 可以通过 payload CRUD tests、artifact crash window tests、liveness CRUD tests 独立验证。✓
- **Stop conditions**: 明确（需要 ToolRuntime/Fins storage/trace、liveness 需要 dispatch record/recovery classifier）。✓

所有三个 slices 满足"file-bounded、有序、可独立验证"的约束。Slice 3 合并了三个子功能但它们在语义上同属"扩展 Slice 2 的 EventLog 引用 + 独立 liveness primitive"，内聚性合理。

## Test Coverage Assessment

### 覆盖的關鍵路径

- Schema bootstrap（fresh、幂等、mismatch）✓
- Transaction atomicity（commit、rollback、after-commit only on commit）✓
- After-commit callback failure after commit（row remains committed）✓
- Busy/locked retry（finite retry、structured error on exhaustion）✓
- Non-retryable errors（unique constraint、FK、schema mismatch、digest mismatch、idempotency conflict）✓
- EventLog append monotonic event_sequence ✓
- Duplicate event_id with same/different body digest ✓
- Multi-process concurrent append ✓
- Idempotency same key same digest / same key different digest ✓
- Payload inline + descriptor write ✓
- Artifact write ordering + crash window ✓
- Host instance register / heartbeat ownership / stopping / stopped ✓
- README trigger check ✓

### 未覆盖或覆盖不足的路径

- EventLog append with non-existent payload_ref FK（见 F6）— 低风险
- Heartbeat on unregistered instance（见 F3）— 低风险，但可从返回类型推断行为
- WAL journal_mode 跨连接持久化验证（见 F4）— 低风险
- `payload_inline_threshold_bytes` 边界值测试（恰好等于 threshold、刚好超过）— 实现细节
- `HostAfterCommitError` 聚合行为（多个 after-commit callbacks 中部分失败）— plan 给了实现选择空间

## Open Questions / Residual Risk

### 已解风险（plan 已覆盖或已 defer）

1. **SQLite + external artifact 非原子写入**：Plan §Risks 明确接受，Slice 3 必须测试 crash window。✓
2. **HostAfterCommitError 后 caller 看到异常但数据已 durable**：Plan §Risks 明确标注，要求 tests 和 docs 让后续 command path 知道此语义。✓
3. **Multi-process tests 时序敏感性**：Plan §Risks 建议围绕不变式而非精确 sleep count。✓
4. **payload_inline_threshold_bytes 默认值可覆盖**：Plan §Risks 明确是 plan-level default 可通过 options 覆盖。✓
5. **Artifact orphan cleanup 策略后置**：Plan Non-blocking Questions 明确 defer 到后续 cleanup/diagnostics work unit。✓

### 持续追踪风险（不阻塞 plan gate）

1. **host instance liveness 被后续 phase 误用为 lease/fencing**：Plan 在 liveness primitive、non-goals 和 risks 中多次明确禁止。Phase 11 的 plan review 需要二次验证。追踪到 `docs/host/implementation-control.md` 追踪区。

2. **event_body_digest 计算与未来 projection checkpoint 的关系**：Projection 按 `event_sequence` cursor 追平，不依赖 `event_body_digest`。但如果未来 audit replay 需要验证 EventLog 完整性，`event_body_digest` 的字段集合会影响验证结果。当前无影响。

3. **Multi-process concurrent append 的性能上限**：Plan 接受 SQLite WAL + busy timeout + retry 的策略。`docs/host/implementation-control.md` 追踪区已明确"性能容量只有在压测或生产观察证明明显后才升级为容量治理问题"。

## Controller Decision Status

All findings: `pending-controller-decision`

Summary:

| Finding | Severity | 阻塞 Slice | 建议动作 |
| --- | --- | --- | --- |
| F1 event_body_digest 字段集合未枚举 | LOW | Slice 2 | 在进入 Slice 2 前确认字段集合或由实现 agent 按 "排除 DB-assigned 字段" 原则自行确定 |
| F2 register 幂等措辞 "may" | LOW | Slice 3 | 改为 MUST；统一错误类型 |
| F3 heartbeat 缺失行错误语义 | LOW | Slice 3 | 明确抛异常及错误类型 |
| F4 WAL journal_mode 持久化验证 | LOW | Slice 1 | 增加跨连接 journal_mode 断言 |
| F5 artifact temp 命名策略 | INFO | Slice 3 | 实现细节，不阻塞 |
| F6 EventLog payload_ref FK 测试 | INFO | Slice 3 | 增加 FK violation 测试 |

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p2-durable-store-eventlog-ds-20260514.md`
