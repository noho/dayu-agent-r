# Host Phase 1 Design Re-Review (Round 2 after User Feedback)

## Review Gate

phase design re-review after user feedback round 2

## Reviewer

AgentMiMo

## Reviewed Target

- Round2 fix artifact: `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`
- Updated docs: `dayu/README.md`, `docs/host/design.md`, `docs/host/implementation-control.md`

## Per-Item Re-Review Result

### 1. lane 是否已从 process-local 正确改为 cross-process named semaphore / capacity guard

**结果: PASS**

证据：

- `dayu/README.md:121` 术语表 `lane` 条目明确写为「层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的具名容量治理」。无 process-local 残留。
- `docs/host/design.md:66` §3 写为「层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的业务并发、LLM 并发或其它非真源资源容量治理」。
- `docs/host/design.md:77` §3.1 开头写为「层中立、cross-process 的 async named semaphore / capacity guard primitive。它用于单机多客户端 / 多进程下对 LLM provider 调用、外部 API 调用、CPU / IO worker 等非真源资源做容量保护。它提供同一机器、同一 runtime lane coordinator 下的跨进程容量计数」。
- `dayu/README.md:143` Runtime 节写为「`lane`：cross-process named semaphore / capacity guard」。
- 全仓库 grep `process-local` / `不提供跨进程` / `跨进程全局容量` 仅命中旧 review artifact（fix round1 和 fix2 自身引用），不出现在 `dayu/README.md`、`docs/host/design.md`、`docs/host/implementation-control.md` 三个目标文件中。
- 项目目标「支持单机多客户端 / 多进程」在 `dayu/README.md:14`、`docs/host/design.md:9`、`docs/host/implementation-control.md:16` 三处均对齐。

lane 设计正确表达为 cross-process，与项目目标一致。

### 2. cross-process lane 设计是否仍保持 runtime capacity boundary

**结果: PASS**

逐项核查 lane 不越界的声明：

- `docs/host/design.md:66`：「lane 只表达资源容量，不表达 Session / Run / Attempt owner，不替代 Host admission、SQLite transaction、CAS 状态迁移、EventLog ordering、fencing token、Attempt takeover 或 recovery proof」。
- `docs/host/design.md:154-155`：「claim_id 必须是不可猜测的随机 id；owner 默认由 runtime 根据当前进程生成...owner identity 只用于 runtime cleanup / diagnostics，不是 Host owner」。
- `docs/host/design.md:173-174`：「stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能驱动 Host recovery，不能写 EventLog」、「heartbeat / TTL 不是 lease / fencing。即使某个 expired claim 被清理，也不授权旧 worker takeover，也不证明旧 side effect 已停止」。
- `docs/host/design.md:181`：「lane token 不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner、不是 dispatch record 状态」。
- `docs/host/design.md:182`：「acquire 成功只表示当前 owner 在 runtime coordinator 中拿到资源容量；执行任何副作用前，Host 后续 dispatch phase 仍必须在短事务内 recheck durable precondition」。
- `docs/host/design.md:147`：「SQLite transaction 只保护 runtime capacity claim 的原子计数和 release；它不是 Host transaction、不能兜底 Host state machine，也不能被任何层解释为 resource fencing」。
- `dayu/README.md:121`：「lane acquire 是可取消的耗时操作；调用方 / supervisor 退出时必须同时触发 Host cancel 与 lane cancel」。
- `dayu/README.md:143` Runtime 节：「它只表达单机多进程的具名资源容量控制，可被 Host、Service、Fins 或其它层复用；它不能表达 Session / Run / Attempt owner，也不能替代 Host admission、SQLite transaction、CAS 状态迁移、lease / fencing、Attempt takeover、EventLog ordering 或 recovery proof」。
- `docs/host/implementation-control.md:199-200` 强制约束：「phase plan、implementation 或 fix 不得把 lane token、`dispatching`、`dispatcher_instance_id` 当作 Host truth、lease / fencing token 或 Attempt owner；lane 只能表达资源容量，不能替代 admission、事务、CAS 或 EventLog ordering」。

lane 边界声明完整且三处文档一致。cross-process 改造未引入 Host truth 泄漏。

### 3. SQLite runtime lane coordinator 选型是否可实施且边界清楚

**结果: PASS**

证据：

- `docs/host/design.md:79-84` 列出选型理由：单机多进程需原子 compare-and-claim、SQLite 是 Python 3.11 标准库能力、独立文件不复用 Host durable store、filelock 不提供可查询状态和 TTL cleanup。
- `docs/host/design.md:104-108` `SQLiteLaneCoordinatorConfig` shape 包含 `db_path: Path`、`create_parent_dirs: bool`、`busy_timeout_seconds: float`、`poll_interval_seconds: float`，显式注入。
- `docs/host/design.md:144-148` 注入约束：「`LaneController.open(...)` 必须显式接收 `SQLiteLaneCoordinatorConfig`；调用方传入独立 runtime lane DB 路径...`db_path` 不得默认为 Host durable store 路径，不得从 Host package 读取配置，也不得通过模块级全局 singleton 隐式创建」。
- `docs/host/design.md:146-147` schema 约束：「coordinator schema 只允许保存 lane capacity coordination 所需的 rows...不得保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段」。
- `docs/host/design.md:149`：「`busy_timeout_seconds` 只限制 runtime coordinator SQLite busy 等待；Host command path SQLite busy policy 属于 Host durable store，不由 runtime lane 决定」。
- `docs/host/design.md:153` 短事务 claim/release：「acquire() 成功时，coordinator 在短事务内先清理同一 lane 中 `expires_at <= now` 的 stale claims，再在 active claim 数量小于 capacity 时插入一条新 claim」。
- `docs/host/design.md:156` 幂等 release：「`LaneClaimToken.release()` 必须异步、幂等，并在短事务内按 `(lane_name, claim_id, owner_id)` 删除 claim」。
- `docs/host/design.md:166` 等待轮询：「等待 acquire 的轮询必须通过 SQLite 短事务重试；不得在一个长事务里等待容量释放」。

