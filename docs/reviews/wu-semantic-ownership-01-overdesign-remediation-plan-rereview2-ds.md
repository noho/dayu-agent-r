# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan 第二轮第二路 Re-Review — AgentDS

## Gate 身份

- **角色**：AgentDS，既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 remediation 总计划**第二轮第二路独立完整 plan re-review**；不是新 WU、R01 plan、implementation 或初轮 review。
- **审查对象**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（经 AgentCodex re-review-fix 关闭 DS-RR-F01 后的最终全文，1270 行）。
- **Re-review-fix evidence**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-fix-codex.md`。
- **唯一 disposition 真源**：
  - 初轮：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`
  - 第一轮 re-review：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview-controller-adjudication.md`
- **产品裁决真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- **设计真源**：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`
- **流程真源**：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`
- **完整阅读材料**：AGENTS.md、phaseflow/control、controller discussion、五份 design truth、最终 plan、初轮 reviews/adjudication/fix（MiMo + DS + Codex）、第一轮 rereviews/controller adjudication（MiMo + DS）、re-review-fix codex artifact。
- **Review date**：2026-07-14
- **禁止动作**：不修改 plan/control/design/代码/测试/README/任何其它 review artifact；不 commit/push/PR。
- **输出**：仅新增本 artifact（`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-rereview2-ds.md`）。

## Review Method

1. 以两份 controller adjudication 为唯一 disposition 真源，不以 reviewer 原始 verdict/severity/建议覆盖裁决。
2. 验证 DS-RR-F01 四点均在最终 plan 中真实关闭（非仅声明，而是可定位的具体文本）。
3. 验证 umbrella mandatory baseline（§7.4 closed manifest、§7.5 per-slice matrix、§8—§19 slice 定义、§21 security matrix、§22 aggregate gates）未被弱化。
4. 验证 accepted sub-WU plan 的 exact truth 只在 accepted-plan commit 后生效的时序规则完整且无歧义。
5. 验证实质 owner/dependency/production allowlist/contract 变化会回 controller 的 stop/escalation 边界。
6. 逐项确认 DS-RR-F02/F03、MIMO-RR-F01/F02/F03 未被实施。
7. 逐项确认初轮全部 closure（5 个 CTL、12 个 DS、15 个 MiMo findings）仍成立。
8. 确认 Topic 8/9 与 Issue 142/151/175/177/178 边界未漂移。
9. 对最终全文执行 adversarial re-review，产出新 findings（不限 severity）。
10. 给出 final verdict 与 blocking questions。

---

## 一、DS-RR-F01 四点 Closure 独立验证

第一轮 re-review controller adjudication 要求修复 DS-RR-F01（中），四点要求如下。以下逐点给出最终 plan 中的可定位文本证据与独立判断。

### Point 1：Umbrella per-slice 命令/文件集合是 mandatory starting baseline，不是直接实施授权

**Plan 文本证据**：

- §0 第 8 行："本文拥有 R01—R12 的切分、顺序、全局不变量、最低验证意图和基于当前代码证据的 mandatory starting baseline，不能替代任一 sub-WU 自己的 code-generation-ready plan"
- §7.3 第 203—204 行："在某个 sub-WU 的 accepted-plan local commit 产生前，本文拥有该 sub-WU 的边界、顺序、全局不变量、最低验证意图，以及第 7.4 节 production allowlist、第 7.5 节和各 Rxx 正文给出的 per-slice 文件集合、测试命令/test node、coverage 与 scan 的 mandatory starting baseline。这些基线是后续独立 plan 必须消费的最低输入，不是跳过 sub-WU plan、review 和 accepted-plan commit 的直接实施授权。"
- §7.5 第 255—256 行："这里和各 Rxx 正文列出的命令、test node、文件集合、coverage `--include` 与 scan 是基于当前代码证据的 mandatory starting baseline；later accepted sub-WU plan 必须逐项映射并核实，只有其 accepted-plan commit 后的 exact 项才支配该 sub-WU implementation。"

**独立判断**：**已关闭**。三处文本相互印证且语义一致：(a) umbrella 在 accepted-plan commit 前拥有 baseline；(b) baseline 是必须消费的最低输入；(c) baseline 不授权跳过 sub-WU plan gate。不存在"baseline = 直接授权"的歧义。

### Point 2：Sub-WU 重新核对真实文件/test node/slice 原子性/scan；accepted-plan commit 后成为 exact execution truth

**Plan 文本证据**：

- §7.3 第 205 行："每个 sub-WU plan 必须在其实际 base 上重新核对真实文件、test node、slice 原子性和 propagation/source/security scan。只有该 plan 完成双路 review、controller adjudication、accepted finding fix、双路完整 re-review并由 controller 创建 accepted-plan local commit 后，该 commit 中的 plan 才成为该 sub-WU 对 exact slice、文件、命令、test node 与 scan 的唯一 execution truth；本文继续独占 sub-WU 边界、顺序、全局不变量和最低验证意图，不与 accepted sub-WU plan 形成第二份 exact 执行真源。"

**独立判断**：**已关闭**。明确了两个关键时序：(a) accepted-plan commit 是 exact truth 生效的 gate；(b) umbrella 与 accepted sub-WU plan 不形成双真源——umbrella 保留治理权（边界/顺序/不变量），sub-WU plan 拥有执行细节（exact slice/文件/命令/test node/scan）。分工清晰且互斥。

### Point 3：差异逐项附直接证据，不得弱化既有验证和 contract

**Plan 文本证据**：

- §7.3 第 206 行："sub-WU plan 必须逐项记录 umbrella baseline 到 accepted-plan exact 项的 `保留 | 基于直接代码证据细化 | 以等价验证替换` 映射；任何差异都必须附真实调用链、文件或 test collection 证据，baseline 项不得静默遗漏。细化或等价替换不得弱化 controller accepted contract、retained security、changed production file 逐文件覆盖率 `>=80%`、全量 pyright、README decision、真实/跨平台 smoke 或 LLM/source/security propagation scan。"

**独立判断**：**已关闭**。(a) 三类映射（保留/细化/等价替换）覆盖了所有可能的差异类型；(b) "baseline 项不得静默遗漏" 防止静默降级；(c) 明确列出了不可弱化的下限清单（contract、security、coverage、pyright、README、smoke、scan）。这是一个完整且可验证的差异管理 contract。

### Point 4：Owner、依赖、production allowlist 或 accepted contract 实质变化必须回 controller

**Plan 文本证据**：

- §7.3 第 207 行："若重新核对发现语义 owner、依赖、production allowlist 或 controller accepted contract 发生实质变化，sub-WU plan 必须停止并回到 controller 裁决；不得以调整 exact slice/命令为名静默扩域、改变 owner 或重写 accepted contract。"
- §7.3 stop condition 第 226 行进一步覆盖："owner 不清、设计与 controller 冲突、需要越界 issue、出现无法同源的中间 schema、retained security 失败、新/扩散 baseline、allowed files 外 diff、accepted finding 未闭合或 Windows release blocker 未被追踪时立即停止，不以 fallback/兼容 shim 继续。"

**独立判断**：**已关闭**。两处文本形成双重防护：(a) §7.3 第 207 行专门针对 sub-WU plan 阶段的实质变化回 controller；(b) §7.3 stop condition 覆盖更广泛的 stop 触发条件。"不得以调整 exact slice/命令为名静默扩域" 精确命中了 controller 担心的风险模式。

### DS-RR-F01 Closure 总评

四点均有唯一、可定位、语义互洽的 plan 文本落点。修复未引入新歧义、未删除既有 baseline、未弱化任何 controller accepted contract。Closure 真实且完整。

---

## 二、Umbrella Mandatory Baseline 完整性回归

逐项核对 umbrella baseline 在 DS-RR-F01 fix 前后的一致性：

| Baseline 组件 | Plan 位置 | Fix 前状态 | Fix 后状态 | 是否弱化 |
| --- | --- | --- | --- | --- |
| §7.4 Closed production/config/package manifest（12 行 × 每 sub-WU 精确文件列表） | §7.4 第 237—251 行 | 完整 | 完整，未修改 | **否** |
| §7.5 Per-slice verification substitution matrix（30 行 × coverage/include/scan/README） | §7.5 第 256—288 行 | 完整 | 完整，仅增加时序解释首句（第 255—256 行） | **否**（仅增加澄清，未删除/修改任何命令或 scan） |
| §8—§19 每个 Rxx 的 slice 定义、exact pytest 命令、scan、smoke | §8—§19 | 完整 | 完整，未修改 | **否** |
| §21 Security retained/modified 行为清单（16 行） | §21 第 1097—1118 行 | 完整 | 完整，未修改 | **否** |
| §22.1 Aggregate regression 命令与 scan（6 条 rg + 11 行 smoke 矩阵） | §22.1 第 1122—1161 行 | 完整 | 完整，未修改 | **否** |
| §22.3 PR gates 七条 criteria | §22.3 第 1175—1186 行 | 完整 | 完整，未修改 | **否** |
| §22.4 Final closeout 验收矩阵（10 维度） | §22.4 第 1189—1205 行 | 完整 | 完整，未修改 | **否** |
| §7.1 Slice transaction 七步协议 | §7.1 第 149—173 行 | 完整 | 完整，未修改 | **否** |
| §7.2 Baseline failure registry 复用规则 | §7.2 第 175—180 行 | 完整 | 完整，未修改 | **否** |

**结论**：DS-RR-F01 fix 仅新增了三处时序/治理澄清文本（§0 第 8 行、§7.3 第 203—207 行、§7.5 第 255—256 行），未删除、修改或弱化任何既有 baseline 条目。Umbrella mandatory baseline 完整性保持。

---

## 三、Accepted Sub-WU Plan Exact Truth 时序规则独立验证

§7.3 第 203—207 行定义的时序规则是本计划的唯一规范位置。独立验证三个关键时点的 owner 分配：

| 时间点 | 唯一 owner | Plan 文本 | 验证 |
| --- | --- | --- | --- |
| Accepted-plan commit **前** | Umbrella plan：sub-WU 边界、顺序、全局不变量、最低验证意图、mandatory starting baseline | §7.3 第 203—204 行 | 不拥有 exact execution items，不授权直接 implementation |
| Accepted-plan commit **后** | Accepted sub-WU plan（该 commit 内）：exact slice、文件、命令、test node、scan | §7.3 第 205 行 | 不重写 umbrella 边界/顺序/不变量/contract |
| 发现实质变化 | Umbrella controller | §7.3 第 207 行 | Sub-WU plan 不得自行裁决或静默扩域 |

三个时点的 owner 互斥且互补，不存在同一语义有双 owner 的窗口。时序规则完整且无歧义。

---

## 四、DS-RR-F02/F03、MIMO-RR-F01/F02/F03 未实施验证

逐项确认五个 rejected/note finding 在最终 plan 中的状态：

| Finding | Controller Disposition | 声称状态（fix-codex） | 独立验证 |
| --- | --- | --- | --- |
| DS-RR-F02 | rejected-with-reason（低） | 未实施 | **确认**。§14.2 仍为 "fresh schema直接使用新布局，不兼容旧布局、不迁移旧库"（第 720 行）；未新增 "旧 storage 数据需 fresh workspace/重新 ingestion" 的用户说明。 |
| DS-RR-F03 | rejected-with-reason（低） | 未实施 | **确认**。§11.3 R04-S2 仍为 "与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 `wait_poller_policy`"（第 555 行）；未增加 deployment-value/internal-constant 的例子或白名单。 |
| MIMO-RR-F01 | rejected-with-reason（低） | 未实施 | **确认**。§10.4 R03-S2 仍为逐列规定的 inventory 字段（文件、具体 source、是否 LLM-facing、语义 owner、disposition、验证证据）（第 491 行）；未增加 Markdown 表格模板。 |
| MIMO-RR-F02 | rejected-with-reason（低） | 未实施 | **确认**。§18.1、§18.3、§22.1 未新增 "CI 平台不支持 Windows runner 时的 fallback 路径" 或替代方案；stop condition 已隐含正确行为（缺 runner → stop → 回 controller）。 |
| MIMO-RR-F03 | note / no fix | 未实施 | **确认**。§13 与 §7.4 R06 行未修改；R06 保持 3 slices、22 storage + 12 pipeline 文件 allowlist；未预拆 R06 或删除 producer。 |

**结论**：五个 rejected/note finding 均未被实施。DS-RR-F01 fix 严格执行了 "只修 accepted" 的规则。

---

## 五、初轮全部 Closure 仍成立——逐类回归

### 5.1 Controller Findings（CTL-PF-01 至 CTL-PF-05）

| Finding | 初轮裁决 | 第一轮 re-review closure | 第二轮独立验证 |
| --- | --- | --- | --- |
| CTL-PF-01（per-sub-WU gate state machine） | accepted/blocking | 已关闭（§7.3 第 186—227 行） | **仍成立**。§7.3 状态机、artifact naming、entry/exit criteria 完整；DS-RR-F01 fix 未修改此区域的核心 gate 结构。 |
| CTL-PF-02（所有 severity accepted finding 修复） | accepted/blocking | 已关闭（§7.3 第 203 行、§22.2 第 1168 行） | **仍成立**。"任一 severity 均不得过滤" 在 §7.3 和 §22.2 两处保留。 |
| CTL-PF-03（controller local commit 与 PR 授权） | accepted/blocking | 已关闭（§7.3 第 225 行、§22.3 第 1170—1182 行） | **仍成立**。四类 accepted commit gates 与已授权 push/draft PR 边界完整。 |
| CTL-PF-04（当前分支串行） | accepted | 已关闭（§6 第 145 行） | **仍成立**。"不得创建独立实施分支，也不得通过 rebase 汇总" 零残留。 |
| CTL-PF-05（R07 无 speculative contract） | accepted | 已关闭（§14.2—14.5） | **仍成立**。全文无固定 hash/prefix/revision grammar/retry 次数/新异常名/cache lease 类名。 |

### 5.2 AgentDS Findings（DS-PF-01 至 DS-PF-12）

逐项抽检关键 finding：

- **DS-PF-01（Windows batch renderer）**：§18.2 第 917—918 行 `DisableDelayedExpansion`、`%`/`!`/`&|^()` 处理、`list2cmdline` 不作为 batch quoting owner → **仍成立**。
- **DS-PF-02（R07 收窄）**：§14.2—14.5 删除固定 hash/retry/lease → **仍成立**。
- **DS-PF-04（人工 source inventory）**：§10.4—10.5 完整 inventory 要求 + "仅有 grep 零命中不得完成 R03" → **仍成立**。
- **DS-PF-06（R08 raw total/public count）**：§15.2—15.4 三类验证（正向 internal scan + 反向 public scan + owner-level test）→ **仍成立**。
- **DS-PF-08（R01→R03 handoff）**：§6 第 146 行 + §8.5 + §10.4 → **仍成立**。
- **DS-PF-11（assets/reset 语义）**：§19.3 第 1024—1026 行 managed-root manifest → **仍成立**。

所有 12 个 DS finding 的 closure 文本均未被 DS-RR-F01 fix 触及，closure 仍成立。

### 5.3 AgentMiMo Findings（MIMO-PF-01 至 MIMO-PF-15）

逐项抽检关键 finding：

- **MIMO-PF-03（policy 数值唯一真源）**：§11.2 第 526 行 `host_runtime.json` + typed policy 无 deployment defaults → **仍成立**。
- **MIMO-PF-05（prewarm first/reset only）**：§19.3 第 1030 行 → **仍成立**。
- **MIMO-PF-06（两类 smoke 分离）**：§18.3 第 945—947 行 → **仍成立**。

所有 15 个 MiMo finding 的 closure 文本均未被 DS-RR-F01 fix 触及，closure 仍成立。

### 5.4 Rejected/Note Findings 未误实现

- DS-PF-07（rejected）：R05 + R09 跨层组合未出现 → **仍成立**。
- MIMO-PF-04（rejected）：未新增 credential fallback/特例脱敏/blacklist → **仍成立**。
- DS-PF-10/12、MIMO-PF-08 至 MIMO-PF-15（note）：均未被升级为实现要求 → **仍成立**。

**初轮 closure 结论**：全部 32 个初轮 finding（5 CTL + 12 DS + 15 MiMo）的 closure 状态在 DS-RR-F01 fix 后仍成立。Fix 未修改任何与初轮 finding 相关的 plan 区域。

---

## 六、Topic 8/9 与 Issue 142/151/175/177/178 边界漂移检查

| 边界 | Plan 约束位置 | 当前文本 | 是否漂移 |
| --- | --- | --- | --- |
| Topic 8（Engine 240 字符异常消息） | §3 第 66 行、§4 追踪表 | "保留 `dayu/engine/agent.py` 的敏感值先脱敏、原始异常消息 240 字符上限、显式截断后缀和完整 traceback 日志；不改配置、不新增 durable full-detail ref" | **否**。全文无 Engine 异常消息修改指令。 |
| Topic 9（统一 tool authorization） | §3 第 67 行、§4 追踪表 | "不设计或实现统一 tool authorization framework、角色模型、policy DSL、capability token 或 sandbox" | **否**。全文无 authorization framework 设计。 |
| Issue 177（TruncationManager） | §3 第 72 行、§4 追踪表 | "不把 Doc 输入完整性改成 Issue 177 的完整 `TruncationManager` 接通" | **否**。§8.1 明确 "不得接 Issue 177"；R01-S1 第 330 行 "不得接 Issue 177"。 |
| Issue 178（credential storage-state lifecycle） | §3 第 72 行、§4 追踪表 | R02 "只保留路径输入，不实现生命周期" | **否**。§9.2 第 390 行 "credential state 的生成/刷新/保留交给 Issue 178"。 |
| Issue 175（Fins 长事务进程隔离） | §3 第 72 行、§4 追踪表 | "不把 Fins 长事务迁往 Issue 175 的进程隔离" | **否**。§12.4 第 640 行 "迁移 Issue 175 executor 的方案立即 stop"。 |
| Issue 142/151（workspace migration / product assets） | §3 第 69 行、§4 追踪表 | "不实施 Issue 142、151" | **否**。§19.3 第 1029 行 "本 WU 不得创建空 `assets`、从 OLD 搬入 assets"；§19.5 第 1077 行 "任何需要迁移旧 schema...立即 stop"。 |
| Web/WeChat/render tracker | §3 第 69 行 | "不把现有 Web/WeChat/render tracker 能力搬入本 WU" | **否**。§18.2 第 925 行 "不得实现 tracker 能力"。 |

**额外验证**：全文 `rg` 等价扫描——无 "Issue 142"、"Issue 151"、"Issue 175"、"Issue 177"、"Issue 178" 的实现指令；无 Topic 8 修改指令；无 Topic 9 框架设计指令。所有出现均为 deferred/no-code 标记或 residual risk destination。

**结论**：Topic 8/9 与全部五个 deferred issue 边界零漂移。

---

## 七、新 Findings（第二轮独立 Adversarial Review）

### DS-RR2-F01 — 低 — Umbrella baseline "mandatory" 措辞与 sub-WU plan 独立性的残余张力

- **位置**：§7.5 第 255 行 "mandatory starting baseline" 与 §7.3 第 205 行 "唯一 execution truth"
- **问题类型**：不可直接实施（措辞歧义）
- **当前写法**：§7.5 将 per-slice 命令称为 "mandatory starting baseline"；§7.3 第 203—204 行解释 baseline 是 "必须消费的最低输入，不是跳过 sub-WU plan...的直接实施授权"。同一段 §0 第 8 行也使用 "mandatory starting baseline"。
- **反例/失败场景**：实施 agent 在编写 R07 sub-WU plan 时，发现现有测试文件命名与 umbrella baseline 的 `-k 'path or identifier or containment or symlink or unicode or document_id or ticker'` 不完全匹配。如果 agent 将 "mandatory" 理解为 "必须逐字使用"，可能强行适配 `-k` 表达式而非基于实际 test node 重写。如果 agent 将 baseline 理解为 "可自由偏离"，又可能遗漏 baseline 覆盖的测试场景。
- **为什么有问题**："mandatory" 在英语中的常规含义是 "compulsory/obligatory"，与 "starting baseline（起点基线）" 存在措辞张力。虽然 §7.3 的解释消除了语义歧义（baseline 是必须消费的输入而非 rigid template），但实施 agent 可能只读 §7.5 的表和命令而不回溯 §7.3 的完整解释。
- **直接证据**：§7.5 第 255 行 "mandatory starting baseline"；§7.3 第 203—204 行的解释在物理位置上与 §7.5 相距约 50 行，且 §7.5 未在本地重复 "不是 rigid template" 的澄清。
- **影响**：实施 agent 在编写 sub-WU plan 时可能过度依赖 umbrella baseline 的 exact 命令，放弃基于代码证据的独立判断；或反之完全忽略 baseline 导致测试覆盖退化。两种偏向都会被 sub-WU plan review 捕获，但可能延长 review cycle。
- **建议改法和验证点**：在 §7.5 第 255 行 "mandatory starting baseline" 后增加一句本地澄清："（即 sub-WU plan 必须逐项核实并解释差异，但 exact 命令以 sub-WU plan 自身为最终执行真源）"。该修改约 30 字，不改变任何 baseline 条目或 contract。
- **修复风险**：低（仅措辞澄清，已在 §7.3 有完整解释，此处为本地冗余）。
- **严重程度**：低。

### DS-RR2-F02 — 低 — Baseline 映射粒度未定义，"逐项" 的可操作边界不清

- **位置**：§7.3 第 206 行 "sub-WU plan 必须逐项记录 umbrella baseline 到 accepted-plan exact 项的 `保留 | 基于直接代码证据细化 | 以等价验证替换` 映射"
- **问题类型**：不可直接实施
- **当前写法**：要求 "逐项" 映射，但未定义 "项" 的粒度。一个 slice 的 umbrella baseline 包含多个元素：pytest 命令（含 `-k` 表达式）、coverage `--include` 模式、一个或多个 `rg` scan 命令、README decision。这些是各自独立映射为一行，还是整个 slice 作为一个 "项"？
- **反例/失败场景**：R06-S3 的 umbrella baseline 有 8 个测试文件的 pytest 命令和 source-propagation scan。Sub-WU plan 发现需要新增第 9 个测试文件。如果 "项" = 整个 slice，plan 标记 "细化" 并列出新增文件即可。如果 "项" = 每个测试文件，plan 需要逐文件标记 8 个 "保留" + 1 个 "新增"。两种粒度都合理，但不一致的粒度会让 reviewer 难以判断映射完整性。
- **为什么有问题**：映射是 sub-WU plan 的 mandatory deliverable，也是 controller 验证 sub-WU plan 未静默弱化 baseline 的关键证据。粒度不定义可能导致：(a) 不同 sub-WU plan 使用不同粒度，aggregate consistency 受损；(b) 粗粒度映射可能掩盖个别 baseline 项的遗漏。
- **直接证据**：§7.3 第 206 行的 "逐项" 未附带粒度定义；§24 completion report format 也未定义映射格式。
- **影响**：plan review 时 reviewer 可能对映射完整性有不同判断；不阻塞 implementation 但可能增加 review 往返。
- **建议改法和验证点**：在 §7.3 第 206 行补充一句："'项' 的粒度为 umbrella baseline 中每个独立的 pytest 命令、coverage `--include` 模式、`rg` scan 命令与 README decision 各为一项；若 sub-WU plan 的 exact 命令合并或拆分 umbrella baseline 中的 pytest 调用，必须在映射中标注新旧对应关系。" 或在 §24 completion report format 中增加一行映射示例。
- **修复风险**：低（仅澄清粒度，不改变 baseline 条目）。
- **严重程度**：低。

### DS-RR2-F03 — 低 — R01 handoff 到 R03 的 LLM-facing 删除清单格式未定义

- **位置**：§8.5 第 352 行 "handoff 到 R03/aggregate：逐文件列出全部 Doc tool name/description/参数/枚举/错误说明、真实 LLM prompt fixture 与其它 LLM-facing 文本中被删除、保留或改写的项，记录 source owner 和最终 disposition；该清单是 R03 人工 source inventory 的必填输入。不得只交一条 grep 结果。"
- **问题类型**：契约缺失
- **当前写法**：R01 completion report 必须产出 LLM-facing 删除清单作为 R03 的必填输入。但清单的格式、字段和存储位置（R01 completion report 的哪一节？独立 artifact？）未定义。
- **反例/失败场景**：R01 完成后，completion report 的 LLM-facing 清单以自由文本段落形式嵌入 §24 模板的 "删除了什么 contract" 字段。R03 启动时，implementation agent 需要从 R01 completion report 中人工提取结构化清单，可能遗漏条目或误解 disposition。
- **为什么有问题**：R01→R03 是 umbrella plan 明确建立的跨 sub-WU 数据依赖（§6 第 146 行），也是 R03 source inventory 的必填输入（§10.4 第 491 行）。如果输入格式不可靠，R03 的 inventory 完整性基础会受影响。
- **直接证据**：§8.5 第 352 行列出了清单必须包含的内容（Doc tool name/description/参数/枚举/错误说明、LLM prompt fixture、LLM-facing 文本），但未定义格式、字段或存储位置。§24 completion report format 的 "删除了什么 contract" 字段过于宽泛，不足以承载结构化清单。
- **影响**：R03 启动时可能需要额外澄清往返；不阻塞 R01 但增加 R01→R03 handoff 的 friction。
- **建议改法和验证点**：在 §8.5 补充："清单以 Markdown 表格形式存入 R01 completion report 的独立一节'R03 handoff: Doc LLM-facing 删除清单'，列：文件路径、具体文本片段、操作（删除/保留/改写）、语义 owner、最终 disposition。" 该格式与 R03 inventory 的字段（§10.4 第 491 行）对齐，减少 R03 的转换成本。
- **修复风险**：低（仅澄清格式）。
- **严重程度**：低。

---

## 八、架构边界与设计质量回归

### 8.1 DS-RR-F01 Fix 的架构影响

Fix 新增的三处文本（§0 第 8 行、§7.3 第 203—207 行、§7.5 第 255—256 行）均属于 plan artifact 的治理/时序语义层，不涉及：
- 产品代码架构（分层、依赖方向、owner 分配）
- 状态机定义（R01/R05/R06/R09/R12 状态机均未修改）
- Public contract（Tool schema、Fins domain、CLI workflow 均未修改）
- Config/schema boundary（`host_runtime.json`、`tool_discovery.json`、storage layout 均未修改）

**结论**：Fix 是纯 plan governance 修改，零架构影响。

### 8.2 过度工程设计检查（§25 自我检查回归）

§25 六条自我检查在 fix 前后一致：
1. 只计划 controller 已接受的 Topic 1—7 → **仍成立**。
2. 12 sub-WU 按唯一 owner/durable blast radius/可独立回滚切分 → **仍成立**。
3. 每个 sub-WU 最多 3 slices → **仍成立**。
4. 无 god object/factory/bag/builder → **仍成立**。
5. 预算/catalog/脚本规则只在已裁决或 OLD-aligned 处出现 → **仍成立**。
6. 验证成本按 umbrella optimization 复用 baseline → **仍成立**。

### 8.3 过度耦合检查

- R03 合并 Topic 3/4 的理由（共享 accepted-evidence projection 与四个 downstream consumers）→ **仍成立**。
- R06 合并 batch authority 与 source publication 的理由（transaction commit point 与 source 可见点必须同时切换）→ **仍成立**。
- R07 合并 revision/snapshot 与 opaque ID mapping 的理由（共同改变 storage path/read snapshot layout）→ **仍成立**。

**结论**：无新增过度耦合。

---

## 九、Open Questions

1. **Baseline 映射的 reviewer 验收标准**：§7.3 第 206 行要求 "逐项记录...映射"，两路 plan reviewer 如何判断映射 "完整"？是按 umbrella baseline 的每行命令逐项核对，还是接受合理的粒度聚合？这不是 umbrella plan 的 defect——每个 sub-WU plan review 时 reviewer 可以自行建立验收标准——但 aggregate consistency 可能受益于 controller 在 R01 plan review 时确立一个先例。

2. **R11 Windows runner 的最晚完成时间与 R01—R10 进度的交互**：如果 R01—R10 全部完成但 R11 Windows smoke 因 runner 不可用而阻塞，整个 umbrella 停在 aggregate gate。Controller 已裁决 "不得把 unsafe quoting 或未验证 Windows 行为列为 residual"，这是 conscious decision。但 contingency 的形态（等待 runner vs. 先完成 POSIX closure 并单独追踪 Windows）会影响 R01—R10 完成后到最终 closeout 的 wall-clock 时间。这不是 umbrella plan 需要现在解决的问题，但值得在 R11 sub-WU plan 的 Windows runner entry criteria 中 explicit。

---

## 十、Residual Risks（本轮新识别，非 plan §23 已有）

无新增 material residual risk。§23 已覆盖 7 项 residual risk（Doc 资源耗尽、browser credential lifecycle、Fins 长事务取消、future product assets、Windows env 非跨资源原子性、HKEX rowRange cap、Web peer proof + proxy incompatibility），均有 owner/destination。

本轮三个低严重度 finding（DS-RR2-F01/F02/F03）均为 plan 措辞澄清建议，可在 controller adjudication 中决定是否修复。三者均不阻塞 plan 进入下一 gate，也不改变任何 accepted contract 或 baseline。

---

## 十一、Final Verdict

### Verdict：**PASS**

### 通过理由

1. **DS-RR-F01 四点均真实关闭**：四点各有唯一、可定位、语义互洽的 plan 文本落点（§0 第 8 行、§7.3 第 203—207 行、§7.5 第 255—256 行）。Closure 完整且未引入新歧义。

2. **Umbrella mandatory baseline 未弱化**：§7.4 closed manifest、§7.5 per-slice matrix（30 行）、§8—§19 slice 定义、§21 security matrix（16 行）、§22 aggregate gates 全部保留原样。DS-RR-F01 fix 仅新增治理/时序澄清文本，未删除或修改任何 baseline 条目。

3. **Accepted sub-WU plan exact truth 时序规则完整**：§7.3 第 203—207 行定义了三个互斥时点的唯一 owner（accepted-plan commit 前 = umbrella baseline，commit 后 = sub-WU plan exact items，实质变化 = controller）。不存在双真源窗口。

4. **实质变化回 controller 的 stop/escalation 边界明确**：§7.3 第 207 行（sub-WU plan 阶段）与 §7.3 第 226 行（通用 stop condition）形成双重防护。

5. **DS-RR-F02/F03、MIMO-RR-F01/F02/F03 均未实施**：五个 rejected/note finding 的对应 plan 区域均未被 DS-RR-F01 fix 触及。

6. **初轮全部 32 个 finding closure 仍成立**：5 个 CTL、12 个 DS、15 个 MiMo finding 的 closure 文本均未被 fix 修改。2 个 rejected finding 仍未被误实现。全部 note 仍未被升级为实现要求。

7. **Topic 8/9 与 Issue 142/151/175/177/178 边界零漂移**：所有边界约束在 §3/§4/§23 中保持一致，全文无越界实现指令。

8. **Fix 零架构影响**：DS-RR-F01 fix 是纯 plan governance 修改，不涉及产品架构、状态机、public contract、config/schema boundary。

### Risks（不阻塞 pass）

三个低严重度新 finding：
- **DS-RR2-F01（低）**：§7.5 "mandatory starting baseline" 措辞与 sub-WU plan 独立性的残余张力。建议在 §7.5 本地增加一句澄清。
- **DS-RR2-F02（低）**：Baseline 映射的 "逐项" 粒度未定义。建议在 §7.3 第 206 行明确 "项" = 每个独立 pytest 命令/coverage 模式/rg scan/README decision。
- **DS-RR2-F03（低）**：R01→R03 handoff 的 LLM-facing 删除清单格式未定义。建议在 §8.5 补充表格模板字段。

三者均可选修复（controller 裁决是否在 umbrella plan 内修 or 委托给对应 sub-WU plan），不阻塞 plan 进入下一 gate。

### Blocking Questions

**无**。总计划已完成 DS-RR-F01 闭合，全部 closure 验证通过，无未裁决的 material finding。Plan 可进入 controller 的 accepted-plan decision。

---

## 十二、逐项证据清单

| 检查项 | 结果 | 关键证据位置 |
| --- | --- | --- |
| DS-RR-F01 Point 1（baseline 非直接授权） | PASS | §0 第 8 行、§7.3 第 203—204 行、§7.5 第 255—256 行 |
| DS-RR-F01 Point 2（accepted-plan commit 后 exact truth） | PASS | §7.3 第 205 行 |
| DS-RR-F01 Point 3（差异逐项记录，不得弱化） | PASS | §7.3 第 206 行 |
| DS-RR-F01 Point 4（实质变化回 controller） | PASS | §7.3 第 207 行、§7.3 stop condition 第 226 行 |
| Umbrella baseline 未弱化 | PASS | §7.4/§7.5/§8—§19/§21/§22 全部保留 |
| Accepted sub-WU plan exact truth 时序规则 | PASS | §7.3 第 203—207 行 |
| 实质变化回 controller 边界 | PASS | §7.3 第 207 行 + 第 226 行 |
| DS-RR-F02 未实施 | PASS | §14.2 未修改 |
| DS-RR-F03 未实施 | PASS | §11.3 未修改 |
| MIMO-RR-F01 未实施 | PASS | §10.4 未修改 |
| MIMO-RR-F02 未实施 | PASS | §18.1/§18.3/§22.1 未修改 |
| MIMO-RR-F03 未实施 | PASS | §13/§7.4 R06 行未修改 |
| CTL-PF-01—05 closure 仍成立 | PASS | 见 §5.1 逐项验证 |
| DS-PF-01—12 closure 仍成立 | PASS | 见 §5.2 逐项验证 |
| MIMO-PF-01—15 closure 仍成立 | PASS | 见 §5.3 逐项验证 |
| Topic 8 边界未漂移 | PASS | §3 第 66 行、§4 追踪表 |
| Topic 9 边界未漂移 | PASS | §3 第 67 行、§4 追踪表 |
| Issue 177 边界未漂移 | PASS | §3 第 72 行、§8.1/§8.4 |
| Issue 178 边界未漂移 | PASS | §3 第 72 行、§9.2 第 390 行 |
| Issue 175 边界未漂移 | PASS | §3 第 72 行、§12.4 第 640 行 |
| Issue 142/151 边界未漂移 | PASS | §3 第 69 行、§19.3 第 1029 行、§19.5 第 1077 行 |
| Web/WeChat/render tracker 边界未漂移 | PASS | §3 第 69 行、§18.2 第 925 行 |
| 架构边界（分层/依赖方向） | PASS | 无反向依赖，分层清晰 |
| 过度工程设计 | PASS | §25 六条自我检查成立 |
| 过度耦合 | PASS | R03/R06/R07 合并理由充分 |
| DS-RR-F01 fix 零架构影响 | PASS | 纯 plan governance 修改 |
