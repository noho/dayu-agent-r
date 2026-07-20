# WU-SEMANTIC-OWNERSHIP-01 R04 plan review Controller adjudication

## 1. Gate identity

- active work unit：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：R04 Awaiting provider resolution config 与 Host composition。
- reviewed plan：`docs/host/wu-semantic-ownership-01-r04-awaiting-provider-resolution-composition-plan.md`。
- review artifacts：
  - `docs/reviews/wu-semantic-ownership-01-r04-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-r04-plan-review-ds.md`
- 本裁决只授权 AgentCodex 修计划；不接受计划、不授权 implementation。

## 2. Review summary

- AgentMiMo：`pass-with-risks`；1 个 blocking accepted candidate、2 个 non-blocking accepted candidates、9 个 no-fix observations。
- AgentDS：`pass-with-risks`；3 个 accepted candidates、2 个 observations、1 个 no-fix。
- 两路共同确认：动机成立；provider/config/Service/Host owner 与设计真源一致；`dayu/host/wait_adapter.py` 是必要且窄化的 owner allowlist refinement；`dayu/host/api.py` 与 `dayu/host/open_host.py` 当前可保持 no-diff；callback 无 transport 时 fail-closed；security/deferred/no-code 边界未漂移。

## 3. Accepted plan findings

### R04-PLAN-F01 — 区分 resolution policy 映射与结构性 tool-name 映射

接受 MiMo Finding 02 与 Finding 07 的共同根因。

计划必须明确：

1. S1 由 typed `AwaitingResolutionMode` 替换 `_binding_for_tool_name` 当前硬编码的 `WaitResumePolicy.POLL`；该修改属于 provider-mode contract 闭环；
2. `_operation_kind_from_tool_name` 是 Fins observation handle 恢复所需的结构性 `tool name -> operation kind` 映射，必须保留；
3. “删除 tool-name 推断”仅指删除从 tool name 发明 resolution policy，不得扩大成删除所有稳定结构映射。

### R04-PLAN-F02 — 修正 S2/S3 共享节点，禁止中间 broken state 或临时兼容 seam

接受 MiMo Finding 04 与 DS F-03。

直接证据是 `ServiceAssemblyOverrides.wait_poller_policy` 字段和 `_compose_options` 的消费者都在 `dayu/service/host_assembly.py`。原计划在 S2 删除字段、到 S3 才重建 composition，会使 S2 无法独立通过 pyright。

AgentCodex 必须重新切分，使删除旧 override source 与替代 typed composition path 在同一原子 slice 完成。允许把删除动作整体移到 composition slice，或基于依赖/验证边界合并 S2/S3；不得引入临时 wrapper、compatibility field、hard-coded `None` 桥、第二 policy owner 或只为跨 slice 过渡的 seam。每个保留 slice 结束时都必须是可运行、可测试、pyright clean 的产品状态。

### R04-PLAN-F03 — 固定 non-awaiting/disabled provider 配置校验 owner

接受 DS F-01 与 F-02 的 owner 澄清要求，但不接受其“提升为 ConfigLoader generic optional field”备选方案。

权威 contract 已固定 `awaiting_resolution_mode` 位于对应 provider 的 opaque config，并由 Fins provider 公共 parser 一次解析；`dayu.runtime` 不得理解 Fins 业务语义。

计划必须明确：

1. Service composition 使用现有 provider identity 判定当前三个 Fins awaiting provider，并在 active filtering 之前调用 Fins-owned parser，因此 disabled Fins provider 的缺失/非法 mode 同样 fail fast；
2. recognized non-awaiting provider 携带该字段时，由 Service provider-assembly boundary 仅检查字段存在并报告 owner misuse；Service 不解析其 raw mode 值、不建立第二 enum/parser；
3. 只有 mode 校验通过且 provider enabled、awaiting tool 可绑定时，typed metadata 才进入 active registry/composition；
4. 增加 disabled+illegal、disabled+legal、recognized non-awaiting misconfig 的明确 tests；不得把规则降级为 best-effort。

