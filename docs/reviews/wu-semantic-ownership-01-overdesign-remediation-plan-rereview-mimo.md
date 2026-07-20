# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Re-Review — AgentMiMo

## Gate 身份与范围

- **角色**：AgentMiMo，既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 remediation 总计划双路 re-review 第一路；不是新 WU、不是 implementation、不是 code review。
- **审查对象**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（plan-fix 后全文，非修订 hunk）。
- **finding disposition 真源**：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-controller-adjudication.md`。初轮 MiMo/DS 原始 severity、verdict 与建议只提供证据，不能覆盖 controller 裁决。
- **证据范围**：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`；plan-fix HEAD `01bbf74c`。
- **完整阅读材料**：AGENTS.md、`docs/phaseflow-umbrella-optimization-control.md`、`docs/host/issues-implementation-control.md`、`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`、五份 design truth review、`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`、初轮 MiMo review、初轮 DS review、controller adjudication、plan-fix codex artifact。
- **输出边界**：仅新增本 artifact；不修改 plan/control/design/代码/测试/README；不 commit/push/PR。

## 审查方法

1. 以 controller adjudication 为 finding disposition 真源，逐项检查全部 accepted findings 是否在修订后 plan 中真实关闭。
2. 逐项检查 rejected/deferred/note findings 是否未被误实现。
3. 对修订后完整最终计划执行 adversarial review（非只看修订 hunk）。
4. 重点复核：每个 R01-R12 独立完整 phaseflow gate、当前分支串行、Windows cmd.exe renderer/真实 runner release blocker、R07 无 speculative algorithm/type/retry contract、R03 人工 source inventory、R04 配置唯一 owner、R08 raw total/public count、R11 OLD 分类和两类 smoke、R12 assets/reset/prewarm、Topic 8/9 与 Issue 142/151/175/177/178 边界。

---

## 一、旧 Findings Closure 检查

### AgentDS Findings（以 controller adjudication 为 disposition 真源）

