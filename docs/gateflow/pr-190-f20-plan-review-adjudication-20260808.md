# PR 190 F20 Plan Review Adjudication

## Gate decision

- Work unit：F20。
- Gate：`plan-review`。
- Reviewed plan：`docs/gateflow/pr-190-f20-plan-20260808.md`，reviewed SHA-256
  `795f15dc6d43027c4648ec2cd423ba0cc3b061b479326801f3c7475495c4e166`。
- Independent reviews：
  - `docs/reviews/plan-review-20260808-202420.md`（AgentDS，`FAIL`，SHA-256
    `029b3b3eb281efbcc7bbd6a7a314b7fdcc5d76d7b0332309ad2e3b46e4de0cb7`）；
  - `docs/reviews/plan-review-20260808-202626.md`（AgentMiMo，`FAIL`，SHA-256
    `80cfa9d0eae38d532baa92bc20469f0004720dbd9da36c5294df062c577df977`）。
- Controller verdict：`FAIL`。两路提出的五类 material finding 全部接受；plan 返回 AgentCodex 修订，修订后必须由
  AgentMiMo 与 AgentDS 对同一冻结 revision 独立 re-review，双路均为二值 `PASS` 才能进入实现。

本裁决不授权真实 provider 调用、F20 formal observation、B2 用户裁决、accepted oracle/scenario 语义修改或 readiness
变更。

## Controller direct verification

Controller 直接核对两份 review artifact 与 reviewed plan 后确认：

1. 两路都接受 F20 的 owner 根因链：F19 高 usage 发生在 continuation dispatch；Host proactive compaction 的 owner transition
   只在 ordinary dispatch 越过 soft threshold 时请求 compaction。F19 ordinary dispatch 全部低于 soft threshold，因此零次
   compaction 是 observation setup/material policy 边界不足，不是已证明的产品缺陷。
2. 原 R2 recipe 同时选择 `s_0013` 父 section 与其五个子 chunk。五个子 chunk 的文本均被父 section 完整包含，总计
   20,202 chars；它们拥有不同 ref 不能消除材料重复。该 recipe 不能作为 no-padding 的真实材料方案。
3. plan 的 “max accepted caps” 算式只覆盖 MemoryPolicy 五个文本字段，没有完整绑定 production renderer、完整 estimator、
   anchor/fallback typed state，也没有证明所有进入 RunInput 的动态字段存在有限 owner 上界。因此当前上界证明不成立。
4. reconnect R4 是新的 ordinary dispatch；若其 usage 再次越过 soft threshold，Host 可以合法发起第三次 proactive
   compaction。原 chain1 只按两次 compactor operation 计预算，不能覆盖该状态空间。
5. publication self-test 必须从 private typed projection 重新计算，而不能信任待校验 summary。原 plan 未冻结 skipped chain
   的 deadline-owner variant，也未逐项证明 typed count/terminal keyset 与 public summary exact equality。
6. provider-free trigger proof 虽计划使用 deterministic Runner/compactor，却没有把 worker factory identity、调用计数、真实
   provider transport 构造/调用计数与 network tripwire 冻结为可审计的 fail-closed gate。

## Finding adjudication

### F20-PA-01 — R2 父子材料重叠违反 no-padding

- 来源：DS `F20-PR-001`、MiMo `F20-PLAN-001`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：重复材料会人为放大 ordinary usage；它既不是新的真实 evidence，也不是 production duplicate-governance 能按内容自动
  合并的同 ref 重放。
- plan 修复：R2 对同一 section 的 parent/chunks 必须二选一；冻结候选 refs、parent relation、字符区间、文本 digest，并以
  production storage 结果断言 pairwise 无 ancestor/descendant 同时入选、无区间重叠、无全文包含、无同 digest。修订后的
  lower/upper trigger proof必须只使用该非重叠 recipe。若真实 AAPL corpus 中不存在能满足边界的非重叠材料，plan 应形成
  setup blocker，不得添加 padding、复制文本、降低 soft threshold 或改产品。

### F20-PA-02 — Trigger 上界缺少完整 typed owner 与 production estimator 证明

- 来源：DS `F20-PR-002`、MiMo `F20-PLAN-002`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：Host owner 比较的是 typed predicted usage；anchored path 与 fallback path 的预测式不同。MemoryPolicy 文本 caps 也不能
  自动约束所有被 renderer 写入 RunInput 的动态字段。
