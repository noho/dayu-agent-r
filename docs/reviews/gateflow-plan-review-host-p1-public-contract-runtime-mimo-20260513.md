# Host Phase 1 Plan Review: 公共契约与 runtime 基础设施

## Review Gate

plan review

## Reviewer

AgentMiMo

## Reviewed Target

- Plan: `docs/host/phase1-public-contract-runtime-plan.md`
- Design truth: `docs/host/design.md`
- Implementation control: `docs/host/implementation-control.md`
- Project term truth: `dayu/README.md`
- Controller decision: `docs/reviews/gateflow-controller-decision-host-p1-phase-design-20260513.md`
- Round2 fix: `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`
- Round2 re-review (MiMo): `docs/reviews/gateflow-phase-design-re-review2-host-p1-mimo-20260513.md`
- Round2 re-review (DS): `docs/reviews/gateflow-phase-design-re-review2-host-p1-ds-20260513.md`

## Review Method

逐项对照 design truth、implementation-control、controller decision 和项目约束，做 evidence-based adversarial review。检查点覆盖：handoff readiness、motivation 对齐、architecture boundary、cross-process lane、SQLite coordinator、filelock wrapper、public typing、slice ordering、test coverage、README sync、blocking open questions。

## Per-Check Review Result

### 1. Plan 是否 handoff-ready 且 code-generation-ready

**Result: PASS**

Plan 为每个 slice 提供了：allowed files/modules、exact allowed changes、implementation instructions、non-goals、tests/validation、expected assertions、completion signal、stop condition。Implementation agent 可以在不自行做 material design choices 的情况下执行每个 slice。

Evidence：
- Slice 1 列出全部 request / snapshot / status / error / context 类型清单，含字段、校验规则、validation failure paths。
- Slice 2 列出完整 public API shape、SQLite coordinator schema、claim/release 生命周期、cancel/timeout/close 语义、multi-process test matrix。
- Slice 3 列出 filelock public API shape、error wrapping 语义、context manager 语义、third-party boundary。
- Slice 4 列出 HostToolingOptions validation rules、reserved name conflict、default policy view。
- 每个 slice 有明确 completion signal 和 stop condition。

### 2. Motivation 是否真实且对齐设计目标

**Result: PASS**

Motivation 直接引用 `docs/host/implementation-control.md` Phase 1 目标、`docs/host/design.md` §11 / §3.1 / §3.2 / §10.1 / §18.1、`dayu/README.md` Runtime 节、controller decision。所有引用均可追溯到 design truth。

对齐检查：
- 单机多客户端 / 多进程：lane 改为 cross-process named semaphore / capacity guard（与 controller decision 一致）。
- Host 强约束：Host public types 放在 `dayu.host`，Engine 不得 import（与 design §11 一致）。
- UI -> Service -> Host -> Engine：import boundary 在 plan 和 tests 中锁定（与 design §2 一致）。

### 3. Architecture boundary violation 检查

**Result: PASS**

逐项核查：

- Engine / Fins 反向依赖：plan 明确禁止修改 `dayu/engine/**`、`tests/engine/**`、`dayu/fins/**`（plan:78-82）。import boundary tests 锁定 `dayu.host` 不 import `dayu.engine` / `dayu.fins`（plan:501）。
- Host durable truth 夹带：plan non-goals 明确不实现 Host durable store / EventLog store / command path（plan:30-38）。lane token 不是 Host truth（plan:391）。
- ToolRuntime 提前实现：plan non-goals 明确不实现 ToolRuntime policy resolution / framework tool injection / TruncationManager / fetch_more 执行逻辑（plan:33）。
- `dayu.runtime` import boundary：plan 禁止从 `dayu.runtime.__init__` re-export lane / filelock 符号（plan:53）。lane 只依赖标准库、`dayu.contracts.cancellation.CancellationToken` 和同包 helper（plan:537）。filelock 只由 `dayu.runtime.filelock` 直接 import 第三方 `filelock`（plan:439）。
- `dayu.host` import `dayu.contracts`：plan 允许 `dayu.host.api` import `JsonValue` from `dayu.contracts.json_value`（plan:484）。这是合法依赖方向（contracts 是跨层共享契约层，host -> contracts 不违反分层）。