| Finding | Controller Disposition | Plan 修订位置 | Closure 验证 |
| --- | --- | --- | --- |
| DS-PF-01 | accepted | §18.2 行 917-918、§21 行 1110、§22.1 行 1157 | **已关闭**。Plan 明确 `DisableDelayedExpansion`、`%`→`%%`、`&|^()` escaping、Unicode invariant；明确 `list2cmdline` 不是 batch quoting owner；真实 cmd.exe recorder/CLI grammar 为 release blocker。不把 unsafe quoting 列为 residual。 |
| DS-PF-02 | accepted in part | §14.2-14.3 行 718-727 | **已关闭**。删除固定 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS=3`、`SourceSnapshotChangedError`、`_CachedProcessor` lease 名称和具体生命周期；只保留 storage-owned 同版本 snapshot/revision/identity、bounded retry 可选、既有 typed `source_changed_during_read`、cache 不持有失效资源。storage-owned 方向保留。 |
| DS-PF-03 | accepted in part | §21 行 1110 | **已关闭**。Plan §21 新增 Windows `cmd.exe` batch quoting 安全矩阵条目。Windows env/config 非全局原子 residual 继续保留。拒绝把 unsafe quoting 写成 residual。 |
| DS-PF-04 | accepted | §10.4 R03-S2 行 486-487 | **已关闭**。Plan 要求人工逐文件 source inventory/audit、逐项 disposition 和 completion evidence；grep 降为自动门禁。 |
| DS-PF-05 | accepted | §18.1 行 908、§18.3 行 947、§22.1 行 1157 | **已关闭**。R11 子计划 implementation 前必须确认真实 Windows runner/CI owner；actual cmd.exe check 最迟 aggregate/PR 通过；缺 runner/skip/failure 不得 final closeout。 |
| DS-PF-06 | accepted | §15.2 行 783-784、§15.3 R08-S2 行 810-811 | **已关闭**。internal provider validation/diagnostic 可保留 raw `total`；public/tool/LLM 只允许 `fact_count == len(deduplicated facts)`；正反扫描与 owner-level test。 |
| DS-PF-07 | rejected-with-reason | 未实现 | **未误实现**。R05 publication fencing 与 R09 terminal validator 继续是独立 owner；未新增组合场景或跨层错误 identity。 |
| DS-PF-08 | accepted with stronger correction | §6 行 145、§7.3 行 186-200、§8.5 行 347 | **已关闭**。删除独立分支/rebase，改为当前分支串行 accepted commits；R01 清单显式 handoff 到 R03。 |
| DS-PF-09 | accepted | §18.2 行 913 | **已关闭**。补 OLD 精确证据：annual=5、periodic=6（仅最新年）、presentation=6、call cap=recognized reports、`FINANCIAL_STATEMENTS` 无材料 cap、同期 `_pick_best_per_period` owner。 |
| DS-PF-10 | note / no plan fix required | 未升级为 fix | **未误实现**。R12 子计划第一步核对 current `models.json` 的既有要求保留。 |
| DS-PF-11 | accepted with correction | §19.3 行 1024-1026 | **已关闭**。current-manifest 仅 `.dayu` 与 `config`；当前 package 无 `dayu/assets`、不创建/搬入 assets、不删除用户自建 assets；Issue 151 才能扩展同一 manifest；portfolio 永不删除。 |
| DS-PF-12 | note | 未修改 | **未误实现**。正面检查结论保留。 |

### AgentMiMo Findings（以 controller adjudication 为 disposition 真源）

| Finding | Controller Disposition | Plan 修订位置 | Closure 验证 |
| --- | --- | --- | --- |
| MIMO-PF-01 | accepted（与 DS-PF-11 合并） | §19.3 行 1024-1026 | **已关闭**。按"当前产品实际拥有的 assets"精确修正。 |
| MIMO-PF-02 | accepted（与 DS-PF-01 合并） | §18.2 行 917-918 | **已关闭**。`%`、`!` 及 cmd 元字符风险全部进入真实 renderer/smoke gate，不作 residual。 |
| MIMO-PF-03 | accepted | §11.2 行 526 | **已关闭**。删除 typed policy deployment defaults 与无参构造语义。`host_runtime.json` 是所有部署 policy 数值唯一真源。 |
| MIMO-PF-04 | rejected-with-reason | 未实现 | **未误实现**。Plan §10.4-10.5 只保留 owner 不清时 stop 回 controller，并补完整 source audit。未新增 credential fallback/特例脱敏。 |
| MIMO-PF-05 | accepted | §19.3 行 1030 | **已关闭**。明确 first/reset 各一次，ordinary/overwrite 零 prewarm；删除"除非 controller design 明确写入"条件性歧义。 |
| MIMO-PF-06 | accepted | §18.3 行 945-947 | **已关闭**。recorder quoting smoke 与真实 `python -m dayu.cli -> Service/Fins -> temp storage` 端到端 smoke 分开。 |
| MIMO-PF-07 | accepted/merged（与 MIMO-PF-03 合并） | §11.2 行 526 | **已关闭**。deployment 数值只来自 `host_runtime.json`，非 policy 内部常量逐条归属。 |
| MIMO-PF-08—15 | notes | 未修改 | **未误实现**。正面结论保留。MIMO-PF-14 与 controller 冲突处由 controller 覆盖。 |

### Controller Findings

| Finding | Disposition | Plan 修订位置 | Closure 验证 |
| --- | --- | --- | --- |
| CTL-PF-01 | accepted/blocking | §7.3 行 186-227 | **已关闭**。每个 R01-R12 独立完整 gate state machine、artifact naming（花括号 `{mimo,ds}` 表示两份独立文件）、entry/exit criteria、accepted commit 规则。 |
| CTL-PF-02 | accepted/blocking | §7.1 行 159、§22.2 行 1168 | **已关闭**。所有 severity 的 controller-accepted actionable finding 均进入 fix + 双 re-review；rejected/deferred/note 不进入 fix。 |
| CTL-PF-03 | accepted/blocking | §7.3 行 225-227、§22.3 行 1172-1182 | **已关闭**。controller 在 accepted-plan/accepted-sub-WU/accepted-deepreview/accepted-PR-review gates 创建 local commit；criteria 满足后 push/open draft PR 无需再次询问；保留未授权外部动作禁令。 |
| CTL-PF-04 | accepted | §6 行 145 | **已关闭**。固定当前 `phaseflow/host-issues-control` 按 R01→R12 串行 accepted commits；删除独立实施分支/rebase 方案。 |
| CTL-PF-05 | accepted | §14.2-14.3 行 718-727 | **已关闭**。删除固定 identity hash/prefix/revision/registry 形态，只保留 storage mapping/round-trip/containment/fail-closed invariant。 |

**旧 findings closure 结论**：全部 5 个 controller findings、12 个 DS findings、15 个 MiMo findings 均已按 controller disposition 真实关闭或正确保留。2 个 rejected findings（DS-PF-07、MIMO-PF-04）未被误实现。全部 notes 未被升级为实现要求。

---

## 二、重点维度逐项复核

### 2.1 R01-R12 独立完整 phaseflow Gate

Plan §7.3 行 186-227 定义了完整的 per-sub-WU 状态机：

```
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