- plan 修复：先定位既有 typed contract 是否对完整 accepted compact output/serialized RunInput 给出有限总上界；不得在 F20
  新增产品 cap。若存在该 owner，直接使用它；若不存在，则必须明确登记为 residual owner question，并把本 work unit 的证明命题
  限定为用户要求的**合法场景存在性**：将 `MemoryProjectionPolicy`实际治理的文本字段置于各自caps，其他typed字段取合法、显式、
  有限canonical值，用 production accept → Memory → RunInput renderer → complete estimator 构造完整candidate。两种路径都必须冻结
  `E_lower`、`P_lower`、计算分支、anchor/current state、各 estimator atom、rendered digest 与 owner identity，分别证明实际适用的
  anchored/fallback等式和本场景的monotonic boundary。正式provider链还必须在每次actual accepted后、下一个ordinary dispatch前
  对完整actual snapshot执行同一production estimator的fail-closed hard-bound guard；若达到hard threshold立即seal
  `needs-more-evidence`，不得dispatch。不得把场景candidate冒充任意未治理字符串的universal worst case。

### F20-PA-03 — Reconnect 可能触发第三次 proactive operation

- 来源：MiMo `F20-PLAN-003`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：R4 是 ordinary dispatch，不继承“只读 reconnect”豁免；触发决策仍由相同 Host owner 计算。
- plan 修复：chain1 hard cap 至少按第三次 operation 增加 5 calls，即 99 calls、三链总上限 245 calls，并冻结分支断言：R4 manifest
  必须消费第二次 accepted compact truth且 operation count 保持 2，才可声明 same-truth reconnect；若 R4 开启第三次 operation，
  立即 seal 为 `needs-more-evidence`/failed branch，不得继续或声明 reconnect predicate 已满足。

### F20-PA-04 — Publication exact projection 与 skipped-chain deadline variant 不闭合

- 来源：DS `F20-PR-003`。
- 裁决：`accepted`，严重程度 `high`。
- 理由：mandatory publication contract 必须验证自己的来源和穷尽性；从 summary 读取 summary 不能证明其与 EventLog/SQLite/
  RunInput/terminal truth 同源。
- plan 修复：为每条 chain 冻结 `attempted` 与 `provider_not_started` 的 discriminated publication variant；不论是否启动，都必须有
  immutable chain/global deadline-owner ref+SHA。self-test 从 private path-redacted typed projection 独立重算 budget/count/terminal
  refs，断言与 summary exact equality、terminal ref 双向穷尽、chain keyset 与 execution-index exact equality，并增加遗漏、伪造、
  extra terminal、deadline SHA mismatch 等 fail-closed corruption tests。

### F20-PA-05 — Provider-free proof 缺少可审计的零真实 transport/network gate

- 来源：MiMo `F20-PLAN-004`。
- 裁决：`accepted`，严重程度 `medium`。
- 理由：依赖注入 deterministic worker 并不单独证明 proof 期间没有创建或调用真实 transport；pre-provider gate 必须由直接计数和
  fail-closed tripwire证明。
- plan 修复：冻结 proof-only `OpenHostOptions.worker_factory` 文件 ref+SHA、factory/ordinary/compactor identity 与调用计数；真实
  provider constructor/call 与 network access 均使用 fail-closed tripwire，记录 `real_transport_create_count=0`、
  `real_transport_call_count=0`、`network_hit_count=0` 与 credential unavailable/unused 状态。任一非零立即失败且不得继续。

## Required revised plan

修订不得扩大产品语义或降低证据标准，必须同时满足：

1. 用非重叠、可追溯的真实 AAPL materials 重做两次 ordinary trigger 的 provider-free 边界证明；禁止 padding 与 profile 热切换。
2. 精确区分“完整typed contract的universal上界”和“用户要求的合法场景存在性”。前者不存在时登记residual，不得伪称已证明；
   后者必须用governed fields at caps + bounded canonical metadata的完整candidate走production链证明，并为formal actual snapshot增加
   dispatch前fail-closed hard-bound guard。
3. 修正 R4 第三次 operation 分支和 99/73/73 = 245 calls hard cap；三条 formal chain 的互斥角色与最多三条 fresh chain 不变。
4. publication self-test 从 private typed truth 独立重算，并覆盖 attempted/provider-not-started、deadline owner、terminal exact
   complement、execution-index、逐 chain path-redacted Tool Trace、final-byte digest 与 secret-scan last-writer。
5. provider-free proof 增加零真实 transport/network 的可审计 fail-closed gate。

修订后必须生成 durable fix artifact，列出每项 finding 的修改位置与直接验证结果；再对 plan 文件 byte-level SHA 冻结并发起两路
独立 re-review。双路未 `PASS` 前禁止真实 provider。