### 4. Cross-process lane plan 可实施性

**Result: PASS**

Controller decision 要求 lane 必须支持单机多客户端 / 多进程。Plan 已正确覆盖：

- SQLite runtime lane coordinator 使用独立 DB 文件，不复用 Host durable store（plan:233-234, design:80-84）。
- `LaneController.open(...)` 显式接收 `SQLiteLaneCoordinatorConfig(db_path=...)`，不提供默认路径 helper（plan:233-234）。
- Schema 只保存 runtime capacity coordination 字段：`lane_name`、`claim_id`、`owner_id`、`pid`、`process_start_token`、`created_at`、`heartbeat_at`、`expires_at`（plan:236-245）。
- `lane_name + claim_id` 为 primary key（plan:245）。
- 不保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段（plan:246）。
- claim / release / heartbeat / stale cleanup 使用短事务（plan:248）。
- 等待容量时不得持有长事务（plan:248）。

Non-goals 正确：
- lane token 不是 Host truth、lease / fencing token、Attempt owner、dispatch record、EventLog ordering、admission 或 recovery proof（plan:391）。
- stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能写 EventLog，不能授权 takeover（plan:392）。
- 不承诺 FIFO、公平性、优先级、跨 lane ordering 或跨机器分布式限流（plan:393）。

### 5. SQLite runtime lane coordinator 详细设计

**Result: PASS**

Plan 已收敛 controller decision 交给 Phase 1 plan 覆盖的实现细节：

- **Schema**：8 个字段，`lane_name + claim_id` primary key，按 `lane_name` 过滤 active claims（plan:236-245）。
- **Heartbeat ownership**：`LaneController` 为当前 controller 持有的 unreleased tokens 启动后台 heartbeat task，按最小 `heartbeat_interval_seconds` 或固定内部调度间隔循环刷新（plan:251-253）。
- **Busy timeout**：`SQLiteLaneCoordinatorConfig.busy_timeout_seconds` 只应用于 runtime lane DB connection，不影响 Host durable store policy（plan:247）。
- **TTL / clock skew**：使用私有 `_LaneClock`，通过 `time.monotonic()` + controller open 时的 UTC wall-clock anchor 生成同一进程内一致的 UTC `datetime`。跨进程 clock skew 只影响 capacity availability eventual consistency，不得被解释为 Host truth（plan:255-256）。
- **Heartbeat failure**：background heartbeat 遇到不可恢复 SQLite error 时，controller 记录 first heartbeat error，停止接受新 acquire，并让后续 acquire 返回 cancelled 或抛结构化 `RuntimeLaneError`（plan:258）。
- **Multi-process tests**：覆盖 capacity invariant、release 后 acquire、crash/stale cleanup 后 eventual acquire（plan:565-570）。

### 6. filelock wrapper 边界

**Result: PASS**

- 只做同步 wrapper（plan:438）。
- 第三方 `filelock` 只由 `dayu.runtime.filelock` 直接 import（plan:439）。
- 错误语义：第三方 `filelock.Timeout` 包装为 `RuntimeFileLockTimeoutError`，parent directory 创建失败 / 路径非法 / acquire 失败统一包装为 `RuntimeFileLockError`（plan:443-444）。
- 不实现 stale lock 探测、锁文件删除、owner pid 解析、跨进程 owner takeover、强制 break lock（plan:446）。
- 不承诺 reentrant lock 语义（plan:447）。
- Release 幂等通过 token 内部 `released` 布尔状态保证（plan:607）。

### 7. `dayu.host` public typing 与 HostToolingOptions

**Result: PASS**