**验证**：
- Artifact naming 完整（§7.3 行 204-220）：每个 sub-WU 最少 13 个 artifact 文件（plan、双 plan review、controller adjudication、plan fix、双 plan re-review、controller re-review adjudication、implementation、双 code review、controller adjudication、code fix、双 code re-review、controller re-review adjudication、completion）。
- Entry criteria 明确（§7.3 行 223-224）：当前分支、前一 accepted commit、owner/允许文件/依赖可确定。
- Implementation entry criteria（§7.3 行 224）：独立计划已双 re-review、所有 accepted plan finding 已修复、controller accepted plan local commit。
- 完成信号（§7.3 行 225）：全部 slices、tests、coverage、pyright、diff/scan、README、smoke 通过；双路 code re-review 确认所有 accepted finding 已修复；controller accepted sub-WU local commit。
- Stop condition（§7.3 行 226）：owner 不清、设计冲突、越界 issue、中间 schema、retained security 失败、baseline 扩散、allowed files 外 diff、accepted finding 未闭合、Windows release blocker 未追踪时立即停止。
- 明确声明（§7.3 行 184-185）："本文不是 R01—R12 任一 sub-WU 的 plan artifact。每个 sub-WU 都必须独立、完整、不可折叠地执行以下状态机；即使 umbrella 总计划、相邻 sub-WU 或 aggregate review 已讨论过相同模块，也不能跳过。"

**结论**：每个 R01-R12 都有独立、完整、不可折叠的 phaseflow gate，不可跳过任何环节。✅

### 2.2 当前分支串行

Plan §6 行 145："所有 sub-WU 都在当前 `phaseflow/host-issues-control` 工作分支按 `R01 -> R02 -> ... -> R12` 串行推进；不得为 R01/R02/R03 或其它 sub-WU 创建独立实施分支，也不得通过 rebase 汇总。每个下一 sub-WU 都以前一 sub-WU 的 controller accepted local commit 为 base。"

唯一允许的并发是同一 immutable review target 上的 AgentMiMo/AgentDS 两路 reviewer。

**结论**：当前分支串行，无独立分支/rebase。✅

### 2.3 Windows cmd.exe Renderer / 真实 Runner Release Blocker

Plan §18.2 行 917-918 定义了 Windows batch renderer 边界：
- 职责单一、平台专用 batch renderer 拥有 `argv -> .cmd command line`
- `DisableDelayedExpansion` 显式关闭
- `%` 按 batch 语义转义
- `!` 在 DisableDelayedExpansion 下保持字面量
- `&|^()` 不得启动第二命令/管道/分组/改变控制流
- Unicode、引号、反斜杠 invariant
- `subprocess.list2cmdline` 不是 batch quoting owner
- 具体 quote/escape 算法由 R11 子计划依据 cmd.exe 文档和真实 runner evidence 固定

