# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Re-Review — AgentDS

## Gate 身份

- **角色**：AgentDS，第二路独立完整 plan re-review；不是新 WU、feature、issue、implementation 或初轮 review。
- **Review target**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（经 AgentCodex plan-fix 修订后的全文，1265 行）。
- **Plan-fix evidence**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-fix-codex.md`。
- **Controller adjudication（唯一 disposition 真源）**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`。
- **产品裁决真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`。
- **设计真源**：`docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
- **流程真源**：`docs/host/issues-implementation-control.md`（当前 gate=`remediation plan re-review`）、`docs/phaseflow-umbrella-optimization-control.md`。
- **初轮 review（不上位替代本 re-review）**：AgentMiMo `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-mimo.md`、AgentDS `docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-ds.md`。
- **Review date**：2026-07-14
- **禁止动作**：不修改 plan/control/design/代码/测试/README；不 commit/push/PR。

## Review Method

1. 逐项核对 controller adjudication 的全部 accepted findings 是否在 plan-fix 中真实关闭。
2. 逐项核对 rejected/deferred/note findings 是否未被误实现。
3. 对完整最终计划执行 adversarial review（非仅修订 hunk），重点复核用户指定的 12 个 focus area。
4. 压测架构边界、状态机、sequencing、overcoupling、overengineering、test gaps。
5. 区分 true blockers、deferred risks、open questions。

## 1. Accepted Findings Closure — 逐项证据

### Controller findings (CTL-PF-01 至 CTL-PF-05)

| Finding | 裁决 | 关闭证据（plan 修订后位置） |
| --- | --- | --- |
| CTL-PF-01 | accepted / blocking | **已关闭**。§7.3（约第 186-227 行）完整状态机：plan→双plan review→controller adjudication→AgentCodex fix→双re-review→accepted plan commit→implementation→双code review→controller adjudication→fix→双re-review→accepted sub-WU commit。Artifact naming 模板（约第 207-219 行）、entry criteria（第 223-224 行）、completion signal（第 225 行）、stop condition（第 226 行）、handoff format（第 227 行）齐全。§0 明确"本文只拥有 R01—R12 的切分、顺序和全局不变量，不能替代任一 sub-WU 自己的 code-generation-ready plan"。 |
| CTL-PF-02 | accepted / blocking | **已关闭**。§7.3 第 203 行："每次 controller adjudication 把每个 finding 且只把它裁决为 `accepted`、`rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence`。AgentCodex 只修 `accepted`；任一 severity 均不得过滤。" §22.2 第 1168 行同样："任何 severity 的 accepted actionable finding都由AgentCodex回到对应owner/sub-WU修复"。§7.1 第 153 行也统一为"任何 severity"。全文无 severity 过滤残留。 |
| CTL-PF-03 | accepted / blocking | **已关闭**。§7.3 completion signal（第 225 行）："controller 创建只含本 sub-WU 授权文件的 accepted local commit"。§22.3（第 1170-1182 行）：明确 controller 在 accepted-plan、accepted-sub-WU、accepted-deepreview、accepted-PR-review gates 创建 local commit；criteria 满足后 push/open draft PR 无需再次询问；保留 ready/merge/approve/request reviewers/external comment/issue mutation/delete branch 禁令。 |
| CTL-PF-04 | accepted | **已关闭**。§6 第 145 行："所有 sub-WU 都在当前 `phaseflow/host-issues-control` 工作分支按 `R01 -> R02 -> ... -> R12` 串行推进；不得为 R01/R02/R03 或其它 sub-WU 创建独立实施分支，也不得通过 rebase 汇总"。独立分支/rebase 表述零残留。 |
| CTL-PF-05 | accepted | **已关闭**。§14.2（第 717-721 行）："算法、前缀、编码长度、revision grammar及是否需要某种 registry 都不是 umbrella contract，由 R07 独立子计划基于当前 storage layout 与直接代码证据决定"。§14.3（第 724-727 行）：只保留 storage 原子取得同版本 snapshot、bounded retry 可选、既有 typed `source_changed_during_read`、cache 不持有失效资源的不变量。全文无固定 hash/prefix/revision grammar、固定 retry 次数、新异常名或 cache lease 类名。 |

### AgentDS findings (DS-PF-01 至 DS-PF-12)

