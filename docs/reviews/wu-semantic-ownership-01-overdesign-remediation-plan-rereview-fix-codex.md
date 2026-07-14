# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Re-Review Fix — AgentCodex

## Gate 身份与范围

- **日期**：2026-07-14。
- **角色**：AgentCodex，既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` remediation 总计划的 re-review fix owner；不是新 WU、R01 plan、implementation 或第二轮 re-review。
- **唯一 finding disposition 真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-controller-adjudication.md`。
- **唯一 accepted finding**：`DS-RR-F01`。本轮没有重新裁决 reviewer 建议，也没有实施 `DS-RR-F02`、`DS-RR-F03`、`MIMO-RR-F01`、`MIMO-RR-F02` 或 `MIMO-RR-F03`。
- **允许修改闭集**：
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
  - 本 artifact
- **禁止动作**：未修改 control/design/产品代码/测试/README/其它 review；未 commit、push、创建 PR、进入 R01 或执行第二轮 re-review。

## 完整输入与第一性原理判断

本轮完整阅读并交叉核对：`AGENTS.md`、`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`、controller discussion、五份 design truth（Host、Engine、Tool、Fins、UI）、当前 remediation plan、初轮 MiMo/DS review、初轮 controller adjudication、初轮 plan-fix artifact、两份 plan re-review，以及本轮唯一 controller adjudication。

`DS-RR-F01` 的动机成立，严重度“中”合理。根因不是现有验证基线太强，而是 umbrella 当前证据基线与 later accepted sub-WU plan 都写了 slice/command/scan，却没有声明 accepted-plan commit 前后的时序优先级。若不修复，实施者既可能机械复制已漂移的 test node，也可能用“独立 plan”绕开安全、覆盖率或 owner contract。正确修复是给两层 artifact 一个时间上互斥、职责上互补的 owner 规则；删除命令或把 baseline 降为参考都会偏离裁决。

## DS-RR-F01 四点 closure

| 裁决要求 | Plan 文本位置 | 修复内容 | Closure |
| --- | --- | --- | --- |
| 1. Umbrella per-slice 命令/文件集合是 mandatory starting baseline，不是直接实施授权 | §0 第 8—10 行；§7.3 第 203—204 行；§7.5 第 253—255 行 | 明确 umbrella 在 accepted-plan commit 前拥有当前证据基线；sub-WU 必须消费，且不能跳过独立 plan/review/commit | 已关闭 |
| 2. Sub-WU 重新核对真实文件、test node、slice 原子性与 scan；accepted-plan commit 后成为 exact execution truth | §7.3 第 205 行 | 把“双 review、controller adjudication、fix、双 re-review、accepted-plan local commit”设为 exact truth 生效条件；只由该 committed plan 支配本 sub-WU exact 执行项 | 已关闭 |
| 3. 差异逐项附直接证据，不得弱化既有验证和 contract | §7.3 第 206 行 | 要求 baseline→exact 项逐项登记 `保留 | 基于直接代码证据细化 | 以等价验证替换`；禁止静默遗漏，显式保留 accepted contract、安全、逐文件覆盖率、pyright、README、真实 smoke 与 propagation scan 下限 | 已关闭 |
| 4. Owner、依赖、production allowlist 或 accepted contract 实质变化必须回 controller | §7.3 第 207 行 | 设置 stop/escalation boundary，禁止 sub-WU plan 以调整 slice/命令为名静默扩域、换 owner 或改写裁决 | 已关闭 |

另外，§26 第 1267—1269 行已更新为本 re-review-fix gate 的准确 stop：artifact-only 检查后停止；第二轮双路 re-review 只能由 umbrella controller 另行派发，本轮不进入。

## 为何这是唯一 owner，而不是双真源

规范性 owner 只定义在 plan §7.3 第 203—207 行；§0 只给 gate 摘要，§7.5 只把现有 matrix 引回 §7.3，不另建优先级规则。

| 时间点/语义 | 唯一 owner | 不拥有的语义 |
| --- | --- | --- |
| Sub-WU accepted-plan commit 前 | Umbrella plan：sub-WU 边界、顺序、全局 invariant、最低验证意图、当前代码证据 baseline | 不授权直接 implementation，不拥有最终 exact test node/命令 |
| Sub-WU accepted-plan commit 后 | 该 commit 中的 accepted sub-WU plan：该 sub-WU exact slice、文件、命令、test node、scan | 不得重写 umbrella 边界、顺序、全局 invariant、最低验证意图或 accepted contract |
| 发现实质 owner/依赖/allowlist/contract 变化 | Umbrella controller | Sub-WU plan 不得自行裁决或静默扩域 |

因此，同一时点只有一个 exact execution truth；umbrella 的长期 owner 只保留跨 sub-WU 治理和验证下限。差异映射把“可随代码证据更新的 exact 细节”与“不可弱化的 contract/验证意图”分开，避免显示正确但执行 truth 漂移。

## 现有验证基线未删除或弱化

- §7.4 production/config/package closed manifest 全表保留。
- §7.5 全部 30 个 slice 的 coverage/source/README matrix 保留，仅增加时序解释。
- §8—§19 的每个 slice、targeted pytest、scan、README 与 smoke 文本均保留。
- §7.1 的逐文件覆盖率 `>=80%`、全量 pyright、`git diff --check`、allowed-file scan 与 README decision 保留。
- §21 retained/modified security matrix、§22 aggregate regression/deepreview/PR/final closeout gates 均保留。

## 反向 scope scan

### Disposition 边界

- `DS-RR-F02`：未补“旧 storage 数据需 fresh workspace/重新 ingestion”说明；§14.2/§14.5 未修改。
- `DS-RR-F03`：未增加 deployment-value/internal-constant 例子或白名单；§11.3 未修改。
- `MIMO-RR-F01`：未增加 R03 inventory 表格模板；§10.4 未修改。
- `MIMO-RR-F02`：未设计 Windows runner fallback/替代路径；§18.1、§18.3、§22.1 未修改。
- `MIMO-RR-F03`：未预拆 R06、未改其三 slices 或 producer allowlist；§13 与 §7.4 R06 行未修改。

### 文件与动作边界

- Preflight 时 remediation plan 已是 untracked 既有输入，pre-edit SHA-256 为 `b12843e7b31cbc6a3ea79c66ab5d37f52208edf5445fd155726fb46a7de56aad`；其余 dirty design/control/review 输入均保留。
- 本轮写入只落在允许的 remediation plan 与本 artifact；没有修改 control/design/产品代码/测试/README/其它 review。
- 没有创建 commit、push、PR，也没有进入第二轮 re-review。

## 验证

- 完整材料阅读：通过。
- 两个目标 artifact 人工 diff/全文落点复核：通过。
- 反向 rejected/note scope scan：通过。
- `git diff --check`：通过，无输出。
- 对两个 untracked 目标分别执行 `git diff --no-index --check /dev/null <target>`：无 whitespace diagnostic；返回码 1 仅表示目标相对 `/dev/null` 有内容。
- `git status --short` 对照 preflight：仅新增本允许 artifact；remediation plan 仍是本轮唯一修订的既有 untracked 目标，其余 dirty 输入状态未被本轮改变。
- 测试/pyright：未运行。本轮只修改 plan/review artifact，没有产品代码或测试变更；用户限定的验证是 artifact scope scan 与 diff check。

## Remaining questions

无。`DS-RR-F01` 四点均有唯一落点；五个 rejected/note finding 保持未实施。

## Stop status

`remediation plan re-review fix complete`。本 artifact 完成并验证后停止；不进入第二轮 re-review、R01 plan 或 implementation。