Plan §22.1 行 1157："R11 独立子计划必须在 implementation 前写明 Windows runner/CI owner；actual `cmd.exe` recorder 与真实 CLI grammar smoke 可以在非 Windows 本地开发之后执行，但最迟必须在本 aggregate regression 或随后的 draft-PR check 中成功。缺少 runner、workflow 未触发、job skipped、artifact 不可读或任一对抗字符失败都阻塞 aggregate/PR/final closeout；不得把 unsafe quoting 或未验证 Windows 行为列为 residual。"

Plan §22.4 行 1194 final closeout 矩阵："Cross-platform CLI — POSIX 与真实 Windows `cmd.exe` CI artifacts — recorder argv exact round-trip、无注入、真实 CLI grammar；unsafe quoting/runner pending 均不通过。"

**结论**：Windows cmd.exe renderer 边界清晰，真实 runner 执行为 release blocker，不得降级为 residual。✅

### 2.4 R07 无 Speculative Algorithm/Type/Retry Contract

Plan §14.2 行 718："算法、前缀、编码长度、revision grammar 及是否需要某种 registry 都不是 umbrella contract，由 R07 独立子计划基于当前 storage layout 与直接代码证据决定。"

Plan §14.3 行 724："具体 revision 编码、前缀和生成算法由 R07 独立子计划基于 storage layout 决定，不是业务/public/LLM contract。"

Plan §14.3 行 725："retry 次数、snapshot API/类型名、copy/digest 策略和资源生命周期形态都由 R07 子计划基于代码证据决定，不在 umbrella 计划固定。"

Plan §14.3 行 727："如何表达 cache entry、resource handle 或关闭责任由 R07 子计划决定；本文不固定任何 lease、context manager 或 cache class形态。"

Plan §14.3 行 726："不得新增另一异常名或让下游从异常消息/revision mismatch 恢复分类。" — 复用既有 typed `source_changed_during_read`。

**结论**：R07 不固定 hash/revision grammar、retry 次数、新异常名、cache lease 形态。只保留 storage-owned 不变量和既有 typed error。✅

### 2.5 R03 人工 Source Inventory

Plan §10.4 R03-S2 行 486-487："在修改前产出并在 R03 completion report 保存人工逐文件 source inventory。Inventory 必须枚举：`dayu/config/prompts/**` 的每个 prompt asset；所有 production ToolDefinition/tool schema 的 name、description、参数、枚举和错误说明；Host/Engine/Tool 中会进入 system/user/assistant/tool message、Memory、Compact、Trace、Evidence 的 renderer；tests/smoke 中模拟真实 LLM 调用的 prompt/schema fixture；以及 R01 handoff 的 Doc LLM-facing 删除清单。每项记录文件、具体 source、是否 LLM-facing、语义 owner、`compliant | modify-at-owner | not-LLM-facing-with-evidence` disposition 与验证证据，不能用目录级'已扫描'代替逐文件审计。"

Plan §10.5 行 511："completion report 必须附完整 inventory、逐项 disposition、R01 handoff 消费记录、实际 owner 修改清单和全部自动门禁结果；仅有 grep 零命中不得完成 R03。"

Plan §8.5 行 347："handoff 到 R03/aggregate：逐文件列出全部 Doc tool name/description/参数/枚举/错误说明、真实 LLM prompt fixture 与其它 LLM-facing 文本中被删除、保留或改写的项，记录 source owner 和最终 disposition；该清单是 R03 人工 source inventory 的必填输入。不得只交一条 grep 结果。"

**结论**：R03 人工 source inventory 是 mandatory deliverable，有明确的枚举范围、disposition 分类、R01 handoff 消费和 completion report 保存要求。自动 grep 只是门禁，不是完整性证明。✅

### 2.6 R04 配置唯一 Owner

