# WU-SEMANTIC-OWNERSHIP-01 R05 Aggregate Re-Review Controller Adjudication

## 1. Gate 与最终裁决

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature、issue，也不是重新打开历史 sub-WU。
- internal remediation sub-WU：R05 wait observation/state-machine ownership。
- R05 entry base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- accepted S1 commit：`c5af5613b21673864fff072a132ac56a46cc9836`。
- accepted S2 commit：`ff7b0b1825491ee3690a45d56a059c5da00af7aa`。
- AgentMiMo full re-review：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-rereview-mimo.md`。
- AgentDS full re-review：`docs/reviews/wu-semantic-ownership-01-r05-aggregate-rereview-ds.md`。
- Controller verdict：`PASS / READY_FOR_EXACT-SCOPE_AGGREGATE_ACCEPTED_LOCAL_COMMIT`。

两路 reviewer 最终都返回 PASS，且没有新的 current material finding。Controller 接受最终 re-review 结果：R05 Topic 5 当前产品 transaction 的 accepted finding 为零；三组 no-fix observation 均有直接理由；两项 retained residual 仍真实、未修、未 waive，并保留明确 later owner/destination。当前只授权 R05 aggregate evidence 的 exact-scope local commit；R05 completion、R06-R12、umbrella closeout、scheduler 产品修复、Issue 175、callback、统一 authorization、push 与 PR 均未获本裁决授权。

## 2. Frozen transaction 与 evidence identity

Controller 相对 R05 entry base 对 aggregate validation 冻结的 16 paths 重新计算：

| 证据 | SHA-256 |
|---|---|
| 16-path binary diff | `41bd8c057cb5ff3d389f909a367a19037a65ae59ffda377cd317b9d1db4eda9a` |
| ordered path set | `ff3b00d67510c45396305a723a939b8006e9e740e61c8ff23ea6fb86e8389f4f` |
| MiMo re-review | `a9a096f425b9d7223c716423d28a29e0218ee1713279c1ab1227337d7af2fbcd` |
| DS final corrected re-review | `86a4daa199727beedbbc5444a26172e3801be510b008bd3c98cecb89426c2668` |

product/test/design/README transaction 与 aggregate validation、initial deepreview、zero-change fix 及 Controller fix validation 完全相同。两路 re-review 和本裁决只增加 review/control evidence，没有改动这 16 个路径；staged path 为零。

## 3. Final finding ledger

| 分类 | 数量 | 最终状态 |
|---|---:|---|
| accepted current finding | 0 | `CLOSED / NO PRODUCT FIX` |
| no-fix observation | 3 组 | `CLOSED WITH DIRECT REASON` |
| retained residual | 2 | `OPEN AT EXPLICIT LATER OWNER / UNFIXED / UNWAIVED` |
| blocker | 0 | `NONE` |

### 3.1 No-fix observations

1. `dayu/host/durable/options.py` 没有 `__all__`：当前只有精确模块 import，没有 package re-export 或稳定顶层 API 承诺；机械增加声明不修复 correctness、ownership 或 public contract。
2. scheduler close + promotion + poll timeout/late result 组合测试：正确 oracle 依赖已确认的 scheduler lifecycle residual；当前在 R05 增加测试会把独立 owner 偷带进来，且可能固化错误行为。它是 future scheduler fix 的 mandatory verification。
3. smoke timing margin、单次 backoff cap 与 Engine 既有 branch coverage：现有 happens-before、deadline headroom 与 R05 Engine no-diff 证据足以支持当前 transaction；没有 current correctness finding。

### 3.2 Retained residuals

| residual | owner / destination | 最终裁决 |
|---|---|---|
| scheduler close / terminal promotion coordination | Host scheduler/lifecycle coordination owner；后续独立显式 work item；umbrella final closeout 必须保留入口；不得归 Issue 175 | 确定性真实 material bug，`UNFIXED / UNWAIVED`。后续必须覆盖 `close + promotion + poll timeout/late result` 组合验证。 |
| cancelled abandon 在 provider 永不提供 authoritative terminal evidence 时长期 capped retry | future Host durable evidence policy owner；需要显式 contract/design work | 真实终止性 residual，`UNFIXED / UNWAIVED`。不得从 timeout、retry count 或 timestamp 猜 LOST。 |

## 4. Controller 对 DS 并发证据的事实纠正

Controller 不接受 reviewer 结论中的间接迹象替代真实 owner 证据。AgentDS 在同一 re-review task 内经过四轮事实纠正，最终 artifact 已删除以下错误论证：

1. 删除“`_poll_once` 单线程所以 close gate 不会在 iteration 中变化”；`WaitPollerSupervisor.close()` 可从另一线程设置 gate，TOCTOU 真实存在。
2. 删除“所有 durable write 都由 `claim_id` CAS 保护”；release 使用 claim CAS，resolve 使用 common `resolve_wait` durable state-machine 与 `(wait_id, idempotency_key)` 幂等，late observation 使用 token fence。
3. 删除“gate check 后的 resolve 已经提交给 DurableActor”；在 `_resolve_claimed_wait` 调用前并未提交。
4. 删除“execution DurableActor 的 teardown 顺序保证 poll resolve 可提交”；production poll round 由 `_OpenHostWaitPollerFactory` 打开独立 `HostCommandHandle`，`_CommandHandleWaitResolver` 在 poller thread 直接调用 common resolve path，不经 execution `DurableActor`。

最终直接证据为：

- drain deadline 内，poll-round 私有 handle 在 `_poll_once` 返回前仍存活；release、resolve、late observation 分别由各自 owner 机制约束。
- finite drain deadline 到期时，`WaitPollerSupervisor.close()` 可以在 poll thread 仍存活时返回；随后 execution actor 与 scheduler teardown 开始。late resolve durable write 与 scheduler after-commit promotion wake 的组合风险没有被 actor 顺序消除。
- 该 deadline 外风险已准确归入既有 scheduler close / terminal promotion coordination residual，不是新的 R05 current finding，也没有被 PASS verdict waive。

Controller 接受修正后的 DS artifact，而不把其被删除的中间错误论证纳入 accepted evidence。

## 5. Topic 5、retained safety 与 deferred boundary

Controller 确认当前 R05 transaction 继续满足：

- provider 的 poll/callback/manual mode 由 `tool_discovery.json` provider config 拥有；runtime cadence/backoff/observation/close/concurrency 参数由 `host_runtime.json` 拥有；Service 不从 scene/tool name 构造默认 poller policy。
- poll/abandon observation timeout 记录 transient diagnostic、释放 claim 并 backoff；不会从 timeout、重试次数或时间戳猜 LOST。
- late publication 继续由 token/generation fence 阻断；只有 authoritative typed lost outcome 进入 common resolve pipeline。
- Engine handshake timer 不限制已被接受的 awaiting 长事务。
- claim CAS、token fence、bounded observation capacity、finite close drain、typed LOST、filesystem containment、allowed paths、Web 防御、DNS/peer proof、resource budgets、atomic mutation 与 process fencing 均未删除或放宽。

本 aggregate gate 没有实施 Issue 175、callback transport、Issue 142/151/177/178、R06+ 或统一 tool authorization / permission schema。Topic 9 的 no-code 决定保持：仓库没有统一 authorization framework，但既有局部权限配置和 defense-in-depth 安全机制继续有效。

## 6. 验证适用性与 README 决定

由于 16-path product transaction digest 未变，aggregate validation 中以下 Controller 证据继续适用于同一代码：functional aggregate `360 passed`、fresh public smoke 11 phases、S1 owner coverage `83%/86%`、S2 owner coverage `88%/85%/100%`、full pyright `0 errors`、changed Ruff green、full Ruff residual `167 -> 165 -> 162`、source/propagation/security/no-diff scans 与 deterministic scheduler residual probe。

本 gate 只增加 review/control artifacts，不改变产品、测试 contract、架构、用户入口或工作流；除 control state 外不触发 README 修改。

## 7. Authorized commit scope 与下一 gate

当前仅授权一个 exact-scope R05 aggregate accepted local commit，包含：

1. 两路 initial aggregate deepreview artifacts；
2. initial Controller adjudication；
3. AgentCodex zero-change fix record；
4. zero-change Controller validation；
5. 两路 full aggregate re-review artifacts；
6. 本 final Controller adjudication；
7. 对应 `docs/host/issues-implementation-control.md` gate/state 更新。

commit 前必须再次确认 16-path digest、staged exact scope、`git diff --check` 与所有新增 artifact whitespace。commit 后下一 gate 是 AgentCodex R05 completion report，再由 Controller 做 completion validation；R05 尚未完成，R06 尚未授权，umbrella WU 继续 active。