| Finding | 裁决 | 关闭证据 |
| --- | --- | --- |
| DS-PF-01 | accepted | **已关闭**。§18.1（第 908 行）要求 R11 子计划在 implementation 前确认真实 Windows runner/CI owner。§18.2（第 917-918 行）定义职责单一 Windows batch renderer：`setlocal DisableDelayedExpansion`、`%`/`!`/`&|^()` 元字符处理、引号/反斜杠/Unicode invariant、`list2cmdline` 明确不作为 batch quoting owner。§18.3（第 945-947 行）要求真实 `cmd.exe` recorder smoke 与真实 CLI grammar smoke；§22.1（第 1157 行）明确"缺少runner、workflow未触发、job skipped、artifact不可读或任一对抗字符失败都阻塞aggregate/PR/final closeout"。 |
| DS-PF-02 | accepted in part | **已关闭**（按裁决范围）。§14 已删除固定 hash/revision grammar、固定三次重试、新异常名、cache lease 类名；只保留 storage-owned 不变量。未保留 reviewer 建议中超出裁决的部分。 |
| DS-PF-03 | accepted in part | **已关闭**（按裁决范围）。§21（第 1110 行）新增平台 quoting 安全条目。§23（第 1211 行）Windows env 非跨资源原子性保留为 residual。未把 unsafe quoting 写成 residual。 |
| DS-PF-04 | accepted | **已关闭**。§10.4 R03-S2（第 486 行）："在修改前产出并在 R03 completion report 保存人工逐文件 source inventory。Inventory 必须枚举：`dayu/config/prompts/**` 的每个 prompt asset；所有 production ToolDefinition/tool schema…Host/Engine/Tool 中会进入 system/user/assistant/tool message…的 renderer；tests/smoke 中模拟真实 LLM 调用的 prompt/schema fixture；以及 R01 handoff 的 Doc LLM-facing 删除清单。" §10.5（第 511 行）："仅有 grep 零命中不得完成 R03"。 |
| DS-PF-05 | accepted | **已关闭**。§18.1（第 908 行）："R11 独立子计划在 implementation 前必须确认真实 Windows runner/CI owner、触发方式与 artifact 读取位置；若当前仓库仍无 runner，子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist并经双 plan review/controller接受"。§22.1（第 1157 行）："actual `cmd.exe` recorder与真实CLI grammar smoke可以在非Windows本地开发之后执行，但最迟必须在本 aggregate regression或随后的draft-PR check中成功"。 |
| DS-PF-06 | accepted | **已关闭**。§15.2（第 784 行）："provider raw `total`只允许保留在明确的 producer validation/diagnostic owner"；"不得在 public/tool schema/LLM文本同时暴露去重前 total、dedupe diagnostic与fact_count"。§15.3 R08-S2（第 810 行）要求三类验证：(1) 正向 scan 证明 raw `total` 只用于 provider 校验/诊断；(2) 反向 scan 证明 public/LLM 零残留；(3) owner-level test 断言 `fact_count == len(returned deduplicated facts)`。 |
| DS-PF-07 | rejected-with-reason | **未实现**（正确）。全文无 R05 publication fencing + R09 terminal validator 跨层组合场景。R05（§12）与 R09（§16）保持独立 owner。 |
| DS-PF-08 | accepted with stronger correction | **已关闭**。§6 第 145 行串行 accepted commits，§6 第 146 行："R01 completion report 的 Doc LLM-facing 删除/保留清单必须作为 R03 人工 source inventory 的显式输入，R03 不得回改 R01 owner 或重复发明删除规则"。 |
| DS-PF-09 | accepted | **已关闭**。§18.2（第 913 行）：annual=5、periodic=6 且仅最新年、presentation=6、call cap=recognized reports、`FINANCIAL_STATEMENTS` 无材料 cap、同期 `_pick_best_per_period` owner。OLD 直接证据精确到文件/行号。 |
| DS-PF-10 | note / no plan fix required | **未升级为 fix**（正确）。Plan §19.2 仍要求 R12 子计划第一步核对 current `models.json`，未复制 catalog snapshot。 |
| DS-PF-11 | accepted with correction | **已关闭**。§19.3（第 1024 行）："当前产品manifest只包含 `<workspace>/.dayu`（整个Dayu-owned Host/runtime/CLI/artifact/storage-state可重建根）与 `<workspace>/config`；当前package没有`dayu/assets`，本WU不得创建空`assets`、从OLD搬入assets，也不得把用户自行建立的`<workspace>/assets`视为Dayu-owned后删除。未来Issue151真正交付product-owned workspace assets时，由Issue151 owner把该root及其ownership证据加入同一managed-root manifest"。 |
| DS-PF-12 | note | **未升级为 fix**（正确）。正面检查结论保留，无新增 contract。 |

### AgentMiMo findings (MIMO-PF-01 至 MIMO-PF-15)

| Finding | 裁决 | 关闭证据 |
| --- | --- | --- |
| MIMO-PF-01 | accepted | **已关闭**。与 DS-PF-11 合并；§19.3 managed-root manifest 精确限定。 |
| MIMO-PF-02 | accepted | **已关闭**。与 DS-PF-01 合并；Windows batch renderer 覆盖 `%`/`!` 及 cmd 元字符。 |
| MIMO-PF-03 | accepted | **已关闭**。§11.2（第 526 行）："`WaitPollerRuntimePolicy` 的全部字段都是 required，不提供带部署数值的字段 default 或无参构造，Service/Host 不复制其中任何数值作为 fallback/default"。 |
| MIMO-PF-04 | rejected-with-reason | **未实现**（正确）。§10.5（第 512 行）保留 owner 不清时 stop 回 controller；未新增 credential fallback/特例脱敏/blacklist。 |
| MIMO-PF-05 | accepted | **已关闭**。§19.3（第 1030 行）："prewarm只在first/reset成功发布后运行一次"；"ordinary init与`--overwrite`都不prewarm；不得因overwrite使用packaged defaults而把它重分类为first"。 |
| MIMO-PF-06 | accepted | **已关闭**。§18.3（第 945-947 行）区分 recorder quoting smoke 与真实 `python -m dayu.cli -> Service/Fins -> temp storage` 端到端 smoke。 |
| MIMO-PF-07 | accepted / merged | **已关闭**。与 MIMO-PF-03 合并；§11.3 R04-S2（第 555 行）要求"命中与 policy 无关的内部常量时逐条记录 owner，不按数值字符串盲删"。 |
| MIMO-PF-08 | note | **未升级为 fix**。closed affected-module 正面结论保留。 |
| MIMO-PF-09 | note | **未升级为 fix**。retained/modified 安全矩阵正面结论保留。 |
| MIMO-PF-10 | note | **未升级为 fix**。Topic 8/9 与 Issue 142/151/175/177/178 边界保留。 |
| MIMO-PF-11 | note | **未升级为 fix**。12 sub-WU/30 slices 切分不变。 |
| MIMO-PF-12 | note | **未升级为 fix**。依赖图业务方向不变，仅按 controller 改为当前分支全串行。 |
| MIMO-PF-13 | note | **未升级为 fix**。R03 继续回到 prompt/tool schema/producer owner。 |
| MIMO-PF-14 | note，冲突由 controller 覆盖 | **未按 note 实现**。R07 按 controller CTL/DS 证据收窄，不保留 reviewer 建议的固定 retry/新类型。 |
| MIMO-PF-15 | note | **未升级为 fix**。验证框架正面结论保留。 |

