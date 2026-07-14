# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Re-Review Controller Adjudication

## Gate 身份

- 本文是既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 remediation 总计划双路 re-review 裁决，不是新 WU、sub-WU、implementation 或 code review。
- 产品裁决真源是 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`；初轮 disposition 真源是 `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`。
- 本轮证据是：
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-fix-codex.md`
  - 修订后的 `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
- Reviewer verdict 不独立授权进入 R01 或 implementation；finding disposition 只由本文决定。

## 旧 findings closure 裁决

两路 re-review 都逐项确认：CTL-PF-01—05、DS-PF-01—12、MIMO-PF-01—15 已按初轮 controller adjudication 真实关闭或正确保持未实施。Controller 复核同意以下结论：

- 所有 accepted / accepted-in-part finding 均有可定位的计划文本；
- DS-PF-07 与 MIMO-PF-04 两个 rejected finding 未被误实现；
- notes 未被升级成额外产品 contract；
- Topic 8/9 仍为 no-code；Issue 142/151/175/177/178 与现有 Web/WeChat/render tracker 仍未越界；
- Windows `cmd.exe` 真实执行仍是 release blocker，未降级为 residual；
- R07 未重新固定 hash、revision grammar、retry 次数、新异常名或 cache lease 类型。

因此，初轮全部 accepted findings 的 closure 状态保持“已修复”。本轮是否接受总计划只取决于下面的新 findings。

## AgentDS 新 findings

### DS-RR-F01 — accepted — 中

**Finding**：umbrella 计划给出了当前证据下的 slice、测试和 scan 命令，同时又规定每个 R01—R12 必须产出独立 code-generation-ready plan；两层 artifact 之间缺少发生差异时的唯一执行真源与变更规则。

**裁决理由**：动机成立。Umbrella owner 应拥有 sub-WU 边界、顺序、全局 invariant、最低验证意图和当前证据基线；每个 sub-WU 的 accepted plan 才应在其 accepted-plan commit 后成为该 sub-WU 的 exact slice/command/scan 执行真源。若不写清时序 owner，implementation agent 可能机械复制已经失效的 `-k`/文件名，也可能以“独立计划”为由弱化安全、覆盖率或 owner contract。

**必须修复**：在总计划 §0、§7.3/§7.5 或等价唯一位置写清：

1. umbrella 中的 per-slice 命令与文件集合是基于当前代码证据的 mandatory starting baseline，不是跳过 sub-WU plan 的直接实施授权；
2. 每个 sub-WU 必须重新核对真实文件、test node、slice 原子性与 scan；其经双 review/controller 接受并提交后的 plan 是该 sub-WU exact execution truth；
3. 差异必须逐项记录直接代码证据，且不得弱化 controller accepted contract、retained security、每文件覆盖率、pyright、README、真实 smoke 或 propagation scan；
4. owner、依赖、production allowlist 或 accepted contract 发生实质变化时必须回 controller，不得由 sub-WU plan 静默扩域。

该修复只澄清 plan artifact 的时序语义 owner，不删除现有验证基线、不新增产品设计。

### DS-RR-F02 — rejected-with-reason — 低

**Finding**：R07 没有进一步声明旧 storage layout 数据在 fresh schema 后不可读。

**裁决理由**：总计划 §14.2 已明确“fresh schema 直接使用新布局，不兼容旧布局、不迁移旧库”，§14.5 又要求 README 发布 fresh schema；这已经直接表达旧布局不是新 contract 的输入。把开发者如何重建本地数据再写成 umbrella 产品 contract 不增加正确性。R07 子计划/README 可按既有要求给出用户可读说明，但本轮无需修改总计划。

### DS-RR-F03 — rejected-with-reason — 低

**Finding**：R04 对 deployment-value 常量与内部算法常量的区分标准不够具体。

**裁决理由**：总计划已经以语义和调用用途区分：为 `WaitPollerRuntimePolicy` 字段提供 default/override/fallback 的值属于部署值，必须删除；独立算法 owner 的常量可保留，并须逐条记录 owner，禁止按数值盲删。具体常量只能由 R04 子计划基于调用链裁决，umbrella 若再列举 thread join/backoff 等例子反而可能把当前猜测固化成例外白名单。

## AgentMiMo 新 findings

### MIMO-RR-F01 — rejected-with-reason — 低

**Finding**：R03 source inventory 缺少表格模板。

**裁决理由**：§10.4 已逐列规定“文件、具体 source、是否 LLM-facing、语义 owner、disposition、验证证据”，同时禁止目录级声明；语义 contract 已完整。Markdown 表格形态属于 R03 plan artifact 的表达选择，不需要由 umbrella 再拥有第二份模板。

### MIMO-RR-F02 — rejected-with-reason — 低

**Finding**：Windows runner 不可用时的 stop 行为可更显式。

**裁决理由**：§7.3 stop condition、§18.1 runner owner 要求、§18.3 和 §22.1 已共同规定：缺 runner、workflow 未触发/skip、artifact 不可读或真实字符矩阵失败均阻塞 aggregate/PR/final closeout，不得降级为 residual；若需新增最小 workflow，必须进入 R11 子计划 allowlist 和双 review。产品裁决明确不允许 fallback，因此无需再设计替代路径。

### MIMO-RR-F03 — note / no fix

**Finding**：R06 producer migration 范围大，可能阻塞后续依赖。

**裁决理由**：Reviewer 已明确这不是 plan-level defect。R06 以唯一 transaction/complete-publication commit point 为 owner 边界，拆开会产生 half-published 中间 schema；其三个 slices 未超过 umbrella 约束。若直接代码证据表明当前 slice 容量不可执行，应在 R06 独立 plan gate 回 controller，而不是现在预拆或删除 producer。

## Gate 决定

- 双路 re-review 不是无条件 pass：共有一个 controller-accepted 中严重度 plan finding（DS-RR-F01）。
- 总计划尚未 accepted；不得 commit accepted plan、进入 R01 子计划或实施产品代码。
- 下一 gate 是 remediation plan re-review fix。AgentCodex 只修改总计划并新增 `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-fix-codex.md`，关闭 DS-RR-F01，且不得顺手实现五个 rejected/note 项。
- Fix 完成后，AgentMiMo / AgentDS 必须对完整最终计划执行第二轮双路 re-review；不能只检查新增句子。

## 当前 finding 状态

| Finding | Final disposition | 当前状态 |
| --- | --- | --- |
| 初轮 CTL/DS/MiMo accepted findings | accepted | 已修复，closure 保持 |
| DS-RR-F01 | accepted | 待 AgentCodex 修复与双路完整 re-review |
| DS-RR-F02 | rejected-with-reason | 关闭，不修改 |
| DS-RR-F03 | rejected-with-reason | 关闭，不修改 |
| MIMO-RR-F01 | rejected-with-reason | 关闭，不修改 |
| MIMO-RR-F02 | rejected-with-reason | 关闭，不修改 |
| MIMO-RR-F03 | note / no fix | 关闭，不修改 |

Blocking user question：无。
