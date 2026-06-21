# WU-RET-00 Host Storage Lifecycle Retention Policy — Plan

- work unit: WU-RET-00 Host Storage Lifecycle Retention Policy
- owner / destination: GitHub Issue #43（OPEN，storage lifecycle / retention umbrella）
- gate: plan（仅本 gate；不进入 implementation）
- 设计真源: `docs/host/design.md`、`docs/engine/design.md`
- 总控真源: `docs/host/issues-implementation-control.md`
- branch: `work/wu-ret-00-retention`（非 protected trunk）
- artifact path: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`

---

## 1. Goal / Motivation / Success Signal

### Goal

为 Host 长期运行补上 storage lifecycle 的**安全底座**，最小正确闭环只解决三件事：

1. **operator-visible storage usage report**：operator 能在不修改任何状态的前提下，看到 Host durable 存储各 owner 分类的占用（EventLog rows、payload descriptors、SQLite payload bytes、artifact logical bytes、各 projection table rows、DB / WAL 文件字节、orphan 诊断计数）。
2. **payload descriptor / SQLite payload / artifact ref 的安全删除证明**：提供 reference-checked 的只读删除证明原语，并用测试覆盖共享引用与 projection lag 场景；据此安全回收当前**永久泄漏的 orphan artifact 文件**。
3. **慢维护不进入 command path**：把文件扫描、orphan 文件回收、WAL checkpoint、物理 size 统计收敛到一个显式 maintenance entrypoint，明确它不得在 EventLog append / admission / cancel / resume / terminal closeout 中执行。

### Motivation（第一性原理 + 直接证据）

- **真实存在的泄漏（root cause，逻辑/数据同源）**：`purge_session_durable(...)` 在同一 SQLite transaction 内删除目标 Session 的 descriptor / SQLite payload row，并把"已确认不再被 durable row 引用"的本地 artifact 相对路径放进 `PurgeSessionDeleteResult.cleanup_refs.artifact_relative_paths`（`dayu/host/durable/purge.py:758-786`）。但 `purge_session(...)` 命令路径（`dayu/host/command.py:769-897`）**只读取 `result.tombstone`，从不消费 `result.cleanup_refs`**。仓库内除 `purge.py` 自身外无任何 `cleanup_refs` / `artifact_relative_paths` 消费者，Host 内唯一的 `.unlink()` 是 artifact 写入的 temp 清理（`dayu/host/durable/artifact.py:220`）。→ **purge 成功后，被删除 descriptor 对应的本地 artifact 文件永久遗留在 artifact root 上，没有任何代码删除它。**
- **第二来源的泄漏**：`docs/host/design.md:1445` 明确"SQLite transaction 无法原子覆盖外部文件系统写入；artifact 发布必须先于 EventLog canonical append。若 SQLite transaction 后续失败，已发布但未被 descriptor 引用的 artifact 只能作为后续 cleanup / diagnostics 处理"。即设计已承诺有一条 cleanup 路径来回收这些 publish-before-commit 残留，但当前代码尚未实现。
- **没有可观测面**：仓库内不存在 `storage_lifecycle` / `StorageUsageReport` / `report_storage_usage` / `run_storage_maintenance` 任何实现（已 grep 确认）。`PurgeDeleteCounts`（`purge.py:163-245`）只是 purge 的副作用计数，operator 无法主动查询当前存储占用。
- **慢维护原语已存在但未投影给 operator**：`run_host_wal_checkpoint(...)`（`dayu/host/durable/maintenance.py:62`）只被测试调用（`tests/host/test_durable_connection.py`），不是 Service-facing maintenance API。

### Success Signal

- operator 可调用一个只读入口拿到 `HostStorageUsageReport`，覆盖控制文档验收信号枚举的 owner 分类与 DB / WAL size。
- payload descriptor / SQLite payload / artifact ref 的删除证明有 reference-checked 原语 + 测试覆盖，尤其**共享引用**（两个 descriptor 指向同一 content-addressed artifact 文件）与 **projection lag**（descriptor 仍被 timeline / run_results / memory / tool_trace / outbox 引用）两类场景。
- 当前永久泄漏的 orphan artifact 文件能被一个显式 maintenance entrypoint 安全回收（content-addressed-safe 证明 + grace window + 删除前 recheck + containment 守卫）。
- maintenance entrypoint 不出现在 command path；文件扫描 / 文件删除 / WAL checkpoint 只在该 entrypoint 内执行。
- 回收/报告不改变 Host recovery、retry、replay、RunInputBuilder、memory projection、analyzer 直接证据；不引入 schema 变更。

---

## 2. Non-Goals / Scope Boundary

明确**不做**（避免过度设计；与总控 goal confirmation 裁决一致）：

- **不重做 `purge_session`**：session-scoped destructive cleanup 已完成且正确，本 WU 不改写 purge 的 SQLite 删除事务语义。
- **不实现 scheduled retention scheduler**：不引入周期 GC、后台线程、定时触发器。回收只在 operator 显式调用 maintenance entrypoint 时发生。
- **不实现 time-window / user / workspace / run-scope 自动 hard delete**：本 WU 不裁决"chat/session history 在手动 purge 之外按时间/用户/workspace 自动删除"——只回收**已无任何 durable 引用的 orphan 物理文件**，不按业务维度删除仍被引用的 Session 数据。
- **不实现完整 DB vacuum 平台**：不做 `VACUUM` / `PRAGMA incremental_vacuum` / auto-vacuum 策略。DB 维护本 WU 只复用既有 `run_host_wal_checkpoint` + 暴露 DB/WAL size 诊断；SQLite vacuum / space reclamation 的后续 owner 是 GitHub Issue 76。
- **不实现 Tool Trace cold JSONL governance**（rotation / retention / compaction / size reporting）——归 WU-RET-01 / #36。
- **不实现 Audit JSONL governance**（rotation / retention / compaction / size reporting）——归 WU-RET-02 / #96。
- **不在 command path 做任何慢 cleanup / 文件扫描 / VACUUM**（控制文档非目标硬约束）。
- **不静默删除**仍被 EventLog / payload descriptor / projection / audit / trace / analyzer 需要的 artifact。
- **不把 credential scrub 与 retention / deletion 混为一谈**。
- **不引入 `dayu.fins.storage` 变更**：财报文档存取与本 WU 无关。
- **本 WU 不删除 orphan SQLite payload row**（仅检测+报告，理由见 §7）；不删除 purge 现有 `cleanup_refs` 字段（避免触碰 89KB 中心 purge 路径，见 §11 residual）。

---

## 3. Design Document Alignment

| 设计真源条目 | 对齐说明 |
| --- | --- |
| `design.md:1435-1453`（13.1 Payload 存储） | descriptor 区分 `sqlite_payload` 与本地 `artifact_ref`；artifact 内容寻址发布。本 WU 的 usage report 与 orphan 证明完全基于既有 descriptor / payload 字段读取，不改 payload 写语义。 |
| `design.md:1445`（publish-before-commit 残留） | 设计已承诺"已发布但未被 descriptor 引用的 artifact 作为后续 cleanup / diagnostics 处理"。本 WU 实现这条被承诺但缺失的 cleanup 路径，且只回收**无任何 descriptor 引用**的文件。 |
| `design.md` Purge = 唯一 destructive EventLog retention exception | 本 WU 不向 command path 增加 destructive EventLog 行为；orphan 文件回收是 artifact root 文件系统操作，不删除任何 canonical fact / 派生 row。 |
| `design.md` public Host API / maintenance boundary | 本 WU 会新增 operator-facing report / maintenance public surface，属于 Host public contract 的稳定边界。实现期必须在 `docs/host/design.md` 增补最小设计说明：maintenance entrypoint、content-addressed-safe artifact deletion proof、grace + recheck + containment、非 command-path 边界，以及 DB VACUUM deferred to Issue 76。 |
| Host durable truth vs projection/read model 边界（README:29） | report 只读 durable truth + 派生 row 计数；不把 storage 调度状态伪装成业务事实。maintenance entrypoint 不反向驱动 Run/Attempt 状态。 |
| 分层 `UI -> Service -> Host -> Engine` | 新增 durable 原语在 `dayu/host/durable/`（Host 内部），Host facade 在 `dayu/host/`，async wrapper 在 `open_host`。无反向依赖，不 import service/ui/fins/engine/runtime 越界。 |
| command path 边界（README:317 admission 写边界） | report / maintenance 都不经 admission，不写 canonical facts；maintenance 用独立 connection 执行 checkpoint，显式标注禁止在 command transaction 内调用。 |

Engine 设计（`docs/engine/design.md`）与本 WU 无接口耦合：Engine 不导入 Host、不读 durable store。已确认无需 Engine 侧改动。

---

## 4. First-Principles Judgment and Direct Code Evidence

### 4.1 判断：WU 成立，但最小正确闭环 ≠ 完整自动保留系统

- purge 已实现 session-scoped destructive cleanup（`purge.py:690 purge_session_durable`，`command.py:769 purge_session`）。重做它没有动机。
- 真实未闭合的是**存储生命周期安全底座**：可观测、可证明的安全删除、慢维护隔离。直接证据见 §1 Motivation。

### 4.2 关键安全洞察：content-addressed 共享使"按 payload_ref 推导删文件"不安全

- artifact 相对路径由内容 digest 决定：`_artifact_relative_path_for_digest(digest)` 生成 `sha256/<shard>/<digest_hex>`（`artifact.py:135-147`）。→ **两个不同 `payload_ref` 的 descriptor，只要内容相同，就指向同一个物理文件。**
- purge 的 `cleanup_refs` 仅证明"被删 descriptor 的 `payload_ref` 不再被 reference 列引用"（`_payload_ref_is_still_referenced`，`purge.py:1914-1934`，扫描 `_payload_reference_columns()` = event_log / timeline / run_results(result_ref,summary_ref) / memory_items / tool_trace_hot / outbox(result_ref,terminal_summary_ref)，`purge.py:1957-1972`）。它**不证明**"该 artifact 相对路径不被其它存活 descriptor 引用"。
- 结论：**任何 artifact 物理文件删除的安全证明，必须是"无任何存活 `payload_descriptors` row 的 `artifact_relative_path` 等于该路径"**，而不是"某个 payload_ref 被删了"。这正是本 WU 必须新建的删除证明原语，也是它不是 trivial 的根因。

### 4.3 直接证据清单（文件:行）

- 泄漏：`command.py:769-897`（purge 命令不消费 cleanup_refs）；`purge.py:758-786`（cleanup_refs 计算）；grep 确认无外部消费者；`artifact.py:220`（唯一 unlink 是 temp）。
- content-addressed：`artifact.py:135-147`。
- 引用边登记：`purge.py:1957-1972`、`1914-1954`。
- 既有 checkpoint 原语：`maintenance.py:62-105`，仅测试调用。
- descriptor / payload 字段：`payload.py:88-112`（`PayloadDescriptor`：`payload_kind` / `payload_size_bytes` / `sqlite_payload_id` / `artifact_relative_path`）；schema 表常量 `schema.py:37-59`。
- 无 schema 外键级联：报告/证明只读既有列，回收只删文件，**无 schema 变更**。
- facade 既有先例：`read_api.py` 用 `host._run_read(...)`（`read_api.py:98,110,...`）、`command.py:223 _audit_sink_options()` 从 `_durable_store.options` 派生配置——新 facade 沿用同一模式。
- 异步面：`open_host.py:288 _PublicHostHandle` 暴露同步 facade 的 async wrapper（如 `purge_session` at `open_host.py:495`）。

---

## 5. Affected Files / Modules

| 文件 | 动作 | 说明 |
| --- | --- | --- |
| `dayu/host/durable/artifact.py` | EDIT | 新增两个公共 helper：`iter_published_artifact_relative_paths(artifact_root)`、`delete_artifact_file(artifact_root, relative_path)`（containment-guarded unlink），复用既有私有 `_validate_relative_path_text` / `_path_from_posix_relative` / `_ensure_contained`，把 containment 守卫集中在 artifact 模块。 |
| `dayu/host/durable/storage_lifecycle.py` | NEW | durable 内部原语：`read_storage_usage(...)`（只读计数/字节）、orphan 删除证明只读原语（`artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`、`collect_orphan_sqlite_payload_ids`）、`scan_orphan_artifact_files(...)`、`reclaim_orphan_artifact_files(...)`。 |
| `dayu/host/command.py` | EDIT | `HostCommandHandle` 增加最小 typed 私有访问：优先拆成 `_db_path()` 与 `_artifact_root_options()`，避免把 SQLite DB 路径和 artifact root 混成一个 bag；`_open_durable_connection()` 委托 `_durable_store.connect()`，docstring 必须明确调用方必须在 `finally` 或 context helper 中关闭 connection。沿用 `_raise_if_closed` + `_host_api_error_from_durable_error`。 |
| `dayu/host/storage_maintenance.py` | NEW | Host facade：`report_storage_usage(host) -> HostStorageUsageReport`、`run_storage_maintenance(host, request) -> HostStorageMaintenanceResult`，及 `HostStorageMaintenanceRequest` / `HostStorageMaintenanceResult` 类型。 |
| `dayu/host/open_host.py` | EDIT | `_PublicHostHandle` 增加 `async report_storage_usage(...)` / `async run_storage_maintenance(...)`，`_raise_if_closed` 后委托同步 facade。 |
| `dayu/host/__init__.py` | EDIT | 包根导出新公共函数与类型。 |
| `tests/host/test_storage_usage_report.py` | NEW | usage report 测试。 |
| `tests/host/test_storage_orphan_proof.py` | NEW | 删除证明（共享引用 / projection lag）测试。 |
| `tests/host/test_storage_maintenance.py` | NEW | maintenance entrypoint（扫描 / dry-run / 回收 / checkpoint / grace / 非 command-path）测试。 |
| `docs/host/design.md` | EDIT | 增补 Host storage maintenance public boundary 的最小设计说明；不扩展 schema，不引入 scheduler / VACUUM 平台。 |
| `dayu/host/README.md` | EDIT（实现期） | 新增"Storage lifecycle / maintenance"小节，仅描述已实现公共面。 |
| `tests/README.md` | EDIT（实现期） | 测试 inventory 增补三个新文件覆盖点。 |

不修改：`docs/engine/design.md`、`docs/host/issues-implementation-control.md`、GitHub Issue #43、`purge.py` 删除事务语义、任何 schema 文件。

---

## 6. Contract / Schema / State-Machine / Public-Interface Changes

### 6.1 Schema

**无 schema 变更。** report/证明只 `SELECT` 既有列；回收只删 artifact root 下文件，不删任何 row。因此不触发"schema 变更 → 全新起库"流程。

### 6.2 State machine

无 Run/Attempt/Session 状态迁移变更。maintenance 与 report 不写 canonical facts、不经 admission、不驱动状态机。

### 6.3 新增 public interface（理由：当前无任何 operator 可观测/维护面）

- `report_storage_usage(host: HostCommandHandle) -> HostStorageUsageReport`
  - 必要性：控制文档验收信号要求 operator 能看到 storage usage report；当前无此面。
- `run_storage_maintenance(host: HostCommandHandle, request: HostStorageMaintenanceRequest) -> HostStorageMaintenanceResult`
  - 必要性：控制文档验收信号要求 slow maintenance 只在显式 entrypoint 运行；当前 checkpoint 原语未投影、orphan 文件无回收路径。
- `open_host` 异步 handle 上对应的 `async report_storage_usage` / `async run_storage_maintenance`。
- 包根导出：上述函数 + `HostStorageUsageReport` / `HostStorageMaintenanceRequest` / `HostStorageMaintenanceResult`（`HostWalCheckpointMode` / `HostWalCheckpointResult` 复用既有类型，按需再导出）。

### 6.4 新增类型（strict typed，全部 `frozen=True, slots=True`，必要处 `kw_only=True`；全部含中文 docstring）

- `HostStorageUsageReport`（字段全部 `int`）：
  - 各 owner 分类 row 计数（复用 `schema.py` 表常量逐表 `COUNT(*)`）：`event_log_rows`、`idempotency_records`、`payload_descriptors`、`sqlite_payloads`、`host_sessions`、`host_runs`、`host_attempts`、`host_run_results`、`host_session_timeline_items`、`host_memory_snapshots`、`host_memory_items`、`host_tool_trace_hot`、`host_outbox_terminal_items`、`host_projection_checkpoints`、`host_projection_failures`、`host_purge_tombstones`（其余表按实现期复核取舍，但分类必须自解释）。
  - `sqlite_payload_logical_bytes: int`（`SELECT COALESCE(SUM(payload_size_bytes),0) FROM host_sqlite_payloads`）。
  - `artifact_descriptor_logical_bytes: int`（`SELECT COALESCE(SUM(payload_size_bytes),0) FROM payload_descriptors WHERE payload_kind='artifact_ref'`；注：这是 descriptor logical sum，不是物理文件占用；内容寻址共享下它可能大于实际物理占用。物理文件占用见 maintenance result 的 `physical_artifact_bytes`）。
  - `db_file_bytes: int` / `wal_file_bytes: int`（`Path.stat()`，缺失为 0；WAL 复用 `maintenance.py:_read_wal_size_bytes` 同名规则 `db_path + "-wal"`）。
  - `orphan_sqlite_payload_count: int`（`host_sqlite_payloads` 中 `payload_id` 不被任何 `payload_descriptors.sqlite_payload_id` 引用的诊断计数）。
  - `json_value() -> JsonValue`：稳定 JSON object（仿 `PurgeDeleteCounts.json_value()`，键为自解释字面量），用于 operator 显示/日志。
- `HostStorageMaintenanceRequest`（`kw_only`）：
  - `reclaim_orphan_artifacts: bool = False`（默认 dry-run，不删任何文件）。
  - `orphan_grace_seconds: float = DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`（具名常量默认值为 `3600.0`；docstring 说明：仅删除 mtime 早于 `now - grace` 的 orphan，防止删掉 publish 已落盘但 descriptor 尚未 commit 的在途文件）。
  - `run_wal_checkpoint: bool = True`。
  - `wal_checkpoint_mode: HostWalCheckpointMode = HostWalCheckpointMode.PASSIVE`。
- `HostStorageMaintenanceResult`：
  - `usage: HostStorageUsageReport`。
  - `physical_artifact_bytes: int`（artifact root 实际文件字节和，排除 `.tmp`）。
  - `orphan_artifact_candidates: tuple[str, ...]`（证明为 orphan 且满足 grace 的相对路径，已排序）。
  - `reclaimed_artifact_paths: tuple[str, ...]`（实际删除的相对路径；dry-run 时为空）。
  - `file_errors: tuple[HostStorageMaintenanceFileError, ...]`（单文件删除失败或 stat 失败的结构化诊断；成功删除的文件才进入 `reclaimed_artifact_paths`）。
  - `wal_checkpoint: HostWalCheckpointResult | None`（`run_wal_checkpoint=False` 时 `None`）。
- `HostStorageMaintenanceFileError`：
  - `artifact_relative_path: str`
  - `error_message: str`
  - `operation: str`（例如 `stat` / `delete`）

### 6.5 显式参数纪律

- orphan 回收的时间基准 `now: datetime` 与 `grace_seconds: float` 作为 durable 原语的**显式参数**传入（不进 extra payload、不用隐式 `datetime.now`），facade 负责注入 `datetime.now(UTC)`，保证可测试与 §CLAUDE.md "禁止把显式参数放进 extra payload"。

---

## 7. Implementation Decisions

1. **Usage report = 只读 SQLite 计数/求和 + 文件 stat**：逐表 `COUNT(*)` 复用 `schema.py` 表常量；字节用既有 `payload_size_bytes` 列求和（logical）；DB/WAL 用 `Path.stat()`。report **不**做 artifact root 目录遍历（遍历是慢 IO，放 maintenance）。report 走 `host._run_read(...)` 读事务 + 纯文件 stat，可安全暴露为只读 facade。

2. **删除证明 = 内容寻址安全的引用检查（只读原语）**：
   - 模块内只允许一个判定逻辑真源，例如私有 `_artifact_relative_path_is_referenced(transaction, path) -> bool` 执行 `SELECT 1 FROM payload_descriptors WHERE artifact_relative_path = ? LIMIT 1`。
   - public/internal helper `artifact_relative_path_is_referenced(...)` 和 `collect_referenced_artifact_paths(...)` 必须复用同一判定语义；前者用于单路径 recheck，后者用于快照所有存活 descriptor 的非空 `artifact_relative_path` 并做文件扫描差集。
   - `collect_orphan_sqlite_payload_ids(transaction) -> tuple[str,...]`：诊断用（report 的 orphan 计数来源）。
   - SQLite payload 引用沿用 `purge.py:_sqlite_payload_is_still_referenced` 同义判定（`payload_descriptors.sqlite_payload_id`）。

3. **Artifact orphan 文件回收（唯一 destructive 操作，隔离在 maintenance）**：
   - 流程：(a) 读事务快照 referenced set；(b) 遍历 artifact root 中**唯一合法的 published artifact namespace `sha256/`**（`iter_published_artifact_relative_paths`，跳过 `.tmp` 和所有非 `sha256/` 路径）得 on-disk set；(c) `candidate = on-disk − referenced`；(d) `deletable = candidate AND file_mtime <= now - grace_seconds`；(e) 仅当 `reclaim_orphan_artifacts=True`：对每个 deletable **重开读事务 recheck `artifact_relative_path_is_referenced` 为 False**，再经 containment 守卫 `delete_artifact_file` 删除。
   - 安全理由：referenced set 覆盖**全部** descriptor（含其它 Session），杜绝 §4.2 的共享文件误删；grace + recheck 收敛 publish-before-commit 竞态；containment 守卫复用 artifact 模块既有路径校验，杜绝越界删除。
   - 残余 TOCTOU：recheck 与 unlink 之间仍存在极短窗口，另一个 write transaction 理论上可能提交同一路径 descriptor。实现 docstring / README 必须显式记录该残余；默认 dry-run、`3600.0` 秒 grace、删除前 recheck 和 content-addressed 可重写性共同把风险降到可接受范围。

4. **Artifact cleanup boundary（不删什么）**：只删"无任何 descriptor 引用"的物理文件。绝不删除：仍被任意 descriptor 引用的文件、`.tmp` 在途文件、mtime 在 grace 窗口内的新文件、artifact root 外路径。purge 的 SQLite 删除事务语义完全不动。

5. **DB / WAL size / checkpoint 诊断**：复用 `run_host_wal_checkpoint(connection, db_path, mode)`。maintenance 用 `host._open_durable_connection()` 开**独立** connection 执行 checkpoint（PRAGMA 作用于同一 DB 文件，且 `run_host_wal_checkpoint` 已校验 connection 与 db_path 同源），必须在 `finally` 或 context helper 中关闭。size 走 `Path.stat()`。**不做 VACUUM**（§2 非目标；DB vacuum / space reclamation owner = GitHub Issue 76）。

6. **慢维护入口隔离**：`run_storage_maintenance` 是独立显式 entrypoint，**不**经 admission、不写 canonical facts、不在 EventLog append / run admission / cancel / resume / terminal closeout 内调用。facade docstring 与 README 显式声明该禁止；测试断言它不写 EventLog、不改 Session/Run 状态。

7. **职责分离**：durable 原语（读证明 vs 文件回收 vs 报告）按函数分离；containment/文件枚举集中在 `artifact.py`；facade 只编排不复制逻辑。符合 CLAUDE.md "数据处理、存储、工具调用职责分离 / 重复逻辑必须抽取"。

8. **orphan SQLite payload 只检测不删除（本 WU）**：`write_sqlite_payload` 总在同一事务写 descriptor + payload（`payload.py:190-248`），orphan SQLite row 仅来自部分失败/未来 bug。本 WU 报告其计数，**不**新增第二条 destructive DB 写路径（避免过度设计）；实际行删除作为 residual 交后续决策。

---

## 8. Small Implementation Slices

> 每个 slice 适合一次 implementation pass + 一次 review pass。slice 间有依赖，按序实现；除非 review 同意合并，否则逐个推进。

### Slice 1 — artifact 模块复用 helper（containment-guarded 文件枚举与删除）

- **objective**：把 artifact root 文件枚举与安全删除收敛到 `artifact.py`，供后续复用，避免跨模块导私有。
- **allowed files**：`dayu/host/durable/artifact.py`、`tests/host/test_artifact_store.py`。
- **prerequisites**：无。
- **exact changes**：
  - 新增 `iter_published_artifact_relative_paths(artifact_root: Path) -> Iterator[str]`：只递归遍历 artifact root 下的 `sha256/` namespace，跳过 `.tmp` 子树和所有非 `sha256/` 路径；对每个普通文件产出 POSIX 相对路径；对越界/异常路径抛 `HostArtifactWriteError`。这是安全要求，不能遍历整个 artifact root，否则 `audit/`、`tool-trace/` 等非 descriptor-managed JSONL 会被误标为 orphan。
  - 新增 `delete_artifact_file(artifact_root: Path, relative_path: str) -> bool`：`_validate_relative_path_text` → `_path_from_posix_relative` → `_ensure_contained(root, final_path)` → `unlink(missing_ok=True)`，返回是否删除了存在的文件。不要只调用 `_ensure_parent_dir_contained`；最终文件路径本身必须经过 `_ensure_contained` 校验，防止 symlink 逃逸。
- **data flow**：纯文件系统读/删；无 SQLite、无网络。
- **error handling**：路径校验失败 / IO 失败抛 `HostArtifactWriteError`；不吞错。
- **invariants**：绝不返回/删除 `.tmp`、非 `sha256/` namespace 文件或 root 外路径；删除是 idempotent（缺失返回 False，不抛）。
- **non-goals**：不读 descriptor、不做 orphan 判定。
- **tests/validation**：枚举只返回 `sha256/` 下普通文件，跳过 `.tmp`、`audit/`、`tool-trace/` 和其它非 artifact namespace；含子目录、空 root；删除存在/不存在文件；越界路径和 symlink 逃逸被拒。
- **completion signal**：新 helper + 测试通过，`artifact.py` 现有测试不回归。

### Slice 2 — storage usage report（只读）

- **objective**：提供 operator 只读 storage usage report。
- **allowed files**：`dayu/host/durable/storage_lifecycle.py`(NEW)、`dayu/host/command.py`、`dayu/host/storage_maintenance.py`(NEW)、`dayu/host/open_host.py`、`dayu/host/__init__.py`、`tests/host/test_storage_usage_report.py`(NEW)。
- **prerequisites**：无（不依赖 Slice 1）。
- **exact changes**：
  - `storage_lifecycle.py`：`HostStorageUsageReport` 类型 + `read_storage_usage(transaction, *, db_path) -> HostStorageUsageReport`（逐表 COUNT、payload/descriptor 字节求和、orphan sqlite 计数、DB/WAL stat）。
  - `command.py`：`HostCommandHandle._db_path()` 与 `_artifact_root_options()` typed accessors，或等价的单职责私有 helper；不要引入无语义的 god bag。
  - `storage_maintenance.py`：`report_storage_usage(host)`，经 `host._run_read(...)` + `_db_path()`。
  - `open_host.py`：`async report_storage_usage`。
  - `__init__.py`：导出 `report_storage_usage`、`HostStorageUsageReport`。
- **data flow**：read 事务读计数 → 文件 stat → 组装 report。无写。
- **error handling**：`HostDurableError -> HostApiError`（复用 `_host_api_error_from_durable_error`）；handle closed 抛 `HostApiError(INVALID_STATE)`。
- **invariants**：纯只读；report 字段非负（`json_value()` 校验）。
- **non-goals**：不遍历 artifact 文件、不 checkpoint、不删除。
- **tests/validation**：空库零计数；写入若干 Session/Run/payload/artifact descriptor 后计数与字节正确；含 orphan sqlite payload 时诊断计数正确；DB/WAL size 非负、WAL 缺失为 0；`open_host` 异步面可读；handle closed 抛错。
- **implementation note**：表清单必须在实现期基于 `HOST_DURABLE_TABLES` / `schema.py` 全量复核；至少覆盖控制文档验收信号中的 owner 分类，并优先纳入 `host_session_slots`、`host_attempt_dispatch_records`、`host_wait_records`、`host_memory_diagnostics`、`host_audit_sink_markers`、`host_outbox_drain_idempotency`、`host_instances` 等 MiMo review 指出的遗漏表，或在代码 docstring 中说明排除理由。
- **completion signal**：测试通过 + pyright 干净。

### Slice 3 — 删除证明只读原语 + maintenance dry-run（扫描 / 物理 size / checkpoint，无删除）

- **objective**：提供内容寻址安全的删除证明原语，并以 dry-run maintenance 暴露 orphan 候选、物理 size 与 checkpoint 诊断；**不删除任何文件**。
- **allowed files**：`dayu/host/durable/storage_lifecycle.py`、`dayu/host/command.py`、`dayu/host/storage_maintenance.py`、`dayu/host/open_host.py`、`dayu/host/__init__.py`、`tests/host/test_storage_orphan_proof.py`(NEW)、`tests/host/test_storage_maintenance.py`(NEW)。
- **prerequisites**：Slice 1（文件枚举）、Slice 2（report 类型 + accessors）。
- **exact changes**：
  - `storage_lifecycle.py`：`artifact_relative_path_is_referenced`、`collect_referenced_artifact_paths`、`scan_orphan_artifact_files(artifact_root, referenced, *, now, grace_seconds) -> tuple[str,...]`、`physical_artifact_bytes(artifact_root) -> int`。
  - `storage_maintenance.py`：`HostStorageMaintenanceRequest` / `HostStorageMaintenanceResult` + `run_storage_maintenance(host, request)`，当 `reclaim_orphan_artifacts=False` 只产出候选/size/checkpoint。
  - `command.py`：`_open_durable_connection()`（委托 `_durable_store.connect()`）。
  - checkpoint：独立 connection 调 `run_host_wal_checkpoint`，`finally` 关闭。
  - `open_host.py`：`async run_storage_maintenance`；`__init__.py` 导出 request/result + 函数。
- **data flow**：read 事务取 referenced set → 枚举文件做差集 → grace 过滤 → 物理 size → 独立 connection checkpoint → 组装 result（`reclaimed_artifact_paths=()`）。
- **error handling**：connection 始终关闭；IO/Durable 错误结构化为 `HostApiError`。
- **invariants**：dry-run 不改变文件系统与 DB row；候选已排序确定性。
- **non-goals**：不删文件、不删 row、不 VACUUM。
- **tests/validation**：
  - 共享引用：两个 descriptor 同 artifact 路径 → 该路径**不**入候选。
  - projection lag：descriptor 仍被 timeline/run_results/memory/tool_trace/outbox 引用 → `artifact_relative_path_is_referenced` 为 True、不入候选。
  - purge 泄漏复现：构造 closed Session + artifact，purge 后该物理文件无 descriptor 引用 → dry-run 候选包含它。
  - namespace 安全：`artifact_root/audit/*.jsonl`、`artifact_root/tool-trace/*.jsonl` 或其它非 `sha256/` 文件不得进入 orphan 候选，即使它们没有 descriptor 引用。
  - grace：mtime 在窗口内的新 orphan 不入候选。
  - checkpoint：`run_wal_checkpoint=True` 返回 `HostWalCheckpointResult`；`False` 为 `None`。
  - 非 command-path：maintenance 调用前后 EventLog rows 与 Session/Run 状态不变。
- **completion signal**：测试通过 + pyright 干净。

### Slice 4 — orphan artifact 文件回收（opt-in destructive，grace + recheck + containment）

- **objective**：在显式 opt-in 下，安全回收已证明 orphan 的 artifact 物理文件，闭合 purge 泄漏。
- **allowed files**：`dayu/host/durable/storage_lifecycle.py`、`dayu/host/storage_maintenance.py`、`tests/host/test_storage_maintenance.py`。
- **prerequisites**：Slice 1、Slice 3。
- **exact changes**：
  - `storage_lifecycle.py`：`reclaim_orphan_artifact_files(is_artifact_path_referenced, artifact_root, candidates) -> tuple[str,...]` 或等价设计——facade 传入一个显式 recheck callable，该 callable 内部用 `host._run_read(...)` 执行 `artifact_relative_path_is_referenced`。不要把 `HostTransaction` 对象通过 transaction factory 泄漏到事务边界外。
  - `storage_maintenance.py`：`run_storage_maintenance` 在 `reclaim_orphan_artifacts=True` 时调用回收，填充 `reclaimed_artifact_paths`。
- **data flow**：候选 → 逐个通过 recheck callable 执行读事务 → containment 删除 → 汇总。
- **error handling**：单文件删除失败不得静默吞掉；失败文件不进入 `reclaimed_artifact_paths`，以 `file_errors` 返回结构化诊断并继续处理其它候选。若发生无法继续的 durable / connection 级错误，则抛 `HostApiError`。
- **invariants**：只删 recheck 仍 orphan 且 grace 外、containment 内的文件；绝不删被引用文件 / `.tmp` / 越界路径；不删任何 DB row。
- **non-goals**：不删 orphan SQLite row、不改 purge、不引入 scheduler。
- **tests/validation**：
  - 回收后 orphan 物理文件消失，DB row 不变，被引用文件保留。
  - 共享引用文件即使有一个 descriptor 被删，只要另一个存活 → 不被回收。
  - recheck 命中（回收前刚被新 descriptor 引用）→ 跳过删除。
  - 删除失败：注入单文件 IO 错误时，该文件进入 `file_errors`，不进入 `reclaimed_artifact_paths`，其它候选仍可处理。
  - dry-run（默认）→ 文件不变、`reclaimed_artifact_paths` 为空。
  - 幂等：连续两次回收，第二次无候选、不抛错。
- **completion signal**：测试通过 + pyright 干净 + 全 §9 验证通过。

---

## 9. Tests / Validation Commands and Expected Assertions

实现期每 slice：`source .venv/bin/activate` 后运行该 slice 测试 + pyright（changed files）。聚合验证：

```bash
source .venv/bin/activate
pytest tests/host/test_artifact_store.py \
       tests/host/test_storage_usage_report.py \
       tests/host/test_storage_orphan_proof.py \
       tests/host/test_storage_maintenance.py \
       tests/host/test_purge_session.py -q
pyright dayu/host/durable/artifact.py \
        dayu/host/durable/storage_lifecycle.py \
        dayu/host/command.py \
        dayu/host/storage_maintenance.py \
        dayu/host/open_host.py \
        dayu/host/__init__.py \
        tests/host/test_storage_usage_report.py \
        tests/host/test_storage_orphan_proof.py \
        tests/host/test_storage_maintenance.py
```

预期断言要点：

- **report**：空库全零；写入后各分类计数/字节匹配；orphan sqlite 计数准确；DB/WAL size 非负、WAL 缺失为 0。
- **删除证明**：共享引用路径判定为"仍被引用"；projection-lag descriptor 判定为"仍被引用"；purge 泄漏文件判定为 orphan。
- **maintenance dry-run**：候选正确、非 `sha256/` 文件不会进入候选、文件与 row 不变、checkpoint 结果可得、EventLog/状态不变。
- **回收**：orphan 文件删除、被引用/共享/in-grace/recheck 命中文件保留、DB row 不变、幂等。
- **回归**：`test_purge_session.py` 全绿（未改 purge 语义）。
- **覆盖率**：新增单文件测试覆盖率目标 ≥ 80%。
- **pyright**：无新增/扩散错误；新代码无 `Any`/`object`/无类型签名。

---

## 10. Docs Decision（按 README 触发规则）

- `docs/host/design.md` → **需要**更新：新增 public Host storage maintenance 边界的最小设计说明。原因：本 WU 增加 operator-facing public API / maintenance entrypoint，属于 Host public contract；必须同步设计真源。更新范围仅限已实现的 maintenance boundary、artifact deletion proof、command-path 隔离和 DB VACUUM deferred to GitHub Issue 76，不扩写 scheduler / JSONL governance / VACUUM 平台。
- `docs/engine/design.md` → **不修改**：Engine 无接口耦合，不读 Host durable store。
- `dayu/host/` 改动 → **需要**更新 `dayu/host/README.md`：在公共面章节新增"Storage lifecycle / maintenance"小节，仅写已实现的 `report_storage_usage` / `run_storage_maintenance` 用途、非用途（无 scheduler / 无 time-window/user/workspace 删除 / 无 VACUUM / 不含 JSONL governance）、command-path 隔离边界、与 purge 的关系。遵守 README"只写当前已实现、不写未来计划"约束（实现完成后再写）。
- `tests/` 新增测试 → **需要**更新 `tests/README.md` inventory，增补三个新测试文件覆盖点。
- `docs/host/issues-implementation-control.md` → **不在本 gate 修改**，由总控在 gate 推进时回写 WU-RET-00 状态。
- GitHub Issue #43 → **不修改**。

---

## 11. Risks / Open Questions

### Residual risks（分类）

- **R1 publish-before-commit 竞态（assigned to current WU，grace 缓解）**：artifact 落盘先于 descriptor commit；若某次写入 commit 延迟超过 `grace_seconds`，理论上仍可能误删在途文件。缓解：grace + 删除前 recheck + 默认 dry-run + 文档要求 grace 显著大于最大事务延迟。→ 由 Slice 3/4 的 grace+recheck 覆盖，剩余尾部风险由 operator 调 grace 控制。
- **R2 purge `cleanup_refs` 死字段未清理（tracked, deferred）**：本 WU 用 maintenance 全量扫描取代 purge 逐路径文件清理，purge 的 `cleanup_refs.artifact_relative_paths` 仍被计算但永不消费。**不在本 WU 删除**该字段（避免触碰 89KB 中心 purge 路径）；记为后续清理项。不影响正确性（maintenance 扫描已覆盖这些 orphan）。
- **R3 orphan SQLite payload 行回收未实现（deferred, owner=后续决策）**：本 WU 仅报告其计数，不删 row（理由见 §7.8）。若未来发现部分失败常态化，再单列 work unit。
- **R4 大 artifact root 全量遍历成本（covered by design）**：遍历是慢 IO，已隔离在 operator 显式 maintenance entrypoint，不进 command path；report 不遍历。符合控制文档非目标。
- **R5 DB VACUUM 未实现（deferred-with-owner: GitHub Issue 76）**：本 WU 只 checkpoint + size 诊断，不回收 DB 物理空间。完整 SQLite vacuum / space reclamation 策略由 GitHub Issue 76 承接，不在当前 WU 关闭。
- **R6 非 `sha256/` namespace 文件误删风险（fixed by plan review）**：artifact root 下可能有 audit / tool-trace JSONL；实现必须只枚举 `sha256/` namespace，并用测试证明非 artifact 文件不进入 orphan 候选。

### Open questions（均非 blocking）

- Q1：包根是否需同时导出 `HostWalCheckpointMode` / `HostWalCheckpointResult`？默认导出（result 出现在 facade 返回类型上）。不阻塞实现。
- Q2：report 是否纳入所有 Host durable table 还是仅控制文档列举的 owner 分类？实现期按"自解释、覆盖验收信号枚举"取舍；遗漏表必须有 docstring 说明。不阻塞。

**无 blocking open question** → 见 §13。

---

## 12. Completion Report Format（本 gate 结束时）

实现各 gate 完成后统一用以下结构回报（本 plan gate 仅回报 §13）：

- **改了什么**：按 slice 列 changed files 与核心行为。
- **验证了什么**：实际运行的 pytest / pyright 命令与结果（含覆盖率）。
- **finding 状态**：review accepted findings 的 `未修复 / 已修复 / 部分修复 / 证据失效`。
- **docs 更新**：`dayu/host/README.md`、`tests/README.md` 实际改动。
- **residual risks / owners**：R1–R6 当前状态与归属。
- **下一入口**：下一 gate / 下一 slice。

---

## 13. Plan Gate 结论

- **为什么是最小正确闭环**：只解决三件被直接证据证明真实缺失的事——可观测（report）、可证明的安全删除（content-addressed-safe 引用证明 + 闭合 purge 永久泄漏的 orphan 文件）、慢维护隔离（复用既有 checkpoint，文件 IO/删除只在显式 entrypoint）。不碰 purge 语义、不改 schema、不引入 scheduler / 业务维度自动删除 / VACUUM 平台 / JSONL governance。
- **为什么没有过度设计**：零 schema 变更；destructive 行为仅"删除已证明无引用的物理文件"且默认 dry-run；scheduler / time-window / user / workspace / VACUUM / JSONL 全部显式列为非目标；复用既有 `run_host_wal_checkpoint`、purge 引用判定同义逻辑与 artifact containment 守卫，不造重复 runtime。
- **plan-ready**：**YES**（无 blocking open question；Q1–Q2 为实现期可自决细节）。
- **blocking open questions**：无。
- **residual risks**：R1–R6 已分类（§11）。