独立 runtime DB、显式注入路径、短事务 claim/release/stale cleanup、不复用 Host durable store——四项边界约束均已明确且可实施。

### 4. Phase Map 是否按用户裁决重排

**结果: PASS**

核查 `docs/host/implementation-control.md` Phase Map：

- `:934` — `### Phase 12. ToolsDiscovery / ScenePrepare`（正确，原 P12 位置现在是 ToolsDiscovery / ScenePrepare）
- `:1000` — `### Phase 13. Audit / Tool Trace / Outbox Projections`（正确，原 P12 projection 后移 P13）
- `:1058` — `### Phase 14. RemoteProxy / RemoteStub`（正确，原 P13 后移 P14）
- `:1116` — `### Phase 15. Retention / Purge / Production Hardening`（正确，原 P14 后移 P15）

引用一致性核查：

- `:318` Phase 1 关键设计问题：「ToolsDiscovery / ScenePrepare 只作为后续 Phase 12 的 boundary constraint；Phase 1 不实现它们，Phase 12 必须补齐 typed manifest / provider contract」— 引用正确。
- `:332` Phase 1 Deferred Slice：「Phase Map 已重排为 Phase 12 ToolsDiscovery / ScenePrepare，原 Audit / Tool Trace / Outbox Projections 后移到 Phase 13」— 明确记录重排。
- `:497` Phase 4 不做：「不实现 `purge_session` 的 destructive cleanup；该能力在 Phase 15 落地」— 引用正确。
- `:527` Phase 4 后续依赖：「`purge_session` public signature / `PurgeSessionResult` / idempotency contract 在本 phase 稳定，destructive cleanup 在 Phase 15 落地」— 引用正确。
- `:875` Phase 11 后续依赖：「远端 orphan execution 仍按 RemoteProxy phase 和 exactly-once 非目标治理」— 未写具体 phase 编号但语义指向 Phase 14，可接受。
- `:961` Phase 12 不做：「不实现 Audit / Tool Trace / Outbox projection；该能力在 Phase 13」— 引用正确。
- `:1129` Phase 15 前置条件：「Phase 8 projection core、Phase 11 recovery、Phase 13 Audit / Tool Trace / Outbox、Phase 14 remote 已完成」— 引用正确。
- `:1287` 追踪区 Session Purge：「Phase 4...Phase 15. Retention / Purge / Production Hardening 必须细化删除范围」— 引用正确。
- `:1303` 追踪区 Host 跨层测试：「Phase 14. RemoteProxy / RemoteStub 必须提供迟到事件、断连、重发和 accept ack 测试」— 引用正确。
- `:1305` 追踪区：「Phase 13. Audit / Tool Trace / Outbox Projections 必须提供 Outbox、audit、usage、tool trace 的幂等追平测试」— 引用正确。
- `:1319` 追踪区 UI/Service Outbox：「Phase 13. Audit / Tool Trace / Outbox Projections 必须保证 outbox item 携带稳定...」— 引用正确。

Phase Map 重排正确，所有跨文件引用已同步到新编号，未发现旧 Phase 12/13/14 引用残留。

### 5. 是否仍有 process-local / 不提供跨进程容量等旧表述残留，或旧 Phase 12/13/14 引用误导

**结果: PASS**

全仓库 grep 结果：

- `process-local` 仅出现在旧 review artifact（fix round1 和 fix2 自身引用历史），不出现在三个目标文件中。
- `不提供跨进程` 仅出现在旧 review artifact，不出现在三个目标文件中。
- `跨进程全局容量` 仅出现在旧 review artifact，不出现在三个目标文件中。
- 旧 Phase 编号引用：Phase 12 全部指向 ToolsDiscovery / ScenePrepare（正确），Phase 13 全部指向 Audit / Tool Trace / Outbox（正确），Phase 14 全部指向 RemoteProxy / RemoteStub（正确），Phase 15 全部指向 Retention / Purge / Production Hardening（正确）。未发现指向旧 scope 的误导引用。

## New Blockers

无。

## Open Questions / Residual Risk

1. **SQLite lane coordinator 实现细节 deferred**：Phase 1 implementation-ready plan 仍需选择具体 error class naming、SQLite schema detail、heartbeat task ownership 实现细节和 test file placement。design 已足够支撑 handoff-ready plan，不阻塞 re-review。
2. **runtime lane DB 路径注入**：cross-process lane 使用 runtime SQLite coordinator 引入 workspace-level runtime DB 文件；后续 plan 必须明确默认路径注入策略、cleanup 策略和 busy timeout 测试。已在 fix2 artifact residual risks 中记录。
3. **ToolsDiscovery / ScenePrepare 业务 provider deferred**：具体业务 provider 与财报 prompt 内容仍属于 Service / Fins / 配置 work unit，不属于 Phase 12 runtime assembly 本体。已在 fix2 artifact residual risks 中记录。

## Review Conclusion

Round 2 fixes 全部通过 re-review。5 项检查均为 PASS，无 new blocker。

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review2-host-p1-mimo-20260513.md`