- 文件边界：`dayu.host.api` 放 request / snapshot / context / status / error / stream cursor 类型；`dayu.host.tooling` 放 ToolBundle 输入边界类型；`dayu.host.__init__` 只导出 Phase 1 承诺的公共类型（plan:88-90）。
- Import boundary：`dayu.host` 不得 import `dayu.engine` / `dayu.fins` / `dayu.service` / `dayu.ui`（plan:92）。Engine 不得 import `dayu.host`（plan:93）。
- 类型清单完整：8 个 StrEnum、4 个 context/input 类型、1 个 handle protocol、12 个 request 类型、8 个 snapshot/stream 类型、1 个 error 类型（plan:99-179）。
- Validation rules 明确：空字符串拒绝、cursor 非负、steer 缺 target_run_id、queue 携带 target_run_id、bind slot 缺 scope/slot_key、CancelMode 只允许 GRACEFUL（plan:183-189）。
- `HostToolingOptions` validation：source_refs 非空、source_id 非空、reserved name 冲突、enabled 是 reserved 子集（plan:233-236）。
- `ToolBundleSourceKind` 与 `FrameworkToolName` 使用 `enum.StrEnum`（plan:226-227）。
- 测试覆盖：package exports、public contracts、import boundary、weak typing guard、tooling options（plan:462-466, 648-650）。

### 8. Slices 是否足够小、有序、可 review

**Result: PASS**

4 个 slice 按依赖顺序排列：

1. S1: `dayu.host` public types — 无外部依赖，只依赖 `dayu.contracts`。
2. S2: `dayu.runtime.lane` — 依赖 `dayu.contracts.cancellation.CancellationToken`，不依赖 S1。
3. S3: `dayu.runtime.filelock` — 只依赖第三方 `filelock` 和标准库，不依赖 S1/S2。
4. S4: `dayu.host.tooling` — 依赖 `dayu.contracts.tool_declaration.ToolBundle` 和 S1 的 `dayu.host` package。

S1 和 S2/S3 可以并行执行（无依赖）。S4 依赖 S1（需要 `dayu.host.__init__` 导出）。每个 slice 有独立的 allowed files、non-goals 和 completion signal，不会诱导 implementation agent 提前做 future-slice 工作。

### 9. Tests、pyright、README sync 覆盖

**Result: PASS**

Failure paths 覆盖（plan:716-725）：
- Host public contract validation：空字符串、非法 cursor、非法 followup behavior/target、slot binding 缺字段。
- Host tooling validation：reserved name conflict、空 source refs、空 source id、enabled framework tool 不在 reserved 集合。
- lane config validation：重复 lane、未知 lane、非正 capacity、TTL <= heartbeat、非正 heartbeat/TTL。
- lane acquire failure：capacity full non-blocking timeout、positive timeout、CancellationToken cancellation、Task.cancel propagation、close cancels pending acquire。
- lane multi-process：capacity invariant、release 后 acquire、crash/heartbeat stopped 后 TTL stale cleanup。
- lane busy timeout：并发竞争下不破坏 capacity invariant。
- filelock failure：parent missing with create disabled、non-blocking timeout wrapping、release idempotency。
- import boundary：runtime 不 import Engine/Host/Service/UI/Fins；Host 不 import Engine/Fins/Service/UI；第三方 filelock 只出现在 `dayu.runtime.filelock`。

Coverage expectation：新增生产模块单文件覆盖率目标 >= 80%（plan:729）。

README sync（plan:733-741）：
- `dayu/README.md`：更新 lane/filelock/`dayu.host` 公共类型从设计要求变为当前代码能力。
- `dayu/host/README.md`：新建 Host 开发手册。
- `tests/README.md`：增加 `tests/host` 层级和 runtime lane multi-process tests。
- 根目录 `README.md`：默认不更新（除非 filelock 依赖改变安装方式）。

### 10. Blocking open questions

**Result: PASS — 0 blocking open questions**

