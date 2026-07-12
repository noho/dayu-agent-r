# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Review

## Review metadata

- **Review target**: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- **Review type**: adversarial plan review (planreview skill)
- **Reviewer**: DS (deepreview / adversarial pass)
- **Timestamp**: 2026-07-12T11:43:48+08:00
- **Gate**: plan review gate, before any implementation
- **Risk level**: production-high
- **Control sources applied**:
  - `AGENTS.md`
  - `docs/host/design.md` (partial, §1-3)
  - `docs/engine/design.md`
  - `docs/host/issues-implementation-control.md` (partial, §1-2)
  - `docs/phaseflow-umbrella-optimization-control.md`
  - `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
- **Code evidence verified**: confirmed DR-006, DR-007, DR-008, DR-009, DR-010, DR-011, DR-012, DR-017, DR-025, DR-029 all still present in current code; confirmed compact_material wrong ref fallback at `dayu/host/compact_material.py:2567`; confirmed process `_started`/`_closed` booleans at `dayu/runtime/interruptible_process.py:272-273`; confirmed lane `_close_completed=True` premature commit at `dayu/runtime/lane.py:591`; confirmed scheduler retry exhaustion self-closes at `dayu/host/dispatch.py:2792`; confirmed watchdog `Queue(maxsize=1)` at `dayu/host/dispatch.py:962`; confirmed recovery single-transaction read at `dayu/host/recovery.py:204`; confirmed wait adapter unbounded join at `dayu/host/wait_adapter.py:1476-1489`; confirmed `Host` Protocol currently exposes `list_sessions`/`purge_session`/`report_storage_usage`/`run_storage_maintenance` at `dayu/host/api.py:3467-3662`; confirmed no existing `HostAdmin`/`UNAVAILABLE` types.

## Assumptions tested

1. All 11 controller-accepted findings + 6 MiMo/DS confirmations still exist in current code → **Confirmed** by direct grep evidence.
2. R3-F baseline is clean (3930 passed, 0 pyright errors) → **Accepted** from R3-F closeout record; plan correctly notes stress 4/5 pass with DR-006 being the 1 failure.
3. Five slices are necessary and cannot be reduced → **Partially rejected** (see Finding 1).
4. S2's 15+ contracts can be safely implemented as one slice → **Rejected** (see Finding 1).
5. S1 doesn't need schema changes → **Unverified** (see Finding 4).
6. S3 daemon thread per observation is safe → **Partially rejected** (see Finding 3).
7. S5 process transient start failure detection is well-specified → **Partially rejected** (see Finding 5).

---

## Findings

### F-01-未修复-高-S2 切片过粗：约15个独立契约打包为一个 slice

- **位置**: Slice S2（§"Slice S2：Host Admin / Async Durable Boundary / Admission 与 Scheduler Health"），allowed files 覆盖 `api.py`(3761行)、`open_host.py`(1349行)、`command.py`(1773行)、`dispatch.py`(4836行)、`recovery.py`(808行) 等共 12,527 行生产代码
- **问题类型**: 切片过粗 / 不可直接实施 / 过度耦合
- **当前写法**: 计划把 admin opener、durable actor、health gate state machine、admission lease、scheduler retry exhaustion、watchdog level-triggered event、recovery keyset batching、cancel deferred race fix、idempotent replay、thread-safe cancel bridge、actor open/close 全部放入 S2。计划论证为"它们共同修改 api.py/open_host.py/command.py/dispatch.py，并且 admission lease 必须原子覆盖 actor commit 与 scheduler wake；拆开会制造一个会接受但不会可靠 dispatch 的中间 contract"
- **反例/失败场景**:
  1. 实施 Agent 在 12,527 行跨 7 个文件的变更中引入一个微妙 race，被 S2 的 24 个测试文件的噪音淹没，debug 时间线性增长
  2. Review Agent 需要同时审查 actor thread safety、health gate state machine、recovery cursor stability、watchdog event semantics、cancel transaction ordering — 这些是 5 种不同的专项知识，一个 reviewer 难以全部覆盖
  3. recovery keyset batching 与 cancel deferred race 不依赖 health gate；它们可以在 health gate 之前或之后独立实现和验证
  4. watchdog level-triggered Event 与 admission lease 不共享 failure mode：watchdog 丢 wake 导致 dispatch 延迟（liveness），admission lease TOCTOU 导致 accepted + zero wake（correctness）— 两种不同严重级别的问题被同一 slice 掩盖
- **为什么有问题**: `docs/phaseflow-umbrella-optimization-control.md` 明确规定"生产 state machine / durable change：按真实 owner boundary 拆 2-4 个 slices"，且"超过 3 个 slices 时，plan 必须说明为什么不能合并"。该约束的本意是限制单个 slice 的范围，不是限制总切片数。当前 S2 用"文件重合"论证把 ~15 个独立契约合并为一个 slice，恰恰是该约束要防止的反模式。admission lease 需要 actor commit + scheduler wake 原子性，但 recovery batching、watchdog event、cancel race 和 idempotent replay 不参与该原子边界。
- **直接证据**:
  - umbrella control §"Slice 切分约束"：禁止按文件机械切分；要求按 semantic owner、validation matrix、failure blast radius、reviewer 专项知识拆分
  - umbrella control §"High Risk"：生产 state machine 变更默认 2-4 slices
  - 计划自身 §"Slice 数量与合并裁决" 承认 S2 内包含 admin opener、durable actor、health gate、recovery 与 cancel race，论证仅为"共同修改相同文件"
  - 当前 `dayu/host/dispatch.py` 4836 行、`dayu/host/api.py` 3761 行 — S2 对这些文件的大部分修改互相独立
- **影响**: 实施 Agent 跑偏（单 slice 太大容易遗漏交互）、review 不可验收（reviewer 无法同时覆盖 5 种专项知识）、后续返工（如果 recovery batching 有 bug，需要回滚整个 S2）
- **建议改法和验证点**:
  1. 将 S2 拆为至少两个 slice：
     - **S2a**: admin opener + durable actor + async boundary（DR-007, DR-011）。allowed files: `api.py`, `open_host.py`, new `_durable_actor.py`, `command.py`, `service/host_admin.py`, `cli/commands/session.py`。验证：admin 不启动 scheduler/recovery/lane/worker；event loop 在 SQLite 持锁时不冻结。
     - **S2b**: health gate + admission lease + scheduler retry + watchdog + recovery batching + cancel race + idempotent replay（DR-009 + 5 confirmations）。allowed files: `admission.py`, `dispatch.py`, `recovery.py`, `command.py`。验证：fatal/admission race、watchdog level-trigger、recovery cursor stability。
  2. 或者至少把 recovery batching + cancel race 作为独立 S2c，因为它们不依赖 health gate state machine。
  3. 每个子 slice 的 allowed tests 相应缩小；集成验证在全部子 slice 完成后统一执行。
- **修复风险**: 中（拆分需要重新定义子 slice 的 stop condition 和 allowed files，但不改变任何修复方案本身）
- **严重程度**: 高（不拆分会导致实施和 review 都无法安全完成，违反 umbrella control 的核心约束）

---

### F-02-未修复-中高-S2 fatal/admission race 测试机制未指定

- **位置**: Slice S2 §"必须测试的反例" #7："fatal transition 与 submit 使用 barrier 竞争：结果只允许'submit 持 lease 先 commit并成功 wake'或'fatal 先 commit、submit unavailable'，不允许 accepted 且 wake 丢失"
- **问题类型**: 测试缺口 / 不可直接实施
- **当前写法**: 计划要求测试证明 fatal/admission 竞争中恰好一个胜出，且 accepted 必须伴随 wake。但没有说明测试如何实现确定性 barrier race
- **反例/失败场景**:
  1. 实施 Agent 使用 `asyncio.sleep(0)` 或 `time.sleep` 模拟竞态 — 这在单线程 asyncio 中不能真正模拟并发 fatal + submit
  2. 实施 Agent 使用多进程测试但 barrier 同步点不对 — 竞态窗口可能完全不被命中，测试假绿
  3. 实施 Agent 放弃确定性测试，改为概率性 stress test — 在 CI 中 flaky，不能作为 correctness gate
- **为什么有问题**: 这是整个 S2 中最强的 correctness 断言（"不允许 accepted 且 wake 丢失"），但计划没有给出任何测试机制指引。实施 Agent 将被迫在设计测试方案时重新设计，这违反"code-generation-ready"的计划目标
- **直接证据**:
  - 计划反例 #7 仅用一句话描述期望结果，没有 barrier/进程数/同步点/断言机制
  - 当前 `tests/host/test_admission_multiprocess.py` 已存在多进程测试基础设施，但计划未说明如何复用
  - `tests/host/test_dispatch_scheduler.py` 没有现成的 fatal-injection 机制
- **影响**: 实施 Agent 可能交付假绿测试，竞态窗口在生产环境中触发
- **建议改法和验证点**:
  1. 明确测试机制：使用 `multiprocessing.Barrier` 或 `asyncio.Event` + 独立线程，在 admission 事务 commit 前/后设置同步点
  2. 至少指定：几个进程、barrier 位置（health gate fatal 写事务内 vs admission lease 获取后）、如何注入 fatal（mock critical task 抛异常 vs 直接调用 fatal transition）
  3. 明确断言：检查 durable state（Run 状态、dispatch record）和 wake port（promotion queue 内容），而非仅检查 public API 返回值
- **修复风险**: 低（补充测试机制说明，不改变修复方案）
- **严重程度**: 中高（测试是 production-high 变更的唯一 correctness 防线；测试机制缺失意味着该防线可能不存在）

---

### F-03-未修复-中-S3 daemon observation thread 生命周期规范不完整

- **位置**: Slice S3 §"已冻结的实现契约" #7："wrapper 使用一次性 daemon observation thread 和 typed result queue；timeout 后 poll path 以 `wait_observation_timeout` 收口为 Wait/Run `LOST`"
- **问题类型**: 并发恢复风险 / 契约缺失
- **当前写法**: 每次 poll observation 创建新 daemon thread。timeout 后 Host 将 wait 收为 LOST，但 daemon thread 可能仍在运行。计划说"late adapter result 经过 lifecycle gate 被丢弃，不能访问已关闭主 store"，但没有说明 daemon thread 如何知道主 store 已关闭
- **反例/失败场景**:
  1. Daemon thread 在 timeout 后、Host close 完成前返回 adapter result，尝试通过 result queue 投递 — queue 的 consumer 端（poller loop）已退出或已进入下一轮。Python daemon thread 在进程退出时被强制终止，但在进程退出前可能已完成 adapter 调用并尝试写 result queue
  2. Adapter 的 `poll_wait()` 返回后、daemon thread 写 result queue 前，poller 已关闭其私有 store/connection — 此时 daemon thread 持有 adapter result 但无处投递
  3. 连续多个 poll 都 timeout，每次创建新 daemon thread — 旧 daemon threads 堆积，虽标记 daemon 但仍在消耗内存和可能的 connection/FD
- **为什么有问题**: "一次性 daemon thread" 的生命周期不完整。`daemon=True` 只保证进程退出时不阻塞，不保证 thread 的资源（adapter connection、result queue reference）在 Host close 后安全释放。计划说"late adapter result 经过 lifecycle gate 被丢弃"但没有定义 lifecycle gate 在 daemon thread 侧的实现
- **直接证据**:
  - 计划 §"已冻结的实现契约" #7："wrapper 使用一次性 daemon observation thread"
  - 计划 §"已冻结的实现契约" #9："late adapter result 经过 lifecycle gate 被丢弃，不能访问已关闭主 store"
  - 计划未说明 lifecycle gate 的实现机制（queue shutdown? sentinel value? thread-local flag?）
  - 当前 `dayu/host/wait_adapter.py:1476-1489` 的 supervisor close 对 daemon thread 无控制
- **影响**: daemon thread 资源泄漏；极端情况下 adapter result 被丢弃但 wait 已 LOST，造成"外部 job 实际完成但 Host 宣告丢失"的语义不一致
- **建议改法和验证点**:
  1. 明确 result queue 的关闭协议：consumer 端退出时 shutdown queue，daemon thread 在 put 时捕获 queue shutdown 异常并静默丢弃
  2. 增加 daemon thread 计数上限或 thread 引用追踪，在 supervisor close 时 join 所有已知 observation threads（有界等待）
  3. 补充测试：mock adapter 在 timeout 后 5 秒返回，验证 result 被正确丢弃且不写 durable store
- **修复风险**: 低（补充实现细节，不改变整体方案）
- **严重程度**: 中（问题在极端的 timeout+late-result 并发下触发；不修复会导致不可复现的 wait 语义漂移）

---

### F-04-未修复-中-S1 descriptor schema 可行性未经预证

- **位置**: Slice S1 §"Allowed production files/modules" 末尾："任何 schema table/version 变更不在默认 allowed list；若直接证据证明现有 descriptor schema 无法表达完整校验，必须停止该 slice 并回到 plan review，不能顺手 migration"
- **问题类型**: open question 未收敛 / 不可直接实施
- **当前写法**: 计划要求 payload_resolution.py 校验 6 个条件（ref、caller digest、row digest、row size、bytes digest/size、canonical JSON），但将 schema 可行性推迟到实施时发现。如果现有 descriptor schema 缺少 row digest/size 列，S1 会在实施中途停止
- **反例/失败场景**:
  1. 实施 Agent 发现 `durable_payload` 表没有 `row_digest`/`row_size` 列，按 stop condition 停止 — 但 S1 的部分代码（runner-call manifest、compact material fix）已写好，形成半成品
  2. 实施 Agent 绕开 stop condition，在 payload_resolution.py 中对缺失列 fallback 为"只校验已有列" — 违反 DR-010 的"四方同源"要求
  3. 实施 Agent 在 SQLite 中新增列但未更新 schema version — 与现有 durable store 不兼容
- **为什么有问题**: 计划把"是否需要 schema 变更"从设计决策降级为实施发现，但 S1 的 stop condition 又要求发现后停止。这使 S1 成为一个可能 dead-end 的 slice。正确的做法是在 plan review 阶段确认 schema 是否足够，或在 S1 前增加一个 0-cost schema audit 子步骤
- **直接证据**:
  - 计划 S1 §"Allowed production files/modules" 末尾的 schema 免责声明
  - 当前代码 `dayu/host/durable/payload.py` 未提供 row-level digest/size 的直接 grep 证据
  - controller adjudication 中 DR-010 描述为"SQL 只取 payload_json，不核对 row digest/size"
- **影响**: S1 中途停止，浪费实施工作量；或实施 Agent 被迫在 plan review 和 implementation 之间自行裁决 schema 变更
- **建议改法和验证点**:
  1. 在 S1 开始前，增加一个 **schema feasibility pre-check**：读取当前 descriptor schema DDL，确认是否存在 `payload_digest`、`payload_size` 列，或现有列能否支持 6 方校验
  2. 如果 schema 不足，在 S1 allowed files 中增加 schema DDL 文件，并在测试反例中增加 schema migration 验证
  3. 更新 stop condition：schema 变更必须在 S1 内完成，不得推迟
- **修复风险**: 低（pre-check 是只读审计，不修改代码）
- **严重程度**: 中（如果 schema 确实不足，当前 plan 的 S1 无法完成；如果 schema 足够，本 finding 自动降级为无影响）

---

### F-05-未修复-低中-S5 process 瞬态启动失败检测依赖 `Process.start()` 异常语义

- **位置**: Slice S5 §"已冻结的实现契约" #2："target 被 handle 保存，process/queue 作为一次 start attempt 的 resources 创建。`Process.start()` 成功后才 commit RUNNING；明确未启动且 cleanup 成功的 transient start failure 重建全新 resources 并回到 NEW。若无法证明未启动或 cleanup 失败，则保持 CLOSING，只允许 close，不虚假允许 retry"
- **问题类型**: 状态机漏洞 / 并发恢复风险
- **当前写法**: process 状态机在 `Process.start()` 抛异常时判断"是否明确未启动"。如果无法证明未启动，保持 CLOSING
- **反例/失败场景**:
  1. `multiprocessing.Process.start()` 在 fork 成功后、子进程初始化期间抛异常（如 pickling error after fork）— 此时进程已创建，PID 存在，但 `start()` 抛出异常。代码无法区分"进程已启动但马上崩溃"和"进程从未启动"
  2. 判断"明确未启动"依赖 `process.pid is None` 或 `process.is_alive() == False` — 但 CPython 在 `Process.start()` 失败时，`pid` 可能已被赋值但进程已死。`is_alive()` 返回 False 既可能是"从未启动"也可能是"启动后立即退出"
  3. 如果错误地回到 NEW 并重试 start，创建第二个进程 — 原来的僵尸进程（如果存在）成为 orphan
- **为什么有问题**: "明确未启动"是一个模糊的运行时判断，底层依赖 CPython `multiprocessing.Process` 的实现细节。状态机的 NEW/CLOSING 分叉依赖一个不可靠的信号。更安全的做法是只区分"start() 成功 → RUNNING"和"start() 失败 → CLOSING（不可重试）"，避免在模糊地带回到 NEW
- **直接证据**:
  - 计划 §"已冻结的实现契约" #2：状态机包含 NEW/RUNNING/CLOSING 分叉逻辑
  - 当前 `dayu/runtime/interruptible_process.py:272-273`：`_started`/`_closed` 两个 bool
  - Python 3.11 `multiprocessing.Process.start()` 文档：fork 后异常时进程状态未定义
- **影响**: orphan 进程泄漏（低概率，但不可恢复）；测试可能假绿因为 CPython 行为在不同 OS/Python 版本间不一致
- **建议改法和验证点**:
  1. 简化状态机：start() 抛异常一律保持 CLOSING，不允许回到 NEW 并重试。如果调用方需要重试，创建新的 `InterruptibleProcessHandle` 实例
  2. 或者在 try/except 中通过 `process.pid` + `os.waitpid(pid, os.WNOHANG)` 主动验证进程是否存活，只有确认未创建进程（`pid is None`）才允许回到 NEW
  3. 补充测试：注入 `Process.start()` 在 fork 后抛异常的场景（需要 mock 或 subprocess fixture）
- **修复风险**: 低（简化状态机或增加显式 OS 级验证）
- **严重程度**: 低中（问题触发概率低，但一旦触发会泄漏 orphan 进程）

---

### F-06-未修复-低-S2 Host Protocol 拆分策略未明确

- **位置**: Slice S2 §"已冻结的实现契约" #2："execution `Host` 保留执行与单对象 read/watch 能力，移除 list/purge/storage-admin 方法；不保留旧 handle compatibility wrapper"
- **问题类型**: 契约缺失
- **当前写法**: 计划说移除 `Host` Protocol 上的 `list_sessions`/`purge_session`/`report_storage_usage`/`run_storage_maintenance`，新增 `HostAdmin` Protocol。但没有说明是：
  - (a) 两个独立 Protocol（`Host` 和 `HostAdmin`），各自描述自己的方法集
  - (b) 一个 `Host` Protocol 保留所有方法，但 execution `_PublicHostHandle` 不实现 admin 方法
  - (c) 拆分 `Host` Protocol，`HostAdmin` 继承部分方法
- **反例/失败场景**:
  1. 实施 Agent 选择 (b) — 保留了 `Host` Protocol 上的 admin 方法签名，CLI/Service 仍可通过 Protocol 类型调用，只是运行时抛 `NotImplementedError` 或 `UNSUPPORTED_OPERATION`。这违反了"禁止兼容 wrapper"的约束
  2. 实施 Agent 选择 (c) — 引入 Protocol 继承层次，过度设计
  3. `tests/host/test_package_exports.py` 和 `tests/host/test_import_boundary.py` 的预期行为取决于 Protocol 拆分方式
- **为什么有问题**: `AGENTS.md` 要求"设计公共契约优先使用直接传参数的朴素接口"。当前 `Host` Protocol (api.py:3427-3700+) 是一个包含 15+ 方法的单一 Protocol。拆分为两个 Protocol 是一个 public contract 变更，需要在 plan 中明确形状
- **直接证据**:
  - 当前 `dayu/host/api.py:3427`：`class Host(Protocol)` 包含 `list_sessions`、`purge_session`、`report_storage_usage`、`run_storage_maintenance`
  - 计划 S2 §"已冻结的实现契约" #2-3 提到"移除"但未指定 Protocol 级别的拆分方式
  - `tests/host/test_package_exports.py` 在 S2 allowed tests 中
- **影响**: 实施 Agent 的 Protocol 拆分选择可能被 review 驳回，造成返工（低影响，因为范围明确）
- **建议改法和验证点**:
  1. 明确选择 (a)：`Host` 和 `HostAdmin` 是两个独立 Protocol，不共享继承
  2. `Host` Protocol 保留：`ensure_session`、`create_session`、`get_session`、`get_run`、`read_outbox_terminal_items`、`drain_outbox_terminal_items`、`submit_followup`、`retry_run`、`replay_run`、`cancel_run`、`cancel_session_runs`、`close_session`、`watch_run_events`、`close`
  3. `HostAdmin` Protocol 新增：`get_session`、`list_sessions`、`purge_session`、`report_storage_usage`、`run_storage_maintenance`、`close`
  4. `Host.get_session` 与 `HostAdmin.get_session` 语义相同，可共享底层 command function
- **修复风险**: 低（设计决策，不涉及复杂实现）
- **严重程度**: 低（不影响 S2 可行性，但缺失会导致实施 Agent 自行裁决）

---

## Slice count judgment

Plan proposes 5 slices. Per `docs/phaseflow-umbrella-optimization-control.md`, production state-machine work normally targets 2-4 slices, and plans above 3 must justify cost.

**The 5-slice count is not the primary problem.** The primary problem is S2's internal scope (~15 contracts in one slice). After S2 is decomposed (see F-01), the total would be 6-7 slices, but each slice would be independently reviewable and testable. The umbrella control's "2-4 slices" guideline is about per-slice scope, not total count — a work unit can have more slices if each is tightly scoped.

**Slice merge assessment:**
- S1 (durable/provenance) + S2 (opener/admission/scheduler): **Cannot merge** — plan correctly argues runner payload stress failure localization would be buried by opener/scheduler changes
- S3 (wait) + S4 (compaction): **Cannot merge** — plan correctly identifies different semantic owner, terminal oracle, and test oracle
- S5 (runtime): **Reasonable merge** — process + lane share "side-effect-before-commit" review pattern; separate classes, separate tests
- S2 internal: **Must split** (F-01) — health gate, recovery, watchdog, cancel race are separate owners

---

## Open questions

1. **S1 schema feasibility**: Does current `durable_payload` schema have `payload_digest` and `payload_size` columns to support the 6-field integrity check? If not, should S1 include DDL changes or is the schema already sufficient?
2. **S2 fatal injection mechanism**: How will the test inject a fatal scheduler error? Direct `HealthGate.report_fatal()` call from test thread? Or mock a critical task to throw?
3. **S3 daemon thread count**: Is there a maximum number of concurrent observation threads? What prevents thread accumulation when every poll times out?
4. **DR-011 residual risk #3**: Plan notes "scheduler open/close及runtime内部短transaction仍由scheduler event-loop owner执行". Does this mean scheduler-owned transactions could still cause heartbeat freeze? The plan defers this to "若集成lock probe证明...必须登记新的R3-A residual". Is this probe planned for S2 validation?

---

## Residual risks and suggested tracking

| Risk | Owner | Suggested destination |
| --- | --- | --- |
| S2 over-broad scope (F-01) | Plan author (AgentCodex) | Fix in plan before implementation gate |
| S2 race test underspecified (F-02) | Plan author | Fix in plan before implementation gate |
| S3 daemon thread lifecycle (F-03) | S3 implementer | Address in S3 implementation or accept as documented risk |
| S1 schema unknown (F-04) | Plan author | Pre-check before S1 start |
| S5 process start ambiguity (F-05) | S5 implementer | Accept as known limitation with explicit OS-level check |
| Fins reverse dependency | R3-D owner | Already tracked in controller adjudication as R3-D/R3-A split |
| Scheduler-owned transaction blocking | R3-A residual | Deferred per plan; needs lock probe in S2 validation |

---

## Final plan review conclusion

**Fail** — with two blocking findings (F-01, F-02) and three material non-blocking findings (F-03, F-04, F-05, F-06).

**Reason**: S2 as currently scoped bundles ~15 independent contracts across 12,527 lines into one slice, violating the umbrella control's constraint against over-broad slices and making safe implementation/review infeasible. The fatal/admission race test (S2 anti-case #7) — the strongest correctness assertion in the entire plan — lacks a specified test mechanism. Without these two issues resolved, the plan is not code-generation-ready for S2.

**What must be fixed before implementation gate**:
1. Decompose S2 into at least 2 (preferably 3) sub-slices along semantic owner boundaries (F-01)
2. Specify the deterministic test mechanism for fatal/admission TOCTOU race (F-02)
3. Optionally: pre-check S1 schema feasibility, clarify daemon thread lifecycle, decide Host/HostAdmin Protocol split strategy

**Strengths of the plan that should be preserved**:
- Clean semantic owner attribution for each finding with explicit "禁止实现" column
- Well-defined non-goals and forbidden repair patterns per slice
- Clear stop conditions gating progression between slices
- Correct README update decisions per AGENTS.md triggers
- S3/S4/S5 have focused scope and well-specified anti-cases
- Integration validation is comprehensive with source audits
