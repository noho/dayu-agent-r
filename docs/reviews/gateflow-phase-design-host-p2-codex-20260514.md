# Host Phase 2 Phase Design Refinement Readiness Review

## Work Gate Name

Phase 2 feature discussion / phase design refinement readiness check.

## Reviewed Source Paths

- `docs/host/design.md` §10 Durable Store
- `docs/host/design.md` §13 EventLog
- `docs/host/design.md` §13.1 Payload 存储
- `docs/host/design.md` §27 Host Lifecycle / Recovery
- `docs/host/implementation-control.md` Phase 2 Durable Store / EventLog / Payload Foundation
- `docs/host/implementation-control.md` 追踪区：SQLite 多进程写入正确性验证、Host 跨层测试策略追踪
- `dayu/README.md` 术语真源：EventLog、canonical event、client / remote / canonical identity、Host event stream、event_sequence、host_instance_id、positive orphan proof

## Readiness Conclusion

**not ready for handoff-ready plan gate。**

Phase 2 的目标、success signal、scope boundary 和 non-goals 成立，且服务于 Host 设计目标：它把 SQLite durable truth、EventLog append primitive、payload descriptor、idempotency record、host instance liveness 和事务边界作为后续 Session / Run / Attempt、ToolRuntime、Projection、Recovery 的基础。

但当前设计真源尚不足以直接生成 handoff-ready plan。阻塞点不是“实现细节还没写”，而是若干会影响 schema convention、public typed contract、transaction semantics、payload persistence、multi-process tests 和 later phase ownership 的决策仍未收敛。若直接进入 plan gate，planning agent 需要自行选择 schema 规则、事务 runner 行为、SQLite policy、payload descriptor shape 和 host instance liveness 最小表语义，这会违反 handoff-ready plan 对 material choices 收敛的要求。

## Direct Evidence

