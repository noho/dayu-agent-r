# WU-SEMANTIC-OWNERSHIP-01 R04 Plan Re-Review Controller Adjudication

## 1. 裁决对象

- plan：`docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`（最终 212 行）
- 第一路完整 re-review：`docs/reviews/wu-semantic-ownership-01-r04-plan-rereview-mimo.md`
- 第二路完整 re-review：`docs/reviews/wu-semantic-ownership-01-r04-plan-rereview-ds.md`
- plan-fix：`docs/reviews/wu-semantic-ownership-01-r04-plan-fix-codex.md`
- Controller validation / re-validation：`docs/reviews/wu-semantic-ownership-01-r04-plan-fix-controller-validation.md`
- 代码基线：`f7006a80`；当前 `dc565d8c` 仅包含 R03 完成与 R04 入口状态迁移

本裁决仍属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R04 overdesign remediation continuation，不创建新 WU，也不重新打开旧 sub-WU。

## 2. 双路结论

- AgentMiMo：`pass`，`0` 个 accepted findings，`0` 个 blocking questions。
- AgentDS：`pass-with-risks`，提出 `3` 个 accepted-candidate、`1` 个 observation，`0` 个 blocking questions。
- 两路均确认 `R04-PLAN-F01..F04` 与 `R04-PLAN-CV-F05` 已关闭，唯一原子 S1 完整保留 umbrella 原 S1/S2/S3 mandatory baseline，Host API/open_host、安全机制与 deferred scope 边界保持不变。

## 3. 新 candidate 逐项裁决

### R04-PLAN-RR-F01：要求 plan 固定 typed metadata 的具体私有数据结构与 `_binding_for_tool_name` 精确签名

**裁决：rejected-with-reason；不是 contract 缺口。**

直接证据：plan §4.2 已规定进入后续装配的私有 typed metadata 必须携带 provider id、tool name、absolute workspace root、既有 source/version facts 与唯一 Fins owner 解析出的 `AwaitingResolutionMode`，并禁止后续重读 raw mode；§6.1 又规定 activation registry 消费全部 active metadata、poll registry 只消费 `poll` metadata、binding 按同一个 typed mode 映射，且 `_compose_options` 一次写入最终结果。当前代码存在 `_FinsAwaitingProviderMetadata`、`_FinsAwaitingRegistryInputs`、`build_fins_wait_adapter_registry` 等多个可安全重构节点，具体是扩展现有私有 dataclass、引入新的私有 typed entry，还是让 builder 接受 typed entry，属于实现层在上述 contract 下的最小结构选择。

Reviewer 建议把签名固定成 `(tool_name, mode)` 反而会提前排除“单个 typed entry 贯穿 binding 与 registry”的更强同源实现，并不能由产品裁决或当前 public contract 唯一推出。Controller 不用 plan 规定私有 helper 形状；implementation review 必须检查 mode 只解析一次、所有消费者复用同一 typed source、没有 raw reread 或第二 mode owner。

### R04-PLAN-RR-F02：Python `bool` 是 `int` 子类，ConfigLoader 可能错误接受布尔值

**裁决：rejected-as-duplicate；已有明确 contract 与 mandatory negative test。**

直接证据：plan §2 已写明“整数位拒绝 bool”；§5.2 再次要求 ConfigLoader 对“bool 冒充数值”失败；§7 要求新增/修改行为具有 owner contract 与 negative 断言。`isinstance(True, int)` 是实现时必须正确处理的 Python 细节，不是 plan 缺失的产品语义。implementation 与 code review 必须用 `claim_batch_size=true`、`max_outstanding_adapter_calls=false` 等 owner-level negative cases验证该既有 contract，但无需再次改写 plan。

### R04-PLAN-RR-F03：要求 plan 预先选择 provider pre-validation 的 helper 拆分方式

**裁决：rejected-with-reason；所需顺序与 owner 已明确，具体 helper 拆分不应由 plan 过度设计。**

直接证据：plan §2 把 provider mode 装配校验唯一归 Service provider-assembly boundary；§4.2 固定“遍历全部 effective configs → 依据现有 identity 路由 → Fins parser 严格解析（含 disabled）/recognized non-awaiting 字段存在性拒绝 → 再做 enabled 与 available-tool filtering → 只传播 typed metadata”的顺序。该 contract 已排除当前函数先过滤 disabled 的旧行为和 loose parsing。

强制新增独立 `_validate_*` pass 可能重复遍历、重复解析并产生 validation result 与 collection result 两个真源；把全部逻辑直接塞入旧函数也可能形成职责膨胀。正确结构必须由 AgentCodex根据当前调用图选择，但只能产生一次 typed validation/collection 结果并供 activation、binding、poll registry 与 composition 复用。该要求属于既有单一真源 contract 的实现审查点，不需要 plan 固定 helper 名称或数量。

### R04-PLAN-RR-F04：`test_import_boundary.py` 只在验证命令、不在修改 allowlist

**裁决：observation / no-fix。**

§4.1 是可修改文件 allowlist，§7 是必须运行的验证集合；import-boundary test 应运行但不应因本 WU 修改。二者没有矛盾。

## 4. 最终 finding ledger

| finding | 最终状态 |
|---|---|
| `R04-PLAN-F01..F04` | closed |
| `R04-PLAN-CV-F05` | closed |
| `R04-PLAN-RR-F01` | rejected-with-reason；私有结构由既有 typed source-of-truth contract 约束 |
| `R04-PLAN-RR-F02` | rejected-as-duplicate；bool/int negative contract 已明确 |
| `R04-PLAN-RR-F03` | rejected-with-reason；不预设私有 helper 拆分，禁止重复解析/双真源 |
| `R04-PLAN-RR-F04` | observation / no-fix |

Controller accepted findings：`0`。Blocking questions：`0`。没有遗留 plan fix，也不需要再次 re-review。

## 5. 边界与授权

- provider config 仍唯一拥有 `poll/callback/manual` mode；Fins 共享 parser 是唯一 raw mode parser。
- `host_runtime.json` 仍唯一拥有完整 12 字段部署 snapshot；ConfigLoader 只做层中立 typed projection。
- Service 只基于 typed inputs 组合 registry 与 Host policy；scene 不拥有 poller authority。
- Host policy dataclass、WaitPoller 与 supervisor 删除 deployment defaults/fallback；Host public API 与 `open_host.py` 不改。
- callback transport 继续 fail-closed；R05 timeout/LOST、Engine handshake、Issue 175、Issues 142/151/177/178、统一 tool authorization、permission DSL 与后续 sub-WU 均未授权。
- 现有身份、文件边界、网络、storage、process、cancel、durable wait 与 ToolRuntime 安全机制必须保留。

## 6. Verdict

**`PASS / PLAN_ACCEPTED / AUTHORIZE_EXACT-SCOPE_LOCAL_PLAN_COMMIT_ONLY`**

最终 212 行 plan 已达到 code-generation-ready。当前只授权把 plan、完整 plan review/fix/re-review/adjudication 链与对应 control 状态做 accepted local commit；在该 commit 被记录并由 Controller 显式切换 gate 前，R04 implementation 仍未授权。