Plan §11.2 行 526："这些名称就是现有 `WaitPollerRuntimePolicy` canonical fields，不建立别名。该 JSON snapshot 是所有部署 policy 数值的唯一真源；`WaitPollerRuntimePolicy` 的全部字段都是 required，不提供带部署数值的字段 default 或无参构造，Service/Host 不复制其中任何数值作为 fallback/default。所有字段由 ConfigLoader 的完整 typed snapshot 显式构造并严格 finite/positive 校验。"

Plan §11.3 R04-S2 行 552："删除 `WaitPollerRuntimePolicy()` 无参路径及 dataclass 上所有 deployment-value defaults；Service/Host 生产代码只能接收 ConfigLoader 已校验的完整 snapshot，不得以模块常量、helper default、factory fallback 或测试 fixture 复制部署值。与部署 policy 无关的内部算法常量可以保留，但任何数值命中必须逐条证明其语义不属于 `wait_poller_policy`；当前承载同一部署语义的 30/5/8 等模块常量必须删除。"

**结论**：`host_runtime.json` 是部署 policy 数值唯一真源；typed policy 无 deployment-value defaults/无参构造；Service/Host 不复制数值。✅

### 2.7 R08 Raw Total / Public Count

Plan §15.2 行 783-784："XBRL processor-owned internal result 只承诺 `query_params`、raw `facts`、`data_quality`、可选 reason；provider raw `total` 只允许保留在明确的 producer validation/diagnostic owner，用于核验 provider 响应，不是 public 或 LLM 业务事实。read projection 可以清洗/去重 raw facts，但必须生成一个独立的 public typed result，输出 deduplicated `facts` 与唯一 `fact_count = len(deduplicated facts)`；不得覆盖 processor raw facts 后把重算值冒充 producer 事实，也不得在 public/tool schema/LLM 文本同时暴露去重前 total、dedupe diagnostic 与 fact_count。"

Plan §15.3 R08-S2 行 810："验证必须同时提供：(1) 限定 internal processor/diagnostic 类型的正向 scan，逐条证明 raw `total` 只用于 provider 校验/诊断；(2) 限定 public result/tool schema/serializer/LLM renderer 的反向 scan，证明 `raw_total|deduped_fact_count|去重前total` 零残留且只有 `fact_count`；(3) owner-level test 断言 `fact_count == len(returned deduplicated facts)`。不得用全仓 `total` 零命中误删内部校验，也不得把内部残留当 public closure。"

**结论**：internal raw total 只在 producer validation/diagnostic owner 保留；public/LLM 只有 deduplicated `fact_count`；正反扫描与 owner-level test 确保边界。✅

### 2.8 R11 OLD 分类和两类 Smoke

Plan §18.2 行 913："OLD 直接证据为 `/Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py:120-125,371-458` 与 `/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py:1520-1544`：annual 最多 5；periodic 只保留识别到的最新 fiscal year 且最多 6；presentation 最多 6；call cap 等于过滤后 recognized report 数量；`FINANCIAL_STATEMENTS` 不在 material cap map 中，因此无材料数量 cap；同一 `(fiscal_year, fiscal_period)` 先由 Fins-owned、等价 `_pick_best_per_period` 的优先级规则选唯一主报告，再应用年度/数量规则。"

两类 smoke 分离（§18.3 行 945-947）：
- **Recorder quoting smoke**：POSIX 用真实 `/bin/sh`，Windows 用真实 `cmd.exe`；受控 recorder 只记录最终 argv；对抗矩阵含空格、Unicode、单双引号、反斜杠、`%`、`!`、`&|^()`。
- **真实端到端 smoke**：生成的 POSIX 脚本真实进入 `python -m dayu.cli upload_filing|upload_material` parser、Service/Fins direct path 与临时 storage。Windows runner 还必须至少让生成 `.cmd` 真实进入同一 `python -m dayu.cli` grammar。外部 provider 只能用可控 fixture。recorder 不得冒充端到端 smoke。

Plan §22.1 行 1157：真实 Windows `cmd.exe` recorder + CLI grammar smoke 最迟 aggregate/PR check 通过；runner 缺失是 release blocker。