### 13 项 plan-fix 闭集对照

Plan-fix artifact 声明的 13 项修复，逐项在修订后 plan 中验证：

| # | 声称状态 | 独立验证 |
| ---: | --- | --- |
| 1 | 已关闭 | **确认**。§0、§7.3、§22.2—22.4、§24 均已反映 per-sub-WU gate state machine。 |
| 2 | 已关闭 | **确认**。§6 第 145 行串行推进，独立分支/rebase 零残留。 |
| 3 | 已关闭 | **确认**。§7.1/§7.3/§22.2/§22.3 统一为所有 severity。 |
| 4 | 已关闭 | **确认**。§7.3/§22.2—22.3 controller local commit 与已授权 push/draft PR 边界。 |
| 5 | 已关闭 | **确认**。§18.1—18.4、§21、§22.1 Windows batch renderer 与 release blocker。 |
| 6 | 已关闭 | **确认**。§14.2—14.5 删除固定 hash/revision/retry/lease。 |
| 7 | 已关闭 | **确认**。§4、§19.3—19.5、§21/§23 managed-root manifest 与 prewarm。 |
| 8 | 已关闭 | **确认**。§11.2—11.4 `host_runtime.json` 唯一真源。 |
| 9 | 已关闭 | **确认**。§7.5、§8.5、§10.4—10.5 人工 inventory/audit。 |
| 10 | 已关闭 | **确认**。§7.5、§15.2—15.4、§22.1 internal raw total 与 public fact_count。 |
| 11 | 已关闭 | **确认**。§18.2—18.4 OLD 证据、两类 smoke。 |
| 12 | 已关闭 | **确认**。§18.1/§18.3、§22.1/§22.3 Windows runner release blocker。 |
| 13 | 已关闭 | **确认**。§6 第 145 行、§8.5、§10.4 R01→R03 handoff。 |

### Closure 结论

全部 5 个 controller finding、12 个 AgentDS finding、15 个 AgentMiMo finding 的 accepted/rejected/note 处置均与 controller adjudication 一致。Accepted findings 在修订后 plan 中有可定位的具体文本证据；rejected（DS-PF-07、MIMO-PF-04）未进入 plan；note（DS-PF-10/12、MIMO-PF-08 至 MIMO-PF-15）未被升级为实现要求。13 项 plan-fix 闭集全部可独立验证。

## 2. Focus Area 逐项复核

### 2.1 每个 R01—R12 独立完整 phaseflow gate

**复核结论**：通过。

§7.3（第 186-227 行）定义了不可跳过的 per-sub-WU 状态机：

```text
controller entry / previous accepted commit
  -> sub-WU code-generation-ready plan
  -> AgentMiMo + AgentDS 双路独立 plan review
  -> controller finding adjudication
  -> AgentCodex plan fix
  -> AgentMiMo + AgentDS 双路完整 plan re-review
  -> controller accepted-plan decision + accepted plan local commit
  -> implementation（按 approved slices 串行）
  -> AgentMiMo + AgentDS 双路独立完整 code review
  -> controller finding adjudication
  -> AgentCodex code fix
  -> AgentMiMo + AgentDS 双路完整 code re-review
  -> controller accepted-sub-WU decision + accepted sub-WU local commit
  -> handoff to next numbered sub-WU
```

验证点：
- Artifact naming 闭集明确（17 个 artifact 类型，含 `{mimo,ds}` 双份）。
- Entry criteria（第 223-224 行）：前一 accepted commit、当前分支、owner/文件/依赖可确定。
- Implementation entry criteria（第 224 行）：plan 已双 re-review、无 blocking question、accepted plan commit 存在。
- Completion signal（第 225 行）：全部 slice/test/coverage/pyright/diff/scan/README/smoke + 双路 code re-review。
- Stop condition（第 226 行）：owner 不清、design 冲突、越界 issue、中间 schema、retained security 失败、baseline 扩散、allowed files 外 diff、accepted finding 未闭合、Windows release blocker 未追踪。
- §0（第 8 行）明确："本文只拥有 R01—R12 的切分、顺序和全局不变量，不能替代任一 sub-WU 自己的 code-generation-ready plan"。

**未发现 gap**。

### 2.2 当前分支串行

**复核结论**：通过。

§6 第 145 行："所有 sub-WU 都在当前 `phaseflow/host-issues-control` 工作分支按 `R01 -> R02 -> ... -> R12` 串行推进；不得为 R01/R02/R03 或其它 sub-WU 创建独立实施分支，也不得通过 rebase 汇总。每个下一 sub-WU 都以前一 sub-WU 的 controller accepted local commit 为 base"。

§6 第 146 行进一步约束并发："唯一允许的并发是同一 immutable review target 上的 AgentMiMo / AgentDS 两路 reviewer"。

全文无独立分支、rebase、或并行 sub-WU 实施的残留表述。

**未发现 gap**。

### 2.3 Windows cmd.exe renderer / 真实 runner release blocker

**复核结论**：通过。本 focus area 是初轮 review 最高风险项，修订后 plan 处理充分。

关键文本：

