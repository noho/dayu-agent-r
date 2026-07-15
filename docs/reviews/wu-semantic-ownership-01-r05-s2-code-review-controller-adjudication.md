# WU-SEMANTIC-OWNERSHIP-01 R05-S2 Code Review Controller Adjudication

## 1. Gate 与 verdict

- umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU、feature 或 issue。
- review target：R05-S2 Engine no-diff regression、public awaiting smoke、README current contract、验证证据与 retained/deferred boundary。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-mimo.md`。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-ds.md`。
- Controller verdict：`PASS_WITH_ACCEPTED_FIXES / FIX_REQUIRED`。

两路 reviewer 都确认 Engine 握手 timeout 的现有 production owner 无需修改，新增 regression 首次即绿；public smoke 也真实经过 packaged config、provider discovery、Service composition、`open_host`、durable poller 与 public terminal/outbox 主链。当前缺口不在产品等待状态机，而在 smoke 为取证新引入的私有 Host 穿透、重复 durable options 投影和失败路径无界阻塞。它们必须在本 slice 内修复，不能因为位于 `utils/`、严重度较低或当前 smoke 已绿而延期。

## 2. Finding ledger 裁决

### 2.1 Accepted current findings

| finding | Controller disposition | 修复边界 |
|---|---|---|
| MiMo-001 / DS-02：smoke `_durable_options()` 重复 `OpenHostOptions` 到 `HostDurableStoreOptions` 的 construction 投影 | `ACCEPTED_CURRENT_FIX`。同一 durable construction 语义已有 production owner；测试脚本复制字段映射会形成第二维护真源。typed fail-closed 只能降低错误后果，不能消除 ownership drift。 | 在 Host durable/construction owner 提供一个直接、typed、可复用的最小 helper，production command/open-host 与 smoke 共享；删除 smoke 的重复嵌套构造。不得直接把另一个模块的下划线私有 helper 当公共契约，不得增加兼容 wrapper/facade，也不得让 `dayu.runtime` 反向依赖 Host。 |
| MiMo-002 / DS-01：smoke 通过局部 Protocol + `cast` 访问 `_HostHandle._wait_poller` | `ACCEPTED_CURRENT_FIX`。这把 Host 私有字段名伪造成测试公共 contract，与本 umbrella 的 semantic ownership 目标直接冲突。 | 删除 `_WaitPollerDiagnosticsHost`、private cast 和对 `_wait_poller` 的直接依赖。不得为了 smoke-only 取证扩张 `Host` public API 或暴露 supervisor。应通过 public Run/outbox、durable Wait owner facts，以及受控第二次 observation 已进入但尚未返回的同步边界，证明首个 late Ready 没有发布权。S1 owner-level runner diagnostics tests 继续拥有 `dropped_count` 内部诊断断言。 |
| DS-05：首轮 fake poll 的 `operation_finished.wait()` 无界阻塞 | `ACCEPTED_CURRENT_FIX`。正常路径只有 0.30 秒不代表异常/失败路径可以永久占用 daemon observation thread；Host close timeout 也不是测试 fake 的 ownership 替代。 | 使用现有命名 timeout/deadline 常量做有限等待，超时 fail-fast 并给出可诊断错误；不得新增魔法数字或改变 production poll/close 语义。补齐或更新对应 smoke assertion/cleanup evidence。 |

### 2.2 Rejected as current defects / no-fix observations

| finding / observation | Controller disposition | 理由 |
|---|---|---|
| MiMo-003：单文件约 2200 行 | `NO_CURRENT_DEFECT / NO_STRUCTURAL_SPLIT` | 行数本身不是 God script 的直接证据；两路逐 helper 走读确认职责已分离。当前不为满足体量偏好拆新 support module。accepted fixes 可自然删除不再需要的私有诊断/重复投影代码。 |
| MiMo-004：test-effective `backoff_max == initial` | `NO_CURRENT_DEFECT / NO_FIX` | 本 smoke 只验证第一次 timeout 的 initial backoff 与真实 due，不承担多轮指数增长或 cap 覆盖；R05-S1 owner tests 已拥有 backoff 算法 contract。改成两倍只改变未到达分支，不增加本场景证据。 |
| DS-03：Engine fake operation 与 Agent 同 event loop | `NO_CURRENT_DEFECT / NO_FIX` | 独立 task 在握手返回后继续、跨越 timeout 且未被取消，已直接证明 Engine timer ownership 边界。引入线程不会改变被测 production 分支，只会增加测试调度复杂度。 |
| DS-04：0.03 秒 margin 在极慢 CI 理论 false negative | `NO_CURRENT_DEFECT / NO_FIX` | durable 状态一旦成立不会瞬时消失；事件/condition、单调总 deadline 与实测 headroom 已形成直接证据。未来真实 CI 失败再按直接数据调整。 |