这仍在当前 `dayu/service/host_assembly.py` allowlist 内，不扩展 ConfigLoader 的 generic provider schema，也不设计未来 non-Fins awaiting framework。

### R04-PLAN-F04 — 明确旧 override/scene 测试的 owner-level 迁移

接受 DS F-05 的 code-generation-ready 精度要求。

计划必须列出至少以下迁移类别：

- 直接传 `ServiceAssemblyOverrides.wait_poller_policy` 的测试删除旧输入路径，改为断言 `host_runtime.json -> ConfigLoader typed snapshot -> Service composition -> OpenHostOptions`；
- `with_entrypoint_wait_poller_policy` / scene-selected auto-enable 测试改为 scene all/select/none 不改变 opener policy 的 negative/propagation tests；
- Host `None/disabled/enabled+missing registry` fail-closed tests保留并改为显式完整 policy 构造；
- provider mode tests覆盖三模式、缺失/错类型/未知、disabled 与 non-awaiting misuse；
- 所有 §6.3 matrix 行必须有 owner-level断言，不能机械删除旧测试获得绿灯。

## 4. Rejected / no-fix / observation dispositions

| 来源 | finding / question | 裁决 |
|---|---|---|
| MiMo 01 | `poll_interval_seconds=1.0` 字面 default 未被常量名 scan 命中 | no-fix；S2 删除所有 dataclass field defaults，构造器 scan 覆盖无参路径。 |
| MiMo 03 | Host API/open_host stop condition 可更具体 | no-fix；现有 plan 已明确 no-diff 与 owner-change stop，review 也直接证明现有三个分支正确。 |
| MiMo 05 | callback+poll 且无 transport 是否整体失败 | no-fix；plan 已明确“任意 callback（含混合）”整体 composition error，符合 fail-closed 裁决。 |
| MiMo 06 | callback positive destination 时间线 | no-fix residual；WU-WAIT-01 / Issue 89 有直接仓库证据，R04 不实施 transport。 |
| MiMo 08 | scan 的实施前/后措辞 | no-fix；§9 明确属于最终验证。 |
| MiMo 09 | `325 passed` 可复现性 | no-fix；它是时间点基线，计划已要求实施后重跑。 |
| MiMo 10 | fresh schema 原子更新 | no-fix；S2 已要求 JSON 与 ConfigLoader 同 slice，且 AGENTS.md 禁止旧 schema 兼容。 |
| MiMo 11 | 单一 `--cov=dayu` 边界 | no-fix；已直接验证的等价替换，并逐文件读取 coverage JSON。 |
| MiMo 12 | provider identity helper 不读取 mode | no-fix；identity 与 mode owner 分离正确。 |
| DS F-04 | 为十个部署常量 scan 增加“内部算法常量”例外 | rejected；scan 只列当前十个已由代码证明属于部署 policy 的常量，umbrella §11.3 明确要求删除。新的不同 owner 证据应 stop 回 Controller，不能预写宽松例外。 |
| DS F-06 | scene `None=all` | no-fix；原计划已删除整个 scene-derived helper。 |
| DS Q2 | 12 个 packaged 值的产品依据 | answered/no-fix；Controller discussion 与 umbrella §11.2 已完成产品裁决，值与当前安全预算一致，不重新讨论。 |
| DS Q3 | Host structural Protocol 是否要更新 | answered/no-fix；required-field 改造只删除 concrete dataclass defaults，Protocol 的 12 个字段形状不变；review 直接确认 no-diff。 |
| DS callback error type | 未指定具体 exception 类型 | no-fix；沿现有 Service composition 异常惯例即可，不新增 public contract。 |

## 5. Verdict and next gate

`PLAN_FIX_REQUIRED / 4 ACCEPTED FINDINGS / NO USER DECISION REQUIRED`

AgentCodex 下一步只修改 R04 plan 并写 plan-fix artifact，逐项关闭 `R04-PLAN-F01..F04`；不得修改代码、测试、README、design、control 或 reviewer artifacts。完成后必须进行 Controller validation 与双路完整 plan re-review。Implementation 仍未授权。