- §18.1（第 908 行）：R11 子计划必须在 implementation 前确认真实 Windows runner/CI owner。
- §18.2（第 917-918 行）：Windows batch renderer 职责单一、平台专用。明确 `setlocal DisableDelayedExpansion`、`%`/`!` 字面量、`&|^()` 元字符拒绝、引号/反斜杠/Unicode invariant。`subprocess.list2cmdline` 明确不作为 batch quoting owner。
- §18.2（第 918 行）：renderer 必须证明脚本尾部追加参数的转发边界。
- §18.3（第 945 行）：recorder quoting smoke — POSIX `/bin/sh` + Windows `cmd.exe` 对抗矩阵。
- §18.3（第 946-947 行）：真实端到端 smoke — 生成脚本进入真实 `python -m dayu.cli` grammar。
- §22.1（第 1157 行）："R11 独立子计划必须在 implementation 前写明 Windows runner/CI owner；actual `cmd.exe` recorder与真实CLI grammar smoke可以在非Windows本地开发之后执行，但最迟必须在本 aggregate regression或随后的draft-PR check中成功。缺少runner、workflow未触发、job skipped、artifact不可读或任一对抗字符失败都阻塞aggregate/PR/final closeout；不得把unsafe quoting或未验证Windows行为列为residual。"
- §21（第 1110 行）：安全清单中 Windows 条目明确"不以`list2cmdline`代签batch quoting"。

**未发现 gap**。Windows closure 路径明确：R11 子计划 plan 必须写明 runner owner → 本地 renderer unit tests → POSIX 两类 smoke 先行 → 真实 `cmd.exe` recorder + CLI grammar smoke 最迟 aggregate/PR 通过。任何缺失都是 release blocker，不能降级为 residual。

### 2.4 R07 无 speculative algorithm/type/retry contract

**复核结论**：通过。

§14.2（第 717-721 行）："算法、前缀、编码长度、revision grammar及是否需要某种 registry 都不是 umbrella contract，由 R07 独立子计划基于当前 storage layout 与直接代码证据决定。不得让 repository、read consumer、CLI或测试 fixture各自实现第二套映射。"

§14.3（第 724-727 行）："具体 revision 编码、前缀和生成算法由 R07 独立子计划基于 storage layout决定，不是业务/public/LLM contract"；"实现可以在 storage 内做有界重试，但 retry 次数、snapshot API/类型名、copy/digest策略和资源生命周期形态都由 R07 子计划基于代码证据决定，不在 umbrella 计划固定"；"cache…如何表达 cache entry、resource handle或关闭责任由 R07 子计划决定；本文不固定任何 lease、context manager或cache class形态"。

全文搜索确认无固定 hash（如 `sha256`、`ticker_`、`doc_` 前缀）、无固定 retry 次数（如 `3`、`_MAX_ATTEMPTS`）、无新异常类名、无 cache lease 类名或具体 context manager 形态。

**未发现 gap**。

### 2.5 R03 人工 source inventory

**复核结论**：通过。

§10.4 R03-S2（第 486-487 行）明确 inventory 必须枚举：
- `dayu/config/prompts/**` 的每个 prompt asset
- 所有 production ToolDefinition/tool schema 的 name、description、参数、枚举和错误说明
- Host/Engine/Tool 中会进入 system/user/assistant/tool message、Memory、Compact、Trace、Evidence 的 renderer
- tests/smoke 中模拟真实 LLM 调用的 prompt/schema fixture
- R01 handoff 的 Doc LLM-facing 删除清单

每项记录：文件、具体 source、是否 LLM-facing、语义 owner、`compliant | modify-at-owner | not-LLM-facing-with-evidence` disposition 与验证证据。

§10.5（第 511 行）："completion report 必须附完整 inventory、逐项 disposition、R01 handoff消费记录、实际 owner 修改清单和全部自动门禁结果；仅有 grep 零命中不得完成 R03。"

§10.5（第 512 行）stop condition："若任一现有 tool schema确实要求 LLM 提交 credential 且无法在该 tool owner内迁移到 config，owner 已不清晰，立即 stop 回 controller"。

**未发现 gap**。但有一个 scheduling note（见 NEW-F02）。

### 2.6 R04 配置唯一 owner

**复核结论**：通过。

§11.2（第 526 行）："`host_runtime.json`…该 JSON snapshot 是所有部署 policy 数值的唯一真源；`WaitPollerRuntimePolicy` 的全部字段都是 required，不提供带部署数值的字段 default 或无参构造，Service/Host 不复制其中任何数值作为 fallback/default。所有字段由 ConfigLoader 的完整 typed snapshot 显式构造并严格 finite/positive 校验。"

§11.3 R04-S2（第 552-553 行）："删除 `WaitPollerRuntimePolicy()` 无参路径及 dataclass 上所有 deployment-value defaults；Service/Host 生产代码只能接收 ConfigLoader 已校验的完整 snapshot，不得以模块常量、helper default、factory fallback 或测试 fixture复制部署值。与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 `wait_poller_policy`；当前承载同一部署语义的 30/5/8 等模块常量必须删除。"

§11.3 R04-S3（第 562 行）：删除 `with_entrypoint_wait_poller_policy` 及 scene 自动启用路径。

**未发现 gap**。但有一个 classification boundary note（见 NEW-F03）。

### 2.7 R08 raw total / public count

**复核结论**：通过。

§15.2（第 784 行）："provider raw `total`只允许保留在明确的 producer validation/diagnostic owner，用于核验 provider 响应，不是 public或LLM业务事实。read projection可以清洗/去重 raw facts，但必须生成一个独立的 public typed result，输出 deduplicated `facts` 与唯一 `fact_count = len(deduplicated facts)`；不得覆盖processor raw facts后把重算值冒充producer事实，也不得在 public/tool schema/LLM文本同时暴露去重前 total、dedupe diagnostic与fact_count。"