### 2.3 Final ledger

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 3 | OPEN，进入 AgentCodex fix |
| rejected-as-current-defect observation | 4 | CLOSED / NO FIX |
| retained R05 residual | 2 | cancelled long retry 的 future Host durable evidence policy；scheduler close / terminal promotion coordination |
| blocker | 0 | NONE |

两项 retained residual 都沿用 accepted R05 plan/S1 裁决：不得在 S2 中推断 LOST、修改 scheduler、创建替代 issue 或归入 Issue 175。

## 3. Controller 复核

Controller 完整读取两份 review artifact，并确认：

1. `dayu/engine/agent.py` 无 diff；handshake timeout 仍只拥有 executor handshake，accepted awaiting 后的外部 operation 生命周期不归 Engine timer；
2. regression fake 有明确 timing、未取消、event sequence、terminal cleanup 断言，不是只验证自身字段的 self-proof；
3. public smoke 当前 11 phase 在 Controller fresh workspace 独立通过，首轮 timeout 后 Run/Wait 保持 `WAITING`、claim release、attempt/backoff、`ADAPTER_ERROR/wait_observation_timeout`、无 terminal outbox，第二轮 authoritative Ready 后 public Run/outbox 同源终态；
4. `dropped_count` 是 observation runner 内部诊断，不是 Service/Host public business fact；R05-S2 smoke 不应为了读取它暴露或穿透 Host internals；
5. durable Wait row 是正确 owner，独立 read 可以保留，但 construction options 必须复用唯一 typed projection source；
6. branch-aware `78%` 与 statement `597/742=80.458%` 解释忠实，且 `agent.py` 没有 production diff；Host S1 owner files 仍为 `83%/86%`；
7. retained safety、scheduler residual、Issue 175、callback、统一 authorization 与 R06+ boundary 均保持。

## 4. Fix 要求

AgentCodex 必须修复三项 accepted findings，并新增：

`docs/reviews/wu-semantic-ownership-01-r05-s2-code-review-fix-codex.md`

必须满足：

1. 先判定 durable construction projection 的唯一 owner，再用最小 typed helper 消除 production/smoke 重复；完整中文 docstring 与严格类型签名；
2. 删除 smoke 对 `_wait_poller`、局部 diagnostics Protocol、`cast` 与 runner `dropped_count` 的依赖，不新增 Host public diagnostics API；
3. 通过受控 adapter 第二轮 observation 同步点，加上 public Run/outbox 与 durable Wait facts，证明首轮 late result 无发布权；不得用固定 sleep、内部字段、`.resolve_wait()` shortcut、状态时间戳推断或人工修改 due time；
4. 首轮 blocking fake 必须有限等待、超时 fail-fast，并保留 finally cleanup；
5. 不实施 scheduler residual、Issue 175、callback、统一 authorization、R06+ 或其他 deferred scope；不修改 Engine production behavior；
6. 重跑 public smoke 至少两次、Engine full file、R04 owner matrix、R05 aggregate、affected Host tests、changed-file coverage、full pyright、Ruff registry comparison、`git diff --check`、README trigger/source/security/no-diff scans；
7. 不 stage、不 commit、不 push。fix 完成后仍须 Controller 独立验证和 AgentMiMo/AgentDS 双路完整 re-review。

## 5. 下一 gate

下一 gate：AgentCodex `R05-S2 accepted code-review findings fix`。

R05-S2 accepted local commit、R05 aggregate、scheduler 产品修复、Issue 175、callback、统一 authorization、R06-R12、push 与 PR 均未授权。
