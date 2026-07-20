# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Controller Validation

## 1. Gate 与结论

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- validation target：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`。
- plan base：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- authoritative decision：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5 final controller decision。
- verdict：**PASS**。
- accepted validation findings：`0`。
- blocking questions：`0`。
- owner / allowlist escalation：**不需要**。
- next gate：AgentMiMo / AgentDS 对同一 immutable target 并发完整 plan review；不得进入 implementation。

本 plan 已达到 code-generation-ready 的 review 入口。它把当前错误定位在 `WaitPoller` 对 observation timeout 的业务解释，而不是误改正确的 runner fencing、durable store primitive 或 Engine handshake owner；两片切分、closed allowlist、test-first 证据、验证矩阵与 stop conditions 均足够约束后续实施。

## 2. 动机与 root cause 复核

动机成立，且严重性评估准确。

当前代码的直接调用链是：

```text
WaitObservationRunner.observe(...)
  -> timeout 时在同一 token/generation owner 内撤销 publication authority
  -> WaitPoller.poll_once() 收到 WaitObservationTimedOut
  -> 当前错误地构造 WaitPollLost(ResolveWaitLostOutcome(...))
  -> common resolver 将 Wait / Run 收为 LOST
```

cancelled-wait abandon 分支同源地把 `WaitObservationTimedOut` 投影到 `_MarkWaitRecordAbandonTimeoutOperation`，写入 `poll_abandoned_at` 并停止后续观察。两条路径都把“本次同步查询没有按时返回”错误提升为 durable business/lifecycle terminal fact。

这不是 runner token/fence 缺陷：`dayu/host/_wait_observation.py` 已在 timeout 时 invalidates 当前 token，`_publish` 以 token identity、state、closed 与 generation 共同拒绝 late result。也不是 store 能力缺口：`release_wait_record_poll_claim(...)` 已原子支持 `WAITING` / `CANCELLED`，能清理四个 claim 字段并写入现有 next-observe、backoff attempt 与 poll-local diagnostic 字段。

因此正确修复边界是 `dayu/host/wait_adapter.py` 的 `WaitPoller` decision owner，复用既有 `_release_with_backoff(...)`；不得新增 schema、timer、scheduler、token/fence、lost outcome 或下游兼容分支。

## 3. 裁决与设计真源一致性

计划逐项满足 Topic 5 final decision：

| 裁决 | plan 映射 | 结论 |
|---|---|---|
| observation timeout 撤销 late publication | 保留唯一 `WaitObservationRunner` token/generation fence，并要求 late result dropped | PASS |
| 写 transient diagnostic、释放 claim、policy backoff | poll / abandon timeout 都复用 `_release_with_backoff(...)` 与既有 durable release operation | PASS |
| timeout 不得把 Wait / Run 标成 LOST | 删除 timeout -> `WaitPollLost` / common resolver reachable path | PASS |
| LOST 只来自 authoritative typed outcome 或显式 durable Host evidence | 保留 provider `WaitPollLost`，不创建 heuristic policy | PASS |
| cancelled-wait abandon timeout 同样 non-terminal retry | 删除 timeout-only abandon terminal operation 调用，保持 `CANCELLED`，不写 `poll_abandoned_at` | PASS |
| accepted awaiting 外部长事务不受 Engine handshake timeout | 先加 regression，预期 `agent.py` production no diff；public smoke 覆盖长事务、Host 后续 resolve | PASS |
| Issue 175 不越界 | process isolation / physical cancellation 明确 stop/deferred | PASS |

`docs/host/design.md` 中 “abandon timeout diagnostic/close marker” 不能解释为继续写 `poll_abandoned_at` 的 terminal marker：同一设计段落、controller final decision 与 umbrella R05 manifest 已明确要求 synchronous abandon observation timeout 释放 claim、进入 backoff，并删除 timeout-only abandon-terminal operation。计划采用这一唯一一致解释，没有设计矛盾或 owner 不清。

## 4. Owner 与 allowlist 裁决

### 4.1 Production owner

- `dayu/host/wait_adapter.py`：唯一预期 production diff；拥有 observation result interpretation、claim release 与 policy cadence。
- `dayu/host/_wait_observation.py`：publication authority owner；当前证据正确，预期 no diff。
- `dayu/host/waiting.py`：typed terminal resolution owner；当前证据正确，预期 no diff。
- `dayu/host/durable/state.py`：现有 atomic release primitive 足够，保持 read-only。
- `dayu/engine/agent.py`：只拥有 `ToolExecutor.execute` handshake timeout；当前源码在 accepted awaiting 后不复用同一 timeout，预期 no diff。

### 4.2 `durable/state.py` 不扩域

`mark_wait_record_poll_abandon_timeout(...)` 是旧 policy 的 store primitive，但不是当前 reachable transition 的 owner。R05 只需在 allowlist 内删除 `_MarkWaitRecordAbandonTimeoutOperation`、相关 import 与调用，使该 primitive 无 production caller。仅为删除一个不可达 helper 而扩大 production allowlist，会把 behavior remediation 扩成无必要的 storage cleanup；当前不接受。

若 implementation 证明该 call graph 无法在 `wait_adapter.py` 内切断，必须触发 plan 的 stop condition，不能自行扩域。

## 5. 两 slice 原子性

R05 保持 umbrella 已裁决的两片最小边界：

1. `R05-S1` 是唯一 production semantic transaction：在 Host owner 内完成 timeout non-terminal release/backoff，并证明 late-publication fence、provider typed terminal、exception/capacity/CAS/close-drain 分支不回归。
2. `R05-S2` 是跨层 contract evidence transaction：新增 Engine handshake regression、增强真实 public Host awaiting smoke、更新触发 README；生产 `agent.py` 必须 no diff。

两片之间存在清晰 handoff：S2 只在 S1 已提供正确 Host transition 后验证 public composition 与 Engine no-diff contract。合并会把 root fix 与跨层 acceptance oracle 混成一个 review target；继续拆分则只增加无语义价值的 gate。当前切分通过。

## 6. Test-first、验证矩阵与基线

计划已明确：

- 当前 `41 passed` Host owner collection 中两条测试正固化错误语义，绿色不能否定 root cause；新断言必须先在未改 production 的 base 上精确红，再由 owner 修复转绿。
- authoritative `WaitPollLost`、explicit lifecycle terminal outcome、adapter exception、capacity、CAS、claim、close-drain 与 wait deadline 均有 preservation 检查。
- Engine regression 同时证明 accepted awaiting 外部 operation 可超过 handshake budget，以及 executor handshake 未返回仍按既有 timeout 失败。
- public smoke 使用 packaged config/discovery/Service/open_host/durable poller/public terminal/outbox 主链，不以私有 direct-resolve 或 durable due-time 篡改伪造验收。
- smoke timing 明确满足 `handshake budget < observation timeout < operation duration < timeout + initial backoff`，并等待真实 backoff 到期后再次 observation。
- actual changed production files 逐文件 coverage `>=80%`；不得用聚合覆盖率掩盖。
- full pyright 必须继续为零；changed-file Ruff 必须归零。
- 全量 Ruff `167` 条既有基线按六元组登记；changed test 中现有 `F401 datetime.UTC` 必须消除，不能继承或 ignore。
- `git diff --check`、closed allowlist、timeout-to-terminal、late token、claim/backoff、R04 ownership、安全/延期 scope scans 均已给出可执行命令与人工判定标准。

计划识别并替换了 umbrella 中会收集零节点的旧 Service 命令，改用 exact non-empty Service/config/Fins owner nodes；这是验证命令修正，不是产品 scope 变化。

## 7. README 与安全边界

- `dayu/host/README.md` 与 `tests/README.md` 命中职责范围，计划在 S2 写入已实现 contract。
- `dayu/engine/README.md` 已覆盖 handshake 定义，`agent.py` no-diff 时不机械修改。
- 根 README 与 `dayu/README.md` 不触发。
- R05 保留现有 token/generation fencing、claim CAS、capacity cap、finite observation/close budget 与 late-publication rejection。
- R05 不实现统一 tool authorization framework，不修改 Web/Doc 权限或其它安全策略，不实施 Issue 175。

## 8. Controller 决定

Controller 接受该 plan 进入完整双路 plan review，且不新增 owner、allowlist 或产品裁决。

reviewers 必须重点挑战：

1. cancelled-wait timeout 的 retry 是否会被 `poll_abandoned_at` 或 due-query 条件意外阻断；
2. late publication、claim release 与下一轮 Ready/explicit lifecycle terminal 是否由同一 durable record 闭环；
3. public smoke 是否真正跨过 Engine handshake budget 并等待 Host policy backoff，而非只测试独立 sleep；
4. `agent.py` no-diff 判定是否被 `BatchToolExecutionContext.timeout_seconds` 的协作语义误读；
5. Ruff baseline registry 与 exact node commands 是否能在 implementation completion 中复现。

在 plan review、AgentCodex plan-fix artifact（即使 accepted findings 为零也必须有 zero-change artifact）以及双路完整 re-review 全部完成并由 Controller 裁决前，不得进入 implementation。