§15.3 R08-S2（第 810 行）要求三类独立验证：
1. 限定 internal processor/diagnostic 类型的正向 scan，逐条证明 raw `total` 只用于 provider 校验/诊断。
2. 限定 public result/tool schema/serializer/LLM renderer 的反向 scan，证明 `raw_total|deduped_fact_count|去重前total` 零残留且只有 `fact_count`。
3. Owner-level test 断言 `fact_count == len(returned deduplicated facts)`。

§7.5 R08-S2 scan（第 274 行）对齐：`public/LLM `statement_locator|raw_total|deduped_fact_count|去重前total`零残留；`fact_count == len(deduplicated facts)`且唯一`。

§22.1 aggregate scan（第 1137 行）包含限定 internal 的正向 scan（`\btotal\b|raw_total` 只在 `xbrl_result_contract.py` 和 `processors`）以及限定 public 的反向 scan（`raw_total|deduped_count` 只在 `fins/tools` 和 `fins/domain`）。

**未发现 gap**。

### 2.8 R11 OLD 分类和两类 smoke

**复核结论**：通过。

分类规则（§18.2 第 913 行）：
- OLD 直接证据：`/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py:120-125,371-458` 与 `cli_support.py:1520-1544`
- annual 最多 5；periodic 只保留最新 fiscal year 且最多 6；presentation 最多 6
- call cap = recognized report 数量
- `FINANCIAL_STATEMENTS` 不在 material cap map 中，无材料数量 cap
- 同一 `(fiscal_year, fiscal_period)` 由 Fins-owned `_pick_best_per_period` 优先级规则选唯一主报告

两类 smoke（§18.3 第 945-947 行）：
1. **Recorder quoting smoke**：POSIX `/bin/sh` + Windows `cmd.exe` 执行生成脚本，受控 recorder 只记录最终 argv，与 typed plan exact 比对。对抗矩阵覆盖空格、Unicode、单双引号、连续/尾随反斜杠、`%`、`!`、`&|^()`。
2. **真实端到端 smoke**：生成脚本真实进入 `python -m dayu.cli upload_filing|upload_material` parser、Service/Fins direct path 与临时 storage。Windows runner 至少真实进入同一 CLI grammar。

§18.3（第 947 行）明确："非Windows开发机可以先运行 renderer unit tests和POSIX两类 smoke，但不能宣称 Windows closure。"

**未发现 gap**。

### 2.9 R12 assets/reset/prewarm

**复核结论**：通过。

§19.3（第 1024 行）managed-root manifest：
- 当前只含 `<workspace>/.dayu` 与 `<workspace>/config`
- 当前 package 没有 `dayu/assets`，本 WU 不创建空 `assets`、不从 OLD 搬入 assets
- 用户自建 `assets` 不被视为 Dayu-owned 后删除
- 未来 Issue 151 交付时由该 owner 加入同一 manifest

§19.3（第 1025 行）reset confirmation：默认 No；`portfolio` 永不删除。

§19.3（第 1030 行）prewarm："只在first/reset成功发布后运行一次：加载 ConfigLoader、prompt/interactive/session assembly、Fins processor registry，不发真实LLM/HTTP请求。ordinary init与`--overwrite`都不prewarm；不得因overwrite使用packaged defaults而把它重分类为first。"

§19.5（第 1072 行）：用户自建 `<workspace>/assets` 不因名称命中而删除。

**未发现 gap**。

### 2.10 Topic 8/9 与 Issue 142/151/175/177/178 边界

**复核结论**：通过。

§3 非目标明确列出：
- Topic 8：保留 Engine 240 字符异常消息策略，不改配置、不新增 durable full-detail ref。
- Topic 9：不设计或实现统一 tool authorization framework。
- 不实施 Issue 142、151、175、177、178。
- 不为旧 schema/路径/测试加兼容读取。

§4 追踪表标记每个 deferred issue 的 owner/destination。
§23 residual risk 表为每个 deferred issue 指定 owner/destination。
§25（第 1255 行）self-check："只计划 controller 已接受的 Topic 1—7，不把 review建议或未来issue自动升级成实现"。
Plan-fix artifact §"Scope 与越界自审"（第 96-101 行）确认 Topic 8/9 与所有 deferred issue 未被实现。

全文搜索确认无 Issue 142/151/175/177/178 的实现指令、无 Topic 8 修改指令、无 Topic 9 框架设计指令。

**未发现 gap**。

## 3. 新 Findings

### NEW-F01 — 中 — Umbrella plan 的 per-slice 具体性与 sub-WU plan 独立性之间存在 contract tension

