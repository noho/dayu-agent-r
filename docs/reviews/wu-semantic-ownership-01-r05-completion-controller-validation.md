# WU-SEMANTIC-OWNERSHIP-01 R05 Completion Controller Validation

## 1. Identity 与 verdict

- active umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- internal remediation sub-WU：R05 wait observation/state-machine ownership。
- completion report：`docs/reviews/wu-semantic-ownership-01-r05-completion-report.md`。
- validation HEAD：`29296ad257a4e169441e6a776c2dc12002ddec43`。
- accepted aggregate evidence commit：`29296ad257a4e169441e6a776c2dc12002ddec43`。
- Controller verdict：`PASS / READY_FOR_R05_COMPLETION_COMMIT`。

Controller 完整读取 343 行 completion report，并独立核对 accepted plan、plan correction、S1/S2 product/evidence commits、aggregate validation/review chain、当前 source tree、commit graph、semantic owner、finding ledger、安全保留项、deferred boundary 和两个 retained residual。报告完整且 materially accurate；没有把 R05、umbrella 或 retained residual 提前宣布完成。

## 2. Immutable evidence 与 worktree ownership

Controller 独立复算：

| 证据 | 值 |
|---|---|
| completion report SHA-256 | `7173b6d179f8e192ab14494320e08023e19ca2aabdcb6dfdf433f0b164181825` |
| 16-path binary diff digest | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` |
| ordered path-set digest | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` |
| pre-validation control SHA-256 | `34e9fb3f819e1b20fa3f2a1dec39c36acb2dabaefb9423e0d77b59f027051bf2` |

AgentCodex completion gate 前后的唯一新增路径是 completion report；既有 dirty path 只有 Controller-owned control 文档，内容 hash 未被 Agent 改动；staged path 为零。product/test/design/README 16-path transaction 与 aggregate validation 精确相同。

六个 accepted commits 均存在并形成严格祖先链：

`201eb7f5 -> cf2f832c -> c5af5613 -> ff7b0b18 -> 45fe5cc4 -> 29296ad2`。

其中 plan correction 只接受 corrected coverage measurement 与 scheduler residual 分离；S1 接受 Host timeout state-machine transaction；S2 接受 Engine no-diff/public smoke 与三个 review fixes；aggregate validation 和 aggregate review commits 只冻结组合 evidence 与最终 ledger，没有未审产品漂移。

## 3. 第一性原理与 owner closure

R05 动机真实且严重性判断正确：observation timeout 只证明本轮 Host 没有取得可发布结果，不能证明 external job lost、cancel succeeded 或 lifecycle terminal。旧实现把不确定 observation 事实提升为 `LOST` 或 timeout-only terminal abandon marker，违反 durable truth 与业务事实同源。

最终修复落在正确 owner：

1. `_wait_observation.py` 保持 token/generation/lock publication authority，no diff；不造第二 fence。
2. `WaitPoller` 把 poll/abandon timeout 解释为 transient diagnostic，并复用唯一 release/backoff 路径。
3. durable state owner 原子清 claim、写 next due、attempt 与 diagnostic；invalid timeout-only terminal primitive 被删除。
4. common resolve owner只消费 authoritative typed result；generic timeout不构造 `ResolveWaitLostOutcome`。
5. Engine 只拥有 `ToolExecutor.execute` 返回 accepted awaiting 之前的 handshake budget；`agent.py` no diff。
6. provider mode、runtime policy 与 Service composition 继续分别由 R04 的 provider config、`host_runtime.json` 与 typed Service composition 拥有；scene/name 不获得 poller authority。

没有在 Service、Engine、LLM projection、smoke fake 或测试 fixture 加 fallback、loose parse、兼容 shim 或第二业务真源。

## 4. Topic 5 completion matrix

Controller 独立确认 completion report 的 Topic 5 matrix：

