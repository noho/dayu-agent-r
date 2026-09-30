RUNTIME/PROVIDER/MODEL: codex/gpt-6-sol/gpt-6.1-sol

CANARY=gpt-6-sol-23046468

# PR197-R1/F4-PV01：历史报告准确性窄修复

## 身份、授权、动机与边界

- Label：`pr197-f4-reportfix-sol-20260930-02`；WU：`fins-hk-download-identity-batch-read`；当前交付为报告准确性 fix，作者交付完成、待总控独立验收；没有 plan accepted 或 gatepass。
- 唯一 workspace：本仓库；branch `codex/upload-material-oracle`。起始 HEAD `60307c15947e2f89457e03126b1251aeb4264c53`；末核 HEAD `b42bbea1e7ccc58561764c20d873214783283eb2`。收尾观察到已授权并行治理证据 checkpoint `b42bbea1`（`gateflow: preserve repair counterexamples and F7 review evidence`），实读 git show/log 确认其为 F3/F7/治理证据归档，包含此前已冻结的 goal 现成修订；22项当前输入仍匹配，非本作者提交，不能据此全局 HEAD 阻断；start/end/final-check 保存已存在 F3 utils/F3/F7/治理文档 dirty，未将并发变化当本次写入或 F4 source 漂移，也不设全局 HEAD 冻结。
- 权威是用户现成裁决及本次窄授权、`workspace/tmp/pr197-f4-report-validation-20260930/controller-evidence.md`、current goal。已读 AGENTS、Gateflow、sub-agents 的 Result Validation / Retry And Sessions、独立裁决、current goal 与两份候选；未重跑全 plan 调查。memory 仅用于定位已有交付/裁决分离原则，本文事实均由当前文件/原事件实读。
- 本轮 provider profile 实读 `model = "gpt-6.1-sol"`。开头 commentary 的 `gpt-6` 家族简称不够精确，已通过配置读取更正；旧候选的历史身份行未改作本轮身份。
- 第一性原理：报告字符串是验收证据，必须与实际字节一致。原工具读取正确不能抵消报告缺字符；缺陷成立且只属于报告准确性，不能借此改变业务规则或重评技术设计。历史值的真源是各轮校验文件/expected；旧接受状态的 owner 是总控独立裁决，作者不能改写。
- 仅修改两候选的历史标记/验证措辞、新增本文，辅助记录仅写 `workspace/tmp/pr197-f4-reportfix-sol-20260930-02/`。未改产品源码/tests/README/goal/controller/queue/旧 fix/旧 review/独立裁决/raw runner/旧字节副本；未派发、stage/commit/push/PR/comment/merge、网络、真实下载/OCR、私样本、升级依赖或新分支/树。

## 本轮校验字节与最终报告的关系