- `docs/host/implementation-control.md:361-362` 定义 Phase 2 目标为建立 SQLite durable truth、EventLog append primitive、payload descriptor、idempotency record、host instance liveness 与事务边界。
- `docs/host/implementation-control.md:373-374` 明确 Phase 2 进入条件：必须确认第一版 SQLite schema convention、transaction runner、WAL / busy timeout、retry policy、payload threshold 与 artifact 目录注入方式，或者设计章节已细化到可直接生成 schema / typed contract / test matrix。
- `docs/host/implementation-control.md:376-383` 将 Phase 2 范围限定为 SQLite connection / transaction runner / bootstrap、EventLog table / appender / reader、payload table / descriptor table、idempotency table、host instance liveness foundation，并禁止 WorkerProxy、ToolRuntime、Projection、Memory、Remote transport。
- `docs/host/implementation-control.md:385-387` 进一步要求确认 EventLog row、canonical event identity、event_sequence、payload descriptor typed contract，以及 SQLite 多进程写入配置和测试策略。
- `docs/host/implementation-control.md:397-403` 建议 Slice 1 schema / transaction、Slice 2 EventLog / idempotency、Slice 3 payload / liveness，并要求 transaction atomicity、event_sequence monotonicity、idempotency conflict、WAL / busy timeout / concurrent append smoke。
- `docs/host/implementation-control.md:407-412` 说明 Phase 2 退出后，后续 phase 应能在同一事务内 append canonical facts、更新 state indexes，并依赖稳定的 schema convention、EventLog append / read、payload descriptor、idempotency primitive、host instance liveness。
- `docs/host/design.md:611-646` 已定义 durable store 是本地治理真源、EventLog append 必须分配全局单调 `event_sequence`、EventLog append 与必要状态索引更新必须在同一 SQLite transaction 内完成、payload 可与 EventLog 同事务提交，并定义 durable foundation 与后续 owner 的 table ownership。
- `docs/host/design.md:1097-1111` 已定义 EventLog append-only、不允许 Projection / audit / memory / timeline / usage / tool trace 写 EventLog，且只有 `canonical_fact` 能驱动治理状态、recovery、resume、memory verified inputs、audit 主链和 outbox terminal delivery intent。
- `docs/host/design.md:1115-1135` 给出 EventLog row 的字段清单，但没有字段类型、nullability、unique constraint、index、payload JSON canonicalization 存储形态或 event_id / event_class 唯一约束策略。
- `docs/host/design.md:1139-1145` 已定义 `event_sequence` 是 SQLite 分配的全局单调序列，`event_id` 是 Host ledger identity，canonical fact 的 `event_id` 同时是 canonical event identity，并区分 client operation id、remote event identity、canonical event identity。
- `docs/host/design.md:1147-1158` 已定义 ingest path 必须 validate、derive identity、check idempotency、classify、append accepted row inside Host transaction，并在 canonical fact 有状态副作用时同事务更新 Run / Attempt indexes。
- `docs/host/design.md:1171-1177` 已定义 EventLog 不内嵌大 payload、小中 payload 默认进 SQLite payload table、大 payload 外移并在 durable 且 digest verified 后 append canonical fact，但没有明确 threshold 默认值、descriptor table 字段、artifact root 注入 contract、external artifact write 与 SQLite transaction 之间的失败顺序。
- `docs/host/design.md:2301` 将 Recovery 输入限定为 Host durable truth：Run / Attempt indexes、EventLog canonical facts、dispatch record、wait record、payload descriptors 和 host instance liveness record；Projection / audit / tool trace / outbox / memory 等 read model 不能作为 recovery scan 前置事实。
- `docs/host/design.md:2332-2346` 定义 positive orphan proof 第一版来自本机 Host 进程存活证据，host instance durable row 推荐字段包括 `host_instance_id`、`pid`、`process_start_token / boot_id / create_time`、`heartbeat_at`、`status`，且 heartbeat 或 pid 单独都不构成 orphan proof。
- `docs/host/design.md:2397` 与 `dayu/README.md:88-89` 均规定 `host_instance_id` 不是 lease、fencing token 或远端 owner，只服务 positive orphan proof。
- `docs/host/design.md:504-508` 与 `docs/host/implementation-control.md:1246-1258` 已确认 SQLite 是第一版单机多进程 Host 真源，正确性依赖 WAL、明确 busy timeout、短事务、显式重试、唯一约束和 CAS-style state transition；但 Phase 2 仍必须明确连接配置、transaction 边界、retry 策略和错误分类。
- `dayu/README.md:71-86` 将 EventLog、canonical event、client / remote / canonical identity、Host event stream 和 `event_sequence` 作为术语真源，明确 Host event stream 来自 EventLog `event_sequence` cursor，不触发执行，远端 ordering hint 不能替代 Host 分配的 `event_sequence`。

## Goal / Success Signal / Scope Boundary / Non-goals

Phase 2 goal 成立：Host 架构要求 Host 是强约束治理真源，后续状态机、恢复、投影和外部投递都依赖可恢复、可排序、可幂等的 durable ledger。先建立 SQLite durable store 与 EventLog append primitive，是避免后续 phase 各自发明存储、幂等、payload、liveness 和事务边界的正确顺序。

Success signal 应保持为：后续 phase 可以复用同一 transaction runner，在一个 Host transaction 内 append canonical facts、写必要 foundation rows、获得全局 `event_sequence`、读取 EventLog cursor，并通过 idempotency primitive 对重复输入返回既有 accepted result 或 conflict；payload descriptor 和 host instance liveness record 已具备后续 ToolRuntime / Recovery 接入的最小稳定 contract。

Scope boundary 成立：Phase 2 应只建立 durable foundation，不实现 Session / Run / Attempt 状态机，不实现 Host command path，不 dispatch Engine，不实现 Projection、Memory、ToolRuntime、Remote transport。`docs/host/design.md:646` 的 table ownership 也支持这个边界：Session / Run / Attempt / active index / queue index 属于状态机与 admission，wait record 属于 Tool Awaiting，projection checkpoint、audit、tool trace、outbox、memory snapshot、context artifacts、purge tombstone 属于各自 phase。