**结论**：OLD 分类规则有精确文件/行号证据；recorder smoke 与端到端 smoke 严格分离；Windows 执行是 release blocker。✅

### 2.9 R12 Assets/Reset/Prewarm

Plan §19.3 行 1024-1026："init owner 必须维护唯一 managed-root manifest，reset 展示、确认、containment 与删除全部消费它。当前产品 manifest 只包含 `<workspace>/.dayu`（整个 Dayu-owned Host/runtime/CLI/artifact/storage-state 可重建根）与 `<workspace>/config`；当前 package 没有 `dayu/assets`，本 WU 不得创建空 `assets`、从 OLD 搬入 assets，也不得把用户自行建立的 `<workspace>/assets` 视为 Dayu-owned 后删除。未来 Issue 151 真正交付 product-owned workspace assets 时，由 Issue 151 owner 把该 root 及其 ownership 证据加入同一 managed-root manifest。"

Plan §19.3 行 1030："prewarm 只在 first/reset 成功发布后运行一次：加载 ConfigLoader、prompt/interactive/session assembly、Fins processor registry，不发真实 LLM/HTTP 请求。ordinary init 与 `--overwrite` 都不 prewarm；不得因 overwrite 使用 packaged defaults 而把它重分类为 first。prewarm 失败给 warning 但已完成 init 仍成功；所有 config validation 失败必须在 swap 前硬失败。"

**结论**：managed-root manifest 只含 `.dayu` + `config`；当前无 assets、不创建/搬入/删除用户自建 assets；Issue 151 拥有未来 assets manifest 扩展；prewarm 仅 first/reset 各一次，ordinary/overwrite 零次。✅

### 2.10 Topic 8/9 与 Issue 142/151/175/177/178 边界

Plan §3 行 66-67（非目标）：
- Topic 8："保留 `dayu/engine/agent.py` 的敏感值先脱敏、原始异常消息 240 字符上限、显式截断后缀和完整 traceback 日志；不改配置、不新增 durable full-detail ref。"
- Topic 9："不设计或实现统一 tool authorization framework、角色模型、policy DSL、capability token 或 sandbox。"

Plan §3 行 69："不实施 Issue 142、151、175、177、178；不把现有 Web/WeChat/render tracker 能力搬入本 WU。"

Plan §4 Accepted/deferred 追踪表：
- Issue 177：deferred，Issue 177 owner，不在本 WU。
- Issue 178：deferred，Issue 178 owner。
- Issue 175：deferred，Issue 175 owner。
- Issue 142/151：deferred，各 issue owner。R12 不创建/搬入 assets 或产品 assets，不迁移旧 schema。
- Topic 8：no code，保留 Engine 240 字符异常消息策略。
- Topic 9：no code，不实现统一授权。

Plan §23 Residual risk 表确认每个 residual 的 owner/destination，且明确"这些 residual 均不得把 Topic 1—7 已接受行为降为 partial"。

**结论**：Topic 8/9 为 no-code，Issue 142/151/175/177/178 均 deferred 且未被实现。边界清晰。✅

---

## 三、Adversarial Findings

### 01-新-低-R03 source inventory 缺少具体模板/checklist

- **位置**：Plan §10.4 R03-S2 行 486-487
- **问题类型**：最佳实践偏离
- **当前写法**：Plan 要求"人工逐文件 source inventory"，列出了枚举范围（prompt assets、tool schemas、renderers、test fixtures、R01 handoff），disposition 分类（`compliant | modify-at-owner | not-LLM-facing-with-evidence`），并要求在 completion report 保存。
- **反例/失败场景**：Implementation agent 可能对"逐文件"的理解不一致——是每个文件一行、每个 source 一行、还是每个 LLM-facing 文本片段一行？缺少具体模板可能导致 inventory 粒度不一致，reviewer 难以验证完整性。
- **为什么有问题**：R03 是 Topic 3/4 的核心 sub-WU，source inventory 是其 mandatory deliverable。如果 inventory 格式不一致，双路 reviewer 可能对"完整"有不同判断。
- **直接证据**：Plan §10.4 行 486 只列了枚举范围和 disposition 分类，未提供表格模板或示例行。
- **影响**：reviewer 验证成本增加；不阻塞 implementation 但可能延长 review cycle。
- **建议改法和验证点**：在 R03 子计划中提供 inventory 表格模板（列：文件路径、具体 source 片段、是否 LLM-facing、语义 owner、disposition、验证证据），并在 §10.4 补充一句"子计划必须提供表格模板"。
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