本轮文件实读：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.KELGKS/canary.txt`；与同目录 `canary.expected` 字节一致。原字节为 `gpt-6-sol-23046468`，长度 `18`，无尾换行，SHA256 `c727338af5cb1832115c00de7d38eca6fc0e2a8106fd2b020cfde8df202b7f54`。本文开头值由文件读取结果直接生成；最终消息也从相同字节生成并工具断言一致，避免凭记忆抄写。候选中的历史标记不作为本轮证明。

本轮独立输出为 `/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.KELGKS/pr197-f4-reportfix-sol-20260930-02.jsonl`，stderr 为同目录 `pr197-f4-reportfix-sol-20260930-02.stderr`，last-message 目标为同目录 `pr197-f4-reportfix-sol-20260930-02.last.md`。这些 runner 文件只读或由 runner 自身维护；本报告不写入它们。写本文时外层仍在途，不能提前声称本轮外层 exit0 / turn.completed；完成后由总控收集并核验全部事件、stderr、最终消息与 artifact。

## 上一失败与本轮恢复分类

上一 label `pr197-f4-planfix-sol-20260930-02`，托管 `51450`，run_dir `sub-agents.AC1pAZ`。原事件实读为 `80` 条有效 JSONL、`1` 个 turn.completed、stderr `0` 字节；外层 exit0 来自独立裁决/托管收集事实，不从最终消息推断。

- 原实际文件：`/private/var/folders/2t/vbqfkdyj40v8f4jc4x180n5c0000gn/T/sub-agents.AC1pAZ/canary.txt`，值 `gpt-6-sol-c242e290`；与原 expected 字节一致。
- item_1 的真实 cat 输出包含完整值，exit0；item_34 虽读取文件，仍写入错误短值。原最后消息与两 artifact 的误报均为 `gpt-6-sol-c242e29`，漏末位 `0`。原 last.md、raw JSONL、两个原字节副本与 sha.json 首末 SHA 均不变。
- 历史裁定仍为 setup ok / agent completed / tool evidence yes / tool trace complete / required evidence complete / canary mismatch / result rejected / retry_class task。不以本次更正文档宣布旧任务验收成功。
- reportfix label01 是预检文件名机械规则导致的 setup fail、agent not_started，未调用 provider，不占 provider 重试。label02 是唯一一次有明确理由的同 provider task 窄修复性重派，保留旧可评分失败；不是重新评分技术方案，也不通过报告缺陷调整业务裁决。
- F4-PV01（低，报告准确性）：本次文字修复已完成，等待总控独立验收；未自行改独立裁决中的“未修复”。F4 产品 finding 未修复、产品未实施、计划未 accepted。

## 文件 SHA 与精确修改边界

| 文件 | 修订前 SHA256 | 修订后 SHA256 |
| --- | --- | --- |
| `docs/gateflow/pr-197-r1-f4-plan-20260930.md` | `e972b900adfd62e8ff27fc9bc0fa72f94f296beef9a903927cf85160a3186c6d` | `0080f24590b7ce4b6b8434c7a7d45d72bdb3cc26a63ab86fdd99f6a749a71cb8` |
| `docs/gateflow/pr-197-r1-f4-user-scope-plan-fix-20260930.md` | `d5fc7f29ee80c2f95031f34c9e3998a49091e75bb9a98437f07226e94bf348ed` | `4cebc4161b4dbcc635f66caba7f2641f8786e810f746ee9ca5ef8b36dfd6afa2` |

旧 SHA 来自保存的原字节并与当前修订前字节核对；新 SHA 从实际修订文件计算。原件保留在 `workspace/tmp/pr197-f4-report-validation-20260930/` 下对应完整相对路径；没有覆盖原件或原 sha.json。

plan 仅补历史值末位并增加历史拒收说明；从 `## 1.` 到 EOF 字节完全一致。user-scope fix 同样修正标记/历史说明，替换“得到上面逐字内容”“canary内容精确匹配”误报，并将原 plan SHA 明确标为报告修订前原字节。第一性原理、方案变化、修复登记、README/风险/下一入口正文逐字不变。下面是相对原字节的全部零上下文 diff，除此没有改动；有序成功前缀+原异常、身份纯索引、原事件两个 fresh 窗口、typed/ordinary 边界全部保持，没有新增技术选择。

```diff
--- frozen/docs/gateflow/pr-197-r1-f4-plan-20260930.md
+++ docs/gateflow/pr-197-r1-f4-plan-20260930.md
@@ -5 +5,3 @@
-CANARY=gpt-6-sol-c242e29
+CANARY=gpt-6-sol-c242e290
+
+历史校验修订（F4-PV01）：上行是上一 label `pr197-f4-planfix-sol-20260930-02` 的实际文件值；原报告误写 `gpt-6-sol-c242e29`，漏末位 `0`。上一任务虽外层 exit0 / turn.completed、工具读取正确，仍因报告不匹配被总控 rejected；本次更正文档不改变旧拒收事实，也不作为本轮校验证明。修复报告见 `docs/gateflow/pr-197-r1-f4-report-validation-fix-20260930.md`；须先由总控独立验收新交付，再送同版双路 Planreview，本文仍未 accepted。
```

```diff
--- frozen/docs/gateflow/pr-197-r1-f4-user-scope-plan-fix-20260930.md
+++ docs/gateflow/pr-197-r1-f4-user-scope-plan-fix-20260930.md
@@ -5 +5,3 @@
-CANARY=gpt-6-sol-c242e29
+CANARY=gpt-6-sol-c242e290
+
+历史校验修订（F4-PV01）：上行是上一 label `pr197-f4-planfix-sol-20260930-02` 的实际文件值；原报告误写 `gpt-6-sol-c242e29`，漏末位 `0`。上一任务虽外层 exit0 / turn.completed、工具读取正确，仍因报告不匹配被总控 rejected；本次更正文档不改变旧拒收事实，也不作为本轮校验证明。修复报告见 `docs/gateflow/pr-197-r1-f4-report-validation-fix-20260930.md`；须先由总控独立验收新交付，再送同版双路 Planreview，候选仍未 accepted。
@@ -11 +13 @@
-- 本轮 canary 通过工具读取 `sub-agents.AC1pAZ/canary.txt` 得到上面逐字内容；不复用旧 canary。runtime/provider/model 按本轮运行身份自报，不拿旧 plan 的 gpt-6 行当本轮证据。
+- 上一任务通过工具读取 `sub-agents.AC1pAZ/canary.txt` 得到完整值 `gpt-6-sol-c242e290`，但原最终报告与两个 artifact 均写成 `gpt-6-sol-c242e29`，不满足逐字匹配，旧 task rejected。本文上行仅更正历史实际值；本轮独立校验与身份见新修复报告，不以历史标记代替本轮证明。
@@ -23 +25 @@
-| 本轮新 plan | `e972b900adfd62e8ff27fc9bc0fa72f94f296beef9a903927cf85160a3186c6d`，唯一允许修改的 frozen产物 |
+| 上一任务新 plan（本次报告修订前原字节） | `e972b900adfd62e8ff27fc9bc0fa72f94f296beef9a903927cf85160a3186c6d`，上一任务唯一允许修改的 frozen产物；本次修订后 SHA 见新修复报告 |
@@ -64 +66 @@
-| cwd/branch/HEAD/status与本轮canary读取 | exit0；canary内容精确匹配，起始60307；status与授权并发范围相符 |
+| cwd/branch/HEAD/status与上一任务 canary 读取 | exit0；工具实际读取完整值，但原报告漏末位，报告不匹配，旧 task rejected；起始60307；status与授权并发范围相符 |
```