Plan 声明「当前设计真源已经足够支撑 Phase 1 implementation plan」（plan:754）。所有 material choices 已在 plan 中收敛为 implementation decisions：

- 默认路径注入：不提供 helper，只文档建议（plan:763）。
- Heartbeat ownership：controller-managed heartbeat task（plan:251-253）。
- SQLite schema：8 字段，lane_name + claim_id primary key（plan:236-245）。
- Busy timeout：只应用于 runtime lane DB connection（plan:247）。
- Clock skew：monotonic + UTC wall-clock anchor，跨进程 eventual consistency（plan:255-256）。

Non-blocking questions 有 working assumption、低风险原因和触发回看信号（plan:758-769）。

## Findings

Finding 数量: 4

### Finding 1: `LaneClaimToken` 同步/异步方法签名未在 plan 中明确标注

- **状态**: 已修复
- **位置**: `docs/host/phase1-public-contract-runtime-plan.md` §Cross-Process `dayu.runtime.lane` Decisions > Public Shape
- **描述**: Plan 中 `LaneClaimToken` 的 `refresh()` 和 `release()` 方法签名未标注 `async`。设计真源 `docs/host/design.md:116-117` 明确写为 `refresh() -> Awaitable[None]` 和 `release() -> Awaitable[None]`。Plan 的 implementation instructions 提到 `LaneClaimToken.release()` 是异步的（plan:554 "异步、幂等"），但 public shape 签名与设计真源不一致。
- **影响**: 低。Implementation agent 可以从 design truth 推断为 async methods。但 plan 作为 code-generation-ready handoff，shape 应与 design 一致。
- **建议**: 在 plan 的 `LaneClaimToken` shape 中标注 `async def refresh(self) -> None` 和 `async def release(self) -> None`。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 2: SQLite WAL mode 未在 plan 中显式要求

- **状态**: 已修复
- **位置**: `docs/host/phase1-public-contract-runtime-plan.md` §Cross-Process `dayu.runtime.lane` Decisions > Coordinator / DB
- **描述**: Plan 要求多进程共享同一 lane DB 时 capacity invariant 不破坏（plan:565-570），但未显式要求 SQLite WAL mode。设计真源 `docs/host/implementation-control.md:1253` 明确写「正确性依赖 WAL、明确 busy timeout、短事务、显式重试、唯一约束和 CAS-style state transition」。WAL mode 对多进程并发读写至关重要；默认 journal mode 在多进程写入时容易触发 `SQLITE_BUSY`。
- **影响**: 低。Implementation agent 大概率会使用 WAL mode（Python sqlite3 默认 journal mode 可能不是 WAL），但 plan 作为 handoff 应显式声明。
- **建议**: 在 plan 的 Coordinator / DB 段添加「DB 初始化必须设置 `PRAGMA journal_mode=WAL`」。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 3: `dayu/runtime/__init__.py` docstring 更新未在 Documentation Update Decision 中显式列出

- **状态**: 已修复
- **位置**: `docs/host/phase1-public-contract-runtime-plan.md` §Documentation Update Decision
- **描述**: Plan 的 Allowed changes 段允许「仅当必须暴露 runtime 子模块 package-level 说明时，允许最小修改 `dayu/runtime/__init__.py` 文档」（plan:53），但 Documentation Update Decision 段未列出 `dayu/runtime/__init__.py` 作为需要更新的文件。当前 `dayu/runtime/__init__.py` docstring 只提到「日志装配、协作式取消等待 / race helper」，Phase 1 新增 lane 和 filelock 后应更新包 docstring 说明当前已实现的层中立能力。
- **影响**: 低。Implementation agent 可以从 allowed changes 推断需要更新，但 plan 的 Documentation Update Decision 应保持完整。
- **建议**: 在 Documentation Update Decision 段添加 `dayu/runtime/__init__.py`：需要更新。原因：新增 lane 和 filelock 能力，包 docstring 需要同步。
- **Controller decision status**: accepted-fixed-by-codex-20260513