- provider 的 `poll/callback/manual` mode 仍由 `tool_discovery.json` provider config 拥有；三个 packaged Fins awaiting provider 显式为 `poll`。
- cadence、backoff、observation、close、concurrency 的完整 12-field policy 仍由 `host_runtime.json` 拥有；无参 `WaitPollerRuntimePolicy()` 和 scene/name auto-enable helper 零残留。
- poll observation timeout 只写 `ADAPTER_ERROR/wait_observation_timeout`、释放 claim、backoff，Run/Wait 保持 `WAITING`。
- cancelled-abandon timeout 只写 `ABANDON_ERROR/wait_abandon_timeout`、释放 claim、backoff，保持 `CANCELLED` 且不写 `poll_abandoned_at`。
- `mark_wait_record_poll_abandon_timeout` 与 `_MarkWaitRecordAbandonTimeoutOperation` 在 production/tests 零定义、零调用；schema no diff。
- late Ready/Applied 由现有 token fence 阻断；只有下一轮 authoritative published result 可更新 durable truth。
- typed `WaitPollLost` 与 common resolver保留；只有 authoritative typed lost 或未来显式 durable evidence policy 可以 LOST。
- accepted awaiting external operation 不受 Engine handshake timeout 再次约束。
- manual 不启动 poller；callback 在没有 authenticated transport 时 pre-open fail closed；本 WU 未实现 callback transport。

## 5. Finding closure 与 final ledger

Controller 复核所有 accepted finding：

- plan `R05-PF-01..PF-04` 与 `R05-PRR-F01`：全部 closed。
- validation-plan correction `R05-S1-VAL-PD-F01` 与 `R05-S1-VAL-CV-F01`：全部 closed；scheduler bug 没有被 measurement exclusion waive。
- S1 current accepted finding：零；zero-change fix/re-review complete。
- S2 三项 accepted findings：shared durable options projection、public/durable smoke evidence、bounded fake gates均在 owner boundary closed，并经双路 full re-review。
- aggregate initial accepted finding：零；zero-change fix、Controller validation、双路 full re-review complete。
- final DS re-review 只有经过 Controller 四轮事实纠正后的版本被接受；被删除的错误并发论证不属于 accepted evidence。

最终 ledger 精确为：

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | `CLOSED / NO PRODUCT FIX` |
| no-fix observation | 3 组 | `CLOSED WITH DIRECT REASON` |
| retained residual | 2 | `OPEN AT EXPLICIT LATER OWNER / UNFIXED / UNWAIVED` |
| blocker | 0 | `NONE` |

没有 accepted finding 被留成“后续优化”，也没有 rejected/no-fix observation 被偷偷实现。

## 6. Final DS concurrency evidence correction

Controller 直接核对最终 source 与 artifact，确认报告准确记录：

- close gate 可从另一线程改变，TOCTOU 真实存在；不能用 `_poll_once` 单线程消除。
- release 使用 claim-id CAS；resolve 使用 common `resolve_wait` durable state-machine 和 `(wait_id, idempotency_key)` 幂等；late observation 使用 token fence。三条路径不是统一 claim CAS。
- production poll resolve owner 是 `_OpenHostWaitPollerFactory` 每轮创建的私有 `HostCommandHandle`；`_CommandHandleWaitResolver` 在 poller thread 直接进入 common resolve path，不经 execution `DurableActor`。
- finite drain deadline 到期后，supervisor可在 poll thread 仍存活时返回；随后 actor/scheduler teardown开始，late resolve durable write与after-commit promotion wake仍有组合风险。

因此 deadline 外风险仍归 scheduler close / terminal promotion coordination residual；aggregate PASS没有消除或 waive 它。

## 7. Verification evidence applicability

本 completion gate 只增加文档，没有改动受保护产品 transaction，因此未冒充重复执行产品测试。相同 digest 下的 accepted Controller evidence继续适用：

| gate | result |
|---|---|
| functional aggregate | `360 passed, 3 warnings` |
| durable projection/public admin focused | `11 passed` |
| fresh public awaiting smoke | PASS，11 named phases |
| S1 changed-owner coverage | `1839 passed, 2 skipped, 5 deselected`；`state.py 83%`、`wait_adapter.py 86%` |
| S2 changed-production coverage | `1840 passed, 1 skipped, 5 deselected`；`command.py 88%`、`open_host.py 85%`、`durable/options.py 100%` |
| full pyright | `0 errors, 0 warnings, 0 informations` |
| changed Ruff | PASS |
| full Ruff registry | `167 -> 165 -> 162`，只删除五条 touched-file F401，无绕过 |