## 22 项只读输入首末校验

原 freeze 共23项，plan 是唯一可改项；其余22项首末 SHA 与 freeze 完全一致。current goal SHA 为 `d1f374b9adb053761c66e9dd04e2a27ae6cdb4e299b715f70d9f91ee99d9d05e`。表内每行的 freeze/首核/末核均为同一完整值，详细机器记录见本轮 start-check.json / end-check.json。

| 只读输入 | freeze = 首核 = 末核 SHA256 | 结果 |
| --- | --- | --- |
| `dayu/fins/storage/source_integrity.py` | `c0b90041a895e85da8af967a727c43034145af6cdead145b3a09c1b33c4aa6f7` | 一致 |
| `dayu/fins/storage/__init__.py` | `f04281910d61fd423cacfac92206d916346d09db9e62ed3812827c64e60290bb` | 一致 |
| `dayu/fins/storage/_fs_identity.py` | `ba0163593d41ea8403b22f00c163c08f9223f0e8cafe9fa553b6105467997d1c` | 一致 |
| `dayu/fins/domain/document_models.py` | `45a90c287dbf51c5ace46f6c41c51d08c2317cf68af35644600c838651fc9e5d` | 一致 |
| `dayu/fins/pipelines/download_events.py` | `c78908c346b6deed6920c0a3e628da90e9264b427640ced617dbc261a56c439a` | 一致 |
| `dayu/fins/pipelines/cn_download_models.py` | `abc7ecaa90d7f7fee89ec51c78902c720a0ca36a4fad6a52ef3e91bf50cedea0` | 一致 |
| `tests/fins/test_cn_download_workflow.py` | `38301f790796e276a9b83f8540306ecc84527d71957a2262040731f0f8a29218` | 一致 |
| `tests/fins/test_cn_download_runtime.py` | `69e8bbf6cb4ff90d9d10a75225436cf0b9c7a8395dcfef46372fb8374bb52004` | 一致 |
| `tests/fins/test_fins_storage_atomicity.py` | `9af834a776ea22a79ec9534cf4ca77de0f13cc0c96b4d769c2b22703ae122430` | 一致 |
| `dayu/fins/README.md` | `329da795925f1966db8bc9625c94ca09f235c009df54cf4e694e15bdd7259d1f` | 一致 |
| `tests/README.md` | `5d7e9d76eebcd0aa9ae8c8de6af70d3327d0854264ae5a09ec9ffa1dbcbe04ad` | 一致 |
| `dayu/README.md` | `cd58b39485ebb77f2be36a56f90969103bac23088b10b906ce349ae8fd895f45` | 一致 |
| `dayu/fins/pipelines/cn_download_identity.py` | `71bb00d438bb681ea0344fdb2679bf5178fb4a804423d02f1168be109de32510` | 一致 |
| `dayu/fins/pipelines/cn_download_workflow.py` | `13bc11cc7bad4aa771becfe63a4eb99428108da3d7c5c9e565a78b3fa646f0a6` | 一致 |
| `dayu/fins/pipelines/cn_download_filing_workflow.py` | `85002256c3375d227add85733cd7b23d3367c1f54e9d40224958fe3a860ed470` | 一致 |
| `dayu/fins/storage/repository_protocols.py` | `8f82d3a4ddc4b1edb5a265e83862a9566e95196edf45c50404f4fbd1e28a35a1` | 一致 |
| `dayu/fins/storage/_fs_source_document_core.py` | `65ba54ae7d58cc765bcda0ef4782461e053e45b409335d5a15774b9f035d4c74` | 一致 |
| `dayu/fins/storage/fs_source_document_repository.py` | `027784a3e201e1a26e63a2a863f7855c8e92eeb611dc20e244599c5745ca1275` | 一致 |
| `dayu/fins/storage/_fs_source_integrity.py` | `eb670d9b3963e57a83163ecf955c4596652b713a812bf23794426494f9743852` | 一致 |
| `dayu/fins/storage/_fs_storage_infra.py` | `f4d1e9ecd94dab2cb2e82ea7f65c85e09eefee34cfcc13ffde9db1adf2f4001f` | 一致 |
| `docs/gateflow/pr-197-r1-f4-goal-20260930.md` | `d1f374b9adb053761c66e9dd04e2a27ae6cdb4e299b715f70d9f91ee99d9d05e` | 一致 |
| `docs/gateflow/pr-197-r1-f4-plan-fix-20260930.md` | `c0d7cd213fc2b0f03ee63c0dca225dfccb0d34cd182abfbb45c197580cbdaccc` | 一致 |