### Finding 4: `tests/runtime/test_import_boundary.py` 新增断言内容未在 plan 中具体描述

- **状态**: 已修复
- **位置**: `docs/host/phase1-public-contract-runtime-plan.md` §Slice 2 / Slice 3 > Allowed files/modules
- **描述**: Plan 列出修改 `tests/runtime/test_import_boundary.py`（plan:523, 591），但未描述需要新增哪些具体断言。现有测试文件有两个 test functions：`test_runtime_does_not_import_business_layers` 和 `test_runtime_does_not_import_phase0_forbidden_modules`。Plan 应明确：
  - 是否新增 test function 检查第三方 `filelock` 只出现在 `dayu.runtime.filelock`（其它 runtime 模块不得 import filelock）。
  - 是否在现有 `test_runtime_does_not_import_business_layers` 中添加对 `dayu.runtime.lane` 和 `dayu.runtime.filelock` 的扫描覆盖（现有测试已通过 AST 扫描覆盖全部 runtime .py 文件，lane.py 和 filelock.py 新增后自动被覆盖，但 plan 应明确说明这一点以消除歧义）。
- **影响**: 低。现有 test 已通过 `_iter_python_files()` 自动覆盖新增 .py 文件。但 plan 作为 handoff 应明确新增断言内容。
- **建议**: 在 Slice 2/3 的 Expected assertions 中添加：「现有 `test_runtime_does_not_import_business_layers` 自动覆盖新增 `lane.py` / `filelock.py`；新增 test function 检查第三方 `filelock` 只被 `dayu.runtime.filelock` import，其它 runtime 模块不得 import `filelock`」。
- **Controller decision status**: accepted-fixed-by-codex-20260513

## Open Questions And Residual Risk

### Open Questions

无 blocking open questions。Plan 的 non-blocking questions 均有 working assumption 和触发回看信号（plan:758-769）。

### Residual Risks

1. **SQLite busy timeout 高并发抖动**：高并发下 SQLite busy 可能导致 acquire loop 抖动。Plan 已覆盖 concurrent acquire 与 busy timeout 测试（plan:773-775）。风险等级：低。

2. **Heartbeat failure 可观测性**：background heartbeat failure 需要让调用方可观测。Plan 已选择 controller-managed heartbeat，failure 标记 token lost（plan:776-778）。风险等级：低。

3. **Clock skew / TTL eventual consistency**：跨进程 clock skew 可能让 stale cleanup 提前或延后。Plan 已明确只影响 runtime capacity，不影响 Host truth（plan:779-781）。风险等级：低。

4. **lane DB cleanup**：workspace runtime DB 文件可能残留。Plan 明确 Phase 1 不负责删除真实 workspace DB，后续 Host composition root / workspace lifecycle phase 负责（plan:782-784）。风险等级：低。

5. **Public Host contracts 初始形状扩展压力**：过早暴露过多内部类型会导致兼容压力。Plan 只导出 request / snapshot / status / error / context 最小类型（plan:785-787）。风险等级：低。

6. **ToolBundle digest / snapshot refs 未实现**：后续 Attempt snapshot phase 需定义 digest 算法。Plan 明确 deferred to ToolRuntime / command path phases（plan:788-790）。风险等级：低。

## Reviewer Conclusion

Plan 是 handoff-ready 且 code-generation-ready 的。4 个 findings 均为低严重性的实现细节澄清，不阻塞 plan 进入 user confirmation。Plan 的架构边界、cross-process lane 设计、SQLite coordinator 详细设计、filelock wrapper 边界、public typing 完整性、slice ordering、test coverage 和 README sync 均与 design truth、implementation-control 和 controller decision 一致。无 blocking open questions。

建议 controller 处理 4 个 findings（接受或拒绝），然后进入 user confirmation gate。

## Artifact Path

`docs/reviews/gateflow-plan-review-host-p1-public-contract-runtime-mimo-20260513.md`
