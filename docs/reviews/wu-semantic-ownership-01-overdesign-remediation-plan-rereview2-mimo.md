# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan 第二轮 Re-Review（第一路） — AgentMiMo

## Gate 身份与范围

- **日期**：2026-07-14。
- **角色**：AgentMiMo，既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` remediation 总计划第二轮双路 re-review 第一路；不是新 WU、不是 R01 plan、不是 implementation、不是 code review。
- **审查对象**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（re-review-fix 后最终全文，1270 行）。
- **唯一 disposition 真源**：
  - 初轮裁决：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`
  - 本轮裁决：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-controller-adjudication.md`
- **产品裁决真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- **设计真源**：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`
- **流程真源**：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- **Re-review-fix 证据**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-fix-codex.md`
- **初轮 re-review（不上位替代本轮）**：
  - AgentMiMo `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-mimo.md`
  - AgentDS `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-ds.md`
- **完整阅读材料**：AGENTS.md、phaseflow control、controller discussion、五份 design truth（Host、Engine、Tool、Fins、UI）、最终 plan、初轮 review（MiMo/DS）、初轮 controller adjudication、初轮 plan-fix、初轮 rereview（MiMo/DS）、初轮 rereview controller adjudication、re-review-fix Codex artifact。
- **输出边界**：仅新增本 artifact；不修改 plan/control/design/代码/测试/README；不 commit/push/PR。

## 审查方法

本审查是"第二轮第一路完整 plan re-review"，**必须 re-review 最终全文而非只看新增规则**。审查范围：

1. 验证 DS-RR-F01 四点均关闭——逐项提供文本证据。
2. 验证 umbrella mandatory baseline 未弱化——逐节确认 §7.4、§7.5、§8—§19、§7.1、§21、§22 完整保留。
3. 验证 accepted sub-WU plan 的 exact truth 只在 accepted-plan commit 后生效——确认 §7.3 line 205 的时序语义。
4. 验证实质 owner/dependency/production allowlist/contract 变化会回 controller——确认 §7.3 line 207 的 stop/escalation boundary。
5. 确认 DS-RR-F02/F03、MIMO-RR-F01/F02/F03 未实施——全文扫描。
6. 确认初轮全部 closure 仍成立——逐项核对 CTL-PF-01—05、DS-PF-01—12、MIMO-PF-01—15。
7. 确认 Topic 8/9 与 Issue 142/151/175/177/178 边界未漂移。
8. 对完整最终计划执行 adversarial review——寻找新 findings。

---

## 一、DS-RR-F01 四点 Closure 验证

### 裁决要求与 Plan 文本证据

| 裁决要求 | Plan 文本位置 | 修复内容 | Closure |
| --- | --- | --- | --- |
| 1. Umbrella per-slice 命令/文件集合是 mandatory starting baseline，不是直接实施授权 | §7.3 line 203-204 | 明确 umbrella 在 accepted-plan commit 前拥有当前代码基线；sub-WU 必须消费，且不能跳过独立 plan/review/commit | **已关闭** |
| 2. Sub-WU 重新核对真实文件、test node、slice 原子性与 scan；accepted-plan commit 后成为 exact execution truth | §7.3 line 205 | 把"双 review、controller adjudication、fix、双 re-review、accepted-plan local commit"设为 exact truth 生效条件；只由该 committed plan 支配本 sub-WU exact 执行项 | **已关闭** |
| 3. 差异逐项附直接证据，不得弱化既有验证和 contract | §7.3 line 206 | 要求 baseline→exact 项逐项登记 `保留 \| 基于直接代码证据细化 \| 以等价验证替换`；禁止静默遗漏，显式保留 accepted contract、安全、逐文件覆盖率、pyright、README、真实 smoke 与 propagation scan 下限 | **已关闭** |
| 4. Owner、依赖、production allowlist 或 accepted contract 实质变化必须回 controller | §7.3 line 207 | 设置 stop/escalation boundary，禁止 sub-WU plan 以调整 slice/命令为名静默扩域、换 owner 或改写裁决 | **已关闭** |

### 逐点文本验证

**Point 1**（§7.3 line 203-204）：

> 在某个 sub-WU 的 accepted-plan local commit 产生前，本文拥有该 sub-WU 的边界、顺序、全局不变量、最低验证意图，以及第 7.4 节 production allowlist、第 7.5 节和各 Rxx 正文给出的 per-slice 文件集合、测试命令/test node、coverage 与 scan 的 mandatory starting baseline。这些基线是后续独立 plan 必须消费的最低输入，不是跳过 sub-WU plan、review 和 accepted-plan commit 的直接实施授权。

**验证**：明确区分"umbrella 拥有 baseline"与"baseline 不是直接实施授权"。sub-WU 必须走完整 plan gate 才能进入 implementation。✅

**Point 2**（§7.3 line 205）：

> 每个 sub-WU plan 必须在其实际 base 上重新核对真实文件、test node、slice 原子性和 propagation/source/security scan。只有该 plan 完成双路 review、controller adjudication、accepted finding fix、双路完整 re-review并由 controller 创建 accepted-plan local commit 后，该 commit 中的 plan 才成为该 sub-WU 对 exact slice、文件、命令、test node 与 scan 的唯一 execution truth；本文继续独占 sub-WU 边界、顺序、全局不变量和最低验证意图，不与 accepted sub-WU plan 形成第二份 exact 执行真源。

**验证**：时序语义精确——accepted-plan commit 是唯一切换点。切换前 umbrella 拥有 baseline；切换后 sub-WU plan 拥有 exact execution truth；umbrella 继续独占边界/顺序/invariant/验证意图。不存在双真源。✅

**Point 3**（§7.3 line 206）：

> sub-WU plan 必须逐项记录 umbrella baseline 到 accepted-plan exact 项的 `保留 | 基于直接代码证据细化 | 以等价验证替换` 映射；任何差异都必须附真实调用链、文件或 test collection 证据，baseline 项不得静默遗漏。细化或等价替换不得弱化 controller accepted contract、retained security、changed production file 逐文件覆盖率 `>=80%`、全量 pyright、README decision、真实/跨平台 smoke 或 LLM/source/security propagation scan。

**验证**：差异映射机制完整——三类 disposition（保留/细化/等价替换）、证据要求（调用链/文件/test collection）、禁止静默遗漏、禁止弱化验证下限。✅

**Point 4**（§7.3 line 207）：

> 若重新核对发现语义 owner、依赖、production allowlist 或 controller accepted contract 发生实质变化，sub-WU plan 必须停止并回到 controller 裁决；不得以调整 exact slice/命令为名静默扩域、改变 owner 或重写 accepted contract。

**验证**：escalation boundary 清晰——四种触发条件（owner/依赖/allowlist/contract 实质变化）、唯一动作（stop 回 controller）、禁止行为（静默扩域/换 owner/改裁决）。✅

### DS-RR-F01 Closure 结论

四点均有唯一规范位置（§7.3 line 203-207），修复内容与裁决要求精确对应，无遗漏、无弱化、无歧义。§0 line 7 引用 §7.3 作为时序规则的唯一位置，§7.5 line 255 声明"本节不另设执行真源；全部字段按第 7.3 节的唯一时序规则解释"——规范位置唯一，不存在双真源。

---

## 二、Umbrella Mandatory Baseline 未弱化验证

逐节确认所有 mandatory baseline 内容保留完整：

| 节 | 内容 | 状态 |
| --- | --- | --- |
| §7.1 Slice transaction（line 149-173） | 逐文件覆盖率 `>=80%`、全量 pyright、`git diff --check`、allowed-file scan、LLM/source/security propagation scan、README decision | **保留** |
| §7.2 Baseline failure registry（line 175-180） | 六项匹配规则、inherited 标准、新增/扩散 stop | **保留** |
| §7.3 Per-sub-WU gate（line 183-232） | 完整状态机、artifact naming、entry/exit criteria、stop condition、handoff format | **保留并增强**（新增 DS-RR-F01 四点时序规则） |
| §7.4 Closed affected-module manifest（line 234-251） | 12 个 sub-WU 的 production/config/package 文件闭集 | **保留**，无修改 |
| §7.5 Per-slice verification matrix（line 253-288） | 30 个 slice 的 coverage `--include`、mandatory scan、README decision | **保留**，仅增加时序解释声明（line 255） |
| §8—§19 每个 Rxx 正文 | 每个 sub-WU 的 owner、依赖、允许范围、contract、implementation slices、exact 测试命令、smoke、README、stop | **保留**，无修改 |
| §21 安全相关 retained/modified 行为清单（line 1096-1118） | 17 项安全行为的 disposition 与验收 | **保留** |
| §22 Aggregate 验证（line 1121-1206） | aggregate regression 命令、aggregate scans（6 条 rg）、smoke 矩阵（11 行）、deepreview、PR gates、final closeout matrix | **保留** |

**结论**：umbrella mandatory baseline 完整保留，未被弱化。DS-RR-F01 修复只增加了 §7.3 的时序语义规则和 §7.5 的解释声明，没有删除或降低任何验证要求。✅

---

## 三、Accepted Sub-WU Plan Exact Truth 时序验证

§7.3 line 205 的时序规则：

| 时间点 | Exact execution truth owner | 不拥有的语义 |
| --- | --- | --- |
| Sub-WU accepted-plan commit 前 | Umbrella plan：sub-WU 边界、顺序、全局不变量、最低验证意图、当前代码证据 baseline | 不授权直接 implementation，不拥有最终 exact test node/命令 |
| Sub-WU accepted-plan commit 后 | 该 commit 中的 accepted sub-WU plan：该 sub-WU exact slice、文件、命令、test node、scan | 不得重写 umbrella 边界、顺序、全局不变量、最低验证意图或 accepted contract |

**验证**：
- 同一时点只有一个 exact execution truth——不存在双真源。
- Umbrella 的长期 owner 只保留跨 sub-WU 治理和验证下限。
- §0 line 7 确认："本文拥有 R01—R12 的切分、顺序、全局不变量、最低验证意图和基于当前代码证据的 mandatory starting baseline，不能替代任一 sub-WU 自己的 code-generation-ready plan"。
- §7.5 line 255 确认："本节不另设执行真源；全部字段按第 7.3 节的唯一时序规则解释"。

**结论**：accepted sub-WU plan 的 exact truth 只在 accepted-plan commit 后生效，语义精确、无歧义。✅

---

## 四、实质变化回 Controller 验证

§7.3 line 207 的 stop/escalation boundary：

> 若重新核对发现语义 owner、依赖、production allowlist 或 controller accepted contract 发生实质变化，sub-WU plan 必须停止并回到 controller 裁决；不得以调整 exact slice/命令为名静默扩域、改变 owner 或重写 accepted contract。

**验证**：
- 四种触发条件完整：语义 owner、依赖、production allowlist、controller accepted contract。
- 唯一动作：stop 回 controller。
- 禁止行为：静默扩域、改变 owner、重写 accepted contract。
- 与 §7.3 line 226 的 stop condition 一致："owner 不清、设计与 controller 冲突、需要越界 issue、出现无法同源的中间 schema、retained security 失败、新/扩散 baseline、allowed files 外 diff、accepted finding 未闭合或 Windows release blocker 未被追踪时立即停止"。

**结论**：实质 owner/dependency/production allowlist/contract 变化必须回 controller，不得由 sub-WU plan 静默扩域。✅

---

## 五、DS-RR-F02/F03、MIMO-RR-F01/F02/F03 未实施验证

### 全文扫描

| Finding | Controller Disposition | Plan 修改证据 | 状态 |
| --- | --- | --- | --- |
| DS-RR-F02（R07 fresh-schema 数据影响） | rejected-with-reason | §14.2/§14.5 未修改 | **未实施** ✅ |
| DS-RR-F03（R04 deployment-value 区分标准） | rejected-with-reason | §11.3 未修改 | **未实施** ✅ |
| MIMO-RR-F01（R03 inventory 表格模板） | rejected-with-reason | §10.4 未修改 | **未实施** ✅ |
| MIMO-RR-F02（Windows runner stop 行为） | rejected-with-reason | §18.1/§18.3/§22.1 未修改 | **未实施** ✅ |
| MIMO-RR-F03（R06 producer migration 范围） | note / no fix | §13 与 §7.4 R06 行未修改 | **未实施** ✅ |

### Re-review-fix Codex Artifact 反向 Scope Scan

Codex fix artifact 第 55-59 行明确记录：

> - `DS-RR-F02`：未补"旧 storage 数据需 fresh workspace/重新 ingestion"说明；§14.2/§14.5 未修改。
> - `DS-RR-F03`：未增加 deployment-value/internal-constant 例子或白名单；§11.3 未修改。
> - `MIMO-RR-F01`：未增加 R03 inventory 表格模板；§10.4 未修改。
> - `MIMO-RR-F02`：未设计 Windows runner fallback/替代路径；§18.1、§18.3、§22.1 未修改。
> - `MIMO-RR-F03`：未预拆 R06、未改其三 slices 或 producer allowlist；§13 与 §7.4 R06 行未修改。

**结论**：五个 rejected/note finding 均未被误实现，与 controller adjudication 一致。✅

---

## 六、初轮全部 Closure 仍成立验证

### Controller Findings（CTL-PF-01 至 CTL-PF-05）

| Finding | Disposition | 初轮 rereview 确认 | 本轮复核 |
| --- | --- | --- | --- |
| CTL-PF-01（per-sub-WU gate state machine） | accepted/blocking | §7.3 line 186-227 | **仍成立** ✅ |
| CTL-PF-02（所有 severity accepted finding 修复） | accepted/blocking | §7.3 line 203、§22.2 line 1168 | **仍成立** ✅ |
| CTL-PF-03（controller local commit 与 PR 授权） | accepted/blocking | §7.3 line 225、§22.3 line 1172-1182 | **仍成立** ✅ |
| CTL-PF-04（当前分支串行） | accepted | §6 line 145 | **仍成立** ✅ |
| CTL-PF-05（R07 无 speculative contract） | accepted | §14.2-14.3 line 718-727 | **仍成立** ✅ |

### AgentDS Findings（DS-PF-01 至 DS-PF-12）

| Finding | Disposition | 初轮 rereview 确认 | 本轮复核 |
| --- | --- | --- | --- |
| DS-PF-01（Windows batch renderer） | accepted | §18.1-18.4、§21、§22.1 | **仍成立** ✅ |
| DS-PF-02（R07 收窄） | accepted in part | §14.2-14.3 | **仍成立** ✅ |
| DS-PF-03（平台 quoting 安全矩阵） | accepted in part | §21 line 1110、§23 line 1211 | **仍成立** ✅ |
| DS-PF-04（人工 source inventory） | accepted | §10.4-10.5 | **仍成立** ✅ |
| DS-PF-05（Windows runner release blocker） | accepted | §18.1、§22.1 | **仍成立** ✅ |
| DS-PF-06（R08 raw total/public count） | accepted | §15.2-15.4 | **仍成立** ✅ |
| DS-PF-07（R05+R09 不跨层组合） | rejected-with-reason | 未实现 | **仍成立** ✅ |
| DS-PF-08（串行 accepted commits） | accepted with stronger correction | §6 line 145-146 | **仍成立** ✅ |
| DS-PF-09（OLD 分类规则） | accepted | §18.2 line 913 | **仍成立** ✅ |
| DS-PF-10（models.json 核对） | note | 未升级 | **仍成立** ✅ |
| DS-PF-11（assets/reset 语义） | accepted with correction | §19.3 line 1024-1026 | **仍成立** ✅ |
| DS-PF-12（正面检查结论） | note | 未修改 | **仍成立** ✅ |

### AgentMiMo Findings（MIMO-PF-01 至 MIMO-PF-15）

| Finding | Disposition | 初轮 rereview 确认 | 本轮复核 |
| --- | --- | --- | --- |
| MIMO-PF-01（assets 精确修正） | accepted | §19.3 line 1024-1026 | **仍成立** ✅ |
| MIMO-PF-02（cmd 元字符） | accepted | §18.2 line 917-918 | **仍成立** ✅ |
| MIMO-PF-03（host_runtime.json 唯一真源） | accepted | §11.2 line 526 | **仍成立** ✅ |
| MIMO-PF-04（credential fallback） | rejected-with-reason | 未实现 | **仍成立** ✅ |
| MIMO-PF-05（first/reset only prewarm） | accepted | §19.3 line 1030 | **仍成立** ✅ |
| MIMO-PF-06（两类 smoke 分离） | accepted | §18.3 line 945-947 | **仍成立** ✅ |
| MIMO-PF-07（deployment defaults 删除） | accepted/merged | §11.2 line 526 | **仍成立** ✅ |
| MIMO-PF-08 至 MIMO-PF-15 | notes | 未升级 | **仍成立** ✅ |

### 初轮 Closure 结论

全部 5 个 controller findings、12 个 DS findings、15 个 MiMo findings 的 closure 状态保持。2 个 rejected findings（DS-PF-07、MIMO-PF-04）未被误实现。全部 notes 未被升级为实现要求。✅

---

## 七、Topic 8/9 与 Issue 142/151/175/177/178 边界验证

### Topic 8（Engine 240 字符异常消息）

Plan §3 line 66："保留 `dayu/engine/agent.py` 的敏感值先脱敏、原始异常消息 240 字符上限、显式截断后缀和完整 traceback 日志；不改配置、不新增 durable full-detail ref。"

§4 追踪表（line 97）："Topic 8；DS F-DS-04 | no code：保留 Engine 240 字符异常消息策略 | aggregate guard | exact regression 不变；diff 中无相关修改"

**验证**：Topic 8 为 no-code，plan 未包含任何修改 Engine 异常消息的指令。✅

### Topic 9（统一 tool authorization）

Plan §3 line 67："不设计或实现统一 tool authorization framework、角色模型、policy DSL、capability token 或 sandbox。"

§4 追踪表（line 99）："Topic 9 | no code：不实现统一授权；保留现有局部权限与 I/O 防御 | 每个 sub-WU security guard | retained behavior matrix 全绿"

**验证**：Topic 9 为 no-code，plan 未包含任何统一授权框架设计。✅

### Issue 142（workspace migration）

Plan §3 line 69："不实施 Issue 142、151、175、177、178。"

§4 追踪表（line 96）："Issue 142 / 151 | deferred：workspace migration；future write/product assets | 各 issue owner | R12 不创建/搬入`dayu/assets`或产品assets，不迁移旧schema"

§19.3 line 1024："当前 package 没有 `dayu/assets`，本 WU 不得创建空 `assets`、从 OLD 搬入 assets"

**验证**：Issue 142 为 deferred，plan 未包含任何旧 schema 迁移指令。✅

### Issue 151（future write/product assets）

§19.3 line 1026："未来 Issue 151 真正交付 product-owned workspace assets 时，由 Issue 151 owner 把该 root 及其 ownership 证据加入同一 managed-root manifest。"

§19.5 line 1076："不创建/搬入 assets 或产品 assets，不迁移旧 schema"

**验证**：Issue 151 为 deferred，plan 未包含任何产品 assets 创建/搬入指令。✅

### Issue 175（Fins 长事务进程隔离）

§4 追踪表（line 85）："Issue 175 | deferred：Fins 长事务进程隔离 | Issue 175 owner | R05 不改变 long-operation executor ownership"

§12.4 line 635："任何把 timeout 结果 publication 接受、重复 terminal、或迁移 Issue 175 executor 的方案立即 stop。"

**验证**：Issue 175 为 deferred，plan 未包含任何进程隔离迁移指令。✅

### Issue 177（TruncationManager）

§4 追踪表（line 79）："Issue 177 | deferred：完整 `TruncationManager` 接通 | Issue 177 owner，不在本 WU | R01 source scan 证明未引入新 manager wiring"

§8.5 line 347："不得只交一条 grep 结果，也不得声称 Issue 177 已完成。"

**验证**：Issue 177 为 deferred，plan 未包含任何 TruncationManager 接通指令。✅

### Issue 178（storage-state lifecycle）

§4 追踪表（line 81）："Issue 178 | deferred：credential storage-state retention/refresh/concurrent publish/cleanup lifecycle | Issue 178 owner | R02 只保留路径输入，不实现生命周期"

§9.2 line 389："必须删除：diagnostic utility 的 TTL、host-derived owner filename、0700/0600 lifecycle authority、orphan/expired cleanup、publish/reconcile 状态机与对应 artifact fields/tests。"

**验证**：Issue 178 为 deferred，plan 删除现有 lifecycle 实现但不引入新 lifecycle。✅

### 边界漂移结论

Topic 8/9 均为 no-code，Issue 142/151/175/177/178 均为 deferred。Plan 未包含任何越界实现指令。边界未漂移。✅

---

## 八、Adversarial Findings

### 01-新-低-§26 stop condition 时序声明与 §7.3 的一致性

- **位置**：Plan §26 line 1269
- **问题类型**：最佳实践偏离
- **当前写法**：§26 写"本文与re-review-fix artifact写完后只执行…完成即停止，本 gate 不进入第二轮 re-review；下一动作只能由umbrella controller另行派发AgentMiMo/AgentDS对完整最终计划执行第二轮双路re-review"。这里"本 gate 不进入第二轮 re-review"的"本 gate"指的是 re-review-fix gate，而"下一动作…第二轮双路 re-review"是后续 gate。
- **反例/失败场景**：如果读者把"本 gate 不进入第二轮 re-review"理解为"本 plan 永远不需要第二轮 re-review"，会与 controller adjudication 要求的"Fix 完成后，AgentMiMo / AgentDS 必须对完整最终计划执行第二轮双路 re-review"矛盾。
- **为什么有问题**：§26 是 plan 的最终 stop section，其措辞应精确区分"当前 gate 停止"与"后续 gate 由 controller 派发"。
- **直接证据**：§26 line 1269 "本 gate 不进入第二轮 re-review；下一动作只能由umbrella controller另行派发AgentMiMo/AgentDS对完整最终计划执行第二轮双路re-review"。Re-review-fix Codex artifact line 29："§26 第 1267—1269 行已更新为本 re-review-fix gate 的准确 stop"。
- **影响**：低。措辞可优化但不阻塞——当前文本的"本 gate"修饰符在上下文中可推断为 re-review-fix gate，且"下一动作"明确指向第二轮 re-review。
- **建议改法和验证点**：将"本 gate 不进入第二轮 re-review"改为"本 re-review-fix gate 完成后停止；下一 gate 由 umbrella controller 派发第二轮双路 re-review"。
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

### 02-新-低-R11 Windows workflow 文件归属确认

- **位置**：Plan §18.1 line 908、§7.4 line 250
- **问题类型**：契约缺失
- **当前写法**：§18.1 写"子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist并经双 plan review/controller接受，umbrella计划不预设 workflow 文件名"。§7.4 R11 allowed files 列出 `pyproject.toml`、`dayu/web/**`、`dayu/wechat/**`、`dayu/render/**` 但没有列出 Windows CI workflow 文件。
- **反例/失败场景**：R11 子计划需要新增 `.github/workflows/windows-ci.yml`（或等价），该文件不在 §7.4 R11 的 allowed production/config/package files 闭集中。子计划的 plan review 可能因为 workflow 文件不在闭集而产生歧义。
- **为什么有问题**：§7.4 的闭集只列 production/config/package 文件，而 CI workflow 文件不是 production 文件。Plan 已在 §18.1 给出"子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist"的指令，子计划可以在自己的 plan 中扩展闭集。这不构成 umbrella plan 的 gap，但 §7.4 可以更明确地声明 CI workflow 文件由子计划自行纳入。
- **直接证据**：§7.4 line 234："下表是 production/config/package 的闭集"。§18.1 line 908："子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist"。
- **影响**：低。子计划已有明确指令自行纳入 workflow 文件。
- **建议改法和验证点**：在 §7.4 增加一句："CI workflow 文件不属于 production/config/package 闭集；R11 子计划按 §18.1 自行纳入 Windows workflow 文件。"
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

### 03-新-note-§7.3 artifact naming 的 `{mimo,ds}` 展开

- **位置**：Plan §7.3 line 209-225
- **问题类型**：最佳实践偏离
- **当前写法**：§7.3 列出 artifact naming 模板，使用花括号 `{mimo,ds}` 表示"必须分别存在两份而不是一份合并文件"。
- **反例/失败场景**：Implementation agent 可能把 `{mimo,ds}` 当作 shell glob 而不是人工展开提示，误生成一个合并文件。
- **为什么有问题**：花括号在 shell 和 Python 中有特定含义，可能被误解。
- **直接证据**：§7.3 line 209："花括号表示必须分别存在两份而不是一份合并文件"。
- **影响**：极低。Plan 已显式解释花括号含义，且 artifact naming 是 review/fix 流程中的手工操作。
- **建议改法和验证点**：无需修改。当前解释已足够清晰。
- **修复风险（低/中/高）**：无
- **严重程度（低/中/高/严重）**：低（note only）

---

## 九、Open Questions

无 blocking open questions。

---

## 十、Residual Risks

无新增 material residual risk。Plan §23 已覆盖 8 项 residual risk，均有 owner/destination。初轮 rereview 识别的 3 个 risk（R03 inventory 模板、R11 Windows runner stop、R06 producer migration 范围）的 disposition：

| Risk | 初轮 rereview 严重度 | Controller 裁决 | 本轮状态 |
| --- | --- | --- | --- |
| R03 source inventory 缺少表格模板 | 低 | MIMO-RR-F01 rejected-with-reason | 关闭，不修改 |
| R11 Windows runner stop 行为 | 低 | MIMO-RR-F02 rejected-with-reason | 关闭，不修改 |
| R06 producer migration 范围 | 低 | MIMO-RR-F03 note / no fix | 关闭，不修改 |

---

## 十一、Final Plan Review Conclusion

### Verdict: **pass**

修订后 remediation plan 通过第二轮第一路完整 re-review。理由：

**DS-RR-F01 四点 closure**：
1. §7.3 line 203-204：umbrella baseline 是 mandatory starting baseline，不是直接实施授权。✅
2. §7.3 line 205：accepted-plan commit 后该 plan 成为唯一 execution truth；umbrella 继续独占边界/顺序/invariant。✅
3. §7.3 line 206：差异逐项登记三类 disposition，附直接证据，禁止弱化验证下限。✅
4. §7.3 line 207：owner/依赖/allowlist/contract 实质变化必须 stop 回 controller。✅

**Umbrella mandatory baseline 未弱化**：§7.1—§7.5、§8—§19、§21、§22 全部保留，仅增加 DS-RR-F01 时序语义规则。✅

**Accepted sub-WU plan exact truth 时序**：同一时点只有一个 exact execution truth；切换点是 accepted-plan local commit。✅

**实质变化回 controller**：四种触发条件、唯一 stop 动作、禁止静默扩域。✅

**DS-RR-F02/F03、MIMO-RR-F01/F02/F03 未实施**：五个 rejected/note finding 均未被误实现。✅

**初轮全部 closure 仍成立**：5 CTL + 12 DS + 15 MiMo findings 全部按 disposition 保持。✅

**Topic 8/9 与 Issue 142/151/175/177/178 边界未漂移**：均为 no-code 或 deferred，无越界实现。✅

**新 findings**：3 个（1 低、1 低、1 note），均不阻塞 implementation。

**计划可以进入 implementation。下一动作由 umbrella controller 派发 R01 子计划。**

---

## 十二、逐项证据清单

| 检查项 | 结果 | 关键证据位置 |
| --- | --- | --- |
| DS-RR-F01 Point 1（baseline 非直接授权） | PASS | §7.3 line 203-204 |
| DS-RR-F01 Point 2（accepted commit 为切换点） | PASS | §7.3 line 205 |
| DS-RR-F01 Point 3（差异逐项登记） | PASS | §7.3 line 206 |
| DS-RR-F01 Point 4（实质变化回 controller） | PASS | §7.3 line 207 |
| Umbrella baseline 未弱化 | PASS | §7.1-§7.5、§8-§19、§21、§22 |
| Accepted sub-WU plan exact truth 时序 | PASS | §7.3 line 205、§0 line 7、§7.5 line 255 |
| 实质变化回 controller | PASS | §7.3 line 207、§7.3 line 226 |
| DS-RR-F02 未实施 | PASS | §14.2/§14.5 未修改 |
| DS-RR-F03 未实施 | PASS | §11.3 未修改 |
| MIMO-RR-F01 未实施 | PASS | §10.4 未修改 |
| MIMO-RR-F02 未实施 | PASS | §18.1/§18.3/§22.1 未修改 |
| MIMO-RR-F03 未实施 | PASS | §13/§7.4 R06 未修改 |
| CTL-PF-01 至 CTL-PF-05 closure | PASS | 各 finding 对应 plan 位置 |
| DS-PF-01 至 DS-PF-12 closure | PASS | 各 finding 对应 plan 位置 |
| MIMO-PF-01 至 MIMO-PF-15 closure | PASS | 各 finding 对应 plan 位置 |
| Topic 8 no-code | PASS | §3 line 66、§4 line 97 |
| Topic 9 no-code | PASS | §3 line 67、§4 line 99 |
| Issue 142 deferred | PASS | §3 line 69、§4 line 96、§19.3 |
| Issue 151 deferred | PASS | §19.3 line 1026 |
| Issue 175 deferred | PASS | §4 line 85、§12.4 line 635 |
| Issue 177 deferred | PASS | §4 line 79、§8.5 line 347 |
| Issue 178 deferred | PASS | §4 line 81、§9.2 line 389 |
| 分层边界 | PASS | §5 owner map |
| 过度工程 | PASS | §25 self-check |
| 过度耦合 | PASS | §5 合并理由 |
| 状态机完整性 | PASS | §8.3/§12.2/§13.2/§16.2/§19.3 |
| Sequencing/依赖 | PASS | §6 dependency graph |