## 实际工具退出、恢复与验证边界

| 操作 | 实际退出及影响 |
| --- | --- |
| pwd/branch/HEAD/status、AGENTS/skill/裁决/goal/候选、原 run_dir inventory/配置读取 | exit0；重要文件可读。组合输出曾截断，已按具体文档段落/旧事件解析补读；无以截断内容推断成功 |
| 本轮/旧轮 canary 与 expected 字节读取、原 JSONL 全量解析、原 last 值读取 | exit0；原读取/误报差异及本轮字节均验证；旧外层退出依据总控托管裁决 |
| 首核22 SHA、原候选字节一致、分支校验 | exit0；22/22一致，两原候选 SHA 匹配 |
| apply_patch 两候选 | 工具成功，无 shell exit 字段；只改上述 diff |
| 相对原件精确 diff、技术正文切片字节比对、22 SHA 复核、历史文件首末 SHA | exit0；全部断言通过，原件/原 raw runner未改 |
| plan 独立 `git diff --no-index --check <原件> <现文件>` | exit1、无输出；表示存在内容差异，无空白错误诊断，未冒称 exit0 |
| user-scope fix 独立同命令 | exit1、无输出；同上，不是产品或报告验证失败 |
| 新 artifact 首次独立 `git diff --no-index --check /dev/null <本文>` | exit3；10条 trailing whitespace，均为嵌入 unified diff 的空白上下文行单空格，不是候选内容错误；改用零上下文精确 diff 保留全部改动行，随后复查 |
| 新 artifact 修正后独立同命令 | 复查 exit1、无输出；新文件内容差异，无空白诊断；最终版本再次独立检查，结果登记于本轮 final-check.json |
| 本轮最后 literal/22 SHA/原证据/branch/HEAD/新报告检查 | exit0；22/22、两候选历史值/完整SHA/精确diff/技术正文、旧证据、本文本轮值均已断言匹配；最终记录于本轮 final-check.json，最后消息由本轮 canary 实读生成并另行断言 |

旧事件的全部非零仍保留并分类：item_25 exit2 为不存在 cn_download_runtime.py 的检索，后续真实 inventory / ingestion_runtime / download_contract / tools / tests 取证恢复；item_26 exit1 为 zsh 不存在 glob，item_27/28 改真实路径补读；item_38 exit1 无输出为新 artifact no-index 差异、无空白诊断。旧初次 pyright 的绝对 include 配置警告虽 exit0，不能称精确 include 生效；已纠正为相对 include/exclude=[]，strict 实际只 Found 1 源文件/0诊断，owner_probe 未纳入 strict，不证明生产新 API 验收。本轮不重跑这些 probe，也不把旧技术验证扩成本轮验证成功。

按本次明确授权，没有重跑 pytest、全量 pyright、owner/typeprobe、coverage 或真实下载/OCR。只有文档历史准确性修订，没有触发 README 职责变化；tests/README 保持只读。

## 风险分类、状态与唯一下一入口

| 风险/未覆盖 | 分类 | Owner / destination |
| --- | --- | --- |
| F4-PV01 历史误报 | fixed in current slice（作者文字修复；待独立验收） | 总控完整核验本文、最终消息、runner终态/退出/stderr/全事件，不自行关闭finding |
| 本轮外层退出/可信终态及完整 raw 流尚在途 | covered by later approved slice（本次交付收集/独立验收步骤） | 总控收集本轮托管91705；缺可信终态不能 accepted |
| F4 技术候选尚未双路复审/accepted，产品未实施 | covered by later approved slice | 总控独立验收本次报告后，冻结同版候选/current goal/source，MiMo/Kimi同时 Planreview；之后总控裁决，按既有流程实施 |
| F4-R01/R02、start/stream外部publication及其它WU | assigned to later work unit（沿用原候选分类） | 原候选列明 owner/destination；本次不改业务裁决、技术正文或风险归属 |

唯一下一入口：**总控独立验收本次报告修复交付 → 验收成立后冻结修订候选与当前输入 → MiMo/Kimi 同版双路 Planreview → 总控独立裁决**。没有自行 gatepass；本轮完成后停止，不派发或进入下一 gate。