Non-goals 应继续显式禁止：完整 Host API、Engine dispatch、projection sink、Session / Run / Attempt 状态迁移、wait record、ToolRuntime accept path、RemoteProxy / RemoteStub、Memory / RunInputBuilder、Audit / Tool Trace / Outbox、retention / purge tombstone、旧库迁移兼容逻辑。

## Blocking Questions For Controller

### BQ1 - SQLite schema convention / fresh DB bootstrap 仍未收敛

- **为什么阻塞**: Phase 2 要产出后续 phase 遵守的 schema convention 与 fresh DB bootstrap。当前设计只规定全新 schema 起库、SQLite durable truth 与 table ownership，但没有明确表命名、主键类型、timestamp 存储、JSON 存储、schema version / user_version、外键策略、index / unique constraint convention、bootstrap 幂等语义、是否允许空 owner 表。后续 EventLog、payload、idempotency、host instance liveness 都会受此影响。
- **建议选项**:
  - A. 在 Phase 2 plan 前由 controller 决策一个最小 convention：single SQLite DB、fresh bootstrap 创建 foundation tables、`PRAGMA user_version` 记录 schema version、TEXT ids、INTEGER unix-ms or ISO UTC timestamp、JSON as canonical TEXT、explicit unique indexes、foreign keys on、no migration compatibility。
  - B. 允许 planning agent 在 plan 中自行制定 convention。
- **推荐决策**: 选择 A。schema convention 是跨 phase 真源，不应由 planning agent现场选择。
- **不决策风险**: Slice 1 会变成 schema 设计讨论；Slice 2 / 3 的唯一约束、idempotency conflict、EventLog cursor 与后续 table ownership 无法一致 review。

### BQ2 - Transaction runner、WAL / busy timeout、retry policy 和错误分类未形成 typed contract

- **为什么阻塞**: `docs/host/implementation-control.md:374` 与 `:1257` 均要求 Phase 2 明确 transaction boundary、WAL、busy timeout、retry 策略和错误分类。当前 `docs/host/design.md:508` 只说 SQLite 使用 WAL、明确 busy timeout 和显式重试策略，具体参数属于 Host storage policy。没有 runner API、BEGIN mode、retryable error set、max attempts / backoff、busy timeout default、read transaction / write transaction 区分、after-commit hook 语义，handoff plan 无法定义多进程 tests 和 error assertions。
- **建议选项**:
  - A. 决策最小同步 SQLite transaction runner：每个 mutating command 使用短 write transaction，显式 BEGIN IMMEDIATE，PRAGMA journal_mode=WAL / foreign_keys=ON / busy_timeout，retry 仅包裹 `database is locked` / busy 类短事务失败，唯一约束冲突不 retry，after-commit callbacks 仅 commit 成功后运行。
  - B. 使用 deferred transaction，让每个 appender 自行处理 busy / retry。
- **推荐决策**: 选择 A。它符合短事务、多进程写入和 Host command path 强约束，且便于测试 transaction atomicity 与 concurrent append。
- **不决策风险**: 多进程 append smoke 无法有稳定预期；busy timeout 失败可能被误归类为 Host governance failure；projection wakeup 可能在 rollback 后误触发。

### BQ3 - EventLog row typed contract 与 idempotency primitive 的唯一约束不够具体

