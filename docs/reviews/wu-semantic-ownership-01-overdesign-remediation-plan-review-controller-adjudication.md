# WU-SEMANTIC-OWNERSHIP-01 Overdesign Remediation Plan Review 总控裁决

## Gate 身份

- 本文裁决既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 remediation 总计划 review，不创建新 WU、feature 或 issue。
- 计划：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`。
- 第一路 review：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-mimo.md`。
- 第二路 review：`docs/reviews/wu-semantic-ownership-01-overdesign-remediation-plan-review-ds.md`。
- 最终产品裁决仍由 `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` 与本轮用户明确执行流程拥有；reviewer verdict 不能自动授权 implementation。

## 总结裁决

计划覆盖 Topic 1—7 的总体 owner map、依赖图、验证矩阵与 deferred/no-code 边界成立，但**不得直接进入 implementation**。必须先完成一次 plan-fix 和双路 re-review。

需要修复的根因共五组：

1. Windows `.cmd` 生成把 MS C runtime quoting 误当作 cmd.exe batch quoting，无法证明 `%`、`!`、`&|^()` 等字符保持 argv 边界。
2. R07 把 storage-owned snapshot/identity 的必要不变量扩写成未经裁决的固定 hash grammar、固定三次重试、新异常类名和 cache lease 形态。
3. R12 没有准确表达 product-present assets 的 reset 条件，且 prewarm 对 overwrite 留下已被 controller 排除的歧义。
4. R03 source audit、R04 runtime policy defaults、R08 raw total、R11 OLD 分类与跨平台/端到端 smoke 的 closure 还不够可证。
5. 总计划没有把用户明确要求的“每个内部 remediation sub-WU 独立 plan/review/fix/re-review/implementation/code-review/fix/re-review/accepted commit”写成不可跳过的状态机，且错误保留了独立分支/rebase和额外授权措辞。

以上都能在计划内部修复，无需重新询问用户，也不改变 Topic 1—9 产品裁决。

## AgentDS findings 裁决