- **位置**：§7.5（per-slice verification substitution matrix，第 248-283 行）与 §8—§19（每个 Rxx 的 slice 定义与 exact 命令）对比 §7.3（"本文不是 R01—R12 任一 sub-WU 的 plan artifact"）。
- **问题类型**：架构边界 / 不可直接实施
- **当前写法**：Umbrella plan §7.5 为每个 slice 指定了 exact `pytest -k` 命令、exact `coverage --include` 模式、exact `rg` scan 模式、README decision 要求。§8—§19 为每个 Rxx 指定了 exact slice 边界、exact 测试命令、exact smoke 描述。同时 §7.3 声明"每个 sub-WU 都必须独立、完整、不可折叠地执行…plan gate"，且 umbrella plan "不能替代任一 sub-WU 自己的 code-generation-ready plan"。
- **反例/失败场景**：R07 sub-WU plan 发现 storage layout 需要不同的 slice 切分（例如 mapping 和 revision 必须在同一 slice 才能保持原子性），或者不同的测试命令（例如现有测试文件命名与 umbrella plan 假定的 `-k` 模式不匹配）。如果 sub-WU plan 不能偏离 umbrella plan 的 slice/命令，则 sub-WU plan 不是真正的 "code-generation-ready plan"。如果 sub-WU plan 可以偏离，则 umbrella plan 的 exact 命令（如 `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py -k 'path or identifier or containment or symlink or unicode or document_id or ticker'`）是不必要的具体性，可能误导 implementation agent。
- **为什么有问题**：违反了"umbrella plan 只拥有切分、顺序和全局不变量"的自我声明。§7.5 和 §8—§19 的 exact 命令已经进入 sub-WU plan 的职责范围。
- **直接证据**：§7.5 表为 R07-S1 指定 exact 命令 `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_storage_atomicity.py -k 'path or identifier or containment or symlink or unicode or document_id or ticker'`，同时 §7.3 说 umbrella plan 不替代 sub-WU plan。§14.4 R07-S1 也写了完全相同的命令。
- **影响**：实施 Agent 在编写 sub-WU plan 时可能因为 umbrella plan 的 exact 命令而放弃基于代码证据的独立判断（blindly copy）；或者在 sub-WU plan 中偏离 umbrella plan 导致两处命令不一致（confusion）。
- **建议改法和验证点**：在 umbrella plan §7.5 和每个 Rxx slice 的命令前增加明确声明："以下命令是 umbrella 基于当前代码证据的建议起点；sub-WU plan 必须基于实际代码状态独立确定 exact 命令并记录差异理由。" 或者在 §7.3 的 plan entry criteria 中增加："sub-WU plan 的 slice 边界、测试命令和 scan 模式以 sub-WU plan 自身为真源；umbrella plan 的 per-slice 命令仅作参考。"
- **修复风险**：低（仅文档澄清）。
- **严重程度**：中。

### NEW-F02 — 低 — R07 fresh-schema 对现有 storage 数据的影响未明确声明

- **位置**：§14.2（第 720 行）。
- **问题类型**：契约缺失
- **当前写法**："fresh schema直接使用新布局，不兼容旧布局、不迁移旧库。"
- **反例/失败场景**：现有开发/测试环境中有通过旧布局写入的 storage 数据。R07 实施后，新 layout 的 key mapping 与旧 layout 的 raw path component 不兼容。如果未提前声明旧数据不可访问，开发者在 R07 实施后遇到 "file not found" 会误认为是 regression。
- **为什么有问题**："不兼容旧布局、不迁移旧库" 是项目全局规则（AGENTS.md schema 变更节），但在 R07 的上下文中，storage layout 变更直接影响本地开发数据和测试 fixture。plan 未明确声明：R07 实施后旧 storage 数据不可读，开发者需重新 ingestion 或使用 fresh workspace。
- **直接证据**：§14.2 第 720 行 "fresh schema直接使用新布局，不兼容旧布局、不迁移旧库"。§14.5 smoke 只描述了 "filesystem并发 smoke：writer持续原子发布"，未描述旧数据不可访问的预期行为。
- **影响**：实施后开发环境 confusion；可能被误报为 regression bug。
- **建议改法和验证点**：在 §14.2 或 §14.5 增加一句："R07 实施后，按旧 layout 写入的 storage 数据不可通过新 key mapping 读取；开发者需使用 fresh workspace 或重新 ingestion。这不是 regression，是 fresh-schema 预期行为。"
- **修复风险**：低（仅文档澄清）。
- **严重程度**：低。

### NEW-F03 — 低 — R04 "deployment-value 常量" 与 "内部算法常量" 的区分标准未提供

- **位置**：§11.3 R04-S2（第 552-553 行）。
- **问题类型**：不可直接实施
- **当前写法**："当前承载同一部署语义的 30/5/8 等模块常量必须删除"；"与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 `wait_poller_policy`"。
- **反例/失败场景**：代码中有一个常数 `_DEFAULT_THREAD_JOIN_TIMEOUT = 5`（与 `close_drain_timeout_seconds=5` 数值相同但语义不同），或 `_MAX_BACKOFF_MULTIPLIER = 2`（与 `backoff_multiplier=2` 数值相同但语义不同）。实施 agent 按数值字符串匹配删除，导致内部算法常量被误删；或者保守地保留所有常量，导致部署语义常量未清理。
- **为什么有问题**：plan 提供了判断原则（"语义不属于 `wait_poller_policy`"）但没有提供可操作的区分标准。`30/5/8` 是已知的明确目标，但代码中可能存在其他数值相等的常量。
- **直接证据**：§11.3 R04-S2 第 555 行 "命中与 policy 无关的内部常量时逐条记录 owner，不按数值字符串盲删"。这条规则本身正确，但判断"是否与 policy 无关"的标准需要 sub-WU plan 补充。
- **影响**：实施 agent 在 R04 sub-WU plan 中需要自行设计区分标准；如果标准不充分，可能误删或漏删。
- **建议改法和验证点**：在 R04 sub-WU plan 中要求：列出 `WaitPollerRuntimePolicy` 全部字段名作为基准；代码中任何数值常量如果其唯一用途是提供 policy 字段的默认值、覆盖值或替代值，属于 deployment-value 常量应删除；如果常量的注释、类型、调用上下文证明其服务于独立算法逻辑（如 thread join、backoff cap calculation），属于内部常量可保留。该分类必须在 R04 sub-WU plan 中完成并进入双路 plan review。
- **修复风险**：低（sub-WU plan 可解决）。
- **严重程度**：低。