- **为什么阻塞**: `docs/host/design.md:1115-1135` 是字段清单，`docs/host/design.md:1139-1145` 是身份语义，但 Phase 2 要生成 EventLog table、appender / reader 与 idempotency table。当前没有确认 `event_sequence` 使用 INTEGER PRIMARY KEY / AUTOINCREMENT 还是独立 sequence row；`event_id` 是否全局唯一或只对 canonical_fact 唯一；preview / diagnostic 是否需要 event_id 唯一；idempotency record 绑定 operation scope、semantic input digest、accepted event refs 还是 target object refs；duplicate 与 conflict 的返回 shape。
- **建议选项**:
  - A. EventLog 使用 SQLite 分配的 INTEGER global `event_sequence` 作为主 cursor；`event_id` 为 TEXT ledger identity 并全局唯一；`event_class` 必填；idempotency table 以 `(scope_kind, scope_id, idempotency_key)` 唯一绑定 `semantic_input_digest`、`result_kind`、`result_ref`、`created_event_id?`、`created_event_sequence?`，同 key 不同 digest 返回 conflict。
  - B. 只对 canonical_fact 做 `event_id` 唯一，preview / diagnostic 使用 nullable event_id。
- **推荐决策**: 选择 A 作为 Phase 2 最小 typed contract。它更容易保证 reader、projection、audit 和重复 ingest 的一致性；preview / diagnostic 也可拥有 ledger identity，但不得成为 governance truth。
- **不决策风险**: EventLog appender 与 idempotency store 会互相重叠或缺口；后续 Session / Run / ToolRuntime 可能各自实现不同 idempotency semantics。

### BQ4 - Payload threshold、descriptor shape、artifact 目录注入与外移失败顺序未收敛

- **为什么阻塞**: Phase 2 要建立 payload descriptor foundation。当前设计规定小中 payload 可写 SQLite，大 payload 外移，digest verified 后才 append EventLog canonical fact，但未定义 threshold policy 的 typed option、descriptor table 最小字段、artifact root 注入、artifact ref 是否允许相对路径、SQLite transaction 与文件写入无法同事务时的顺序和清理策略。这直接影响 payload persistence、crash recovery foundation tests 和后续 ToolRuntime / fetch_more ownership。
- **建议选项**:
  - A. Phase 2 只支持两类 descriptor：`sqlite_payload` 与 `artifact_ref`。typed options 注入 `payload_inline_threshold_bytes` 与 `artifact_root`；小于等于 threshold 的 canonical payload 与 EventLog 同事务写 SQLite payload table；超过 threshold 的 artifact 由调用方或 payload store 先写入临时路径、fsync / digest verify、原子 rename 到 artifact root 后，再在 SQLite transaction 中写 descriptor + EventLog。Phase 2 不实现 tool trace cold store 或 domain repository adapter。
  - B. Phase 2 只定义 descriptor，不实现 artifact write helper，外部 artifact durable 由后续 phase 负责。
- **推荐决策**: 选择 A 的最小版，但 artifact write helper 只覆盖本地 artifact root，不进入 ToolRuntime / trace / domain repository。否则 payload descriptor 无法被多进程和 crash tests 验证。
- **不决策风险**: implementation agent 可能把大 payload 放回 EventLog JSON，或把 artifact path 写成不可恢复的绝对临时路径；canonical fact 可能引用未 durable 或 digest 不匹配的 payload。

### BQ5 - Host instance liveness foundation 的最小边界需要裁决

- **为什么阻塞**: `docs/host/design.md:2332-2346` 给出 recommended durable row 字段和 positive orphan proof 原则，但 Phase 2 不实现 recovery scan 或 dispatch record。需要确定本 phase 是否只提供 host instance registration / heartbeat row，还是同时提供 liveness checker / stale classifier。字段类型、status enum、heartbeat update ownership、process_start_token 来源都会影响 Phase 11 recovery 和 multi-process tests。
- **建议选项**:
  - A. Phase 2 只实现 host instance liveness record primitive：register current instance、heartbeat current instance、mark stopping / stopped best-effort、read instance row；字段包含 `host_instance_id`、`pid`、`process_start_token`、`boot_id?`、`created_at`、`heartbeat_at`、`status`。不实现 orphan classification，不读取 dispatch record。
  - B. Phase 2 同时实现 positive orphan proof classifier。