### 02-新-低-R11 Windows runner 缺失时的具体 stop 行为未明确

- **位置**：Plan §18.1 行 908、§22.1 行 1157
- **问题类型**：契约缺失
- **当前写法**：Plan 要求 R11 子计划 implementation 前确认 Windows runner/CI owner；"缺少 runner、workflow 未触发、job skipped、artifact 不可读或任一对抗字符失败都阻塞 aggregate/PR/final closeout；不得把 unsafe quoting 或未验证 Windows 行为列为 residual。"
- **反例/失败场景**：如果 R11 子计划启动时发现仓库确实没有 Windows runner，且无法在合理时间内新增，子计划应如何处理？Plan 说"子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist 并经双 plan review/controller 接受"，但未说明如果 CI 平台不支持 Windows runner 时的 fallback 路径。
- **为什么有问题**：这是一个真实场景——如果 CI 平台（如 GitHub Actions free tier）不支持 Windows runner，子计划会卡在 entry criteria。
- **直接证据**：Plan §18.1 行 908 说"若当前仓库仍无 runner，子计划必须把新增最小 Windows workflow 的精确文件列入自己的 closed allowlist"。
- **影响**：子计划可能在 entry criteria 处 stop，需要 controller 决策。
- **建议改法和验证点**：这是正确的 stop behavior——如果 runner 不可用，子计划 stop 并上报 controller，controller 决定是否接受 Windows CI 的 delay 或替代方案。Plan 已隐含此行为（stop condition 覆盖），但可以更显式。建议在 §18.1 补充："若 CI 平台不支持 Windows runner 且无法在合理时间内新增，子计划 stop 并上报 controller 决策；不得自行降级为 residual。"
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

### 03-新-低-R06 producer migration 范围可能过宽

- **位置**：Plan §7.4 行 240（R06 allowed production files）
- **问题类型**：切片过粗
- **当前写法**：R06 的 allowed files 包含 22 个 storage core/repository 文件和 12 个 pipeline 文件，所有 producer 都在同一个 sub-WU 内迁移。
- **反例/失败场景**：如果某个 pipeline（如 `docling_upload_service.py`）的迁移比预期复杂，可能阻塞整个 R06 sub-WU。
- **为什么有问题**：R06 是 R07/R08/R09/R10/R11 的硬依赖；R06 延迟会级联阻塞后续所有 sub-WU。
- **直接证据**：Plan §5 行 112 确认 R06 有 3 个 slices；§6 行 129 确认 R07/R08/R09/R10/R11 均依赖 R06。
- **影响**：如果 R06 的某个 pipeline migration 遇到困难，可能延迟整个 remediation 进度。
- **建议改法和验证点**：这是 sub-WU 内部的 implementation 风险，不是 plan-level 缺陷。R06 子计划可以在自己的 plan review 中评估是否需要额外 slice 或降级某个 pipeline 的迁移范围。Plan 的 3-slice 切分已合理。
- **修复风险（低/中/高）**：低
- **严重程度（低/中/高/严重）**：低

---

## 四、Open Questions

无 blocking open questions。所有 controller-accepted findings 均有明确 closure；rejected/deferred/note 未被误实现；每个重点维度均有直接 plan 文本证据。

---

## 五、Residual Risks