Controller 本 gate 重新执行并通过 commit ancestry、16-path digest/path set、no-diff owner、timeout primitive deletion、private smoke diagnostic、duplicate durable projection、scene/default fallback、shared projection owner、whitespace 与 staged-path scans。

第一次 private-smoke scan 误把合法 production `open_host._wait_poller` 一并纳入并产生预期命中；Controller 随即把 scan纠正为只扫描 smoke private penetration，结果零匹配。这是 validation harness scope correction，不是产品或报告 finding，也没有被当成通过证据。

## 8. README 与 retained safety

README 触发处理正确：Host design/README 与 tests README 已随 owner contract更新；Engine README、根 README、`dayu/README.md` 因 Engine production、用户工作流和分层关系无变化而保持 no diff。本 completion gate只增加 review/control artifacts，不触发其它 README。

R05 保留：token/generation publication fence、claim CAS、typed LOST、bounded observation capacity、finite close drain、backoff cap、filesystem containment、allowed paths、symlink防御、Web private/local/custom-port policy、DNS/redirect/peer proof、proxy/peer fail-closed、HTTP/browser/diagnostic budgets、atomic durable/storage mutation、journal recovery、atomic write/publish、ToolRuntime cancellation与process/late-result fencing。

Topic 9 no-code决定保持：仓库没有统一 tool authorization framework，但既有局部权限配置和 defense-in-depth 安全机制继续有效。R05没有新增 permission schema/DSL、role/capability、credential broker或 sandbox。

## 9. Retained residual owner/destination

### 9.1 Scheduler close / terminal promotion coordination

- 状态：确定性真实 material bug；`UNFIXED / UNWAIVED`。
- owner：Host scheduler/lifecycle coordination。
- destination：后续独立显式 work item；umbrella final closeout必须保留明确入口；不得归 Issue 175。
- mandatory verification：`close + terminal promotion + poll timeout/late result`，覆盖 finite drain deadline内外、poll-round private handle resolve、after-commit wake、scheduler teardown与public/durable terminal一致性。

### 9.2 Cancelled-abandon 长期 capped retry

- 状态：真实终止性 residual；`UNFIXED / UNWAIVED`。
- owner：future Host durable evidence policy。
- destination：后续显式 contract/design work。
- mandatory rule：timeout、retry count、timestamp、日志或process termination都不得被猜成 LOST；只有明确、durable、authoritative evidence能改变 terminal fact，并须让 Wait、Run、trace/audit 与 LLM-facing projection同源。

两项 residual 都不是 R05 current blocker，但也不是 umbrella-final 已接受行为；后续 control/final closeout必须继续追踪。

## 10. Deferred/no-code boundary

Controller确认 completion report没有偷带：

- Issue 175 Fins Docling process isolation、hard timeout、terminate/kill；
- authenticated callback transport；
- Issues 142、151、177、178；
- scheduler residual产品修复或future durable evidence policy；
- R06+；
- unified authorization framework；
- push、PR或外部Issue状态变更。

## 11. Final decision 与 authorized scope

**R05 completion evidence通过，当前可执行 exact-scope local completion commit。**

该 commit 只能包含：

1. `docs/reviews/wu-semantic-ownership-01-r05-completion-report.md`；
2. 本 Controller validation；
3. `docs/host/issues-implementation-control.md` 对 R05 completion verdict、accepted commits、residual owner/destination与下一入口的更新。

commit完成后，R05作为 umbrella 内部 remediation sub-WU 达到 completion；`WU-SEMANTIC-OWNERSHIP-01` 仍 active。下一 gate只能是 R06 Fins transaction/complete-publication plan；R06 implementation、R07-R12、umbrella aggregate deepreview/fix/re-review/final closeout、push与PR仍须各自gate授权。