| Finding | 裁决 | 理由与要求 |
| --- | --- | --- |
| DS-PF-01 | **accepted** | `subprocess.list2cmdline` 只解决 Windows C runtime argv 编码，不完整拥有 `.cmd` 的 batch 解析。R11 必须改成一个职责单一、平台专用且有文档依据的 cmd renderer；至少固定 delayed expansion 语义、正确处理 `%` 与引号/反斜杠，并用真实 Windows `cmd.exe` 对 `&|^()%!`、空格、Unicode、单双引号执行 recorder smoke。不能把不安全 quoting 留作 residual。 |
| DS-PF-02 | **accepted in part** | storage-owned snapshot/revision 是已裁决方向；固定 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3`、新异常名、`_CachedProcessor` lease 名称和具体生命周期不是产品裁决。计划只保留“storage 原子取得同版本 source/files/provenance、允许有界内部重试、耗尽后使用既有 typed `source_changed_during_read`、cache 不持有失效资源”的不变量。API/类名、重试次数和 lease 实现留给 R07 子计划基于代码证据决定。 |
| DS-PF-03 | **accepted in part** | §21 增加平台 quoting/argv boundary 安全条目；Windows env persistence 非跨资源原子性的 residual 保留。拒绝把未解决的 `.cmd` quoting 风险列为 residual，因为正确 quoting 是 Topic 7 accepted contract 和 release blocker。 |
| DS-PF-04 | **accepted** | grep 只能做自动门禁。R03 必须列出并逐文件人工审计所有 prompt assets、tool name/description/parameter schema、测试真实 LLM prompt、Host/Engine/Tool LLM renderer；completion report 保存 inventory、逐项 disposition 和自动扫描结果。 |
| DS-PF-05 | **accepted** | 当前仓库没有 Windows CI/workflow。R11 子计划必须在 implementation 前明确实际 Windows runner/CI owner；本地 renderer tests 不能代替最终 `cmd.exe` 执行。真实 Windows smoke 最迟在 umbrella aggregate/PR check 前完成，未完成不得 final closeout；若需新增最小 Windows CI workflow，先在 R11 子计划列为直接验证文件。 |
| DS-PF-06 | **accepted** | R08 明确区分 internal provider validation/diagnostic 中可保留的 raw `total` 与 public/LLM result 中必须删除的 raw total，并提供限定目录/类型的正反扫描和 owner-level test。 |
| DS-PF-07 | **rejected-with-reason** | R05 publication fencing 与 R09 Fins stream terminal validation 是不同 owner、不同事实层级。把“observation timeout + duplicate result”强行组合会制造并不存在的跨层协议。保留 R05 的 late typed result 整体不可发布测试，以及 R09 的 duplicate/event-after-result 测试；不新增耦合场景。 |
| DS-PF-08 | **accepted with stronger correction** | 不是只补 handoff 清单。用户要求逐个 sub-WU 推进，且共享同一工作分支；删除 R01/R02/R03 独立分支/rebase表述，固定顺序 accepted commit。R01 的 LLM-facing 删除清单必须成为 R03 source audit 输入。 |
| DS-PF-09 | **accepted** | R11 补 OLD 精确证据与未写清的规则：annual 5、latest-year periodic 6、presentation 6、call cap 等于 recognized reports、`FINANCIAL_STATEMENTS` 无材料数量 cap、同期优先级/去重由 Fins-owned等价 `_pick_best_per_period` 规则拥有。 |
| DS-PF-10 | **note / no plan fix required** | 计划已要求以 current `models.json` 为准并由 ConfigLoader 验证。R12 子计划第一步必须重做 catalog/config diff，但无需在 umbrella 计划再次复制 snapshot。 |
| DS-PF-11 | **accepted with correction** | reviewer 认为正文已覆盖 assets，不符合文本证据。计划必须明确：reset 语义包含 Dayu-owned `.dayu`、config，以及**当前产品实际提供/拥有时**的 workspace assets；当前 package 没有 `dayu/assets`，本 WU 不创建或从 OLD 搬入 assets，也不得删除任意用户自建 `assets`。未来 Issue 151 交付产品 assets 时，由该 owner 将其纳入同一 managed-root manifest。portfolio 永不删除。 |
| DS-PF-12 | **note** | 正面检查结论保留，不产生 fix。 |

## AgentMiMo findings 裁决

| Finding | 裁决 | 理由与要求 |
| --- | --- | --- |
| MIMO-PF-01 | **accepted** | 与 DS-PF-11 合并，按“当前产品实际拥有的 assets”精确修正，不能只写未来扩展，也不能在当前仓库臆造 assets surface。 |
| MIMO-PF-02 | **accepted** | 与 DS-PF-01 合并。不得把 `%` 或任何已知 cmd 元字符风险标为 residual。 |
| MIMO-PF-03 | **accepted** | `host_runtime.json` 是部署 policy 数值唯一真源。`WaitPollerRuntimePolicy` 不再提供带部署数值的无参/default 构造；Service/Host 代码不得复制 30/5/8 等 policy defaults。测试必须显式传完整 snapshot。 |
| MIMO-PF-04 | **rejected-with-reason** | 计划现有 stop condition 正确。若真实 tool 必须由 LLM 提交 credential 且无法在 tool owner迁移，owner 已不清晰，必须 stop 回 controller；预先设计“特例脱敏/fallback”会重建本次明确删除的下游安全归一语义。只需按 DS-PF-04 补完整 source audit。 |
| MIMO-PF-05 | **accepted** | controller 已裁决 first/reset only。删除“除非 controller design 明确写入”；ordinary init 和 overwrite 不 prewarm。 |
| MIMO-PF-06 | **accepted** | fake recorder 只验证 renderer/argv 边界。R11 还必须执行生成的 POSIX 脚本经过真实 `python -m dayu.cli upload_filing|upload_material` parser、Service/Fins direct path和临时 storage；外部 provider可用可控 fixture，不能把 recorder冒充端到端 smoke。Windows同样至少真实进入 CLI grammar。 |
| MIMO-PF-07 | **accepted / merged** | 与 MIMO-PF-03 合并；删除 duplicate deployment defaults，scan 允许与部署 policy 无关的内部常量但必须逐条归属。 |
| MIMO-PF-08—15 | **notes, except conflicts resolved above** | 文件闭集、Topic/deferred边界、总体 owner map与验证框架的正面结论保留。MIMO-PF-14 对固定 retry/新类型“无 speculative design”的判断被更高优先级 controller裁决和 DS-PF-02 直接证据覆盖；R07按本 artifact收窄。 |

## Controller 新增 findings

### CTL-PF-01 — 每个内部 sub-WU 的独立完整 gate 未写成状态机

- **状态**：accepted，blocking。
- 用户明确要求每个 remediation sub-WU 逐个执行：plan → 两路 plan review → AgentCodex fix accepted findings → 两路 re-review → implementation → 两路 code review → fix all accepted findings → 两路 re-review → accepted local commit。
- 当前 umbrella plan §7 主要写了 slice implementation/code review，§22只统计 `12×2 code review artifacts`，不能证明每个 R01—R12 都有独立 plan/fix/re-review artifact。
- **修复**：增加 per-sub-WU gate state machine、artifact naming、controller adjudication和进入/退出条件。当前总计划只拥有切分与全局依赖；不能替代 R01—R12 各自的 code-generation-ready plan gate。

### CTL-PF-02 — 任一 accepted finding 都必须修复，不按 reviewer severity 过滤

- **状态**：accepted，blocking。
- 当前 §7.1 只写“production-high finding回 implementation”，§22.2 又只列 high/medium actionable finding；用户要求所有 controller-accepted findings全部修复。
- **修复**：所有 plan/code/deepreview/PR review finding 先由 controller裁决；任何 severity 的 accepted actionable finding 都必须由 AgentCodex修复并双路 re-review。rejected/deferred/note不进入 fix。

### CTL-PF-03 — accepted local commit 与外部 gate 授权表述错误

- **状态**：accepted，blocking。
- 每个 sub-WU完成 re-review后必须由 controller创建 accepted local commit。当前 §7.3 未把 commit写入 completion signal，§22.3 “不得自动commit/push/open”与用户本轮明确授权的完整 phaseflow冲突。
- **修复**：计划明确 controller在 accepted-plan、accepted-sub-WU、aggregate/PR-review gates创建本地accepted commit；所有 sub-WU完成后按 phaseflow push并创建 draft PR，无需再次询问本轮已授权事项。仍禁止未经额外授权 mark ready、merge、approve、request reviewers、发布外部 comment、创建/修改 issue或删除分支。

### CTL-PF-04 — 同一工作分支必须串行推进

- **状态**：accepted。
- 当前计划写 R01/R02/R03 可在独立分支后 rebase；用户要求逐个 sub-WU accepted local commit，且当前工作区含有必须保留的有意 artifacts。
- **修复**：删除独立分支/rebase方案。R01—R12按依赖在当前 `phaseflow/host-issues-control` 串行推进；每个下一 sub-WU以此前accepted commit为base。可以并发的只有两路 reviewer，不并发修改共享工作区。

### CTL-PF-05 — R07 internal identity algorithm 同样被过早固定

- **状态**：accepted。
- controller只裁决 storage-owned mapping/encoding boundary、containment与identity round-trip；没有裁决 `ticker_<sha256>`、`doc_<sha256>`、无 reverse registry或 `rev_ + UUID`。
- **修复**：umbrella plan只保留 opaque external identity不直接成为路径、storage唯一映射、collision/corruption fail closed、meta同源round-trip、fresh schema和containment不变量。算法、前缀、revision编码、registry形态由R07子计划基于现有storage布局选择，不成为业务/public/LLM contract。

## Plan-fix 必须完成的闭集

AgentCodex 的 plan-fix 必须一次关闭以下事项：

1. 增加每个 R01—R12 的完整独立 gate state machine与artifact/accepted-commit规则。
2. 删除独立分支/rebase，改为当前分支串行accepted commits；只并发review。
3. 将所有 controller-accepted finding（不限severity）纳入fix/re-review。
4. 修正 phaseflow已授权的local commit、push、draft PR边界，并保留未授权的ready/merge/reviewer/comment/issue/delete禁令。
5. 用正确的 Windows batch renderer边界替代 `list2cmdline等价cmd quoting`，补真实Windows runner/CI closure和安全矩阵。
6. 收窄 R07：不固定hash/revision grammar、retry次数、新异常/lease类名；保留storage-owned snapshot/identity不变量和既有typed error。
7. 明确R12 managed roots：`.dayu`、config、current-product-owned assets（若产品提供），不创建OLD assets、不删portfolio；first/reset only prewarm。
8. 明确R04 policy数值只来自`host_runtime.json`，typed policy无部署默认；删除重复常量语义。
9. 把R03完整人工source inventory/audit作为必交付证据；不新增credential fallback/blacklist。
10. 区分R08 internal raw total与public/LLM唯一deduplicated fact count。
11. 补R11 OLD精确分类规则与证据，区分recorder quoting smoke和真实CLI/Fins端到端smoke。
12. 明确Windows实际执行最迟在aggregate/PR check前通过；缺runner不得final closeout。
13. R01完成后把其LLM-facing删除清单交给R03，避免平行修改冲突。

## Next gate

- gate：remediation plan fix。
- owner：AgentCodex。
- 允许修改：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`，并新增一个 plan-fix artifact。
- 禁止：产品代码、测试、README、design/control artifact、commit、push、PR。
- fix完成后必须由AgentMiMo与AgentDS双路 re-review；在两路 closure与controller裁决前不得 implementation。