- **推荐决策**: 选择 A。positive orphan proof 需要 dispatch record 与 Attempt 状态，属于 Phase 11 或 dispatch / recovery phase；Phase 2 只稳定 durable row 和 heartbeat write semantics。
- **不决策风险**: Slice 3 容易夹带 recovery classifier、Attempt takeover 判断或 lease / fencing 语义，破坏 Phase 2 non-goals。

## Scope / Non-goals Enforcement

Phase 2 plan 必须禁止夹带以下后续内容：

- Session / Run / Attempt 状态机、active slot、queue promotion、cancel / retry / replay / resolve_wait state transition。
- Host public command path、Host handle 的完整 command facet、Service / UI 调用入口。
- WorkerProxy、Engine dispatch、LocalProxy / RemoteProxy / RemoteStub、EngineEvent ingest 的完整状态机。
- ToolRuntime accept path、framework tool 注入、tool fact governance、fetch_more / truncation cursor 的完整读取策略。
- Projection Core、Host event stream fanout、Memory、Audit、Tool Trace、Outbox、RunInputBuilder。
- Recovery scan、positive orphan proof classifier、old Attempt LOST / RECOVERING transition。
- Retention / purge tombstone、旧库迁移兼容、schema migration framework、服务化 DB / message queue。

Phase 2 可以为上述后续内容提供 typed primitives，但不能实现它们的业务语义。

## Recommended Slice Shape

建议 slice 仍保持总控文档的三段式，但必须在进入 plan gate 前先解决上述 blocking questions。若 blocker 已收敛，slice 可维持：

- **Slice 1: SQLite schema convention / migration-free fresh DB bootstrap / transaction runner**。该 slice 应拥有 schema convention、fresh bootstrap、connection policy、WAL / busy timeout、transaction runner、retry / error classification、after-commit boundary 与基础 transaction tests。
- **Slice 2: EventLog append / read / event_sequence / idempotency primitive**。该 slice 应拥有 EventLog row typed contract、global `event_sequence` 分配、append / duplicate / read cursor、idempotency record、unique constraints 和 concurrent append tests。
- **Slice 3: payload descriptor / host instance liveness / diagnostics foundation**。该 slice 应拥有 payload descriptor / payload table / artifact ref minimal helper、digest verification boundary、host instance registration / heartbeat primitive 与 liveness row tests。

不建议在当前证据下重排为更多或更少 slice。原因是 `docs/host/implementation-control.md:397-399` 的顺序符合依赖方向：transaction runner 是 EventLog / payload / liveness 的共同前置，EventLog / idempotency 是 canonical fact 的核心，payload / liveness 可以依赖前两者并作为 foundation 收口。需要调整的是每个 slice 的 working decisions，不是 slice 大方向。

## Recommended Next Gate

不要进入 handoff-ready plan gate。下一步应由 controller 处理 `Blocking Questions For Controller`，把决策写回设计真源或形成 controller-accepted phase design fix artifact。所有 blocking decisions 收敛后，再重新做 Phase 2 design refinement readiness check 或直接进入 plan gate。

## Residual Risks

- 本次只审阅设计真源与总控文档，没有审阅现有 `dayu/host` 代码或测试实现；该风险不影响当前结论，因为当前 gate 不是 implementation review。
- 即使 blocking questions 收敛，Phase 2 plan review 仍需重点压测 multi-process concurrent append、busy timeout / retry、unique constraint conflict、transaction rollback 后 after-commit 不触发、payload artifact crash window、host instance heartbeat ownership。
- Phase 2 只能建立 host instance liveness foundation。真正 positive orphan proof、旧 Attempt LOST、Run RECOVERING、新 Attempt 创建仍必须留给后续 recovery / state machine phase，否则会把 liveness primitive 误升级为 lease / fencing。
- Payload descriptor 的 artifact ref 与后续 ToolRuntime / trace / domain repository 的边界需要持续追踪：Phase 2 不应把财报领域仓储或 tool trace cold store 变成 Host durable store 的内部实现。

## Artifact Path

`docs/reviews/gateflow-phase-design-host-p2-codex-20260514.md`