## 4. 架构边界与过度工程检查

### 4.1 分层边界

Plan 中 R01—R12 的 owner 分配遵守 `UI -> Service -> Host -> Engine` 分层：
- R01/R02: Tool 层（Doc/Web 配置与执行）
- R03/R04/R05: Host 层（projection、composition、wait state machine）
- R06—R10: Fins 层（storage transaction、snapshot、domain contract、validator、provider）
- R11/R12: UI/CLI 层（script renderer、init workflow）

无反向依赖。R05→Engine 只允许 regression tests，不允许修改 `agent.py`（除非"真实证据表明 accepted awaiting仍被二次计时"）。R09→Service/CLI 严格只消费已验证 stream。

**通过**。

### 4.2 过度工程设计

§25 自我检查成立：
- 只计划 controller 已接受的 Topic 1—7。
- 12 sub-WU 按唯一 owner/durable blast radius/可独立回滚切分。
- 最多 3 slices/sub-WU。
- 无 god object/factory/bag/builder。
- 无 speculative 通用框架（Topic 9、Issue 175/177/178 均为 deferred）。
- R07 retry/hash/revision/lease 细节留给子计划基于代码证据决定。

**通过**。

### 4.3 过度耦合检查

- R03 合并 Topic 3/4 是因为共享 accepted-evidence projection 和四个 downstream consumers；拆开会产生中间态（opaque ref 暴露给新参数投影），理由充分。
- R06 合并 batch authority 与 source publication 是因为 transaction commit point 与 source 可见点必须同时切换，理由充分。
- R07 合并 revision/snapshot 与 opaque ID mapping 是因为共同改变 storage path/read snapshot layout，理由充分。
- 其他 sub-WU 均无不当合并。

**通过**。

### 4.4 状态机完整性

- R01: source snapshot `new -> active -> closed`。
- R05: wait observation `WAITING(due) -> claim -> observe -> resolved/not-ready/fatal/timeout(release/backoff, remain WAITING, never LOST)`。
- R06: transaction `begin -> mutations -> commit/rollback -> published/rolled-back`。
- R09: direct stream `OPEN -> progress*/RESULT_BUFFERED -> CLOSED`。
- R12: init `PARSE -> lock -> validate -> staging -> swap/rollback -> prewarm -> release`。

所有状态机均有显式状态集合、transition、error/failure path、幂等/cleanup 语义。

**通过**。

## 5. Sequencing 与依赖完整性

§6 依赖图：

```text
R01 ───────────────────────────────────────────────────┐
R02 ───────────────────────────────────────────────────┤
R03 ───────────────────────────────────────────────────┤
R04 ──> R05                                            │
R06 ──> R07 ──> R08                                    │
     ├───────> R09                                     │
     └───────> R10                                     │
R06 ──> R11 ───────────────────────────────────────────┤
R08/R09/R11 ───────────────────────────────────────────> R12
all R01-R12 ──> aggregate tests ──> aggregate deepreview ──> PR gates ──> final closeout
```

验证：
- R04→R05：config contract 必须先于 behavior 变更（正确）。
- R06→R07→R08→R09/R10：storage transaction 先建立唯一 commit point，snapshot/read 才能消费，domain contract 才能收敛（正确）。
- R06→R11：upload batch plan 需要 final transaction contract（正确）。
- R01 handoff → R03：§6 第 146 行明确 "R01 completion report 的 Doc LLM-facing 删除/保留清单必须作为 R03 人工 source inventory 的显式输入"。

**通过**。有一个 minor note：R01→R03 的数据依赖未在 ASCII 图中以箭头表示（图中 R01/R02/R03 三条独立线只是 ──┐ 汇聚），但 prose 已明确。不影响正确性。

## 6. Test Gaps 与验证覆盖

### 6.1 每个 sub-WU 的测试策略

每个 Rxx 均有：
- Targeted tests（exact `pytest` 命令）
- Changed-file coverage（`>=80%` per file）
- 全量 pyright
- `git diff --check` + allowed-file scan
- LLM/source/security propagation scan
- 真实 smoke（描述具体场景与通过信号）

### 6.2 Aggregate 验证

§22.1 定义 aggregate regression 命令、aggregate scans（6 条 `rg` 命令）和真实 smoke 矩阵（11 行）。

### 6.3 潜在覆盖缺口

- **R07 smoke 的并发 race 注入**：§14.5 "writer持续原子发布两个明显不同版本，reader多轮读取"，但未说明如何注入并发 race（如 `time.sleep`、file lock hold）。这是 sub-WU plan 的细节，umbrella plan 层面不构成 gap。
- **R12 Windows CI smoke**：§19.4 R12-S3 "Windows CI运行同样current-schema加载、user env writer mock/isolated process、atomic tree和R11 `.cmd` smoke"。如果 Windows CI 不存在（§18.1 承认当前仓库无 runner），R12 smoke 的 Windows 部分与 R11 面临相同的 runner dependency。plan 已将 R11 Windows runner 作为 release blocker，R12 Windows CI smoke 自然也被同一条件阻塞。可接受。

**通过**，无 material test gap。

## 7. Open Questions

1. **R07 sub-WU plan 的算法选择自由度**：Umbrella plan §14.2 说算法"由 R07 独立子计划基于当前 storage layout 与直接代码证据决定"，又说"不得让 repository、read consumer、CLI或测试 fixture各自实现第二套映射"。如果 R07 sub-WU plan 选择的算法在后续 aggregate deepreview 中被认为引入了新的 overdesign，回滚成本是多少？（这属于 sub-WU plan review 的职责，不是 umbrella plan 的 blocking question。）