| residual risk | 当前处理 | owner/destination |
| --- | --- | --- |
| Doc 极大输入可能耗尽资源 | 本 WU 删除未经裁决的业务 hard-fail，保留 spool/cancel/output limit | Issue 177 |
| browser credential state retention/refresh/并发 cleanup | 本 WU 删除 utility 自造 lifecycle，只保留显式输入 | Issue 178 |
| Fins thread-backed 长事务不可物理取消 | wait fencing 防 late publication，不迁移 executor | Issue 175 |
| future product assets 与其它 init 迁移 | 当前 package 不创建/搬入 assets，用户自建 assets 不删 | Issue 142/151 |
| Windows env 写与 POSIX profile/config 无法形成跨资源全局原子事务 | 必需 env 先成功再 config swap；失败报告 env names 不泄值 | R12 CLI owner |
| HKEX 未来可能出现 rowRange 硬 cap | 当前官方累计协议无证据支持第二机制 | HKEX provider 后续 evidence-driven issue |
| Web peer proof 与企业 proxy 同时启用不可证明最终 peer | typed incompatibility fail closed | Web config owner |
| unified tool authorization 尚未设计 | 保留局部 permission/I/O 防御 | Topic 9 后续独立 design WU |

这些 residual 均已在 plan §23 中明确定义，不把 Topic 1—7 已接受行为降为 partial。

---

## 六、Final Plan Review Conclusion

### Verdict: **pass**

修订后 remediation plan 通过双路 re-review。理由：

1. **旧 findings 全部真实关闭**：5 个 controller accepted findings、12 个 DS findings（含 accepted in part）、15 个 MiMo findings 均按 controller disposition 真实关闭或正确保留。2 个 rejected findings 未被误实现。全部 notes 未被升级为实现要求。
2. **每个 R01-R12 有独立完整 phaseflow gate**：§7.3 定义了完整的 per-sub-WU 状态机，包含 plan→双 plan review→controller adjudication→fix→双 re-review→accepted plan commit→implementation→双 code review→controller adjudication→fix→双 re-review→accepted sub-WU commit。13 个 artifact 文件命名明确。
3. **当前分支串行**：§6 固定 `phaseflow/host-issues-control` 按 R01→R12 串行 accepted commits，无独立分支/rebase。
4. **Windows cmd.exe renderer 边界清晰**：§18.2 定义了职责单一的 batch renderer 边界（DisableDelayedExpansion、% escaping、&|^() invariant），明确 `list2cmdline` 不是 batch quoting owner。真实 cmd.exe 执行为 release blocker（§22.1/§22.4）。
5. **R07 无 speculative design**：§14.2-14.3 删除固定 hash/revision grammar、retry 次数、新异常名、cache lease 形态；只保留 storage-owned 不变量和既有 typed error。
6. **R03 人工 source inventory 是 mandatory deliverable**：§10.4-10.5 有明确枚举范围、disposition 分类、R01 handoff 消费和 completion report 保存要求。
7. **R04 配置唯一 owner**：§11.2 确认 `host_runtime.json` 是部署 policy 数值唯一真源，typed policy 无 deployment-value defaults/无参构造。
8. **R08 raw total/public count 分离**：§15.2-15.3 区分 internal provider validation raw total 与 public/LLM deduplicated `fact_count`，正反扫描确保边界。
9. **R11 OLD 分类精确**：§18.2 有精确文件/行号证据，annual=5/periodic=6/presentation=6/call cap/`FINANCIAL_STATEMENTS` 无 cap。recorder smoke 与端到端 smoke 严格分离。
10. **R12 assets/reset/prewarm 无歧义**：§19.3 确认 managed-root manifest 只含 `.dayu`+`config`，当前无 assets，prewarm 仅 first/reset 各一次。
11. **Topic 8/9 和 Issue 142/151/175/177/178 边界正确**：均为 no-code 或 deferred，未被实现。

3 个新 finding 均为低严重度，不阻塞 implementation：
- R03 source inventory 缺少具体模板（最佳实践偏离）
- R11 Windows runner 缺失时的 stop 行为可更显式（契约缺失）
- R06 producer migration 范围可能过宽（切片过粗风险，由子计划管理）

**计划可以进入 implementation。下一动作由 umbrella controller 派发 R01 子计划。**