2. **R11 Windows runner 的最晚完成时间**：§22.1 说"最迟必须在本 aggregate regression或随后的draft-PR check中成功"。如果 R01—R10 已完成但 R11 Windows smoke 仍因 runner 不可用而阻塞，整个 umbrella 会停在 aggregate gate。是否有 fallback 策略（如先完成 POSIX closure 并标记 Windows 为 known-blocked，单独追踪）？（Controller 已明确"不得把unsafe quoting或未验证Windows行为列为residual"，所以这是 conscious decision，不是 gap。）

## 8. Residual Risks（未在 plan §23 中列出，但本 re-review 识别）

无新增 material residual risk。§23 已覆盖 7 项 residual risk，均有 owner/destination。

## 9. Final Verdict

**PASS-WITH-RISKS**

### 通过理由

1. **全部 accepted findings 已关闭**：5 个 CTL finding、12 个 DS finding、15 个 MiMo finding 的 accepted/rejected/note 处置与 controller adjudication 完全一致，每个 closure 在修订后 plan 中有可定位的文本证据。
2. **全部 rejected/deferred/note 未被误实现**：DS-PF-07（rejected）、MIMO-PF-04（rejected）未进入 plan；DS-PF-10/12、MIMO-PF-08 至 MIMO-PF-15（note）未被升级为实现要求。
3. **10 个 focus area 全部通过逐项复核**：per-sub-WU gate、串行分支、Windows cmd.exe renderer/release blocker、R07 无 speculative contract、R03 人工 inventory、R04 配置唯一 owner、R08 raw total/public count、R11 OLD 分类与两类 smoke、R12 assets/reset/prewarm、Topic 8/9 与 Issue 边界。
4. **架构边界、过度工程、过度耦合、状态机完整性**检查通过。
5. **Sequencing 与依赖**完整且合理。
6. **13 项 plan-fix 闭集**全部可独立验证。

### Risks

1. **NEW-F01（中）**：Umbrella plan per-slice exact 命令与 sub-WU plan 独立性的 tension。建议在 §7.3 或 §7.5 增加 umbrella 命令仅作参考起点的声明。
2. **NEW-F02（低）**：R07 fresh-schema 对现有 storage 数据影响的声明缺失。
3. **NEW-F03（低）**：R04 deployment-value vs internal-constant 区分标准需 sub-WU plan 补充。

三个 risk 均不阻塞 plan 进入 re-review closure；可在 controller adjudication 中决定是否在 umbrella plan 内修复（澄清措辞）或委托给对应 sub-WU plan。

### Blocking Questions

无。Plan 可进入 controller adjudication 与双路 re-review closure。

## 10. 逐项证据清单（即使 pass）

| 检查项 | 结果 | 关键证据位置 |
| --- | --- | --- |
| CTL-PF-01 per-sub-WU gate state machine | PASS | §7.3 第 186-227 行 |
| CTL-PF-02 所有 severity accepted finding 修复 | PASS | §7.3 第 203 行、§22.2 第 1168 行 |
| CTL-PF-03 controller local commit 与 PR 授权 | PASS | §7.3 第 225 行、§22.3 第 1170-1182 行 |
| CTL-PF-04 当前分支串行 | PASS | §6 第 145 行 |
| CTL-PF-05 R07 无 speculative contract | PASS | §14.2—14.5 |
| DS-PF-01 Windows batch renderer | PASS | §18.1—18.4、§21、§22.1 |
| DS-PF-02 R07 收窄 | PASS | §14 全文 |
| DS-PF-03 平台 quoting 安全矩阵 | PASS | §21 第 1110 行、§23 第 1211 行 |
| DS-PF-04 人工 source inventory | PASS | §10.4—10.5 |
| DS-PF-05 Windows runner release blocker | PASS | §18.1、§22.1 |
| DS-PF-06 R08 raw total/public count | PASS | §15.2—15.4、§7.5、§22.1 |
| DS-PF-07 rejected — 未实现 | PASS | 全文无跨层 R05+R09 组合 |
| DS-PF-08 R01→R03 handoff | PASS | §6 第 146 行、§8.5、§10.4 |
| DS-PF-09 OLD 分类规则 | PASS | §18.2 第 913 行 |
| DS-PF-10 note — 未升级 | PASS | §19.2 保留 catalog 核对要求 |
| DS-PF-11 assets/reset 语义 | PASS | §19.3 第 1024-1025 行 |
| DS-PF-12 note — 未升级 | PASS | 无新增 contract |
| MIMO-PF-01 至 MIMO-PF-15 | PASS | 见 §1 逐项证据表 |
| 13 plan-fix items | PASS | 见 §1 逐项验证 |
| Focus: per-sub-WU gate | PASS | §2.1 |
| Focus: 串行分支 | PASS | §2.2 |
| Focus: Windows cmd.exe | PASS | §2.3 |
| Focus: R07 no speculative | PASS | §2.4 |
| Focus: R03 inventory | PASS | §2.5 |
| Focus: R04 config owner | PASS | §2.6 |
| Focus: R08 raw/public | PASS | §2.7 |
| Focus: R11 OLD + smokes | PASS | §2.8 |
| Focus: R12 assets/prewarm | PASS | §2.9 |
| Focus: Topic 8/9 + Issues | PASS | §2.10 |
| Architecture boundaries | PASS | §4.1 |
| Overengineering | PASS | §4.2 |
| Overcoupling | PASS | §4.3 |
| State machines | PASS | §4.4 |
| Sequencing/dependencies | PASS | §5 |
| Test coverage | PASS | §6 |
